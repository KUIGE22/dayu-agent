# Slice 1.4 temp ownership terminal closure final plan re-review（Terra）

## 审查范围

- **本机时间**：2026-08-10 23:42:57 CST。
- **审查目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 当前 Slice 1.4 的 temp-ownership 修订，判断其能否闭合 `S14-TO-THREAD-FINAL-01/02`，并复核既有阶段 A/B/C 与 S3 closure 是否回归。
- **已读真源和前序证据**：根 `AGENTS.md`、master plan、`docs/reviews/plan-to-thread-final-rereview-20260810-slice-1.4-terra.md`、其 MiM Native counterpart `docs/reviews/plan-to-thread-final-rereview-20260810-slice-1.4-mimo-native.md`、`docs/reviews/plan-fix-20260810-slice-1.4-temp-ownership-deepseek.md`。
- **只读源码核验**：`dayu/fins/pipelines/cn_download_filing_workflow.py`、`cn_download_workflow.py`、`cn_pipeline.py`、`dayu/fins/downloaders/cninfo_downloader.py`、`hkexnews_downloader.py`。
- **边界**：仅新增本 artifact；未编辑计划、代码、测试、README 或其他 artifact；未运行 MinIO、live/network/model/broker、测试或静态检查。

## 已验证的假设

1. Active Allowed/test scope 已去除已废止的 CN 全窗口 token/timeout 断言：`test_cn_to_thread_boundary` 规定 CN 阶段 A/B 无 token、阶段 C 才有单一 token；`test_cn_temp_pdf_ownership` 已被加入 allowlist（plan:1480-1492、2767-2778）。SEC await-streaming 同-token 例外被明确保留，未泛化给 CN。
2. `_read_and_unlink_temp_pdf` 的 worker `finally` 是临时 PDF 的唯一最终清理 owner；outer cancellation 只做 best-effort unlink，且 Docling 只接收已读 bytes。该设计不向阶段 B 泄漏 repository/batch/token（plan:2727-2739）。
3. 阶段 B permit 明确须绑定实际 inner future，outer cancellation 不得提前 release；worker 永不结束时不会释放 permit（plan:2740-2747）。阶段 C 仍只在 A/B 成功和 cancellation fence 后 begin，且 commit-start 前 rollback、之后只走 journal/recovery（plan:2645-2657、2675-2705）。
4. stale-temp sweep 的目标、文件名、对象类型、时间阈值、fail-safe 语义与锁被限定为 owned CN/HK temp dirs；它不接触 storage token，并要求在任意 CN/HK provider work 前、无 active stage-B worker 时串行执行（plan:1413-1418、2748-2756）。
5. `replace_source_meta` owner batch、terminal-state、S3 `delete_entry` stage-delete 和 upload overwrite 的既有条款未被本轮改动放宽（plan:2583-2601、2675-2705、2797-2829）。

## Findings

### S14-TEMP-OWNERSHIP-FINAL-01-未修复-[中]-阶段 B gate 在临时 PDF 已创建后才取得 permit，文件数量仍可在并发 pipeline 下无界排队

- **位置**: S14-CTRL-12 的“阶段 B bounded gate / 容量 residual / 测试反向锁定”（plan:2740-2747、2757-2776）；`test_cn_temp_pdf_ownership` allowlist（plan:1486-1492）。
- **问题类型**: 并发恢复风险 / 测试缺口。
- **当前写法**: plan 要求阶段 B 的 `to_thread` 经容量为 `N` 的 gate，permit 绑定 inner future；并据此宣称 worker 永不结束时临时文件与 permit 的上限为配置容量。临时 PDF 的清理只能在读取 worker 的 finally 或 outer cancel best-effort unlink 中发生。
- **反例/失败场景**: 同一进程并发启动 `N+K` 个 CN/HK pipeline。第一个 filing 在阶段 B 的 `read_bytes` 或 Docling worker 永久阻塞并持有其 permit。其余 filing 的阶段 A 仍可分别完成：当前真实调用顺序是 `await asyncio.to_thread(_download_report_pdf_with_gate)` 返回 `DownloadedReportAsset.pdf_path` 后，才 `await asyncio.to_thread(pdf_path.read_bytes)`（`cn_download_filing_workflow.py:191-221`）。两种 provider 都在阶段 A 内以 `NamedTemporaryFile(delete=False)` 写出 PDF（`cninfo_downloader.py:394-404`；`hkexnews_downloader.py:410-420`）。这些已创建的 PDF 随后只是在 gate 上等待、尚无阶段 B worker，因此不会持有 permit，也不会触发 worker finally；若 outer 不取消，文件数可随并发工作流数增长到 `N+K`，而非 `N`。
- **为什么有问题**: 这不是“worker 最终结束”的残余风险，而是 plan 的 gate 取得时点与临时文件创建时点之间的直接竞态。现有 `run_cn_download_stream_impl` 仅在单一 ticker 的 candidate loop 内串行（`cn_download_workflow.py:239-289`），但计划未给跨 ticker/pipeline 一个全局并发上限；`CnPipeline` 也可由 factory 为不同工作流构造。因此不能用单 ticker 串行性证明每进程临时文件数有界。当前的“上限 = 配置容量”与 focus 的 file-count 目标不成立。
- **直接证据**: plan:2740-2747 的 gate 仅覆盖阶段 B，而 plan:2631-2644 将产生 `DownloadedReportAsset.pdf_path` 的 provider download 归入阶段 A；源码显示资产在 read worker 前已写入 `delete=False` 文件。plan:2757-2764 将临时文件上限归因于阶段 B permit，但没有给已创建、等待该 permit 的资产 reservation。
- **影响**: 实施 Agent 可能实现一个正确地绑定 inner future 的 worker semaphore，但仍可在高并发/卡死 worker 下积累无限等待的 `cninfo_*.pdf` / `hkexnews_*.pdf`，造成磁盘压力；测试若只覆盖“已获 permit 的永不结束 worker”会错误验收该断言。
- **建议改法和验证点**: 将容量 reservation 前移到任何 provider 能创建 temp PDF 之前，并把它持有至该 asset 被 worker finally 或 outer cancel 清理；或引入与阶段 B gate 共享同一上限的、先于阶段 A 获取的 pending-temp slot。必须明确 `provider_download_timeout_seconds` 只从真正进入阶段 A 后开始计时，等待 reservation 不产生 token、临时文件或 provider 调用；outer 在等待 reservation 时取消不泄漏 slot。该 reservation 不得提前释放给被取消的 outer，而应在尚未创建 asset 时立即释放、在已创建 asset 时只在最终 unlink 后释放。补充 `N+1` 个并发 CN/HK filing 的 deterministic test：使第一个阶段 B inner future 永不结束，证明其余 filing 在创建 PDF 前被阻塞（或所有已创建 PDF+inner worker 总数始终 `<= N`）；并测试取消等待者、正常完成和 worker late completion 都回收 reservation。stale sweep 的测试还应证明其不在 active reservation/worker 存在时运行。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。

## Open Questions

无。上述并发反例可由当前 plan 的阶段划分和真实 PDF 创建调用顺序直接证明。

## Residual Risks

- 修复后，阶段 B 的不可协作 worker 仍可永久占用至多配置容量个 reservation；这是可接受且被准确表述的容量 residual，不应再承诺 worker 最终结束或后续 filing 必定启动。
- startup stale-temp sweep 只能在安全启动窗口处理前一运行遗留的 owned stale 文件，不能替代当前进程对已创建 PDF 的 admission bound。
- 本次为只读计划审查，未运行 MinIO、fault injection、pyright、coverage 或 live 验证；这些仍由 implementation gate 覆盖。

## Final plan review conclusion

**FAIL**

**Open H/M/L：0 / 1 / 0。**

本轮已正确闭合 stale CN 全窗口 token、单 worker owner/outer best-effort unlink、inner-future permit ownership、窄化并串行的 stale sweep，以及 A/B/C 和既有 S3 closure 的一致性。但 gate 在 `delete=False` PDF 已于阶段 A 创建后才生效，无法证明每进程临时文件数受配置容量限制。闭合上述一个 Medium finding 并经双路复审前，Slice 1.4 不应进入 implementation gate。
