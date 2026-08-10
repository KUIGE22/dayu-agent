# Slice 1.4 terminal-final independent plan re-review（Terra）

## 审查范围与方法

- **本机时间**：2026-08-10 23:16:23 CST。
- **目标**：当前 `docs/plans/2026-08-10-investment-platform-restoration.md` 的 Slice 1.4（重点为 S14-CTRL-12/13）。
- **已读真源**：根 `AGENTS.md`、master plan 当前 Slice 1.4、上一轮 Terra/MiM Native terminal re-review、`plan-fix-20260810-slice-1.4-terminal-final-corrective-deepseek.md` 及其列出的 Slice 1.4 fix 历史。
- **只读源码核验**：`_fs_source_document_core.py`、`repository_protocols.py`、`cn_download_filing_workflow.py`、`cn_download_workflow.py`、`sec_download_workflow.py`、CN/HK downloader 与 `docling_export.py`。
- **边界**：仅新增本 artifact；未改计划、代码、测试、README 或既有 review；未运行 MinIO、live/network/model/broker，未 commit/push/PR。

## 重点闭合复验

| 复验项 | 结论 | 直接证据 |
| --- | --- | --- |
| `replace_source_meta` public-write completeness 与单 owner batch | 已闭合 | plan:2341-2407 将真源扩到全部公开写入口，并在表 #12b 明确 `replace_source_meta` 用 `AUTO_ATOMIC_ALLOWED` 的单 owner batch 完成 old/new inventory diff、delete intent、meta + manifest swap；plan:1952-1961 要求失败零 publish、shrink 与 restart 覆盖。此前真实绕过仍可由源码复现：`_fs_source_document_core.py:323-398` 在 :354 直写 meta、:356-397 再写 manifest，因此新约束必要且覆盖正确。 |
| per-filing terminal outcome、rollback 与 commit fence | 已闭合 | plan:2437-2460 明确只允许恰好一个 `FILING_COMPLETED`（含 skip）且 pre-commit fence 通过后 commit；`FILING_FAILED`、缺失/重复/矛盾 terminal、cancel、timeout、其它异常都 rollback；同步 commit 开始后只走 journal/recovery。源码直接支持原 finding：CN `cn_download_filing_workflow.py:212-218,233-239,406-412` 均是 `FILING_FAILED` 后正常 return。 |
| `delete_entry` 的 S3 删除时序 | 已闭合 | plan:2509-2537 与 :2563-2570 唯一规定 stage-delete journal intent、仅改 staging local、metadata swap 后才 remote delete/recovery；plan:1940-1951 覆盖 head drift、阶段 kill/restart 与 AUTO destructive 复用 helper。 |
| upload overwrite 的 reset/store 原子性 | 已闭合 | plan:2379-2390 将 reset 移进 `DoclingUploadService.execute_upload` 的单 per-document explicit batch，禁止 workflow 前置 reset；plan:1856-1863 覆盖 reset 后/store 中/commit 前失败且旧 source/bytes 可读。 |
| 既有 closure 无回归 | 已闭合 | S14-CLOSURE-01 同-core ingestion 链仍在 plan:2233-2252；runtime/startup 唯一 owner 与 exact toolset name 契约未被本轮改动反向放宽；S14-CTRL-13 的 inventory contraction 仍要求所有 blob inventory 收缩在 swap 前记录 delete intent（plan:2538-2567）。 |

## Findings

### S14-TERMINAL-FINAL-01-未修复-[中]-CN `to_thread` 的“底层有限 timeout”前提与当前真实 Docling/本地读路径矛盾

- **位置**: master plan S14-CTRL-12 网络边界：plan:2423-2436、2464-2479；stop condition：plan:2025-2028；测试矩阵：plan:1877-1883。
- **问题类型**: 契约缺失 / 状态机资源恢复风险 / 测试缺口。
- **当前写法**: plan:2435-2436 用 `asyncio.timeout` 覆盖完整 per-filing 窗口（明确包括 Docling）；plan:2464-2473 又要求每个被该 timeout 覆盖的 `to_thread` 路径都必须有底层有限 timeout，否则 STOP；plan:2474-2479 同时把 CN Docling 定义为无界 CPU residual。测试却要求 fake worker 会在“自身有限 provider/request timeout”后结束（plan:1877-1883）。
- **反例/失败场景**: 默认 CN converter 是 `convert_pdf_bytes_to_docling_json_bytes`（`cn_pipeline.py:174-175`），而它直接调用 Docling runtime（`docling_export.py:100`；上游转换在 :60-73），没有 timeout/cancel 参数或任何有限运行时上界。该函数实际在 `cn_download_filing_workflow.py:391-395` 通过 `asyncio.to_thread` 执行，且该调用正处于 plan:2420/2435 所定义的完整 per-filing timeout 窗口。另一个同窗口 `asyncio.to_thread(pdf_path.read_bytes)` 位于 `cn_download_filing_workflow.py:220-221`，同样没有底层 timeout。
- **为什么有问题**: `asyncio.timeout` 只能取消 outer task，不能杀死已经提交到线程池的工作。计划虽正确规定 worker 不得持有 repo/batch、outer timeout 应 rollback/清 token/丢 late result（plan:2464-2471），但“任一被覆盖路径无有限 timeout 即 STOP”与已知默认 Docling（以及本地 `read_bytes`）直接冲突。把 Docling 标为 residual 不能使该 STOP 条件或“fake worker 最终有限结束”的验收可满足；持续触发 timeout 可留下无界线程/CPU 工作，且计划没有实际路径可证明其最终停止。
- **直接证据**:
  - `cn_download_filing_workflow.py:191-221,382-395` 有三条 relevant `to_thread` 路径：provider PDF download、`pdf_path.read_bytes`、默认/注入的 Docling converter。
  - `docling_export.py:76-101` 的 `convert_pdf_bytes_to_docling_json_bytes` 只有 `(raw_data, stream_name) -> bytes`，其实现未接收 timeout、deadline 或取消对象；`cn_pipeline.py:174-175` 将它设为默认 converter。
  - plan:2472-2473 的“任一被 `per_filing_timeout` 覆盖的 to_thread 路径底层无任何有限 timeout => STOP”与 plan:2476-2478 的“CN Docling 转换段为无界 CPU 工作”并存；后二者针对同一 `to_thread` 调用，不能同时作为 implementation-pass 条件成立。
- **影响**: 当前 Slice 不能按自己的 stop condition 完成 CN per-filing timeout 的实现/验收；实现者只能违反 STOP、错误宣称线程已有限结束，或临时把 fake 的 provider timeout 误当成 Docling/local read 的实证。数据 publish 可因既有 rollback/late-result 禁止而保持安全，但执行资源、后续吞吐和验收真实性不闭合。
- **建议改法和验证点**: 在进入 implementation 前唯一化二选一的真实执行语义：
  1. 若要保持“per-filing window 真正有界”和现有 STOP，则把默认 Docling（以及任何可能阻塞的本地读取）迁到可监督、可终止的执行单元，并为其规定有限 deadline、终止/回收与容量上限；测试须用真实不可协作 worker 验证超时后最终终止，而非仅 fake provider timeout。
  2. 若不扩展本 Slice，则将 `per_filing_timeout` 的硬有界承诺限定到可证明有限的 provider download；把 Docling/local read 放到明确独立、不可中断且不持有 batch 的阶段，或在开始前 STOP。相应删除“完整窗口包括 Docling”与“fake worker 自身有限 timeout”的相反断言，并明确外部事件语义、token 生命周期和并发上限。

  无论选择哪一种，必须新增针对默认 Docling converter 与 `pdf_path.read_bytes` 的测试，而不仅是抽象 fake：timeout 后 active token 已清、late result 零 repo/batch 访问、下一 filing 可开始，并证明后台 work 的实际终止或其不再属于 bounded contract。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。

## Open Questions

无。默认 converter、`to_thread` 调用点和其无 timeout 的签名均可由当前源码直接确认。

## Residual Risks

- 在本 finding 修复前，不应把 CN 的 per-filing timeout 作为资源上界或 implementation gate 的通过依据；outer rollback 只能保护仓储一致性，不能回收已运行的 Python thread。
- 本次为计划审查，未执行 MinIO、fault injection、pyright、coverage 或 live 验证；这些仍应按已列 implementation gate 验收。

## Final plan review conclusion

**FAIL**

**Open H/M/L：0 / 1 / 0。**

上一轮 Terra 两项 High 与 MiM 的 delete-entry High、upload-overwrite Medium 已由当前计划以可实施的单一契约闭合，既有 closure 未见回归；但 CN `to_thread` 的真实底层有限性与计划的 STOP/测试承诺仍不自洽。完成该项计划修正并复核前，Slice 1.4 不应进入 implementation gate。
