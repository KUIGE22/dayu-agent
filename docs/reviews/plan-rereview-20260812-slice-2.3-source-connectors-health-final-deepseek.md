# Plan Re-Review（Final / Independent DeepSeek）：Slice 2.3 数据源连接器、同步收据与健康状态

- 日期：2026-08-12T17:16:33+0800（系统时钟）
- Reviewer：DeepSeek（独立 reviewer，非 Controller / 非 implementation agent）
- Gate：independent-final-plan-review
- 分支：`codex/investment-platform`；基线：`0db6c7b63608a15cd157f842a5be772799fdacd9`（HEAD 与基线一致）
- 审查目标（唯一）：
  `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- **Reviewed SHA-256**：`96bceb321464223c9022af25905ca36c4bfe5cdca371111384567acb396ee4f0`
  - 审查前验证：`96bceb32...ee4f0` ✅
  - 审查后复核：`96bceb32...ee4f0` ✅（无 drift，未 STOP）
- 审查约束：未读取 `docs/reviews/` 下任何 prior review/fix artifacts；未读取其他 reviewer 结论；无实现/测试/commit/push/PR/网络动作；唯一可写文件为本 artifact。

## 1. 审查范围与方法

对目标 plan 全文（2288 行）做对抗性 review，并将 plan 中每个可证伪的代码事实 claim 与真实源码交叉验证：

- 读根 `AGENTS.md`（架构硬约束、编码硬约束、schema 变更、测试/文档规则）并逐条对照 plan；
- 验证 60+ 个代码事实点：contracts（`dayu/investment/domain/jobs.py`、`dayu/services/job_service.py`、`dayu/investment/storage/protocols.py`、`dayu/investment/composition.py`、`dayu/services/startup_preparation.py`、`dayu/services/schedule_service.py`）、Fins（`service_runtime.py`、`pipelines/sec_pipeline.py`、`cn_pipeline.py`、`download_events.py`、`sec_download_event_mapping.py`、`sec_download_source_upsert.py`、`ticker_normalization.py`、`domain/evidence_locator.py`、`domain/document_models.py`、`storage/repository_protocols.py`）、migrations 0001–0004、`models_identity.py`、集成测试目录、CI workflows；
- 三个探索子代理（explore-1/2/4，均被明确禁止读取 `docs/reviews/`）独立收集事实，主 agent 亲自复核关键文件；
- 专项攻击面：架构边界/过度耦合、纯 DTO 与精确签名、manual/schedule response-loss 恢复、Fins DownloadEvent/date/no-change/locator/aclose、Source acquire/takeover/replay 与 async-to-sync 桥（FOR UPDATE NOWAIT / 55P03 / PONR / cancellation）、0005 精确 DDL/object manifest/FK lineage/CHECK/RLS/grants/upgrade/downgrade、startup explicit-vs-auto provider、allowlist/slices/命名测试/coverage/CI/STOP。

## 2. 被验证的关键事实（plan claim vs 真实代码）

以下全部一致（`✅`），按 plan 章节组织：

### 2.1 Job/registry/scope 契约（§2.2、§3.1、§3.4、§9）
- ✅ `JobExecutionHandlerProtocol` 当前为二参数 `execute(request, cancellation)`（`job_service.py:151-155`），plan 的三参数全量替换 claim 成立；production handler 当前为零个（仅协议桩 `job_service.py:133`），测试 fake/stub 恰 3 个（`test_job_service.py:903/980`、`test_postgres_jobs.py:141`），替换面与 plan 描述一致。
- ✅ `JobExecutionRequest` 精确八字段（`jobs.py:1209-1216`）；`execute_claim` 已持有 scope 且已有 `claim.tenant_id != scope.tenant_id` 拒绝（`job_service.py:605`）。
- ✅ `_handler_rejected_failure()` 存在（`job_service.py:1342`）；既有 `JobCompletion + cancel_requested -> rejected` 后置门存在（`job_service.py:637-638`），与 §2.3/§3.1 新增 CANCELLED gate 相容。
- ✅ `SafeJobErrorCode.REPOSITORY_FAILURE='repository_failure'` 已存在（`jobs.py:162`）；`JobFailure(safe_error_code, retryable)` 构造期已有不可重试集合校验（`jobs.py:1355-1364`）。
- ✅ `JobHandlerDescriptor` 七字段（`jobs.py:986-992`）；`JobEnqueueRequest` 五字段（`jobs.py:1030-1034`）；`JobEnqueueReceipt` 五字段含 `idempotency_reused`（`jobs.py:1069-1073`），plan §3.4 重建 receipt 语义可实施。
- ✅ `CanonicalJobDocument`（schema_name/schema_version/canonical_bytes/sha256，`jobs.py:399-412`）与 `build_canonical_document(value, *, schema_name, schema_version)`（`jobs.py:602`）存在；`JobIdempotencyRecord` 当前不存在（新增，`grep` 零匹配）。
- ✅ `JobStoreProtocol` 当前 14 方法（`protocols.py:313-612`），无 `get_by_idempotency_key`（新增）；`ScheduleStoreProtocol` 当前 9 方法（`protocols.py:614-850`），+2 = 精确 11 与 plan §5.2 一致。
- ✅ `JobHandlerRegistry`（`job_service.py:264`）与 `JobExecutionRegistry`（`job_service.py:318`）当前均无 seal/is_sealed/count 成员，plan §3.1 为纯新增。
- ✅ `JobClaim` 字段（`jobs.py:1137-1162`）含 worker_id/lease，但 handler 收到的八字段 request 不含它们，与 §3.1 "lease/fence/raw token/worker id 永不进入 handler" 一致。

### 2.2 Schedule/startup/composition（§3.3、§5.2、§10）
- ✅ `_validate_croniter_expression` 存在（`schedule_service.py:164`）；`ScheduleRegistrationRequest`（`schedules.py:373-395`）与 `ScheduleDefinition`（`schedules.py:426-462`）字段与 plan §3.2.1 兼容；`ScheduleMisfirePolicy` 唯一成员 `COALESCE_ONE`（`schedules.py:74-77`）；`ScheduleInputError/ScheduleVersionConflictError/ScheduleRepositoryError` 均已定义。
- ✅ `postgres_schedules.py register()` 为 create-only `ON CONFLICT (tenant_id, schedule_key) DO NOTHING`（`postgres_schedules.py:1350`），plan §5.2 ensure_registered 与既有 register 并存方案与现状相容。
- ✅ `_default_provider_or_fail`（`startup_preparation.py:733`）与 `_build_production_services_provider`（`startup_preparation.py:616`）存在；当前 auto-provider mapping 精确三项 `investment_identity/durable_jobs/durable_schedules`（`startup_preparation.py:726-730`），plan 扩为四项（+`investment_sources`）与现状一致；explicit provider 分支直接返回注入 provider（`startup_preparation.py:765-766`）。
- ✅ `DefaultFinsRuntime` 在 `startup_preparation.py:1459` 无条件以 `create()` 构造并持有 `source_repository`，与 plan §10 explicit-provider 路径 "既有 Host 所需 DefaultFinsRuntime 仍按同一 baseline 构造、但不装配 source connector/FinsService" 一致。
- ✅ `PlatformServiceProtocol`（`composition.py:60`）与 `PlatformComposition` 严格校验（`composition.py:272-394`）支持新增 `PlatformSourceSyncServiceProtocol`/`investment_sources`。

### 2.3 Fins 契约与事件流（§3.2.2、§4.1-§4.4）
- ✅ `DefaultFinsRuntime` 3144 行（plan "超过 3000 行" 成立）；`_build_pipeline_for_ticker` 存在（`service_runtime.py:1981`）；`FinsService/FinsServiceProtocol` 当前无 `sync_worker_source`（新增）。
- ✅ sec/cn `download_stream` 签名与 plan §4.1 `FinsSourceSyncDownloadPipelineProtocol` 完全一致（`sec_pipeline.py:474`、`cn_pipeline.py:393`，含 keyword-only `cancel_checker: Callable[[],bool]`）。
- ✅ `dayu.contracts.cancellation.CancelledError` 存在（`cancellation.py:9`）；FinsRuntime 既有 `cancel_checker` 下传先例存在（`service_runtime.py:690` 等）。
- ✅ `DownloadEvent` 结构/事件类型齐全（`download_events.py:16-45`，含 FILING_STARTED/COMPLETED/FAILED、FILE_DOWNLOADED/SKIPPED/FAILED、PIPELINE_COMPLETED、COMPANY_RESOLVED）。
- ✅ FILING_STARTED identity 字段与 plan §4.3 逐项吻合：SEC 含 form_type/filing_date/report_date/accession_number（`sec_download_workflow.py:466-477`）；CN/HK 含 form_type/filing_date/fiscal_year/fiscal_period/source_id（`cn_download_workflow.py:252-263`）。
- ✅ `filing_result` nested 结构（document_id/status downloaded/skipped/failed/skip_reason/reason_code）由 `build_download_filing_event_payload` 构造（`sec_download_event_mapping.py:39-55`）；PIPELINE_COMPLETED `payload["result"]`（status ok/cancelled/failed、filters forms/start_dates/end_date/overwrite、filings、summary）由 `SecPipeline._build_result`（`sec_pipeline.py:2001-2017`）/ CN `_build_result`（`cn_download_workflow.py:675-715`）构造。
- ✅ skip reason 闭集全部真实存在于代码：already_downloaded_complete/source_fingerprint_matched/remote_files_equivalent（`sec_pipeline.py:1002/1031/1036`）、not_modified、remote_fingerprint_matched/pdf_sha256_matched（`cn_download_filing_workflow.py:1206/1159`）、rejection_registry/6k_filtered（`sec_download_filing_workflow.py:231/337`）、candidate_not_found（`cn_download_workflow.py:522`）。
- ✅ `FileObjectMeta` 存在（`document_models.py:28`），FILE_* 事件 payload 携带 `file_meta`（`sec_download_event_mapping.py:158-194`），与 plan §4.3 "FILE_* 只校验 order/ticker/document_id/cap、忽略 payload" 前提一致。
- ✅ `EvidenceLocatorProjection` 恰 11 个 public 字段、`to_json()` 不含 schema_version（`evidence_locator.py:318-328,357-373`）；`DocumentLocatorPayload` 为空 dataclass、`to_dict()` 返回 `{}`（`evidence_locator.py:114-134`），与 plan §3.2.2 "locator_payload 精确等于空 object {}" 一致。
- ✅ `SourceDocumentRepositoryProtocol.get_source_meta/get_primary_source` 存在（`repository_protocols.py:148-185`）；`SourceKind.FILING` 存在（`fins/domain/enums.py`）。
- ✅ source meta.json 实际写入 `form_type/filing_date/ingest_complete/is_deleted/deleted_at/document_version/source_fingerprint`（`sec_download_source_upsert.py:202-214`），plan §4.3 reused 判定（ingest_complete/not deleted/form/date/window identity）可实施。
- ✅ 嵌套 generator 链确认：sec/cn `download_stream` 以 `async for ... yield` 转发 `_ingestion_service.download_stream`（`sec_pipeline.py:505-515`）→ backend（`pipeline_backends.py:84-114`）→ `download_stream_impl` → workflow async generator，plan §4.4 的 aclose 修改前提（外层 aclose 不自动关闭内层）与 8 文件 owner 链成立。
- ✅ `normalize_ticker` 输出形态（US/market=US/exchange=None、HK→HKEX、CN→SSE/SZSE，`ticker_normalization.py:84-98`）与 plan §4.2 closed map 的目标形态一致；MIC 值域（XHKG/XSHG/XSHE 精确、US 允许任意 4 位大写 MIC）与既有 `workspace_import.py:379-403` 校验兼容。

### 2.4 存储/迁移（§6、§8）
- ✅ migration 链 `0001→0002→0003→0004`（down_revision 逐个确认）；0001=13 表、0002=2、0003=7（含 job_attempt_receipts/job_events）、0004=2，合计 24 表，与 plan "24→27" 精确一致。
- ✅ `PlatformBase.metadata` 当前恰好 15 表（models_identity 8 + models_auth 5 + workspace_import 2），与 plan "15→18" 一致；Job/Schedule raw SQL 表确实不在 ORM metadata。
- ✅ 0001 `source_sync_runs` 11 列 / `source_health_snapshots` 10 列（`0001_platform_foundation.py:433-507`），与 plan §8.2 新增 14 列 / health_state_version 不冲突；0001 弱 FK `(tenant_id,sync_run_id)` 存在（`:490-492`），0005 的三列替换前提成立。
- ✅ 0001 三个 partial unique index 的 baseline shape 与 plan §8.5 preflight claim 逐字义相等（`0001_platform_foundation.py:412-429`）。
- ✅ 0001 grants：`source_sync_runs/source_health_snapshots` 属 `_APP_APPEND_TABLES` 仅 SELECT/INSERT（`:69,563-564`），且 0001 无 trigger（grep 零匹配），0005 安装 UPDATE/DELETE immutable guards 的必要性成立。
- ✅ 0001 RLS `tenant_isolation` policy 命名存在（`:594`）；0003 已有 trigger 先例（`job_leases_single_release` 等，`0003_durable_jobs.py:386-406`）。
- ✅ `job_runs` 有 `current_attempt_number`（`0003:191`）无 `current_attempt_id`；含 `cancel_requested_at/payload_sha256/request_fingerprint/deadline_at/available_at`；`job_attempts` 含 `lease_expires_at/fence/lease_token_sha256/state`（`0003:260-300`）；`job_leases` 含 `expires_at/acquired_at/released_at`（`0003:332-390`），且 heartbeat 只更新 `job_attempts.lease_expires_at` 不更新 `job_leases.expires_at`（`postgres_jobs.py:1320-1406`），与 plan §6.1 的 live 判定规则（不得读 `job_leases.expires_at`）完全一致。
- ✅ `job_attempts` 当前无 `(tenant_id,job_run_id,id)` UNIQUE，0005 新增 `uq_job_attempts_tenant_job_run_id_v2` 为纯新增且作为 FK parent 必要。

### 2.5 测试/CI/文档（§11-§15）
- ✅ 测试文件存在性：`tests/investment/test_architecture_boundaries.py`（含纯层 forbidden dayu.fins 规则 `:71-91`）、`test_platform_migrations.py`、`test_identity_repositories.py`；`tests/integration/investment/` 下 `test_platform_migrations_postgres.py/test_identity_repositories_postgres.py/test_postgres_jobs.py/test_postgres_schedules.py/test_fins_s3_blob_repository_minio.py` 均存在；`test_postgres_sources.py/test_source_sync_job.py` 不存在（plan 中为新建，与 §11 allowlist 一致）。
- ✅ `ci-pr-extended.yml` 现有 5 个独立 pytest 进程 + aggregate `--ignore` 结构，与 plan §14 Gate 2/3 扩为 8 lane 的模式一致；既有 pinned postgres/redis digest 存在。
- ✅ 五份 README（根/dayu/fins/investment/tests）均存在，plan §11 的 README 更新在职责范围内。

## 3. Findings（H/M/L）

经全部上述事实点交叉验证与对抗性状态机审查（并发 NOWAIT 序列、PONR 后 outer cancel 不可覆盖 durable decision、clock_timestamp 单次读取 + GREATEST formula、takeover/stale 判定、response-loss 恢复、0005 preflight/downgrade 逆序、RLS/grants/guards），**未发现 material finding**。

open H/M/L = **0 / 0 / 0**。

### 3.1 信息性观察（不构成 material finding，建议实施时注意）

- **O1（§4.2 preflight MIC map 的真源）**：plan 的 closed map（XNAS/XNYS→US/None、XHKG→HK/HKEX、XSHG→CN/SSE、XSHE→CN/SZSE）是 plan 新增的 MIC→期望形态表；`normalize_ticker` 消费的是 ticker 前缀 token（`NASDAQ/NYSE`，`ticker_normalization.py:54`）而非 MIC 字面量，`workspace_import.py:379-403` 对 US 仅要求 4 位大写 MIC。行为已闭合（"其它 MIC → unsupported_market"），但实现时应以 `workspace_import` 既有校验为 MIC 值域基线，避免为 preflight 另造第三张映射表；建议在实现说明中显式记录 US MIC 子集决策（XNAS/XNYS 之外如 `NYSE`/`ARCX`/`BATS` 一律 unsupported_market 的既有意图已由 §4.2 文本覆盖）。
- **O2（§2.2 JobFailure 不可重试矩阵）**："反向组合构造即拒绝" 需要把 `SOURCE_INVALID` 加入既有 `JobFailure.__post_init__` 的不可 retryable 集合（`jobs.py:1357-1363`）；plan 未显式点名该代码改动点，但 §13.1 命名测试 `test_safe_job_source_error_members_values_retryability_and_persisted_receipt_matrix_are_exact` 强制正确行为，且 `jobs.py` 在 §11 allowlist 内，不构成实施缺口。

## 4. 压测的假设清单（均未被证伪）

1. 二参数 handler 全量替换的迁移面（0 production handler + 3 fake + 新 source handler）成立；
2. ScheduleStore 9→11 方法、JobStore 新增 get_by_idempotency_key 为纯扩展；
3. source terminal 与 Job terminal 两事务的 crash residual 被显式接受并有测试路径（`test_crash_after_source_terminal_before_job_complete_replays_when_next_attempt_exists` 等）；
4. `job_leases.expires_at` 审计语义、heartbeat 仅延长 attempt lease，与现有 PostgresJobStore 行为一致；
5. 0005 的 parent-key-before-child-FK 顺序、downgrade 逆序、admission fail-closed，与 0001-0004 既有 catalog/ACL/RLS 相容；
6. 0005 安装 UPDATE/DELETE immutable guards 对 append-only 表是真实缺口修复（0001 无 trigger）；
7. explicit provider 分支保持 identity、mapping、registry 不变，DefaultFinsRuntime 仍按 baseline 构造（新增 eager component 为 `repr=False, compare=False` 引用，无独立 close 顺序），与现状装配路径一致；
8. CI 扩为 8 独立 lane + pinned MinIO + aggregate ignore 与既有 workflow 结构同构；
9. 全部命名测试可与 §11 allowlist 的测试文件一一对应。

## 5. Residual risks / Open questions

- （已知 residual，plan §16 已列出）provider 非 exactly-once、source/Job 双事务、Redis wakeup 弱语义、health disabled 不停止 schedule no-op Job、RSS/manual/industry 不可执行、alert 仅持久化、date-only freshness——均为 plan 显式接受项，不构成 gate 阻断。
- 0005 的 11 个 trigger/function 与 9 类 CHECK 的 SQL 细节（plpgsql 正文）未在 plan 中逐行给出，属于 implementation agent 需在 manifest 约束内填写的确定性内容；catalog self-check 与真实 PG 命名测试将逐项验证，风险已后置到验收测试。
- `DefaultFinsWorkerSourceSyncRuntime` 对既有 pipeline 事件的 strict narrowing 依赖 DownloadEvent payload 的稳定性；plan 已设 STOP（§15）覆盖 `download_events.py` 修改场景，边界可防。

## 6. Conclusion

**PASS**（open H/M/L = 0/0/0）。

plan 与真实代码事实（60+ 点）全部一致；架构边界、并发恢复、schema 迁移、startup 装配与 CI 设计自洽且可交给 implementation agent 直接实施。无 material finding；O1/O2 为信息性实施注意项，已在 §3.1 记录。Reviewed SHA-256 在审查前、后一致（`96bceb321464223c9022af25905ca36c4bfe5cdca371111384567acb396ee4f0`），无 drift。
