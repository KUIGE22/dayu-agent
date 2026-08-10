# Slice 1.4 to-thread boundary final independent plan re-review（Terra）

## 审查范围

- **本机时间**：2026-08-10 23:32:45 CST。
- **目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 当前 Slice 1.4，在 `to_thread` boundary fix 后重新判断 code-generation readiness 与既有闭合项回归。
- **已读证据**：根 `AGENTS.md`、master plan、上一轮 Terra/MiM Native terminal-final re-review，以及 `plan-fix-20260810-slice-1.4-to-thread-boundary-deepseek.md`。
- **只读源码核验**：`cn_download_filing_workflow.py`、`cninfo_downloader.py`、`hkexnews_downloader.py`、`sec_download_workflow.py`、`sec_download_filing_workflow.py`、`docling_export.py` 与 storage batching protocol。
- **边界**：仅新增本 artifact；未修改计划、代码、测试、README 或既有审查记录；未运行 MinIO、live/network/model/broker、测试或静态检查。

## 已验证的假设

1. `provider_download_timeout_seconds` 在现行 S14-CTRL-12 中仅覆盖阶段 A；CN provider PDF download 的 `to_thread` worker 仍由既有 request timeout 自行收敛，未把阶段 B/C 伪装为 hard-bounded。
2. CN `pdf_path.read_bytes` 与默认/注入 Docling converter 已被明确放到 begin 前的阶段 B；worker 只接收 path/不可变输入，零 repository/batch/token 句柄，且不承诺可中断或最终有限结束。
3. 阶段 C 规定为 A/B 成功及 `cancel_checker` fence 后的短仓储事务；无独立 hard duration timeout、无 provider/Docling I/O，commit 前再 fence，commit-start 前 rollback、之后按 journal/recovery 收敛。
4. SEC 仍为 await-based streaming 例外；其同一 token 覆盖 list/download 与写入。`replace_source_meta` 的 owner batch、terminal outcome 状态机、S3 `delete_entry` stage-delete 与 upload overwrite 单 batch 均未被本轮新契约反向放宽。

## Findings

### S14-TO-THREAD-FINAL-01-未修复-[中]-当前测试修改清单仍要求已废止的 CN 全窗口 token/timeout 语义

- **位置**: Slice 1.4 的现行 `Allowed（final corrective 精确清单）` 测试修改项（plan:1447-1455）；S14-CTRL-12 当前网络边界与测试反向锁定（plan:2531-2547、2629-2638）。
- **问题类型**: 不可直接实施 / 测试缺口。
- **当前写法**: plan:1452-1455 仍要求 `tests/fins/test_cn_download_workflow.py` 等断言“SEC/CN 下载 per-filing 显式 batch + per-filing timeout：list/download/Docling 期间恰有同一 active token”。但计划当前唯一契约要求 CN 阶段 A/B（含 provider download、`read_bytes`、Docling）无 token，只有阶段 C 才 begin；`provider_download_timeout_seconds` 也仅约束阶段 A。
- **反例/失败场景**: 实现者同时遵循该测试修改项和 S14-CTRL-12 时，CN Docling 要么在 token 已存在时执行，从而违反新三段边界；要么测试仍断言旧行为并失败。若为保留旧断言重新把 `asyncio.timeout` 包住完整 filing，则会复发上一轮 Terra S14-TERMINAL-FINAL-01。
- **为什么有问题**: 该处位于当前 Slice 1.4 的精确 allowlist/test scope，不是已标明为历史处置的 changelog；它给出了与当前规范性网络契约相反的测试断言，无法作为生成代码时的唯一验收真源。
- **直接证据**: plan:1452-1455 与 plan:1934-1956、2525-2552、2629-2638 直接矛盾；当前 CN 调用点确为 `read_bytes`（`cn_download_filing_workflow.py:220-221`）和 Docling `to_thread`（:391-395）。
- **影响**: 实施 Agent 跑偏；测试可能强制恢复已删除的伪中断/全窗口 token 语义，或留下相互矛盾的验收标准。
- **建议改法和验证点**: 将 plan:1447-1455 的 CN 测试说明改为当前三段断言：阶段 A/B 无 token、阶段 B worker 零 repo/batch/token、阶段 C 才有单一 token；阶段 A timeout 零 begin/零 publish，阶段 B 取消仅观测后台 work，阶段 C 的失败按 commit-start 前后收敛。保留 SEC streaming 的同-token 例外，禁止将该例外泛化给 CN。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### S14-TO-THREAD-FINAL-02-未修复-[中]-阶段 B 取消后的临时 PDF 清理责任未定义，可能无限累积本地文件

- **位置**: S14-CTRL-12 阶段 B/测试反向锁定（plan:2531-2539、2610-2615、2629-2638）；`test_cn_to_thread_boundary` 的范围（plan:1934-1946）。
- **问题类型**: 状态机漏洞 / 测试缺口。
- **当前写法**: 计划规定阶段 B 外层取消后丢弃 late result、worker 不持有 repo/batch/token，并记录 warning/metrics；但未规定 `DownloadedReportAsset.pdf_path` 的清理 owner、延迟清理时点或测试。
- **反例/失败场景**: CN/HK downloader 使用 `NamedTemporaryFile(delete=False)` 创建 PDF（`cninfo_downloader.py:394-404`、`hkexnews_downloader.py:410-420`）。当前 read 路径只在普通 `Exception` 或成功 `else` 中调用 `_unlink_temp_pdf`（`cn_download_filing_workflow.py:220-241`）；外层任务在 await `to_thread(pdf_path.read_bytes)` 时被取消会绕开这些分支。由于阶段 B 明确不承诺 worker 结束，若无 worker 内 finally 或等价的完成回调，重复取消或永久卡住的 worker 可遗留临时 PDF 并消耗本地磁盘。
- **为什么有问题**: 新边界正确地把 repository 一致性与线程回收解耦，但临时文件是阶段 A 产生、阶段 B 消费的额外资源。零 publish/零 token 不能回收它；warning/metrics 也不能建立清理所有权。当前计划不要求实现者在不与仍在 read 的 worker 竞争的条件下完成或延迟清理。
- **直接证据**: `cn_download_filing_workflow.py:220-241,775-781` 无覆盖取消路径的 finally；两种 downloader 均明确 `delete=False`。plan:2610-2615 同时允许阶段 B 不确定何时结束。
- **影响**: 持续取消/卡住的 CN/HK 下载可造成临时目录积累直至磁盘压力，影响后续 filing 与宿主稳定性；该失败不被现有“零 repo/batch/token”断言捕获。
- **建议改法和验证点**: 在计划中指定临时 PDF 的单一清理 owner：读取 worker 必须在自身 `finally`（或等价、不会提前删除正在读取的 completion callback）删除 path，且该清理逻辑仅接收 path/日志输入，不接触仓储或 token；若 worker 永不结束，则将文件保留与容量风险显式列为 residual 并规定有界的启动前 stale-temp sweep owner。`test_cn_to_thread_boundary` 应覆盖阶段 B 外层取消后：无 token/零 publish，worker 完成时 PDF 被删；并覆盖长期未完成时的既定 residual/清理策略。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

## Open Questions

无。两项 finding 均可由当前 master plan 与源码直接确认。

## Residual Risks

- 即使上述两项修复，阶段 B 的不可协作 `to_thread` 仍可长期占用执行单元；这是计划已诚实声明的容量 residual，不应再被表述为可中断或必然有限结束。
- 本次只读计划审查未执行 MinIO、fault injection、pyright、coverage 或 live 验证；这些仍应由 implementation gate 覆盖。

## Final plan review conclusion

**FAIL**

**Open H/M/L：0 / 2 / 0。**

三段边界本身已正确闭合上一轮 `to_thread` timeout 的根因，且 SEC streaming、`replace_source_meta`、terminal rollback/commit fence、S3 stage-delete 与 upload overwrite 未见回归；但现行测试清单仍保留相反的 CN token/timeout 断言，并遗漏取消后 `delete=False` 临时 PDF 的资源所有权。完成这两项计划修正并复核前，Slice 1.4 不应进入 implementation gate。
