# Slice 1.4 S3 Fins blob repository final corrective plan fix（DeepSeek worker）

- **Worker**：DeepSeek Flash fix worker
- **日期**：2026-08-10
- **基线**：`5d7e6bb`（branch `codex/investment-platform`，HEAD/worktree 冻结为只读审计）
- **状态**：**SLICE 1.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **任务范围**：只修 master plan Slice 1.4
  （`docs/plans/2026-08-10-investment-platform-restoration.md`）与两份既有 fix artifacts
  （`plan-fix-20260810-slice-1.4-s3-blob-repository-codex.md`、
  `plan-fix-20260810-slice-1.4-s3-blob-repository-corrective-deepseek.md`）；新增本
  artifact 与 final closure artifact
  `docs/reviews/plan-fix-20260810-slice-1.4-final-closure-deepseek.md`；
  production/tests/README/dependencies 全部冻结；未安装依赖、未 pull 镜像、
  未运行 live/network/model/broker、未 commit/push/PR。
- **Controller fix**：`docs/reviews/plan-fix-20260810-slice-1.4-s3-blob-repository-codex.md`
- **Final source reviews（只读）**：
  `docs/reviews/plan-review-20260810-211302.md`（Terra，FAIL，S14-FINAL-01..04，3H/1M）、
  `docs/reviews/plan-review-20260810-211155-slice-1.4-s3-blob-repository-mimo-native.md`
  （MiM Native，PASS-WITH-RISKS，MR1/MR2/MR3）。
- **Final closure source reviews（只读）**：
  `docs/reviews/plan-final-rereview-20260810-213617-slice-1.4-terra.md`
  （Terra，FAIL，S14-REREVIEW-01..03，2H/1M）、
  `docs/reviews/plan-final-rereview-20260810-213634-slice-1.4-mimo-native.md`
  （MiM Native，PASS-WITH-RISKS，F-01 1M）。

## Controller 裁决（final corrective，唯一实现，不留二选一）

- 接受 Terra 211302 全部四项：S14-FINAL-01（Host scene 真实 Fins tool path 绕过注入
  runtime）、S14-FINAL-02（remote journal 未跨越真实 blob 写 + 随后 metadata 写）、
  S14-FINAL-03（delete/reset/cleanup 先删 S3 后删 FS 不可恢复，journal 未建模 delete
  target）、S14-FINAL-04（公共协议文档与“已验证、seekable、caller-owned”不一致）。
- 接受 MiM 211155 MR1（begin_batch copytree 的 S3 模式语义）与 MR2（journal 写入
  原子性）；MR3（staged capability 的 isinstance 类型安全）为 verified non-finding。
- 必须唯一实现以下四项裁决（A–D），全部落进 master plan S14-CTRL-03..13。

## 只读 callgraph 审计（final round，支撑唯一化）

- **Host scene 真实 tool path（S14-FINAL-01 直接证据）**：
  - `dayu/host/scene_preparer.py:747-784` `_build_tool_registry`：只经
    `workspace.config_loader.load_toolset_registrars()`（`dayu/startup/config_loader.py:333`）
    拿 `toolset_registrars.json` 的 import path，`_load_toolset_registrar`（`scene_preparer.py:373`）
    import 后调用；`ToolsetRegistrationContext`（`dayu/contracts/toolset_registrar.py:42-66`）
    只有 workspace/config/permissions，无 Fins runtime 字段。
  - `dayu/fins/toolset_registrars.py:16-30` `_get_cached_fins_runtime`：`@lru_cache`
    模块级缓存，`DefaultFinsRuntime.create(workspace_root=Path(...))`；read/ingestion 两个
    registrar（L46/L73）都以 workspace 路径自建 FS runtime。这是必须删除/禁用的
    production path。
  - Host 装配：`host.py:2068-2111` `_build_default_scene_preparation` → `DefaultScenePreparer`；
    `startup_preparation.py:553` `DefaultFinsRuntime.create`，`startup_preparation.py:562`
    `Host(...)`。`dayu/host/` 当前零 Fins import（可保持）。
- **producer 调用链（S14-FINAL-02 直接证据）**：`store_file`
  （`_fs_blob_core.py:115-151`）与 `store_rejected_filing_file`
  （`_fs_maintenance_core.py:114-152`）直连 `file_store.put_object`，不进入 batch、无
  token；`_execute_with_auto_batch`（`_fs_storage_infra.py:295-335`）在已有 active batch
  时复用（L318）。真实 producer 见下文“S14-CTRL-12 的七条调用链”。
- **destructive 路径（S14-FINAL-03 直接证据）**：`delete_entry`/`_delete_entry_impl`
  （`_fs_blob_core.py:70,92`）、`_reset_source_document_impl`（`_fs_source_document_core.py:504`）、
  `_delete_processed_impl`/`_clear_processed_documents_impl`（`_fs_processed_core.py:96,233`）、
  `_clear_filing_documents_impl`/`_cleanup_stale_filing_documents_impl`
  （`_fs_maintenance_core.py:330,383`）全部是本地 rmtree/unlink，包裹在 auto-batch 内；
  现有 remote journal 只有 publish target，无 delete intent。
- **协议与细节（S14-FINAL-04 / MR1 / MR2 / MR3 直接证据）**：
  - `FileStore.get_object`（`file_store.py:38-51`）与 `Source.open`
    （`dayu/engine/processors/source.py:42-55`）的 docstring 无 owner/seekable/close/
    读取异常共同语义；checksum 契约只可能由 S3 concrete adapter 持有。
  - `begin_batch`（`_fs_storage_infra.py:190`）`shutil.copytree(target_ticker_dir,
    staging_ticker_dir)`；S3 模式下本地 ticker dir 只有 metadata（blob 在 S3）。
  - `_write_json`（`_fs_storage_utils.py:439-463`）当前实现本身已是 same-dir
    temp+flush+fsync+`os.replace`+dir-fsync 原子写；本裁决仍要求 remote_op_journal 使用
    独立 atomic JSON helper（不复用 `_write_json`，保持 journal 路径自包含）。
  - staged capability 分发点 `_fs_storage_infra.py:827-842` `_build_file_store`；
    `@runtime_checkable` 私有 Protocol + `isinstance` 类型安全（MR3 确认）。

## 唯一化契约（S14-CTRL-11/12/13 与 S14-CTRL-04/05/06/08/10 修订）

### A. Host 唯一 runtime（S14-CTRL-11，闭合 Terra S14-FINAL-01）

1. 删除 `dayu/fins/toolset_registrars.py` 的 `_get_cached_fins_runtime`（模块级
   lru_cache）+ 其导入；该模块不再从 workspace 路径自造 runtime。
2. 新增 `build_fins_toolset_registrars(runtime: FinsRuntimeProtocol) ->
   Mapping[str, ToolsetRegistrarProtocol]`：返回只读映射（`MappingProxyType`），键
   `fins`/`ingestion`，值为持有该 runtime 的 typed frozen callable（模块级私有函数 +
   `functools.partial` 绑定，或 frozen dataclass 实现 `__call__`）；无模块级可变状态、
   无 runtime 缓存。闭包逻辑与现 `register_fins_*_toolset` 一致。
3. `DefaultScenePreparer` 新增只读字段 `toolset_registrar_overrides: Mapping[str,
   ToolsetRegistrarProtocol]`；`_build_tool_registry` 按 name 优先用 override，否则才
   load 配置 path；**Fins-owned toolset（配置 path 为 `dayu.fins.*`，即现
   `toolset_registrars.json` 的 `fins`/`ingestion`）启用但 override 缺失 => 抛稳定错误
   `fins_toolset_override_required` fail closed**，绝不回退配置 path 构造本地 runtime。
4. `Host.__init__` 新增 keyword-only `toolset_registrar_overrides`，经
   `_build_default_host_components`/`_build_default_scene_preparation` 透传；
   **Host/contracts 不 import Fins，bucket/key 不越层**。
5. `prepare_host_runtime_dependencies` 在 `DefaultFinsRuntime.create` 后调用
   `build_fins_toolset_registrars(fins_runtime)` 构造 override 传入 `Host`；startup 是
   唯一构造位置。production S3 下缺 override 必须 fail closed，不得回退。
6. allowlist 精确展开：`dayu/fins/toolset_registrars.py`、`dayu/host/scene_preparer.py`、
   `dayu/host/host.py`、`dayu/services/startup_preparation.py`、相关测试
   （`tests/application/test_scene_execution.py`、`tests/application/test_service_startup_preparation.py`、
   `tests/engine/test_cli_running_config.py`）与 README（`dayu/host/README.md`、
   `dayu/README.md`）。
7. 真实 Host scene black-box 测试：S3 模式 startup 装配真实 Host，启用
   `fins`+`ingestion` 的 scene 执行 read/ingestion/process/evidence，断言四条路径都经
   同一 repository_set（同一 core/同一 S3 store），第二 writer 被 lease 拒绝。

### B. Blob + metadata 共同 operation（S14-CTRL-12，闭合 Terra S14-FINAL-02）

1. 复用现有 `BatchingRepositoryProtocol`（`begin_batch`/`commit_batch`/`rollback_batch`），
   不发明第二 public 事务 API。S3 模式 `store_file`/`store_rejected_filing_file` 必须
   已有该 ticker 的 active explicit BatchToken，否则稳定失败 `s3_write_requires_batch`；
   只 stage 远端 target + per-target journal，不 publish。`_execute_with_auto_batch`
   复用 active token（`_fs_storage_infra.py:318`），因此显式 begin 后 blob 写与随后
   source/processed/manifest metadata 更新共享同一 core/token。
2. 真实 producer 在最高原子边界显式 `begin_batch(ticker)` → blob 写 + metadata 写 →
   `commit_batch`，异常 `rollback_batch`。逐一 allowlist 全部 `store_file`/
   `store_rejected_filing_file` 直接 public 调用链（不得漏）：
   - **SEC active filing**：`dayu/fins/pipelines/sec_download_filing_workflow.py`
     （`_build_store_file` L109；调用点 L407/L428）→ `sec_download_persistence.py`
     `build_store_file` L131 → `_store_file_callback` L404 → `store_file` L425；
     `sec_downloader.py` L1250/L1269；随后 `commit_filing_source_document`/
     `update_staging_source_document`。
   - **SEC rejected artifact**：`sec_download_persistence.py` `build_rejected_store_file`
     L151 → `_store_rejected_filing_file_callback` L428 → `store_rejected_filing_file`
     L451；调用方 `persist_rejected_filing_artifact` L179；随后 `upsert_rejected_filing_artifact`。
   - **CN filing**：`dayu/fins/pipelines/cn_download_filing_workflow.py` L314（pdf）、
     L414/L428（docling）`store_file`；随后 `update_cn_staging_source_document` L355、
     `commit_cn_filing_source_document` L447。
   - **Docling upload**：`dayu/fins/pipelines/docling_upload_service.py` L225
     `store_file`；随后 `_upsert_source_document` L271。
   - **Tool snapshot**：`dayu/fins/pipelines/tool_snapshot_export.py` L1513
     `_write_tool_snapshot_file` → `store_file`（processed）；随后 processed meta 更新。
   - **Rejected rescue**：`dayu/fins/rejected_6k_rescue.py` L580
     `_copy_rejected_files_to_active_source` → `store_file`；随后 source upsert。
   - **Rejected retriage**：`dayu/fins/active_6k_retriage.py` L431
     `_archive_active_filing_as_rejected` → `store_rejected_filing_file`；随后
     `upsert_rejected_filing_artifact` L459。
   每个 producer 的 top-level 编排入口接收共享 core 实现的 batch 能力；不允许任何不经
   batch 的直连 `store_file`/`store_rejected_filing_file` 路径。
3. commit 时所有 publish targets verified 后才 FS metadata swap；recovery per-target 规则
   保留（S14-CTRL-04）。每个 producer 必须有真实 MinIO crash 测试：blob 后 kill、
   metadata 前 kill、overwrite 后 kill + restart。
4. `build_fs_repository_set`（`_fs_repository_factory.py:24`）与
   `DefaultFinsRuntime.create` 唯一参数/互斥：`file_store` 与 `repository_set` 同时传抛
   `ValueError`，至多一个非 `None`（都 `None` = 默认 FS）；所有窄仓储共享同一
   `_FsRepositorySet`（同一 core、同一 `_active_batches` token 空间）。

### C. Destructive 状态机（S14-CTRL-13，闭合 Terra S14-FINAL-03）

1. journal target `action` 闭合 `publish|delete`；delete target 记录 `final_key`、
   `expected_sha256`、`expected_size`、`delete_state: pending|remote_deleted`。
2. delete/reset/clear/stale cleanup（S3 模式）在 batch impl 内：对每个要删的
   `meta.files` key 先 head 记录 expected sha/size + delete intent（journal
   `action=delete` target），更新 FS staging metadata（meta.json/manifest 移除引用），
   **此阶段绝不执行远端删除**。涉及：`delete_entry`（`_fs_blob_core.py:70,92`）、
   `reset_source_document`（`_fs_source_document_core.py:504`）、delete/clear processed
   （`_fs_processed_core.py:96,233`）、clear filing/stale cleanup
   （`_fs_maintenance_core.py:311-351,353-437`）。
3. commit 顺序（唯一）：head 验证每个 delete target 的 remote 仍匹配 expected（digest
   drift 或缺失 => FS swap 前 abort fail closed，保留 journal）→ FS metadata swap →
   之后幂等 remote delete（post-commit cleanup）。post-commit delete 失败 => success +
   `cleanup_pending`，startup 重试；commit 后 key 缺失 => 幂等 cleaned（置
   `remote_deleted`）。**任何路径禁止先删 remote**。
4. recovery 逐 action/per-target：delete target 在 metadata_committed => 收敛 remote
   delete（缺失=幂等 cleaned）；仍 staged => 验证匹配后补 swap+delete；drift/缺失 =>
   FAIL CLOSED（保留 journal 供人工恢复）。
5. fault matrix：single delete、reset、processed clear、filing clear/stale cleanup、
   missing/ambiguous delete、每 phase kill（head 记录后/FS swap 前/remote delete 中）。

### D. 协议与细节

1. `FileStore.get_object` 与 engine `Source.open` docstring 只锁跨实现共同语义：
   caller-owned、caller 负责 close、seekable、读取异常（`FileNotFoundError`/`OSError`）；
   checksum 验证是 S3 concrete adapter 契约（写入 `s3_file_store.py` 的 get_object
   docstring），不虚构 Local 相同 remote metadata 验证；`FileStore.list_objects` docstring
   保留。allowlist：`dayu/fins/storage/file_store.py`（get_object + list_objects
   docstring）、`dayu/engine/processors/source.py`（仅 `Source.open` docstring）。
2. S3 模式 `begin_batch` copytree 精确声明只复制 FS metadata/manifest/journal tree（blob
   不在本地）；staging 缺损 => fail closed 保留 journal 供人工恢复，有显式测试，不伪造
   自动重建。
3. remote_op_journal 使用独立 atomic JSON helper（same-dir temp、flush+fsync、
   `os.replace`、parent dir fsync），不复用 `_write_json`；注：`_write_json`
   （`_fs_storage_utils.py:439-463`）当前已原子，不改动它。
4. staged capability 用 `@runtime_checkable` 私有 Protocol + `isinstance`，禁止
   `Any`/`object`/`getattr`/`hasattr`。

## 关键状态机（remote journal，per-target publish/delete）

顶层 `phase` 仅表示 batch/meta 阶段：

```text
staged -> metadata_committed -> cleanup_done
   \--> rolled_back（publish target 只删 staging keys；delete target 无远端副作用）
   metadata_committed + cleanup 失败 -> cleanup_pending（startup recovery 重试）
```

- `action=publish` target 独立携带 `publish_state: staged|final_verified`。
- `action=delete` target 独立携带 `delete_state: pending|remote_deleted`。
- commit：先全部 publish target verified（CopyObject + 原子持久 final_verified），再对
  delete target 逐个 head 验证（drift/缺失 swap 前 abort），然后 FS metadata swap，最后
  post-commit 幂等 remote delete（失败 => cleanup_pending 重试）。绝不先删 remote。
- 恢复（startup `ensure_batch_recovery` 重放，逐 token、逐 target、逐 action）：
  - publish：head final digest+size 匹配 => verified（即使 journal 仍写 staged）；staging
    存在 => 完成发布；staging 缺失 => FAIL CLOSED。
  - delete：metadata_committed => 收敛 remote delete（缺失=幂等 cleaned）；staged =>
    验证匹配后补 swap+delete；drift/缺失 => FAIL CLOSED（保留 journal/远端 objects）。
  - 全部 verified 且 FS batch staging 完整 => metadata roll-forward；FS staging 缺损 =>
    FAIL CLOSED。只删 operation-owned staging keys，禁全前缀扫删，永不删仍被 metadata
    引用的 final key。

## 校验

- `git diff --check` 通过；修改的四份文档（master plan、codex fix、corrective fix、本
  artifact）trailing whitespace 为零、final LF 齐全。
- 未修改 production/tests/README/dependencies；四份 source review 保持只读。
- master plan 状态：**SLICE 1.4 FINAL CORRECTIVE REVIEW OBSERVATIONS FIXED /
  AWAITING FINAL CORRECTIVE DUAL PLAN RE-REVIEW**。
- finding completeness：Terra 211302 四项（S14-FINAL-01..04）与 MiM 211155
  MR1/MR2 全部 **CLOSED-IN-PLAN**（分别闭合于 S14-CTRL-11/12/13/06/04），MR3
  **VERIFIED-NON-FINDING/CLOSED**；原 round 1/2 findings（Terra S14-01..04、MiM M1..M5）
  保持历史。


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
