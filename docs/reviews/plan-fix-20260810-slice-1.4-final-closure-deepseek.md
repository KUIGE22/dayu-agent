# Slice 1.4 S3 Fins blob repository final closure plan fix（DeepSeek worker）

- **Worker**：DeepSeek Flash fix worker
- **日期**：2026-08-10
- **基线**：`5d7e6bb`（branch `codex/investment-platform`，HEAD/worktree 冻结为只读审计）
- **状态**：**SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **任务范围**：只修 master plan Slice 1.4
  （`docs/plans/2026-08-10-investment-platform-restoration.md`）与三份既有 fix artifacts
  （`plan-fix-20260810-slice-1.4-s3-blob-repository-codex.md`、
  `plan-fix-20260810-slice-1.4-s3-blob-repository-corrective-deepseek.md`、
  `plan-fix-20260810-slice-1.4-final-corrective-deepseek.md`）；新增本 artifact；
  production/tests/README/dependencies 全部冻结；未安装依赖、未 pull 镜像、未运行
  live/network/model/broker、未 commit/push/PR。
- **Final closure source reviews（只读）**：
  `docs/reviews/plan-final-rereview-20260810-213617-slice-1.4-terra.md`
  （Terra，FAIL，S14-REREVIEW-01..03，2H/1M）、
  `docs/reviews/plan-final-rereview-20260810-213634-slice-1.4-mimo-native.md`
  （MiM Native，PASS-WITH-RISKS，F-01 1M）。
- **Final closure corrective source reviews（只读，round 5）**：
  `docs/reviews/plan-final-closure-rereview-20260810-slice-1.4-terra.md`
  （Terra，FAIL，S14-CLOSURE-01..02，2H）、
  `docs/reviews/plan-final-closure-rereview-20260810-slice-1.4-mimo-native.md`
  （MiM Native，PASS，open 0/0/0）。

## Controller 裁决（final closure，唯一实现，不留二选一）

- 接受 Terra 213617 全部三项：S14-REREVIEW-01（同-core BatchToken 传播无路径且
  allowlist 排除必经编排点，High）、S14-REREVIEW-02（`file_store` 与 `repository_set`
  参数互斥规定与固定 startup 步骤矛盾，High）、S14-REREVIEW-03（destructive state
  machine 未覆盖 processed 更新的文件移除，processed `meta.files` 前提未建立，Medium）。
- 接受 MiM Native 213634 F-01（`_execute_with_auto_batch` 在 S3 模式的 auto-begin 行为
  与 `s3_write_requires_batch` 约束存在实现歧义，Medium）。
- 合并为 **2H/2M**，全部必须在 plan 中精确修复；implementation 继续冻结。

## 只读 callgraph 审计（final closure round，支撑唯一化）

本 round 在既有 final corrective 审计基础上，补证同-core BatchToken 的真实传播路径与
destructive inventory 缺口（均为只读结论，未修改任何 production 文件）：

- **runtime → pipeline 传播链**：
  `DefaultFinsRuntime.create()`（`service_runtime.py:1890-1934`）当前在
  `build_fs_repository_set(workspace_root=...)`（L1909）后构造 5 个窄仓储
  （L1912-1931），**不构造任何 batching repository**；`DefaultFinsRuntime` 是 dataclass
  （L1851-1865），字段无 batching；`_build_pipeline_for_ticker`（L1874-1887）→ 模块级
  `_build_pipeline`（L797-808）→ `get_pipeline_from_normalized_ticker`
  （`pipelines/factory.py:54-95`）→ `SecPipeline(...)`（factory:82）/`CnPipeline(...)`
  （factory:90），透传 5 个窄仓储。
- **pipeline 内部自建第二 core 的事实**：`SecPipeline.__init__`（`sec_pipeline.py:293-359`）
  无条件 `repository_set = build_fs_repository_set(workspace_root=self._workspace_root)`
  （L327）；`CnPipeline.__init__`（`cn_pipeline.py:101-183`）同（L147）。注入 5 窄仓储时
  仍执行该行，产生独立 core/token 空间；`DoclingUploadService` 在 `sec_pipeline.py:352-355`/
  `cn_pipeline.py:180-183` 用 pipeline 自身的 source/blob repository 构造。
- **七条 producer 的真实编排点**（均位于 `dayu/fins/` 内部）：
  1. SEC active + rejected：`run_download_stream_impl`（`sec_download_workflow.py:207`，
     `SecDownloadWorkflowHost` `sec_download_workflow.py:42`）per-ticker 循环
     （L425-460）→ `run_download_single_filing_stream`（`sec_download_filing_workflow.py:140`）
     → `_store_file_callback`（`sec_download_persistence.py:404`）→ `repository.store_file`
     （L425）；rejected 经 `build_rejected_store_file`（L151）→
     `_store_rejected_filing_file_callback`（L428）→ `store_rejected_filing_file`（L451）
     （`persist_rejected_filing_artifact` L179）；metadata 写为
     `upsert_downloaded_filing_source_document`（`sec_download_source_upsert.py:57`）与
     `upsert_rejected_filing_artifact`（`_fs_maintenance_core.py:154`）。
  2. CN filing：`run_cn_download_stream_impl`（`cn_download_workflow.py:41`，
     `CnDownloadWorkflowHost` `cn_download_protocols.py:123`）per-ticker 循环
     （L259-264）→ `run_cn_download_single_filing_stream`（`cn_download_filing_workflow.py:83`）
     → `store_file`（L314/414/428）；metadata 写为
     `update_cn_staging_source_document`/`commit_cn_filing_source_document`
     （`cn_download_source_upsert.py:124,191`）。
  3. Docling upload：`DoclingUploadService.execute_upload`（`docling_upload_service.py`，
     ctor L98）→ `store_file`（L225）→ `_upsert_source_document`（L271）。
  4. Tool snapshot：`export_tool_snapshot`（`tool_snapshot_export.py:516`）→
     `_write_tool_snapshot_file`（L1503）→ `repository.store_file(processed_handle, ...)`；
     调用点 `sec_pipeline.py:1784`/`cn_pipeline.py:1538`。
  5. Rejected rescue：`rescue_rejected_6k_filings`（`rejected_6k_rescue.py:80`）→
     `_copy_rejected_files_to_active_source`（L546）→ `store_file`（L580）+ source upsert。
  6. Rejected retriage：`retriage_active_6k_filings`（`active_6k_retriage.py:83`）→
     `_archive_active_filing_as_rejected`（L395）→ `store_rejected_filing_file`（L431）+
     `upsert_rejected_filing_artifact`（L459）。
  rescue/retriage 仅被 `utils/` 脚本调用（`utils/rescue_rejected_6k_filings.py`、
  `utils/retriage_active_6k_filings.py`）。
- **batch 语义事实**：`FsBatchingRepository`（`fs_batching_repository.py:15-24`）已实现
  `begin_batch`/`commit_batch`/`rollback_batch`/`recover_orphan_batches`，构造器接受
  `repository_set` 并复用同一 core；`_execute_with_auto_batch`（`_fs_storage_infra.py:295-335`）
  无 active token 时自动 begin（L318-320）；`begin_batch` 对已 active ticker 抛
  RuntimeError（L149-153）；`BatchingRepositoryProtocol`（`repository_protocols.py:40-57`）
  与 `DocumentBlobRepositoryProtocol`（L224-254，无 batch 方法）协议层分离。
- **destructive inventory 事实**：`_upsert_processed`（`_fs_processed_core.py:258-351`）
  在 `financials is None` 且旧文件存在时执行 `financials_path.unlink()`（L289-296），
  `merged_meta` **不含 `files` inventory**；source meta 在
  `_fs_source_document_core.py:735` 写入 `merged_meta["files"] = file_payloads`。
- **startup 事实**：`prepare_host_runtime_dependencies`（`startup_preparation.py:469`）当前
  `DefaultFinsRuntime.create` 调用点 L553（无 repository_set 实参）；`PreparedHostRuntimeDependencies`
  （L114-163）持有 `_owned_platform_lifecycle`；`_OwnedLifecycleRegistration`（L340-414）
  exact-once atexit。
- **toolset 注册真源**：`dayu/config/toolset_registrars.json` 的 exact key 为
  `utils/doc/web/fins/ingestion`，其中 `fins`/`ingestion` 指向
  `dayu.fins.toolset_registrars.*`；`scene_preparer.py:747-784` `_build_tool_registry`
  当前按配置 import path 判断 Fins-owned toolset。

## 唯一化契约（master plan S14-CTRL-04/05/08/10/11/12/13 修订）

### A. 同-core BatchToken 传播（S14-CTRL-12，闭合 Terra S14-REREVIEW-01）

1. `DefaultFinsRuntime` 从 `create()` 内同一 `_FsRepositorySet` 构造并持有**唯一
   `FsBatchingRepository`**（复用现有 `fs_batching_repository.py`，同一 core/同一
   `_active_batches` token 空间）；新字段 `batching_repository: BatchingRepositoryProtocol`。
2. 逐层显式传递：`_build_pipeline_for_ticker`（service_runtime.py:1874-1887）→ 模块级
   `_build_pipeline`（797-808）→ `get_pipeline_from_normalized_ticker`
   （factory.py:54-95）→ `SecPipeline`/`CnPipeline` 构造器，各新增 keyword-only
   `batching_repository`；`SecPipeline.__init__`/`CnPipeline.__init__` 持有
   `self._batching_repository`，且**注入路径不再无条件 `build_fs_repository_set` 建第二
   core**（现 sec:327/cn:147 改为仅当注入仓储全为 `None` 且无 batching 时自建）。
3. host protocols：`SecDownloadWorkflowHost`（sec_download_workflow.py:42）与
   `CnDownloadWorkflowHost`（cn_download_protocols.py:123）新增 `batching_repository`
   property；`run_download_stream_impl`/`run_cn_download_stream_impl` 在 per-ticker 循环
   外层显式 begin/commit/rollback；`run_cn_download_single_filing_stream`
   （cn_download_filing_workflow.py:83）新增 keyword-only `batching_repository`（由
   cn_download_workflow.py:259-264 传入同一实例）并复用 active token（禁止 per-filing
   嵌套 begin——`begin_batch` 对 active ticker 抛 RuntimeError）。七条 producer 逐条
   列出（SEC active、SEC rejected[与 active 共享同一 per-ticker batch]、CN filing、
   Docling upload、tool snapshot、rejected rescue、rejected retriage），各自显式
   begin/commit/rollback。
4. `DoclingUploadService`（构造点 sec:352-355/cn:180-183）新增构造参数
   `batching_repository`，`execute_upload` per-document 显式 begin/commit/rollback；
   `export_tool_snapshot`（tool_snapshot_export.py:516）新增 keyword-only
   `batching_repository`，per-document 显式 begin/commit/rollback；
   `rescue_rejected_6k_filings`/`retriage_active_6k_filings` 各新增 keyword-only
   `batching_repository`，per-ticker 显式 begin/commit/rollback。
5. Host/Agent 只见 Services/Toolset，不见 repository/core；`FinsToolService`
   （service.py:130-138）不持有 batching；不发明 Host 侧 wrapper、全局缓存、第二事务 API。
6. allowlist 精确展开：`service_runtime.py`、`pipelines/factory.py`、`sec_pipeline.py`、
   `cn_pipeline.py`、`sec_download_workflow.py`、`sec_download_filing_workflow.py`、
   `cn_download_workflow.py`、`cn_download_filing_workflow.py`、`cn_download_protocols.py`、
   `sec_download_persistence.py`、`sec_download_source_upsert.py`（只读引用 metadata 写点）、
   `docling_upload_service.py`、`tool_snapshot_export.py`、`rejected_6k_rescue.py`、
   `active_6k_retriage.py`、`storage/fs_batching_repository.py` 及其测试
   （`tests/fins/test_runtime_batch_injection.py` 等，见 master plan Allowed）。

### B. runtime/startup 唯一所有权（S14-CTRL-05，闭合 Terra S14-REREVIEW-02）

1. `DefaultFinsRuntime.create()` 只接受 `repository_set: _FsRepositorySet | None = None`
   可选 keyword-only（+ 既有 `cn_download_pdf_gate`），**不新增、不接受 `file_store`**；
   `repository_set is None` 时内部按现状自建 FS set。
2. startup 唯一调用：先 `build_fs_repository_set(workspace_root, file_store=s3_store)`
   （触发 `ensure_batch_recovery` 一次），再只调
   `DefaultFinsRuntime.create(workspace_root, repository_set=repository_set, ...)`；
   绝不双参同传；runtime 内部不重复 recovery。
3. `build_fs_repository_set` 保留 `file_store`/`repository_set` 两参数，同时非 `None` 抛
   `ValueError`（改掉当前"repository_set 存在即提前返回、静默忽略 file_store"）。
4. `PreparedHostRuntimeDependencies` 独占并关闭 S3 store（`_owned_s3_store`）与 writer
   lease（`_owned_writer_lease`），runtime 不重复 close。
5. startup unit 精确锁定：`create()` 收到的 keyword 实参集合恰为 `repository_set`
   （+`cn_download_pdf_gate`）、无 `file_store` 实参；`ensure_batch_recovery` 只执行一次；
   runtime 5 窄仓储与 `batching_repository` 引用同一 `repository_set`；`close()` 只关闭
   唯一 S3 store/lease owner（exact-once）。

### C. destructive inventory contraction（S14-CTRL-13，闭合 Terra S14-REREVIEW-03）

1. **processed meta 显式持久化 authoritative files inventory**：`_upsert_processed`
   的 `merged_meta` 写入稳定 `files` 清单（sections/tables/financials 及期望 sha/size），
   不再依赖"缺 files 即缺文件"的隐式形状。
2. **所有改变 blob inventory 的 metadata mutation**（processed `financials` present→None、
   source file-list shrink）比较 old/new authoritative inventory，在 local metadata swap
   前把 removed targets journal 为 `action=delete` delete intents；metadata-first commit
   后 remote delete 幂等重放；**任何路径禁止先删 remote、禁止全前缀扫删**。
3. 测试：`tests/fins/test_destructive_inventory_contraction.py` 覆盖 `financials` 有→无、
   source files shrink、crash at head/staging/metadata swap/post-delete、重启 recovery
   收敛；MinIO fault matrix 同（S14-CTRL-08）。

### D. S3 batch admission（S14-CTRL-12，闭合 MiM F-01）

1. `_execute_with_auto_batch`（`_fs_storage_infra.py:295-335`）：**FS/local 模式保留现有
   auto-begin**；**S3 模式（`isinstance(self._file_store, _StagedFileStore)`）且该 ticker
   无 active BatchToken 时稳定抛 `s3_write_requires_batch`，禁止自动 begin/commit**；
   已有同-core active token 才复用（现 L318-320 复用分支保留）。
2. 模式判定用 `@runtime_checkable` 私有 Protocol + `isinstance`（S14-CTRL-06 同一判定），
   不靠隐式 FileStore 类型猜测或 `getattr`/`hasattr` 动态属性。
3. 测试：`tests/fins/test_batch_mode_admission.py`（FS 无 token auto-begin 保留；S3 无
   token fail-loud 且零 begin/commit 副作用；S3 有同-core token 复用一个 token 对象）。

### E. Fins-owned toolset exact name fail-closed（S14-CTRL-11，Controller 额外精确化）

1. 模块级 frozen 常量 `_FINS_OWNED_TOOLSET_NAMES = frozenset({"fins", "ingestion"})`
   （注册真源 `dayu/config/toolset_registrars.json` 的 exact key）。
2. `_build_tool_registry` 对启用 toolset：**name ∈ `_FINS_OWNED_TOOLSET_NAMES` 且
   override 缺失 => 抛 `fins_toolset_override_required` fail closed，绝不回退配置 path**；
   判定只比较 exact toolset name，**不再用 import-path prefix**——workspace 把
   `fins`/`ingestion` 映射到任意 alternate import path 仍必须 fail-closed。
3. 测试：`tests/application/test_scene_execution.py` 追加 alternate import path 仍
   fail-closed 用例。

## 逐 ID 处置汇总

| Finding | 严重程度 | 处置 | 闭合位置 |
| --- | --- | --- | --- |
| Terra S14-REREVIEW-01 | High | **CLOSED-IN-PLAN** | S14-CTRL-12（A：同-core 唯一 `FsBatchingRepository` + 真实 callgraph 逐层传递 + host protocols + 七条 producer 边界；allowlist 展开） |
| Terra S14-REREVIEW-02 | High | **CLOSED-IN-PLAN** | S14-CTRL-05（B：startup 先 build repository_set 再只传 `repository_set`；`create` 不接 `file_store`；唯一 close owner） |
| Terra S14-REREVIEW-03 | Medium | **CLOSED-IN-PLAN** | S14-CTRL-13（C：inventory diff + processed files inventory + 每 phase kill 测试） |
| MiM F-01 | Medium | **CLOSED-IN-PLAN** | S14-CTRL-12（D：`_execute_with_auto_batch` S3 fail-loud，FS 保留 auto-begin） |

逐 ID 均无 **RE-REVIEW-REQUIRED**；最终闭合仍以 Terra + MiM Native 双路 **final closure
plan re-review** PASS 且 open H/M/L=`0/0/0` 为 gate。原 round 1/2/3 裁决（Terra
S14-01..04、MiM M1..M5、Terra S14-FINAL-01..04、MiM MR1/MR2、MR3）保持历史不变。

## 校验

- `git diff --check` 通过；修改的五份文档（master plan、codex fix、corrective fix、
  final corrective fix、本 artifact）trailing whitespace 为零、final LF 齐全。
- 未修改 production/tests/README/dependencies；六份 source review（204331/204201/211302/
  211155/213617/213634）保持只读。
- master plan 状态：**SLICE 1.4 REVIEW OBSERVATIONS FIXED / AWAITING FINAL CLOSURE DUAL
  PLAN RE-REVIEW**（round 5 final closure corrective 后置
  **AWAITING FINAL CORRECTIVE DUAL PLAN RE-REVIEW**，见下）。
- finding completeness：Terra 213617 三项与 MiM 213634 F-01 全部 **CLOSED-IN-PLAN**
  （分别闭合于 S14-CTRL-12/05/13/12），原 findings 保持历史。

## Final closure corrective 补充（round 5：Terra final-closure S14-CLOSURE-01/02 + MiM Native 220137）

final closure corrective re-review 新增 findings（Terra
`docs/reviews/plan-final-closure-rereview-20260810-slice-1.4-terra.md`
S14-CLOSURE-01/02，2H；MiM Native
`docs/reviews/plan-final-closure-rereview-20260810-slice-1.4-mimo-native.md`
PASS/open0 记录为证据）由
`docs/reviews/plan-fix-20260810-slice-1.4-final-closure-corrective-deepseek.md` 详细
展开，全部唯一化进 master plan S14-CTRL-12/13：

- **S14-CLOSURE-01（Host ingestion factory 同-core propagation）**：真实 Host
  `ingestion` toolset 走 `DefaultFinsRuntime.build_ingestion_service_factory()`
  （`service_runtime.py:2497-2508`）而非 `_build_pipeline_for_ticker`；唯一链固定为
  `DefaultFinsRuntime.batching_repository` → `build_ingestion_service_factory(...
  batching_repository=self.batching_repository)` → `dayu.fins.ingestion.factory.
  build_ingestion_service_factory`（`ingestion/factory.py:30-39` 新增 keyword-only，
  闭包 `:78-101` 透传）→ `build_ingestion_service_from_normalized_ticker`
  （`pipelines/factory.py:116-126` 新增 keyword-only）→
  `get_pipeline_from_normalized_ticker`（`pipelines/factory.py:54-65` 新增
  keyword-only）→ `SecPipeline`/`CnPipeline` 同一实例/同一 `_FsRepositorySet`/core；
  `FinsRuntimeProtocol.build_ingestion_service_factory` 与
  `IngestionServiceFactory = Callable[[str], FinsIngestionService]` 签名不变，
  Host/Agent/tool contract 不见 repository/core；禁第二 `FsBatchingRepository`、
  global cache、wrapper；`dayu/fins/ingestion/factory.py` 加入 allowlist；
  `test_runtime_batch_injection.py` 扩展 runtime direct pipeline 与 ingestion factory
  的 US/CN 同实例、真实 Host ingestion scene 至少一条写 producer 证明同-core、零
  无-token admission。
- **S14-CLOSURE-02（S3 fail-loud 全 mutation 最小 explicit boundary）**：不只围住七条
  `store_file` producer，S14-CTRL-12 逐名列出：SEC company upsert
  （`sec_download_workflow.py:371-376`）、SEC/CN overwrite filing clear
  （`:378-379`/`cn_download_workflow.py:224`）、SEC stale filing cleanup
  （`:475`）、CN company upsert（`cn_download_workflow.py:201-206`）、source reset
  （`cn_download_filing_workflow.py:159,292`、`docling_upload_service.py:969`）、
  processed clear（`sec_process_workflow.py:328`、`cn_pipeline.py:989`）、SEC/CN
  snapshot pre-cleanup+export（boundary 上移到
  `_export_tool_snapshot_for_document` `sec_pipeline.py:1754`/`cn_pipeline.py:1502`，
  一次覆盖 `_cleanup_processed_snapshot_dir` + `export_tool_snapshot`，export 内不得
  再创建第二 batch、有 active same-core token 时复用）。每段 metadata/delete-only
  mutation 用同一 runtime batching_repository 最小 begin/commit/rollback、异常
  rollback、禁止跨网络下载长期持有 token；blob+metadata 保持既有 per-filing/
  per-document 边界；S3 不恢复 auto-begin、FS/local 现有行为不变；S14-CTRL-13 继续
  metadata-first delete/journal/recovery，不得 prefix sweep；`dayu/fins/pipelines/
  sec_process_workflow.py` 加入 allowlist；S14-CTRL-08 test matrix/stop conditions
  与 S14-CTRL-10 disposition 同步（workflow mutation boundary 测试断言每个 mutator
  已有 same-core token、delete intent ordering、operation/commit 异常与 restart、零
  S3 auto-begin）。

S14-CLOSURE-01/02 全部 **CLOSED-IN-PLAN**（S14-CTRL-12/13）；master plan 状态置
**REVIEW OBSERVATIONS FIXED / AWAITING FINAL CORRECTIVE DUAL PLAN RE-REVIEW**；两份
final closure corrective source review 保持只读。最终 gate 为 Terra + MiM Native 双路
**final corrective plan re-review** PASS 且 open H/M/L=`0/0/0`。

## Terminal corrective 补充（round 6：Terra S14-CORRECTIVE-01/02 + MiM Native final-corrective rereview）

terminal corrective re-review 新增 findings（Terra
`plan-final-corrective-rereview-20260810-slice-1.4-terra.md` S14-CORRECTIVE-01/02，2H；
MiM Native `plan-final-corrective-rereview-20260810-slice-1.4-mimo-native.md`
PASS/open0 记录为证据，不覆盖 Terra 直接反例）由
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
corrective source review 保持只读。最终 gate 为 Terra + MiM Native 双路 **terminal
plan re-review** PASS 且 open H/M/L=`0/0/0`。


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
