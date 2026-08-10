# Slice 1.4 S3 Fins blob repository final closure corrective plan fix（DeepSeek worker）

- **Worker**：DeepSeek Flash fix worker
- **日期**：2026-08-10
- **基线**：`5d7e6bb`（branch `codex/investment-platform`，HEAD/worktree 冻结为只读审计）
- **状态**：**SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **任务范围**：只修 master plan Slice 1.4
  （`docs/plans/2026-08-10-investment-platform-restoration.md`）与四份既有 fix artifacts
  （`plan-fix-20260810-slice-1.4-s3-blob-repository-codex.md`、
  `plan-fix-20260810-slice-1.4-s3-blob-repository-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-closure-deepseek.md`）；新增本 artifact；
  production/tests/README/dependencies 全部冻结；未安装依赖、未 pull 镜像、未运行
  live/network/model/broker、未 commit/push/PR。
- **Final closure corrective source reviews（只读）**：
  `docs/reviews/plan-final-closure-rereview-20260810-slice-1.4-terra.md`
  （Terra，FAIL，S14-CLOSURE-01..02，2H）、
  `docs/reviews/plan-final-closure-rereview-20260810-slice-1.4-mimo-native.md`
  （MiM Native，PASS，open 0/0/0）。

## Controller 裁决（final closure corrective，唯一实现，不留二选一）

- Terra final-closure re-review **FAIL / open 2H**：S14-CLOSURE-01（Host ingestion
  factory 绕过计划规定的唯一 batching 传播链，High）、S14-CLOSURE-02（S3 fail-loud
  与真实下载/快照工作流的 boundary 顺序矛盾，High）**两项均 ACCEPT**。
- MiM Native final-closure re-review **PASS / open 0/0/0**：记录为证据，但该 review 未
  覆盖 Terra 指出的 ingestion factory 链与真实 mutation boundary 顺序缺口，不能替代
  上述两项 High 的修复。
- implementation 继续冻结：只改 plan 与 fix artifacts，不触碰 source/code/tests/
  README/deps。

## 只读 callgraph 审计（final closure corrective round，支撑唯一化）

本 round 按 Terra 两项 finding 的 direct evidence 重新只读核对真实调用链（未修改任何
production 文件）：

- **Host ingestion factory 真实链（S14-CLOSURE-01 直接证据）**：
  - `DefaultFinsRuntime.build_ingestion_service_factory()`（`service_runtime.py:2497-2508`）
    当前只传 5 个窄仓储 + processor registry，**无 batching_repository**；
  - `dayu/fins/ingestion/factory.py:30-39` `build_ingestion_service_factory` 签名与闭包
    （`:78-101`）均无 batching 参数；`:92` 调用
    `build_ingestion_service_from_normalized_ticker` 未透传 batching；
  - `dayu/fins/pipelines/factory.py:116-126` `build_ingestion_service_from_normalized_ticker`
    无 batching 参数，`:151` 调用 `get_pipeline_from_normalized_ticker`（`:54-65`）也未
    透传；
  - 结论：真实 Host `ingestion` toolset（`build_fins_toolset_registrars` 闭包 →
    `build_ingestion_service_factory` → `get_ingestion_manager_key`，S14-CTRL-11）构造的
    pipeline 没有同-core batch capability；S3 模式下 producer 写将触发
    `s3_write_requires_batch` 或实现者被迫建第二 `FsBatchingRepository`。
- **S3 fail-loud 下真实 mutation 位置（S14-CLOSURE-02 直接证据）**——逐一核对
  `_execute_with_auto_batch` 分发的真实 mutator 与计划指定 boundary 的错位：
  - SEC `run_download_stream_impl`（`sec_download_workflow.py:207`）在指定下载循环
    （`:425-460`）**之前**调用 `host._upsert_company_meta`（`:371-376`，
    `_fs_company_meta_core.py:130-143`）与 overwrite `clear_filings_dir`
    （`:378-379`，`_fs_maintenance_core.py:330`），**之后**调用 stale cleanup
    （`:475`，`sec_pipeline.py:1928-1955` → `_fs_maintenance_core.py:383`）；
  - CN `run_cn_download_stream_impl`（`cn_download_workflow.py:41`）在候选循环
    （`:259-264`）之前调用 company upsert（`:201-206`）与 overwrite clear
    （`:224`）；
  - SEC/CN snapshot pre-cleanup（`cleanup_processed_snapshot_dir`，
    `processed_snapshot_helpers.py:61-87` → `repository.delete_entry`，
    `_fs_blob_core.py:70-90`）位于 `_export_tool_snapshot_for_document`
    （`sec_pipeline.py:1754`/`cn_pipeline.py:1502`）内、`export_tool_snapshot`
    （`tool_snapshot_export.py:516`）调用**之前**；
  - source reset（`cn_download_filing_workflow.py:159,292`、`docling_upload_service.py:969`
    → `_fs_source_document_core.py:504`）与 processed clear（SEC
    `sec_process_workflow.py:328`、CN `cn_pipeline.py:989` →
    `_fs_processed_core.py:233`）同属 `_execute_with_auto_batch` 分发路径；
  - 结论：S3 fail-loud 生效后，这些真实 mutation 在无 active same-core token 时
    确定性抛 `s3_write_requires_batch`，计划仅规定七条 `store_file` producer 边界
    不足闭合。

## 唯一化契约（master plan S14-CTRL-12/13 修订）

### A. Host ingestion factory 同-core propagation（闭合 Terra S14-CLOSURE-01）

1. 真实唯一链固定为：
   `DefaultFinsRuntime.batching_repository`
   -> `DefaultFinsRuntime.build_ingestion_service_factory(... batching_repository=self.batching_repository)`
   -> `dayu.fins.ingestion.factory.build_ingestion_service_factory(... batching_repository)`
   （新增 keyword-only，闭包 `factory(ticker)` 透传）
   -> `build_ingestion_service_from_normalized_ticker(... batching_repository)`
   （新增 keyword-only 并透传）
   -> `get_pipeline_from_normalized_ticker(... batching_repository)`（新增 keyword-only）
   -> `SecPipeline`/`CnPipeline`。
2. 该链必须是**同一实例/同一 `_FsRepositorySet`/同一 core**；禁止第二
   `FsBatchingRepository`、global cache、wrapper。
3. 能力只停留在 Fins runtime/factory/pipeline 内部编排：
   `FinsRuntimeProtocol.build_ingestion_service_factory`（`service_runtime.py:757`）签名
   仍为 `() -> IngestionServiceFactory`，`IngestionServiceFactory = Callable[[str],
   FinsIngestionService]`（`ingestion/factory.py:27`）不变；Host/Agent/tool contract
   不见 repository/core。
4. allowlist 加入 `dayu/fins/ingestion/factory.py`。
5. `tests/fins/test_runtime_batch_injection.py` 扩展：runtime direct pipeline 与
   ingestion factory 的 US/CN 均收到同一 batching_repository 实例（断言
   `pipeline._batching_repository is runtime.batching_repository`）；真实 Host
   ingestion scene 至少执行一条写 producer（经 `FinsIngestionService` 完成一次
   `store_file`+metadata 写）并证明同-core、零无-token admission。

### B. S3 fail-loud 全 mutation 最小 explicit boundary（闭合 Terra S14-CLOSURE-02）

1. 不只围住七条 `store_file` producer；S14-CTRL-12 逐名列出（owner/caller/函数/位置）：
   SEC/CN company upsert（`sec_download_workflow.py:371-376`、
   `cn_download_workflow.py:201-206`）、SEC/CN overwrite filing clear
   （`sec_download_workflow.py:378-379`、`cn_download_workflow.py:224`）、SEC stale
   filing cleanup（`sec_download_workflow.py:475`）、source reset
   （`cn_download_filing_workflow.py:159,292`、`docling_upload_service.py:969`）、
   processed clear（`sec_process_workflow.py:328`、`cn_pipeline.py:989`）、SEC/CN
   snapshot pre-cleanup + export（`sec_pipeline.py:1754`/`cn_pipeline.py:1502`）。
2. 每段 metadata/delete-only mutation 使用**同一 runtime batching_repository** 最小
   explicit begin/commit/rollback；异常一律 `rollback_batch`；**禁止跨网络下载长期
   持有 token**；blob+metadata 保持既有 per-filing/per-document 边界（七条 producer
   清单不变）。
3. snapshot 的 boundary **上移到真实 caller `_export_tool_snapshot_for_document`**，
   一次覆盖 `_cleanup_processed_snapshot_dir` + `export_tool_snapshot`；`export_tool_snapshot`
   内**不得再创建第二 batch**，有 active same-core token 时复用（经
   `_execute_with_auto_batch` 复用分支）。
4. S3 不恢复 auto-begin；FS/local 现有行为不变；S14-CTRL-13 继续 metadata-first
   delete/journal/recovery，**不得 prefix sweep**。
5. allowlist 加入 `dayu/fins/pipelines/sec_process_workflow.py`。
6. S14-CTRL-08 测试在 staged store 下断言：每个 mutator 已有 same-core token、delete
   intent ordering（head 记录 → FS swap → post-commit 幂等 delete）正确、
   operation/commit 异常与 restart 收敛、零 S3 auto-begin；覆盖 SEC/CN
   `overwrite=True`、company upsert、stale cleanup、snapshot 含旧文件、source/
   processed destructive branches。
7. 若实现时发现任何真实 mutator 仍在 token 外 => **STOP 并逐名报告**，不得用宽泛
   "有路径"替代逐名清单（已写入 S14-CTRL-08 stop conditions）。

## 逐 ID 处置汇总

| Finding | 严重程度 | 处置 | 闭合位置 |
| --- | --- | --- | --- |
| Terra S14-CLOSURE-01（Host ingestion factory 绕过唯一 batching 传播链） | High | **CLOSED-IN-PLAN** | S14-CTRL-12（A：ingestion factory 同-core 唯一链 + `ingestion/factory.py` allowlist + 测试扩展） |
| Terra S14-CLOSURE-02（S3 fail-loud 下真实 mutation boundary 顺序缺口） | High | **CLOSED-IN-PLAN** | S14-CTRL-12/13（B：逐名 mutation 最小 explicit boundary + snapshot boundary 上移 + `sec_process_workflow.py` allowlist + 测试/stop 同步） |

逐 ID 均无 **RE-REVIEW-REQUIRED**；最终闭合仍以 Terra + MiM Native 双路 **final
corrective plan re-review** PASS 且 open H/M/L=`0/0/0` 为 gate。原 round 1/2/3/4 裁决
（Terra S14-01..04、MiM M1..M5、Terra S14-FINAL-01..04、MiM MR1/MR2/MR3、Terra
S14-REREVIEW-01..03、MiM F-01）保持历史不变。

## 校验

- `git diff --check` 通过；修改的六份文档（master plan、codex fix、corrective fix、
  final corrective fix、final closure fix、本 artifact）trailing whitespace 为零、
  final LF 齐全。
- 未修改 production/tests/README/dependencies；八份 source review（204331/204201/
  211302/211155/213617/213634/final-closure-terra/final-closure-mimo-native）保持只读。
- master plan 状态：**SLICE 1.4 REVIEW OBSERVATIONS FIXED / AWAITING FINAL CORRECTIVE
  DUAL PLAN RE-REVIEW**。
- finding completeness：Terra S14-CLOSURE-01/02 全部 **CLOSED-IN-PLAN**（分别闭合于
  S14-CTRL-12、S14-CTRL-12/13）；MiM Native 220137 PASS/open0 已记录为证据（未覆盖
  上述两缺口）。

## Terminal corrective 补充（round 6：Terra S14-CORRECTIVE-01/02 + MiM Native final-corrective rereview）

terminal corrective re-review 新增 findings（Terra
`docs/reviews/plan-final-corrective-rereview-20260810-slice-1.4-terra.md`
S14-CORRECTIVE-01/02，2H；MiM Native
`docs/reviews/plan-final-corrective-rereview-20260810-slice-1.4-mimo-native.md`
PASS/open0 记录为证据，不覆盖 Terra 直接反例）由
`docs/reviews/plan-fix-20260810-slice-1.4-terminal-corrective-deepseek.md` 详细展开。
Controller 架构修正：**放弃对每个业务 caller 逐一包事务 wrapper（会把事务知识泄漏到
所有 workflow），改为 storage owner 显式 per-operation admission**，已全部唯一化进
master plan S14-CTRL-12/13：

- **(A) 完整 mutation inventory + admission 分类（闭合 S14-CORRECTIVE-01）**：不再用
  "八类"；以全部 `_execute_with_auto_batch` 调用点与 dayu/fins production callers 的
  交叉为真源写 exhaustive 分类表（新增 SEC/CN upload company upsert +
  overwrite reset + SEC rejection registry save 等真源），并加 AST/unit completeness
  gate（每个调用点显式传 `BatchAdmission` 分类，缺失/未知即 fail；未归类 caller 即
  STOP）。上传/registry 路径零业务 wrapper：单短 `AUTO_ATOMIC_ALLOWED` batch、
  无嵌套、同 core/recovery；上传测试 owner
  `tests/fins/test_sec_pipeline_upload_filing_stream.py`/`test_sec_pipeline_upload_material_stream.py`/
  `test_cn_pipeline.py` 加入 allowlist。
- **(B) S3 batch admission 改为 per-operation 分类（修正 MiM F-01 闭合语义）**：
  `_fs_storage_infra` 新增私有 typed/frozen `BatchAdmission`
  （`EXPLICIT_REQUIRED` vs `AUTO_ATOMIC_ALLOWED`，S3 无隐式默认）；S3
  EXPLICIT_REQUIRED 无同-core active token => `s3_write_requires_batch` 零 auto
  begin/commit；AUTO_ATOMIC_ALLOWED 方法自身即完整原子语义单元、至多一个短内部
  batch；FS/local 保留 auto-begin；active token 一律复用（禁嵌套）。跨
  repository/blob+metadata 原语（`store_file`/`store_rejected_filing_file`/
  `delete_entry`）分类 EXPLICIT_REQUIRED，其 producer 边界保持显式同-core；完整
  单-repository metadata/destructive 操作（company upsert、独立 clear/reset/stale
  cleanup、rejection registry save、processed clear 等）分类 AUTO_ATOMIC_ALLOWED。
- **(C) 网络边界契约（闭合 S14-CORRECTIVE-02）**：删除"不得跨网络持 token"绝对约束；
  SEC/CN 每个 filing 在调用 `run_*_download_single_filing_stream` 之前 begin 一个
  同-core 显式 batch，允许覆盖该 filing 的远端 listing/download（及 CN Docling
  转换）与随后 blob+metadata 写入直到 commit/rollback；**token 绝不扩到整个 ticker
  循环**。生命周期由既有 per-request timeout + cancel_checker + 任务取消有界，并
  **新增 bounded `per_filing_timeout_seconds` 契约**（`asyncio.timeout` 包裹整个
  per-filing 窗口；当前不存在 per-filing/overall 聚合 timeout，不假装存在）；
  timeout/cancel/network error 无条件 rollback、零 publish，继续/停止行为保持现有
  owner contract；长持风险降为明确 residual（慢源占用同 ticker active batch、不泄漏
  第二 writer、由 timeout/cancel/metrics 缓解）。

Terra S14-CORRECTIVE-01/02 全部 **CLOSED-IN-PLAN**（S14-CTRL-12/13）；MiM F-01 闭合
语义修订为 per-operation admission 分类（非全局 S3 fail-loud）；S14-CLOSURE-01、
S14-REREVIEW-02/03、exact toolset names 保持 closed 无回归。master plan 状态置
**REVIEW OBSERVATIONS FIXED / AWAITING TERMINAL DUAL PLAN RE-REVIEW**；两份 final
corrective source review（final-corrective-rereview terra/mimo-native）保持只读。


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
