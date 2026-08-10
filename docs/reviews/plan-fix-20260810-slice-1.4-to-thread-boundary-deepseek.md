# Slice 1.4 CN to-thread boundary plan fix（DeepSeek worker）

- **Worker**：DeepSeek Flash fix worker
- **日期**：2026-08-10
- **基线**：`5d7e6bb`（branch `codex/investment-platform`，HEAD/worktree 冻结为只读审计）
- **状态**：**SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **任务范围**：只修 master plan Slice 1.4
  （`docs/plans/2026-08-10-investment-platform-restoration.md`）与七份既有 fix artifacts
  （`plan-fix-20260810-slice-1.4-s3-blob-repository-codex.md`、
  `plan-fix-20260810-slice-1.4-s3-blob-repository-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-closure-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-closure-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-terminal-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-terminal-final-corrective-deepseek.md`）；新增本
  artifact；production/tests/README/dependencies 全部冻结；未安装依赖、未 pull 镜像、
  未运行 live/network/model/broker、未 commit/push/PR。
- **Terminal final independent source reviews（只读）**：
  `docs/reviews/plan-terminal-final-rereview-20260810-slice-1.4-terra.md`
  （Terra，FAIL，S14-TERMINAL-FINAL-01，1M）、
  `docs/reviews/plan-terminal-final-rereview-20260810-slice-1.4-mimo-native.md`
  （MiM Native，PASS，open 0/0/0）。

## Controller 裁决（to-thread boundary，唯一实现，不留二选一）

- Terra terminal-final re-review **FAIL / open 1M**：S14-TERMINAL-FINAL-01（CN
  `to_thread` 的"底层有限 timeout"前提与真实默认 Docling/本地读路径矛盾，Medium）
  **ACCEPT**。
- MiM Native terminal-final re-review **PASS / open 0/0/0**：记录为证据（五项 terminal
  findings 均已由 round 7 闭合），但该 review 未覆盖 Terra 指出的默认 Docling/
  `pdf_path.read_bytes` 无有限 timeout 与 round 7 STOP/测试承诺的自相矛盾，不能替代
  本 finding 的修复；**不得提前 ACCEPTED**。
- **Controller 架构修正（本 round 核心）**：采用 Terra 建议改法 **option 2（诚实三段
  边界，不扩 subprocess framework）**——不把 CN 默认 Docling/本地读迁到可监督可终止
  的执行单元；把硬有界承诺唯一限定到可证明有限的 provider download/request（阶段 A），
  把 `pdf_path.read_bytes` 与默认 Docling converter 放到明确独立、不可中断且不持有
  batch 的阶段（阶段 B），repository batch 只在 preparation 成功并经过 cancellation
  fence 后 begin（阶段 C）。删除 round 7 的冲突承诺，不伪装可中断。
- implementation 继续冻结：只改 master plan 与 fix artifacts，不触碰
  source/code/tests/README/deps；如需改 Host/public domain protocol/第二 transaction
  API/引入 subprocess 框架则 STOP。

## 只读 callgraph 审计（to-thread boundary round，支撑唯一化）

本 round 按 Terra S14-TERMINAL-FINAL-01 的 direct evidence 只读核验（未修改任何
production 文件）：

- **CN `to_thread` 三条路径（`cn_download_filing_workflow.py`）**：
  - 阶段 A 候选：provider PDF download
    `asyncio.to_thread(_download_report_pdf_with_gate, ...)`（:193-199）——底层
    downloader 有既有有限 per-request timeout（`cninfo_downloader.py:212`/
    `hkexnews_downloader.py:247` `request_timeout_seconds`），worker 可自行结束；
  - 阶段 B 候选 1：`asyncio.to_thread(pdf_path.read_bytes)`（:220-221）——本地读，
    **无任何底层 timeout**；
  - 阶段 B 候选 2：`asyncio.to_thread(convert_pdf_to_docling_json, pdf_bytes,
    pdf_filename)`（:391-395）——默认 converter 为
    `convert_pdf_bytes_to_docling_json_bytes`（`cn_pipeline.py:174-175`），实现在
    `docling_export.py:76-101`：签名 `(raw_data, stream_name) -> bytes`，**无
    timeout/deadline/cancel 参数**；上游 `convert_pdf_bytes_to_docling_payload`
    （`docling_export.py:60-73`）直接调 Docling runtime（do_ocr/table_structure/
    cell_matching），**无有限运行时上界**。
- **结论（Terra 反例成立）**：round 7 计划把 `asyncio.timeout` 覆盖"完整 per-filing
  窗口（含 Docling）"、又要求"任一被覆盖 to_thread 无有限 timeout 即 STOP"，同时把
  Docling 标为无界 residual——三者针对同一 `to_thread` 调用不能同时成立；测试的
  "fake worker 在自身有限 provider/request timeout 后结束"与"timeout 后下一 filing
  必可启动"也无法为真实默认 Docling/本地读路径实证。
- **不回归复核**：SEC 无等价 preparation 阶段（其下载为 await-based 流式
  `store_file`，per-filing batch 在调用 `run_download_single_filing_stream` 前 begin
  的 streaming 例外成立）；`replace_source_meta`、per-filing terminal 状态机、
  `delete_entry` stage-delete、upload overwrite 的契约本轮不触碰。

## 唯一化契约（master plan S14-CTRL-12 网络边界契约修订，reviewer option 2 三段边界）

### A. 阶段 A（provider download/request）——唯一 hard bounded

1. `run_download_stream_impl`/`run_cn_download_stream_impl` 新增 keyword-only
   `provider_download_timeout_seconds: float`（模块级私有有限正数默认常量；非法值
   fail-fast）——**替代 round 7 的 `per_filing_timeout_seconds`**。
2. `asyncio.timeout(provider_download_timeout_seconds)` **只包裹阶段 A 的 await 窗口**
   （SEC 异步 listing/download；CN provider download 的 await）；每个独立请求继续由
   既有 per-request timeout 有界。**仅阶段 A 可宣称 hard bounded**；超时取消 outer
   task（CN 阶段 A 的 to_thread worker 仍运行到其底层有限 per-request timeout 结束，
   outer 侧立即进入取消处理）。

### B. 阶段 B（preparation）——明确不纳入 hard timeout、不承诺可中断/最终有限结束

1. 覆盖 `pdf_path.read_bytes`（`cn_download_filing_workflow.py:220-221`）与默认/注入
   Docling converter（:391-395 → `docling_export.py:76-101`，签名无
   timeout/deadline/cancel）。
2. worker 经 `asyncio.to_thread` 执行，**只接收 immutable/path input**（pdf
   bytes/path、stream_name），**绝不持有 repository/batch/token 句柄**。
3. **明确不纳入 hard timeout、不承诺 interruptible/最终有限结束、不用
   `asyncio.timeout` 伪装**；outer cancellation（取消/超时）丢弃 late result（worker
   结束后其结果零写入 repo/batch）但**不宣称回收 worker**；记录
   warning/metrics/residual；阶段 B 的并发只受执行单元容量限制，**不把"worker 最终
   结束"当作 bounded contract**。
4. **开始此阶段前若实现发现 worker 会持有/访问 repository/batch/token 句柄 =>
   STOP 并逐名报告**。

### C. 阶段 C（repository transaction）——短事务窗口

1. 阶段 A/B 成功并经过 **cancellation fence（仅 cancel_checker）** 后，**才**经注入的
   batching_repository begin 同-core explicit repository batch。
2. **所有 blob/meta writes（store_file、source meta 更新等）在短 repository
   transaction window 内**；**阶段 C 无独立 hard duration timeout、不含外部
   await/Docling/provider I/O**（`provider_download_timeout_seconds` 只约束阶段 A，
   不约束已开始的阶段 C）；**commit 前再查 cancel_checker（precommit fence）**；
   **staging/commit 失败或取消在 commit-start 前 => rollback，commit-start 后 =>
   只按 S14-CTRL-04 journal/recovery 收敛**。
3. **CN 阶段 A/B 期间无 active token**，token 只在阶段 C 存在、每 filing 恰好一个、
   绝不扩到整个 ticker 循环；SEC 无阶段 B（await-based streaming 例外，其网络与同
   token 写窗口由 `provider_download_timeout_seconds` 覆盖）。

### D. 删除/修正 round 7 冲突承诺

1. 删除"`asyncio.timeout` 包裹每个 per-filing 显式 batch 的完整窗口（begin → 远端
   list/download/Docling → blob+metadata 写 → commit）"——完整窗口含 Docling 的表述
   不再成立；
2. 删除"任一被 `per_filing_timeout` 覆盖的 to_thread 路径底层无任何有限 timeout =>
   STOP"——改为阶段 A 唯一 hard-bounded + 阶段 B 显式不承诺 + 阶段 B worker 持有
   repo/batch 即 STOP；
3. 修正"fake blocking worker 在自身有限 provider/request timeout 后结束"——只有阶段 A
   的 provider fake（底层有限 timeout）可证明终止；阶段 B 的 fake worker 仅观测不声称
   终止；
4. 修正"timeout 后下一 filing 必可启动"——**后续 filing 只在容量可用时可启动，不作
   无限 worker 条件承诺**。

### E. 测试修订（S14-CTRL-08，`tests/fins/test_cn_to_thread_boundary.py`）

1. **真实默认 Docling converter（`docling_export.py:76-101`）与
   `pdf_path.read_bytes`（`cn_download_filing_workflow.py:220-221`）位于阶段 B
   （begin_batch 前）**，worker 零 repo/batch/token 句柄、late result 零写入；
2. **provider fake（阶段 A）带有限 timeout 可证明终止**（唯一 hard-bounded 实证）；
3. **阶段 B 取消后无 token、零 publish，但后台 work 仅观测（warning/metrics）不声称
   终止、不宣称回收 worker**；
4. **后续 filing 只在容量可用时可启动**，不作无限 worker 条件承诺；
5. **repository transaction failure/cancellation/rollback/terminal-state 测试保留**：
   **阶段 A/B 失败/取消 => 零 begin（无 token、零 publish）；只有阶段 C 已 begin 后
   的失败/取消才 rollback（commit-start 前 rollback、commit-start 后 journal/recovery）；
   阶段 C 无独立 timeout（不新增 repository timeout 参数）**；per-filing terminal
   状态机、commit-start journal/recovery 语义不变。

## 逐 ID 处置汇总

| Finding | 严重程度 | 处置 | 闭合位置 |
| --- | --- | --- | --- |
| Terra S14-TERMINAL-FINAL-01（CN `to_thread` 的"底层有限 timeout"前提与真实默认 Docling/本地读路径矛盾；round 7 STOP/测试承诺自相矛盾） | Medium | **ACCEPTED / FIXED-IN-PLAN** | S14-CTRL-12 网络边界契约（A/B/C/D/E：reviewer option 2 诚实三段边界——阶段 A provider download/request 唯一 hard-bounded（`provider_download_timeout_seconds`）、阶段 B preparation（`pdf_path.read_bytes` + 默认 Docling converter）明确不纳入 hard timeout/不承诺可中断/有限结束/不用 `asyncio.timeout` 伪装且 worker 零 repo/batch/token 句柄、阶段 C 在 preparation 成功 + cancellation fence（仅 cancel_checker）后才 begin 同-core explicit batch、blob/meta 写在短事务窗口内且**阶段 C 无独立 timeout**、commit 前再查 cancel_checker、commit-start 前 rollback / commit-start 后 journal/recovery；删除"完整窗口含 Docling""任一无有限 timeout 即 STOP""fake worker 自身有限结束""timeout 后下一 filing 必可启动"冲突承诺；`test_cn_to_thread_boundary.py`） |
| MiM Native terminal-final PASS/open0 | — | **记录为证据，不 ACCEPTED** | round 7 五项 terminal findings 已闭合；本 round 不引入新 finding 于 MiM 侧 |

逐 ID 均无 **RE-REVIEW-REQUIRED**。Terra 上一轮 S14-TERMINAL-01/02 与 MiM
delete_entry/upload overwrite/CN timeout 保持 **closed 无回归**；
`replace_source_meta`、per-filing terminal rollback/commit fence、S3 stage-delete、
upload overwrite 及既有 closure（S14-CLOSURE-01/02、S14-REREVIEW-02/03、exact
toolset names）均保持 **closed 无回归**（本 round 未触碰其契约）。原 round 1..7 裁决
全部保持历史不变。

## 校验

- `git diff --check` 通过；修改的九份文档（master plan、七份既有 fix artifacts、本
  artifact）trailing whitespace 为零、final LF 齐全。
- 未修改 production/tests/README/dependencies；十四份 source review 保持只读
  （204331/204201/211302/211155/213617/213634/final-closure-terra/
  final-closure-mimo-native/final-corrective-terra/final-corrective-mimo-native/
  terminal-terra/terminal-mimo-native/terminal-final-terra/terminal-final-mimo-native）。
- master plan 状态：**SLICE 1.4 REVIEW OBSERVATION FIXED / AWAITING FINAL DUAL PLAN
  RE-REVIEW**。
- finding completeness：Terra S14-TERMINAL-FINAL-01 按 **ACCEPTED / FIXED-IN-PLAN**
  记录（Controller ACCEPT、plan FIXED，未提前 ACCEPTED）；MiM Native PASS/open0
  记录为历史证据。

## 新增 gap / residual（如实记录，非假设）

1. **CN 阶段 B（read_bytes + Docling 转换）为无界 CPU/IO 工作**：`asyncio.to_thread`
   不可中途取消、底层无有限 timeout，占用执行单元容量但不持有任何
   token/batch/repository；由外层 cancel_checker 边界
   （`cn_download_filing_workflow.py:382,413`）与 warning/metrics 观测；"worker 最终
   结束"不作为 bounded contract。
2. **后续 filing 启动受容量约束**：阶段 B 后台 work 存在期间，同 ticker 后续 filing
   只在容量可用时可启动；不承诺无限 worker 条件下必可启动。
3. **outer cancellation 只保护仓储一致性与 token 生命周期**：不回收已运行的 Python
   thread；late result 由"worker 不得访问 repo/batch"契约丢弃；worker 对第三方
   provider 的副作用不受本 slice 控制，由既有 per-request timeout 收敛。
4. **commit-start 后的同步窗口**：`commit_batch` 为同步过程，一旦开始
   `asyncio.timeout` 无法注入取消——按 S14-CTRL-04 journal/recovery 收敛，
   `cleanup_pending` 由 startup 重试，这是已知语义而非缺陷。


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
