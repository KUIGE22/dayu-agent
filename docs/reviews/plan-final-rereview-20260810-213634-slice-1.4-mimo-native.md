# Slice 1.4 S3 Fins blob repository final corrective plan re-review（MiM Native）

- **Reviewer**: MiM Native（独立 final corrective plan re-review worker）
- **本机时间**: 2026-08-10 21:36:34 CST
- **基线**: `5d7e6bb`（branch `codex/investment-platform`）
- **Gate**: Slice 1.4 final corrective plan re-review
- **审查目标**: `docs/plans/2026-08-10-investment-platform-restoration.md` Slice 1.4 S14-CTRL-01..13
- **Controller fix**: `docs/reviews/plan-fix-20260810-slice-1.4-s3-blob-repository-codex.md`
- **Corrective fix**: `docs/reviews/plan-fix-20260810-slice-1.4-s3-blob-repository-corrective-deepseek.md`
- **Final corrective fix**: `docs/reviews/plan-fix-20260810-slice-1.4-final-corrective-deepseek.md`
- **Source reviews（只读）**:
  - Terra `plan-review-20260810-204331.md`（FAIL 3H/1M）
  - MiM `plan-review-20260810-204201-slice-1.4-s3-blob-repository-mimo-native.md`（PASS-WITH-RISKS M1-M5）
  - Terra `plan-review-20260810-211302.md`（FAIL S14-FINAL-01..04）
  - MiM `plan-review-20260810-211155-slice-1.4-s3-blob-repository-mimo-native.md`（PASS-WITH-RISKS MR1/MR2/MR3）
- **Output**: `docs/reviews/plan-final-rereview-20260810-213634-slice-1.4-mimo-native.md`

## Scope

只读核对 master plan Slice 1.4 final corrective contract（S14-CTRL-01..13）与真实 Fins storage callgraph、Host startup/toolset flow、batch/journal/lease 语义。不修改 plan、代码、测试、README、依赖；不安装依赖、pull 镜像、运行 live/network/model/broker、commit/push/PR。

## Assumptions tested

1. Terra S14-FINAL-01..04 和 MiM MR1/MR2 已在 S14-CTRL-03..13 内真实 closed；MR3 确为 non-finding。
2. Host override 唯一 runtime、无 global FS cache、无反向依赖、无 production 旁路。
3. 七条 producer 列全、existing batching 能跨 blob+metadata 同 token、S3 无 token 时拒绝、rollback/nested auto 语义可实施。
4. publish/delete target 对 partial/multi/crash/overwrite/remote drift/metadata-first/postcommit cleanup/restart 闭合；所有 destructive path 无先删 remote。
5. runtime/factory 参数互斥、startup/lifecycle 固定、public stream docs 契约化、atomic journal/copytree/lease/MinIO/tests/allowlist 均可实施。
6. architecture/best-practice/optimal/overengineering/overcoupling 无 material issue。

## 只读 callgraph 审计摘要

基于 explore subagent 与直接 source audit，真实 callgraph 确认如下：

| 方法 | FileStore? | 直接本地路径? | file:line |
|------|:---:|:---:|-----------|
| `_fs_blob_core.store_file` | **YES** | no | `:145-146` |
| `_fs_blob_core.list_entries` | no | **YES** | `:39-45` |
| `_fs_blob_core.read_file_bytes` | no | **YES** | `:63-68` |
| `_fs_blob_core._delete_entry_impl` | no | **YES** | `:107-113` |
| `_fs_source_document_core.get_source` | no | **YES** | `:633-641`（`_local_path_from_uri`+`LocalFileSource`） |
| `_fs_source_document_core.get_primary_source` | no | **YES** | `:660-662`（委托 get_source） |
| `_fs_source_document_core.has_filing_xbrl_instance` | no | **YES** | `:496-502` |
| `_fs_processed_core._upsert_processed` | no | **YES** | `:275-320` |
| `_fs_maintenance_core.store_rejected_filing_file` | **YES** | no | `:146-152` |
| `_fs_maintenance_core.read_rejected_filing_file_bytes` | no | **YES** | `:302-307` |
| `_fs_maintenance_core._clear_filing_documents_impl` | no | **YES** | `:344-351` |
| `_fs_maintenance_core._cleanup_stale_filing_documents_impl` | no | **YES** | `:405-437` |
| `_fs_storage_infra.begin_batch` | no | **YES** | `:163-199`（shutil.copytree） |
| `_fs_storage_infra.commit_batch` | no | **YES** | `:201-257`（shutil.move+rmtree） |
| `_fs_storage_infra._execute_with_auto_batch` | 复用 active token | 分发点 | `:295-335` |
| `_fs_storage_infra._build_file_store` | 分发点 | 分发点 | `:827-842` |
| `DefaultFinsRuntime.create()` | **无 file_store 参数** | — | `service_runtime.py:1889-1895` |
| `prepare_host_runtime_dependencies()` | **无 S3 步骤** | — | `startup_preparation.py:469-602` |
| writer lease / flock | **不存在** | — | — |
| remote operation journal | **不存在** | — | — |
| `FileStore.get_object` docstring | 无 caller-owned/seekable/close | — | `file_store.py:38-51` |
| `Source.open` docstring | 无 caller-owned/seekable/close | — | `source.py:42-55` |
| `_StagedFileStore` capability | **不存在** | — | 需新增 |
| `action=delete` journal | **不存在** | — | 仅 plan 文档 |

---

## Terra S14-FINAL-01..04 与 MiM MR1/MR2/MR3 逐项闭合核验

### Terra S14-FINAL-01：Host scene 真实 Fins tool path 自行构造 FS runtime，绕过 S3 store 与 writer lease

**Controller 裁决**: CLOSED-IN-PLAN via S14-CTRL-11。

**真实 callgraph 证据**: `toolset_registrars.py` 的 `_get_cached_fins_runtime`（L16-30）使用 `@lru_cache` 缓存 `DefaultFinsRuntime.create(workspace_root=...)`，完全从 workspace 路径自造 FS runtime。`scene_preparer.py:747-784` 的 `_build_tool_registry` 只向 `ToolsetRegistrationContext` 传 workspace/config/permissions（无 Fins runtime 字段），registrar 自行 import 并调用缓存 runtime。Host 的 `__init__` 和 `_build_default_scene_preparation` 当前无 `toolset_registrar_overrides` 参数。

**闭合判定**: S14-CTRL-11 方案——删除 `_get_cached_fins_runtime`，改为 `build_fins_toolset_registrars(runtime)` 返回 typed frozen callable 只读映射；`DefaultScenePreparer` 接受 `toolset_registrar_overrides`，`_build_tool_registry` 优先 override、Fins-owned toolset 缺 override fail closed；startup 是唯一构造点；Host/contracts 不 import Fins。**闭合有效**。

### Terra S14-FINAL-02：remote journal 没有跨越真实的 blob 写入与随后的 FS metadata 写入

**Controller 裁决**: CLOSED-IN-PLAN via S14-CTRL-12。

**真实 callgraph 证据**: `store_file`（`_fs_blob_core.py:145-146`）走 FileStore，但当前直接 `put_object`，不进入任何 batch；随后的 metadata 更新（`commit_filing_source_document`/`_upsert_source_document`/`_upsert_processed`）各自启动独立 auto-batch。`_execute_with_auto_batch`（L318）在有 active token 时复用，无 active token 时自动 `begin_batch`。当前 batch 系统完全是本地 FS 操作（copytree/move/rmtree），无 S3 感知。

**闭合判定**: S14-CTRL-12 要求 producer 在最高原子边界显式 `begin_batch(ticker)` → blob 写 + metadata 写 → `commit_batch`，七条调用链逐一 allowlist。复用现有 `BatchingRepositoryProtocol`，不发明第二事务 API。S3 模式无 active explicit batch 时稳定失败 `s3_write_requires_batch`。**闭合有效**。

### Terra S14-FINAL-03：delete/reset/cleanup 先删 S3 bytes 后删 FS metadata 不可恢复

**Controller 裁决**: CLOSED-IN-PLAN via S14-CTRL-13。

**真实 callgraph 证据**: 所有 destructive 路径（`_delete_entry_impl` L107-113、`_reset_source_document_impl` L542-546、`_delete_processed_impl` L110-115、`_clear_processed_documents_impl` L246-254、`_clear_filing_documents_impl` L344-351、`_cleanup_stale_filing_documents_impl` L404-437）全部是纯本地 `shutil.rmtree`/`unlink`，无任何远程操作。当前无 remote journal、无 `action=delete` 概念。

**闭合判定**: S14-CTRL-13 新增 journal target `action=publish|delete`，delete target 记录 `expected_sha256/expected_size/delete_state`；head 验证 → FS metadata swap → post-commit 幂等 remote delete；任何路径禁止先删 remote；fault matrix 覆盖每 phase kill。**闭合有效**。

### Terra S14-FINAL-04："已验证、seekable、caller-owned BinaryIO"与冻结公共协议文档不一致

**Controller 裁决**: CLOSED-IN-PLAN via S14-CTRL-06。

**真实 callgraph 证据**: `FileStore.get_object`（`file_store.py:38-51`）docstring 仅写"读取对象内容"→"二进制流"→"FileNotFoundError"；`Source.open`（`source.py:42-55`）docstring 仅写"打开只读流"→"二进制只读流"→"OSError"。均无 caller-owned、seekable、close、checksum 语义。

**闭合判定**: S14-CTRL-06 要求两个公共 docstring 只锁跨实现共同语义（caller-owned、caller close、seekable、读取异常）；checksum 为 S3 concrete adapter 契约，不虚构 Local 同义。方法签名与语义不改。**闭合有效**。

### MiM MR1：begin_batch copytree 在 S3 模式只拷贝本地 metadata

**Controller 裁决**: CLOSED-IN-PLAN via S14-CTRL-04。

**闭合判定**: S14-CTRL-04 明确 S3 模式 `begin_batch` copytree 只复制 FS metadata/manifest/journal tree；staging 缺损 fail closed 保留 journal 供人工恢复 + 显式测试。**闭合有效**。

### MiM MR2：`_write_json` 非原子写入可能损坏 journal

**Controller 裁决**: CLOSED-IN-PLAN via S14-CTRL-04。

**闭合判定**: remote_op_journal 使用独立 atomic JSON helper（same-dir temp+flush+fsync+os.replace+parent dir fsync），不复用 `_write_json`。只读核验注：`_write_json`（`_fs_storage_utils.py:439-463`）当前已 temp+replace+dir-fsync 原子，但 plan 仍要求 journal 自包含。**闭合有效**。

### MiM MR3：staged capability 的 isinstance 类型安全

**验证结论**: `@runtime_checkable` 私有 Protocol + `isinstance` 是 Python 内置类型检查，类型安全，不违反 AGENTS.md 的 `hasattr`/`getattr` 限制。**VERIFIED-NON-FINDING / CLOSED**。

---

## 逐项闭合判定汇总

| Finding | 闭合位置 | 判定 |
|---------|---------|------|
| Terra S14-FINAL-01 | S14-CTRL-11 | **CLOSED** |
| Terra S14-FINAL-02 | S14-CTRL-12 | **CLOSED** |
| Terra S14-FINAL-03 | S14-CTRL-13 | **CLOSED** |
| Terra S14-FINAL-04 | S14-CTRL-06 | **CLOSED** |
| MiM MR1 | S14-CTRL-04 | **CLOSED** |
| MiM MR2 | S14-CTRL-04 | **CLOSED** |
| MiM MR3 | VERIFIED-NON-FINDING | **CLOSED** |

---

## Host override 唯一 runtime、无 global FS cache、无反向依赖、无 production 旁路

S14-CTRL-11 的方案：
- 删除 `_get_cached_fins_runtime`（模块级 lru_cache），消除 global FS cache。
- `toolset_registrars.py` 改为 `build_fins_toolset_registrars(runtime)` 返回 frozen callable 只读映射，无模块级可变状态。
- `Host.__init__` 新增 `toolset_registrar_overrides` keyword-only 参数，类型为 `Mapping[str, ToolsetRegistrarProtocol]`——Host/contracts 只引用 `ToolsetRegistrarProtocol`（在 `dayu/contracts/toolset_registrar.py`），不 import `dayu.fins.*`，bucket/key 不越层。
- startup（`prepare_host_runtime_dependencies`）在 `DefaultFinsRuntime.create` 后调用 `build_fins_toolset_registrars(fins_runtime)` 构造 override，传入 `Host(...)`——startup 是唯一构造点。
- Fins-owned toolset（配置 path 为 `dayu.fins.*`）启用但 override 缺失 => `fins_toolset_override_required` fail closed，绝不回退配置 path 构造本地 runtime。
- 真实 Host scene black-box：S3 模式 startup 装配真实 Host，fins+ingestion scene 执行 read/ingestion/process/evidence，断言四条路径经同一 repository_set，第二 writer 被 lease 拒绝。

**判定：Host 唯一 runtime、无 global FS cache、无反向依赖、无 production 旁路。** 无 material finding。

---

## 七条 producer 是否列全

S14-CTRL-12 列出的七条 `store_file`/`store_rejected_filing_file` 直接 public 调用链：

| # | Producer | 文件 | store 方法 | grep 验证 |
|---|---------|------|-----------|----------|
| 1 | SEC active filing | `sec_download_filing_workflow.py` → `sec_download_persistence.py` | `store_file` | ✅ L407/L428 → L131 → L425 |
| 2 | SEC rejected artifact | `sec_download_persistence.py` | `store_rejected_filing_file` | ✅ L151 → L428 → L451 |
| 3 | CN filing | `cn_download_filing_workflow.py` | `store_file` | ✅ L314/L414/L428 |
| 4 | Docling upload | `docling_upload_service.py` | `store_file` | ✅ L225 |
| 5 | Tool snapshot | `tool_snapshot_export.py` | `store_file` | ✅ L1513 |
| 6 | Rejected rescue | `rejected_6k_rescue.py` | `store_file` | ✅ L580 |
| 7 | Rejected retriage | `active_6k_retriage.py` | `store_rejected_filing_file` | ✅ L431 |

**grep 全覆盖验证**：`dayu/fins/` 下所有 `store_file`/`store_rejected_filing_file` 调用点均在上述七条链或 narrow repository 层内（`fs_document_blob_repository.py:60`、`fs_filing_maintenance_repository.py:67`），不存在未列名的第八条 producer。

**判定：七条 producer 列全。**

---

## Existing batching 能跨 blob+metadata 同 token

`_execute_with_auto_batch`（`_fs_storage_infra.py:318`）在有 active token 时复用同一 token，无 active token 时自动 `begin_batch`。S14-CTRL-12 要求 producer 在最高原子边界显式 `begin_batch(ticker)`，因此 blob 写（`store_file`/`store_rejected_filing_file`）与随后的 metadata 更新（`_upsert_source_document`/`_upsert_processed`/`commit_filing_source_document`）共享同一 `_active_batches` token 空间。所有窄仓储共享同一 `_FsRepositorySet`（S14-CTRL-05/12），同一 core、同一 token。

**但存在一个实现歧义**：S14-CTRL-12 说"S3 模式 store_file 必须已有 active explicit BatchToken，否则稳定失败 `s3_write_requires_batch`"；而当前 `_execute_with_auto_batch` 在无 active token 时会自动 `begin_batch`（L320）。若 implementation agent 不显式禁用 S3 模式下的 auto-begin 行为，`store_file` 可能通过 auto-batch 获得 token 而不报 `s3_write_requires_batch`，绕过 producer 级 batch 边界。**见 Finding F-01**。

**判定：跨 blob+metadata 同 token 语义可实施，但 auto-batch 在 S3 模式的行为需显式约束。**

---

## S3 无 token 拒绝、rollback/nested auto 语义

- S3 模式 `store_file`/`store_rejected_filing_file` 无 active explicit batch 时抛 `s3_write_requires_batch`——由 `_fs_blob_core.py` / `_fs_maintenance_core.py` 在注入 S3 store 时检查。
- rollback：`_execute_with_auto_batch`（L326-333）在异常时调用 `rollback_batch`，S3 模式下清理 staging keys + remote journal targets。
- nested auto：S14-CTRL-12 要求 producer 显式 begin/commit/rollback，不依赖 auto-batch。`_execute_with_auto_batch` 在有 active token 时直接执行（L318-319），不嵌套 begin。

**判定：可实施。**

---

## publish/delete target 对 edge cases 的闭合

| 场景 | 闭合位置 | 判定 |
|------|---------|------|
| partial（单 target 失败） | S14-CTRL-04 commit ordering 逐 target 原子 | ✅ |
| multi（2+ targets） | S14-CTRL-04 per-target publish_state/delete_state 独立 | ✅ |
| crash（每 phase kill） | S14-CTRL-04 recovery 逐 target 独立判定 | ✅ |
| overwrite | S14-CTRL-04 staging→final CopyObject 覆盖旧 bytes | ✅ |
| remote drift | S14-CTRL-04 copy 响应模糊时 head final digest/size 判定 | ✅ |
| metadata-first | S14-CTRL-04 commit ordering = publish-before-swap | ✅ |
| postcommit cleanup | S14-CTRL-04 cleanup_pending + startup 重试 | ✅ |
| restart | S14-CTRL-04 startup `ensure_batch_recovery` 重放 | ✅ |
| FS staging 缺损 | S14-CTRL-04 FAIL CLOSED + 保留 journal/远端 objects | ✅ |

**判定：全部闭合。**

---

## 所有 destructive path 无先删 remote

S14-CTRL-13 明确：commit 顺序为 head 验证每个 delete target → FS metadata swap → post-commit 幂等 remote delete。"任何路径禁止先删 remote"。fault matrix 覆盖 single delete、reset、processed clear、filing clear/stale cleanup、missing/ambiguous delete、每 phase kill。

**判定：所有 destructive path 无先删 remote。**

---

## 其余 contract 逐项验证

| 合约项 | plan 描述 | 代码/设计证据 | 判定 |
|--------|----------|-------------|------|
| runtime/factory 参数互斥 | `DefaultFinsRuntime.create(file_store=None, repository_set=None)` 互斥 | S14-CTRL-05/12 明确互斥 + ValueError | ✅ |
| startup 12 步顺序 | load→paths→S3 admission→lease→recovery→provider→...→runtime→Host | S14-CTRL-05 fixed | ✅ |
| lifecycle/atexit | `PreparedHostRuntimeDependencies` 私有持有 lease+S3+lifecycle，close 幂等 | S14-CTRL-05/09 | ✅ |
| public stream docs | `FileStore.get_object`/`Source.open` docstring 契约化 | S14-CTRL-06 明确 | ✅ |
| atomic journal | 独立 atomic JSON helper（temp+flush+fsync+replace+parent fsync） | S14-CTRL-04 明确 | ✅ |
| copytree S3 mode | 只复制 FS metadata/manifest/journal tree | S14-CTRL-04 明确 | ✅ |
| lease | 非阻塞 exclusive flock + exact-once lifecycle + atexit | S14-CTRL-09 | ✅ |
| MinIO | pinned digest + TERM→KILL→rm-f + owner label + bounded timeout | S14-CTRL-07 | ✅ |
| tests | unit/journal/lease/startup/MinIO/producer crash/destructive fault/Host scene | S14-CTRL-08 | ✅ |
| allowlist | 精确文件级展开（新增5+修改N+测试M+文档D） | S14-CTRL-11/12/13 | ✅ |

---

## Architecture / best-practice / optimal / overengineering / overcoupling lenses

### Architecture boundary
S14-CTRL-11 的 Host→Fins 注入正确：Host 只接受 `Mapping[str, ToolsetRegistrarProtocol]`，不 import `dayu.fins.*`，bucket/key 不越层。startup 是唯一构造点。FS metadata + S3 bytes 分离在 `dayu.fins.storage` owner 内。S14-CTRL-03 byte-path matrix 正确识别全部 12 个字节 owner 路径。

### Best practice
strict JSON env-name、explicit credential、HEAD-only stat、typed boto3 stubs、verified BinaryIO、single-writer flock、atomic journal 都是合理约束。destructive 状态机的 metadata-first + post-commit idempotent delete 符合 S3 最佳实践。

### Optimal solution
FS metadata + S3 blob 是避免复制整套 workspace 到 bucket 的最小方向。remote journal 复用现有 FS batch owner 而非新建第二 metadata repository。single-writer flock 是当前 production topology 的最实际约束。

### Overengineering
未发现。S14-CTRL-01..13 每个约束都有明确 failure mode 支撑。`_StagedFileStore` capability protocol 是最小扩展。

### Overcoupling
S14-CTRL-03 byte-path matrix 要求修改 12 个字节 owner 路径，但每个路径的 corrective 后实现自包含在 Fins storage 层内。S14-CTRL-12 的七条 producer allowlist 是对现有调用点的逐个适配，不是跨层耦合。

---

## Open Questions

1. **无。** 所有 prior findings 已由 S14-CTRL-03..13 唯一化闭合。

---

## Findings

### F-01-未修复-[中]-S3 模式 `_execute_with_auto_batch` auto-begin 行为与 `s3_write_requires_batch` 约束存在实现歧义

- **位置**: S14-CTRL-12（master plan S14-CTRL-12 "S3 模式 store_file/store_rejected_filing_file 必须已有 active explicit BatchToken，否则稳定失败 s3_write_requires_batch"）与 `_fs_storage_infra.py:295-335`（`_execute_with_auto_batch` L318-320）
- **问题类型**: 实现歧义 / 可能被绕过的安全约束
- **当前写法**: S14-CTRL-12 要求 S3 模式下 `store_file` 必须已有 active explicit BatchToken，否则抛 `s3_write_requires_batch`。但当前 `_execute_with_auto_batch` 在无 active token 时自动 `begin_batch`（L320），不区分 FS/S3 模式。
- **反例/失败场景**: 若 implementation agent 未显式修改 `_execute_with_auto_batch` 在 S3 模式下的 auto-begin 行为，某个直接调用 `store_file` 的代码路径（未被七条 allowlist 覆盖的 future 调用者）可能通过 auto-batch 获得 token 而不报 `s3_write_requires_batch`，绕过 producer 级 batch 边界。这不导致 data loss（auto-batch 仍有 commit/rollback），但破坏 S14-CTRL-12 的显式 batch 约束——该约束的目的是确保 blob+metadata 的原子边界完全由 producer 控制。
- **为什么有问题**: S14-CTRL-12 明确要求"不允许任何不经 batch 的直连 store_file/store_rejected_filing_file 路径"，且 S3 模式无 active batch 时稳定失败。但 `_execute_with_auto_batch` 的现有行为与此冲突——它在无 active batch 时 auto-begin，S3 模式下也会 auto-begin。
- **直接证据**: `_fs_storage_infra.py:318-320`：`if normalized_ticker in self._active_batches: return operation(*args, **kwargs)` else `token = self.begin_batch(normalized_ticker)`。S14-CTRL-12："S3 模式 store_file/store_rejected_filing_file 必须已有该 ticker 的 active explicit BatchToken，否则稳定失败 s3_write_requires_batch"。
- **影响**: implementation agent 可能遗漏对 `_execute_with_auto_batch` 的 S3 模式约束，导致 auto-batch 绕过 producer 级 batch 边界。
- **建议改法和验证点**: S14-CTRL-12 增加一条明确约束：`_execute_with_auto_batch` 在 S3 模式（检测注入的 file_store 为 S3 类型）下，若无 active token 则抛 `s3_write_requires_batch` 而非 auto-begin。或更简洁地：S3 模式下 `_execute_with_auto_batch` 的 auto-begin 行为必须被禁用，所有 S3 写操作必须经显式 producer batch 入口。验证点：S3 模式 `_execute_with_auto_batch` 无 active token 时的错误类型与消息。
- **修复风险（低）**: 只需在 `_execute_with_auto_batch` 增加 S3 模式判断，不影响 FS 模式。
- **严重程度（中）**: 不导致 data loss，但破坏 plan 的显式 batch 约束；若 future 新增未列名调用者可能绕过原子边界。

---

## Residual Risk

| 风险 | 严重程度 | 建议跟踪 |
|------|---------|---------|
| FS+S3 双层存储的运维复杂度：FS metadata 在本地磁盘，S3 blob 在远端，需分别备份 | 中 | `dayu/fins/README.md` 运维前置条件声明 |
| `_build_store_key` 的 key 格式变更风险：未来修改会同时影响 FS 和 S3 | 低 | 所有 backend 共享 risk，非 S3 特有 |
| `_execute_with_auto_batch` 在 S3 模式下 auto-begin 行为可能绕过 producer batch 约束 | 中 | S14-CTRL-12 增加显式约束（见 F-01） |

---

## Final plan review conclusion

**pass-with-risks**

S14-CTRL-01..13 的 corrective contract 对 implementation agent 足够确定性：

1. **Terra S14-FINAL-01..04 全部 CLOSED**——Host toolset override 唯一 runtime（S14-CTRL-11）、producer blob+metadata 共享 batch（S14-CTRL-12）、destructive 状态机（S14-CTRL-13）、protocol docstring 契约化（S14-CTRL-06）。
2. **MiM MR1/MR2 全部 CLOSED**——S3 模式 copytree 语义（S14-CTRL-04）、独立 atomic journal helper（S14-CTRL-04）。
3. **MiM MR3 VERIFIED-NON-FINDING/CLOSED**。
4. **七条 producer 列全**，grep 全覆盖验证无遗漏。
5. **S3 authoritative bytes 全路径覆盖**，12 个字节 owner 逐行确认。
6. **per-target remote journal 可实现**，publish/delete 两种 action 独立状态机。
7. **单 writer flock admission 可执行**。
8. **destructive 状态机完整**，任何路径禁止先删 remote。
9. **startup/lifecycle/lease/MinIO/tests/allowlist 均可实施**。

**Open 0 H / 1 M / 0 L**：

- **F-01（M）**: `_execute_with_auto_batch` 在 S3 模式下 auto-begin 行为与 `s3_write_requires_batch` 约束存在实现歧义——需在 S14-CTRL-12 增加显式约束。

**结论：plan 可以进入 implementation gate**。F-01 不是 blocker（不导致 data loss，只需显式禁用 S3 模式 auto-begin），Controller 可在接受该 risk 的前提下批准 implementation。不建议因 F-01 阻塞 implementation gate——其影响在 fail closed 范围内，且 implementation agent 有足够信息识别并处理。
