# Slice 2.3 Stream Ownership / Domain Split — DeepSeek Flash Independent Corrective Plan Re-review Round 2（Fresh Same-SHA）

- 日期：2026-08-12 20:08 CST
- Gate：Gateflow corrective plan 独立同 SHA 复审 round 2（implementation FROZEN）
- Reviewer：DeepSeek Flash（独立；未读取 MiMo 本轮或历史 review；本文件是唯一可写 artifact）
- 角色边界：仅 reviewer，非 Controller/author/planner/implementer/fixer
- 分支：`codex/investment-platform`
- Baseline HEAD：`f0414facbef13081bb036e76d748e1f1cbf178b7`
- Reviewed target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- **Reviewed target SHA-256：`cb192c2bb679d58e465121a4764c8bbe163ffa66e5db0d7e2c74bcb28df9e8e2`（2821 行；评审前/后复核一致）**
- Corrective adjudication（fix）：`docs/reviews/plan-fix-20260812-slice-2.3-stream-ownership-domain-split-codex.md` SHA-256 `469b921de114deba4080fd33e91e4e6ca1bfdd009daa2596aead41b5454af733`（289 行；评审前/后复核一致）
- Prior DeepSeek review（历史 SHA，已被 supersede）：`docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-corrective-deepseek.md`（SHA-256 `20dc65a18bd9fee5183dae01994b6224ee78b6a4c32fbac24a8bd3a1480f9db1`，只读参照，其结论仅证明历史字节）
- Preserved WIP：`dayu/investment/domain/source_sync.py` 1839 行、未跟踪（untracked），SHA-256 `4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e`（评审前/后复核一致，字节未触碰）
- **结论：CLARIFY**
- **Open findings：H/M/L = 0 / 0 / 1**

---

## 1. 评审范围与方法

本评审是 corrective round 2 fresh same-SHA 独立复审。目标：不再只复核旧 finding 是否闭合，而是对冻结 target 全文 2821 行做 adversarial plan review，重点压测用户指定的验证项：

1. M1 exact 43-path owner→tests matrix、29 tracked + 14 planned-new 分类、18 项 coverage-only read-only catalog；
2. Gate 1 strict singleton branch-enabled JSON 门槛与 NUL-safe tracked+untracked 集合；
3. 五个 PG/migration concrete owner 的 Gate 1+Gate 2 单次 instrumented 复用、plain Gate 2 与 executed-file ledger；
4. L2 exact symbol owner、L3 connector/runtime 派生公式、L4 rejected downloader Protocol；
5. 五 owner DAG 与 source.py 零反向 import；
6. AsyncGenerator direct ownership vs coroutine root 语义；
7. writable allowlist、157 项 named tests、STOP conditions 与 residual timeout。

方法：以真实代码事实逐项对账（`pytest.ini`、`tests/integration/investment/conftest.py`、`sec_download_persistence.py`、`sec_download_filing_workflow.py`、`sec_pipeline.py`、`sec_downloader.py`、`base.py`、`cn_pipeline.py`、`cn_download_workflow.py`、`cn_download_filing_workflow.py`、`ingestion/service.py`、`pipeline_backends.py`、`service_runtime.py`、`fins_service.py`、`jobs.py`、`schedule_service.py`、`protocols.py`、`ticker_normalization.py`、`download_events.py`、`evidence_locator.py`、WIP `source_sync.py`、`pyproject.toml`、两个 CI workflow、`git ls-files`/`git cat-file` 分类）。评审期间未修改 plan/fix/WIP/source/tests，未 stage/commit/push/PR，未访问网络，未运行任何实现或测试，未写任何 /tmp 文件。

## 2. 已验证成立的 corrective 机制（逐项 code facts 对账）

### 2.1 M1 43-path owner-test matrix、29/14 分类、18 项 catalog — 全部成立

- §11.1 表格（L2340–2384）恰 43 行 key，无重复 key；43 个 key 与 §11 production allowlist 中 43 个 Python path 双向逐值 exact-equal（`comm -23`/`comm -13` 双向为空），非 Python 的 workflow/docs/README 正确排除。
- 43 个 path 按 `git cat-file -e HEAD:` 分类：**29 tracked-existing + 14 planned-new**，与 plan 声称逐字一致；`source_sync.py`（preserved WIP）正确归入 planned-new（untracked），worktree `git ls-files --others` 证明其为唯一 untracked production Python。
- 43 个 tuple 每个非空、无重复 member；matrix 引用 56 个 unique test 文件，全部落在 40 项 writable test allowlist ∪ 18 项 catalog 内（逐 member 校验 bad=0）。
- 18 项 catalog 文件全部存在于 HEAD、全部被 matrix 引用、与 writable allowlist 零交集；逐文件扫描 18 项 catalog 与全部 non-integration matrix member：**0 个 `@pytest.mark.integration`/`e2e`、0 个 docker/POSTGRES digest 引用**——M1 历史核心矛盾（Gate 1 单文件 lane 混入 Docker 依赖）在分类层面被根除。
- 五个 PG/migration owner 在 §11.1 中的 tuple 与其 §14 Gate 2 表格（L2710–2716）逐项一致；non-PG tuple 全部零 integration member。
- `tests/integration/investment/test_source_sync_job.py` 与 `test_fins_s3_blob_repository_minio.py` 刻意不进 matrix（§14 独立 lane 声明一致），不构成 stale/missing key。

### 2.2 Gate 1 strict singleton branch JSON 门槛 — 模板可执行

- `pytest.ini` addopts 仅 `-v --strict-markers --tb=short`，无 dotted `--cov`、无默认 `not integration` 排除（与 plan 对 Gate 1 模板"无 marker 过滤"的前提一致；PG lane 由 §14 Gate 2 显式 `-m integration` 单独处理）。
- 模板（L2640–2690）：NUL-safe tracked `git diff --name-only -z --diff-filter=ACMRT --find-renames` + untracked `git ls-files --others --exclude-standard -z` + `LC_ALL=C sort -zu` union；fresh `COVERAGE_FILE`（先断言不存在）；`coverage run --branch --include=<path> -m pytest -p no:cacheprovider`；`coverage json --include` 后断言 `meta.branch_coverage is True`、`set(files)=={target_path}` exact singleton、`totals.percent_covered >= 80.0` 原始数值（非 term 取整）；`coverage report --fail-under=80`；任一 collect 失败/空 data/非 singleton/<80 均 fail closed。
- 环境对账：`.venv/bin/python` 存在；`coverage 7.15.4` 可用且 CLI 语义（`--branch`/`--include`/`json --include`/`fail-under`）与模板逐项匹配；`pytest-timeout>=2.1.0` 在 `pyproject.toml` 中声明，Gate 2 的 `--timeout=120` 有依赖支撑。

### 2.3 五个 PG/migration Gate 1+Gate 2 复用与 ledger — 自洽

- `tests/integration/investment/conftest.py` 的 pinned digest `postgres@sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8` 与 plan Gate 2 preflight digest 逐字符一致；conftest `_image_present()` 缺镜像硬失败、不 pull（L196–212），与 Gate 2 "STOP 而非 pull"一致。
- instrumented 单 process 同时满足 Gate 1+2（tests PASS + data 非空 + JSON singleton + >=80.0）、随后只跑同 data 的 report/JSON/shape、禁止 plain rerun 掩盖失败；unchanged owner plain Gate 2 一次且不产生 Gate 1 证据；`test_source_sync_job.py` 独立 lane 不补分母；executed-file ledger（key=test file、kind=instrumented-owner|plain-gate2）防重复启动、防多 owner 组合。
- baseline 数值（postgres_identity 78.6344%、postgres_jobs 79.874706%、postgres_schedules 80.232558%）由 §13.1/§13.4 新增 named test 补足至 strict >=80，且 plan 明确"仍须当次实证、不得按 term rounding 接受"。
- CI 扩展：`ci-pr-extended.yml` 现状已有 PG/Redis pinned lanes 与 aggregate ignore；plan 要求显式 pull MinIO digest、八个独立 pytest process、八个 `--ignore`——与 fix 的"八个 isolated lanes"及 §14 表格一致。

### 2.4 L2/L3/L4 — 已闭合

- **L2**：§3.2 L291–300 明确冻结 foundation 精确拥有 13 个共享符号（SourceConnectorKey/SourceSyncOrigin/SourceBindingDisposition/SourceSyncOutcome/SourceSyncErrorCode/三个 rejection code/三个 closed exception/两个 service error）与 evidence 精确拥有 SourceNoProviderReason + SourceConnectorSyncAction；WIP 中两符号实际位于 evidence 段（source_sync.py:124, 1773 与 :155），与计划归属逐行吻合；foundation 其余 enum/error（L100–257）归属无歧义。
- **L3**：§3.3 L718–732 冻结 `FinsSourceConnector.sync` 逐字段派生公式：`ticker=snapshot.canonical_ticker`、`exchange_mic=snapshot.binding.exchange_mic`、`forms=tuple(sorted(config.forms))`、`start_date/end_date=snapshot.query_*`、`max_documents=config.max_documents_per_sync`、`max_events=16_064` 常量；禁止 alias/overwrite/rebuild 进入 request。§4.1 L1108–1123 冻结 runtime 对 pipeline 的唯一调用形状（comma-joined forms、ISO dates、overwrite/rebuild=False、`ticker_aliases=[request.ticker]`、`cancel_checker`）；`exchange_mic` 仅 preflight、caps 仅 runtime。`FinsWorkerSyncRequest` 字段（ticker/exchange_mic/forms/start/end/max_documents/max_events，全无 default、frozen slots、forms 1..16 sorted unique）与 §3.5 硬限（500/16064/16）互洽。
- **L4**：§4.4 item 7（L1296–1319）冻结 `_RejectedArtifactDownloaderProtocol.download_files_stream` 完整签名 `(remote_files, overwrite, store_file, existing_files=None, primary_document=None) -> AsyncGenerator[DownloaderEvent, None]`，与真实 `SecDownloader.download_files_stream`（sec_downloader.py:1164–1170）逐字段一致；删除 optional callable 与 legacy fallback 的方向与真实代码（sec_download_persistence.py:192–196、232–253 的 fallback 分支）一致。**但发现参数清单缺口，见 L1。**

### 2.5 五 owner DAG、AsyncGenerator direct owner vs coroutine root — 成立

- §3.2 L190–198 与 L747–755 六节点 DAG（source.py -> nothing new；source_sync -> source/jobs/schedules；source_payload -> +identifiers；source_evidence -> +payload；source_health -> +identifiers；source_operation -> payload/evidence/health/jobs）单向无环；`source.py` 897 行现状（wc 实测）与"零反向 import"前提一致；`dayu/investment/connectors/source.py` 为唯一 adapter，`connectors/` 目录当前不存在（planned-new，符合 allowlist）。
- AsyncGenerator 链（§4.4 items 1–8）与真实消费拓扑逐项对应：`base.py::PipelineProtocol.download_stream` 当前返回 `AsyncIterator`（L31–48）→ 需改；`SecPipeline.download_stream`（L474–485 native generator，AST 验证含 yield）、`CnPipeline.download_stream`（L393–404）、`ingestion/service.py`（L20–30 协议、L74–85 实现）、`pipeline_backends.py`（L17–28/L84–94）、`sec_download_workflow.py`（L162/L238，batching-none L478–479 与 batching-timeout L501–502 两路均存在）、`sec_download_filing_workflow.py`（L140）、`cn_download_workflow.py`（L44）、`cn_download_filing_workflow.py`（L114，无 inner）——全部真实存在且为 native async generator；`SecDownloader.download_files_stream`（L1164）AST 验证含 yield 为 native generator。
- coroutine root 语义正确：`sync_worker_source`（新 coroutine）与 `persist_rejected_filing_artifact`（sec_download_persistence.py:179 普通 `async def`）无 aclose 伪造；§4.4 明确两者由 caller-task cancellation 进入自身 finally。
- 三处 exact signature：`FinsRuntimeProtocol`（service_runtime.py:678）与 `DefaultFinsRuntime`（:1950，已有 `source_repository` 字段与 `_build_pipeline_for_ticker`:1981）当前均无 `sync_worker_source`——与 plan"新增并逐 token 相同 required keyword-only cancel_checker"一致；`FinsService`（fins_service.py:32）当前无 `sync_worker_source`，plan 为唯一新增点；`JobCancellationSignalProtocol.is_cancel_requested`（jobs.py:1288）存在，FinsService 内部 adapter 缝成立。
- `SafeJobErrorCode` 当前含 12 成员（含 REPOSITORY_FAILURE），无 SOURCE_* 三值——plan §2.2 新增三个成员且 exact value 正确；`JobIdempotencyRecord` 当前不存在（jobs.py 无此 class）——plan 为新增。
- `ScheduleStoreProtocol`（protocols.py:614）当前 9 方法；plan §5.2 新增 get_by_key/ensure_registered 成 11 方法——数字自洽。`JobExecutionHandlerProtocol.execute`（job_service.py:151）当前二参数——plan 三参数全量替换一致；`execute_claim`（:576）与 `_handler_rejected_failure`（:1342）存在。
- `download_events.py` 不在 allowlist 且 plan 显式禁止修改；`DownloadEvent.payload: dict[str, Any]`（L45）与 §4.3"legacy dict 消费、不递归校验 FILE 事件 payload"一致；`ticker_normalization.py` 的 `normalize_ticker -> NormalizedTicker(market/exchange)`（L84、L29–44）与 §4.2 MIC→market/exchange 映射互洽。
- `EvidenceLocatorProjection`（evidence_locator.py:298）11 字段与 §3.2.2 严格 parse 的 12 key（11 字段 + schema_version）一致；`to_json()`（:357）存在，adapter 两 hash 算法可构造。

### 2.6 writable allowlist、157 项 named tests、STOP/residual — 成立

- §11 writable test allowlist 40 项（29 tracked-existing + 11 planned-new，实测）；全部 40 项被 matrix 引用，无孤儿。
- §13 named tests：47（§13.1）+ 42（§13.2）+ 53（§13.3）+ 15（§13.4）= **157 项，zero duplicate**（四段各自与跨段 uniq -d 均为空）——与 fix "§13 有 157 项 named tests 且 zero duplicate"声明一致。
- STOP conditions（§15）覆盖 allowlist 外触碰、Fins submit、tenant 重建、lease/fence、伪造 source date、aclose 缺失、JobStore 读 source 表、God module、download_events 修改、CI 未隔离等；residual（§16）明确记录 PONR 无界等待依赖（SQLAlchemy/psycopg/OS 永不返回）、provider 非 exactly-once、source/Job 非同事务等，且 OQ1 已按 fix §2 S23-CORR-RESIDUAL-08 记录为 reliability residual，不扩 scope。

## 3. Findings

### L1-未修复-[低]-rejected persistence 的参数删除清单与真实签名不全等，两个剩余 helper 参数去向未冻结
- **位置**：target §4.4 item 7（L1296–1319）、§13.2 rejected-artifact 扩展描述（L2539–2543）
- **问题类型**：契约缺失 / constructibility / 不可直接实施
- **当前写法**：``````persist_rejected_filing_artifact``接收required ``downloader: _RejectedArtifactDownloaderProtocol``，并删除旧 ``download_files_stream``、``download_files``与``normalize_download_file_result``三个参数及全部fallback``````；§13.2 断言"以 required ``downloader`` 替换旧三个参数，以及 ``SecPipeline`` caller 只传 ``downloader=self._downloader``"。
- **反例/失败场景**：真实签名（sec_download_persistence.py:179–196）有 **5 个** helper/callable 参数：`download_files_stream`、`download_files`、`build_file_result_from_downloader_event`、`normalize_download_file_result`、`summarize_failed_download_file_reasons`。plan 只冻结删除前三个（stream/legacy aggregate/normalize），而 `build_file_result_from_downloader_event`（L234 stream 分支内把 DownloaderEvent 转 file result dict 的必需 helper）与 `summarize_failed_download_file_reasons`（L253 失败汇总的必需 helper）的去向未冻结：它们当前由 `SecPipeline` 从 `sec_download_event_mapping.py` import 后作参数传入（sec_pipeline.py:683–685、1240–1242），且 `sec_download_event_mapping.py` **不在 production allowlist**。若按"只传 downloader"字面执行，这两个 helper 必须改为模块级 direct import（触碰 allowlist 外文件，触发 §15 STOP）或在 persistence 内复制逻辑（违反 AGENTS.md 重复逻辑抽取规则）；若保留为参数，则"caller 只传 downloader"断言（§13.2 AST 检查点）无法成立。
- **为什么有问题**：本 corrective 的核心卖点是"消灭 implementation agent 再设计"；L4 声称"冻结完整真实签名"，但对 5 个参数中 2 个的删除/保留/来源未给出裁决，把设计决策交还 agent，且两个方向各自撞上 plan 自己的一条硬约束（allowlist STOP vs AST 断言）。
- **直接证据**：sec_download_persistence.py:179–196（五参数签名）、:232–253（stream/legacy 分支使用两 helper）；sec_pipeline.py:84–87、:683–685、:1240–1242（caller 传入来源）；target §4.4 item 7（L1311–1313）、§13.2（L2541–2543）；`sec_download_event_mapping.py` 不在 §11 production allowlist。
- **影响**：implementation agent 跑偏 / 触发不必要的 STOP 往返 / AST 断言与实现二选一冲突。
- **建议改法和验证点**：在 §4.4 item 7 补一行冻结：persistence 新签名只接收 `downloader`（与 `filing_maintenance_repository` 等非 callable 参数），并将 `build_file_result_from_downloader_event`/`summarize_failed_download_file_reasons` 改为 persistence 模块从 `sec_download_event_mapping.py` 的 direct import（该文件保持零编辑、仅新增 import 边，需把该 import 关系与"零编辑"写进 §11.1 或 §4.4 注释），或在签名中显式保留这两个 helper 参数并同步修改 §13.2"caller 只传 downloader"断言为"caller 只传 downloader 与两个 mapping helper"；随后以 §13.2 AST 断言核对该选择。任选其一都能闭合，plan 当前二者皆未冻结。
- **修复风险（低/中/高）**：低
- **严重程度（低/中/高/严重）**：低

## 4. Open questions

- **OQ1（Low，defer）**：§14 Gate 1 模板中 `--include="$production_path"` 使用相对路径（repo root 相对）；coverage 的 `files` key 输出形式与 `--include` 模式匹配在既有探针（fix 用 ticker_normalization 95% 证明 exact-file 可测）下成立，但本 review 未实际运行该模板（只读限制）。建议 Gate 1 首次执行时以 probe 报告记录一次相对路径 key 输出，确认 JSON `files` 为 `{path}` 而非 `./path` 或绝对路径。
- **OQ2（Low，defer）**：`postgres_schedules` 既有 80.232558% 与 identity/jobs 的 78.6344%/79.874706% 是 fix 声称的实测 baseline；本 review 无法独立复测（未运行 PG lane）。plan 已要求当次实证并禁止 term rounding 接受，残留为 Gate 2 执行风险而非 plan 缺口。

## 5. Residual risks（建议跟踪位置）

- L1 闭合路径（direct import vs 保留参数）由 Controller 裁决后以 plan 补丁冻结；未冻结前 implementation 保持冻结。
- PONR 无界等待（§16 item 8）：已记录，建议在实现 artifact 中记录对 pool/connect/statement/network timeout 的依赖，后续 platform reliability gate 落地 bounded 配置。
- 0005 真实 PG 行为（NOT VALID+VALIDATE 两阶段 FK swap、legacy row 兼容、immutable guards、RLS/grant）为 Gate 2 真实环境验证风险，plan 已冻结 exact 步骤，非 plan finding。
- alert dedupe/event_id 确定性依赖 concurrent terminal 完全串行化：由 generation/lock/UNIQUE 闭合，低风险。

## 6. Final conclusion

**CLARIFY / open H/M/L = 0/0/1。**

本轮 fresh same-SHA 复审的核心结论：corrective 机制经真实代码逐项对账全部成立——M1 的 43-path owner matrix 与 29/14 分类、18 项零编辑 catalog（且全部无 integration marker/docker 依赖，M1 历史矛盾根除）、strict singleton branch JSON gate 模板、五个 PG/migration owner 的 Gate1+Gate2 单次 instrumented 复用与 ledger、L2/L3/L4 主体闭合、五 owner DAG、AsyncGenerator direct owner vs coroutine root 语义、157 项 named tests、STOP/residual 均与代码事实一致。唯一 open finding 是 L1：rejected persistence 真实签名 5 个 callable 参数中，plan 只冻结删除 3 个，`build_file_result_from_downloader_event` 与 `summarize_failed_download_file_reasons` 两个必需 helper 的删除/保留/来源未裁决，且 `sec_download_event_mapping.py` 不在 allowlist——两条闭合路径各自撞上一条硬约束。该 finding 不涉及行为语义（下载/close 形态已冻结），修复风险低；按本 gate 规则 PASS 需 open H/M/L=0/0/0，因此当前结论为 CLARIFY。L1 由 Controller 裁决并补丁冻结后，本 reviewer 建议进入下一轮同 SHA 复核。

评审后复核：target SHA-256 仍为 `cb192c2bb679d58e465121a4764c8bbe163ffa66e5db0d7e2c74bcb28df9e8e2`、fix SHA-256 仍为 `469b921de114deba4080fd33e91e4e6ca1bfdd009daa2596aead41b5454af733`、WIP SHA-256 仍为 `4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e`（1839 行、未跟踪），branch/HEAD 未变；未修改任何 plan/master/fix/source/test/WIP，未 stage/commit/push/PR，未访问网络，未写除本 artifact 外任何文件。
