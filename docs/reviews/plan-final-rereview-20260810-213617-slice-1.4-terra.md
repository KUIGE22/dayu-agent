# Slice 1.4 final corrective plan re-review（Terra）

## 审查目标与范围

- **本机时间**：2026-08-10 21:36:17（Asia/Shanghai）
- **基线**：`5d7e6bb`；分支：`codex/investment-platform`
- **审查目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 的 Slice 1.4，尤其 S14-CTRL-01..13；并复核 final corrective fix `docs/reviews/plan-fix-20260810-slice-1.4-final-corrective-deepseek.md`。
- **已读前序材料**：Terra `plan-review-20260810-211302.md`（S14-FINAL-01..04）与 MiM `plan-review-20260810-211155-slice-1.4-s3-blob-repository-mimo-native.md`，以及前序 corrective fix/source review。
- **代码事实范围**：Host scene registrar callgraph、`prepare_host_runtime_dependencies`、`DefaultFinsRuntime.create`、`build_fs_repository_set`、全部生产 `store_file`/`store_rejected_filing_file` 调用点、FS batch/core、processed/source/maintenance 的删除路径及 `FileStore`/`Source` 公共协议。
- **边界**：只读；未修改 plan、fix、source review、代码、测试、README 或依赖；未安装、pull、联网、运行 MinIO/live/model/broker；未 commit/push/PR。

## 已验证的 assumptions

| 假设 | 直接证据与结论 |
| --- | --- |
| S14-FINAL-01 可由 S14-CTRL-11 真实闭合 | **已闭合（针对当前 production 配置）**。当前实际路径是 `DefaultScenePreparer._build_tool_registry`（`dayu/host/scene_preparer.py:758-783`）按 `dayu/config/toolset_registrars.json:5-6` 导入 `dayu.fins.toolset_registrars.*`；当前 registrar 的 `_get_cached_fins_runtime`（`dayu/fins/toolset_registrars.py:16-30`）确实是唯一绕过点。CTRL-11 删除该缓存，以 runtime-bound override 优先、Fins import-path 缺 override fail-closed，并仅让 Service startup（`startup_preparation.py:553-562`）构造映射；Host/contracts 只依赖 `ToolsetRegistrarProtocol`。这保持 Host/contracts 零 Fins import、没有 module-global FS runtime 或恢复旁路，且 real Host black-box 已要求断言 read/ingestion/process/evidence 同一 core/store/lease。 |
| S14-FINAL-02 可由 S14-CTRL-12 真实闭合 | **未闭合，见 H-01**。生产代码中仅有七条直接写 producer，计划列举完整；但当前传参图没有能把同一 core 的 `BatchingRepositoryProtocol` 传到它们的授权改动，不能获得 active token。 |
| S14-FINAL-03 可由 S14-CTRL-13 真实闭合 | **部分闭合，仍有 M-01**。`action=publish|delete`、head → metadata swap → post-commit delete、missing/drift/restart 的主状态机足以修正原 review 所列 reset/clear/delete 方向；但计划没有覆盖实际 processed 更新中的文件移除与文件清单收缩，因而不能证明“所有真实 destructive paths”或无 remote drift。 |
| S14-FINAL-04 可由 S14-CTRL-06 真实闭合 | **已闭合**。CTRL-06 已把 `FileStore.get_object` 与 `Source.open` 的 caller-owned、seekable、可重读和 `FileNotFoundError`/`OSError` 共同语义明确纳入这两个允许修改的公共 docstring；S3 checksum/StreamingBody close 明确限于 concrete adapter，不向 Local 虚构远端元数据契约。 |
| S3 生产装配可在同一 repository/core/token 空间中启动 | **未闭合，见 H-02**。CTRL-05 的参数互斥契约与其 own startup call 相互矛盾。 |
| producer 清单与嵌套 auto-batch 语义 | `rg` 生产源码确认直接 public 写入恰为七组：SEC active、SEC rejected、CN filing、Docling upload、tool snapshot、rejected rescue、rejected retriage（落点分别在 `sec_download_persistence.py:425,451`、`cn_download_filing_workflow.py:314,414,428`、`docling_upload_service.py:225`、`tool_snapshot_export.py:1513`、`rejected_6k_rescue.py:580`、`active_6k_retriage.py:431`；SEC active 的 callback 最终由 `sec_downloader.py:1250,1269` 调用）。`_execute_with_auto_batch`（`_fs_storage_infra.py:295-335`）只会在**已有同一 core** 的 `_active_batches` 中复用 token；无共享 core/token 时它必然另开 batch，不能补救 H-01。 |

## Findings

### S14-REREVIEW-01-未修复-[高]-S14-CTRL-12 没有可实施的同-core BatchToken 传播路径，且 allowlist 排除了必经编排点

- **位置**: S14-CTRL-12 的“每个 producer 在最高原子边界显式 begin → blob → metadata → commit”与 Slice 1.4 Allowed 清单。
- **问题类型**: 不可直接实施 / 架构边界 / 状态机漏洞 / 测试缺口。
- **当前写法**: 计划要求复用 `BatchingRepositoryProtocol`，并宣称七个 producer 的 top-level entry 可接收共享 core 的 batch capability；`store_file` 无 active explicit token 时 fail-closed。
- **反例/失败场景**: production S3 执行 SEC/CN 下载、Docling upload 或 snapshot。producer 当前仅收到窄 `DocumentBlobRepositoryProtocol`、source/processed/maintenance repositories；它们没有 `begin_batch`。若 producer 自建 `FsBatchingRepository(workspace_root)`，将得到独立 `_FsRepositorySet`/`_active_batches`，`store_file` 看不到那个 token；若改用 auto-batch，则 blob 与随后 metadata 各自提交，重新出现 FINAL-02 的 publish-before-meta crash window。
- **为什么有问题**: 当前 `DefaultFinsRuntime` 没有 batching repository 字段，`_build_pipeline`（`dayu/fins/service_runtime.py:797-821`）也不传递 batch capability；`FsBatchingRepository` 虽存在（`dayu/fins/storage/fs_batching_repository.py:15-64`），但仅可通过共享 `_FsRepositorySet` 才与窄仓储同 token 空间。实际长期编排入口在 `dayu/fins/pipelines/sec_pipeline.py` 与 `cn_pipeline.py`（各自构造 `DoclingUploadService` 于 `:352-355`、`:180-183`，并调用 snapshot export 于 `:1784`、`:1538`），CN 下载还须经 `cn_download_workflow.py:259-264` 把 capability 传入 `run_cn_download_single_filing_stream`。这些必经文件都不在 Allowed；仅修改列出的七个 producer 和 `service_runtime.py` 无法在不访问 concrete 私有字段、不新增第二 core 或改变未授权调用边界的条件下闭合。
- **直接证据**: `_execute_with_auto_batch` 只检查 `self._active_batches`（`_fs_storage_infra.py:318-334`）；`build_fs_repository_set` 当前每次无传入 set 都新建 `FsStorageCore`（`_fs_repository_factory.py:24-53`）；`DocumentBlobRepositoryProtocol` 仅定义 blob 方法（`repository_protocols.py:225-253`），没有 batch API。前序 Terra FINAL-02 指出的 Docling/snapshot 调用链仍由这些同一 pipeline 编排点持有。
- **影响**: S3 无 active token 的 fail-closed 会使真实生产 ingestion/process 路径不可用；放松它则恢复 metadata/hash drift、crash 后无可靠 journal 的高风险。每 producer 的 MinIO kill matrix 无法证明不存在该问题。
- **建议改法和验证点**: 先唯一确定 batch capability 的 Fins 内部注入边界：由 `DefaultFinsRuntime` 从同一 `_FsRepositorySet` 构造并持有一个 `FsBatchingRepository`，再经 `_build_pipeline`、SEC/CN pipeline、download workflow、`DoclingUploadService`、snapshot export/rescue/retriage 的实际 top-level callgraph 显式传递；将所有必经生产与对应测试模块加入 allowlist。每条 producer 链须断言 batch repository、blob/source/processed/maintenance 四者同一 core，并覆盖 nested auto-batch、operation exception rollback、commit exception 与无 token 的 S3 fail-closed。
- **修复风险（低/中/高）**: 中；边界应留在 Fins 内部，不能让 Host/Agent 接触 repository/core。
- **严重程度（低/中/高/严重）**: 高。

### S14-REREVIEW-02-未修复-[高]-S14-CTRL-05 对 runtime 参数互斥的规定与其固定 startup 步骤互相矛盾

- **位置**: S14-CTRL-05 首段及步骤 10；S14-CTRL-12 末段。
- **问题类型**: 契约缺失 / 不可直接实施 / startup-lifecycle 风险。
- **当前写法**: CTRL-05 和 CTRL-12 都规定 `DefaultFinsRuntime.create(file_store=..., repository_set=...)` 的两个参数“同时非 None 抛 `ValueError`”；但 CTRL-05 首段又要求先 `build_fs_repository_set(..., file_store=s3store)` 后“把同一 `file_store`+`repository_set` 传入 create”，步骤 10 也明确写作 `create(workspace_root, file_store=..., repository_set=...)`。
- **反例/失败场景**: production S3 admission 已成功并已获得 writer lease/recovery 后，严格按计划调用 `create`；它必须抛 `ValueError`。若 implementation 为完成 startup 而悄悄忽略一个参数，则违反“唯一参数/互斥”真源，且无法由 API 保证传入 repository_set 的实际 FileStore 与 startup 负责关闭的 store 是同一实例。
- **为什么有问题**: 这是同一 Slice 的明确互斥 API 与唯一启动顺序的直接矛盾，不是实现细节。它阻断 startup 唯一 runtime、writer lease 生命周期、Host override 和 MinIO startup 测试的可执行性。
- **直接证据**: master plan S14-CTRL-05 的首个 bullet 与步骤 10，及 S14-CTRL-12 最后一 bullet；当前 `DefaultFinsRuntime.create` 仅构造一个 `repository_set`（`service_runtime.py:1890-1933`），`build_fs_repository_set` 当前也在 `repository_set is not None` 时直接 return（`_fs_repository_factory.py:46-47`），所以不存在可从当前行为推导出的隐式一致性校验。
- **影响**: S3 startup 无法同时满足计划契约；测试只能选择一边通过，无法证明 repository/store/lease 的唯一 ownership。
- **建议改法和验证点**: 选择唯一调用：startup 预构造 S3-backed `repository_set` 后，只向 `DefaultFinsRuntime.create(..., repository_set=repository_set)` 传该参数；`file_store` 仅用于构造 set 并由 `PreparedHostRuntimeDependencies` 持有/关闭。若需防错，`repository_set` 在 Fins storage 私有边界暴露受控一致性校验，不再让两个同义 owner 同时进入 public factory。startup unit 应精确断言 create 的实参、只有一次 recovery、runtime 所有窄仓储共享该 set，且 close 关闭同一 S3 store/lease。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 高。

### S14-REREVIEW-03-未修复-[中]-destructive state machine 未覆盖 processed 更新的文件移除，`meta.files` 前提也未为 processed 建立

- **位置**: S14-CTRL-03 processed JSON 路径、S14-CTRL-13 destructive 清单及 S14-CTRL-08 destructive fault matrix。
- **问题类型**: 状态机漏洞 / 远端漂移 / 测试缺口。
- **当前写法**: 计划将 `sections/tables/financials` 改为 FileStore bytes，却把 delete intent 仅规定为 reset/delete/clear/stale cleanup 中“从 `meta.files` 枚举”；S14-CTRL-13 未列 `update_processed` 的旧文件移除。
- **反例/失败场景**: 已有 XBRL 的 processed document 被更新为 `financials is None`。现实现 `_upsert_processed` 会在同一 metadata update 路径执行 `financials_path.unlink()`（`dayu/fins/storage/_fs_processed_core.py:289-296`），再写 `has_xbrl=False` 的 meta（`:299-351`）。S3 化后若没有 delete target，旧 `processed/.../financials.json` 永久残留；若实现者直接删 S3，又重现 metadata-first 前的不可恢复窗口。当前 processed meta 的构造也没有写入 `files` inventory（同段 `merged_meta` 字段），不能按 CTRL-13 的 `meta.files` 规则发现该对象。
- **为什么有问题**: 这是从现有写入路径必然迁移出的真实 destructive branch，而非清理偏好。它违反 S3 authoritative bytes 下的无 remote drift 要求；同类 source metadata replacement 也可改变 `files` 集合，计划没有定义 old/new file inventory diff 如何转为 delete target。
- **直接证据**: `_fs_processed_core.py:256-351` 的直接文件写/删与 `meta` 构造；S14-CTRL-13 只列 `delete_entry`、reset、processed delete/clear、filing clear/stale cleanup。S14-CTRL-08 的 destructive matrix 同样未包含 processed update removing `financials` 或 metadata file-set contraction。
- **影响**: 未引用 S3 bytes 长期残留，可能造成成本、保留期与敏感财报数据治理问题；若临时修复为先删，会产生 FINAL-03 所禁止的悬挂 metadata。
- **建议改法和验证点**: 在每个 metadata mutation 的 staging 版本中比较旧/新 authoritative file inventory，把移除项以 `action=delete` 记录进同一 journal；processed 应明确持久化 inventory（或明确、受控地从 deterministic schema keys 构造 inventory，不能全前缀扫描）。加入 `financials` 有→无、source file-list 收缩、crash 在 head/FS swap/post-delete 的 unit 与 MinIO restart tests，验证 post-commit cleanup 可重试且无先删 remote。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。

## 显式审查 lenses

- **Architecture boundary**：CTRL-11 的 Service→Fins runtime-bound override 保持 Host/contracts 不 import Fins，是正确且最小的闭合；H-01 所需补线也应限在 Fins runtime/pipeline，不可把 batch/core 泄漏给 Host/Agent。
- **Best practice**：per-target journal、metadata-first delete、HEAD-only stat、原子 journal、single-writer lease 和 real fault matrix 的方向正确；但 H-01/H-02 使核心事务和 startup 契约目前不能按该最佳实践运行。
- **Optimal solution**：不需要引入第二事务 API、CAS、multipart 或第二 metadata repository。用已有 `BatchingRepositoryProtocol` 是最优路径，前提是把它从同一 repository set 沿真实调用图显式传递。
- **Overengineering**：未发现计划要求的 S3 journal、private staged capability、lease 或 override 为无需求抽象；它们均有直接 failure mode 支撑。
- **Overcoupling**：H-01 不是要求 Host 与 Fins 耦合，恰恰相反：遗漏的 Fins 内部编排 wiring 使实现者只能选择 concrete-private access 或另建 core。以一个 Fins-internal batch dependency 明确传递，可消除这种错误耦合。

## Open questions

无。三个问题均由当前源码调用图与计划文本的直接矛盾/遗漏证明，不依赖 MinIO 或外部状态。

## Residual risks

- 本次未运行 resolver、pyright、MinIO、故障注入、coverage 或 Docker；这些仍是纠正后必须执行的实现 gate，不能用于消除上述开放 finding。
- CTRL-11 的 fail-closed 判断目前以 registrar import-path 的 `dayu.fins.*` 前缀识别 Fins-owned toolset。当前 production config 确实满足该条件；若未来允许 workspace config 将 `fins`/`ingestion` 映射到其它 path，应把该 ownership 规则提升为明确的受保护 toolset-name 契约，并追加测试。

## Conclusion

**FAIL**。

Open H/M/L：**2 / 1 / 0**。

S14-FINAL-01 与 S14-FINAL-04 已由 CTRL-11/06 真实闭合；S14-FINAL-02 因 H-01 仍未闭合，S14-FINAL-03 因 M-01 仍未完全闭合，且 H-02 另行阻断唯一 S3 startup/runtime 契约。未满足“PASS 且 open=0”，Slice 1.4 不得恢复 implementation gate。
