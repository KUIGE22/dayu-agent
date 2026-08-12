# Slice 2.3 Stream Ownership / Domain Split — Codex Corrective Plan Fix

- 日期：2026-08-12
- Gate：Gateflow corrective plan acceptance bookkeeping after round-3 fresh same-SHA dual PASS
- 状态：CORRECTIVE PLAN FIX CLOSED / ROUND-3 DEEPSEEK FLASH + MIMO PASS OPEN 0/0/0 / LOCAL ACCEPTED CORRECTIVE-PLAN COMMIT NEXT / IMPLEMENTATION FROZEN UNTIL COMMIT SUCCEEDS
- 分支：`codex/investment-platform`
- Accepted plan commit：`f0414facbef13081bb036e76d748e1f1cbf178b7`
- 前序代码基线：`0db6c7b63608a15cd157f842a5be772799fdacd9`
- Target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- Master control：`docs/plans/2026-08-10-investment-platform-restoration.md`
- Target accepted bytes SHA-256：`7550c9e888fda5af4771cc92a7b716fefbeb08cfdb498fb114c88cf09624ef83`
- Historical independently reviewed semantic SHA-256：`96bceb321464223c9022af25905ca36c4bfe5cdca371111384567acb396ee4f0`
- Round-3 input target SHA-256：`cb192c2bb679d58e465121a4764c8bbe163ffa66e5db0d7e2c74bcb28df9e8e2`
- Round-3 input fix SHA-256：`469b921de114deba4080fd33e91e4e6ca1bfdd009daa2596aead41b5454af733`
- Corrective target frozen SHA-256：`ab14e3a97a069551211df303c902ee711d48f0d160ca9c53d54908c78d2c849f`
- Corrective master frozen SHA-256：`3f6171d64c81862d495c432897b6de5c4cf7fe159d3b74f70ec8acdc191ae3a6`
- 模型路由：本fix由Codex internal完成；DeepSeek与MiMo只在candidate冻结后做相互独立的同SHA plan review。
- Historical corrective reviews：DeepSeek在target SHA
  `0712f30daabfe26dc6c5368a1521dc63f88a6c19480b100d32f04430b396f39e`给出
  `CLARIFY / open H/M/L=0/1/3`；MiMo对同SHA给出`PASS / 0/0/0`。两者只证明历史candidate，当前修订后均
  失效，必须fresh same-SHA双审。只读artifact分别为
  `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-corrective-deepseek.md`与
  `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-corrective-mimo.md`。
- Historical round-2 reviews：DeepSeek Flash在target SHA
  `cb192c2bb679d58e465121a4764c8bbe163ffa66e5db0d7e2c74bcb28df9e8e2`给出
  `CLARIFY / open H/M/L=0/0/1`，artifact
  `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round2-deepseek-flash.md` SHA-256
  `25bdcb28718a5840d3cac0a1dee41a282a5e5405bfeb7203da4d3be8211e6289`；MiMo对同target给出
  `PASS / 0/0/0`，artifact
  `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round2-mimo.md` SHA-256
  `163c409a993c1c323873f50888df7c13fc59a2ba21fc282b4b0ca960b66c687a`。二者均为当前round-3
  candidate的只读历史证据，不能授权实现；必须fresh round-3 same-SHA双审。
- Final round-3 reviews：DeepSeek Flash
  ``docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round3-deepseek-flash.md``
  SHA-256 ``78f8a2eaee1d505841c2d8ce141519701cdfa02d1d18110338af508759526a76``与MiMo
  ``docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round3-mimo.md``
  SHA-256 ``7725b87136f1594a51535e0aaac30f6c2ef3b2ef3a50f474c0298f2aa73c1c91``独立锁定同一
  target SHA ``ab14e3a97a069551211df303c902ee711d48f0d160ca9c53d54908c78d2c849f``与fix SHA
  ``9d972471c35956add14930a7bb3311bf156dd7bcb0cee66e5be3a4c5694dd024``，结论均为
  ``PASS / open H/M/L=0/0/0``。Corrective acceptance见
  ``docs/reviews/plan-acceptance-20260812-slice-2.3-stream-domain-coverage-codex.md``。
- 外部边界：本acceptance bookkeeping未运行网络、provider、付费模型、Broker、交易或部署；未stage、commit、push、PR，未修改任一reviewer artifact或历史acceptance artifact。

## 1. STOP事实与scope ownership

accepted plan commit之后开始Slice 2.3首个pure-domain implementation。Controller在实现尚未完成时按计划
STOP条件冻结：

| Evidence | Exact fact |
| --- | --- |
| Worktree | 唯一implementation WIP是未跟踪`dayu/investment/domain/source_sync.py`；无其它source/test WIP |
| WIP bytes | 1839物理行；SHA-256 `4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e` |
| Completion point | receipt/result尚未完成；文件尾当前只到connector decision |
| Mixed responsibilities | enum/error/config/input、payload canonicalization、binding/snapshot、locator/evidence、candidate/connector已聚合在同一owner |
| Stream contract | 真实download wrappers/leaf均为native async generators，但accepted contracts返回`AsyncIterator`，静态类型不提供`aclose()` |
| Closure behavior | 当前多层`async for inner_call(...)`不绑定inner；generator wrapper的outer `aclose()`不会自动关闭悬停的direct inner；coroutine root则须由caller-task cancellation进入自身`finally` |

WIP属于implementation agent的保留工作：本plan fix未编辑、删除、覆盖或stage它。恢复实施时必须先核对同一
SHA，再机械split；禁止把STOP当作丢弃/重写授权。

初始corrective pass的scope是target、master与本artifact；round-3语义修复scope进一步收窄为target与本artifact
exactly。round-3 review期间master、existing acceptance、四份历史DeepSeek/MiMo review、production、tests、
README、CI、migration均保持只读；reviewed master SHA-256为
`3f6171d64c81862d495c432897b6de5c4cf7fe159d3b74f70ec8acdc191ae3a6`。双审PASS后，本次acceptance
bookkeeping只允许target、master、本artifact与新acceptance artifact写入status/review链接；不改变任何实施语义。

## 2. Controller finding adjudication

### S23-CORR-STREAM-01-已修复-[高]-download stream合同无法表达direct owner关闭责任

- **Plan位置**：历史target §4.1、§4.4、§11、§13.2。
- **问题类型**：架构边界 / 契约缺失 / allowlist缺口 / cancellation与resource lifecycle。
- **计划当前写法**：`FinsSourceSyncDownloadPipelineProtocol.download_stream`和全链返回
  `AsyncIterator[DownloadEvent]`，同时要求`await inner.aclose()`；只列部分wrapper owner。
- **为什么有问题**：`AsyncIterator`没有typed `aclose`；native outer async generator被提前关闭时不会自动
  关闭正悬停的inner。计划要求与静态类型/真实Python生命周期矛盾，实现者只能漏关或使用
  `cast/getattr/ignore`逃逸。
- **直接证据**：`pipelines/base.py`、SEC/CN pipeline、ingestion service/backend、market/per-filing workflow、
  `SecDownloader.download_files_stream`均是native async generator；SEC normal与rejected-artifact链还存在
  `getattr/callable/cast`及legacy aggregate fallback。
- **影响**：outer early-close、mapping error、domain/asyncio cancellation或timeout可能悬挂inner provider/
  downloader generator，破坏exact ownership、取消收敛和resource cleanup。
- **Controller decision**：`accepted`。
- **Fix**：target统一download-only返回为`collections.abc.AsyncGenerator[T, None]`；冻结root→pipeline→
  ingestion→backend→impl→market→per-filing→SEC downloader exact chain。每个direct owner先绑定inner，
  `try/async for/finally await inner.aclose()`恰好一次；删除SEC normal/rejected链的`getattr/cast/optional
  fallback`。不自定义stream协议、不修改`DownloadEvent`、不扩大process/upload/legacy runtime命令链。
- **新增production allowlist（stream only，exact 4）**：
  `dayu/fins/pipelines/base.py`、`dayu/fins/downloaders/sec_downloader.py`、
  `dayu/fins/pipelines/sec_download_persistence.py`、
  `dayu/fins/pipelines/cn_download_filing_workflow.py`。
- **新增test allowlist（stream only，exact 5）**：
  `tests/fins/test_pipeline_cli.py`、`tests/fins/test_cli_helpers_coverage.py`、
  `tests/fins/test_ingestion_factory.py`、`tests/fins/test_ingestion_job_manager.py`、
  `tests/fins/test_sec_pipeline_rejection_registry.py`。
- **明确不扩scope**：`cli_support.py`与`ingestion/job_manager.py`production是exhaustive consumers；
  `AsyncGenerator <: AsyncIterator`，不需改。legacy `DefaultFinsRuntime._execute_stream/_iter_stream_events`不是
  source-specific root；`tests/fins/test_fins_runtime_tool_service.py`不改。`SecDownloader.download_files`不在
  2.3 source path，不新增aggregate close refactor/test。
- **验证点**：协议/runtime annotations、success/error/domain cancel/asyncio cancel、generator层outer
  early-aclose、timeout与rejected mapping error均证明每层direct inner `aclose_calls == 1`；coroutine root与
  rejected persistence只测caller-task cancellation，不伪造`aclose()`。AST/rg拒绝ownership path的
  `getattr/hasattr/cast/ignore`和legacy fallback。

### S23-CORR-DOMAIN-02-已修复-[高]-三pure-owner假设已被1839行未完成WIP证伪

- **Plan位置**：历史target §3.2、§3.3 architecture、§9、§11–§13、§15。
- **问题类型**：架构边界 / God module / owner职责 / implementation slice不可直接执行。
- **计划当前写法**：`source_sync.py`同时拥有foundation、config/binding/payload、evidence/candidate、receipt/
  result；与health/operation共三个new owner，并宣称这能避免第二个God module。
- **为什么有问题**：receipt/result未实现时`source_sync.py`已达1839行且混合至少三组变化原因；继续实施必然
  违反根`AGENTS.md`禁止God module与最小依赖规则。
- **直接证据**：冻结WIP top-level manifest显示lines 100–589为enum/error/validation，590–1409为
  config/input/binding/snapshot/payload/canonical，1410–1839为locator/evidence/candidate/connector；
  `source.py`现有identity owner为897行。
- **影响**：任何payload/evidence改动都命中同一大owner，测试/coverage/依赖边界失去局部性；receipt/result
  继续加入会放大耦合并诱导compat re-export。
- **Controller decision**：`accepted`。
- **Fix**：固定五个direct-module public owner：
  `source_sync` foundation、`source_payload` binding/snapshot/payload、`source_evidence` locator/evidence/
  candidate/connector/receipt/result、`source_health` health/alert、`source_operation` acquire/terminal。
  target冻结exact one-way DAG、每owner exact `__all__`与public/important-private top-level symbol manifest、
  AST unknown-symbol fail-closed、class/function `__module__`、alias/constant AST owner、package-root零re-export、
  五个direct tests与single-module branch>=80%。行数只作review observation，无任意line gate。
- **新增production allowlist（domain only，exact 2）**：
  `dayu/investment/domain/source_payload.py`、`dayu/investment/domain/source_evidence.py`。
- **新增test allowlist（domain only，exact 2）**：
  `tests/investment/test_source_payload_domain.py`、`tests/investment/test_source_evidence_domain.py`。
- **机械复用**：恢复后先核对WIP SHA，按top-level调用闭包搬移既有bytes/behavior，改全部call sites为direct
  imports并删除旧定义；不能在foundation留alias/wrapper，也不能discard后重新发明contract。
- **构造闭合**：target补齐receipt/result/health/alert builder与parser签名，避免worker再次设计；result只从
  完整receipt派生，receipt parser显式接收canonical JSON中不存在的outer tenant。

### S23-CORR-CANONICAL-03-已修复-[中]-共享decoder的固定8MiB上限会放宽alert合同

- **Plan位置**：target §3.2 responsibility ratchet、§3.2.3。
- **问题类型**：canonical contract / boundary validation。
- **计划/WIP当前写法**：WIP `_decode_document`固定使用8,388,608 byte cap；target alert cap为1,048,576。
- **为什么有问题**：直接复用会让alert parser接受计划上限八倍的文档，或迫使health另造decoder。
- **直接证据**：WIP helper与target §3.2.3 alert cap逐值矛盾。
- **Controller decision**：`accepted`，作为domain split内的同scope闭合。
- **Fix**：foundation private decoder固定参数`schema_name/schema_version/max_bytes`；payload/evidence/receipt/
  result caller传8MiB，health alert caller传1MiB。named architecture test以AST穷举每个direct caller并核对
  exact cap常量，同时运行8,388,608/1,048,576 exact-boundary accept与各自one-byte-over reject；该测试进入
  Gate 6及sync/payload/evidence/health四个single-file coverage mapping。locator sensitive-key scan仍留
  evidence owner。

### S23-CORR-RUNTIME-04-已修复-[高]-把coroutine root误当generator且public signature未闭合

- **Plan位置**：target §4.1、§4.4、§13.2。
- **问题类型**：Python async语义 / public contract / cancellation cleanup / structural typing。
- **计划当前缺口**：早期closure描述把outer `aclose()`套到整个链；同时component、`FinsRuntimeProtocol`与
  `DefaultFinsRuntime`没有一份逐项相同、可机械验证的source-sync signature。
- **为什么有问题**：`DefaultFinsWorkerSourceSyncRuntime.sync_worker_source`和rejected persistence是普通
  coroutine，没有`aclose()`；伪造该测试无法证明真实caller cancellation cleanup。若三层checker可选性或
  positional/keyword约束漂移，Service适配会绕开required cancellation seam且Pyright不能证明替换性。
- **Controller decision**：`accepted`。
- **Fix**：outer early-aclose只保留给返回`AsyncGenerator`的wrapper/workflow；coroutine root与rejected
  persistence在success/error/domain cancellation/caller-task `asyncio.CancelledError`中由自身`finally`关闭
  direct inner。三处精确冻结
  `async def sync_worker_source(request: FinsWorkerSyncRequest, *, cancel_checker: Callable[[], bool]) ->
  FinsWorkerSyncResult`，checker required、keyword-only、无default且不接受`None`；named runtime测试以
  `inspect.signature`、`get_type_hints`和Pyright structural assignment核对三者逐项一致。

### S23-CORR-COVERAGE-05-已修复-[高]-tracked-only与dotted pytest-cov让new owner逃逸或无法执行

- **Plan位置**：target §14 Gate 1/6。
- **问题类型**：validation gate constructibility / untracked planned-new coverage / evidence isolation。
- **计划当前缺口**：changed set只取`git diff`，遗漏未跟踪new modules；每模块mandate使用dotted
  `pytest --cov=<module>`，本地复现该import path失败，且共享coverage data可把别的文件计入结果。
- **为什么有问题**：本次STOP本身就是未跟踪production WIP；继续只看tracked diff会让planned-new
  `source_payload.py`/`source_evidence.py`跳过owner coverage。不可执行的命令或package aggregate也无法证明
  单一责任owner达到branch coverage门槛。
- **Controller decision**：`accepted`。
- **Fix**：changed production set以NUL-safe `git diff --name-only -z --diff-filter=ACMRT --find-renames`与
  `git ls-files --others --exclude-standard -z`对`dayu/**/*.py`取`LC_ALL=C sort -zu` union；每个exact
  production path用全新unique `COVERAGE_FILE`执行
  `coverage run --branch --include=<path> -m pytest ...`，再用同一data执行exact-path report/JSON assertion。
  每份报告只允许一个production file，JSON必须`meta.branch_coverage=true`且files为exact singleton；门槛是
  branch-enabled statement+branch combined coverage >=80%，不是standalone branch-edge percent。missing/no-data/
  任一nonzero均fail closed；禁止dotted pytest-cov、旧data追加、package aggregate、网络安装或planned-new
  escape。

### S23-CORR-COVERAGE-06-已修复-[中]-DeepSeek M1缺少43-path owner test映射与PG Gate复用裁决

- **来源**：DeepSeek corrective re-review M1，`accepted`；MiMo同一历史SHA为PASS，不覆盖该finding。
- **Plan位置**：target §11.1、§13.1/13.4、§14 Gate 1/2。
- **问题**：旧Gate要求从不存在的owner mapping解析tests；concrete PG owners若进普通unit lane会混入Docker，
  若不运行又无法证明exact-file combined >=80。`postgres_identity`实测78.6344%、`postgres_jobs`实测
  79.874706%，term report取整会伪装达标。
- **Controller decision**：`accepted`。
- **Fix**：新增规范``COVERAGE_OWNER_TESTS`` exact 43-key表，keys必须与Python production allowlist
  exact-equal，tuple unique/nonempty且无default/glob/name inference；tuple成员只来自writable test allowlist或
  18项``COVERAGE_ONLY_EXISTING_OWNER_TESTS``零编辑catalog。五个PG/migration concrete owners单独以本地
  pinned PostgreSQL 16 digest、一个fresh instrumented process同时满足Gate 1/2；strict JSON原始值、singleton
  与tests PASS缺一不可，禁止plain rerun掩盖失败。unchanged PG owner plain Gate 2一次，source-sync-job独立一次，
  executed-file ledger防重复，remaining aggregate exact ignore八lane。新增identity三target unique test与Job
  idempotency exact/missing/cross-tenant/persisted-drift parameterized test闭合已知coverage边界。

### S23-CORR-CONTRACT-07-已修复-[低]-DeepSeek L2/L3/L4仍留owner与adapter参数设计点

- **来源**：DeepSeek corrective re-review L2–L4，全部`accepted`。
- **L2 Fix**：foundation exact拥有connector/origin/binding/outcome/error、三种failure/rejection code、三种closed
  exception及两种service error；evidence exact拥有``SourceNoProviderReason``与
  ``SourceConnectorSyncAction``。所有consumer direct import，零re-export。
- **L3 Fix**：冻结connector从execution snapshot/config派生worker request的逐字段公式：canonical ticker、
  MIC、sorted forms、query dates、config max documents、constant 16,064 events；operation/snapshot SHA/aliases/
  overwrite/rebuild不进入request。runtime对pipeline只传ticker、comma forms、ISO dates、两个false、单元素
  alias list与checker；MIC仅preflight，caps仅runtime。新增两个exact named tests。
- **L4 Fix**：冻结module-private ``_RejectedArtifactDownloaderProtocol.download_files_stream``完整真实签名；
  persistence只接收required downloader并删除旧五个dependency参数及fallback；两个mapping helper改由
  persistence direct import既有mapping owner，caller只传``self._downloader``。既有closure/static test扩展到
  asyncio cancellation、private signature、direct imports与caller AST；round-2 L1对helper来源的进一步闭合见
  ``S23-CORR-CONTRACT-09``。

### S23-CORR-RESIDUAL-08-已裁决-DeepSeek OQ1接受记录，OQ2/OQ3不扩scope

- **OQ1**：`accepted as residual`。owned-thread/PONR cleanup不提供SQLAlchemy/psycopg/OS永不返回时的
  wall-clock bound；NOWAIT只限制row-lock contention。本Slice不以``wait_for``遗弃线程、不扩大global timeout
  scope；后续platform reliability gate需交付bounded pool/connect/statement/network配置与故障验证。
- **OQ2**：`rejected as plan gap`。eager component所有构造路径已由existing identity/explicit-provider named
  tests闭合，无需扩大allowlist。
- **OQ3**：`rejected as edit ripple`。``test_cn_download_runtime.py``只作为coverage-only existing owner test
  zero-edit运行；其``AsyncIterator``属于legacy command stream，与download-only contract无关。

### S23-CORR-CONTRACT-09-已修复-[低]-DeepSeek round-2 L1剩余两个helper callback去向未冻结

- **来源**：
  `docs/reviews/plan-rereview-20260812-slice-2.3-stream-domain-coverage-round2-deepseek-flash.md`
  L1，source review SHA-256
  `25bdcb28718a5840d3cac0a1dee41a282a5e5405bfeb7203da4d3be8211e6289`，结论
  `CLARIFY / open H/M/L=0/0/1`；MiMo round-2 `PASS / 0/0/0`只证明同一历史target。
- **Plan位置**：target §4.4 item 7、§11、§13.2、§15。
- **问题类型**：contract constructibility / dependency ownership / duplicated logic风险。
- **问题**：历史candidate只明确删除``download_files_stream``、``download_files``与
  ``normalize_download_file_result``三个dependency参数，却未裁决仍由SecPipeline callback注入的
  ``build_file_result_from_downloader_event``和``summarize_failed_download_file_reasons``。保留注入与“caller
  dependency只传downloader”矛盾；复制helper或编辑mapping owner又违反owner/scope。
- **Controller decision**：`accepted`；选择best-practice direct import owner，不保留callback seam。
- **Fix**：``sec_download_persistence.py``只module-level direct import
  ``sec_download_event_mapping.py``既有两个helper；mapping owner保持zero diff且不进入writable allowlist/matrix。
  冻结persistence完整keyword-only signature：十个existing business args、
  ``filing_maintenance_repository``与required private-protocol ``downloader``；五个旧dependency参数全部删除。
  删除无用legacy helper/import，typed inner以try/async-for/finally close exactly once，事件mapping与failed
  summary直接使用module binding。SecPipeline rejected caller保留business/repository args，dependency kwargs
  只传``downloader=self._downloader``；normal filing path仍需的mapping imports不删。
- **验证**：既有rejected test覆盖success、monkeypatch persistence binding mapping error、inner error、
  file-failed exact summary与asyncio cancellation，对各路径验证close exactly once及DB side effect；AST test核对
  exact protocol/signature/direct imports/五旧参数absent/inner-finally/caller，并拒绝callback injection、adapter、
  copied helper、escape与fallback。新增STOP禁止任何需要编辑mapping owner或保留legacy seam的实现路径。

## 3. Corrective architecture closure

source-specific direct dependency DAG冻结为：

```text
source.py -> nothing new
source_sync -> source/jobs/schedules
source_payload -> source_sync/identifiers/source/jobs
source_evidence -> source_sync/source_payload/identifiers/source/jobs
source_health -> source_sync/identifiers/source/jobs
source_operation -> source_sync/source_payload/source_evidence/source_health/jobs
```

`identifiers.py`是既有leaf强标识owner；每个模块按真实字段直接import，不能通过新owner re-export。
health transition只依outcome/error/config/current head，不依evidence；connector只需sync+evidence，snapshot经
evidence-owned connector request消费。storage protocol按七个annotation direct import五owner。

## 4. Review gate与恢复条件

1. target/fix的round-3 frozen bytes已完成fresh independent same-SHA review；历史round-1/round-2
   DeepSeek/MiMo结论继续只证明各自旧SHA，不被删除或改写。
2. Codex internal同bytes机械、DAG、allowlist、named-test与constructibility closure已完成；round-3 DeepSeek
   Flash与MiMo均为`PASS / open H/M/L=0/0/0`，没有新finding或blocking open question。
3. Controller已接受corrective plan并创建acceptance artifact；下一步只创建本地accepted corrective-plan commit。
   commit成功前implementation继续冻结，不能以review PASS本身恢复WIP实施。
4. commit成功后才可恢复Codex-internal implementation；恢复首步仍是核对WIP SHA并机械split；任何新
   production/test ripple超出expanded allowlist立即STOP。

## 5. Validation与scope audit

本fix完成时必须记录：

- `git diff --check -- <target> <master> <artifact>`；
- 三文件UTF-8、LF-only、final newline；
- target/master SHA-256与WIP SHA复核；
- `git status --short`证明tracked dirty仍只有target/master，untracked scope精确为本artifact、preserved WIP与
  四份只读round-1/round-2 reviewer artifacts；
- target stale scan：无旧三owner/four-node DAG、旧AsyncIterator stream contract、错误“仅public
  download_stream”allowlist或legacy runtime command edit；coroutine root/rejected persistence无伪造outer
  `aclose`，generator层仍保留early-aclose；
- allowlist existence/new-path classification与exact stream additions 4+5、domain additions 2+2；
- exact signature audit：component、`FinsRuntimeProtocol`、`DefaultFinsRuntime`同一required keyword-only
  `cancel_checker` contract及named structural/Pyright test均已冻结；
- canonical cap audit：AST caller穷举、8,388,608/1,048,576双tier exact/one-over runtime test及Gate 6/四owner
  coverage mapping均已冻结；
- Gate 1 audit：tracked + untracked sorted-unique production集合、fresh unique coverage data、exact-path
  run/report/JSON与单文件shape assertion均已冻结；43-key exact owner map、29 tracked + 14 planned-new
  classification、18项zero-edit coverage-only catalog及member provenance均machine-auditable；active mandate不再
  使用dotted `pytest --cov`；
- PG Gate audit：五个concrete owner exact test file、本地pinned digest preflight、changed owner单次
  instrumented Gate 1+2、unchanged owner单次plain Gate 2、source-sync-job独立lane、strict JSON raw threshold、
  executed-file ledger与八lane aggregate ignore均已冻结；
- DeepSeek closure audit：M1、L2–L4均accepted并闭合；OQ1只记录reliability residual，OQ2/OQ3拒绝扩大
  writable scope；§13 named tests至少155项且列表内unique；
- DeepSeek round-2 L1 audit：persistence两个helper只direct import existing mapping owner、完整五旧dependency
  参数删除、exact keyword-only signature、legacy-only dead import/helper cleanup、typed inner close、SecPipeline
  caller及两项named test/STOP均已冻结；mapping owner保持zero diff且不进writable allowlist/matrix；
- 无source/test写入、stage、commit、push或network动作。

最终冻结实际结果：

- tracked target/master的scoped ``git diff --check``：PASS；untracked artifact的
  ``git diff --no-index --check /dev/null <artifact>``零whitespace diagnostic（no-index有内容差异的预期rc=1）；
- 三条authorized docs：UTF-8文本、LF-only（CR count均0）、final byte均``0a``；
- target/master SHA-256分别为
  ``ab14e3a97a069551211df303c902ee711d48f0d160ca9c53d54908c78d2c849f``与
  ``3f6171d64c81862d495c432897b6de5c4cf7fe159d3b74f70ec8acdc191ae3a6``；
- preserved WIP仍为1839行、未跟踪，SHA-256仍为
  ``4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e``；
- tracked diff name-only精确只有target/master；untracked精确为preserved WIP、本artifact及四份只读reviewer
  artifacts：round-1 DeepSeek/MiMo与round-2 DeepSeek Flash/MiMo；本fix未编辑任一reviewer artifact；
- ``git diff --cached --name-only``为空，index未stage任何文件；
- target/master stale scan PASS；stream 4 production + 5 test既有路径全部存在且已显式allowlist；domain
  2 production + 2 test planned-new路径当前均不存在且已显式allowlist；closure finding audit覆盖decoder双cap、
  coroutine cancellation、三层exact signature与tracked+untracked fresh single-file coverage；
- §11/§11.1 audit精确为43 production Python keys（29 tracked-existing、14 planned-new）、43 unique mapping keys、
  zero missing/extra、每tuple nonempty/unique、所有member只来自40项writable tests或18项disjoint
  coverage-only existing catalog；non-PG tuple含零integration member，只有五个concrete PG/migration owner使用
  exact integration tuple；§13有157项named tests且zero duplicate；
- 未运行Slice 2.3 WIP测试或实现。只读coverage constructibility probe在既有
  ``dayu/fins/ticker_normalization.py`` direct owner lane执行68 tests PASS，fresh branch-enabled exact-file
  combined coverage 95%，同时证明untracked Python可被exact path测量且threshold fail closed；probe输出只在
  system temp目录，worktree status与WIP SHA前后不变。dotted pytest-cov eager-import失败证据因此从active
  mandate移除，未安装依赖、未访问网络。

## 6. Open questions / residual

- Blocking open question：无。
- Gate residual：fresh round-3双审已完成且open H/M/L=`0/0/0`；implementation仍冻结至本地accepted
  corrective-plan commit成功。这是当前gate，不是deferred plan finding。
- Reliability residual：``S23-CORR-RESIDUAL-08``对DeepSeek OQ1的裁决保持不变。owned-thread/PONR cleanup
  在SQLAlchemy/psycopg/OS connect、pool、network或statement永不返回时没有wall-clock上界；NOWAIT只覆盖
  row-lock contention。本Slice不以``asyncio.wait_for``遗弃运行中的thread，也不扩大global timeout scope；
  后续platform reliability gate负责bounded pool/connect/statement/network timeout配置与故障验证。
- STOP：若Pyright或direct ownership test证明需要修改已明确排除的legacy CLI/runtime/job-manager/downloader
  aggregate路径，或任何其它allowlist外production/test文件，必须交回Controller补证据和重新review。

## 7. Final corrective closure metadata

- ``S23-CORR-STREAM-01``、``DOMAIN-02``、``CANONICAL-03``、``RUNTIME-04``、``COVERAGE-05``、
  ``COVERAGE-06``、``CONTRACT-07``与``CONTRACT-09``均为Controller ``accepted / fixed``；其中round-2唯一
  open L1由``S23-CORR-CONTRACT-09``以zero-diff mapping owner direct imports、exact 12-field signature、
  five-old-dependency removal、typed inner close与AST/behavior tests闭合。
- Round-3两份review均锁定target
  ``ab14e3a97a069551211df303c902ee711d48f0d160ca9c53d54908c78d2c849f``、fix
  ``9d972471c35956add14930a7bb3311bf156dd7bcb0cee66e5be3a4c5694dd024``与WIP
  ``4396d9d62a21853acc360be1d9f5bac8bcd0041c19dafa29ee2a5d0f2904107e``，并均给出
  ``PASS / open H/M/L=0/0/0``。metadata写回后的closure SHA由acceptance artifact单独记录，不冒充外审
  frozen bytes。
- 历史accepted plan commit ``f0414facbef13081bb036e76d748e1f1cbf178b7``与六份corrective review artifact
  均保留；本artifact不声称新commit已完成，不授权stage、push、PR、部署、provider、网络、模型、Broker、
  交易或资金动作。
