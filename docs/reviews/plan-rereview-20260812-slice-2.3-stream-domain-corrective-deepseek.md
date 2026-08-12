# Slice 2.3 Stream Ownership / Domain Split — DeepSeek Independent Corrective Plan Re-review

- 日期：2026-08-12
- Gate：Gateflow corrective plan 独立同 SHA 复审（implementation FROZEN）
- Reviewer：DeepSeek（独立；未读取任何先前行 review、未读取其他同轮新 review）
- 分支：`codex/investment-platform`
- Accepted plan commit：`f0414facbef13081bb036e76d748e1f1cbf178b7`
- Reviewed target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- **Reviewed target SHA-256：`0712f30daabfe26dc6c5368a1521dc63f88a6c19480b100d32f04430b396f39e`（评审后复核一致）**
- Master（设计真源）：`docs/plans/2026-08-10-investment-platform-restoration.md` SHA-256 `3f6171d64c81862d495c432897b6de5c4cf7fe159d3b74f70ec8acdc191ae3a6`（复核一致）
- Fix artifact（对照）：`docs/reviews/plan-fix-20260812-slice-2.3-stream-ownership-domain-split-codex.md` SHA-256 `7be0444e5fe067a2bc47b19e80ceeac063e0d23a740f77065f4e04c24967ad46`（复核一致）
- Preserved WIP：`dayu/investment/domain/source_sync.py` 1839 行、未跟踪，SHA-256 `4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e`（复核一致，未触碰）
- **结论：CLARIFY**
- **Open findings：H/M/L = 0 / 1 / 3**

---

## 1. 评审范围与方法

对冻结 target 做 adversarial plan review，重点压测八条主轴：

1. code-generation constructibility（能否直接交给 implementation agent，无需再设计）；
2. AsyncGenerator direct-owner `aclose`/cancellation 链（§4.4）；
3. `sync_worker_source` 三处 exact signature（component / `FinsRuntimeProtocol` / `DefaultFinsRuntime`）；
4. 五 owner DAG 与 public/private symbol manifest（§3.2）；
5. decoder 双 cap 与命名测试（§3.2、§13.1）；
6. allowlist 与 ripple 完整性（§11）；
7. untracked-aware exact-file branch-enabled coverage gate（§14 Gate 1）；
8. sequencing / schema（0005）/ concurrency（NOWAIT 锁序）/ STOP conditions。

方法：以 real code facts 逐项对账（pipelines/base.py、sec/cn pipeline、ingestion service/backend、
workflows、sec_downloader、sec_download_persistence、service_runtime、fins_service、job_service、
jobs.py、source.py、schedules.py、WIP source_sync.py、pytest.ini、integration conftest、§11 两清单、
pytest 收集/运行环境）。评审期间未修改 plan/master/fix/WIP/source/tests，未 stage/commit/push/PR，
未访问网络，未运行任何实现或测试。

## 2. 已验证成立的 corrective 机制（code facts 对账）

以下机制经真实代码逐项验证，与 target 描述一致：

- **aclose 链拓扑完整且真实**：`SecPipeline.download_stream`(sec_pipeline.py:474)→`FinsIngestionService.download_stream`(:505)→`PipelineIngestionBackend.download_stream`(pipeline_backends.py:114)→`download_stream_impl`(:548)→`run_download_stream_impl`(sec_download_workflow.py:238, batching-none :479 与 batching-timeout :502 两路)→`SecPipeline._download_single_filing_stream`(:649)→`run_download_single_filing_stream`(sec_download_filing_workflow.py:140)→`SecDownloader.download_files_stream`(:404 getattr 点)。CN 链同理（cn_pipeline.py:424/:467 → cn_download_workflow.py:265 → cn_download_filing_workflow.py:114，后者无 inner）。全部消费点/叶子的 native-generator 性质与 `AsyncIterator` 当前注解已逐项核实，§4.4 items 1–8 与真实消费拓扑一一对应。
- **coroutine root 与 rejected persistence 语义**：`sync_worker_source`（新）、`persist_rejected_filing_artifact`（sec_download_persistence.py:179，普通 `async def`）均无 `aclose`；§4.4 不伪造 outer aclose、改测 caller-task cancellation 的处理正确。`SecPipeline._persist_rejected_filing_artifact` 的 getattr/callable/cast（sec_pipeline.py:1220-1225）与 `run_download_single_filing_stream` 的 getattr（sec_download_filing_workflow.py:398）均在 allowlist 文件内，删除点精确。
- **三处 exact signature**：`FinsRuntimeProtocol`(service_runtime.py:678)、`DefaultFinsRuntime`(service_runtime.py:1950, 已有 `source_repository` 字段与 `_build_pipeline_for_ticker`:1981)、新 component 三者同签名、`cancel_checker` required keyword-only 的冻结可机械验证；`JobCancellationSignalProtocol.is_cancel_requested`(jobs.py:1288) 存在，FinsService 内部 adapter 缝成立。
- **五 owner DAG 与拆分**：WIP 顶层 manifest（100–589 enum/error/validator、590–1409 config/input/binding/snapshot/payload、1410–1839 locator/evidence/candidate/connector）与 §3.2 描述逐行吻合；receipt/result 确未实现；`_decode_document` 确把 8MiB cap 硬编码（source_sync.py:391-421）。拆分行号区间（862–1409 / 1410–1839）与 WIP 实际边界一致。
- **decoder 双 cap**：`parse_canonical_document`（jobs.py:553）无独立 byte cap，foundation decoder 的 `max_bytes` 参数不与通用 parser 冲突；8,388,608/1,048,576 双 tier 与 one-byte-over 的 runtime 断言可构造。
- **coverage gate 模板**：NUL-safe tracked+untracked union、fresh `COVERAGE_FILE`、`--include=<path>` 单文件、JSON `meta.branch_coverage`/exact-singleton 断言、`--fail-under=80` 对应 combined percent，模板本身可执行（fix 已用 probe 证明），`pytest.ini` addopts 无 dotted `--cov` 依赖。
- **handler 三参数替换 ripple 收敛**：全仓只有 `tests/application/test_job_service.py` 与 `tests/integration/investment/test_postgres_jobs.py` 注册 handler fake（均已在 test allowlist），`PipelineProtocol` 生产实现者只有 Sec/CnPipeline（均已在 allowlist），无 allowlist 外实现者会被返回类型变更破坏。
- **STOP/sequencing/schema**：§12 切片顺序合理（WIP SHA 复核→拆 owner→handler→Fins→0005→repository→facade→startup→CI）；0005 upgrade/downgrade DAG、NOWAIT 锁序、immutable guards、RLS/grant manifest 在 §8 内自洽；`JobCompletion`(jobs.py:1318, 仅 `result: CanonicalJobDocument`) 与 PONR 后 byte-identical completion 的构造可闭合。

## 3. Findings

### M1-未修复-[中]-Gate 1 的 owner→tests 映射未冻结，PG store 文件与单文件 branch≥80% 门槛互相冲突
- **位置**：target §14 Gate 1（L2472-2527）、§11 test allowlist（L2224-2265）
- **问题类型**：不可直接实施 / 契约缺失 / validation gate constructibility
- **当前写法**：``对 changed list 中的每个 ``production_path`` 从 §11/owner mapping 解析唯一 ``owner_tests`` 数组``——但 §11 不含任何映射表；同时 §11 production allowlist 包含 `dayu/investment/storage/postgres_jobs.py`（5354 行）、`postgres_schedules.py`（2038 行）、`postgres_sources.py`（新），它们的 §11 "direct owner test" 全部是 `tests/integration/investment/test_postgres_*.py`（integration marker）。
- **反例/失败场景**：实现 agent 若把 postgres_*.py 映射到其 integration owner test，Gate 1 的模板命令 ``-m pytest`` 无 marker 过滤（`pytest.ini` addopts 仅 `-v --strict-markers --tb=short`，无默认 ``not integration`` 排除），会收集并运行 integration 测试：`tests/integration/investment/conftest.py` 会在缺本地 pinned image 时直接抛 `PlatformIntegrationError`（:310-315，"不在 pytest 内隐式 pull"），与 Gate 1 "禁止联网或安装依赖"的约束冲突；即使镜像在本地，也等于把 Docker/PG lane 混入"单文件 coverage"gate，与 Gate 2 职责重叠。若 agent 改为只映射 unit 测试，则 5354 行 concrete PG store 的 branch-enabled combined coverage≥80% 无法达成，Gate 1 对这批文件要么不可执行、要么被静默豁免。
- **为什么有问题**：本 corrective plan 的核心卖点就是"消灭 implementation agent 再设计"；owner→tests 映射正是 Gate 1 能否跑通的关键设计决策，却未在 plan 中冻结。两种合理解读各自撞上 plan 自己的一条硬约束。
- **直接证据**：`pytest.ini` L25-27（addopts）；`tests/integration/investment/conftest.py` L310-315（缺镜像硬失败、不 pull）；target §11 test allowlist 的 integration 路径；target §14 Gate 1 模板（L2491-2517）无 marker 过滤与 owner-mapping 出处；`dayu/investment/storage/postgres_jobs.py` wc=5354。
- **影响**：implementation agent 跑偏 / Gate 1 对 PG store 文件无法执行或静默豁免 / 覆盖率门槛失去证明力。
- **建议改法和验证点**：在 target 中冻结 exact production→owner_tests 映射表；并明确其一——(a) Gate 1 排除 PG-store 文件（其 coverage 由 Gate 2 真实 PG lane 证明），或 (b) 显式允许 Gate 1 对 PG-store 文件使用本地 pinned image 的 Docker lane（列出 exact 测试清单，仍禁止 pull/install）；随后以一条 dry-run 证明每个 production path 的 lane 可 collect、可执行、JSON exact-singleton 成立。
- **修复风险（低/中/高）**：低
- **严重程度（低/中/高/严重）**：中

### L2-未修复-[低]-五 owner 的共享 enum/error 精确归属未在冻结清单中逐项指定
- **位置**：target §3.2 L257-272（owner 清单）、§3.2 bullet 1（foundation 职责）
- **问题类型**：契约缺失 / constructibility
- **当前写法**：清单中仅 `SourceSyncOutcome`/`SourceHealthStatus`/`SourceConnectorSyncAction`/`SourceTerminalRecordAction` 带括号 owner；`SourceConnectorKey`、`SourceSyncOrigin`、`SourceBindingDisposition`、`SourceNoProviderReason`、`SourceSyncErrorCode`、三个 rejection code、两个 service error 均无括号 owner。
- **反例/失败场景**：foundation 描述"执行共享 enum / closed exception"可默认覆盖大多数，但 `SourceNoProviderReason` 实际只被 evidence 的 `SourceNoProviderTerminalCandidate` 使用；agent 既可留在 foundation 也可随 evidence 搬移。architecture manifest 测试只保证自洽，不保证计划的 intended 归属。
- **为什么有问题**：corrective 的目标是"冻结 exact `__all__` 与 public manifest"，共享符号的归属是 manifest 的核心内容，留白即把裁决权交还 agent。
- **直接证据**：target L257-272 逐行（括号 owner 只出现 4 次）；`SourceNoProviderReason` 在 WIP 中位于 evidence 段（source_sync.py:124, 1773）。
- **影响**：轻微跑偏 / manifest 与计划意图可能不一致。
- **建议改法和验证点**：在 §3.2 冻结清单为剩余 9 个共享符号补括号 owner（建议全部 foundation，`SourceNoProviderReason` 可随 evidence）；named manifest 测试据此写死。
- **修复风险**：低
- **严重程度**：低

### L3-未修复-[低]-connector 的 snapshot→`FinsWorkerSyncRequest` 派生公式未冻结
- **位置**：target §3.3（FinsSourceConnector "只委托"）、§4.1（`FinsWorkerSyncRequest` 字段）
- **问题类型**：契约缺失 / constructibility
- **当前写法**：`FinsSourceConnector.sync()` 需由 `SourceExecutionSnapshot`/config 派生 `FinsWorkerSyncRequest`（ticker/MIC/forms/start/end/max_documents/max_events），但 plan 未给出 exact 派生公式——尤其 `max_events`（§3.5 硬上限 16064）由谁以何常量传入未指定。
- **反例/失败场景**：agent 可能把 `max_events` 与 `max_documents` 混用，或新造第三个 cap 常量绕过 16064 硬限。
- **为什么有问题**：adapter 是 Fins-to-investment 唯一边界，构造公式是该边界最易漂移的点；plan 对其余边界都冻结了逐字段公式，此处留白不一致。
- **直接证据**：target §3.3 L699-702（"只委托"）、§4.1 L956-961（字段无 default）、§3.5 L944-948（16064 硬限）；`FinsSourceConnector` 为新文件（allowlist 内）。
- **影响**：低风险跑偏，可通过 `test_fins_worker_sync_rejects_unknown_market...` 类测试兜住。
- **建议改法和验证点**：补一行冻结：`max_documents=config.max_documents_per_sync`、`max_events=16064 常量`、window=snapshot query window、forms=config.forms。
- **修复风险**：低
- **严重程度**：低

### L4-未修复-[低]-rejected persistence 的"窄 typed downloader dependency"参数形状未冻结
- **位置**：target §4.4 item 7
- **问题类型**：契约缺失 / constructibility
- **当前写法**：现状签名是 `download_files_stream: Optional[Callable[..., AsyncIterator[DownloaderEvent]]]`（sec_download_persistence.py:192）；corrective 只写"定义窄 typed downloader dependency，其 `download_files_stream` 精确返回 `AsyncGenerator[DownloaderEvent, None]`；删除 optional callable 与 legacy fallback"，未冻结新参数是 Protocol 类实例还是绑定方法、以及 `SecPipeline._persist_rejected_filing_artifact` 如何构造它。
- **反例/失败场景**：agent 可能新造一个一次性 adapter 类（god wrapper）或把 `SecDownloader` 直接塞入 persistence 模块，破坏"窄依赖"意图。
- **为什么有问题**：行为（始终 bind/close、无 fallback）已冻结，但参数形状是 agent 的设计决策点。
- **直接证据**：sec_download_persistence.py:192、:232-233；target §4.4 item 7。
- **影响**：轻微跑偏，owner test（`test_rejected_artifact_persistence_closes_typed_downloader_stream_once_...`）可兜住。
- **建议改法和验证点**：补一句：persistence 接收一个 module-private Protocol 依赖，其唯一方法 `download_files_stream(...) -> AsyncGenerator[DownloaderEvent, None]`，由调用方（SecPipeline）传入自身 typed `SecDownloader`。
- **修复风险**：低
- **严重程度**：低

## 4. Open questions

- **OQ1（Low，defer）**：§6.1.1 PONR 的 `shield(to_thread(...))` 循环在 inner 无限阻塞（PG 网络分区、无 statement_timeout 兜底）时无界等待，Worker drain 可能悬挂。plan 已显式接受该语义，但未记录对 statement_timeout/连接超时的依赖或 bounded 处理。建议在 §16 residual 或实现 artifact 中记录该依赖，避免后续 Worker drain 问题被误判为回归。
- **OQ2（Low，defer）**：`DefaultFinsRuntime.__post_init__` eager 构造 component 会作用于所有 dataclass 直接构造点（不只 `create()`）。plan 声明所有路径一致且 component 为纯对象无副作用；建议 named test 覆盖 explicit-provider 路径（`test_explicit_production_provider_keeps_identity_...` 已列）并记录每个既有构造点的 behavior 不变。
- **OQ3（Low，verify at Gate 7）**：`tests/fins/test_cn_download_runtime.py` 引用 `PipelineProtocol`（:26,:208）但不在 §11 test allowlist；返回注解 `AsyncIterator→AsyncGenerator` 无运行时影响（base.py 的 `PipelineProtocol` 非 `runtime_checkable`，已核实），但建议 Gate 7 named-test/allowlist audit 显式确认该文件零 diff，防"悄悄扩 scope"。

## 5. Residual risks（建议跟踪位置）

- Gate 1 与 Gate 2 对 PG-store 文件的 coverage 职责划分：跟踪 M1，由 Controller 裁决后在 target 补丁闭合。
- PONR 无限阻塞收敛保证：跟踪 OQ1，记录到实现 artifact/§16。
- 0005 真实 PG 行为（NOT VALID+VALIDATE 两阶段 FK swap、legacy row 兼容、immutable guards）：plan 已冻结 exact 步骤，残留为 Gate 2 真实环境验证风险，非 plan finding。
- alert dedupe/`event_id` 确定性依赖 concurrent terminal 完全串行化：由 generation/lock/UNIQUE 闭合，plan 已冻结，低风险。

## 6. Final conclusion

**CLARIFY / open H/M/L = 0/1/3。**

核心 corrective 机制经真实代码拓扑逐项验证成立：aclose direct-owner 链完整且与 §4.4 一一对应、
coroutine root 语义正确、三处 exact signature 可机械验证、五 owner 拆分与 WIP 结构吻合、
decoder 双 cap 无通用 parser 冲突、coverage gate 模板 NUL-safe 且 untracked-aware、
allowlist 覆盖全部真实实现者/消费者。M1 是 validation gate 的可实施性缺口（owner→tests 映射未冻结 +
PG store 文件与 80% 门槛冲突），需要 Controller 裁决后以 plan 补丁闭合或提供 Gate 1/Gate 2 职责划分证据；
L2-L4 为低风险留白。在 M1 闭合前不建议解冻 implementation。

评审后复核：target SHA-256 仍为 `0712f30daabfe26dc6c5368a1521dc63f88a6c19480b100d32f04430b396f39e`，
master/fix/WIP SHA 均未变化；未修改任何 plan/master/fix/source/test，未 stage/commit/push/PR。
