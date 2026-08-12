# Slice 2.3 corrective plan 独立复审（DeepSeek，独立 reviewer）

- Reviewer：DeepSeek（未参考任何 MiMo reviewer 结论；独立只读复审 corrective target）
- 日期：2026-08-12（生成 timestamp 20260812-140119）
- 目标计划：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- 目标计划 SHA-256：`281f0a753423df5142d76a9cf2597b143e8c32bea5f8d4c70a3e2c691b7f8e23`（已核对一致）
- 设计真源：`docs/plans/2026-08-10-investment-platform-restoration.md`（Slice 2.3 高层定义 §Slice 2.3 / §8.0 DAG / §6.3 evidence locator / §6.1 data-plane）
- 初审：`docs/reviews/plan-review-20260812-slice-2.3-source-connectors-health-deepseek.md`（FAIL 2H/2M/5L）
- Controller 纠偏：`docs/reviews/plan-fix-20260812-slice-2.3-source-connectors-health-codex.md`（13 项 finding 全部 ACCEPT）
- 基线：`0db6c7b63608a15cd157f842a5be772799fdacd9`（已核对 `git rev-parse HEAD` 一致）
- 性质：只读 plan re-review。未修改 target/master/code/tests；未联网/live/provider/Broker。

## 1. Reviewed target & scope

审阅 corrective target 全部 16 节，并对以下代码事实做直接核对（本轮重点证伪项）：

- `dayu/services/job_service.py`：JobExecutionHandlerProtocol（execute 两参数签名）、JobHandlerRegistry/JobExecutionRegistry（无 seal/count）、execute_claim（scope 校验 605、cancel_requested gate 637-638、八字段 request 构造 618-627）、enqueue registry gate 538-545；
- `dayu/investment/domain/jobs.py`：SafeJobErrorCode 现有 12 值（148-162）、JobExecutionRequest 八字段（1191-1244）、JobFailure retryable 校验（1342-1364）、_validate_receipt_combination（831-888）、JobEnqueueRequest（1018-1053）、JobHandlerDescriptor 七字段（973-1015）；
- `dayu/investment/storage/postgres_jobs.py`：claim（1090-1261）、heartbeat 只 UPDATE `job_attempts.lease_expires_at`（1320-1335/1389-1406）、job_leases 仅 release 时 UPDATE（3285）、`_lock_job_attempt_lease` 只验证 attempt.lease_expires_at 与 released_at（3155-3174）、fail() retryable 判定（1621-1624）、complete/fail cancel-intent/deadline 收敛（1473-1520/1583-1620）；
- `dayu/investment/domain/schedules.py`：ScheduleRegistrationRequest（373-422）、ScheduleDefinition（426-462）；
- `dayu/services/schedule_service.py`：_schedule_idempotency_key（354-378，schedule_id+schedule_version+scheduled_for）；
- `dayu/investment/storage/protocols.py`：ScheduleStoreProtocol 现有 9 方法（614-847），无 ensure_registered；
- `dayu/investment/storage/postgres_schedules.py`：register() create-only（ON CONFLICT DO NOTHING + conflict，1304-1391）；
- `dayu/fins/service_runtime.py`：execute_stream_command 嵌套 stream（3007-3026）、_iter_stream_events（3101-3137）、_build_pipeline_for_ticker（1981-1996）、resolve/validate_evidence_locator（2552-2590）；
- `dayu/fins/pipelines/sec_pipeline.py`（474-515 转发 download_stream、517+ download_stream_impl）、`dayu/fins/pipelines/cn_pipeline.py`（393/436）；`dayu/fins/ingestion/service.py`（FinsIngestionService.download_stream 105-115）；`dayu/fins/ingestion/pipeline_backends.py`（PipelineIngestionBackend.download_stream 84-124）；
- `dayu/fins/pipelines/sec_download_workflow.py`（FILING_STARTED 467、PIPELINE_COMPLETED payload={"result": final_result} 612-615、status ok/cancelled 610）、`sec_download_filing_workflow.py`（skip_reason 值域）、`cn_download_workflow.py`（_build_result status 可为 failed）；
- `dayu/fins/domain/evidence_locator.py`：DocumentLocatorPayload 存在（115）、LocatorKind.DOCUMENT（77）；
- migrations `0001_platform_foundation.py`（source_sync_runs UNIQUE(tenant_id, idempotency_key) 451、source_health_snapshots 弱二列 FK 490-492、subscription 三 partial index 412-430）、`0003_durable_jobs.py`（job_attempts UNIQUE 285-289、_downgrade_admission 932-971）、`0004_durable_schedules.py`（revision/down_revision、job_schedules UNIQUE(tenant_id, schedule_key) 132-133、occurrence UNIQUE 249-250、_TABLES 64）；
- `dayu/investment/storage/models_identity.py`（8 表）、`models_auth.py`（5 表）、`models_workspace_import.py`（2 表）→ ORM metadata 现共 15 表；
- `dayu/services/fins_service.py`（FinsService submit 入 Host 39-72、resolve/validate 179-213）；
- `dayu/services/startup_preparation.py`（_build_production_services_provider 616-676 三服务、PreparedHostRuntimeDependencies.fins_runtime 348/1518、host 构造 1470、FinsService 不在 startup 构造）；
- `dayu/startup/platform.py`（build_platform_composition 仅校验 key==platform_service_name，不校验服务集合）；
- `dayu/investment/composition.py`（_validate_registry_entry 349-392）。

## 2. Assumptions tested（结论摘要）

| 假设 | 结论 |
|---|---|
| provider/business outcome 一律 JobCompletion，commit 前 closed failure 才 JobFailure；每 Job 只写一条 producer run，后续 attempt 只重放（DS23-001/002 closure） | **成立**（§2.2/§6.3 与 execute_claim、store.fail retryable 判定、0001 UNIQUE(tenant_id,idempotency_key) 兼容） |
| 不得从 handler 返回 CANCELLED；PG cancel intent 由 JobStore 收敛（DS23-006 closure） | **成立**（§2.2；与 _validate_receipt_combination 831-888、fail/complete cancel-intent 分支一致） |
| trusted TenantScope：execute_claim 校验 scope==claim==request 并传原 scope，禁止重建（Controller §3.1） | **成立**（execute_claim 605 已有 claim!=scope 拒绝；八字段 request 与 claim 同 tenant） |
| live Job lease 是唯一租约真源；acquire/terminal 按 job->attempt->lease 锁序验证（DS23-003 closure） | **部分不成立**（F1：plan 要求验证 `job_leases.expires_at>clock`，但 heartbeat 从不更新该列；JobStore 自身只验证 attempt.lease_expires_at） |
| schedule ensure_registered：create-only register 保持、ensure ON CONFLICT DO NOTHING + 逐字段比较（Controller §3.2） | **成立**（ScheduleStoreProtocol 现有 9 方法 +1=10；register 已是 create-only；幂等键公式已含 schedule_id/version/scheduled_for） |
| Fins 只有 calendar date、no-change 合法、DownloadEvent/locator/aclose 由 Fins runtime 唯一核对（Controller §3.4/§3.5） | **成立**（filing_date/report_date 存在；PIPELINE_COMPLETED result 含 status；DocumentLocatorPayload 存在；skip_reason 值域与 §4.3 闭集一致） |
| 0005 exact DDL、composite FK、RLS/grants、downgrade fail-closed（Controller §3.6/§3.8） | **部分成立**（表数 24→27、ORM 15→18、down_revision、composite FK parent unique 均与代码一致；F3：两处 partial UNIQUE 缺 WHERE predicate） |
| nested async stream exact-once aclose（Controller §3.5） | **不成立**（F2：修改清单与 allowlist 漏 SecPipeline/CnPipeline.download_stream 转发层） |

## 3. Findings

### 1-未修复-[高]-plan §6.1 要求验证 `job_leases.expires_at>clock`，但 heartbeat 从不更新该列，且 JobStore 自身 live 判定只用 attempt.lease_expires_at；按字面实现慢源（Fins 时长 > lease_duration 900s 但 < job deadline）会被误判 lease 失效而永不收敛

- **位置**: 目标计划 §6.1「再按 tenant+job+attempt+attempt.fence 锁未 release 的 lease，验证 lease.token_sha256=attempt.lease_token_sha256 且 lease.expires_at>clock。heartbeat 延长 attempt/lease 后自动生效。」；§13.3 test_heartbeat_extended_live_job_lease_allows_source_terminal_commit。
- **问题类型**: 状态机漏洞 / 并发恢复风险 / 代码事实冲突
- **当前写法**: source repository 的 acquire/terminal commit 在锁 job_leases 行后要求 `lease.expires_at > clock`（该列属于 `job_leases`），并声称 heartbeat 延长 attempt/lease 后自动生效。
- **反例/失败场景**: 慢源 Fins 同步耗时 > 900s（lease_duration_seconds=900，§3.4）但 < job deadline（schedule 默认 job_deadline_seconds 可远大于 900）。Worker heartbeat 每周期只 UPDATE `job_attempts.lease_expires_at`（postgres_jobs.py:1320-1335/1389-1406），**从不更新 `job_leases.expires_at`**（该列仅在 claim 时写入 clock+lease_duration，postgres_jobs.py:1187-1207；唯一后续 UPDATE 是 release 的 released_at，3285）。JobStore 自身的 live 判定 `_lock_job_attempt_lease`（3100-3189）也只检查 `attempt.lease_expires_at > clock` 与 `released_at IS NULL`，**不检查 job_leases.expires_at**（3155-3174）。因此：900s 后 `job_leases.expires_at` 必然过期，而 attempt lease 仍被 heartbeat 续约、JobStore 认为 lease 有效。若 source repository 按 plan §6.1 字面验证 job_leases.expires_at，则 acquire 或 terminal commit 会误判 lease_lost/job_not_live → 抛 SOURCE_INTERRUPTED/零 source row → 下一 attempt 重做同一 Fins 工作 → 3 次 attempt（max_attempts=3）内永不收敛，且每次 Fins 工作被丢弃重做。若实现者改用 attempt.lease_expires_at（与 JobStore 一致），则偏离 plan 文字，§13.3 的 heartbeat 测试将暴露该不一致。
- **为什么有问题**: plan §6.1 的 lease 校验条件与代码事实（heartbeat 不续约 job_leases.expires_at；JobStore 判定以 attempt.lease_expires_at 为准）直接矛盾。slow-source 是 plan 自己承认的真实场景（§16 residual「Provider 读取不是 exactly-once」「Fins 现有 date-only 元数据」），且 §11 STOP「source operation 保存自有 authoritative lease」明确反对自造 lease 语义——plan 却在 source repository 引入了与 JobStore 不一致的第二套 lease 判定。
- **直接证据**: plan §6.1 原文；postgres_jobs.py:1187-1207（claim 写 job_leases.expires_at）、1320-1335/1389-1406（heartbeat 只 UPDATE job_attempts）、3155-3174（_lock_job_attempt_lease 只检查 attempt.lease_expires_at + released_at）、3285（job_leases 唯一 UPDATE 是 release）；plan §3.4 lease_duration_seconds=900。
- **影响**: 生成错误代码（慢源被误判 lease_lost）/ 有界重试形同虚设 / 健康状态无法收敛 / 后续返工。
- **建议改法和验证点**: (a) §6.1 明确 source repository 的 live lease 判定与 JobStore 完全一致：锁 job_runs（state=leased、cancel_requested_at IS NULL、deadline_at>clock、current_attempt_number=request.attempt_number）→ 锁 job_attempts（id=request.attempt_id、state=leased、attempt.lease_expires_at>clock）→ 锁 job_leases（released_at IS NULL、token_sha256=attempt.lease_token_sha256），**删除/改写「lease.expires_at>clock」为「attempt.lease_expires_at>clock」**；(b) 若产品真的需要 job_leases.expires_at 参与判定，则必须先改 heartbeat 同步续约该列（触碰 postgres_jobs.py，超出 allowlist → 回 Controller），二选一不得并存；(c) 验证点：§13.3 test_heartbeat_extended_live_job_lease_allows_source_terminal_commit 必须用真实 heartbeat 语义（只续 attempt）构造「Fins 时长 > 900s 但 < deadline」的 PG fault 测试，断言 terminal commit 成功且不依赖 job_leases.expires_at。
- **修复风险（低）**: 只是澄清判定真源，不新增机制；与 JobStore 现有一致。
- **严重程度（高）**:

### 2-未修复-[中]-§4.4 nested aclose 修改清单与 §11 allowlist 漏掉 SecPipeline/CnPipeline 的 download_stream 转发层，实现者无法在 allowlist 内闭合 exact-once aclose

- **位置**: 目标计划 §4.4「因此同时修改 dayu/fins/service_runtime.py、dayu/fins/ingestion/service.py、dayu/fins/ingestion/pipeline_backends.py，每层把 inner stream 保存为唯一局部 owner，并在 finally await inner.aclose()；禁止依赖 GC」；§11 allowlist（无 dayu/fins/pipelines/sec_pipeline.py、cn_pipeline.py）；§15 STOP「nested async stream 没有 exact owner/aclose」。
- **问题类型**: 不可直接实施 / 测试缺口 / allowlist 冲突
- **当前写法**: sync_worker_source（§4.1）复用 `_build_pipeline_for_ticker(request.ticker)` 与 `pipeline.download_stream`。真实 generator 链为：service_runtime（sync_worker_source / execute_stream_command）→ `SecPipeline.download_stream`（sec_pipeline.py:474-515，async for 转发 `self._ingestion_service.download_stream`）→ `FinsIngestionService.download_stream`（ingestion/service.py:105-115，转发 backend）→ `PipelineIngestionBackend.download_stream`（pipeline_backends.py:114-124，转发 download_stream_impl）。plan §4.4 只授权修改三层（runtime / ingestion.service / pipeline_backends），**未覆盖 SecPipeline/CnPipeline 的 download_stream 转发层**，而该层同样持有 inner generator 且无 finally aclose。
- **反例/失败场景**: Python async generator 的 `aclose()` 只会关闭被调用者的 generator 帧，**不会**级联关闭其内部 `async for` 持有的 inner generator（`async for` 不隐式 close）。实现者按 §4.4 只改三层后：sync_worker_source 对 `pipeline.download_stream(...)` 返回的 SecPipeline generator 调 aclose()，SecPipeline.download_stream 内部挂起的 FinsIngestionService generator 不会被关闭 → 违反「禁止依赖 GC」与 STOP「nested async stream 没有 exact owner/aclose」；若实现者为了闭合而修改 sec_pipeline.py/cn_pipeline.py，则触碰 §11 allowlist 之外文件 → 触发 STOP 回 Controller。两种路径都使实现者卡住，或留下未关闭的内层 generator（资源泄漏 + §13.2 test_runtime_ingestion_and_backend_streams_close_exactly_once_on_every_exit_path 无法按现有 allowlist 构造通过）。
- **为什么有问题**: §4.4 声称的「每层」与实际嵌套层数（4 层，含 sec_pipeline/cn_pipeline 转发层）不一致；§11 又禁止修改该层所在文件。plan 在自身要求的 STOP 条件与 allowlist 之间自相矛盾，不是 code-generation-ready。
- **直接证据**: sec_pipeline.py:474-515（async def download_stream + async for + yield，无 finally aclose inner）、cn_pipeline.py:393-435；ingestion/service.py:105-115、pipeline_backends.py:114-124；plan §4.4 三文件清单、§11 allowlist、§15 STOP、§13.2 对应命名测试。
- **影响**: 实现阻塞（STOP）/ 资源泄漏 / 验收测试无法闭合 / 后续返工。
- **建议改法和验证点**: (a) 把 `dayu/fins/pipelines/sec_pipeline.py` 与 `dayu/fins/pipelines/cn_pipeline.py`（仅 download_stream 转发层）加入 §11 allowlist，并在 §4.4 修改清单中显式列入——每层（含 Sec/Cn pipeline 转发层）保存 inner stream 为唯一局部 owner 并 finally aclose exactly once；(b) 或明确 sync_worker_source 不经过 Sec/Cn pipeline 包装层、直接使用 FinsIngestionService 链，并同步调整 §4.1「复用 pipeline.download_stream」文字；(c) 验证点：test_runtime_ingestion_and_backend_streams_close_exactly_once_on_every_exit_path 断言四层 generator 的 finally aclose 各恰一次（用 recording wrapper 而非 sleep）。
- **修复风险（低）**: 纯 allowlist + 修改清单增量；不改业务语义。
- **严重程度（中）**:

### 3-未修复-[中]-§8.2 两处 partial UNIQUE 未指定 WHERE predicate，0005 exact DDL 不可直接生成

- **位置**: 目标计划 §8.2「source_sync_runs 新增 … partial UNIQUE(tenant_id,job_run_id)、partial UNIQUE(tenant_id,job_attempt_id)」；§13.4「0005 exact 27-table/columns/FK/CHECK/index…catalog」。
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: 只写「partial UNIQUE(tenant_id, job_run_id)」「partial UNIQUE(tenant_id, job_attempt_id)」，未给出 WHERE 子句；而 source_sync_runs 的 job_run_id/job_attempt_id 均为 nullable（旧 0001 row 全 NULL，plan §8.2 明确「nullable 旧 row 仍兼容」）。
- **反例/失败场景**: PostgreSQL partial unique index 必须带 WHERE 才有意义。实现者若写成无 predicate UNIQUE(tenant_id, job_run_id)，则 NULL 语义（NULL != NULL）会让旧 row 不冲突但新 row 约束行为取决于 predicate；若补 `WHERE job_run_id IS NOT NULL`，则该 index 强制「同 job 至多一行非 NULL run」——这与「每 Job 只写一条 producer run」的 §6.3 语义一致但**用途未说明**（约束 vs 查询索引），且 downgrade 恢复（§8.4「撤 job_attempts 新 unique」等逆序描述）没有对应这些 partial index 的处置。实现者必须自行发明 predicate 与命名，0005 exact catalog 验收（§13.4）无法对照计划生成期望。
- **为什么有问题**: 0005 被要求 exact DDL（表数、列、FK、CHECK、index、RLS、trigger、grant 逐项冻结），partial index 缺少 predicate/用途/命名即不是 exact 契约；与同一段落其它约束（如带 WHERE 的 `UNIQUE(tenant_id,subscription_id,health_state_version) WHERE health_state_version IS NOT NULL`）形成不一致的规格粒度。
- **直接证据**: plan §8.2 原文；0001_platform_foundation.py:412-430（subscription 三 partial index 均显式带 WHERE，可作惯例参照）；0003 中 partial unique 同样带 WHERE。
- **影响**: 实现 Agent 自行发明 DDL / 0005 catalog 验收失真 / 后续返工。
- **建议改法和验证点**: (a) 明确两处 partial UNIQUE 的精确 predicate（建议 `WHERE job_run_id IS NOT NULL` / `WHERE job_attempt_id IS NOT NULL`）与用途（约束 vs 索引）；若无约束意图仅作查询索引，应改为普通 index 并说明；若仅靠 §6.3 应用层保证每 job 一行，则删除这两条并说明不依赖 DB 约束；(b) downgrade 逆序处置补上这两条；(c) 验证点：0005 catalog 测试直接引用计划给出的 predicate/命名。
- **修复风险（低）**:
- **严重程度（中）**:

### 4-未修复-[低]-execute_claim 的 cancel_requested gate 会把「已提交 source terminal 的 JobCompletion」转成 HANDLER_REJECTED，plan §2.2/§2.3 未显式声明该竞态

- **位置**: 目标计划 §2.2「下列 source outcomes 均以 JobCompletion 返回」、§2.3 crash residual、§6.2 step 8-9；代码事实 job_service.py:637-638「`if isinstance(result, JobCompletion) and cancel_requested: return rejected`」。
- **问题类型**: 状态机漏洞（窄窗口）/ 契约未声明
- **当前写法**: plan 只约束 handler 不返回 CANCELLED、PG cancel intent 由 JobStore 收敛；未提及 execute_claim 在 handler 返回 JobCompletion 后再次检查 Worker 侧 cancel signal 并整体替换为 HANDLER_REJECTED（non-retryable）。
- **反例/失败场景**: handler 在 terminal transaction 中已提交 source run/health/operation terminal 并返回 JobCompletion（按 §2.2 合法）；随后 Worker drain 竞态使 `cancellation.is_cancel_requested()` 在 execute_claim 637-638 处为 True（cancel signal 置位但 PG 无 cancel intent、未到 deadline——Worker 侧 signal 与 PG intent 非同一时刻）→ execute_claim 返回 HANDLER_REJECTED（non-retryable）→ store.fail 以非重试失败终结 job，而 source truth 已提交。这与 §2.3 crash residual 的「Job envelope 可与已持久化 source outcome 不同」兼容，但 plan 只把它归因于「deadline/cancel/max attempts 使 JobStore 终结」，未声明「execute_claim gate 主动替换 JobCompletion」这一特定竞态，且 §13.3 无对应命名测试。
- **为什么有问题**: 不是正确性 blocker（residual 可覆盖），但 §2.2 声称「JobCompletion 表示已可靠持久化」与 execute_claim 的替换行为并存时，operator 看到 Job FAILED(HANDLER_REJECTED) 而 source truth 已提交，审计语义需要 plan 显式声明，否则实现者/后续 slice 会误以为是 handler 缺陷。
- **直接证据**: job_service.py:637-638；plan §2.2/§2.3/§6.2/§16（residual 2 只描述 crash/终结，未列该 gate 路径）。
- **影响**: 语义未声明导致误判 / 测试缺口（窄竞态无覆盖）/ 审计歧义。
- **建议改法和验证点**: (a) 在 §2.3 或 §16 residual 显式补充：handler 返回 JobCompletion 后若 Worker 侧 cancel signal 置位，execute_claim 将替换为 HANDLER_REJECTED（non-retryable），source truth 保留、Job envelope 可失败，属接受的窄窗口 residual；(b) §13.3 增补命名测试（test-owned gateway 注入 cancel signal 在 handler 返回后置位，断言 Job FAILED 且 source run 行保留）或明确标注该窗口不测试。
- **修复风险（低）**:
- **严重程度（低）**:

## 4. 已验证无问题的重点区域

- **provider outcome / JobCompletion / crash residual 主体（DS23-001/002 closure）**：每 Job 一条 producer run + idempotency_key=`source-sync-attempt:v1:{job_id}:{producer_attempt_id}` 与 0001 `UNIQUE(tenant_id, idempotency_key)`（0001:451）兼容；后续 attempt 只重放、不插第二行；`source_sync_run` 新 row 的 11 core 字段（除 latest_source_observed_date）all-or-none 与 §8.2 CHECK 自洽；JobFailure 闭集（SOURCE_INVALID/BUSY/INTERRUPTED/REPOSITORY_FAILURE）不与 JobFailure retryable 校验（jobs.py:1355-1364）冲突，且 handler 返回 CANCELLED 会被 _validate_receipt_combination（831-888）拒绝——plan 已闭环。
- **trusted TenantScope / registry seal**：execute_claim 已持 scope 且已有 claim!=scope 拒绝（605）；八字段 request 从 claim 构造不新增字段；seal/count 是 registry 纯新增，不影响 execute_claim 与 enqueue（get 只读）；「seal 后 exact replay 拒绝」与 append-only 语义一致。
- **schedule ensure_registered**：ScheduleStoreProtocol 现有 9 方法 → +1=10 与「精确十方法」一致；register() 保持 create-only（postgres_schedules.py:1304-1391）与「ensure 不得 DO UPDATE」一致；occurrence 幂等键公式已含 schedule_id/version/scheduled_for（schedule_service.py:354-378），与「不同 occurrence 不同 Job」、0004 `UNIQUE(tenant_id, schedule_id, schedule_version, scheduled_for)`（249-250）一致；ScheduleRegistrationRequest 字段覆盖 ensure 逐字段比较所需全部 immutable 字段。
- **Fins date / no-change / DownloadEvent / locator**：Fins 仅持久化 filing_date/report_date（`_fs_source_document_core.py:504-527`），date + calendar-day freshness 方向正确；`documents=() 且全 skipped/total=0 → complete/no_change/healthy` 与 SEC/CN 事件流（summary 计数、PIPELINE_COMPLETED result 含 status）兼容；FILING_STARTED（sec:467 / cn:253）、FILING_COMPLETED/FAILED terminal 一一对应可核对；skip_reason 值域（not_modified/rejection_registry/6k_filtered/candidate_not_found/pdf_sha256_matched/remote_fingerprint_matched/already_downloaded_complete/source_fingerprint_matched/remote_files_equivalent）与 §4.3 reused/ignored 闭集一致；DocumentLocatorPayload（evidence_locator.py:115）与 LocatorKind.DOCUMENT 存在，resolve/validate 已具备；PIPELINE_COMPLETED.payload 精确含 result、status=ok/cancelled/failed（sec 610/cn 124,145,337,346）与 §4.3 核对条件一致。
- **0005 DDL 骨架**：表数 24→27（0001 13+0002 2+0003 7+0004 2）、ORM metadata 15→18（identity 8+auth 5+workspace 2）、down_revision=`0004_durable_schedules`、job_attempts 新增 `UNIQUE(tenant_id, job_run_id, id)` 支撑 composite FK parent、snapshot 弱二列 FK 替换三列、health_state_version 无 predicate 五列 UNIQUE 作 alert FK parent、0003/0004 downgrade admission 先例（pg_depend 外部依赖 preflight）均与代码事实一致；RLS/grants/guard 设计与 0001 `_APP_APPEND_TABLES` 惯例兼容。
- **allowlist / 测试 / STOP**：§11 文件清单与 master 2.3 allowlist 及 corrective 扩展一致（更严格）；S23 切片顺序、crash cut 双 seam（test-owned commit barrier + test-owned gateway 不调 complete）、禁 sleep/真实 provider、§15 STOP 与 §16 residual 诚实完整（F1/F2 的修正应并入 STOP/residual 说明）。

## 5. Open questions

- O1（并入 F1）：live lease 判定真源最终取 attempt.lease_expires_at 还是要求 JobStore 同步续约 job_leases.expires_at（后者需越界改 postgres_jobs.py 并扩 allowlist）——需 Controller 裁决并唯一化进 §6.1。
- O2（并入 F2）：sync_worker_source 的 stream 获取路径是「pipeline.download_stream（含 Sec/Cn 包装层）」还是「直接 FinsIngestionService 链」——决定 §4.1 文字与 §11 allowlist 的最终形态。
- O3（并入 F3）：两处 partial UNIQUE 的 predicate/用途（约束 vs 索引）需唯一化。

## 6. Residual risks / 建议去向

- F1 未修复前，slow-source 收敛只依赖 STOP 兜底；建议把「source 侧 live lease 判定 == JobStore 判定」作为明确契约并加 PG fault 测试。
- F2 未修复前，aclose 验收测试无法按现有 allowlist 构造通过；建议在 corrective 中直接扩展 allowlist。
- 其余 residual（provider at-least-once read、schedule disabled 时 no-op Job、semantic alert 仅持久化、date-only freshness、Redis hint）与 §16 一致，无需额外跟踪。
- 建议 F1/F2/F3 的修正唯一化进 target 后执行 dual re-review，再解除 implementation freeze。

## 7. Final plan review conclusion

**FAIL**（open H/M/L = **1/2/1**）

F1 是代码事实与计划契约的确定性冲突（heartbeat 不续约 job_leases.expires_at、JobStore 判定只用 attempt.lease_expires_at），按字面实现会让慢源同步在 3 次 attempt 内永不收敛；F2 使 aclose 修复在 §11 allowlist 内无法闭合（要么 STOP、要么留泄漏）；F3 使 0005 exact DDL 无法直接生成。三项修复唯一化进 target 并通过 dual re-review 前，Slice 2.3 不应进入 implementation gate。
