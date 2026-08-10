# Slice 1.4 CN temp PDF ownership plan fix（DeepSeek worker）

- **Worker**：DeepSeek Flash fix worker
- **日期**：2026-08-10
- **基线**：`5d7e6bb`（branch `codex/investment-platform`，HEAD/worktree 冻结为只读审计）
- **状态**：**SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **任务范围**：只修 master plan Slice 1.4
  （`docs/plans/2026-08-10-investment-platform-restoration.md`）、八份既有 fix artifacts
  （`plan-fix-20260810-slice-1.4-s3-blob-repository-codex.md`、
  `plan-fix-20260810-slice-1.4-s3-blob-repository-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-closure-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-closure-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-terminal-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-terminal-final-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-to-thread-boundary-deepseek.md`）与
  本轮 to-thread artifact；新增本 artifact；
  production/tests/README/dependencies 全部冻结；未安装依赖、未 pull 镜像、未运行
  live/network/model/broker、未 commit/push/PR。
- **To-thread final independent source reviews（只读）**：
  `docs/reviews/plan-to-thread-final-rereview-20260810-slice-1.4-terra.md`
  （Terra，FAIL，S14-TO-THREAD-FINAL-01/02，2M）、
  `docs/reviews/plan-to-thread-final-rereview-20260810-slice-1.4-mimo-native.md`
  （MiM Native，PASS，open 0/0/0）。

## Controller 裁决（temp-ownership，唯一实现，不留二选一）

- Terra to-thread-final re-review **FAIL / open 2M**：S14-TO-THREAD-FINAL-01（现行测试
  修改清单仍要求已废止的 CN 全窗口 token/timeout 语义，Medium）、
  S14-TO-THREAD-FINAL-02（阶段 B 取消后的临时 PDF 清理责任未定义，
  `NamedTemporaryFile(delete=False)` 文件可能无限累积，Medium）**两项均 ACCEPT**。
- MiM Native to-thread-final re-review **PASS / open 0/0/0**：记录为证据（三段边界、
  stage-C 一致性、prior closures 均已闭合），但该 review 未覆盖 Terra 指出的测试清单
  残留断言与 `delete=False` 临时 PDF 资源所有权，不能替代上述两项 Medium 的修复；
  **不得提前 ACCEPTED**。
- implementation 继续冻结：只改 master plan 与 fix artifacts，不触碰
  source/code/tests/README/deps；如需改 Host/public domain protocol/第二 transaction
  API 则 STOP。

## 只读 callgraph 审计（temp-ownership round，支撑唯一化）

本 round 按 Terra S14-TO-THREAD-FINAL-01/02 的 direct evidence 只读核验（未修改任何
production 文件）：

- **测试清单残留（F1 直接证据）**：master plan Allowed 测试修改项
  （`tests/fins/test_cn_download_workflow.py` 等）仍断言"SEC/CN 下载 per-filing 显式
  batch + per-filing timeout：list/download/Docling 期间恰有同一 active token"，与
  S14-CTRL-12 三段边界（CN 阶段 A/B 无 token、阶段 C 才 begin）直接矛盾。
- **临时 PDF 事实（F2 直接证据）**：
  - CN/HK downloader 用 `tempfile.NamedTemporaryFile(prefix="cninfo_"|"hkexnews_",
    suffix=".pdf", dir={tempdir}/dayu_cn_downloads|dayu_hk_downloads, delete=False)`
    创建 PDF（`cninfo_downloader.py:394-404`、`hkexnews_downloader.py:410-420`）；
  - `DownloadedReportAsset.pdf_path`（`cn_download_models.py:161-177`）在
    `cn_download_filing_workflow.py:220-241` 读取：`_unlink_temp_pdf` 只在普通
    `Exception` 分支（:223）与成功 `else` 分支（:241）调用，**无覆盖 await 取消路径的
    finally**；外层任务在 await `asyncio.to_thread(pdf_path.read_bytes)`（:221）时被
    取消会绕开这些分支；
  - 阶段 B 明确不承诺 worker 结束——若 worker 内无 finally/等价完成回调清理，
    重复取消/永久卡住的 worker 可遗留临时 PDF 消耗磁盘；plan 的"零 token/零 publish"
    与 warning/metrics 不建立清理所有权。
- **不回归复核**：SEC streaming 例外、`replace_source_meta`、per-filing terminal
  rollback/commit fence、S3 `delete_entry` stage-delete、upload overwrite 的契约本轮
  不触碰。

## 唯一化契约（master plan S14-CTRL-12 修订）

### F1. 修正 active Allowed/test 清单的旧 CN token/timeout 断言（闭合 Terra S14-TO-THREAD-FINAL-01）

1. `tests/fins/test_cn_download_workflow.py` 等测试修改项（master plan Allowed）不再
   断言"SEC/CN list/download/Docling 期间恰有同一 active token + per-filing timeout"；
2. 改为三段断言（唯一）：
   - **SEC streaming 例外仍同 token**：SEC list/download 流
     （`sec_download_filing_workflow.py:243-253,404-432`）期间恰有同一 active token、
     per-filing batch 在调用 `run_download_single_filing_stream` 之前 begin、网络与同
     token 写窗口由 `provider_download_timeout_seconds` 覆盖、每 filing 一个 token、
     绝不第二 batch/auto-begin、token 不跨整个 ticker；**不把该例外泛化给 CN**；
   - **CN 阶段 A/B 无 token、阶段 C 才单 token**（阶段 C 内每 filing 恰好一个）；
   - **阶段 A `provider_download_timeout_seconds` 超时/失败 => 零 begin（无 token、
     零 publish）**；
   - **阶段 B 取消仅观测后台 work**（零 token、零 publish、不声称终止）；
   - **阶段 C 已 begin 后的 repository transaction failure/cancel 按 commit-start
     前后收敛**（commit-start 前 rollback、commit-start 后 journal/recovery）。

### F2. 唯一化临时 PDF owner 与容量（闭合 Terra S14-TO-THREAD-FINAL-02，code-generation-ready 不实现）

1. **临时 PDF 唯一清理 owner（`cn_download_filing_workflow`）**：私有函数
   `_read_and_unlink_temp_pdf(path: Path, *, module: str) -> bytes`：
   - worker 读取 bytes，并在**自身 `finally` 幂等 `unlink`**（`missing_ok=True`）删除
     `DownloadedReportAsset.pdf_path`（`{tempdir}/dayu_cn_downloads/cninfo_*.pdf`、
     `dayu_hk_downloads/hkexnews_*.pdf`）；
   - **outer cancel 也 best-effort unlink**：POSIX 可删除仍被读取的目录项；Windows
     删除失败由 worker 自身 finally 重试兜底；
   - **Docling converter 只接收已读 bytes（`pdf_bytes`），不再持有 pdf path**；
   - 清理逻辑只接收 path/日志输入，不接触仓储/batch/token。
2. **阶段 B bounded gate（私有 pipeline-owned）**：阶段 B 所有
   `run_in_executor`/`asyncio.to_thread` 一律经**模块私有 bounded gate**（模块级私有
   有限正数默认容量，建议 `1`）执行；**permit 必须绑定实际 inner future 而非 outer
   await**：用 `asyncio.shield`/完成回调保证 outer 取消后仍由 **inner 真正完成时
   release permit**；**禁止"取消即提前释放"导致无限后台 worker**；worker 零
   repo/batch/token。
3. **容量 residual（明确、有界）**：worker 永不结束时 temp 文件与 permit 一并保留，
   **上限 = 配置容量（每进程）**，不泄漏第二 writer、不无限增长。
4. **bounded startup stale-temp sweep owner**：在任何 CN/HK provider work 前、且无
   active stage-B worker 时，由**单一 runtime/process 私有 helper**（模块私有函数，
   在 `CnPipeline` 构造时单次调用；持 exact temp-dir cleanup lock，如
   `{tempdir}/dayu_cn_downloads/.cleanup.lock` 非阻塞 flock）执行一次有界清理：
   - 只限 `tempfile.gettempdir()/dayu_cn_downloads/cninfo_*.pdf` 与
     `dayu_hk_downloads/hkexnews_*.pdf`；
   - 只删 **regular 非 symlink** 且 **mtime 早于模块级有限 stale 阈值**（私有有限
     正数默认）的文件；
   - unknown/symlink/lock busy **fail-safe 不删**并记 metrics；
   - **禁止广泛 temp sweep**；sweep 不触碰 repository/batch/token。
5. **测试（`tests/fins/test_cn_temp_pdf_ownership.py`，加入 allowlist）**：
   - worker 正常完成 => `finally` 幂等 unlink 临时 PDF；
   - outer 取消 + worker 稍后完成 => 最终仍删除（POSIX outer best-effort unlink /
     Windows worker finally 重试）；
   - worker 永不结束 => temp/permit 数量上限 = 配置容量/进程（建议 1），不无限增长；
   - 重启 startup stale-temp sweep 只删 owned 且 stale 的 regular 非 symlink，不删
     fresh/unknown/symlink，unknown/symlink/lock busy fail-safe 不删并记 metrics；
   - 全程无 token、零 publish。

## 逐 ID 处置汇总

| Finding | 严重程度 | 处置 | 闭合位置 |
| --- | --- | --- | --- |
| Terra S14-TO-THREAD-FINAL-01（现行测试修改清单仍要求已废止的 CN 全窗口 token/timeout 语义） | Medium | **ACCEPTED / FIXED-IN-PLAN** | S14-CTRL-12 Allowed/test 清单（F1：SEC streaming 例外仍同 token；CN 阶段 A/B 无 token、阶段 C 才单 token；阶段 A timeout 零 begin/零 publish；阶段 B 取消仅观测；阶段 C failure/cancel 按 commit-start 前后收敛；不把 SEC 例外泛化给 CN） |
| Terra S14-TO-THREAD-FINAL-02（阶段 B 取消后的临时 PDF 清理责任未定义，`NamedTemporaryFile(delete=False)` 文件可能无限累积） | Medium | **ACCEPTED / FIXED-IN-PLAN** | S14-CTRL-12（F2：`_read_and_unlink_temp_pdf` worker finally 幂等 unlink + outer cancel best-effort unlink + Docling 只收已读 bytes；阶段 B 模块私有 bounded gate（permit 绑定 inner future、outer 取消不提前释放、容量建议 1）；worker 永不结束时 temp/permit 上限 = 配置容量/进程；bounded startup stale-temp sweep owner（CN pipeline 构造时单次、exact temp-dir lock、只删 owned regular 非 symlink 且 mtime 早于模块级有限 stale 阈值、unknown/symlink/lock busy fail-safe 不删并记 metrics、禁止广泛 temp sweep）；`tests/fins/test_cn_temp_pdf_ownership.py` 加入 allowlist） |
| MiM Native to-thread-final PASS/open0 | — | **记录为证据，不 ACCEPTED** | 三段边界与 prior closures 已闭合；本 round 不引入新 finding 于 MiM 侧 |

逐 ID 均无 **RE-REVIEW-REQUIRED**。既有 closure（S14-CORRECTIVE-01/02、
S14-CLOSURE-01/02、S14-REREVIEW-02/03、S14-TERMINAL-01/02、S14-TERMINAL-FINAL-01、
MiM delete_entry/upload overwrite/CN timeout、exact toolset names、
`replace_source_meta`、per-filing terminal、S3 stage-delete、upload overwrite）全部
保持 **closed 无回归**（本 round 未触碰其契约）。原 round 1..8 裁决全部保持历史
不变。

## 校验

- `git diff --check` 通过；修改的十份文档（master plan、八份既有 fix artifacts、本
  artifact）trailing whitespace 为零、final LF 齐全。
- 未修改 production/tests/README/dependencies；十六份 source review 保持只读
  （204331/204201/211302/211155/213617/213634/final-closure-terra/
  final-closure-mimo-native/final-corrective-terra/final-corrective-mimo-native/
  terminal-terra/terminal-mimo-native/terminal-final-terra/terminal-final-mimo-native/
  to-thread-final-terra/to-thread-final-mimo-native）。
- master plan 状态：**SLICE 1.4 REVIEW OBSERVATIONS FIXED / AWAITING FINAL DUAL PLAN
  RE-REVIEW**。
- finding completeness：Terra S14-TO-THREAD-FINAL-01/02 逐项按 **ACCEPTED /
  FIXED-IN-PLAN** 记录（Controller ACCEPT、plan FIXED，未提前 ACCEPTED）；MiM Native
  PASS/open0 记录为历史证据。

## 新增 gap / residual（如实记录，非假设）

1. **阶段 B worker 永不结束**：temp 文件与 permit 保留，**上限 = 配置容量/进程**
   （建议 1）；由 bounded startup stale-temp sweep 收敛（只删 owned 且 mtime 早于模块
   级有限 stale 阈值的 regular 非 symlink），"worker 最终结束"不作为 bounded contract。
2. **outer cancel 只负责 best-effort unlink 与 token 生命周期**：不回收已运行的
   Python thread；late result 与残留临时文件由 worker 自身 finally / startup sweep
   收敛；Windows 下 outer unlink 失败由 worker finally 重试兜底。
3. **startup sweep 的精确 owner 与 lock**：只在 `CnPipeline` 构造（startup）且无
   active stage-B worker 时执行一次；lock busy / unknown / symlink fail-safe 不删并
   记 metrics；禁止广泛 temp sweep——避免与正在读取的 worker 竞争。
4. **commit-start 后的同步窗口**：`commit_batch` 为同步过程，一旦开始
   `asyncio.timeout` 无法注入取消——按 S14-CTRL-04 journal/recovery 收敛，
   `cleanup_pending` 由 startup 重试，这是已知语义而非缺陷。


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
