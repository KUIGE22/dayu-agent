# Slice 1.4 S3 Fins blob repository terminal final corrective plan fix（DeepSeek worker）

- **Worker**：DeepSeek Flash fix worker
- **日期**：2026-08-10
- **基线**：`5d7e6bb`（branch `codex/investment-platform`，HEAD/worktree 冻结为只读审计）
- **状态**：**SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **任务范围**：只修 master plan Slice 1.4
  （`docs/plans/2026-08-10-investment-platform-restoration.md`）与六份既有 fix artifacts
  （`plan-fix-20260810-slice-1.4-s3-blob-repository-codex.md`、
  `plan-fix-20260810-slice-1.4-s3-blob-repository-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-closure-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-closure-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-terminal-corrective-deepseek.md`）；新增本 artifact；
  production/tests/README/dependencies 全部冻结；未安装依赖、未 pull 镜像、未运行
  live/network/model/broker、未 commit/push/PR。
- **Terminal independent source reviews（只读）**：
  `docs/reviews/plan-terminal-rereview-20260810-slice-1.4-terra.md`
  （Terra，FAIL，S14-TERMINAL-01/02，2H）、
  `docs/reviews/plan-terminal-rereview-20260810-slice-1.4-mimo-native.md`
  （MiM Native，FAIL，delete_entry High + upload overwrite Medium + CN timeout Medium）。

## Controller 裁决（terminal final corrective，唯一实现，不留二选一）

- Terra terminal re-review **FAIL / open 2H**：S14-TERMINAL-01（exhaustive inventory 仍
  遗漏绕过 `_execute_with_auto_batch` 的 `replace_source_meta` 生产写路径，High）、
  S14-TERMINAL-02（per-filing timeout/cancel 未把正常结束的 `FILING_FAILED` 映射为
  rollback，且 commit 缺 deadline 决策点，High）**两项均 ACCEPT**。
- MiM Native terminal re-review **FAIL / open 1H/2M**：delete_entry（S3 模式
  `delete_entry` 行为未由 plan 唯一规定，High）、upload overwrite（跨 batch 部分失败
  无恢复路径，Medium）、CN blocking timeout（`asyncio.timeout` 对 `to_thread` 阻塞
  I/O 的中断能力未验证，Medium）**三项均 ACCEPT**。
- **合并闭合**：Terra 两项 High 与 MiM 三项（1H/2M）全部唯一化进 master plan
  S14-CTRL-03/04/08/10/12/13；无 RE-REVIEW-REQUIRED、无二选一。
- implementation 继续冻结：只改 master plan 与 fix artifacts，不触碰
  source/code/tests/README/deps；如需改 Host/public domain protocol/第二 transaction
  API 则 STOP。

## 只读 callgraph 审计（terminal final round，支撑唯一化）

本 round 按两份 terminal rereview 的 direct evidence 只读核验（未修改任何 production
文件）：

- **`replace_source_meta` 绕过（S14-TERMINAL-01 直接证据）**：
  - `_fs_source_document_core.py:323-398` 公开 `replace_source_meta` 在 :354 直接
    `_write_json(meta_path, normalized_meta)`，随后 :356-397 调
    `upsert_filing_manifest`/`upsert_material_manifest`；**不调用
    `_execute_with_auto_batch`**；
  - manifest helper 本身（`_fs_storage_infra.py:898-917,937-957`）经
    `_execute_with_auto_batch` 分发；`_ticker_dir_for_write`
    （`_fs_storage_infra.py:1115-1134`）在无 active token 时返回 target 目录——因此
    meta 直写先落 target、manifest 才可能另开 batch；
  - 该入口是稳定仓储协议一部分（`repository_protocols.py:157-165`），真实 production
    callers：CN rebuild `cn_download_rebuild.py:234-239`（payload 含 `files`，
    `:205-239`）、SEC rebuild `sec_rebuild_workflow.py:399`（`overwrite_rebuilt_meta`
    `:386-404` 写 `payload["files"]`）；SEC rebuild 经
    `sec_download_workflow.py:287`→`sec_pipeline.py:508-545`→
    `rebuild_single_local_filing`（`sec_rebuild_workflow.py:229`）→:351；
  - 结论：S3 下若前一次 meta 直写成功、后一次 begin/commit 失败，source meta 与
    manifest 不一致；files 收缩也绕过 S14-CTRL-13 的 inventory diff/delete-intent。
- **per-filing terminal 事实（S14-TERMINAL-02 直接证据）**：
  - CN `run_cn_download_single_filing_stream` 在 PDF 下载失败（:212-218）、PDF 读失败
    （:233-239）、Docling 转换失败（:406-412）时 yield `FILING_FAILED` 后**正常 return**；
    外层 `run_cn_download_stream_impl`（:259-299）只 `async for` 消费事件，仅
    `CancelledError`/`Exception` 走 :286-308 分支；
  - SEC `run_download_single_filing_stream` 在 6-K 预取失败（:317-323）、rejected
    artifact 失败（:354-360）、文件下载失败（:467-473）时同样 yield `FILING_FAILED`
    后**正常 return**；外层 `sec_download_workflow.py:425-462` 只消费事件并继续循环；
  - `BatchingRepositoryProtocol.commit_batch`/`rollback_batch` 均为同步 `-> None`
    （`repository_protocols.py:47-53`），现有实现 commit 也是同步过程
    （`_fs_storage_infra.py:201-257`）——`asyncio.timeout` 无法取消已开始的同步 commit；
  - 结论：正常 `FILING_FAILED` 若被当"成功"commit，已 stage 的 PDF/source meta 会被
    publish，违反零 publish；commit-start 的 deadline 决策点必须唯一化。
- **delete_entry S3 行为（MiM delete_entry H 直接证据）**：
  - `delete_entry`（`_fs_blob_core.py:70-90`）经 `_execute_with_auto_batch` 分发，
    `_delete_entry_impl`（:92-113）只做本地 `unlink`/`shutil.rmtree`；production 代码
    中 `file_store.delete_object` 无调用点（仅 `tests/fins/test_local_file_store.py`）；
  - AUTO_ATOMIC_ALLOWED 方法（表 #4/#5/#12）在 S3 模式做本地 `rmtree`（清理
    staging/metadata），远端 blob 删除路径未规定；若 `S3FileStore.delete_object` 执行
    远端删除则违反 S14-CTRL-13"禁止先删 remote"，若只清 staging 则远端 bytes 永删不掉；
  - 结论：必须在 plan 唯一规定 stage-delete 路径（记录 `action=delete`/
    `delete_state=pending`，remote delete 只在 swap 后 cleanup/recovery）。
- **upload overwrite（MiM upload-overwrite M 直接证据）**：
  - SEC `run_upload_filing_stream`（`sec_upload_workflow.py:182-198`）依次
    company upsert（:182）、`reset_upload_target_for_overwrite`（:190，
    →`reset_source_document` `docling_upload_service.py:969`）、`execute_upload`（:199）；
    CN `cn_pipeline.py:547-563,801-817` 同构；
  - 三个独立 AUTO batch：reset commit 成功后若 upload 失败，source 处于 deleted 状态
    且无新 bytes 替代；plan 的 restart recovery 只恢复单 batch，不覆盖跨 batch 业务状态；
  - 结论：overwrite reset 移入 `execute_upload` per-document 显式 batch（begin →
    reset 复用 token → store_file + source meta → commit；失败 rollback 保留旧
    source/bytes），workflow 不预先 reset、无外层 wrapper。
- **CN blocking timeout（MiM CN timeout M 直接证据）**：
  - CN PDF download 用 `asyncio.to_thread(_download_report_pdf_with_gate)`
    （`cn_download_filing_workflow.py:193-199`）、Docling 转换
    `asyncio.to_thread(convert_pdf_to_docling_json)`（:391-395）；`asyncio.timeout`
    只能在 await 边界抛 `TimeoutError`，不中断 to_thread 内阻塞工作；
  - CN downloader 有既有有限 per-request timeout（`cninfo_downloader.py:212`/
    `hkexnews_downloader.py:247` `request_timeout_seconds`）；Docling 转换段为无界 CPU
    （round 6 residual）；
  - 结论：`per_filing_timeout` 的中断承诺只适用于 outer task；to_thread worker 继续到
    自身有限 timeout、不得访问 repo/batch；outer timeout 立即 rollback/清 token/丢
    late result；底层无有限 timeout 的路径不得承诺可中断并 STOP。

## 唯一化契约（master plan S14-CTRL-03/04/08/10/12/13 修订）

### A. completeness 真源升级 + `replace_source_meta` owner batch（闭合 Terra S14-TERMINAL-01）

1. **inventory 真源升级**：不再只以 `_execute_with_auto_batch` 调用点为真源，扩展为
   **storage core 全部公开写入口 + 直接 FileStore/blob 原语 + manifest/inventory
   helper**（master plan S14-CTRL-12 exhaustive 表与 completeness gate 同步改写）。
2. **`replace_source_meta` 唯一契约**：改为同一 storage-owner
   `_execute_with_auto_batch` + `BatchAdmission.AUTO_ATOMIC_ALLOWED`，在**一个 owner
   batch** 内完成：old/new files inventory diff → removed files 记 `action=delete`
   delete intents（S14-CTRL-13）→ source meta + filing/material manifest 一起
   staging/swap → commit 后幂等 remote delete；**禁止先直接写 target**（meta 直写与
   manifest 不再分离成两个事务窗口）。
3. **AST/unit completeness gate 升级**（`tests/fins/test_batch_admission_classification.py`）：
   - 枚举 storage core `_fs_company_meta_core.py`/`_fs_maintenance_core.py`/
     `_fs_processed_core.py`/`_fs_source_document_core.py`/`_fs_blob_core.py`/
     `_fs_storage_infra.py` **全部公开写入口**（含写副作用的公开方法：直接
     `put_object`/`delete_object` 调用、`_write_json` 调用、manifest/inventory helper
     调用），断言**公开写入口集合与分类表一一对应**（任何写入口不在分类表 => fail）；
   - **抓直接 put/delete/write-json+manifest 绕过**：任何公开方法在
     `_execute_with_auto_batch` 之外直接写 meta.json/FileStore 后再调
     manifest/inventory helper => fail，除非以 AUTO_ATOMIC_ALLOWED 在 owner batch 内
     完成 inventory diff + delete intents + swap（`replace_source_meta` 已归类表 #12b）；
   - 原有逐调用点显式 `BatchAdmission` 分类断言保留（缺失/未知即 fail）。
4. **allowlist**：`dayu/fins/pipelines/sec_rebuild_workflow.py`、
   `dayu/fins/pipelines/cn_download_rebuild.py`（rebuild 路径真实 owner，无需业务
   wrapper）加入；`tests/fins/test_rebuild_staged_store.py` 新增；rebuild staged-store
   测试覆盖 rebuild 成功、manifest 写失败（owner batch rollback 零 publish）、files
   shrink（removed 文件 journal delete intent + swap 后幂等 remote delete）、
   crash/restart 恢复收敛。

### B. per-filing terminal 状态机（闭合 Terra S14-TERMINAL-02）

1. SEC `run_download_stream_impl`/CN `run_cn_download_stream_impl` 各自定义**私有
   typed/frozen `FilingTerminalState`（`PENDING`/`COMPLETED`/`FAILED`）**，消费
   single-filing events 并记录唯一 terminal outcome：
   - **恰好一个 `FILING_COMPLETED`（含现有 skip：SEC 6k_filtered
     `sec_download_filing_workflow.py:382-388`、CN pdf_sha 匹配
     `cn_download_filing_workflow.py:283-289`）且 pre-commit cancel/deadline fence 通过**
     => `commit_batch(token)`；
   - **`FILING_FAILED` 正常 return**、缺 terminal（stream 结束无 terminal event）、
     重复/矛盾 terminal（COMPLETED 后 FAILED 或反之）、`CancelledError`、
     `TimeoutError`、**其它 exception** 一律 `rollback_batch(token)`；
   - 外部 event yield 顺序/内容与现有 continue/stop 语义不变（SEC 收集
     `filing_results`、CN 失败后继续下一 candidate）。
2. **`commit_batch` 同步开始后为不可取消决策点**：deadline 在 commit 调用前触发 =>
   无条件 rollback 零 publish；commit 已开始后异常/crash 只按 S14-CTRL-04
   journal/recovery 收敛，**不再宣称 timeout 能中断 commit**。
3. 测试（`tests/fins/test_per_filing_terminal_state.py` + `test_sec_pipeline_download.py`/
   `test_cn_download_workflow.py` 适配）：SEC/CN 已 stage 后 `FILING_FAILED`、missing/
   duplicate/矛盾 terminal、precommit timeout/cancel、commit-start 后 crash/recovery。

### C. delete_entry S3 唯一行为（闭合 MiM delete_entry H）

1. **S3 模式 `delete_entry` 绝不直接 `file_store.delete_object(key)`**：经**私有
   同-core stage-delete helper**（`_fs_blob_core` 私有方法，复用同一 core/
   `_active_batches`）对每个要删 key 记录 final key + expected sha/size 为 journal
   `action=delete` target（`delete_state=pending`）、**只改 staging local**（删
   meta/manifest 引用）；remote delete 只出现在 commit 的 post-swap cleanup 阶段或
   recovery 收敛（S14-CTRL-04）。
2. **destructive AUTO 方法**（`clear_filing_documents`/`cleanup_stale_filing_documents`/
   `reset_source_document`/processed delete/clear）从 old authoritative inventory
   逐 key 复用同一 stage-delete helper 记录 delete intents 后**只 `rmtree`/`unlink`
   staging local**；**无 prefix sweep**。
3. FS/local 模式保留现有本地删除（`unlink`/`rmtree`）。
4. 测试（`tests/fins/test_delete_entry_staged_delete.py`）：intent 记录 → swap →
   post-delete 每 phase kill/restart、head drift fail closed、missing/ambiguous
   delete、AUTO 方法逐 key 复用 helper 且不先删 remote。

### D. upload overwrite 单 batch（闭合 MiM upload-overwrite M）

1. company upsert 保持独立短 AUTO batch（表 #1，零 wrapper）。
2. **overwrite reset 移进 `DoclingUploadService.execute_upload` 已有 per-document 显式
   batch**：begin → overwrite 时 `reset_source_document`（`docling_upload_service.py:969`）
   复用同一 token（delete intents 进同一 journal）→ store_file（:225）→
   `_upsert_source_document`（:271）→ commit；失败 rollback 保留旧 source/bytes。
3. **workflow 不得预先 reset**（`sec_upload_workflow.py:190-198`/`cn_pipeline.py:
   555-563,809-817` 的预先 `reset_upload_target_for_overwrite` 调用移除）；无外层
   wrapper、无嵌套 batch（`begin_batch` 对 active ticker 抛 RuntimeError）。
4. 测试（`tests/fins/test_upload_overwrite_batch.py` + 既有 upload 测试 owner 更新）：
   SEC/CN filing/material create/update/overwrite 成功、reset 后 store_file 中 kill、
   commit 前 kill 均 rollback 且旧 source/bytes 可读、restart 收敛、零第二 batch。

### E. CN blocking timeout 边界（闭合 MiM CN timeout M）

1. **`asyncio.timeout` 只取消 outer task**（await 边界注入 `TimeoutError`）；to_thread
   worker（CN PDF download `cn_download_filing_workflow.py:193-199` 等）可继续运行到
   现有有限 provider/request timeout（`cninfo_downloader.py:212`/`hkexnews_downloader.py:247`
   `request_timeout_seconds`）自行结束。
2. **worker 不得访问 repository/batch 句柄**（只接收输入数据）。
3. **outer timeout 触发后立即 rollback/清 active token/丢弃 late result**（worker 结束
   后其结果不得写 repo/batch）；随后下一 filing 可正常 begin 新 token。
4. **底层无有限 timeout 的 to_thread 路径不得纳入"可中断"承诺**：实现时发现任一被
   `per_filing_timeout` 覆盖的 to_thread 路径底层无任何有限 timeout => STOP 并逐名
   报告；CN Docling 转换段保持 round 6 residual（外层 cancel_checker 边界
   `cn_download_filing_workflow.py:382,413` + metrics 观测，不承诺可中断）。
5. 测试（`tests/fins/test_cn_blocking_timeout.py`）：fake blocking worker（不可被
   TimeoutError 中断）在 outer timeout 后仍运行到自身有限 timeout 结束、late result
   不能写 repo、active token 已清、timeout 后下一 filing 可启动。

## 逐 ID 处置汇总

| Finding | 严重程度 | 处置 | 闭合位置 |
| --- | --- | --- | --- |
| Terra S14-TERMINAL-01（exhaustive inventory 遗漏绕过 `_execute_with_auto_batch` 的 `replace_source_meta` 生产写路径） | High | **CLOSED-IN-PLAN** | S14-CTRL-12/13（A：completeness 真源升级——storage core 全部公开写入口 + 直接 FileStore/blob 原语 + manifest/inventory helper；`replace_source_meta` 改 storage-owner `AUTO_ATOMIC_ALLOWED` 单 batch 内 inventory diff + delete intents + meta/manifest swap、禁止先直接写 target；AST gate 断言公开写入口集合与分类表一一对应并抓直接 put/delete/write-json+manifest 绕过；SEC/CN rebuild 真实 owner/tests 加入 allowlist；`test_rebuild_staged_store.py`） |
| Terra S14-TERMINAL-02（per-filing timeout/cancel 未把正常 `FILING_FAILED` 映射为 rollback、commit 缺 deadline 决策点） | High | **CLOSED-IN-PLAN** | S14-CTRL-12（B：per-filing terminal 状态机——私有 typed/frozen PENDING/COMPLETED/FAILED 消费 single-filing events、恰好一个 FILING_COMPLETED（含 skip）且 pre-commit cancel/deadline fence 通过才 commit、FILING_FAILED 正常 return 及其它异常均 rollback 同一 token、外部 event/continue/stop 语义不变、commit-start 后不可取消只按 journal/recovery 收敛；`test_per_filing_terminal_state.py`） |
| MiM delete_entry（S3 模式 `delete_entry` 行为未唯一规定） | High | **CLOSED-IN-PLAN** | S14-CTRL-12/13（C：`delete_entry` S3 唯一行为——stage-delete helper 记录 `action=delete`/`delete_state=pending` 仅改 staging local、remote delete 只在 swap 后 cleanup/recovery、destructive AUTO 方法逐 key 复用同一 helper 后只 rmtree/unlink staging、无 prefix sweep、FS/local 保留本地删除；`test_delete_entry_staged_delete.py`） |
| MiM upload overwrite（跨 batch 部分失败无恢复路径） | Medium | **CLOSED-IN-PLAN** | S14-CTRL-12（D：overwrite reset 移入 `execute_upload` per-document 显式 batch（begin → reset 复用 token → store_file + source meta → commit；失败 rollback 保留旧 source/bytes）、workflow 不预先 reset、无外层 wrapper/嵌套 batch；`test_upload_overwrite_batch.py`） |
| MiM CN timeout（`per_filing_timeout` 对 `to_thread` 阻塞 I/O 中断能力未验证） | Medium | **CLOSED-IN-PLAN** | S14-CTRL-12（E：`asyncio.timeout` 只取消 outer task、to_thread worker 只继续到现有有限 provider/request timeout 且不访问 repo/batch、outer timeout 立即 rollback/清 token/丢 late result、底层无有限 timeout 即 STOP、Docling 转换段保留 residual；`test_cn_blocking_timeout.py`） |

逐 ID 均无 **RE-REVIEW-REQUIRED**。S14-CORRECTIVE-01/02、S14-CLOSURE-01/02、
S14-REREVIEW-02/03、exact toolset names 均保持 **closed 无回归**（本 round 未触碰其
契约）。原 round 1/2/3/4/5/6 裁决（Terra S14-01..04、MiM M1..M5、S14-FINAL-01..04、
MR1/MR2、MR3、S14-REREVIEW-01..03、F-01、S14-CLOSURE-01/02、S14-CORRECTIVE-01/02）
保持历史不变。

## 校验

- `git diff --check` 通过；修改的七份文档（master plan、六份既有 fix artifacts、本
  artifact）trailing whitespace 为零、final LF 齐全。
- 未修改 production/tests/README/dependencies；十二份 source review 保持只读
  （204331/204201/211302/211155/213617/213634/final-closure-terra/
  final-closure-mimo-native/final-corrective-terra/final-corrective-mimo-native/
  terminal-terra/terminal-mimo-native）。
- master plan 状态：**SLICE 1.4 REVIEW OBSERVATIONS FIXED / AWAITING TERMINAL FINAL
  DUAL PLAN RE-REVIEW**。
- finding completeness：Terra S14-TERMINAL-01/02 全部 **CLOSED-IN-PLAN**；MiM 三项
  （delete_entry H、upload overwrite M、CN timeout M）全部 **CLOSED-IN-PLAN**；原
  findings 全部保持历史记录。

## 新增 gap / residual（如实记录，非假设）

1. **`replace_source_meta` 是唯一已知绕过 `_execute_with_auto_batch` 的公开写入口**；
   AST gate 升级后任何新增直接 put/delete/write-json+manifest 绕过入口会 fail——
   实现期若发现其它绕过入口 => STOP 并逐名报告。
2. **CN Docling 转换段为无界 CPU 工作**（`asyncio.to_thread` 不可中途取消，底层无
   有限 timeout）：不被 `per_filing_timeout` 承诺为可中断，只由外层 cancel_checker
   边界与 metrics 观测——并入 round 6 长持 residual。
3. **to_thread worker 的 late result 丢弃**：outer timeout 后 worker 仍运行，其结果
   由"worker 不得访问 repo/batch"契约丢弃；worker 对第三方系统（provider）的副作用
   不受本 slice 控制，由既有 provider 自身有限 timeout 收敛。
4. **commit-start 后的同步窗口**：`commit_batch` 为同步过程，一旦开始
   `asyncio.timeout` 无法注入取消——按 S14-CTRL-04 journal/recovery 收敛，
   `cleanup_pending` 由 startup 重试，这是已知语义而非缺陷。


## To-thread boundary 补充（round 8：Terra S14-TERMINAL-FINAL-01 + MiM terminal-final PASS）

terminal final plan re-review 新增 findings（Terra
`docs/reviews/plan-terminal-final-rereview-20260810-slice-1.4-terra.md`
S14-TERMINAL-FINAL-01，一项 Medium）按 **ACCEPTED / FIXED-IN-PLAN** 处置；MiM Native
`docs/reviews/plan-terminal-final-rereview-20260810-slice-1.4-mimo-native.md`
PASS/open0 记录为证据（不得提前 ACCEPTED），由
`docs/reviews/plan-fix-20260810-slice-1.4-to-thread-boundary-deepseek.md`
详细展开，唯一化进 master plan S14-CTRL-12 网络边界契约（reviewer option 2 诚实三段
边界，不扩 subprocess framework）：
(A) **阶段 A（provider download/request）唯一 hard-bounded**——`per_filing_timeout_
seconds` 更名为 keyword-only `provider_download_timeout_seconds`，`asyncio.timeout`
只包裹阶段 A 的 await 窗口；每个独立请求继续由既有 per-request timeout 有界；仅此
可宣称 hard bounded；
(B) **阶段 B（preparation：`pdf_path.read_bytes`
`cn_download_filing_workflow.py:220-221` 与默认/注入 Docling converter :391-395→
`docling_export.py:76-101`）明确不纳入 hard timeout、不承诺 interruptible/最终有限
结束、不用 `asyncio.timeout` 伪装**——worker 只接收 immutable/path input、零
repo/batch/token 句柄；outer cancellation 丢弃 late result（零写入）但不宣称回收
worker，记录 warning/metrics/residual；开始此阶段前若 worker 会持有 repo/batch =>
STOP 并逐名报告；
(C) **阶段 C（repository transaction）**——阶段 A/B 成功 + cancellation fence（仅
cancel_checker）后才 begin 同-core explicit repository batch，所有 blob/meta writes
在短事务窗口内；**阶段 C 无独立 hard duration timeout、不含外部 await/Docling/
provider I/O**（`provider_download_timeout_seconds` 只约束阶段 A，不约束已开始的
阶段 C）；commit 前再查 cancel_checker（precommit fence）；**staging/commit 失败
或取消在 commit-start 前 => rollback，commit-start 后 => 只按 S14-CTRL-04
journal/recovery 收敛**；CN 阶段 A/B 期间无 active token、token 只在阶段 C 存在；
SEC 无阶段 B（await-based streaming 例外，其网络与同 token 写窗口由
`provider_download_timeout_seconds` 覆盖）。

删除/修正 round 7 的冲突承诺："完整 per-filing window 包含 Docling"、"任一被
`per_filing_timeout` 覆盖的 to_thread 无有限 timeout 即 STOP"、"fake worker 自身
有限结束"、"timeout 后下一 filing 必可启动"；`test_cn_blocking_timeout` 改为
`test_cn_to_thread_boundary`（真实默认 Docling/read_bytes 在 begin_batch 前、worker
零 repo/batch 句柄、late result 零写入、provider fake 有限 timeout 可证明终止、
preparation 取消后无 token/零 publish 但后台 work 仅观测不声称终止、后续 filing 只在
容量可用时可启动、repository transaction failure/cancellation/rollback/terminal-state 测试保留）。

Terra S14-TERMINAL-FINAL-01 按 **ACCEPTED / FIXED-IN-PLAN** 处置；Terra 上一轮
S14-TERMINAL-01/02 与 MiM 三项（delete_entry/upload overwrite/CN timeout）及
`replace_source_meta`、per-filing terminal rollback/commit fence、S3 stage-delete、
upload overwrite、既有 closure 全部保持 closed 无回归。allowlist、test matrix、stop
conditions、residuals、finding table、completion 全部同步；两份 terminal final source
review（plan-terminal-final-rereview terra/mimo-native）保持只读。master plan 状态置
**REVIEW OBSERVATION FIXED / AWAITING FINAL DUAL PLAN RE-REVIEW**；最终 gate 为
Terra + MiM Native 双路 **final dual plan re-review** PASS 且 open H/M/L=`0/0/0`。


## Temp-ownership 补充（round 9：Terra S14-TO-THREAD-FINAL-01/02 + MiM to-thread-final PASS）

to-thread final plan re-review 新增 findings（Terra
`docs/reviews/plan-to-thread-final-rereview-20260810-slice-1.4-terra.md`
S14-TO-THREAD-FINAL-01/02，两项 Medium）逐项按 **ACCEPTED / FIXED-IN-PLAN** 处置；
MiM Native `docs/reviews/plan-to-thread-final-rereview-20260810-slice-1.4-mimo-native.md`
PASS/open0 记录为证据（不得提前 ACCEPTED），由
`docs/reviews/plan-fix-20260810-slice-1.4-temp-ownership-deepseek.md` 详细展开，
唯一化进 master plan S14-CTRL-12：
(F1) **修正 active Allowed/test 清单的旧 CN token/timeout 断言（闭合
S14-TO-THREAD-FINAL-01）**——`tests/fins/test_cn_download_workflow.py` 等测试修改项
不再断言"SEC/CN list/download/Docling 期间恰有同一 active token + per-filing
timeout"：SEC streaming 例外仍同 token（`provider_download_timeout_seconds` 覆盖其
网络与同 token 写窗口）；CN 阶段 A/B 无 token、阶段 C 才单 token；阶段 A
`provider_download_timeout_seconds` 超时/失败 => 零 begin（无 token、零 publish）；
阶段 B 取消仅观测后台 work（零 token、零 publish、不声称终止）；阶段 C 已 begin 后
repository transaction failure/cancel 按 commit-start 前后收敛（commit-start 前
rollback、之后 journal/recovery）；不把 SEC streaming 例外泛化给 CN。
(F2) **唯一化临时 PDF owner 与容量（闭合 S14-TO-THREAD-FINAL-02，
code-generation-ready 不实现）**——`cn_download_filing_workflow` 私有
`_read_and_unlink_temp_pdf(path, module) -> bytes`（worker 自身 `finally` 幂等
unlink `{tempdir}/dayu_cn_downloads/cninfo_*.pdf` 与 `dayu_hk_downloads/
hkexnews_*.pdf`，`delete=False`；outer cancel 也 best-effort unlink，POSIX 可撤目录
项、Windows 由 worker finally 重试；Docling converter 只接收已读 bytes 不再持 pdf
path）；阶段 B 所有 `to_thread`/`run_in_executor` 经**模块私有 bounded gate**（模块
私有有限正数默认容量，建议 1），**permit 绑定实际 inner future**（shield/完成回调，
outer 取消不提前释放、不产生无限后台 worker），worker 零 repo/batch/token；worker
永不结束时 temp/permit 保留、上限 = 配置容量/进程；新增**bounded startup stale-temp
sweep owner**（CN pipeline 构造时、任何 CN/HK provider work 前、无 active stage-B
worker，单一 runtime/process 私有 helper 持 exact temp-dir cleanup lock，只限上述
两个 `*.pdf` 形态、只删 regular 非 symlink 且 mtime 早于模块级有限 stale 阈值的
文件，unknown/symlink/lock busy fail-safe 不删并记 metrics，禁止广泛 temp sweep）；
`tests/fins/test_cn_temp_pdf_ownership.py` 加入 allowlist（worker 完成删除、outer
取消 + worker 稍后完成删除、永不结束时文件/permit 数量有界、重启 startup sweep 只删
owned stale 且不删 fresh/unknown/symlink、无 token/零 publish）。

Terra S14-TO-THREAD-FINAL-01/02 全部 **ACCEPTED / FIXED-IN-PLAN**（未提前
ACCEPTED）；S14-CORRECTIVE-01/02、S14-CLOSURE-01/02、S14-REREVIEW-02/03、
S14-TERMINAL-01/02、S14-TERMINAL-FINAL-01、MiM delete_entry/upload overwrite/CN
timeout、exact toolset names 及 `replace_source_meta`、per-filing terminal、S3
stage-delete、upload overwrite 全部保持 closed 无回归。allowlist、test matrix、stop
conditions、residuals、finding table、completion 全部同步；两份 to-thread final
source review（plan-to-thread-final-rereview terra/mimo-native）保持只读。master
plan 状态置 **REVIEW OBSERVATIONS FIXED / AWAITING FINAL DUAL PLAN RE-REVIEW**；
最终 gate 为 Terra + MiM Native 双路 **final dual plan re-review** PASS 且 open
H/M/L=`0/0/0`。


## Preparation-gate 补充（round 10：Terra S14-TEMP-OWNERSHIP-FINAL-01 + MiM temp-ownership-final PASS）

temp-ownership final plan re-review 新增 findings（Terra
`docs/reviews/plan-temp-ownership-final-rereview-20260810-slice-1.4-terra.md`
S14-TEMP-OWNERSHIP-FINAL-01，一项 Medium）按 **ACCEPTED / FIXED-IN-PLAN** 处置；
MiM Native `docs/reviews/plan-temp-ownership-final-rereview-20260810-slice-1.4-mimo-native.md`
PASS/open0 记录为证据（不得提前 ACCEPTED），由
`docs/reviews/plan-fix-20260810-slice-1.4-preparation-gate-deepseek.md` 详细展开，
唯一化进 master plan S14-CTRL-12：
(A) **共享 `CnPreparationGate`**——私有 `CnPreparationGate`（容量有限正数默认 1）是
`DefaultFinsRuntime`/`PreparedHostRuntimeDependencies` owner 的共享实例（生产 startup
唯一 runtime；所有经 runtime direct + ingestion factory 创建的 `CnPipeline` 显式传播
同一实例、不得 per-pipeline 另建；与 `batching_repository` 同一传播链
runtime → `_build_pipeline`/`build_ingestion_service_factory` →
`get_pipeline_from_normalized_ticker` → `CnPipeline` → host protocols →
`run_cn_download_stream_impl`；Host/Agent/tool contract 不见 gate、不改 public domain
protocol/Host imports）；
(B) **slot 先于 provider 获取**——每个 CN/HK filing 在提交阶段 A provider worker 之前
先 acquire slot；等待 slot 不启动 provider、不创建临时 PDF；同一 slot 跨阶段 A provider
future 与阶段 B read+Docling 实际 inner futures、最后 inner 真正完成才 release；
(C) **阶段 A 语义**——`provider_download_timeout_seconds` 只从真正进入阶段 A 后计时
（等待 slot 不计时、零 token/临时文件/provider 调用）；阶段 A timeout/outer cancel
不能取消 provider inner future（`asyncio.shield`）；late `DownloadedReportAsset` 由
completion callback 只做 exact temp unlink + metrics 后 release slot（禁止进入
read/Docling/repo）；provider exception 后 release；正常 provider 成功继续持 slot；
(D) **阶段 B/C 时序**——`_read_and_unlink_temp_pdf` finally 删 path、再 Docling、
Docling 实际 future 完成后 release slot；outer cancel 不提前 release；slot/gate 绝不
持有 repo/batch/token；阶段 C 在 slot 正常完成/release 后 + cancel fence 才 begin
batch；
(E) **容量与进程上限**——files/workers bound = 每唯一 production runtime `<=` 容量
（生产 startup 唯一 runtime closure 保证进程实际上限；测试多 runtime 各自隔离
per-runtime gate、不宣称全 OS 进程单例，不同 runtime 仅 test isolation residual）；
(F) **startup stale-temp sweep 前置条件收紧**——只在共享 gate 尚未 admit 任何 work
（无 active slot）时持 exclusive cleanup lock 运行；
(G) **传播链 allowlist/test 扩展**——精确扩展既有 runtime → ingestion factory →
`CnPipeline` 传播链（`preparation_gate` 与 `batching_repository` 同链显式传递）；
`test_runtime_batch_injection.py` 扩展同 runtime 多 `CnPipeline` 并发断言（容量 1：
第二条 provider 前等待、temp 文件数 `<= 1`、cancel 阶段 A late asset 被 callback 删
且 slot 最终 release、cancel 阶段 B 仍按前轮）；不同 runtime 仅 test isolation
residual。

Terra S14-TEMP-OWNERSHIP-FINAL-01 按 **ACCEPTED / FIXED-IN-PLAN** 记录（未提前
ACCEPTED）；S14-CORRECTIVE-01/02、S14-CLOSURE-01/02、S14-REREVIEW-02/03、
S14-TERMINAL-01/02、S14-TERMINAL-FINAL-01、S14-TO-THREAD-FINAL-01/02、MiM
delete_entry/upload overwrite/CN timeout、exact toolset names 及
`replace_source_meta`、per-filing terminal、S3 stage-delete、upload overwrite 全部保持
closed 无回归。allowlist、test matrix、stop conditions、residuals、finding table、
completion 全部同步；两份 temp-ownership final source review
（plan-temp-ownership-final-rereview terra/mimo-native）保持只读。master plan 状态置
**REVIEW OBSERVATION FIXED / AWAITING FINAL DUAL PLAN RE-REVIEW**；最终 gate 为
Terra + MiM Native 双路 **final dual plan re-review** PASS 且 open H/M/L=`0/0/0`。

## Final dual plan re-review PASS（round 11：Slice 1.4 ACCEPTED）

Terra `docs/reviews/plan-preparation-gate-final-rereview-20260810-slice-1.4-terra.md`
与 MiM Native `docs/reviews/plan-preparation-gate-final-rereview-20260810-slice-1.4-mimo-native.md`
双路 **final dual plan re-review 均 PASS / open H/M/L=`0/0/0`**；
S14-TEMP-OWNERSHIP-FINAL-01 与此前全部 findings（S14-CORRECTIVE-01/02、
S14-CLOSURE-01/02、S14-REREVIEW-02/03、S14-TERMINAL-01/02、S14-TERMINAL-FINAL-01、
S14-TO-THREAD-FINAL-01/02、MiM delete_entry/upload overwrite/CN timeout、Terra
S14-01..04、MiM M1..M5、S14-FINAL-01..04、MR1/MR2、MR3 等）全部 **CLOSED / open0**；
Slice 1.4 implementation gate 恢复（可恢复依赖 resolution、镜像拉取与实现编辑，
随后按 implementation gate 完成 unit/MinIO/静态检查验收）。状态置
**SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**；两份 final dual plan re-review
source review（plan-preparation-gate-final-rereview terra/mimo-native）保持只读。
Production/tests/README/deps 冻结状态随实现 gate 恢复解冻（仅限 Slice 1.4 allowlist
内文件），其余 work unit 冻结不变。

## Gate status

- **SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**：Terra 与 MiM Native 双路 final
  dual plan re-review 均 PASS、open H/M/L=`0/0/0`；S14-TEMP-OWNERSHIP-FINAL-01 与此前
  全部 findings CLOSED；Slice 1.4 implementation gate 恢复。
- 未运行 live data/model/broker，未 commit/push/PR。
