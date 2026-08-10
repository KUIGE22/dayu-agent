# Slice 1.4 S3 Fins blob repository terminal corrective plan fix（DeepSeek worker）

- **Worker**：DeepSeek Flash fix worker
- **日期**：2026-08-10
- **基线**：`5d7e6bb`（branch `codex/investment-platform`，HEAD/worktree 冻结为只读审计）
- **状态**：**SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **任务范围**：只修 master plan Slice 1.4
  （`docs/plans/2026-08-10-investment-platform-restoration.md`）与五份既有 fix artifacts
  （`plan-fix-20260810-slice-1.4-s3-blob-repository-codex.md`、
  `plan-fix-20260810-slice-1.4-s3-blob-repository-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-closure-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-closure-corrective-deepseek.md`）；新增本 artifact；
  production/tests/README/dependencies 全部冻结；未安装依赖、未 pull 镜像、未运行
  live/network/model/broker、未 commit/push/PR。
- **Terminal corrective source reviews（只读）**：
  `docs/reviews/plan-final-corrective-rereview-20260810-slice-1.4-terra.md`
  （Terra，FAIL，S14-CORRECTIVE-01..02，2H）、
  `docs/reviews/plan-final-corrective-rereview-20260810-slice-1.4-mimo-native.md`
  （MiM Native，PASS，open 0/0/0）。

## Controller 裁决（terminal corrective，唯一实现，不留二选一）

- Terra final-corrective re-review **FAIL / open 2H**：S14-CORRECTIVE-01（"八类"mutation
  清单遗漏上传与 rejection registry 路径，High）、S14-CORRECTIVE-02（producer 的计划
  batch 起点仍跨越真实网络下载，与"不得长持 token"互相矛盾，High）**两项均 ACCEPT**。
- MiM Native final-corrective re-review **PASS / open 0/0/0**：记录为证据，但该 review
  未覆盖 Terra 指出的上传/registry 真源与网络边界顺序缺口，不能替代上述两项 High 的
  修复。
- **Controller 架构修正（本 round 核心）**：全局 S3 fail-loud 会让事务知识泄漏到所有
  workflow（每个业务 caller 都要知道 batch 契约）；**放弃对每个业务 caller 逐一包事务
  wrapper，改为在 storage owner 显式 per-operation admission 分类**；网络边界采用最小
  契约（per-filing 显式 batch 允许跨远端 fetch/stream/Docling），不引入两阶段暂存文件
  系统、第二 manifest 或新 transaction API。
- implementation 继续冻结：只改 master plan 与 fix artifacts，不触碰
  source/code/tests/README/deps。

## 只读 callgraph 审计（terminal corrective round，支撑唯一化）

本 round 按 Terra 两项 finding 的 direct evidence 只读核对真实调用链与 timeout/cancel
覆盖（未修改任何 production 文件）：

- **上传/registry 真源（S14-CORRECTIVE-01 直接证据）**：
  - SEC `run_upload_filing_stream`/`run_upload_material_stream`
    （`sec_upload_workflow.py:104,279`）在 `:182-189,375-382` 调用
    `upsert_company_meta_for_upload`（→`FsCompanyMetaRepository.upsert_company_meta`，
    `_fs_company_meta_core.py:143`），随后 `:190-198,383-391` 调用
    `reset_upload_target_for_overwrite`（→`reset_source_document`，
    `docling_upload_service.py:935-973,969` → `_fs_source_document_core.py:262`），
    之后才进入 Docling `execute_upload`（producer 4 per-document batch）；
  - CN `CnPipeline.upload_filing_stream`/`upload_material_stream`
    （`cn_pipeline.py:470,711`）同样在 `:547-554,801-808` company upsert、
    `:555-563,809-817` overwrite reset，之后才进入 `execute_upload`；
  - SEC 下载 `run_download_stream_impl` 在 per-filing 循环**之后**
    （`sec_download_workflow.py:464`）调用 `save_rejection_registry`
    （`sec_download_state.py:49-68` → `_fs_maintenance_core.py:65-88`，
    `_execute_with_auto_batch` 分发）；
  - 结论：S3 模式下这些真实 mutation 若被全局 fail-loud 且无任何 admission 通道，
    上传/registry 路径确定性失败；"八类"表未列它们。
- **`_execute_with_auto_batch` 全部调用点（storage core private mixins，共 23 处）**：
  `_fs_company_meta_core.py:143`；`_fs_maintenance_core.py:83,170,324,375`；
  `_fs_processed_core.py:48,69,90,182,227`；
  `_fs_source_document_core.py:73,95,117,140,166,188,210,233,262`；
  `_fs_blob_core.py:85`；`_fs_storage_infra.py:912,951,990`。另两个 blob 原语
  `store_file`（`_fs_blob_core.py:115`）与 `store_rejected_filing_file`
  （`_fs_maintenance_core.py:114`）**不经** `_execute_with_auto_batch`、直连
  `file_store.put_object`（S3 staging admission 在 `_StagedFileStore` 层）。
  → admission 分类枚举、AST/unit completeness gate 完全可表达在
  `dayu/fins/storage` 私有 owner 内（`_execute_with_auto_batch` 是 `_FsStorageInfra`
  私有方法，全部调用点在 `_fs_*_core.py` 私有 mixin，公共协议
  `repository_protocols.py`/Host 零改动），**不触发 STOP**。
- **timeout/cancel 覆盖验证（S14-CORRECTIVE-02 决策依据，直接证据）**：
  - per-request HTTP timeout **存在**：SEC `SecDownloader._request_timeout_seconds`
    （默认 30s，`sec_downloader.py:67,758,1409,1415`）；CN
    `cninfo_downloader.py:212`/`hkexnews_downloader.py:247`
    `request_timeout_seconds`——每个独立网络请求有界；
  - cancel_checker **存在**：SEC filing 边界（`sec_download_workflow.py:426`）、CN PDF
    gate 与文档边界（`cn_download_filing_workflow.py:79,382,413`），job manager 注入
    （`ingestion/job_manager.py:312`）；`CancelledError` CN 显式捕获
    （`cn_download_workflow.py:286`）、SEC 向上传播；
  - **per-filing 聚合 timeout 不存在**、**enforced overall workflow timeout 不存在**
    （tool 层 `timeout_budget` 被丢弃 `ingestion_tools.py:77`；`_run_download_job`
    无 deadline）——**因此按 Controller 指令新增 bounded `per_filing_timeout_seconds`
    契约，不假装存在**；
  - SEC 下载流内无 mid-filing cancel 检查（`sec_download_filing_workflow.py` 不接收
    cancel_checker）——由 per-filing batch 边界在 begin 前/commit 前检查 cancel_checker
    与 per-filing timeout 闭合；CN Docling 转换为无界 CPU 段但被
    `cn_download_filing_workflow.py:382,413` 的 cancel 检查包围。

## 唯一化契约（master plan S14-CTRL-12/13 修订）

### A. 完整 mutation inventory + per-operation admission 分类（闭合 Terra S14-CORRECTIVE-01）

1. **放弃"八类"**：以全部进入 `_execute_with_auto_batch` 的 storage core public
   mutator 与 dayu/fins production callers 的交叉为真源，写 exhaustive 分类表（master
   plan S14-CTRL-12 表，16 组含内部 helper 与 blob 原语）。分类规则：
   - 跨 repository/blob+metadata 原语（`store_file`、`store_rejected_filing_file`，
     以及正确性依赖随后 metadata 更新的 `delete_entry`）→ **`EXPLICIT_REQUIRED`**，
     必须在 producer 显式 same-core batch 内；
   - 完整单-repository metadata/destructive 操作（company upsert、独立
     clear/reset/stale cleanup、rejection registry save、processed clear、source
     CRUD/upsert、manifest helper 等）→ **`AUTO_ATOMIC_ALLOWED`**，仅当方法自身原子
     journal 全部远端 publish/delete + metadata swap；存在跨 repository 不变量者必须
     改判 `EXPLICIT_REQUIRED` 并入 producer 边界。
2. **新增真源行**（S14-CORRECTIVE-01 直接证据）：SEC/CN upload company upsert
   （`sec_upload_workflow.py:182,375`/`cn_pipeline.py:547,801`）、upload overwrite
   reset（`reset_upload_target_for_overwrite`→`reset_source_document`，
   `docling_upload_service.py:969`）、SEC `save_rejection_registry`
   （`sec_download_workflow.py:464`），全部 `AUTO_ATOMIC_ALLOWED`；上传/registry 路径
   **零业务 wrapper**——S3 下各自恰好一个短 auto-atomic batch（同一 runtime
   batching_repository、同 core、走既有 journal/recovery、无嵌套、不进入 Docling
   producer 的 active token）。
3. **completeness gate**：AST/unit（`tests/fins/test_batch_admission_classification.py`）
   枚举 `_fs_company_meta_core.py`/`_fs_maintenance_core.py`/`_fs_processed_core.py`/
   `_fs_source_document_core.py`/`_fs_blob_core.py`/`_fs_storage_infra.py` 全部
   `_execute_with_auto_batch` 调用点，断言每个显式传 `BatchAdmission` 分类字面量；
   **缺失/未知分类即 fail**；实现期任何未归类 caller、或 EXPLICIT_REQUIRED 原语在 S3
   无 active same-core token 被触达 => **STOP 并逐名报告**。
4. **allowlist**：`tests/fins/test_sec_pipeline_upload_filing_stream.py`、
   `tests/fins/test_sec_pipeline_upload_material_stream.py`、`tests/fins/test_cn_pipeline.py`
   （upload/registry auto-atomic batch 测试）与 `tests/fins/test_batch_admission_classification.py`
   加入；`sec_upload_workflow.py`/`cn_pipeline.py` 上传方法**无需批量改造**
   （AUTO_ATOMIC_ALLOWED 由 storage owner 闭合），不加入生产 allowlist；下载 workflow
   与 `_fs_storage_infra.py` 等已在 allowlist。

### B. S3 batch admission 改为 per-operation 分类（修正 MiM F-01 闭合语义）

1. `_fs_storage_infra` 新增**私有 typed/frozen `BatchAdmission` 枚举**
   （`EXPLICIT_REQUIRED`/`AUTO_ATOMIC_ALLOWED`，S3 无隐式默认）。
2. `_execute_with_auto_batch` 行为：FS/local 保留 auto-begin（无论分类）；S3
   EXPLICIT_REQUIRED 无同-core active token => `s3_write_requires_batch`、零 auto
   begin/commit；S3 AUTO_ATOMIC_ALLOWED => 至多一个短内部 batch（begin→op→
   commit/rollback，同一 core、journal/恢复）；**active token 一律复用（禁嵌套，
   `begin_batch` 对 active ticker 抛 RuntimeError）**。
3. 模式判定继续用 `@runtime_checkable` 私有 Protocol + `isinstance(self._file_store,
   `_StagedFileStore`)`，不靠类型猜测/动态属性。
4. **MiM F-01 闭合语义修订**：歧义由 per-operation 显式 admission 消除，非全局 S3
   fail-loud（master plan S14-CTRL-10 disposition 相应更新）。

### C. 网络边界契约（闭合 Terra S14-CORRECTIVE-02，最小实现）

1. **撤销"SEC/CN per-filing token 不得跨外部下载/转换网络"绝对约束，删除该矛盾文字**
   （master plan 正文已清除；仅 changelog 历史与 disposition 的"删除"表述保留）。
2. **唯一契约**：SEC/CN 每个 filing 在调用 `run_*_download_single_filing_stream` 之前
   begin 一个同-core 显式 batch；该 batch 允许覆盖该 filing 的远端 listing/download
   （及 CN Docling 转换）与随后的 blob+metadata 写入，直到 commit/rollback；**token
   绝不扩到整个 ticker 循环**。这是 streaming callback 与原子 blob+metadata 的明确
   例外；single-writer admission 已存在（S14-CTRL-09）。
3. **生命周期有界（基于验证，不假装存在）**：既有 per-request timeout 覆盖每个网络
   请求；cancel_checker 在 SEC filing 边界与 CN PDF gate/文档边界生效；任务取消
   （CancelledError）在 CN 被捕获、SEC 传播；**新增 bounded `per_filing_timeout_seconds`
   契约**——`run_download_stream_impl`/`run_cn_download_stream_impl` keyword-only
   参数 + 模块级有限正数默认，`asyncio.timeout` 包裹整个 per-filing 窗口。
4. **timeout/cancel/network error 无条件 `rollback_batch`、零 publish**；继续/停止行为
   保持现有 owner contract（SEC 向上传播、CN 产出 FILING_FAILED 后继续下一 filing）。
5. **residual（明确降级，非缺陷）**：慢源/超大 Docling 占用同 ticker 的 active batch
   （同 ticker 的恢复与后续 mutation 被阻塞），但不泄漏第二 writer；由 per-filing
   timeout、cancel_checker、job cancel 与 metrics 缓解。
6. **测试反向锁定**：SEC list/download 流、CN PDF download/Docling 期间恰有同一 active
   token；每 filing 一个 token；网络失败/取消/timeout rollback 且零 publish；后续
   filing 按现有 contract 可新 token；绝不第二 batch/auto-begin；ticker 循环外
   company/clear/registry/stale cleanup 各自短 AUTO_ATOMIC_ALLOWED batch。

## 逐 ID 处置汇总

| Finding | 严重程度 | 处置 | 闭合位置 |
| --- | --- | --- | --- |
| Terra S14-CORRECTIVE-01（"八类"mutation 清单遗漏上传与 rejection registry 路径） | High | **CLOSED-IN-PLAN** | S14-CTRL-12（A：exhaustive admission 分类表 + AST/unit completeness gate + upload/registry 真源 + 上传测试 owner allowlist；上传/registry 单短 AUTO_ATOMIC_ALLOWED batch、零 wrapper、无嵌套、同 core/recovery） |
| Terra S14-CORRECTIVE-02（producer 的计划 batch 起点仍跨越真实网络下载，与"不得长持 token"矛盾） | High | **CLOSED-IN-PLAN** | S14-CTRL-12（C：网络边界契约——per-filing 显式 batch 允许跨远端 list/download/Docling + blob+metadata 写直到 commit/rollback、token 不跨整个 ticker、删除矛盾文字、bounded `per_filing_timeout` 契约、长持 residual 明确化、测试反向锁定） |
| MiM F-01（S3 模式 auto-begin 行为歧义） | Medium | **CLOSED-IN-PLAN（闭合语义修订）** | S14-CTRL-12（B：`BatchAdmission` per-operation 分类消除歧义，非全局 S3 fail-loud） |

逐 ID 均无 **RE-REVIEW-REQUIRED**。S14-CLOSURE-01（Host ingestion factory 同-core 链）、
S14-REREVIEW-02/03（runtime/startup 唯一 ownership、inventory contraction）、exact
toolset names 均保持 **closed 无回归**（本 round 未触碰其契约）。原 round 1/2/3/4/5
裁决（Terra S14-01..04、MiM M1..M5、S14-FINAL-01..04、MR1/MR2、MR3、S14-REREVIEW-01..03、
F-01、S14-CLOSURE-01/02）保持历史不变。

## 校验

- `git diff --check` 通过；修改的七份文档（master plan、五份既有 fix artifacts、本
  artifact）trailing whitespace 为零、final LF 齐全。
- 未修改 production/tests/README/dependencies；十份 source review 保持只读
  （204331/204201/211302/211155/213617/213634/final-closure-terra/
  final-closure-mimo-native/final-corrective-terra/final-corrective-mimo-native）。
- master plan 状态：**SLICE 1.4 REVIEW OBSERVATIONS FIXED / AWAITING TERMINAL DUAL
  PLAN RE-REVIEW**。
- finding completeness：Terra S14-CORRECTIVE-01/02 全部 **CLOSED-IN-PLAN**；MiM Native
  final-corrective rereview PASS/open0 已记录为证据（未覆盖上述两缺口）。

## 新增 gap / residual（如实记录，非假设）

1. **per-filing 聚合 timeout 与 enforced overall workflow timeout 原本不存在**：本次以
   新增 bounded `per_filing_timeout_seconds` 契约闭合，不宣称既有机制已覆盖。
2. **SEC 下载流内无 mid-filing cancel 检查**（`sec_download_filing_workflow.py` 不接收
   cancel_checker）：per-filing batch 边界在 begin 前/commit 前检查 cancel_checker +
   per-filing timeout 兜底；CancelledError 向上传播触发 rollback。
3. **CN Docling 转换段为无界 CPU 工作**（`asyncio.to_thread` 不可中途取消），但被
   `cn_download_filing_workflow.py:382,413` cancel 检查包围；转换期间 token 持有时长
   只受转换完成时间约束——并入长持 residual，由 per-filing timeout/metrics 观测。
4. **AUTO_ATOMIC_ALLOWED 方法自身原子性前提**：company upsert 等 metadata-only 方法
   无远端 publish/delete 风险；destructive 方法（reset/clear/delete/stale cleanup）依赖
   S14-CTRL-13 在 batch impl 内原子 journal 全部 delete targets + swap——实现时若发现
   任一标 AUTO 的方法存在跨 repository 不变量，必须改判 EXPLICIT_REQUIRED（completeness
   gate STOP 项）。


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
