# Slice 1.4 terminal final independent plan re-review（MiM Native）

## 审查范围

- **本机时间**：2026-08-10 23:15:36 CST。
- **目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 当前 Slice 1.4，重点复核 terminal final corrective 对五项 findings 的闭合性。
- **已读证据**：根 `AGENTS.md`、master plan 当前 Slice 1.4（S14-CTRL-01..13 全部修订版）、`plan-terminal-rereview-20260810-slice-1.4-terra.md`（FAIL，S14-TERMINAL-01/02，2H）、`plan-terminal-rereview-20260810-slice-1.4-mimo-native.md`（FAIL，delete_entry 1H + upload overwrite 1M + CN timeout 1M）、`plan-fix-20260810-slice-1.4-terminal-final-corrective-deepseek.md`（五项唯一化进 S14-CTRL-03/04/08/10/12/13）、`plan-fix-20260810-slice-1.4-terminal-corrective-deepseek.md`（此前 terminal corrective round）及 Slice 1.4 全部 controller/corrective/final-corrective/final-closure/terminal fix 历史；并只读核验了 storage、SEC/CN download/rebuild 调用链。
- **边界**：仅新增本 review；未改 plan、代码、测试、README 或既有 review；未运行 MinIO、live/network/model/broker、commit/push/PR。

## 已验证的假设

1. completeness 真源已升级为"storage core 全部公开写入口 + 直接 FileStore/blob 原语 + manifest/inventory helper"，不再只以 `_execute_with_auto_batch` 调用点为真源。
2. `replace_source_meta` 已改为同一 storage-owner `_execute_with_auto_batch` + `AUTO_ATOMIC_ALLOWED`，在 owner batch 内完成 inventory diff + delete intents + meta/manifest swap，禁止先直接写 target。
3. per-filing terminal 状态机已唯一化：FILING_FAILED 及其它异常均 rollback，恰好一个 FILING_COMPLETED 且 pre-commit fence 通过才 commit；commit-start 后为不可取消决策点。
4. `delete_entry` S3 模式行为已唯一规定：stage-delete helper 记录 `action=delete`/`delete_state=pending`，remote delete 只在 swap 后 cleanup/recovery。
5. upload overwrite reset 已移入 `execute_upload` per-document 显式 batch，workflow 不预先 reset，失败保留旧 source/bytes。
6. CN `asyncio.to_thread` timeout 边界已明确：outer timeout 只取消 outer task，to_thread worker 继续到自身有限 timeout，worker 不访问 repo/batch，late result 丢弃。
7. 既有 closure（S14-CLOSURE-01/02、S14-REREVIEW-02/03、exact toolset names）无回归。

## Findings

### 无新增 findings。

五项 terminal findings 均已在 master plan 中唯一化闭合，且 plan 提供了 code-generation-ready 的具体约束。逐项复核：

#### 1. Terra S14-TERMINAL-01：replace_source_meta 绕过 _execute_with_auto_batch

**plan 闭合位置**：S14-CTRL-12 表 #12b + completeness gate 升级（plan:2373,2392-2414）

**当前写法**：表 #12b 明确 `replace_source_meta`（`_fs_source_document_core.py:323-398`）从"当前不经 `_execute_with_auto_batch`、先直接 `_write_json(meta_path)` 再 manifest upsert"改为"同一 storage-owner `_execute_with_auto_batch` + `BatchAdmission.AUTO_ATOMIC_ALLOWED`，在 owner batch 内完成 old/new files inventory diff、removed delete intents、source meta + filing/material manifest staging/swap，**禁止先直接写 target**"。

**证据验证**：
- 源码 `_fs_source_document_core.py:354` 当前确实直接 `_write_json(meta_path, normalized_meta)`，随后 :356-397 调用 `upsert_filing_manifest`/`upsert_material_manifest`，不经过 `_execute_with_auto_batch`——与 plan 的"旧行为"描述一致。
- plan 的改造方向正确：将 meta 写入与 manifest upsert 纳入同一 owner batch，确保 inventory diff（old/new files）、delete intents、meta+manifest swap 原子完成。
- completeness gate（plan:2399-2407）要求 AST gate 断言"公开写入口集合与分类表一一对应"并"抓直接 put/delete/write-json+manifest 绕过"——直接覆盖此路径。
- `test_rebuild_staged_store.py`（plan:1952-1961）覆盖 rebuild 成功、manifest 写失败、files shrink、crash/restart——覆盖真实 SEC/CN rebuild callers。

**结论**：闭合，无回归。

#### 2. Terra S14-TERMINAL-02：per-filing terminal outcome 语义

**plan 闭合位置**：S14-CTRL-12 per-filing terminal 状态机（plan:2437-2486）

**当前写法**：
- 私有 typed/frozen `FilingTerminalState`（`PENDING`/`COMPLETED`/`FAILED`）消费 single-filing events。
- **恰好一个 `FILING_COMPLETED`（含 skip）且 pre-commit cancel/deadline fence 通过** => `commit_batch(token)`。
- **`FILING_FAILED` 正常 return、缺/重复/矛盾 terminal、`CancelledError`、`TimeoutError`、其它 exception** 一律 `rollback_batch(token)`。
- **`commit_batch` 同步开始后为不可取消决策点**：此前 deadline 触发 => rollback 零 publish；开始后异常/crash 只按 S14-CTRL-04 journal/recovery 收敛。
- 外部 event yield 顺序/内容与现有 continue/stop 语义不变。

**证据验证**：
- 源码确认 CN `run_cn_download_single_filing_stream` 在 PDF 下载失败（:212-218）、Docling 失败（:406-412）时 yield `FILING_FAILED` 后正常 return；SEC 同理（:317-323,354-360,467-473）。
- `BatchingRepositoryProtocol.commit_batch`/`rollback_batch` 均为同步 `-> None`（`repository_protocols.py:47-53`），`asyncio.timeout` 无法取消已开始的同步 commit——plan 准确反映此约束。
- `test_per_filing_terminal_state.py` 覆盖已 stage 后 `FILING_FAILED`、missing/duplicate/矛盾 terminal、precommit timeout/cancel、commit-start 后 crash/recovery。

**结论**：闭合，无回归。

#### 3. MiM delete_entry H：S3 模式 delete_entry 行为

**plan 闭合位置**：S14-CTRL-03 byte-path matrix（plan:1501）+ S14-CTRL-13 destructive 状态机（plan:2505-2537）+ 表 #13（plan:2374）

**当前写法**：
- `delete_entry`（`_fs_blob_core.py:85`）分类 `EXPLICIT_REQUIRED`——必须在 producer 显式 same-core batch 内。
- S3 模式绝不直接 `file_store.delete_object(key)`：经**私有同-core stage-delete helper** 记录 final key + expected sha/size 为 journal `action=delete`/`delete_state=pending`，只改 staging local；remote delete 只在 commit 的 post-swap cleanup 或 recovery 收敛。
- destructive AUTO 方法（`clear_filing_documents`/`cleanup_stale_filing_documents`/`reset_source_document`/processed delete/clear）从 old authoritative inventory 逐 key 复用同一 stage-delete helper 后只 `rmtree`/`unlink` staging local，无 prefix sweep。
- FS/local 模式保留现有本地删除。

**证据验证**：
- 源码 `_fs_blob_core.py:85-90` 当前经 `_execute_with_auto_batch` 分发，`:92-113` 做本地 `unlink`/`shutil.rmtree`——FS 模式正确，S3 模式需改为 journal stage-delete。
- plan 的 byte-path matrix（:1501）明确"S3 模式绝不直接 `file_store.delete_object(key)`"。
- plan 的 S14-CTRL-13（:2512-2537）规定 "S3 模式下 `delete_entry` 绝不直接 `file_store.delete_object(key)`"并指定 stage-delete helper 路径。
- `test_delete_entry_staged_delete.py` 覆盖 intent 记录→swap→post-delete 每 phase kill/restart、head drift fail closed、missing/ambiguous delete、AUTO 方法逐 key 复用 helper 且不先删 remote。

**结论**：闭合，无回归。

#### 4. MiM upload overwrite M：跨 batch 部分失败无恢复路径

**plan 闭合位置**：S14-CTRL-12 upload 路径（plan:2384-2390）+ 上传路径说明（plan:2379-2390）

**当前写法**：
- company upsert 保持独立短 AUTO batch（表 #1，零 wrapper）。
- **overwrite reset 移入 `DoclingUploadService.execute_upload` 已有 per-document 显式 batch**：begin → overwrite 时 `reset_source_document` 复用同一 token（delete intents 进同一 journal）→ store_file + source meta → commit；失败 rollback 保留旧 source/bytes。
- workflow 不得预先 reset（`sec_upload_workflow.py:190-198`/`cn_pipeline.py:555-563,809-817` 的预先 reset 调用移除）；无外层 wrapper、无嵌套 batch。
- `test_upload_overwrite_batch.py` 覆盖 SEC/CN filing/material create/update/overwrite 成功、reset 后 store_file 中 kill、commit 前 kill 均 rollback 且旧 source/bytes 可读、restart 收敛、零第二 batch。

**证据验证**：
- 源码 `sec_upload_workflow.py:182-198` 当前依次调用 company upsert、overwrite reset、execute_upload 三个独立 batch——plan 将 reset 合并进 execute_upload。
- plan 的改造使 reset 与 upload 在同一 atomic boundary 内，失败时 reset 的 delete intents 被 rollback，旧 source/bytes 保留。

**结论**：闭合，无回归。

#### 5. MiM CN timeout M：asyncio.timeout 对 to_thread 阻塞 I/O 的中断能力

**plan 闭合位置**：S14-CTRL-12 网络边界契约 CN blocking timeout（plan:2464-2479）

**当前写法**：
- `asyncio.timeout` **只取消 outer task**（在 await 边界抛 `TimeoutError`）。
- to_thread worker（CN PDF download `cn_download_filing_workflow.py:193-199` 等）可继续运行到现有有限 provider/request timeout 自行结束。
- **worker 不得访问 repository/batch 句柄**（只接收输入数据）。
- **outer timeout 触发后立即 rollback/清 active token/丢弃 late result**（worker 结束后其结果不得写 repo/batch）。
- **底层无有限 timeout 的 to_thread 路径不得纳入"可中断"承诺** => STOP 并逐名报告。
- CN Docling 转换段保留 round 6 residual（外层 cancel_checker 边界 + metrics 观测，不承诺可中断）。
- `test_cn_blocking_timeout.py` 覆盖 fake blocking worker（不可被 TimeoutError 中断）在 outer timeout 后仍运行到自身有限 timeout 结束、late result 不能写 repo、active token 已清、timeout 后下一 filing 可启动。

**证据验证**：
- CN PDF download 使用 `asyncio.to_thread`（阻塞 I/O 在线程中执行）——`asyncio.timeout` 不能中断 `to_thread` 中的阻塞操作。
- CN downloader 有既有有限 per-request timeout（`cninfo_downloader.py:212`/`hkexnews_downloader.py:247` `request_timeout_seconds`）——worker 有界。
- plan 准确区分了 outer task 可中断与 to_thread worker 不可中断的边界，不虚假承诺。

**结论**：闭合，无回归。CN Docling 转换段为已知 residual（round 6），由 cancel_checker + metrics 缓解。

## 无回归复核

| 项目 | 结论 | 计划证据 |
| --- | --- | --- |
| ingestion 同-core 链（S14-CLOSURE-01） | 无回归 | plan:2233-2252 仍固定 runtime → ingestion factory → pipeline 的同一 `batching_repository` 实例。 |
| runtime owner / startup（S14-REREVIEW-02） | 无回归 | plan S14-CTRL-05 与 S14-CTRL-12 保持 `repository_set` 唯一构造和 Host 不见 core 的边界。 |
| inventory contraction（S14-REREVIEW-03） | 无回归 | plan S14-CTRL-13 仍要求 old/new inventory 与 delete intent；`replace_source_meta` 已纳入表 #12b 的 inventory diff 路径。 |
| exact toolset names | 无回归 | plan S14-CTRL-11 仍以 `fins`/`ingestion` exact name fail-closed。 |
| S14-CORRECTIVE-01/02 | 无回归 | exhaustive 表与网络边界契约保持 terminal final corrective 修订。 |
| S14-CLOSURE-02 | 无回归 | admission 分类保持不变。 |
| MiM F-01 | 无回归 | per-operation admission 分类语义不变。 |

## Open Questions

无。五项 finding 均由当前 plan 的具体契约与直接源码证据闭合，不依赖 MinIO 或外部运行环境。

## Residual Risks

| 风险 | 严重程度 | 建议跟踪 |
|------|---------|---------|
| CN Docling 转换段为无界 CPU 工作（`asyncio.to_thread` 不可中途取消，底层无有限 timeout），不被 `per_filing_timeout` 承诺为可中断 | 低（已知 residual） | round 6 residual，由 cancel_checker + metrics 缓解；实现期若发现其它无界 to_thread 路径 => STOP |
| commit-start 后的同步窗口（`commit_batch` 为同步过程，一旦开始 `asyncio.timeout` 无法注入取消） | 低（已知 residual） | 按 S14-CTRL-04 journal/recovery 收敛，`cleanup_pending` 由 startup 重试 |
| 本次是计划审查，未执行 MinIO/fault-injection/pyright/coverage/Docker | 低 | implementation gate |
| to_thread worker 的 late result 丢弃依赖"worker 不得访问 repo/batch"契约 | 低 | 实现期断言 worker 只接收输入数据，不持有 repo/batch 句柄 |

## Final plan review conclusion

**PASS**

**Open H/M/L：0 / 0 / 0。**

五项 terminal findings 全部在 master plan 中唯一化闭合：

1. **Terra S14-TERMINAL-01**（replace_source_meta 绕过 `_execute_with_auto_batch`）：`replace_source_meta` 归类表 #12b AUTO_ATOMIC_ALLOWED，同一 owner batch 内完成 inventory diff + delete intents + meta/manifest swap；AST gate 断言公开写入口集合与分类表一一对应并抓直接绕过；`test_rebuild_staged_store.py` 覆盖 SEC/CN rebuild callers。
2. **Terra S14-TERMINAL-02**（per-filing terminal outcome 语义）：私有 typed/frozen PENDING/COMPLETED/FAILED 状态机，FILING_FAILED 及异常均 rollback，恰好一个 COMPLETED 且 pre-commit fence 通过才 commit；commit-start 为不可取消决策点；`test_per_filing_terminal_state.py` 覆盖全部 terminal 边界。
3. **MiM delete_entry H**（S3 模式行为未唯一规定）：`delete_entry` 分类 EXPLICIT_REQUIRED，S3 模式经 stage-delete helper 记录 `action=delete`/`delete_state=pending`，remote delete 只在 swap 后 cleanup/recovery；`test_delete_entry_staged_delete.py` 覆盖 intent/swap/post-delete 每 phase kill。
4. **MiM upload overwrite M**（跨 batch 部分失败无恢复路径）：overwrite reset 移入 `execute_upload` per-document 显式 batch，workflow 不预先 reset，失败保留旧 source/bytes；`test_upload_overwrite_batch.py` 覆盖 overwrite 成功/失败/recovery。
5. **MiM CN timeout M**（`asyncio.timeout` 对 `to_thread` 阻塞 I/O 中断能力）：明确 outer task 可中断、to_thread worker 不可中断但有自身有限 timeout、worker 不访问 repo/batch、late result 丢弃、底层无有限 timeout 即 STOP；`test_cn_blocking_timeout.py` 覆盖 fake blocking worker 场景。

既有 closure 无回归。Slice 1.4 满足 terminal final plan re-review PASS 条件（open H/M/L=0/0/0）。
