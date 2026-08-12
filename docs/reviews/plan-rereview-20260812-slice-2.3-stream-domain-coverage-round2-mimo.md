# Slice 2.3 Full Plan Re-Review Round 2 — MiMo Independent Review

- 日期：2026-08-12T20:00:58Z（初始）/ 2026-08-12T20:15:00Z（修正）
- Gate：Gateflow corrective plan fix after implementation STOP；fresh same-SHA dual plan review
- 角色：Independent MiMo reviewer only；not Controller, author, planner, implementer, or fixer
- 分支：`codex/investment-platform`
- 基线：`0db6c7b63608a15cd157f842a5be772799fdacd9`
- Accepted plan commit：`f0414facbef13081bb036e76d748e1f1cbf178b7`
- Target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- Target SHA-256：`cb192c2bb679d58e465121a4764c8bbe163ffa66e5db0d7e2c74bcb28df9e8e2`（2821 lines）
- Corrective artifact：`docs/reviews/plan-fix-20260812-slice-2.3-stream-ownership-domain-split-codex.md`
- Corrective SHA-256：`469b921de114deba4080fd33e91e4e6ca1bfdd009daa2596aead41b5454af733`
- Preserved WIP：`dayu/investment/domain/source_sync.py`
- WIP SHA-256：`4396d9d62a21853acc360be1d9f5ac8bcd0041c19dafa29ee2a5d0f2904107e`（1839 lines）
- 历史 accepted-plan 独立复审语义 SHA-256：`96bceb321464223c9022af25905ca36c4bfe5cdca371111384567acb396ee4f0`
- 模型路由：MiMo only review；DeepSeek review is historical only
- 外部边界：未运行网络、provider、付费模型、Broker、交易或部署；未 stage、commit、push、PR

## 1. SHA 与 WIP 验证

| Artifact | Required SHA-256 | Actual SHA-256 | Lines | Status |
|---|---|---|---|---|
| Target plan | `cb192c2bb679d58e465121a4764c8bbe163ffa66e5db0d7e2c74bcb28df9e8e2` | `cb192c2bb679d58e465121a4764c8bbe163ffa66e5db0d7e2c74bcb28df9e8e2` | 2821 | MATCH |
| Corrective artifact | `469b921de114deba4080fd33e91e4e6ca1bfdd009daa2596aead41b5454af733` | `469b921de114deba4080fd33e91e4e6ca1bfdd009daa2596aead41b5454af733` | 289 | MATCH |
| Preserved WIP | `4396d9d62a21853acc360be1d9f5ac8bcd0041c19dafa29ee2a5d0f2904107e` | `4396d9d62a21853acc360be1d9f5ac8bcd0041c19dafa29ee2a5d0f2904107e` | 1839 | MATCH |

## 2. Evidence Summary

独立验证了以下 plan 声明：

### 2.1 五 Owner 域拆分（§3.2）

- **DAG 正确性**：6 节点有向图，`source.py -> nothing new`、`source_sync -> source/jobs/schedules`、`source_payload -> source_sync/identifiers/source/jobs`、`source_evidence -> source_sync/source_payload/identifiers/source/jobs`、`source_health -> source_sync/identifiers/source/jobs`、`source_operation -> source_sync/source_payload/source_evidence/source_health/jobs`。无环、无反向边。
- **WIP 证伪**：`source.py` 既有 897 行，WIP `source_sync.py` 1839 行混合 enum/error/config/input/payload/evidence/connector，证伪三 owner 假设。
- **拆分顺序冻结**：先复制 WIP SHA 并验证不变，再按 top-level symbol 闭包搬移，每步改 direct import 并删旧定义。

### 2.2 43-Path Owner Test Matrix（§11.1）

- 43 个 production Python key 与 production allowlist（§11）精确一一对应，已逐行交叉验证。
- 每个 tuple 非空、无重复成员。
- 29 个 tracked-existing + 14 个 planned-new 分类明确。
- 每个 tuple member 只来自 40 项 writable test allowlist 或 18 项 coverage-only catalog。

### 2.3 18 Coverage-Only Catalog（§11.1）

精确 18 项，全部为 `tests/fins/` 下的既有文件，声明零编辑：
1. `test_fins_runtime_tool_service.py`
2. `test_cn_download_runtime.py`
3. `test_evidence_locator_runtime.py`
4. `test_runtime_batch_injection.py`
5. `test_sec_downloader.py`
6. `test_sec_pipeline_helpers.py`
7. `test_sec_pipeline_http_cache.py`
8. `test_sec_pipeline_process.py`
9. `test_sec_pipeline_process_filing_source.py`
10. `test_sec_pipeline_process_material.py`
11. `test_sec_pipeline_upload_filing_stream.py`
12. `test_sec_pipeline_upload_material_stream.py`
13. `test_sec_rebuild_workflow.py`
14. `test_cn_pipeline_coverage_extra.py`
15. `test_cn_pipeline_helpers.py`
16. `test_cn_pipeline_process.py`
17. `test_cn_temp_pdf_ownership.py`
18. `test_cn_to_thread_boundary.py`

### 2.4 Singleton Branch JSON Gate（§14 Gate 1）

每个 production path 用 fresh unique `COVERAGE_FILE` 执行 `coverage run --branch --include=<path> -m pytest ...`，JSON 断言 `meta.branch_coverage=true`、`files` 为 exact singleton、`totals.percent_covered >= 80.0`。JSON 原始值为 pass/fail 真源，term report 四舍五入不替代。

### 2.5 五 PG/Migration Gate1+Gate2 Reuse（§14 Gate 2）

| Production owner | Test file | Gate |
|---|---|---|
| `migrations/versions/0005_source_connectors_health.py` | `test_platform_migrations_postgres.py` | changed→instrumented Gate1+2 |
| `postgres_identity.py` | `test_identity_repositories_postgres.py` | changed→instrumented Gate1+2 |
| `postgres_jobs.py` | `test_postgres_jobs.py` | changed→instrumented Gate1+2 |
| `postgres_schedules.py` | `test_postgres_schedules.py` | changed→instrumented Gate1+2 |
| `postgres_sources.py` | `test_postgres_sources.py` | changed→instrumented Gate1+2 |

unchanged owner 单次 plain Gate 2；`test_source_sync_job.py` 独立 lane。executed-file ledger 防重复，remaining aggregate 八 lane ignore。

### 2.6 Symbol Ownership 与 Connector/Runtime Formula

- §3.2 exact public/private symbol manifest：每个 class/enum/alias/constant/builder/parser 只在一个 owner 定义。
- §3.2.1 精确 DTO 字段表（4 DTO）。
- §3.2.2 terminal candidate、acquire/record request/decision 精确字段/类型矩阵。
- §3.2.3 receipt/result/health/alert 精确字段与 canonical schema owner。
- §3.3 connector boundary DTO 与 `FinsSourceConnector.sync` 逐字段派生公式冻结（§4.1 lines 718-736）。
- §4.1 `FinsWorkerSyncRequest` 精确 7 字段、`FinsWorkerSyncOutcome` 8 值、`FinsWorkerSourceDocument` 5 字段、`FinsWorkerSyncResult` 8 字段。
- §4.1 `DefaultFinsWorkerSourceSyncRuntime` pipeline 调用形状冻结（7 参数）。
- 拒绝 downloader Protocol：`_RejectedArtifactDownloaderProtocol` 冻结 `download_files_stream` 精确签名（§4.4 lines 1299-1309），`persist_rejected_filing_artifact` 只接收 `downloader` 参数。

### 2.7 AsyncGenerator Direct Ownership vs Coroutine Root

- §4.4 定义 8 层精确 owner chain，每层先绑定 inner、try/async-for/finally `await inner.aclose()` exactly once。
- §4.4 明确区分：返回 `AsyncGenerator` 的 wrapper/workflow 有 outer early-aclose；`DefaultFinsWorkerSourceSyncRuntime.sync_worker_source` 和 `persist_rejected_filing_artifact` 是 coroutine root，由 caller-task cancellation 进入自身 finally 关闭 direct inner，不得伪造 outer `aclose`。
- §4.1 三处精确冻结 `async def sync_worker_source(request, *, cancel_checker)` 签名，checker required/keyword-only/无 default。

### 2.8 Writable Allowlist（§11）

Production 43 项 + Test 40 项精确列出。禁止修改 `dayu/host/worker.py`、0001-0004、Web/UI、Broker、Fact/Claim/Evidence、Agent/model。

### 2.9 157 Named Tests（§13）

| Section | Count |
|---|---|
| 13.1 Job/scope/registry/schedule | 47 |
| 13.2 Fins contract | 42 |
| 13.3 Operation/crash/health | 53 |
| 13.4 Migration/security | 15 |
| **Total** | **157** |

无重复，unique。

### 2.10 Stop Conditions（§15）与 Residual（§16）

- §15 列出 15+ 明确 STOP 条件。
- §16 列出 8 项已知 residual，其中第 8 项为 owned-thread/PONR cleanup 无 wall-clock bound，明确不扩大 scope。

### 2.11 五 Domain DAG 与 Storage Protocol

- 六节点 DAG 无环无反向边，已验证。
- `storage/source_sync_protocols.py` 按 7 个方法 annotation import 5 个 domain owner DTO，不 import session/Row/Fins/Service。
- `storage/protocols.py` 不 re-export source-sync protocol。

### 2.12 Corrective Artifact Finding Closure

| Finding | Status | Plan Evidence |
|---|---|---|
| S23-CORR-STREAM-01 AsyncGenerator | accepted/fixed | §4.1/§4.4 frozen chain |
| S23-CORR-DOMAIN-02 Five-owner | accepted/fixed | §3.2 frozen DAG/manifest |
| S23-CORR-CANONICAL-03 Decoder cap | accepted/fixed | §3.2 dual 8MiB/1MiB |
| S23-CORR-RUNTIME-04 Coroutine root | accepted/fixed | §4.1/§4.4 frozen signatures |
| S23-CORR-COVERAGE-05 Fresh coverage | accepted/fixed | §14 Gate 1 template |
| S23-CORR-COVERAGE-06 43-path matrix | accepted/fixed | §11.1 43-key table |
| S23-CORR-CONTRACT-07 Owner/adapter | accepted/fixed | §3.2/§3.3/§4.4 frozen |
| S23-CORR-RESIDUAL-08 OQ1-OQ3 | closed | §16 residual #8 |

## 3. Findings

### 1-已裁决-[证据失效]-decoder callers test coverage placement

- **初始 Finding**：声称 §3.2/§14 要求 `test_source_document_decoder_callers_use_exact_source_and_alert_caps_with_boundary_rejection` 必须在 §11.1 matrix 的四个 source owner tuple 中显式出现，但 matrix 未列出。
- **裁决结果**：**证据失效**。matrix 是 file-level owner_tests，不是 node-id-level。该 test 定义在 `tests/investment/test_architecture_boundaries.py` 中；§11.1 matrix 中四个 source owner tuple 均已包含 `test_architecture_boundaries.py`：
  - `source_sync.py` → `(test_source_sync_domain.py, test_architecture_boundaries.py)`（line 2343）
  - `source_payload.py` → `(test_source_payload_domain.py, test_architecture_boundaries.py)`（line 2344）
  - `source_evidence.py` → `(test_source_evidence_domain.py, test_architecture_boundaries.py)`（line 2345）
  - `source_health.py` → `(test_source_health_domain.py, test_architecture_boundaries.py)`（line 2346）
- **Gate 1 执行语义**：runner 对每个 production path 执行 `pytest "${owner_tests[@]}"`，其中包含 `test_architecture_boundaries.py`；该 file 中的 named decoder callers test 在四条 lane 中均被执行。§3.2 line 239-241 和 §14 lines 2743-2745 的要求通过 file-level membership 已满足。
- **失效原因**：初始 review 误将 matrix 的 file-level 语义理解为 test-node-level 语义，错误声称 named test 未在 tuple 中。重新检查 plan lines 2343-2346 后确认 file membership 已闭合。

## 4. Open Questions

无 blocking open question。

## 5. Residual Risks

1. **owned-thread/PONR wall-clock bound**：已记录于 §16 residual #8，不影响 2.3 scope。
2. **corrective review 历史结论**：DeepSeek `CLARIFY 0/1/3` 和 MiMo `PASS 0/0/0` 只证明历史 target SHA，当前修订后均失效。本 review 为 fresh same-SHA review。

## 6. Final Open H/M/L

| Severity | Count |
|---|---|
| H | 0 |
| M | 0 |
| L | 0 |

**Conclusion**: PASS

Plan 在架构、contract、closure、validation gate、coverage matrix、symbol ownership、DAG、AsyncGenerator chain、connector formula、writable allowlist、named tests、stop conditions 和 residual 等所有维度均通过独立 adversarial review。初始 Finding 1 经重新检查 plan matrix file-level 语义后确认证据失效：decoder callers test 通过其 containing file `test_architecture_boundaries.py` 在四个 source owner lane 中均已执行，§3.2 和 §14 要求已满足。无 open H/M/L findings。

## 7. Post-Review SHA Check

Target plan SHA-256: `cb192c2bb679d58e465121a4764c8bbe163ffa66e5db0d7e2c74bcb28df9e8e2`
Corrective artifact SHA-256: `469b921de114deba4080fd33e91e4e6ca1bfdd009daa2596aead41b5454af733`
Preserved WIP SHA-256: `4396d9d62a21853acc360be1d9f5ac8bcd0041c19dafa29ee2a5d0f2904107e`
