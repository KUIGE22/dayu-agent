# Slice 2.3 Corrective Plan Re-Review Round 3 — MiMo Independent Review

- 日期：2026-08-12T20:37:06Z
- Gate：Slice 2.3 corrective plan re-review round 3
- 角色：Independent MiMo reviewer only
- 分支：`codex/investment-platform`
- Target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- Target SHA-256：`ab14e3a97a069551211df303c902ee711d48f0d160ca9c53d54908c78d2c849f` (2884 lines)
- Fix artifact：`docs/reviews/plan-fix-20260812-slice-2.3-stream-ownership-domain-split-codex.md`
- Fix SHA-256：`9d972471c35956add14930a7bb3311bf156dd7bcb0cee66e5be3a4c5694dd024` (335 lines)
- Preserved WIP：`dayu/investment/domain/source_sync.py`
- WIP SHA-256：`4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e` (1839 lines, untracked)
- HEAD baseline：`f0414facbef13081bb036e76d748e1f1cbf178b7`
- 历史 round-2 MiMo review SHA：`163c409a993c1c323873f50888df7c13fc59a2ba21fc282b4b0ca960b66c687a` (independent re-review，不读取 DeepSeek review)
- 外部边界：未运行网络、provider、付费模型、Broker、交易或部署；未 stage、commit、push、PR 或修改 existing review/acceptance artifact

## 1. Round-3 Persistence Contract Adversarial Verification

### 1.1 Module direct imports exactly two pure helpers from zero-diff mapping owner

Plan §4.4 item 7 冻结 `sec_download_persistence.py` 只在 module level 从 `sec_download_event_mapping.py` direct import exactly 两个 helper：

- `build_file_result_from_downloader_event`
- `summarize_failed_download_file_reasons`

Plan 明确禁止：复制 helper、增加 adapter、修改 mapping owner、callback injection。mapping owner 保持 zero diff 且不进入 writable production allowlist (§11) 或 coverage matrix (§11.1)。§15 STOP 禁止任何需要编辑 mapping owner 的实现路径。

**结论：VERIFIED。** 两个 helper 是 module-level direct import binding，mapping owner zero diff，无旁路。

### 1.2 Exact 12-field keyword-only signature

Plan §4.4 item 7 冻结 `persist_rejected_filing_artifact` 签名：

| # | Field | Type |
|---|---|---|
| 1 | `ticker` | `str` |
| 2 | `cik` | `str` |
| 3 | `filing` | `RejectedArtifactFilingRecord` |
| 4 | `remote_files` | `list[RemoteFileDescriptor]` |
| 5 | `overwrite` | `bool` |
| 6 | `rejection_reason` | `str` |
| 7 | `rejection_category` | `str` |
| 8 | `selected_primary_document` | `str` |
| 9 | `source_fingerprint` | `str` |
| 10 | `classification_version` | `str` |
| 11 | `filing_maintenance_repository` | `FilingMaintenanceRepositoryProtocol` |
| 12 | `downloader` | `_RejectedArtifactDownloaderProtocol` |

全部 keyword-only (`*` 前缀)，精确 12 fields。§13.2 named test `test_download_stream_owner_path_contains_no_getattr_hasattr_cast_ignore_or_legacy_download_files_fallback` 以 AST/signature 逐项核对。

**结论：VERIFIED。** Exact 12-field keyword-only signature frozen。

### 1.3 Five old dependencies removed

Plan §4.4 item 7 明确列出删除的五个旧 dependency 参数/imports：

1. `download_files_stream` — callback parameter
2. `download_files` — legacy fallback
3. `build_file_result_from_downloader_event` — 从 callback 改为 module-level direct import
4. `normalize_download_file_result` — legacy helper
5. `summarize_failed_download_file_reasons` — 从 callback 改为 module-level direct import

同时删除 legacy-only `_AwaitableResult`、`_maybe_await` 以及 `inspect`/`AsyncIterator`/`Awaitable`/`TypeVar` imports。§13.2 named test 断言 five old parameters absent 且无 legacy import 残留。

**结论：VERIFIED。** 五个旧 dependency 全部删除，legacy dead code 清理冻结。

### 1.4 Stream bind/try/async-for/finally/aclose once

Plan §4.4 item 7 冻结函数内唯一下载形态：

```
inner = downloader.download_files_stream(...)  # bind once
try:
    async for event in inner:                   # single async-for
        build_file_result_from_downloader_event(event)
    ...
finally:
    await inner.aclose()                        # exactly once
```

该函数是 coroutine owner（不是 async generator），不伪造 outer `aclose()`。success、mapping error、inner error、file-failed 与 caller-task `asyncio.CancelledError` 五路都经 finally close direct inner。§13.2 named test `test_rejected_artifact_persistence_closes_typed_downloader_stream_once_on_success_error_and_asyncio_cancel` 覆盖全部路径并断言 `aclose_calls == 1`。

**结论：VERIFIED。** bind/try/async-for/finally/aclose exactly-once pattern frozen。

### 1.5 Wrapper dependency only downloader while keeping business/repository args

Plan §4.4 item 7 明确：

- `SecPipeline._persist_rejected_filing_artifact` 保留既有 business args
- 调用 persistence 时传 business args、`filing_maintenance_repository` 及唯一 dependency kwarg `downloader=self._downloader`
- 五个旧 dependency kwargs 全部删除

§13.2 named test 以 AST 核对 SecPipeline caller 保留 business/repository args 且 dependency kwargs 只有 `downloader`。

**结论：VERIFIED。** Wrapper 只传 downloader 作为 dependency，business/repository args 保留。

### 1.6 Normal filing path unaffected

Plan §4.4 item 7 最后一句明确冻结：「不得删除 `sec_pipeline.py` 中 normal filing path 仍使用的 mapping helper imports/calls。」§15 STOP 条件禁止任何需要编辑 mapping owner 或保留 legacy seam 的实现路径。

**结论：VERIFIED。** Normal filing path 的 mapping helper imports/calls 保留不变。

### 1.7 Tests and STOP/allowlist closed

§13.2 两项 named test 明确冻结：

1. `test_rejected_artifact_persistence_closes_typed_downloader_stream_once_on_success_error_and_asyncio_cancel` — 覆盖 success、monkeypatch mapping error、inner error、file-failed exact summary 与 asyncio cancellation；五路断言 `aclose_calls == 1`
2. `test_download_stream_owner_path_contains_no_getattr_hasattr_cast_ignore_or_legacy_download_files_fallback` — AST/signature 核对 exact protocol、12-field signature、direct imports、five old params absent、inner finally、caller AST

§15 STOP 条件明确：「rejected persistence 需要编辑 `sec_download_event_mapping.py`、新增 adapter、复制 mapping/summary helper、保留任一 helper callback injection 或 legacy aggregate/fallback → STOP。」

§11 production allowlist 和 §11.1 coverage matrix 均不包含 `sec_download_event_mapping.py`（zero diff owner）。

**结论：VERIFIED。** Tests frozen，STOP/allowlist closed。

## 2. Full Plan Regression Scan

### 2.1 43 Owner Mapping / 18 Catalog / Strict Coverage

- §11.1 `COVERAGE_OWNER_TESTS` 精确 43 production Python keys，与 §11 writable allowlist 逐值 exact-equal
- 每个 tuple 非空、unique；runner 按 exact key 取 tuple，禁止 default/glob/name inference
- 18 项 `COVERAGE_ONLY_EXISTING_OWNER_TESTS` catalog（只运行、零编辑）
- Gate 1 使用 NUL-safe `git diff -z` + `git ls-files --others -z` 取 sorted unique union，覆盖 tracked diff 与 untracked planned-new modules
- 每个 production path 用全新 fresh `COVERAGE_FILE` 执行 `coverage run --branch --include=<path>`，JSON 必须 `meta.branch_coverage=true` 且 files 为 exact singleton
- 门槛：branch-enabled statement+branch combined coverage >= 80%，strict JSON raw 值
- 五个 PG/migration concrete owners 单独以 pinned PostgreSQL 16 digest 执行 instrumented process

**结论：PASS。** Mapping 43 keys exact，18 catalog disjoint，coverage isolation frozen。

### 2.2 Five PG Reuse

五个 concrete PG/migration owners：

| Owner | Exact test file | Instrumented/Plain |
|---|---|---|
| `0005_source_connectors_health.py` | `test_platform_migrations_postgres.py` | instrumented (if changed) |
| `postgres_identity.py` | `test_identity_repositories_postgres.py` | instrumented (if changed) |
| `postgres_jobs.py` | `test_postgres_jobs.py` | instrumented (if changed) |
| `postgres_schedules.py` | `test_postgres_schedules.py` | instrumented (if changed) |
| `postgres_sources.py` | `test_postgres_sources.py` | instrumented (if changed) |

changed owner 单次 instrumented Gate 1+2；unchanged owner 单次 plain Gate 2；source-sync-job 独立 lane；executed-file ledger 防重复；remaining aggregate exact ignore 八 lane。

**结论：PASS。** 五 PG owners 冻结 exact test file、pinned digest preflight、strict JSON threshold。

### 2.3 157 Tests

Named tests in §13 精确 157 项（machine count confirmed）。覆盖：Job/scope/registry/schedule (§13.1)、Fins contract (§13.2)、Operation/crash/health (§13.3)、Migration/security (§13.4)。

**结论：PASS。** 157 named tests unique。

### 2.4 Five-Domain DAG

§3.2 冻结精确 one-way DAG：

```
source.py -> nothing new
source_sync -> source/jobs/schedules
source_payload -> source_sync/identifiers/source/jobs
source_evidence -> source_sync/source_payload/identifiers/source/jobs
source_health -> source_sync/identifiers/source/jobs
source_operation -> source_sync/source_payload/source_evidence/source_health/jobs
```

五个 owner 之间绝无反向边或 cycle。`identifiers.py` 是既有 leaf，各模块按字段直接 import，不得 re-export。§13.1 named test `test_source_sync_payload_evidence_health_operation_domain_dag_is_one_way_and_source_never_imports_any_sync_owner` 以 AST 验证。

**结论：PASS。** DAG frozen，反向边/cycle 闭合。

### 2.5 AsyncGenerator vs Coroutine Roots

Plan §4.4 精确区分两类直接 owner：

- **AsyncGenerator owner**（wrapper/workflow 层）：`PipelineProtocol.download_stream`、SEC/CN pipeline public/impl、IngestionBackend/service、market workflow、per-filing workflow、`SecDownloader.download_files_stream`；这些返回 `AsyncGenerator[T, None]`，支持 outer early-aclose
- **Coroutine root**（`DefaultFinsWorkerSourceSyncRuntime.sync_worker_source`）和 rejected persistence（`persist_rejected_filing_artifact`）：普通 `async def` coroutine，没有 `aclose()` 入口；success/error/cancel 由自身 `finally` 关闭 direct inner

§4.4 item 7 明确：coroutine root 与 rejected persistence 改测 caller-task cancellation，不伪造 outer `aclose()`。§13.2 named test 分别覆盖 generator 层 outer early-aclose 与 coroutine root/persistence caller-task cancellation。

**结论：PASS。** AsyncGenerator vs coroutine distinction frozen。

### 2.6 Schema / Locking / Cancellation / Recovery / Security / Residuals

- **Schema**：§8 frozen 三新表 exact columns/CHECK/FK/UNIQUE/index；§8.4.1 exact object-name manifest；§8.5 exact upgrade/downgrade DAG
- **Locking**：§6.1 frozen NOWAIT lock order (job_run -> definition -> attempt -> lease -> operation -> subscription -> definition -> security -> health)；§6.1.1 owned-thread reap for sync repository；PONR frozen
- **Cancellation**：§6.1.1 pre-PONR shield/reap；PONR 后 cancellation 不覆盖 inner durable decision；§4.4 stream owner aclose chain
- **Recovery**：§5.1 manual idempotency；§5.2 schedule ensure_registered recovery；§6.3 terminal replay byte-identical
- **Security**：§8.4 RLS tenant isolation + FORCE RLS；§8.4 grants 最小权限；§9 repository error surface closed
- **Residuals**：§16 documented 8 known residuals，全部 explicit且被 test 覆盖

**结论：PASS。** 六维全面冻结。

## 3. Findings

No material findings. All constraints from the round-3 persistence contract verification are evidence-based and frozen in the plan. Full regression scan confirms consistency across 43 owner mapping, 18 catalog, strict coverage, five PG reuse, 157 tests, five-domain DAG, AsyncGenerator vs coroutine roots, schema/locking/cancellation/recovery/security/residuals.

## 4. Open Questions

None. All plan assumptions verified against evidence.

## 5. Residual Risks

1. **Implementation fidelity risk**：Plan is code-generation-ready with exact signatures, DAGs, and test names. However, the actual implementation has not been executed. The mechanical WIP split (1839 lines -> five owners) and all frozen contracts depend on faithful implementation agent execution. This is a known gate, not a plan finding.
2. **Coverage threshold at boundary**：`postgres_identity` (78.6344%) and `postgres_jobs` (79.874706%) need planned new tests to reach strict >=80.0%. The plan explicitly documents this and provides exact named tests. No finding.

## 6. Post-Review SHA Check

| Artifact | Expected SHA-256 | Actual SHA-256 | Status |
|---|---|---|---|
| Target plan | `ab14e3a97a069551211df303c902ee711d48f0d160ca9c53d54908c78d2c849f` | `ab14e3a97a069551211df303c902ee711d48f0d160ca9c53d54908c78d2c849f` | MATCH |
| Fix artifact | `9d972471c35956add14930a7bb3311bf156dd7bcb0cee66e5be3a4c5694dd024` | `9d972471c35956add14930a7bb3311bf156dd7bcb0cee66e5be3a4c5694dd024` | MATCH |
| Preserved WIP | `4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e` | `4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e` | MATCH |

All SHAs verified. No drift.

## 7. Conclusion

**PASS / open H=0 / M=0 / L=0**

Round-3 corrective plan is code-generation-ready. Persistence contract (two pure helpers, 12-field signature, five old deps removed, aclose-once pattern, wrapper-only-downloader, normal path unaffected, tests/STOP closed) fully verified. Full regression scan (43 owner mapping, 18 catalog, strict coverage, five PG reuse, 157 tests, five-domain DAG, AsyncGenerator vs coroutine roots, schema/locking/cancellation/recovery/security/residuals) passes with no material findings. SHAs all match.

Artifact path：`docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round3-mimo.md`
