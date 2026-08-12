# Slice 2.3 Stream Ownership / Domain Split — DeepSeek Flash Independent Corrective Plan Re-review Round 3（Focused L1 Closure + Regression Scan）

- 日期：2026-08-12 20:37 CST（本机系统时钟生成）
- Gate：Gateflow corrective plan round-3 fresh same-SHA 复审（implementation FROZEN）
- Reviewer：DeepSeek Flash（独立 reviewer；未读取任何 MiMo artifact，包括 round-2 MiMo review 与本轮历史）
- 角色边界：仅 reviewer，非 Controller/author/planner/implementer/fixer
- 分支：`codex/investment-platform`
- Baseline HEAD：`f0414facbef13081bb036e76d748e1f1cbf178b7`（评审前/后复核一致）
- Reviewed target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- **Reviewed target SHA-256：`ab14e3a97a069551211df303c902ee711d48f0d160ca9c53d54908c78d2c849f`（2884 行；评审前/后复核一致）**
- Corrective adjudication（fix）：`docs/reviews/plan-fix-20260812-slice-2.3-stream-ownership-domain-split-codex.md` SHA-256 `9d972471c35956add14930a7bb3311bf156dd7bcb0cee66e5be3a4c5694dd024`（335 行；评审前/后复核一致）
- Source review to re-review（round-2，只读）：`docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round2-deepseek-flash.md` SHA-256 `25bdcb28718a5840d3cac0a1dee41a282a5e5405bfeb7203da4d3be8211e6289`（结论 `CLARIFY / open H/M/L = 0/0/1`，唯一 open L1 为本轮核查对象）
- Preserved WIP：`dayu/investment/domain/source_sync.py` 1839 行、未跟踪（untracked）、immutable，SHA-256 `4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e`（评审前/后复核一致，字节未触碰）
- **结论：PASS**
- **Open findings：H/M/L = 0 / 0 / 0**

---

## 1. 评审范围与方法

本轮是 focused corrective re-review：核查 round-2 唯一 open finding **L1** 是否被 fix 的
`S23-CORR-CONTRACT-09` 与 round-3 target 完整闭合，并对 round-3 edit 做 regression scan。方法为真实代码
facts 逐项对账（只读）：

1. L1 七项闭合核验：persistence direct import 精确两 helper（zero-diff mapping owner）；exact keyword-only
   签名 = 10 business 字段 + `filing_maintenance_repository` + required `downloader`、五旧 dependency 参数
   absent；typed bind/try/async-for/finally/aclose once；wrapper 保留 business/repository 且 dependency 只传
   downloader；normal filing imports 保留；两项 named test 覆盖 success/mapping error/inner error/file_failed
   summary/asyncio cancel + AST exactness；STOP/allowlist 一致。
2. Regression scan：43 项 owner mapping、18 项 catalog、五个 PG gate、157 项 named tests、五 owner DAG /
   stream 链 / cancellation 语义、§16 residual。
3. 对账代码事实：`sec_download_persistence.py`（真实五 dependency 参数签名、legacy 死代码
   `_AwaitableResult`/`_maybe_await`/`inspect`/`AsyncIterator`/`Awaitable`/`TypeVar`）、
   `sec_download_event_mapping.py`（三 helper 真实存在、tracked、git 零 diff）、`sec_pipeline.py`（L674 normal
   filing 调用点与 L1226 rejected caller 调用点、`self._downloader` 存在）、`sec_downloader.py`（
   `download_files_stream` 真实签名与 `RemoteFileDescriptor`）、`conftest.py` 与 CI pinned digests、`git
   ls-files`/`git status` 分类。

评审期间未修改 plan/fix/WIP/source/tests，未 stage/commit/push/PR，未访问网络，未运行任何实现或测试，未写
除本 artifact 外任何文件。

## 2. Round-2 L1 最终状态与闭合证据

Round-2 L1（`CLARIFY 0/0/1`）：plan 只冻结删除 `download_files_stream`/`download_files`/
`normalize_download_file_result` 三个 dependency 参数，而 `build_file_result_from_downloader_event` 与
`summarize_failed_download_file_reasons` 两个必需 helper 的删除/保留/来源未裁决，且 mapping owner 不在
allowlist，两条闭合路径各自撞上硬约束。

最终状态：**L1 已修复并闭合（accepted，fix `S23-CORR-CONTRACT-09`）**。逐项证据如下。

### 2.1 闭合项 1：persistence 只 direct import 精确两 helper，mapping owner zero diff

- Target §4.4 item 7（L1311–1323）：``sec_download_persistence.py`` 在 module level 只从既有
  ``sec_download_event_mapping.py`` direct import ``build_file_result_from_downloader_event`` 与
  ``summarize_failed_download_file_reasons``；两 helper 名是 persistence module-owned import binding，不再由
  caller 注入；mapping owner 保持 zero diff，不进入 §11 writable production allowlist 或 §11.1 coverage
  matrix；只新增 direct import edge，禁止复制 helper、增加 adapter 或修改 mapping owner。冻结 import 块
  （L1318–1323）逐字为 ``from .sec_download_event_mapping import (build_file_result_from_downloader_event,
  summarize_failed_download_file_reasons)``。
- 代码事实：`sec_download_event_mapping.py` 真实存在三个 helper（`summarize_failed_download_file_reasons`
  L58、`normalize_download_file_result` L93、`build_file_result_from_downloader_event` L145），文件 tracked 于
  HEAD 且 `git diff --name-only HEAD -- <file>` 与 `git status --porcelain` 均为空（零 diff 实测）。
- §11（L2332–2334）双重复确认：mapping owner 不是 writable production path、不进 §11.1 matrix，只授权
  persistence 新增 direct import；import dependency ≠ edit scope 或 changed-production coverage key。

### 2.2 闭合项 2：exact keyword-only 签名 = 10 business + repository + required downloader，五旧参数 absent

- Target L1325–1347 冻结签名（`async def persist_rejected_filing_artifact(*, ticker, cik, filing,
  remote_files, overwrite, rejection_reason, rejection_category, selected_primary_document,
  source_fingerprint, classification_version, filing_maintenance_repository, downloader)`，全部 keyword-only、
  无 default）：10 个 business 字段 + `filing_maintenance_repository` + required private-protocol
  ``downloader``；L1345–1347 明确删除旧五个 dependency 参数 ``download_files_stream``、
  ``download_files``、``build_file_result_from_downloader_event``、``normalize_download_file_result``、
  ``summarize_failed_download_file_reasons``。
- 代码事实：真实签名（sec_download_persistence.py:179–197）恰好 = 上述 10 个 business 字段 +
  ``filing_maintenance_repository`` + 五个 dependency 参数，plan 冻结的字段名/顺序与真实代码逐字一致；
  冻结签名引用的类型全部真实存在（``RejectedArtifactFilingRecord``=该模块 L28 Protocol、
  ``RemoteFileDescriptor``=sec_downloader.py:90、``_RejectedArtifactDownloaderProtocol``=§4.4 item 7
  L1300–1309，其 ``download_files_stream`` 签名与真实 ``SecDownloader.download_files_stream``
  （sec_downloader.py:1164–1170）逐字段一致）。

### 2.3 闭合项 3：typed stream bind / try / async-for / finally / aclose once

- Target L1351–1355：唯一下载形态先绑定 ``inner = downloader.download_files_stream(remote_files=...,
  overwrite=..., store_file=..., existing_files={}, primary_document=filing.primary_document)``；``try`` 内唯一
  ``async for event in inner`` 逐项直接调用 module-bound ``build_file_result_from_downloader_event(event)``；
  ``finally`` 内 ``await inner.aclose()`` 恰好一次；``file_failed`` 分支直接调用 module-bound
  ``summarize_failed_download_file_reasons(failed_files)``（L1356–1357）。
- §13.2 AST 测试（L2599–2600）要求 AST 看到 typed inner bind、唯一 ``async for``、covering ``try/finally``
  与唯一 ``await inner.aclose()``，防止 double-close/跨层 close/直接写调用表达式。

### 2.4 闭合项 4：wrapper 保留 business/repository，dependency 只传 downloader

- Target L1357–1359：``SecPipeline._persist_rejected_filing_artifact`` 保留既有 business args，调用 persistence
  时传 business args、``filing_maintenance_repository`` 及唯一 dependency kwarg
  ``downloader=self._downloader``；五个旧 dependency kwargs、``getattr/callable/cast`` 与 fallback 全部删除。
- 代码事实：真实 caller（sec_pipeline.py:1226–1242）当前仍以 ``getattr(self._downloader,
  "download_files_stream", None)`` + ``cast`` + ``callable`` 构造 ``normalized_download_stream`` 并传五个
  dependency kwargs——正是 plan 删除的目标；``self._downloader`` 属性真实存在（L1213/L1233 已使用），
  ``downloader=self._downloader`` 可构造。

### 2.5 闭合项 5：normal filing path 的 mapping imports 保留

- Target L1360：不得删除 ``sec_pipeline.py`` 中 normal filing path 仍使用的 mapping helper imports/calls。
- 代码事实：normal filing 路径（sec_pipeline.py:674–690 `_download_single_filing_stream`）仍向
  ``run_download_single_filing_stream`` 传 ``build_file_result_from_downloader_event``、
  ``normalize_download_file_result``、``summarize_failed_download_file_reasons`` 三个 callback——该调用点
  与 rejected caller（L1226）不同，plan 冻结的删除范围只命中 rejected 调用点，normal 调用点与
  L84–87 的模块级 import 保留，AST 测试（L2601–2602）同时拒绝"误删 normal filing path 仍使用的 mapping
  imports"。

### 2.6 闭合项 6：测试覆盖五路行为 + AST exactness

- `test_rejected_artifact_persistence_closes_typed_downloader_stream_once_on_success_error_and_asyncio_cancel`
  （L2583，扩展要求 L2589–2594）：success、monkeypatch ``sec_download_persistence`` module binding 制造的
  mapping-helper error、inner stream error、mapped ``file_failed``、caller-task ``asyncio`` cancellation 五路，
  每路断言 direct inner ``aclose_calls == 1``；success 只 upsert 一次，mapping/inner/cancel 零
  filing-maintenance upsert，file-failed 返回 ``(False, <module-bound summary helper exact 结果>)`` 且零
  upsert；禁止 callback 注入，mapping error 必须 patch persistence module 的 direct-import binding。
- `test_download_stream_owner_path_contains_no_getattr_hasattr_cast_ignore_or_legacy_download_files_fallback`
  （L2584，扩展要求 L2595–2604）：AST/signature 核对 ``_RejectedArtifactDownloaderProtocol`` exact method；
  persistence keyword-only 参数集合只含十个 business 参数 + repository + required downloader，五旧参数
  absent；两 helper 是来自 mapping owner 的 exact module-level direct imports 且无 copied def/adapter；AST 见
  typed inner bind/唯一 async for/covering try/finally/唯一 aclose；caller dependency kwargs 只有
  ``downloader=self._downloader``；拒绝 ``getattr/hasattr/callable/cast/ignore``、legacy fallback、helper
  callback injection、误删 normal imports；断言不再定义 ``_AwaitableResult``/``_maybe_await`` 且不再保留无
  其它真实使用的 ``inspect``/``AsyncIterator``/``Awaitable``/``TypeVar`` imports。
- 代码事实支撑：persistence 当前确含 ``_AwaitableResult``（L62）、``_maybe_await``（L65，L242 legacy
  aggregate 分支使用）、``import inspect``（L5）、``AsyncIterator, Awaitable``（L6）、``TypeVar``（L8）——plan
  的删除目标与真实死代码一一对应，L1347–1349 同时冻结"若无其它引用则删除"的条件语义。

### 2.7 闭合项 7：STOP / allowlist 一致

- §15 STOP（L2856–2858）：rejected persistence 需要编辑 ``sec_download_event_mapping.py``、新增 adapter、
  复制 mapping/summary helper、保留任一 helper callback injection 或 legacy aggregate/fallback 而不能按 §4.4
  direct import owner 合同实现 → 立即 STOP 回 Controller。
- §11（L2332–2334）：mapping owner 明确不是 writable path、不进 §11.1 matrix；§11.1 43 key 中无
  ``sec_download_event_mapping.py``（实测确认），persistence owner tuple =
  (``test_sec_pipeline_rejection_registry.py``, ``test_sec_pipeline_download.py``)，全部来自 writable allowlist。
- 与 fix 的 STOP 条款（§5 "DeepSeek round-2 L1 audit"）逐项一致：direct import existing mapping owner、
  完整五旧参数删除、exact keyword-only signature、legacy dead import/helper cleanup、typed inner close、
  caller 与两项 named test/STOP 均冻结。

## 3. Regression scan（round-3 edit 未引入回归）

| 检查面 | 要求 | 实测证据 | 结果 |
|---|---|---|---|
| 43 owner mapping | key 与 production Python allowlist exact-equal、唯一、tuple 非空/唯一、member provenance | 43 key 唯一；43 纯路径（剥离括号注解）与 43 key 双向 exact-equal（missing/extra 均为空）；29 tracked-existing + 14 planned-new 与 `git ls-files` 分类逐字一致（含 preserved untracked `source_sync.py` 归 planned-new）；108 个 tuple member 覆盖 56 个 unique test 文件，0 个 member 落在 40 writable ∪ 18 catalog 之外；40 项 writable test 中仅 `test_source_sync_job.py` 与 `test_fins_s3_blob_repository_minio.py` 不进 matrix——与 §14"独立 lane 不补分母"的刻意声明一致，非 stale/missing key | PASS |
| 18 catalog | 零编辑、与 writable 零交集、全被 matrix 引用、全存在 | 18 项唯一；全部 tracked 存在；与 40 writable 交集为空；全部被 matrix 引用（catalog unreferenced = 空） | PASS |
| 五个 PG gate | 恰好五 owner、exact integration test file、非 PG tuple 零 integration member | 五个 PG/migration owner 各对应单一 integration 测试文件且全部 integration；其余 38 个非 PG tuple 零 integration member；§14 冻结 changed owner 单次 instrumented Gate1+2、unchanged owner 单次 plain Gate2、source-sync-job 独立 lane、executed-file ledger、八 isolated lanes 与逐项 ignore | PASS |
| 157 named tests | 四段合计 157、zero duplicate | 13.1=47 + 13.2=42 + 13.3=53 + 13.4=15 = 157，跨段全量去重后仍 157（dups=[]） | PASS |
| DAG / stream / cancellation | 六节点单向 DAG、§4.4 items 1–8、coroutine root vs generator early-aclose | 六条 DAG 边逐字在位（source.py->nothing new 等）；§4.4 items 1–8 全部在位；coroutine root/`persist_rejected_filing_artifact` 无伪造 outer aclose、generator 层保留 early-aclose（L1266–1269）；§6.1.1 offload/shield/reap 与 PONR 语义完整 | PASS |
| Residuals | §16 全量保留 | items 1–8 全部在位；末尾 DeepSeek OQ 不扩 scope 声明在位（L2881–2884） | PASS |
| CI / digest | postgres digest 与 conftest 一致、redis 保留 | `ci-pr-extended.yml` postgres digest `64154d0b...` 与 conftest `POSTGRES_16_14_IMAGE` 逐字一致；redis pinned lane 与 aggregate ignore 在位；MinIO pinned digest（`14cea493...`）为 planned 新增 | PASS |

## 4. Open questions / findings

无 open findings（H/M/L = 0/0/0）。无新 open question。

## 5. Residual risks（建议跟踪位置）

- §16 item 8（PONR owned-thread 无 wall-clock 上界）保持记录，后续 platform reliability gate 落地 bounded
  pool/connect/statement/network timeout；本 Slice 不扩 scope——非 plan finding。
- §14 Gate 1 模板相对路径 `--include=<path>` 的 coverage JSON `files` key 输出形态仍以首次执行 probe 记录为
  准（fix 已用 ticker_normalization 95% probe 证明 exact-file 可测）——执行期风险，非 plan 缺口。
- `postgres_identity`/`postgres_jobs`/`postgres_schedules` 的 baseline 数值（78.6344%/79.874706%/80.232558%）
  需按 §14 当次实证、禁止 term rounding 接受——Gate 2 执行风险，plan 已冻结要求。
- L1 的 helper 绑定已由 AST 测试固定为 module-bound binding，实现阶段不得重新引入 caller 注入或 adapter。

## 6. Final conclusion

**PASS / open H/M/L = 0/0/0。**

Round-2 唯一 open L1（rejected persistence 两 helper 去向未冻结）已被 fix `S23-CORR-CONTRACT-09` 与 round-3
target 完整闭合：persistence 只从 zero-diff mapping owner direct import 精确两 helper（mapping owner tracked、
git 零 diff 实测、不进 allowlist/matrix）；exact keyword-only 签名 = 10 business 字段 +
`filing_maintenance_repository` + required `downloader`、五旧 dependency 参数 absent；typed
bind/try/async-for/finally/aclose once；wrapper 保留 business/repository 且 dependency 只传
`downloader=self._downloader`；normal filing imports 保留；两项 named test 覆盖 success/mapping error/inner
error/file_failed exact summary/asyncio cancel（各路径 `aclose_calls==1`）+ AST exactness；STOP/allowlist 一致。
Regression scan 全部通过：43 mapping（29+14 分类 exact）、18 catalog（零编辑、零交集）、五 PG gate、157
named tests（zero duplicate）、六节点 DAG / §4.4 stream items 1–8 / cancellation 语义、§16 residuals 均无
round-3 edit 回归。

评审后复核：target SHA-256 仍为 `ab14e3a97a069551211df303c902ee711d48f0d160ca9c53d54908c78d2c849f`（2884
行）、fix SHA-256 仍为 `9d972471c35956add14930a7bb3311bf156dd7bcb0cee66e5be3a4c5694dd024`（335 行）、WIP
SHA-256 仍为 `4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e`（1839 行、未跟踪），
branch/HEAD 未变（`f0414facbef13081bb036e76d748e1f1cbf178b7`）；未修改任何 plan/master/fix/source/test/WIP，
未 stage/commit/push/PR，未访问网络，未写除本 artifact 外任何文件。
