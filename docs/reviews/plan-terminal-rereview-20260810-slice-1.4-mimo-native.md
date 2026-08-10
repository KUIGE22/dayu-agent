# Slice 1.4 terminal independent plan re-review（MiM Native）

## Scope

- Mode: 独立计划复核（只读源码与计划）
- Branch: `codex/investment-platform`
- 本机时间: 2026-08-10 22:59 CST
- Output file: `docs/reviews/plan-terminal-rereview-20260810-slice-1.4-mimo-native.md`
- 已读取: 根 `AGENTS.md`、master plan 当前 Slice 1.4（含 S14-CTRL-01..13 修订版）、
  `plan-final-corrective-rereview-20260810-slice-1.4-terra.md`（FAIL，S14-CORRECTIVE-01/02）、
  `plan-final-corrective-rereview-20260810-slice-1.4-mimo-native.md`（PASS，open 0/0/0）、
  `plan-fix-20260810-slice-1.4-terminal-corrective-deepseek.md`，
  及 Slice 1.4 的全部 controller/corrective/final-corrective/final-closure/terminal
  fix 历史。
- Included scope: S14-CORRECTIVE-01/02 的 exhaustive callsite 分类、AST+completeness
  gate、upload/overwrite/reset/rejection registry 跨 repo 不变量、per-filing
  batch/token 边界、per_filing_timeout 可实施性、ingestion 同-core 链、runtime
  owner、inventory contraction、toolset exact names 无回归。
- Excluded scope: plan/code/tests/README/既有 reviews 修改；MinIO、live/network/model/
  broker、commit/push/PR。

## Assumptions tested

1. S14-CTRL-12 的 16 组 exhaustive admission 分类表以 `_execute_with_auto_batch`
   全部调用点与真实 caller 交叉为真源，无遗漏。
2. 每个 AUTO_ATOMIC_ALLOWED 方法在 S3 模式下自身原子 journal 全部远端
   publish/delete + metadata swap，不存在跨 repository 不变量。
3. `delete_entry` 作为 EXPLICIT_REQUIRED 原语在 S3 模式下的行为（staging vs
   immediate remote delete）已由 plan 唯一规定。
4. SEC/CN per-filing 显式 batch 允许覆盖远端 fetch/Docling，token 不跨
   ticker，per_filing_timeout 可有界整个窗口。
5. 上传 overwrite 路径的 company upsert、overwrite reset、Docling upload 三
   个独立 AUTO_ATOMIC_ALLOWED/EXPLICIT_REQUIRED batch 的跨 batch 部分失败
   场景已由 plan 的 restart recovery 闭合。
6. ingestion 同-core 链、runtime owner、inventory contraction、toolset exact
   names 无回归。

## Findings

### S14-CORRECTIVE-01-未修复-[高]-delete_entry 在 S3 模式下的行为未由 plan 唯一规定，与 AUTO_ATOMIC_ALLOWED 方法的调用关系存在逻辑间隙

- **位置**: S14-CTRL-12 exhaustive 表 #13（`delete_entry`，EXPLICIT_REQUIRED）；
  S14-CTRL-13 destructive 状态机；`_fs_blob_core.py:70-90`（当前实现）。
- **问题类型**: 契约缺失
- **当前写法**: plan S14-CTRL-12 将 `delete_entry`（`_fs_blob_core.py:85`）分类为
  `EXPLICIT_REQUIRED`——"blob 原语；正确性依赖随后 metadata 更新"。plan S14-CTRL-03
  byte-path matrix 规定 blob delete 走 `file_store.delete_object(key)`。plan
  S14-CTRL-13 规定 "任何路径禁止先删 remote"，remote delete 只允许出现在 commit 的
  post-swap cleanup 阶段。
- **反例/失败场景**: `delete_entry` 当前实现（`_fs_blob_core.py:85-90`）经
  `_execute_with_auto_batch(handle.ticker, self._delete_entry_impl, ...)` 执行，
  `_delete_entry_impl`（`:92-109`）做本地 `path.unlink()`。在 FS 模式下这是正确的
  本地删除。但在 S3 模式下：(a) 如果 `S3FileStore.delete_object` 执行远端 S3 删除
  （如 byte-path matrix 所述），则 `delete_entry` 在 batch operation 阶段就执行了
  远端删除——这直接违反 S14-CTRL-13 "任何路径禁止先删 remote"；(b) 如果
  `S3FileStore.delete_object` 只清理本地 staging，则远端 blob 永远不会被删除（因为
  `delete_entry` 不经由 journal 记录 delete intent）。plan 未指定 S3 模式下
  `delete_entry` 应走哪条路径。
- **为什么有问题**: `delete_entry` 被 AUTO_ATOMIC_ALLOWED 方法调用（表 #4
  `clear_filing_documents`→`_clear_filing_documents_impl`：`_fs_maintenance_core.py:347`
  的 `shutil.rmtree`；表 #5 `cleanup_stale_filing_documents`→
  `_cleanup_stale_filing_documents_impl`：`:437` 的 `shutil.rmtree`；表 #12
  `reset_source_document`→`_reset_source_document_impl`：`_fs_source_document_core.py:544`
  的 `shutil.rmtree`）。这些 AUTO_ATOMIC_ALLOWED 方法在 S3 模式下做本地
  `shutil.rmtree`（清理 staging/metadata），但远端 blob 删除的路径未被 plan
  明确规定。如果 `delete_entry` 在 S3 模式下直接调 `file_store.delete_object`，
  则 AUTO_ATOMIC_ALLOWED 方法内部的 `delete_entry` 调用会在 batch operation 阶段
  执行远端删除，违反 S14-CTRL-13。
- **直接证据**:
  - `_fs_blob_core.py:85-90`：`delete_entry` 调 `self._execute_with_auto_batch(
    handle.ticker, self._delete_entry_impl, handle, name)`——当前实现经
    `_execute_with_auto_batch` 分发。
  - `_fs_blob_core.py:92-113`：`_delete_entry_impl` 做 `shutil.rmtree(path)` 或
    `path.unlink()`——本地操作。
  - `_fs_maintenance_core.py:330-351`：`_clear_filing_documents_impl` 对 filings
    目录下每个子项做 `shutil.rmtree(child)` / `child.unlink(missing_ok=True)`——
    本地操作，不调 `file_store.delete_object`。
  - `_fs_maintenance_core.py:383-438`：`_cleanup_stale_filing_documents_impl` 对
    stale document 做 `shutil.rmtree(filings_dir / document_id)`——本地操作。
  - `_fs_source_document_core.py:504-552`：`_reset_source_document_impl` 对
    document_dir 做 `shutil.rmtree(document_dir)`——本地操作。
  - **`S3FileStore` 与 `_StagedFileStore` 尚未实现**（explore agent 确认：glob
    `*s3*file*store*`/`*S3*Store*` 无匹配；grep `S3FileStore|_StagedFileStore`
    无匹配；当前唯一 `FileStore` 实现为 `LocalFileStore`）。
  - **`FileStore.delete_object` 在生产代码中从未被调用**（explore agent 确认：
    grep `delete_object` 在 `_fs_blob_core.py`/`_fs_maintenance_core.py`/
    `_fs_source_document_core.py` 均无匹配；仅在 `tests/fins/test_local_file_store.py`
    出现）。当前所有删除路径直接操作本地 `pathlib.Path`。
  - S14-CTRL-13："delete/reset/clear/stale cleanup（S3 模式）在 batch impl
    内：对每个要删的 `meta.files` key **先 head 并记录 expected sha/size +
    delete intent（journal `action=delete` target）**；更新 FS staging
    metadata；**此阶段绝不执行远端删除**"。
  - S14-CTRL-03 byte-path matrix："source reset：按 `meta.files` 枚举 key 删
    S3，再删本地元数据/manifest"。
- **影响**: `S3FileStore` 尚未实现（explore agent 确认不存在），因此当前所有
  删除路径都是本地 `shutil.rmtree`/`unlink`。implementation agent 在实现
  `S3FileStore` 时面临两难：(a) 让 `S3FileStore.delete_object` 执行远端 S3
  删除——`delete_entry` 在 AUTO_ATOMIC_ALLOWED 方法内调用时会在 batch operation
  阶段执行远端删除，违反 S14-CTRL-13；(b) 让 `S3FileStore.delete_object` 只
  清理本地 staging——远端 blob 永不删除，inventory 不收缩。两种选择都导致 plan
  自相矛盾或数据不一致。AUTO_ATOMIC_ALLOWED 方法的 "原子 journal + swap" 前提
  在 S3 模式下无法闭合。
- **建议改法和验证点**:
  1. 在 S14-CTRL-12 exhaustive 表 #13 补充 `delete_entry` 在 S3 模式下的
     唯一行为：`_delete_entry_impl` 在 S3 模式（`isinstance(self._file_store,
     _StagedFileStore)`）下不调 `file_store.delete_object`，而是对每个要删的
     key 记录 `expected_sha256`/`expected_size`（从 meta.files 读取）并写入
     journal `action=delete` target（`delete_state=pending`）+ 更新 staging
     metadata。实际远端 delete 只在 `commit_batch` post-swap cleanup 阶段执行
     （S14-CTRL-04/13）。
  2. 在 S14-CTRL-12 exhaustive 表 #4/#5/#12 补充说明：这些 AUTO_ATOMIC_ALLOWED
     方法在 S3 模式下的 `shutil.rmtree`/`unlink` 只清理本地 staging/metadata
     目录；远端 blob 删除通过 `delete_entry` 的 journal 机制在 commit 阶段完成。
     或者，这些方法在 S3 模式下不调 `delete_entry` 做本地 `shutil.rmtree`，
     而是只更新 manifest/metadata，由 journal 机制统一处理远端删除。
  3. 更新 S14-CTRL-08 测试矩阵：补充 `delete_entry` 在 S3 模式下的 journal
     delete intent 测试（head 记录 → staging metadata 更新 → commit post-swap
     remote delete → recovery 每 phase kill）。
- **修复风险（低/中/高）**: 中；需要明确 S3 模式下 `delete_entry` 的行为，
  但不改变 Host/Agent 边界或 S3 admission 契约。
- **严重程度（低/中/高/严重）**: 高。

### S14-CORRECTIVE-01-未修复-[中]-upload overwrite 跨 batch 部分失败场景未由 plan 明确覆盖

- **位置**: S14-CTRL-12 exhaustive 表 #1/#12；`sec_upload_workflow.py:182-198`；
  `cn_pipeline.py:547-563,801-817`。
- **问题类型**: 测试缺口 / 状态机漏洞
- **当前写法**: plan S14-CTRL-12 规定 upload 路径的 company upsert（表 #1）、
  overwrite reset（表 #12）、Docling upload（producer 4）各自独立
  AUTO_ATOMIC_ALLOWED/EXPLICIT_REQUIRED batch——"无业务 wrapper、无嵌套、同
  core/recovery"。test matrix 规定 "operation/commit 异常与 restart 收敛"。
- **反例/失败场景**: SEC `run_upload_filing_stream`（`sec_upload_workflow.py:182-198`）
  依次调用 `upsert_company_meta_for_upload`（line 182）、`reset_upload_target_for_
  overwrite`（line 190）、`host._upload_service.execute_upload`（line 199）。
  三个操作各自经 repository→`_execute_with_auto_batch` 创建独立 batch。在 S3 模式
  下：(a) company upsert batch commit 成功；(b) reset batch commit 成功（源文档标记
  删除）；(c) Docling upload batch 失败。此时源文档已被标记删除但无新数据替代——
  source 处于 deleted 状态、没有可读的 bytes。plan 的 restart recovery 机制（startup
  `ensure_batch_recovery`）处理的是单个 batch 的 journal 恢复，不是跨 batch 的
  业务状态恢复。plan 未规定此场景的恢复路径。
- **为什么有问题**: 三个独立 batch 的原子性只保证各自内部的 journal/swap/recovery，
  不保证跨 batch 的业务状态一致性。overwrite 是一个逻辑上原子的业务操作（删除旧
  + 写入新），但 plan 将其拆为三个独立 batch。如果中间 batch 失败，业务状态不一致
  且无恢复路径。
- **直接证据**:
  - `sec_upload_workflow.py:182-198`：三个操作顺序调用，无外层 batch 包裹。
  - `docling_upload_service.py:935-973`：`reset_upload_target_for_overwrite` 调
    `source_repository.reset_source_document`——独立经 `_execute_with_auto_batch`。
  - `upload_company_meta.py:24-`：`upsert_company_meta_for_upload` 调
    `repository.upsert_company_meta`——独立经 `_execute_with_auto_batch`。
  - plan S14-CTRL-12："上传/registry 路径零业务 wrapper、单短 AUTO batch、无嵌套、
    同 core/recovery"——明确拆为独立 batch。
- **影响**: overwrite 上传失败后 source 处于 deleted 状态，无新数据替代，且 plan
  无恢复路径。实现者可能为解决此问题引入跨 batch 的业务 wrapper，违反 plan 的
  "零业务 wrapper" 约束。
- **建议改法和验证点**:
  1. 在 S14-CTRL-12 upload 路径说明中补充：overwrite 场景下，reset 与 upload
     的跨 batch 部分失败是已知 residual（由 single-writer admission + per-filing
     timeout 缓解），不引入跨 batch wrapper。或，将 overwrite reset 合并进
     Docling upload 的 per-document batch（不作为独立 batch），使 reset 与 upload
     在同一 atomic boundary 内。
  2. 在 S14-CTRL-08 测试矩阵补充：upload overwrite 场景下 reset 成功/upload
     失败的 restart recovery 测试（验证恢复后 source 状态可辨识、可重试或可回滚）。
- **修复风险（低/中/高）**: 低；如果选择 residual 路径，只需在 plan 中明确
  记录；如果选择合并路径，需要调整 upload 调用顺序但不改变 Host/Agent 边界。
- **严重程度（低/中/高/严重）**: 中。

### S14-CORRECTIVE-02-未修复-[中]-per_filing_timeout 对 blocking I/O 的中断能力未由 plan 验证

- **位置**: S14-CTRL-12 网络边界契约；`sec_download_filing_workflow.py`；
  `cn_download_filing_workflow.py`。
- **问题类型**: 最佳实践偏离 / 契约缺失
- **当前写法**: plan S14-CTRL-12 规定 `per_filing_timeout_seconds` keyword-only
  参数 + `asyncio.timeout` 包裹整个 per-filing 窗口。timeout/cancel/network error
  无条件 rollback 零 publish。
- **反例/失败场景**: `asyncio.timeout` 通过向 asyncio task 抛 `TimeoutError`
  工作。对于 async I/O（`await` 网络请求），`TimeoutError` 能在 await 点中断。
  但 SEC downloader 的某些路径（`sec_downloader.py` 的 `_request_timeout_seconds`
  已覆盖 per-request timeout）是 async 的，而 CN downloader 使用
  `asyncio.to_thread(_download_report_pdf_with_gate)` 将阻塞 I/O 放入线程池。
  `asyncio.timeout` 不能中断 `to_thread` 中的阻塞操作——线程会继续运行直到
  完成。如果 CN PDF 下载是大文件阻塞读取，`per_filing_timeout` 可能无法在
  timeout 时立即中断，导致 token 长持。
- **为什么有问题**: plan 的 timeout 契约假设 `asyncio.timeout` 能中断整个
  per-filing 窗口内的所有 I/O。但 `asyncio.to_thread` 中的阻塞操作不受
  `TimeoutError` 中断。这导致 timeout 的有界性在 CN 路径下可能不成立。
- **直接证据**:
  - `cn_download_filing_workflow.py` 的 PDF 下载使用 `asyncio.to_thread`（阻塞
    I/O 在线程中执行）。
  - `asyncio.timeout` 只在 asyncio task 的 await 点抛 TimeoutError，不中断
    `to_thread` 中的阻塞操作。
  - plan S14-CTRL-12："新增 bounded `per_filing_timeout_seconds` 契约……
    `asyncio.timeout` 包裹整个 per-filing 窗口"——未区分 async/blocked I/O。
- **影响**: CN 大文件 PDF 下载期间 per_filing_timeout 可能无法中断阻塞读取，
  导致 token 长持超出预期时间。虽然不导致数据损坏（rollback 仍会在 download
  完成后执行），但 timeout 的有界性承诺不完全成立。
- **建议改法和验证点**:
  1. 在 S14-CTRL-12 网络边界契约中明确：`per_filing_timeout` 对 async 路径
     （SEC）有效中断，对 `to_thread` 阻塞路径（CN PDF download）的中断依赖
     线程内的 per-request timeout（已存在 `request_timeout_seconds`）。整体
     per-filing 有界性 = per_filing_timeout（async）+ per-request timeout
     （blocking）的组合。这是已知 residual，不引入 cancel 信号到线程池。
  2. 在 S14-CTRL-08 测试矩阵补充：CN 大文件 download 场景下 per_filing_timeout
     与 per-request timeout 的组合作用测试。
- **修复风险（低/中/高）**: 低；只需在 plan 中明确 timeout 的适用边界和
  residual。
- **严重程度（低/中/高/严重）**: 中。

## Prior-closure regression check

| 项目 | 判定 | 直接计划证据 |
| --- | --- | --- |
| S14-CLOSURE-01 | CLOSED | plan S14-CTRL-12 ingestion factory 同-core 唯一链 + `ingestion/factory.py` allowlist + test 扩展；无回归。 |
| S14-REREVIEW-02 | CLOSED | plan S14-CTRL-05 runtime/startup 唯一 ownership + `PreparedHostRuntimeDependencies` close owner；无回归。 |
| S14-REREVIEW-03 | CLOSED | plan S14-CTRL-13 inventory contraction：old/new diff + delete intent + processed files inventory；无回归。 |
| MiM F-01 | CLOSED（语义修订） | plan S14-CTRL-12 BatchAdmission per-operation 分类；无回归。 |
| exact toolset names | CLOSED | plan S14-CTRL-11 `frozenset({"fins", "ingestion"})` exact name；无回归。 |

## Open Questions

- 无。

## Residual Risk

| 风险 | 严重程度 | 建议跟踪 |
|------|---------|---------|
| `delete_entry` S3 模式行为需在 implementation 前唯一化，否则 AUTO_ATOMIC_ALLOWED 方法的原子性前提不成立 | 高 | S14-CTRL-12/13 修订 |
| upload overwrite 跨 batch 部分失败无恢复路径 | 中 | S14-CTRL-12 upload 路径补充或 residual 记录 |
| CN `asyncio.to_thread` 阻塞 I/O 不受 `per_filing_timeout` 中断 | 中 | S14-CTRL-12 timeout 契约边界明确 |
| 本次未运行 MinIO、故障注入、pyright、coverage 或 Docker | 低 | implementation gate |

## Final plan review conclusion

**FAIL**

**Open 1 H / 2 M / 0 L。** S14-CORRECTIVE-01 的 exhaustive classification 表结构正确（16 组含内部 helper 与 blob 原语），但 `delete_entry`（#13）在 S3 模式下的行为未由 plan 唯一规定——当前实现做本地 `unlink`，S3 模式需改为 journal delete intent 但 plan 未明确此路径，导致 AUTO_ATOMIC_ALLOWED 方法调 `delete_entry` 时存在 S14-CTRL-13 违反风险。S14-CORRECTIVE-02 的 per-filing batch 边界与 network boundary 契约自洽（删除矛盾文字、token 不跨 ticker、bounded timeout），但 `per_filing_timeout` 对 CN `asyncio.to_thread` 阻塞 I/O 的中断能力未验证。upload overwrite 跨 batch 部分失败场景未由 plan 的 restart recovery 覆盖。完成三项最小计划修复并重新复核前，Slice 1.4 不得进入 implementation gate。
