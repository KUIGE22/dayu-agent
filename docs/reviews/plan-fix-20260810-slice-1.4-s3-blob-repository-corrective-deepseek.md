# Slice 1.4 S3 Fins blob repository corrective plan fix（DeepSeek worker）

- **Worker**：DeepSeek Flash fix worker
- **日期**：2026-08-10
- **基线**：`5d7e6bb`（branch `codex/investment-platform`，HEAD/worktree 冻结为只读审计）
- **状态**：**SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **任务范围**：只修 master plan Slice 1.4（`docs/plans/2026-08-10-investment-platform-restoration.md`）
  与 `docs/reviews/plan-fix-20260810-slice-1.4-s3-blob-repository-codex.md`；新增本 artifact
  与 final corrective artifact
  `docs/reviews/plan-fix-20260810-slice-1.4-final-corrective-deepseek.md`
  以及 final closure artifact
  `docs/reviews/plan-fix-20260810-slice-1.4-final-closure-deepseek.md`；
  production/tests/README/dependencies/全部 source review 冻结；未安装依赖、未 pull 镜像、
  未运行 live/network/model/broker、未 commit/push/PR。
- **Controller fix**：`docs/reviews/plan-fix-20260810-slice-1.4-s3-blob-repository-codex.md`
- **Source reviews（只读）**：`docs/reviews/plan-review-20260810-204331.md`（Terra）、
  `docs/reviews/plan-review-20260810-204201-slice-1.4-s3-blob-repository-mimo-native.md`（MiM）、
  `docs/reviews/plan-review-20260810-211302.md`（Terra final，S14-FINAL-01..04）、
  `docs/reviews/plan-review-20260810-211155-slice-1.4-s3-blob-repository-mimo-native.md`
  （MiM Native final，MR1/MR2/MR3）

## Controller rulings（双路 review 裁决）

- 接受 Terra S14-01..04（全 High）。
- 接受 MiM M1/M3/M4/M5。
- MiM M2 接受其核心修正：`stat_object` 必须 HEAD-only 验证 size/metadata；完整 bytes SHA
  校验移到 `get_object`/`Source.open` 真实读取并返回 owner 明确、seekable、已验证的
  `BinaryIO`，不得让 StreamingBody 泄漏；禁止本地 bytes fallback 或双写。
- 把 plan 修成唯一可实施契约，不保留二选一。

## 真实 callgraph 审计结论（只读，支撑唯一化）

- **写入已走 FileStore**：`_fs_blob_core.py:115` `store_file`、`_fs_maintenance_core.py:114`
  `store_rejected_filing_file`、`tool_snapshot_export.py:1513` 均经注入 FileStore。
- **读取/枚举/删除绕过 FileStore**：`_fs_source_document_core.py:615/643` `get_source`/
  `get_primary_source` 无条件 `_local_path_from_uri`+`LocalFileSource`（S3 uri 必抛
  ValueError）；`_fs_blob_core.py:26/47/92` `list_entries`/`read_file_bytes`/
  `_delete_entry_impl` 直接操作本地路径；`_fs_processed_core.py:258` `_upsert_processed`
  直接 `_write_json` 写 sections/tables/financials；`_fs_source_document_core.py:480`
  `has_filing_xbrl_instance` 本地目录扫描；`_fs_maintenance_core.py:280/330/383`
  rejected 读取与清理全为本地路径。这些是 Terra S14-01 的直接证据。
- **batch/recovery 是纯本地 journal 状态机**：`_fs_storage_infra.py` `begin_batch`（copytree
  元数据目录）、`commit_batch`（backup/swap/journal `_PHASE_*`）、`recover_orphan_batches`
  （`transaction.json` + `batch_locks`），无任何 S3 感知——Terra S14-02 的直接证据。
- **startup 顺序**：`startup_preparation.py:469` `prepare_host_runtime_dependencies` 现为
  `load_platform_settings` -> `_default_provider_or_fail`（PG engine+probe）-> composition ->
  paths/ConfigLoader -> `HostStore.initialize_schema` -> `DefaultFinsRuntime.create` -> Host
  -> recover；`DefaultFinsRuntime.create`（`service_runtime.py:1890`）无 `file_store` 参数；
  `PreparedHostRuntimeDependencies.close()`（`startup_preparation.py:144`）只释放 platform
  lifecycle——Terra S14-04 / MiM M3 的直接证据。
- **互斥现状**：只有 per-ticker 本地文件锁 `.dayu/batch_locks/{ticker}.lock`
  （`_fs_storage_infra.py:410`），无全局 writer admission——Terra S14-03 的直接证据。

## 唯一化契约（master plan S14-CTRL-03..09）

- **S14-CTRL-03**：S3 是 authoritative blob bytes，FS 只持 metadata/manifest/journal；
  byte-path matrix 列出全部真实字节 owner 的 corrective 后路径（create/read/list/delete/
  process/evidence/reset/cleanup/XBRL 探测）；新增 FileStore-backed `Source` adapter
  （`store_source.py`），close ownership 明确；禁止本地 bytes fallback 或双写；allowlist
  精确展开到文件级。
- **S14-CTRL-04**：最小 remote-operation journal（`.dayu/remote_ops/{operation_id}.json`）
  并入现有 FS batch owner；**顶层 `phase` 仅表 batch/meta 阶段，bytes 发布进度由每个
  target 的 `publish_state`（`staged|final_verified`）独立表达**；commit ordering =
  publish-before-swap，逐 target copy 前后原子持久（temp+replace），copy/journal 写模糊
  以 head final digest/size 判定完成；恢复逐 target 独立（final 匹配 -> verified；
  未发布且 staging 存在 -> 完成发布；staging 缺失 -> fail closed），全部 targets verified
  且 FS staging 完整才 metadata roll-forward，FS staging 缺失/损坏 fail closed 保留
  journal/远端 objects；只删 operation-owned staging、禁全前缀扫删、永不删 final；覆盖
  put 后 crash、第 1 个 copy 后 crash（2+ targets）、copy 后 journal 写前 crash、final
  发布后 metadata 前 crash、metadata commit 后 cleanup 失败、重启、overwrite、
  auto/explicit batch；cleanup 失败语义分 pre/post commit。
- **S14-CTRL-05**：startup 顺序固定 load settings -> S3 admission（strict JSON/credentials/
  build store/head_bucket）-> writer lease/recovery -> provider -> composition/runtime/Host；
  任一 S3 失败 provider/workspace/Host 零调用，已建 S3/lease 资源确定性 cleanup、零 atexit
  残留；shutdown owner 评估（`PreparedHostRuntimeDependencies.close`/`_OwnedLifecycleRegistration`/
  `DefaultFinsRuntime` 无 close）与 exact files/functions/tests 列出。
- **S14-CTRL-06**：`stat_object` HEAD-only（`dayu-sha256` presence + size）；SHA 校验移至
  `get_object`/`Source.open`，返回 owner 明确、seekable、已验证 BinaryIO，StreamingBody
  不泄漏；list 全量/内部穷尽 pagination/按 key 排序/排除 `.dayu-staging/`。
- **S14-CTRL-07**：MinIO fixture TERM（`docker stop --time=1`）-> bounded 等待 -> KILL ->
  `docker rm -f`；删除前复核 name+label；cleanup bounded 总超时；fault injection + restart
  recovery、两个独立 writer 等真实 lane。
- **S14-CTRL-08**：test matrix（unit/journal/lease/startup/integration roundtrip/无本地
  fallback/两 writer/fault+restart/startup order）与 stop conditions。
- **S14-CTRL-09**：单 Fins writer + 同一共享 workspace 的 flock 式 admission
  （`.dayu/fins_writer.lock`，非阻塞 exclusive）+ 持有/释放生命周期（`PreparedHostRuntimeDependencies`
  私有持有、close 幂等释放、atexit exact-once、崩溃 OS 自动释放）；拒绝第二 writer、
  不 last-writer-wins；多 host 多 writer 显式归后续 durable job ownership。

## 关键状态机（remote journal，per-target publish_state）

顶层 `phase` 仅表示 batch/meta 阶段：

```text
staged -> metadata_committed -> cleanup_done
   \--> rolled_back（回滚：删 staging keys）
   metadata_committed + cleanup 失败 -> cleanup_pending（startup recovery 重试）
```

每个 target 独立携带 `publish_state: staged | final_verified`，bytes 发布进度只由它表达，
不得从顶层 phase 推导。commit 逐 target：copy 前持久 `staged`、copy 后立即原子持久
`final_verified`；copy/journal 写模糊以 head final digest/size 判定本 target 完成。

恢复（startup `ensure_batch_recovery` 重放，逐 token）：
- 逐 target：head final 的 digest+size 匹配期望 => 置 `final_verified`（即使 journal 仍写
  `staged`，绝不把部分 publish 当全未 publish）；不匹配且 staging 存在 => 完成发布；
  不匹配且 staging 缺失 => FAIL CLOSED（保留 journal/远端 objects）。
- 全部 targets verified 且 FS batch staging 目录完整 => 未 swap 则 metadata roll-forward；
  已 swap/committed 只删 staging keys。
- FS batch staging 缺失/损坏 => FAIL CLOSED，保留 journal/远端 objects，不删除、不宣称已恢复。
- 只删 operation-owned staging；禁止全前缀扫删；永不删除 final key。

## 自审追加修正（multi-target crash gap）

总控自审发现并已闭合：原契约顶层 `phase` 单薄，2+ targets 时“第 1 个 copy 后 crash”
会被误判为“finals 从未发布”。修正（master plan S14-CTRL-04/06/08 + Allowed）：

1. per-target `publish_state`（`staged|final_verified`）+ target 期望 digest/size 作为
   head 完成判定真值；顶层 `phase` 仅表 batch/meta 阶段。
2. commit 逐 target 原子持久（copy 前 staged、copy 后 final_verified）；copy 响应或
   journal 写模糊以 head final digest/size 幂等判定。
3. recovery 逐 target 独立：final 匹配 -> verified；未发布且 staging 存在 -> 完成发布；
   staging 缺失 -> FAIL CLOSED（保留 journal/远端 objects）；全部 targets verified 且
   FS staging 完整才 roll-forward；FS staging 缺失/损坏 FAIL CLOSED。
4. unit/MinIO fault matrix 新增 2+ targets 第 1 个 copy 后 crash、copy 后 journal 写前
   crash、recovery 后 metadata 与全部 bytes 一致。
5. Allowed 新增 `dayu/fins/storage/file_store.py`（仅 `list_objects` docstring contract
   修改，方法签名/语义不改），消除与“public protocol 冻结”的歧义。

其余裁决（Terra S14-01..04、MiM M1/M3/M4/M5、MiM M2 HEAD-only stat + verified get、
单 writer 拓扑、startup 顺序、依赖/pinned MinIO/secret/locator identity、S14-CTRL-10
逐 ID CLOSED-IN-PLAN）保持不变；两份 source review 仍只读。

## 校验

- `git diff --check` 通过；四份目标文档（master plan、codex fix、本 artifact、final
  corrective artifact）trailing whitespace 为零、final LF 齐全（追加自审修正后已重跑）。
- 未修改 production/tests/README/dependencies；全部 source review 只读。
- master plan 状态为 REVIEW OBSERVATIONS FIXED / AWAITING FINAL CORRECTIVE DUAL PLAN
  RE-REVIEW；fix 文档逐 ID 记录 Controller 裁决与 CLOSED-IN-PLAN/RE-REVIEW-REQUIRED
  （final corrective round 无 RE-REVIEW-REQUIRED：Terra 211302 四项与 MiM MR1/MR2 全部
  CLOSED-IN-PLAN，MR3 VERIFIED-NON-FINDING/CLOSED）。

## 最终 corrective 补充（round 3：Terra 211302 + MiM 211155）

final re-review 新增 findings（Terra S14-FINAL-01..04 全 High、MiM MR1/MR2/MR3）由
`docs/reviews/plan-fix-20260810-slice-1.4-final-corrective-deepseek.md` 详细展开，已全部
唯一化进 master plan S14-CTRL-03..13：S14-CTRL-11（Host toolset override 唯一 runtime）、
S14-CTRL-12（真实 producer blob+metadata 共享 batch）、S14-CTRL-13（destructive
状态机）、S14-CTRL-04/06/08/10 相应修订。本 round 只修改 master plan、codex fix 与两
份 fix artifacts；两份 final source review 保持只读。

## Final closure 补充（round 4：Terra 213617 + MiM Native 213634）

final closure re-review 新增 findings（Terra S14-REREVIEW-01/02/03，2H/1M；MiM Native
F-01，1M）由 `docs/reviews/plan-fix-20260810-slice-1.4-final-closure-deepseek.md` 详细
展开，已全部唯一化进 master plan S14-CTRL-04/05/08/10/11/12/13：(A) 同-core BatchToken
传播——`DefaultFinsRuntime` 持有唯一 `FsBatchingRepository`，经
`_build_pipeline_for_ticker`→`_build_pipeline`→`get_pipeline_from_normalized_ticker`→
`SecPipeline`/`CnPipeline` 逐层传递，host protocols（`SecDownloadWorkflowHost`/
`CnDownloadWorkflowHost`）暴露能力并在 per-ticker/per-document 循环显式
begin/commit/rollback，注入路径不再自建第二 core；(B) runtime/startup 唯一所有权——
`DefaultFinsRuntime.create` 只接受可选 `repository_set`，startup 先
`build_fs_repository_set(workspace_root, file_store=s3_store)` 再只传 `repository_set`，
`PreparedHostRuntimeDependencies` 独占并关闭 S3 store/lease；(C) destructive inventory
contraction——metadata mutation 比较 old/new inventory、local swap 前 journal delete
intents、processed meta 显式持久化 files inventory；(D) S3 batch admission——
`_execute_with_auto_batch` FS/local 保留 auto-begin、S3 模式无 token fail-loud
`s3_write_requires_batch`；(E) Fins-owned toolset fail-closed 按 exact toolset name 判定。
allowlist 精确展开并新增测试文件；S14-CTRL-08 test matrix/stop conditions 与
S14-CTRL-10 disposition 同步更新。本 round 只修改 master plan、codex fix、corrective
fix、final corrective fix 与 final closure fix；两份 final closure source review
（213617/213634）保持只读。状态置 REVIEW OBSERVATIONS FIXED / AWAITING FINAL CLOSURE
DUAL PLAN RE-REVIEW。

## Final closure corrective 补充（round 5：Terra final-closure S14-CLOSURE-01/02 + MiM Native 220137）

final closure corrective re-review 新增 findings（Terra
`plan-final-closure-rereview-20260810-slice-1.4-terra.md` S14-CLOSURE-01/02，2H；MiM
Native `plan-final-closure-rereview-20260810-slice-1.4-mimo-native.md` PASS/open0 记录为
证据）由 `docs/reviews/plan-fix-20260810-slice-1.4-final-closure-corrective-deepseek.md`
详细展开，已全部唯一化进 master plan S14-CTRL-12/13：(1) Host ingestion factory 同-core
唯一链——`DefaultFinsRuntime.batching_repository` → `build_ingestion_service_factory(...
batching_repository=self.batching_repository)` → `dayu.fins.ingestion.factory.
build_ingestion_service_factory` → `build_ingestion_service_from_normalized_ticker` →
`get_pipeline_from_normalized_ticker` → `SecPipeline`/`CnPipeline` 逐层显式传递同一
实例/同一 core，`dayu/fins/ingestion/factory.py` 加入 allowlist，`test_runtime_batch_injection.py`
扩展 runtime direct + ingestion factory 的 US/CN 与真实 Host ingestion 写 producer 同-core/
零无-token admission；(2) S3 fail-loud 全 mutation 最小 explicit boundary 逐名清单——
SEC/CN company upsert、SEC/CN overwrite clear、SEC stale cleanup、source reset、
processed clear、snapshot pre-cleanup+export（boundary 上移到
`_export_tool_snapshot_for_document`，export 不建第二 batch 复用 active same-core
token），每段 metadata/delete-only mutation 用同一 runtime batching_repository 最小
begin/commit/rollback、禁跨网络长期持有 token、S3 不恢复 auto-begin；
`dayu/fins/pipelines/sec_process_workflow.py` 加入 allowlist；S14-CTRL-08 test
matrix/stop conditions 与 S14-CTRL-10 disposition 同步更新。本 round 只修改 master
plan、四份既有 fix artifacts 与本 corrective fix；两份 final closure corrective source
review 保持只读。状态置 REVIEW OBSERVATIONS FIXED / AWAITING FINAL CORRECTIVE DUAL
PLAN RE-REVIEW；最终 gate 为双路 final corrective plan re-review PASS/open0。

## Terminal corrective 补充（round 6：Terra S14-CORRECTIVE-01/02 + MiM Native final-corrective rereview）

terminal corrective re-review 新增 findings（Terra
`plan-final-corrective-rereview-20260810-slice-1.4-terra.md` S14-CORRECTIVE-01/02，2H；
MiM Native `plan-final-corrective-rereview-20260810-slice-1.4-mimo-native.md`
PASS/open0 记录为证据）由
`docs/reviews/plan-fix-20260810-slice-1.4-terminal-corrective-deepseek.md` 详细展开。
Controller 架构修正（storage owner 显式 per-operation admission，不再对每个业务
caller 包事务 wrapper）已全部唯一化进 master plan S14-CTRL-12/13：
(A) exhaustive `_execute_with_auto_batch` admission 分类表 + AST/unit completeness
gate（闭合 S14-CORRECTIVE-01：新增 SEC/CN upload company upsert、upload overwrite
reset、SEC rejection registry save 真源；上传/registry 单短 AUTO_ATOMIC_ALLOWED
batch、零 wrapper、无嵌套、同 core/recovery）；
(B) S3 batch admission 改为私有 typed/frozen `BatchAdmission`
（`EXPLICIT_REQUIRED` vs `AUTO_ATOMIC_ALLOWED`，S3 无隐式默认）——EXPLICIT_REQUIRED
无 active token fail-loud `s3_write_requires_batch`、AUTO_ATOMIC_ALLOWED 至多一个短
内部 batch、FS/local 保留 auto-begin、active token 一律复用；MiM F-01 闭合语义修订
为 per-operation admission 分类（非全局 S3 fail-loud）；
(C) 网络边界契约（闭合 S14-CORRECTIVE-02）：SEC/CN 每 filing 在调用
`run_*_download_single_filing_stream` 之前 begin 一个同-core 显式 batch，允许覆盖该
filing 的远端 listing/download（及 CN Docling 转换）与随后 blob+metadata 写入直到
commit/rollback，token 不跨整个 ticker；删除"不得跨网络持 token"矛盾文字；新增
bounded `per_filing_timeout_seconds` 契约（`asyncio.timeout` 包裹整个 per-filing
窗口，timeout/cancel/network error 无条件 rollback 零 publish）；长持风险降为明确
residual。Terra S14-CORRECTIVE-01/02 全部 **CLOSED-IN-PLAN**；S14-CLOSURE-01、
S14-REREVIEW-02/03、exact toolset names 保持 closed 无回归。master plan 状态置
**REVIEW OBSERVATIONS FIXED / AWAITING TERMINAL DUAL PLAN RE-REVIEW**；两份 final
corrective source review 保持只读。最终 gate 为双路 **terminal plan re-review**
PASS/open0。


## Terminal final corrective 补充（round 7：Terra S14-TERMINAL-01/02 + MiM terminal rereview 三项）

terminal plan re-review 新增 findings（Terra
`docs/reviews/plan-terminal-rereview-20260810-slice-1.4-terra.md`
S14-TERMINAL-01/02，2H；MiM Native
`docs/reviews/plan-terminal-rereview-20260810-slice-1.4-mimo-native.md`
delete_entry High + upload overwrite Medium + CN timeout Medium）全部 ACCEPT 并合并
闭合，由 `docs/reviews/plan-fix-20260810-slice-1.4-terminal-final-corrective-deepseek.md`
详细展开，全部唯一化进 master plan S14-CTRL-03/04/08/10/12/13：
(1) **completeness 真源升级（闭合 Terra S14-TERMINAL-01）**——inventory 真源从
"`_execute_with_auto_batch` 调用点"扩展为"storage core 全部公开写入口 + 直接
FileStore/blob 原语 + manifest/inventory helper"；`replace_source_meta`
（`_fs_source_document_core.py:323-398`，公开协议 `repository_protocols.py:157-165`，
真实 SEC/CN rebuild callers `sec_rebuild_workflow.py:399`/`cn_download_rebuild.py:234-239`）
改为同一 storage-owner `_execute_with_auto_batch` + `BatchAdmission.AUTO_ATOMIC_ALLOWED`，
在 owner batch 内完成 old/new files inventory diff、removed delete intents、source
meta + filing/material manifest staging/swap，禁止先直接写 target；AST gate 断言公开
写入口集合与分类表一一对应并抓直接 put/delete/write-json+manifest 绕过；SEC/CN
rebuild 真实 owner/tests 加入 allowlist；
(2) **per-filing terminal 状态机（闭合 Terra S14-TERMINAL-02）**——SEC/CN outer
workflow 定义私有 typed/frozen PENDING/COMPLETED/FAILED 状态消费 single-filing
events；只有恰好一个 FILING_COMPLETED（含现有 skip）且 pre-commit cancel/deadline
fence 通过才 commit；FILING_FAILED 正常 return、缺/重复/矛盾 terminal、
CancelledError、TimeoutError、其它 exception 均 rollback 同一 token；外部 event 与
现有 continue/stop 语义不变；`commit_batch` 同步开始后为不可取消决策点（此前
deadline 保证 rollback 零 publish，开始后异常/crash 只按 S14-CTRL-04
journal/recovery 收敛，不宣称 timeout 能中断同步 commit）；
(3) **delete_entry S3 唯一行为（闭合 MiM delete_entry H）**——S3+active batch 绝不
直接 remote delete，用私有同-core stage-delete helper 记录 final key、expected
sha/size 为 journal `action=delete`/`delete_state=pending`（仅改 staging local），
remote delete 只在 metadata swap 后 cleanup/recovery；destructive AUTO 方法从 old
authoritative inventory 逐 key 复用同一 helper 后只 rmtree/unlink staging、无 prefix
sweep；FS/local 保留本地删除；
(4) **upload overwrite（闭合 MiM upload-overwrite M）**——company upsert 保持独立短
AUTO；overwrite reset 移进 `DoclingUploadService.execute_upload` 已有 per-document
显式 batch（begin → `reset_source_document` 复用 token → store_file + source meta →
commit；失败 rollback 保留旧 source/bytes）；workflow 不得预先 reset，无外层
wrapper/嵌套 batch；
(5) **CN blocking timeout（闭合 MiM CN timeout M）**——`asyncio.timeout` 只取消 outer
task，to_thread worker 可继续到现有有限 provider/request timeout（CN PDF download
底层 `request_timeout_seconds`）但不得访问 repo/batch；outer timeout 立即
rollback/清 active token/丢弃 late result；底层无有限 timeout 的 to_thread 路径不得
纳入"可中断"承诺并 STOP；Docling 转换段保留 round 6 residual。

Terra S14-TERMINAL-01/02 与 MiM 三项（delete_entry/upload overwrite/CN timeout）全部
**CLOSED-IN-PLAN**；S14-CORRECTIVE-01/02、S14-CLOSURE-01/02、S14-REREVIEW-02/03、
exact toolset names 保持 closed 无回归。allowlist、test matrix、stop conditions、
residuals、finding table、completion 全部同步；两份 terminal source review
（plan-terminal-rereview terra/mimo-native）保持只读。master plan 状态置
**REVIEW OBSERVATIONS FIXED / AWAITING TERMINAL FINAL DUAL PLAN RE-REVIEW**；最终 gate
为 Terra + MiM Native 双路 **terminal final plan re-review** PASS 且 open
H/M/L=`0/0/0`。


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
