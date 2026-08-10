# Slice 1.4 CN preparation-gate plan fix（DeepSeek worker）

- **Worker**：DeepSeek Flash fix worker
- **日期**：2026-08-10
- **基线**：`5d7e6bb`（branch `codex/investment-platform`，HEAD/worktree 冻结为只读审计）
- **状态**：**SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **任务范围**：只修 master plan Slice 1.4
  （`docs/plans/2026-08-10-investment-platform-restoration.md`）、九份既有 fix artifacts
  （`plan-fix-20260810-slice-1.4-s3-blob-repository-codex.md`、
  `plan-fix-20260810-slice-1.4-s3-blob-repository-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-closure-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-closure-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-terminal-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-terminal-final-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-to-thread-boundary-deepseek.md`、
  `plan-fix-20260810-slice-1.4-temp-ownership-deepseek.md`）与 temp/to-thread
  artifacts；新增本 artifact；
  production/tests/README/dependencies 全部冻结；未安装依赖、未 pull 镜像、未运行
  live/network/model/broker、未 commit/push/PR。
- **Temp-ownership final independent source reviews（只读）**：
  `docs/reviews/plan-temp-ownership-final-rereview-20260810-slice-1.4-terra.md`
  （Terra，FAIL，S14-TEMP-OWNERSHIP-FINAL-01，1M）、
  `docs/reviews/plan-temp-ownership-final-rereview-20260810-slice-1.4-mimo-native.md`
  （MiM Native，PASS，open 0/0/0）。

## Controller 裁决（preparation-gate，唯一实现，不留二选一）

- Terra temp-ownership-final re-review **FAIL / open 1M**：S14-TEMP-OWNERSHIP-FINAL-01
  （阶段 B gate 在临时 PDF 已创建后才取得 permit，并发 pipeline 下文件数量可在等待
  gate 时无界排队，无法证明每进程上限 = 配置容量，Medium）**ACCEPT**。
- MiM Native temp-ownership-final re-review **PASS / open 0/0/0**：记录为证据
  （temp-ownership F1-F5 与三段边界、prior closures 均已闭合），但该 review 未覆盖
  Terra 指出的 gate 取得时点与 temp PDF 创建时点之间的竞态，不能替代本 finding 的
  修复；**不得提前 ACCEPTED**。
- **Controller 架构修正（本 round 核心）**：把容量 reservation 前移到**任何 provider
  能创建 temp PDF 之前**——新增**共享 `CnPreparationGate`**（runtime owner 唯一实例、
  容量有限正数默认 1），每个 CN/HK filing 在提交阶段 A provider worker 之前先
  `acquire` slot；同一 slot 跨阶段 A provider future 与阶段 B read+Docling 实际 inner
  futures，最后 inner 真正完成才 release。等待 slot 的 filing 不得启动 provider、
  不得创建临时 PDF——彻底消除"已创建、等待 permit 的 `delete=False` 文件无界排队"。
- implementation 继续冻结：只改 master plan 与 fix artifacts，不触碰
  source/code/tests/README/deps；如需改 Host/public domain protocol/第二 transaction
  API 则 STOP。

## 只读 callgraph 审计（preparation-gate round，支撑唯一化）

本 round 按 Terra S14-TEMP-OWNERSHIP-FINAL-01 的 direct evidence 只读核验（未修改
任何 production 文件）：

- **竞态事实（Terra 反例成立）**：`run_cn_download_single_filing_stream` 的真实调用
  顺序是 `await asyncio.to_thread(_download_report_pdf_with_gate)` 返回
  `DownloadedReportAsset.pdf_path` 后，才 `await asyncio.to_thread(pdf_path.read_bytes)`
  （`cn_download_filing_workflow.py:191-221`）；两种 provider 都在阶段 A 内以
  `NamedTemporaryFile(delete=False)` 写出 PDF（`cninfo_downloader.py:394-404`、
  `hkexnews_downloader.py:410-420`）。若阶段 B gate 只在 read/Docling 前获取 permit，
  已创建的 PDF 在等待 permit 时不持 permit、不触发 worker finally——并发 pipeline 下
  文件数可增长到 `N+K` 而非 `N`。
- **单 ticker 串行性不足**：`run_cn_download_stream_impl` 只在单一 ticker 的
  candidate loop 内串行（`cn_download_workflow.py:239-289`），但 `CnPipeline` 可由
  factory 为不同工作流构造，计划未给跨 ticker/pipeline 全局并发上限——因此不能用单
  ticker 串行性证明每进程临时文件数有界。
- **不回归复核**：SEC streaming 例外（await-based、无阶段 B）、`replace_source_meta`、
  per-filing terminal rollback/commit fence、S3 `delete_entry` stage-delete、upload
  overwrite、三段边界（阶段 A 唯一 hard-bounded、阶段 B 不承诺有限结束、阶段 C 无
  独立 timeout + cancel fences）、`_read_and_unlink_temp_pdf` worker finally、startup
  stale-temp sweep 的既有契约本轮不触碰。

## 唯一化契约（master plan S14-CTRL-12 修订）

### A. 共享 `CnPreparationGate`（闭合 Terra S14-TEMP-OWNERSHIP-FINAL-01）

1. **私有 `CnPreparationGate`**（模块级私有 typed/frozen dataclass，容量有限正数默认
   `1`）是 **`DefaultFinsRuntime`/`PreparedHostRuntimeDependencies` owner 的共享实例**：
   生产 startup 唯一 runtime 构造并持有唯一 `_preparation_gate`；
2. **传播链（与 `batching_repository` 同链，精确扩展既有 runtime → ingestion factory
   → `CnPipeline` 唯一链，不改 public domain protocol/Host imports）**：
   `DefaultFinsRuntime._build_pipeline_for_ticker`/`build_ingestion_service_factory`
   （... `preparation_gate=self._preparation_gate`）-> `_build_pipeline`/
   `dayu.fins.ingestion.factory.build_ingestion_service_factory`
   -> `build_ingestion_service_from_normalized_ticker`
   -> `get_pipeline_from_normalized_ticker`
   -> `CnPipeline.__init__(... preparation_gate)`（实例持有）
   -> host protocols（`CnDownloadWorkflowHost` 新增 `preparation_gate` property）
   -> `run_cn_download_stream_impl`/`run_cn_download_single_filing_stream`
   （keyword-only `preparation_gate`，per-filing 阶段 A 前 `acquire` slot）；
   所有经 runtime direct + ingestion factory 创建的 `CnPipeline` 显式传播**同一实例**，
   **不得 per-pipeline 另建、global cache、wrapper**；`FinsRuntimeProtocol`/Host/Agent/
   tool contract 不见 gate；
3. **allowlist/test**：`service_runtime.py`/`ingestion/factory.py`/`pipelines/factory.py`/
   `cn_pipeline.py`/`cn_download_protocols.py`/`cn_download_workflow.py`/
   `cn_download_filing_workflow.py` 已在 allowlist（同链显式传递 `preparation_gate`）；
   `test_runtime_batch_injection.py` 扩展断言同 runtime 多 `CnPipeline` 收到同一
   `preparation_gate` 实例。

### B. slot 先于 provider 获取（消除 temp 排队竞态）

1. **每个 CN/HK filing 在提交阶段 A provider worker 之前先 `acquire` slot**；等待 slot
   的 filing **不得启动 provider、不得创建临时 PDF**；
2. **同一 slot 跨阶段 A provider future 与阶段 B read+Docling 的实际 inner futures**，
   直至**最后一个 inner 真正完成才 release**；
3. `provider_download_timeout_seconds` **只从真正进入阶段 A 后开始计时**（等待 slot
   不计时、不产生 token/临时文件/provider 调用）。

### C. 阶段 A 语义（provider inner future 与 late completion）

1. **阶段 A timeout/outer cancel 不能取消 provider inner future（`asyncio.shield`）**；
2. **late provider completion** 若返回 `DownloadedReportAsset`，其 **completion
   callback 只做 exact temp unlink + metrics 后 release slot**，**禁止进入
   read/Docling/repo**；
3. **provider exception 后 release slot**；正常 provider 成功**继续持有 slot**。

### D. 阶段 B/C 时序

1. 阶段 B（slot 已持有）：`_read_and_unlink_temp_pdf` 的 worker finally 删 path，再
   Docling，**Docling 实际 future 完成后 release slot**；**outer cancel 不提前
   release**（permit 绑定实际 inner future，shield/完成回调保证由 inner 真正完成时
   release，禁止"取消即提前释放"导致无限后台 worker）；worker 零 repo/batch/token；
2. **slot/gate 绝不持有 repo/batch/token**；
3. **阶段 C**：**slot 正常完成/release 后** + cancellation fence（cancel_checker）
   通过，才 begin 同-core explicit repository batch（blob/meta 写在短事务窗口内，
   precommit fence、commit-start 前后语义保持）。

### E. 容量与进程上限

1. **files/workers bound = 每唯一 production runtime `<=` 容量**（生产 startup 唯一
   runtime closure 保证进程实际上限）；
2. **测试若构造多个 runtime 必须各自隔离（per-runtime gate），不得宣称全 OS 进程
   单例**；不同 runtime 仅作为 test isolation residual。

### F. startup stale-temp sweep 前置条件收紧

1. **只在共享 `CnPreparationGate` 尚未 admit 任何 work（无 active slot）时**，持
   exclusive cleanup lock 运行一次有界清理（只限
   `{tempdir}/dayu_cn_downloads/cninfo_*.pdf` 与 `dayu_hk_downloads/hkexnews_*.pdf`
   regular 非 symlink 且 mtime 早于模块级有限 stale 阈值；unknown/symlink/lock busy
   fail-safe 不删并记 metrics；禁止广泛 temp sweep）。

### G. 测试新增（`test_runtime_batch_injection.py` 扩展 + `test_cn_temp_pdf_ownership.py`）

1. **同一 runtime 多 `CnPipeline` 并发（容量 1）**：第二条在 provider 之前等待 slot
   （不创建临时 PDF）、temp 文件数 `<= 1`；
2. **cancel 阶段 A**：late `DownloadedReportAsset` 被 completion callback 删除且 slot
   最终 release；
3. **cancel 阶段 B**：仍按前轮语义（worker finally 删 path、outer cancel 不提前
   release、后台 work 仅观测不声称终止）；
4. **不同 runtime**：各自隔离（per-runtime gate），仅 test isolation residual；
5. **startup stale-temp sweep**：只在共享 gate 未 admit 任何 work 时运行，只删 owned
   stale、不删 fresh/unknown/symlink；全程无 token、零 publish。

## 逐 ID 处置汇总

| Finding | 严重程度 | 处置 | 闭合位置 |
| --- | --- | --- | --- |
| Terra S14-TEMP-OWNERSHIP-FINAL-01（阶段 B gate 在临时 PDF 已创建后才取得 permit，并发 pipeline 下文件数量无界排队，每进程上限 = 配置容量不成立） | Medium | **ACCEPTED / FIXED-IN-PLAN** | S14-CTRL-12（A-G：共享 `CnPreparationGate`（runtime owner 唯一实例、与 `batching_repository` 同链传播到所有 `CnPipeline`、不得 per-pipeline 另建、Host/Agent/tool contract 不见 gate）；slot 先于阶段 A provider 获取（等待 slot 不启动 provider、不创建临时 PDF、`provider_download_timeout_seconds` 只从真正进入阶段 A 后计时）；同一 slot 跨阶段 A provider future 与阶段 B read+Docling 实际 inner futures、最后 inner 真正完成才 release；阶段 A timeout/outer cancel 用 shield 不取消 provider inner future、late `DownloadedReportAsset` 由 completion callback 只做 exact temp unlink + metrics 后 release slot、provider exception 后 release、正常成功继续持 slot；阶段 B `_read_and_unlink_temp_pdf` finally 删 path、Docling 实际 future 完成后 release、outer cancel 不提前 release；slot/gate 零 repo/batch/token；阶段 C 在 slot 正常完成/release 后 + cancel fence 才 begin batch；files/workers bound = 每唯一 production runtime `<=` 容量（测试多 runtime 各自隔离、不宣称全 OS 进程单例、不同 runtime 仅 test isolation residual）；startup stale-temp sweep 只在共享 gate 未 admit 任何 work 时持 exclusive cleanup lock 运行；传播链 allowlist/test 精确扩展（`test_runtime_batch_injection.py` 同 runtime 多 `CnPipeline` 并发断言）） |
| MiM Native temp-ownership-final PASS/open0 | — | **记录为证据，不 ACCEPTED** | temp-ownership F1-F5 与三段边界、prior closures 已闭合；本 round 不引入新 finding 于 MiM 侧 |

逐 ID 均无 **RE-REVIEW-REQUIRED**。既有 closure（S14-CORRECTIVE-01/02、
S14-CLOSURE-01/02、S14-REREVIEW-02/03、S14-TERMINAL-01/02、S14-TERMINAL-FINAL-01、
S14-TO-THREAD-FINAL-01/02、MiM delete_entry/upload overwrite/CN timeout、exact
toolset names、`replace_source_meta`、per-filing terminal、S3 stage-delete、upload
overwrite）全部保持 **closed 无回归**（本 round 未触碰其契约）。原 round 1..9 裁决
全部保持历史不变。

## 校验

- `git diff --check` 通过；修改的十一份文档（master plan、九份既有 fix artifacts、本
  artifact）trailing whitespace 为零、final LF 齐全。
- 未修改 production/tests/README/dependencies；十八份 source review 保持只读
  （204331/204201/211302/211155/213617/213634/final-closure-terra/
  final-closure-mimo-native/final-corrective-terra/final-corrective-mimo-native/
  terminal-terra/terminal-mimo-native/terminal-final-terra/terminal-final-mimo-native/
  to-thread-final-terra/to-thread-final-mimo-native/temp-ownership-final-terra/
  temp-ownership-final-mimo-native）。
- master plan 状态：**SLICE 1.4 REVIEW OBSERVATION FIXED / AWAITING FINAL DUAL PLAN
  RE-REVIEW**。
- finding completeness：Terra S14-TEMP-OWNERSHIP-FINAL-01 按 **ACCEPTED /
  FIXED-IN-PLAN** 记录（Controller ACCEPT、plan FIXED，未提前 ACCEPTED）；MiM Native
  PASS/open0 记录为历史证据。

## 新增 gap / residual（如实记录，非假设）

1. **阶段 B worker 永不结束 / 排队等待 slot**：temp 文件与 slot 上限 = 每唯一
   production runtime `<=` 配置容量（建议 1）；由 startup stale-temp sweep 收敛
   （仅删 owned stale、gate 未 admit 任何 work 时）；"worker 最终结束"不作为 bounded
   contract。
2. **等待 slot 的 filing 不启动 provider、不创建临时 PDF**——容量 reservation 先于
   temp 创建，文件数上限 = 容量（每唯一 runtime）而非并发 filing 数。
3. **late provider completion 的 slot 回收**：只在 completion callback 完成 exact
   temp unlink + metrics 后 release；禁止进入 read/Docling/repo。
4. **不同 runtime 的 gate 隔离**：测试构造多个 runtime 时各自持有独立
   `CnPreparationGate`，不宣称全 OS 进程单例；生产 startup 唯一 runtime closure 保证
   进程实际上限。
5. **commit-start 后的同步窗口**：`commit_batch` 为同步过程，一旦开始
   `asyncio.timeout` 无法注入取消——按 S14-CTRL-04 journal/recovery 收敛，
   `cleanup_pending` 由 startup 重试，这是已知语义而非缺陷。

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
