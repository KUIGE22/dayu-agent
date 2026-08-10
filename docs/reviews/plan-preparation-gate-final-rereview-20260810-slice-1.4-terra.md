# Slice 1.4 preparation-gate final plan re-review（Terra）

## 审查范围

- **本机时间**：2026-08-10 23:52:09 CST。
- **审查目标**：当前 `docs/plans/2026-08-10-investment-platform-restoration.md` 的 Slice 1.4 preparation-gate 修订，复核它是否闭合 Terra `S14-TEMP-OWNERSHIP-FINAL-01`，且不破坏此前 S3、BatchToken、三阶段和临时文件所有权契约。
- **已读真源与前序证据**：根 `AGENTS.md`、master plan、`docs/reviews/plan-temp-ownership-final-rereview-20260810-slice-1.4-terra.md`、其 MiM Native counterpart `docs/reviews/plan-temp-ownership-final-rereview-20260810-slice-1.4-mimo-native.md`、`docs/reviews/plan-fix-20260810-slice-1.4-preparation-gate-deepseek.md`。
- **只读源码核验**：`dayu/fins/service_runtime.py`、`dayu/fins/ingestion/factory.py`、`dayu/fins/pipelines/factory.py`、`cn_pipeline.py`、`cn_download_workflow.py`、`cn_download_filing_workflow.py`、`cninfo_downloader.py` 与 `hkexnews_downloader.py`。
- **边界**：仅新增本 artifact；未编辑 plan、代码、测试、README 或其他 artifact；未运行 MinIO、live/network/model/broker、测试或静态检查。

## 已验证的关键假设

1. **唯一 gate 与两条真实构造链**：现有 runtime-direct 链为 `DefaultFinsRuntime._build_pipeline_for_ticker` → `_build_pipeline` → `get_pipeline_from_normalized_ticker`；ingestion 链为 `DefaultFinsRuntime.build_ingestion_service_factory` → `ingestion.factory` → `build_ingestion_service_from_normalized_ticker` → 同一 factory。计划在两条链上都以 keyword-only 参数传递同一 runtime-owned `CnPreparationGate` 至 `CnPipeline`，明确禁止 per-pipeline 创建、global cache 和 wrapper；Host/Agent/tool public contract 不暴露 gate。该 ownership 与既有 `batching_repository` 同-core 传播边界一致。
2. **admission 在 temp 创建之前**：源码中 `run_cn_download_single_filing_stream` 先等待 provider 返回 `DownloadedReportAsset.pdf_path`，随后才读文件；CNInfo/HKEX provider 都以 `NamedTemporaryFile(delete=False)` 创建 PDF。计划要求在提交该 provider worker 前获得 slot，且等待 slot 的 filing 不得启动 provider 或创建临时文件，直接消除了此前“已创建 PDF 在阶段 B gate 排队”的反例。
3. **slot 生命周期与取消**：同一 slot 跨阶段 A provider future 和阶段 B 的 read/Docling 实际 inner futures。阶段 A timeout/outer cancellation 不取消被 shield 的 provider future；late asset completion callback 仅精确 unlink、记录 metrics 后释放 slot，不可进入 read、Docling 或 repository。阶段 B outer cancellation 也不得提前释放，实际 future 完成后才释放。这同时覆盖 late provider、late read/Docling 与正常 provider exception 的 slot 回收。
4. **仓储边界不回退**：slot 不持有 repository、BatchToken 或 token；CN 阶段 A/B 继续零 token，只有 slot 正常释放并通过 `cancel_checker` fence 后才进入阶段 C 的同-core explicit batch。因此没有恢复 CN 全窗口 token、auto-begin 或跨阶段 blob/meta 写入。
5. **启动 sweep 与容量**：计划把 owned stale-temp sweep 限定为一次、exact temp-dir cleanup lock、owned regular non-symlink、有限 stale 阈值和 fail-safe no-delete，并要求在共享 gate 尚无 active slot、任何 CN/HK provider work 前运行。生产 startup 的唯一 runtime 使 files/workers 的上界为该 runtime 的配置容量；多 runtime 仅限测试隔离，计划没有不成立的全 OS 进程单例承诺。
6. **回归检查**：`replace_source_meta` owner batch、per-filing terminal state machine、`delete_entry` 的 S3 stage-delete、upload overwrite 的 per-document batch、S14-CLOSURE-01 的 ingestion same-core 链，以及阶段 C commit-start 前 rollback / 后 journal recovery 均未被 preparation-gate 修订放宽。

## Findings

### 无新增 findings。

原 Terra `S14-TEMP-OWNERSHIP-FINAL-01` 已由共享 `CnPreparationGate` 闭合：reservation 先于任何可创建临时 PDF 的 provider 提交，等待者零 provider 调用、零 temp、零 token；permit 绑定实际 inner work，并在 late asset 清理后而非 outer cancellation 时归还。计划还明确了 runtime-direct 和 ingestion-factory 的同实例传播、startup sweep 的 admission 前置条件及容量为每唯一 production runtime 的有限上界，足以交付实现。

## Open Questions

无。

## Residual Risks

| 风险 | 严重程度 | 建议跟踪 |
| --- | --- | --- |
| 阶段 B 的 `to_thread` read/Docling 可无限运行并长期占用 slot | 低 | S14-CTRL-12 的 warning/metrics、取消 fence 与 `test_cn_temp_pdf_ownership.py`；不承诺其最终终止 |
| `commit_batch` 开始后的同步窗口不可取消 | 低 | S14-CTRL-04 journal/recovery 与 startup recovery 测试 |
| 本次仅审查计划，尚未执行 MinIO/fault injection/pyright/coverage | 低 | Slice 1.4 implementation gate 的受影响 unit、MinIO integration 与静态检查 |

## Final plan review conclusion

**PASS**

**Open H/M/L：0 / 0 / 0。**

当前 plan 已精确满足：每个 production runtime 唯一共享 gate、runtime-direct 与 ingestion-factory 的 `CnPipeline` 同实例传播、slot 在 provider/temp 创建前取得并覆盖 late provider/read/Docling futures、等待 filing 零 temp、late asset 清理后回收、startup sweep 先于 admission，以及并发容量的有限上界；此前 repository/token/S3 契约无回归。Slice 1.4 可满足本轮 Terra + MiM Native final dual plan re-review 的计划门槛。
