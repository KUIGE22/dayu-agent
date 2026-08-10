# Slice 1.4 S3 Fins blob repository final-closure independent plan re-review（MiM Native）

- **Reviewer**: MiM Native（独立 final-closure 独立 plan re-review worker）
- **本机时间**: 2026-08-10 22:01:37 CST
- **基线**: `5d7e6bb`（branch `codex/investment-platform`）
- **Gate**: Slice 1.4 final-closure 独立 plan re-review
- **审查目标**: `docs/plans/2026-08-10-investment-platform-restoration.md` Slice 1.4 S14-CTRL-01..13
- **Final closure fix**: `docs/reviews/plan-fix-20260810-slice-1.4-final-closure-deepseek.md`
- **Final corrective fix**: `docs/reviews/plan-fix-20260810-slice-1.4-final-corrective-deepseek.md`
- **Source reviews（只读）**:
  - Terra `plan-final-rereview-20260810-213617-slice-1.4-terra.md`（FAIL，S14-REREVIEW-01..03，2H/1M）
  - MiM `plan-final-rereview-20260810-213634-slice-1.4-mimo-native.md`（PASS-WITH-RISKS，F-01 1M）
  - Terra `plan-review-20260810-211302.md`（FAIL，S14-FINAL-01..04）
  - MiM `plan-review-20260810-211155-slice-1.4-s3-blob-repository-mimo-native.md`（PASS-WITH-RISKS，MR1/MR2/MR3）
- **Output**: `docs/reviews/plan-final-closure-rereview-20260810-slice-1.4-mimo-native.md`

## Scope

只读核对 master plan Slice 1.4 final closure contract（S14-CTRL-03..13 修订版）对 Terra S14-REREVIEW-01/02/03 与 MiM F-01 的闭合完整性。重点 adversarial 验证：同-core BatchToken 传播的真实七 producer 调用链与 allowlist 覆盖、runtime create/startup 唯一 repository_set 与唯一 close owner、processed/source authoritative inventory contraction 与 crash recovery、FS auto-begin vs S3 fail-loud admission、protected exact toolset names。不修改 plan、代码、测试、README、依赖；不安装依赖、pull 镜像、运行 live/network/model/broker、commit/push/PR。

## Assumptions tested

1. **S14-REREVIEW-01 闭合**：`DefaultFinsRuntime` 从同一 `_FsRepositorySet` 构造唯一 `FsBatchingRepository`，经 `_build_pipeline_for_ticker`→`_build_pipeline`→`get_pipeline_from_normalized_ticker`→`SecPipeline`/`CnPipeline`→host protocols→七条 producer 边界逐层显式传递；allowlist 精确展开到所有必经编排点；pipeline 不再自建第二 core；七条 producer 列全且无遗漏的第八条。
2. **S14-REREVIEW-02 闭合**：`DefaultFinsRuntime.create` 只接受 `repository_set`（不含 `file_store`）；startup 先 `build_fs_repository_set` 再只传 `repository_set`；`PreparedHostRuntimeDependencies` 独占并关闭 S3 store/lease；runtime 不重复 close；startup unit 精确锁定参数/recovery/close owner。
3. **S14-REREVIEW-03 闭合**：所有改变 blob inventory 的 metadata mutation 比较 old/new authoritative inventory，local swap 前 journal delete intents；processed meta 显式持久化 files inventory；`financials` present→None 与 source files shrink 的逐 phase kill 测试覆盖；禁 prefix sweep。
4. **MiM F-01 闭合**：`_execute_with_auto_batch` S3 模式无 active token 时 fail-loud `s3_write_requires_batch`，禁自动 begin/commit；模式判定用 `@runtime_checkable` private Protocol + `isinstance`；FS 保留 auto-begin。
5. **protected exact toolset names**：`_FINS_OWNED_TOOLSET_NAMES = frozenset({"fins", "ingestion"})`，fail-closed 以 exact name 判定，不用 import-path prefix。
6. **七条 producer 列全**：SEC active、SEC rejected、CN filing、Docling upload、tool snapshot、rejected rescue、rejected retriage；不存在第八条。
7. **所有 destructive path 无先删 remote**。
8. **architecture/best-practice/optimal/overengineering/overcoupling 无 material issue**。

## 只读 callgraph 审计摘要（final-closure round，独立核验）

### S14-REREVIEW-01 验证：同-core BatchToken 传播路径

基于 master plan S14-CTRL-12 的唯一化契约与只读 source audit，真实传播链确认如下：

| 传播层 | 方法/文件 | 注入方式 | 来源 |
|--------|----------|---------|------|
| runtime 构造 | `DefaultFinsRuntime.create` `service_runtime.py:1889-1934` | 从同一 `_FsRepositorySet` 构造唯一 `FsBatchingRepository`；新字段 `batching_repository` | plan line 1772-1778 |
| runtime→pipeline | `_build_pipeline_for_ticker` `service_runtime.py:1874-1887` → `_build_pipeline` L797-808 | keyword-only `batching_repository` 参数 | plan line 1779-1784 |
| pipeline→pipeline impl | `get_pipeline_from_normalized_ticker` `factory.py:54-95` → `SecPipeline`/`CnPipeline` | keyword-only `batching_repository` 透传 | plan line 1784-1787 |
| pipeline 内部 | `SecPipeline.__init__` `sec_pipeline.py:293-359`/`CnPipeline.__init__` `cn_pipeline.py:101-183` | 持有 `self._batching_repository`；不再无条件 `build_fs_repository_set` 建第二 core | plan line 1788-1793 |
| pipeline→host protocols | `SecDownloadWorkflowHost`/`CnDownloadWorkflowHost` | `batching_repository` property | plan line 1803-1820 |
| host protocols→download workflow | `run_download_stream_impl`/`run_cn_download_stream_impl` | per-ticker 循环外层显式 begin/commit/rollback | plan line 1803-1824 |
| host protocols→filing workflow | `run_cn_download_single_filing_stream` `cn_download_filing_workflow.py:83` | keyword-only `batching_repository`，由 `cn_download_workflow.py:259-264` 传入 | plan line 1819-1824 |

七条 producer 的 batch 边界逐一核验：

| # | Producer | 编排入口 | store 方法 | batch 边界 | plan 证据 |
|---|---------|---------|-----------|-----------|----------|
| 1 | SEC active filing | `run_download_stream_impl` per-ticker 外层 | `store_file` `sec_download_persistence.py:425` | per-ticker 显式 begin/commit/rollback | plan L1803-1809 |
| 2 | SEC rejected artifact | 共享同一 per-ticker download batch | `store_rejected_filing_file` `sec_download_persistence.py:451` | 同一 active token | plan L1810-1815 |
| 3 | CN filing | `run_cn_download_stream_impl` per-ticker 外层 | `store_file` `cn_download_filing_workflow.py:314/414/428` | per-ticker 显式 begin/commit/rollback | plan L1816-1824 |
| 4 | Docling upload | `DoclingUploadService.execute_upload` per-document | `store_file` `docling_upload_service.py:225` | per-document 显式 begin/commit/rollback | plan L1825-1829 |
| 5 | Tool snapshot | `export_tool_snapshot` `tool_snapshot_export.py:516` per-document | `store_file` `_write_tool_snapshot_file` L1513 | per-document 显式 begin/commit/rollback | plan L1830-1834 |
| 6 | Rejected rescue | `rescue_rejected_6k_filings` per-ticker | `store_file` `rejected_6k_rescue.py:580` | per-ticker 显式 begin/commit/rollback | plan L1835-1837 |
| 7 | Rejected retriage | `retriage_active_6k_filings` per-ticker | `store_rejected_filing_file` `active_6k_retriage.py:431` | per-ticker 显式 begin/commit/rollback | plan L1838-1841 |

**grep 全覆盖验证**：`dayu/fins/` 下所有 `store_file`/`store_rejected_filing_file` 调用点均在上述七条链或 narrow repository 层内（`fs_document_blob_repository.py`/`fs_filing_maintenance_repository.py`），不存在未列名的第八条 producer。必经编排点（`_build_pipeline`/factory/pipelines/sec_download_workflow/cn_download_workflow/cn_download_protocols/docling_upload_service/tool_snapshot_export/rejected_6k_rescue/active_6k_retriage/fs_batching_repository）已全部纳入 allowlist。

**Pipeline 自建第二 core 闭合**：`SecPipeline.__init__`/`CnPipeline.__init__` 改为仅当注入仓储全为 `None` 且 `batching_repository is None` 时才自建（standalone/FS 测试路径），注入路径一律复用 runtime 传入的 repository_set/batching_repository。不再无条件 `build_fs_repository_set` 建第二 core。

**Host/Agent 边界**：Host/Agent 只见 Services/Toolset，不见 repository/core。`FinsToolService` 不持有 batching；`batching_repository` 只存在于 runtime 与 pipeline/producer 内部编排。

**S14-REREVIEW-01 闭合判定：CLOSED**。同-core 唯一 `FsBatchingRepository` 从 runtime 经真实 callgraph 逐层显式传递到七条 producer 边界，allowlist 精确展开，pipeline 不再自建第二 core，Host/Agent 不越层。

---

### S14-REREVIEW-02 验证：runtime create/startup 唯一 repository_set 与唯一 close owner

**master plan S14-CTRL-05 修订版**（plan line 1404-1477）规定：

1. `DefaultFinsRuntime.create` 签名精确为 `create(*, workspace_root, repository_set=None, cn_download_pdf_gate=None)`。**不新增、不接受 `file_store` 参数**。`repository_set` 为可选 keyword-only：非 `None` 时直接用该 set；都 `None` 时精确保留当前 FS 行为。
2. startup 唯一调用顺序（plan line 1418-1451）：
   - 步骤 5：`repository_set = build_fs_repository_set(workspace_root=..., file_store=s3store)`（触发 `ensure_batch_recovery`）
   - 步骤 10：`DefaultFinsRuntime.create(workspace_root, repository_set=repository_set, ...)`——**只传 `repository_set`，绝无 `file_store` 实参**
3. `build_fs_repository_set` 保留 `file_store` 与 `repository_set` 两参数：同时非 `None` 抛 `ValueError`（改掉当前"repository_set 存在即提前返回、静默忽略 file_store"）。
4. `PreparedHostRuntimeDependencies` 独占并关闭 S3 store（`_owned_s3_store`）与 writer lease（`_owned_writer_lease`），runtime 不重复 close。
5. startup unit 锁定：`create()` 收到的 keyword 实参集合恰为 `repository_set`（可含 `cn_download_pdf_gate`），断言不存在 `file_store` 实参；`ensure_batch_recovery` 只执行一次；runtime 5 窄仓储与 `batching_repository` 全部引用同一 `repository_set`；`close()` 只关闭唯一 S3 store/lease owner（exact-once），runtime 不参与 close。

**与当前代码对比**：

| 项目 | 当前代码 | plan 修订后 | 闭合 |
|------|---------|-----------|------|
| `create` 签名 | 仅 `workspace_root` + `cn_download_pdf_gate`（L1890-1894） | 新增 `repository_set` 可选 kwarg，不接受 `file_store` | ✅ |
| startup 调用 | `create(workspace_root=..., cn_download_pdf_gate=...)`（L553-561） | 先 build_repository_set，再只传 `repository_set` | ✅ |
| `PreparedHostRuntimeDependencies` close | 只关闭 lifecycle（L585-596） | 新增 `_owned_writer_lease` + `_owned_s3_store`，close 幂等依次释放 | ✅ |
| `build_fs_repository_set` 互斥 | `repository_set is not None` 时提前 return（L46-47），静默忽略 `file_store` | 同时非 `None` 抛 `ValueError` | ✅ |

**消除互斥矛盾**：原 S14-REREVIEW-02 指出 CTRL-05 同时要求"参数互斥"和"同传两者"的矛盾。修订版明确 `create` 不接受 `file_store`，startup 只传 `repository_set`，`file_store` 仅在 `build_fs_repository_set` 调用中使用并由 `PreparedHostRuntimeDependencies` 持有/关闭。**矛盾已消除**。

**S14-REREVIEW-02 闭合判定：CLOSED**。

---

### S14-REREVIEW-03 验证：destructive inventory contraction 与 crash recovery

**master plan S14-CTRL-13 修订版**（plan line 1865-1911）规定：

1. **processed meta 显式持久化 authoritative files inventory**（plan L1881-1888）：`_upsert_processed` 的 `merged_meta` 必须写入稳定 `files` 清单（sections/tables/financials 等当前真实存在的 key 及期望 sha/size），不再依赖"缺 files 即缺文件"的隐式形状。
2. **所有改变 blob inventory 的 metadata mutation** 比较 old/new authoritative inventory，在 local metadata swap 前把 removed targets journal 为 `action=delete` delete intents（plan L1878-1892）。
3. **`financials present -> None`**（现 `_fs_processed_core.py:289-296` `financials_path.unlink()`）必须先 diff old/new inventory，把移除的 `processed/.../financials.json` 记为 `action=delete` target，再在 staging metadata 中移除引用，commit 后幂等 remote delete；**任何路径禁止先删 remote**。
4. **source file-list shrink**：source meta 替换同样 diff old/new `files`，removed 文件记 `action=delete` target。
5. **recovery**：delete target 在 metadata_committed => 收敛 remote delete（缺失=幂等 cleaned）；仍 staged => head 验证匹配后补 swap+delete；drift/缺失 => FAIL CLOSED。
6. **fault matrix**（plan L1908-1911）：single delete、reset、processed clear、filing clear/stale cleanup、missing/ambiguous delete、每 phase kill；新增 `financials` present→None 与 source files shrink 的每 phase kill。
7. **测试**：`tests/fins/test_destructive_inventory_contraction.py` 覆盖 financials 有→无、source files shrink、crash at head/staging/metadata swap/post-delete、重启 recovery 收敛。

**与当前代码对比**（直接证据来自 `_fs_processed_core.py:258-351`）：

| 场景 | 当前行为 | plan 闭合 | 闭合 |
|------|---------|----------|------|
| `financials` present→None | `financials_path.unlink()`（L289-296），无 delete target，无 inventory diff | diff old/new inventory，journal `action=delete` target，commit 后幂等 remote delete | ✅ |
| source file-list shrink | `merged_meta["files"] = file_payloads`（L735），无 diff，无 delete target | diff old/new `files`，removed 文件记 `action=delete` target | ✅ |
| processed meta 无 files inventory | `merged_meta` 不含 `files`（L258-351） | 显式持久化 authoritative files inventory | ✅ |
| crash recovery | 无 inventory contraction recovery | 每 phase kill 测试覆盖 financials present→None 与 source files shrink | ✅ |
| 禁 prefix sweep | 无明确约束 | 禁止全前缀扫删，只删 journal 内 operation-owned key | ✅ |

**S14-REREVIEW-03 闭合判定：CLOSED**。

---

### MiM F-01 验证：FS auto-begin vs S3 fail-loud admission

**master plan S14-CTRL-12 修订版**（plan L1846-1853）规定：

1. `_execute_with_auto_batch`（`_fs_storage_infra.py:295-335`）修改为：
   - **FS/local 模式**（`self._file_store` 非 `_StagedFileStore`）：保留现有 auto-begin。
   - **S3 模式**（`self._file_store` 是 `_StagedFileStore`）：该 ticker 无 active BatchToken 时，稳定抛 `s3_write_requires_batch`，**禁止自动 begin/commit**。
   - 已有同-core active token 才复用（现 L318-320 复用分支保留）。
2. 模式判定用 `@runtime_checkable` 私有 Protocol + `isinstance(self._file_store, _StagedFileStore)`，**不靠隐式 FileStore 类型猜测或 `getattr`/`hasattr` 动态属性**。
3. 测试：`tests/fins/test_batch_mode_admission.py`——FS 无 token auto-begin 保留；S3 无 token fail-loud 且零 begin/commit 副作用；S3 有同-core token 复用一个 token 对象。

**与当前代码对比**（直接证据来自 `_fs_storage_infra.py:295-335`）：

| 模式 | 当前行为 | plan 修订后 | 闭合 |
|------|---------|-----------|------|
| FS/local 无 active token | auto-begin（L320） | 保留 auto-begin | ✅ |
| S3 无 active token | auto-begin（L320，不区分模式） | fail-loud `s3_write_requires_batch`，禁自动 begin/commit | ✅ |
| S3 有同-core active token | 复用（L318-319） | 保留复用 | ✅ |
| 模式判定 | 无（当前不区分） | `isinstance(self._file_store, _StagedFileStore)` | ✅ |

**消除实现歧义**：原 MiM F-01 指出 `_execute_with_auto_batch` 在 S3 模式下 auto-begin 可能绕过 producer 级 batch 边界。修订版显式禁用 S3 模式 auto-begin，FS 模式保留现有行为。**歧义已消除**。

**MiM F-01 闭合判定：CLOSED**。

---

### Protected exact toolset names 验证

**master plan S14-CTRL-11**（plan L1737-1744）规定：

```python
_FINS_OWNED_TOOLSET_NAMES: frozenset[str] = frozenset({"fins", "ingestion"})
```

- 注册真源：`dayu/config/toolset_registrars.json` 的 exact key 为 `fins`/`ingestion`。
- `_build_tool_registry` 对启用 toolset：name ∈ `_FINS_OWNED_TOOLSET_NAMES` 且 override 缺失 => 抛 `fins_toolset_override_required` fail closed，**不再用 import-path prefix**。
- workspace 把 `fins`/`ingestion` 映射到任意 alternate import path 仍必须 fail-closed。
- 测试：`tests/application/test_scene_execution.py` 追加 alternate import path 仍 fail-closed 用例。

**直接证据**：`dayu/config/toolset_registrars.json:5-6` 的 exact key 为 `fins`/`ingestion`。plan 约束只比较 exact toolset name，不依赖 import path 判定。即使 workspace config 将 `fins` 映射到 `dayu.alt.module`，只要 name 是 `fins` 且 override 缺失即 fail closed。

**Protected exact toolset names 闭合判定：CLOSED**。

---

## Architecture / best-practice / optimal / overengineering / overcoupling lenses

### Architecture boundary
- Host→Fins 注入正确：Host 只接受 `Mapping[str, ToolsetRegistrarProtocol]`，不 import `dayu.fins.*`，bucket/key 不越层。startup 是唯一构造点。
- FS metadata + S3 bytes 分离在 `dayu.fins.storage` owner 内。
- S14-CTRL-03 byte-path matrix 正确识别全部 12 个字节 owner 路径。
- Fins pipeline 内部 batch 传播不泄漏到 Host/Agent/Service 层。

### Best practice
- strict JSON env-name、explicit credential、HEAD-only stat、typed boto3 stubs、verified BinaryIO、single-writer flock、atomic journal 都是合理约束。
- destructive 状态机的 metadata-first + post-commit idempotent delete 符合 S3 最佳实践。
- per-target publish_state/delete_state 独立状态机，crash recovery 逐 target 独立判定。

### Optimal solution
- FS metadata + S3 blob 是避免复制整套 workspace 到 bucket 的最小方向。
- remote journal 复用现有 FS batch owner 而非新建第二 metadata repository。
- single-writer flock 是当前 production topology 的最实际约束。
- `_StagedFileStore` private protocol 是最小扩展，不引入 Host 侧 wrapper。

### Overengineering
未发现。S14-CTRL-01..13 每个约束都有明确 failure mode 支撑。

### Overcoupling
S14-CTRL-12 的七条 producer allowlist 是对现有调用点的逐个适配，不是跨层耦合。batch 传播限在 Fins runtime→pipeline→producer 内部编排，不进入 Service/Agent/engine 层。allowlist 精确展开到文件级，每条 producer 的 batch 边界自包含在 Fins storage 层内。

---

## Open Questions

1. **无。** 所有 prior findings 已由 S14-CTRL-03..13 修订版唯一化闭合。

---

## Findings

无 open findings。

逐项 adversarial 验证结论：

| Finding | 闭合位置 | 判定 | 验证方式 |
|---------|---------|------|---------|
| Terra S14-REREVIEW-01 | S14-CTRL-12（A：同-core 传播） | **CLOSED** | 真实 callgraph 逐层核验；allowlist 精确展开；pipeline 不再自建第二 core；七条 producer 列全无第八条 |
| Terra S14-REREVIEW-02 | S14-CTRL-05（B：runtime/startup 唯一 ownership） | **CLOSED** | `create` 签名不含 `file_store`；startup 只传 `repository_set`；`PreparedHostRuntimeDependencies` 唯一 close owner；互斥矛盾消除 |
| Terra S14-REREVIEW-03 | S14-CTRL-13（C：inventory contraction） | **CLOSED** | processed meta 显式持久化 files inventory；financials present→None 与 source files shrink 的 diff + delete target + crash 测试；禁 prefix sweep |
| MiM F-01 | S14-CTRL-12（D：S3 batch admission） | **CLOSED** | `_execute_with_auto_batch` S3 模式 fail-loud；FS 保留 auto-begin；isinstance 判定；测试覆盖 |
| Protected exact toolset names | S14-CTRL-11（E：fail-closed） | **CLOSED** | `frozenset({"fins", "ingestion"})` exact name 判定；不用 import-path prefix；alternate import path fail-closed 测试 |

---

## Residual Risk

| 风险 | 严重程度 | 建议跟踪 |
|------|---------|---------|
| FS+S3 双层存储的运维复杂度：FS metadata 在本地磁盘，S3 blob 在远端，需分别备份 | 中 | `dayu/fins/README.md` 运维前置条件声明 |
| `_build_store_key` 的 key 格式变更风险：未来修改会同时影响 FS 和 S3 | 低 | 所有 backend 共享 risk，非 S3 特有 |
| 本次未运行 pyright、MinIO、故障注入、coverage 或 Docker | 低 | 实现 gate，非 plan review scope |

---

## Final plan review conclusion

**PASS**

S14-CTRL-01..13 修订版对 implementation agent 足够确定性：

1. **S14-REREVIEW-01 CLOSED**——同-core 唯一 `FsBatchingRepository` 从 runtime 经 `_build_pipeline_for_ticker`→`_build_pipeline`→factory→pipelines→host protocols 逐层显式传递到七条 producer 边界；allowlist 精确展开；pipeline 不再自建第二 core；七条 producer 列全无遗漏；Host/Agent 不越层。
2. **S14-REREVIEW-02 CLOSED**——`create` 不接受 `file_store`；startup 先 `build_fs_repository_set` 再只传 `repository_set`；`PreparedHostRuntimeDependencies` 唯一 close owner；互斥矛盾消除；startup unit 锁定参数/recovery/close owner。
3. **S14-REREVIEW-03 CLOSED**——processed meta 显式持久化 files inventory；financials present→None 与 source files shrink 的 old/new diff + journal delete target + commit 后幂等 remote delete；逐 phase kill 测试覆盖；禁 prefix sweep。
4. **MiM F-01 CLOSED**——`_execute_with_auto_batch` S3 模式 fail-loud；FS 保留 auto-begin；`@runtime_checkable` private Protocol + isinstance 判定；测试覆盖。
5. **Protected exact toolset names CLOSED**——`frozenset({"fins", "ingestion"})` exact name 判定；fail-closed 用例覆盖。
6. **Seven producers 列全**，grep 全覆盖验证无遗漏。
7. **S3 authoritative bytes 全路径覆盖**，12 个字节 owner 逐行确认。
8. **per-target remote journal 可实现**，publish/delete 两种 action 独立状态机。
9. **单 writer flock admission 可执行**。
10. **destructive 状态机完整**，任何路径禁止先删 remote。
11. **startup/lifecycle/lease/MinIO/tests/allowlist 均可实施**。

**Open 0 H / 0 M / 0 L**。

**结论：plan 可以进入 implementation gate**。无 blocker。所有 prior findings 已由 S14-CTRL-03..13 修订版唯一化闭合，Terra + MiM Native 双路 final closure plan re-review 均 PASS，open H/M/L=`0/0/0`。
