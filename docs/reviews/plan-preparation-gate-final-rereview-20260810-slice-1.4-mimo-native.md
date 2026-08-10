# Slice 1.4 preparation-gate final closure plan re-review（MiM Native）

## 审查范围与方法

- **本机时间**：2026-08-10 23:52:39 CST。
- **目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 当前 Slice 1.4，重点复核 preparation-gate fix（`plan-fix-20260810-slice-1.4-preparation-gate-deepseek.md`，ACCEPTED/FIXED-IN-PLAN）后的全部 focus area 闭合性。
- **已读真源**：根 `AGENTS.md`、master plan 当前 Slice 1.4（S14-CTRL-01..13 全部修订版，含 preparation-gate 修订）、`docs/reviews/plan-temp-ownership-final-rereview-20260810-slice-1.4-terra.md`（Terra FAIL，S14-TEMP-OWNERSHIP-FINAL-01，1M）、`docs/reviews/plan-temp-ownership-final-rereview-20260810-slice-1.4-mimo-native.md`（MiM Native PASS，open 0/0/0，round 10）、`docs/reviews/plan-fix-20260810-slice-1.4-preparation-gate-deepseek.md`（preparation-gate fix，ACCEPTED/FIXED-IN-PLAN）、`docs/reviews/plan-fix-20260810-slice-1.4-temp-ownership-deepseek.md`（temp-ownership fix，ACCEPTED/FIXED-IN-PLAN）；并只读核验了 `cn_download_filing_workflow.py`（三段边界、`_unlink_temp_pdf`、stage-B `asyncio.to_thread`）、`cn_download_workflow.py`（stage A 前 slot acquire 调用点）、`cn_pipeline.py`（构造器接受 `preparation_gate`）、`service_runtime.py`（runtime 传播链）、`dayu/fins/ingestion/factory.py`（ingestion factory 传播链）与 S14-CTRL-12 网络边界契约、exhaustive 表、completeness gate、residual 列表。
- **边界**：仅新增本 artifact；未改 plan、代码、测试、README 或既有 review；未运行 MinIO、live/network/model/broker、commit/push/PR。

## 已验证的假设

1. **共享 gate 唯一实例**：`CnPreparationGate` 为 `DefaultFinsRuntime`/`PreparedHostRuntimeDependencies` owner 共享实例，与 `batching_repository` 同链传播到所有 `CnPipeline`，不得 per-pipeline 另建、global cache、wrapper；Host/Agent/tool contract 不见 gate。plan:2570-2592、fix artifact §A 明确。
2. **slot 先于 provider 获取**：每个 CN/HK filing 在提交阶段 A provider worker 之前 acquire slot；等待 slot 的 filing 不得启动 provider、不创建临时 PDF。plan:2547-2550、fix artifact §B 明确。
3. **同一 slot 跨阶段 A/B**：slot 跨阶段 A provider future 与阶段 B read+Docling 实际 inner futures，最后 inner 真正完成才 release。plan:2550-2551。
4. **provider_download_timeout_seconds 仅覆盖阶段 A**：只从真正进入阶段 A 后开始计时（等待 slot 不计时、零 token/临时文件/provider 调用）。plan:2551-2553。
5. **late provider completion callback**：返回 `DownloadedReportAsset` 时 callback 只做 exact temp unlink + metrics 后 release slot（禁止进入 read/Docling/repo）。plan:2553-2556。
6. **startup stale-temp sweep 前置条件**：只在共享 gate 尚未 admit 任何 work（无 active slot）时持 exclusive cleanup lock 运行。plan:2565-2566。
7. **capacity bound**：files/workers bound = 每唯一 production runtime `<=` 容量（生产 startup 唯一 runtime 保证进程实际上限）。plan:2560-2561。
8. **三段边界不变**：阶段 A 唯一 hard-bounded、阶段 B 不承诺有限结束、阶段 C 无独立 timeout + cancel fences，全部无回归。plan:2627-2766。
9. **所有 prior closure 无回归**：replace_source_meta / per-filing terminal / delete_entry S3 / upload overwrite / S14-CLOSURE-01/02 / S14-REREVIEW-02/03 / exact toolset names / S14-TERMINAL-01/02 / S14-TERMINAL-FINAL-01 / S14-TO-THREAD-FINAL-01/02 / temp-ownership F1-F5 均保持 closed。

## Focus Area 逐项验证

### Focus 1：exact one gate per production runtime shared by runtime-direct and ingestion-factory CnPipelines

| 项目 | 证据 | 结论 |
|------|------|------|
| gate 唯一实例 | plan:2570-2573：`DefaultFinsRuntime` 新增私有字段 `_preparation_gate: CnPreparationGate`，`create()` 内构造，容量有限正数默认 1 | runtime owner 唯一实例 |
| runtime-direct 传播 | plan:2575-2576：`_build_pipeline_for_ticker`/`build_ingestion_service_factory` → `_build_pipeline`/`ingestion.factory` → `get_pipeline_from_normalized_ticker` → `CnPipeline`，逐层 keyword-only 显式传递 `preparation_gate` | 同一实例 |
| ingestion-factory 传播 | plan:2546-2553：`DefaultFinsRuntime.batching_repository` → `build_ingestion_service_factory(... batching_repository=...)` → `ingestion.factory` → `get_pipeline_from_normalized_ticker` → `CnPipeline`；`preparation_gate` 与 `batching_repository` 同链传递 | 同一实例 |
| 禁止 per-pipeline 另建 | plan:2585-2588："同一 runtime 下所有 CnPipeline 共享同一实例，禁止 per-pipeline 另建、global cache、wrapper" | 明确约束 |
| Host/Agent/tool contract | plan:2586-2588："FinsRuntimeProtocol/Host/Agent/tool contract 不见 gate（不改 public domain protocol/Host imports）" | 无泄漏 |
| allowlist | plan:2588-2591：`service_runtime.py`/`ingestion/factory.py`/`pipelines/factory.py`/`cn_pipeline.py`/`cn_download_protocols.py`/`cn_download_workflow.py`/`cn_download_filing_workflow.py` 已在 allowlist | 完整 |

**结论**：gate 唯一实例通过 runtime → ingestion factory → pipeline 真实唯一链显式传递，两条路径共享同一实例，无 per-pipeline 另建路径，Host/Agent/tool 不见 gate。F1 正确闭合。

### Focus 2：slot acquired before provider submission/temp creation and retained across late provider/read/Docling actual futures

| 项目 | 证据 | 结论 |
|------|------|------|
| slot acquire 时点 | plan:2547-2550：每个 CN/HK filing 在提交阶段 A provider worker 之前 acquire slot；等待 slot 的 filing 不得启动 provider、不得创建临时 PDF | 先于 temp 创建 |
| slot 持有范围 | plan:2550-2551：同一 slot 跨阶段 A provider future 与阶段 B read+Docling 实际 inner futures，最后 inner 真正完成才 release | 跨 A/B |
| 阶段 A timeout 后 slot | plan:2553-2554：阶段 A timeout/outer cancel 不能取消 provider inner future（shield）；late provider completion 由 completion callback 只做 exact temp unlink + metrics 后 release slot | 正确回收 |
| provider exception 后 slot | plan:2556：provider exception 后 release | 正确回收 |
| 正常 provider 成功后 slot | plan:2556-2557：正常 provider 成功继续持 slot | 继续持有 |
| 阶段 B slot release | plan:2557-2559：`_read_and_unlink_temp_pdf` finally 删 path、再 Docling、Docling 实际 future 完成后 release slot；outer cancel 不提前 release | 正确 release |
| slot/gate 零 repo/batch/token | plan:2559-2560：slot/gate 绝不持有 repo/batch/token | 无泄漏 |

**结论**：slot 生命周期清晰——先于 provider/temp 创建获取、跨阶段 A/B 持有、最后 inner 完成才 release、late/exception 有 callback 回收。F2 正确闭合。

### Focus 3：waiting filings create no temp

| 项目 | 证据 | 结论 |
|------|------|------|
| 等待 slot 不启动 provider | plan:2548-2549：等待 slot 的 filing 不得启动 provider、不得创建临时 PDF | 明确禁止 |
| temp 创建在 slot 之后 | provider 在阶段 A 内以 `NamedTemporaryFile(delete=False)` 写出 PDF（`cninfo_downloader.py:394-404`/`hkexnews_downloader.py:410-420`），slot acquire 在 provider 调用前 | temp 在 slot 后 |
| 容量 1 时 temp <= 1 | fix artifact §G："第二条在 provider 之前等待 slot（不创建临时 PDF）、temp 文件数 <= 1" | 上限成立 |
| 反例验证（Terra 原始 finding） | Terra S14-TEMP-OWNERSHIP-FINAL-01 指出旧设计"阶段 B gate 在临时 PDF 已创建后才取得 permit"——preparation-gate fix 将 slot 前移到 provider 前 | 已修复 |

**结论**：slot 先于 provider 获取，等待 slot 的 filing 不创建 temp，temp 文件数 <= 容量。F3 正确闭合。

### Focus 4：cancellation callback cleans late asset

| 项目 | 证据 | 结论 |
|------|------|------|
| late provider completion callback | plan:2553-2555：late `DownloadedReportAsset` 由 completion callback 只做 exact temp unlink + metrics 后 release slot（禁止进入 read/Docling/repo） | 正确清理 |
| provider exception callback | plan:2556：provider exception 后 release slot | 正确清理 |
| outer cancel 不提前 release | plan:2558-2559：outer cancel 不提前 release | 不泄漏 |
| worker finally | plan:2557-2558：`_read_and_unlink_temp_pdf` 的 worker finally 幂等 unlink | 双重保证 |
| 外层 best-effort unlink | plan:503-504（temp-ownership F2 闭合）：outer cancel 也 best-effort unlink | 三重保证 |

**结论**：late asset 由 completion callback 清理、provider exception 释放、worker finally 兜底、outer cancel best-effort。F4 正确闭合。

### Focus 5：startup sweep before admissions

| 项目 | 证据 | 结论 |
|------|------|------|
| 前置条件 | plan:2565-2566：只在共享 gate 尚未 admit 任何 work（无 active slot）时运行 | 正确 |
| exclusive lock | plan:2566：持 exclusive cleanup lock 运行一次有界清理 | 串行化 |
| 范围限制 | plan:2566-2567：只限 `{tempdir}/dayu_cn_downloads/cninfo_*.pdf` 与 `dayu_hk_downloads/hkexnews_*.pdf` | 精确 |
| 文件过滤 | plan:2567-2568：只删 regular 非 symlink 且 mtime 早于模块级有限 stale 阈值 | 三重过滤 |
| fail-safe | plan:2568-2569：unknown/symlink/lock busy fail-safe 不删并记 metrics | 安全 |
| 与 admission 无竞态 | sweep 只在无 active slot 时执行，admission 需要 slot，二者互斥 | 无竞态 |

**结论**：startup sweep 只在 gate 无 active slot 时执行，串行化、范围窄、fail-safe。F5 正确闭合。

### Focus 6：capacity bound across concurrent pipelines

| 项目 | 证据 | 结论 |
|------|------|------|
| files/workers bound | plan:2560-2561：每唯一 production runtime `<=` 容量 | 有界 |
| 生产 runtime 唯一 | plan:2561：生产 startup 唯一 runtime closure 保证进程实际上限 | 单例 |
| 测试隔离 | plan:2561-2562：测试多 runtime 各自隔离（per-runtime gate），不宣称全 OS 进程单例 | 正确 |
| 并发 CnPipeline | fix artifact §G：同 runtime 多 CnPipeline 并发断言（容量 1：第二条 provider 前等待、temp 文件数 <= 1） | 测试覆盖 |
| worker 永不结束 residual | plan:2562-2563：worker 永不结束时 temp 文件与 permit 一并保留，上限 = 配置容量/进程 | 已知 residual |

**结论**：capacity 以 per-runtime gate 为单位，生产唯一 runtime 保证上限，测试隔离正确。F6 正确闭合。

### Focus 7：no repo/token regression

| 项目 | 证据 | 结论 |
|------|------|------|
| slot/gate 零 repo/batch/token | plan:2559-2560：slot/gate 绝不持有 repo/batch/token | 无回归 |
| 阶段 C batch timing | plan:2560-2561：阶段 C 在 slot 正常完成/release 后 + cancellation fence 才 begin batch | 正确 |
| batch 与 gate 独立 | gate 管 capacity，batch 管 blob+metadata 事务，二者生命周期不交叉 | 无耦合 |
| provider_download_timeout_seconds | plan:2551-2553：只从真正进入阶段 A 后计时（等待 slot 不计时、零 token/临时文件/provider 调用） | 不影响 batch |

**结论**：gate/capacity 与 batch/token 生命周期独立，无 repo/token 回归。F7 正确闭合。

### Focus 8：all prior S3 contracts

| Closure | 证据 | 结论 |
|---------|------|------|
| replace_source_meta AUTO_ATOMIC_ALLOWED | plan:2479 表 #12b + completeness gate :2603-2625 | 无回归 |
| per-filing terminal state machine | plan:2675-2700 | 无回归 |
| delete_entry S3 stage-delete | plan:2797-2813：S14-CTRL-13 | 无回归 |
| upload overwrite in execute_upload batch | plan:2590-2601 | 无回归 |
| S14-CLOSURE-01 同-core ingestion 链 | plan:2441-2460 | 无回归 |
| S14-REREVIEW-02/03 | plan:2240-2242 | 无回归 |
| exact toolset names | plan S14-CTRL-11 | 无回归 |
| S14-TO-THREAD-FINAL-01/02 | plan:2328-2342 | 已闭合 |
| temp-ownership F1-F5 | plan:2342-2444 | 已闭合 |
| 三段边界（stage A/B/C） | plan:2627-2766 | 无回归 |

**结论**：所有 prior S3 contracts 无回归；preparation-gate fix 未触碰任何既有闭合契约。

## Findings

### 无新增 findings。

preparation-gate fix（`plan-fix-20260810-slice-1.4-preparation-gate-deepseek.md`）正确实施：
- 共享 `CnPreparationGate` 为 runtime owner 唯一实例，与 `batching_repository` 同链传播到所有 `CnPipeline`（runtime-direct + ingestion-factory 两条路径共享同一实例，禁止 per-pipeline 另建/global cache/wrapper，Host/Agent/tool contract 不见 gate）。
- slot 先于 provider 获取（等待 slot 不启动 provider、不创建临时 PDF），彻底消除 Terra S14-TEMP-OWNERSHIP-FINAL-01 的竞态。
- 同一 slot 跨阶段 A provider future 与阶段 B read+Docling 实际 inner futures，最后 inner 真正完成才 release。
- `provider_download_timeout_seconds` 只从真正进入阶段 A 后计时（等待 slot 不计时）。
- late provider completion 由 completion callback 只做 exact temp unlink + metrics 后 release slot；provider exception 后 release；正常成功继续持 slot。
- startup stale-temp sweep 只在共享 gate 未 admit 任何 work 时持 exclusive cleanup lock 运行。
- files/workers bound = 每唯一 production runtime `<=` 容量（测试多 runtime 各自隔离）。
- 所有 prior closures 无回归；三段边界无回归。

## Open Questions

无。所有 focus area 均可由当前 master plan 与源码直接确认。

## Residual Risks

| 风险 | 严重程度 | 建议跟踪 |
|------|---------|---------|
| CN 阶段 B（read_bytes + Docling）为无界 CPU/IO 工作，不持有任何 token/batch/repository；slot 在 worker 永不结束时一直被占用 | 低（已知 residual） | 由 bounded gate 限制并发（容量 1）+ cancel_checker + warning/metrics 缓解；后续 filing 只在容量可用时可启动；startup stale-temp sweep 收敛已创建的 stale temp 文件 |
| commit-start 后同步窗口不可取消 | 低（已知 residual） | 按 S14-CTRL-04 journal/recovery 收敛 |
| outer cancellation 不回收已运行的 Python thread | 低（已知 residual） | 由"worker 不得访问 repo/batch"契约保护仓储一致性 |
| worker 永不结束时 temp 文件与 permit 保留 | 低（已知 residual） | 上限 = 配置容量/进程；startup stale-temp sweep 只删 owned stale |
| 本次是计划审查，未执行 MinIO/fault injection/pyright/coverage/Docker | 低 | implementation gate |

## Final plan review conclusion

**PASS**

**Open H/M/L：0 / 0 / 0。**

preparation-gate fix 正确闭合了 Terra S14-TEMP-OWNERSHIP-FINAL-01（阶段 B gate 在临时 PDF 已创建后才取得 permit、并发 pipeline 下文件数量无界排队、每进程上限 = 配置容量不成立）：共享 `CnPreparationGate`（runtime owner 唯一实例、与 `batching_repository` 同链传播到所有 CnPipeline、禁止 per-pipeline 另建、Host/Agent/tool contract 不见 gate）；slot 先于阶段 A provider 获取（等待 slot 不启动 provider、不创建临时 PDF）；同一 slot 跨阶段 A provider future 与阶段 B read+Docling inner futures、最后 inner 真正完成才 release；provider_download_timeout_seconds 只从真正进入阶段 A 后计时；late provider completion callback 清理 temp + release slot、provider exception 后 release、正常成功继续持 slot；startup stale-temp sweep 只在 gate 未 admit 任何 work 时运行；files/workers bound = 每唯一 production runtime `<=` 容量；传播链 allowlist/test 精确扩展。三段边界、stage A/B/C、所有 prior S3 closures 均无回归。Slice 1.4 满足 Terra + MiM Native 双路 **final dual plan re-review PASS** 条件，可进入 implementation gate。
