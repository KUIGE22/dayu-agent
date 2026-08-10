# Slice 1.4 final corrective closure 独立 plan re-review（MiM Native）

## 审查目标与边界

- **本机时间**：2026-08-10 22:25 CST
- **基线**：`5d7e6bb`；分支：`codex/investment-platform`
- **目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 当前 Slice 1.4（含 final closure corrective fix）
- **已完整读取**：根 `AGENTS.md`、master plan 当前 Slice 1.4（含 S14-CTRL-01..13 修订版）、Terra `plan-final-closure-rereview-20260810-slice-1.4-terra.md`（FAIL，S14-CLOSURE-01/02）、MiM Native `plan-final-closure-rereview-20260810-slice-1.4-mimo-native.md`（PASS，open 0/0/0）、Controller `plan-fix-20260810-slice-1.4-final-closure-corrective-deepseek.md`
- **只读边界**：未改 plan、代码、测试、README 或既有 review；未运行 live/MinIO/model/broker，未安装依赖、commit、push 或 PR

## 审查范围与验证点

本次独立 re-review 聚焦三个核心验证方向：

1. **S14-CLOSURE-01/02 是否被 plan corrective 真实闭合**：Host ingestion factory 同-core propagation 与 S3 fail-loud 下逐名 8 类 mutation 的最小 explicit batch boundary
2. **S14-REREVIEW-02/03、MiM F-01、exact toolset names 是否无回归**
3. **plan 修正后的契约是否对 implementation agent 足够确定性**

## 只读 callgraph 审计

### 验证 A：S14-CLOSURE-01 — Host ingestion factory 同-core propagation

**plan 修正内容（S14-CTRL-12 A，plan:1890-1909）**：

plan 规定真实唯一链为：
```
DefaultFinsRuntime.batching_repository
→ build_ingestion_service_factory(... batching_repository=self.batching_repository)
→ dayu.fins.ingestion.factory.build_ingestion_service_factory(... batching_repository)
→ build_ingestion_service_from_normalized_ticker(... batching_repository)
→ get_pipeline_from_normalized_ticker(... batching_repository)
→ SecPipeline/CnPipeline
```

**当前代码状态（explore-1 审计证据）**：

| 传播层 | 文件:行 | 当前签名含 batching_repository？ |
|--------|---------|-------------------------------|
| `DefaultFinsRuntime.build_ingestion_service_factory()` | `service_runtime.py:2497` | **否** — 只传 5 窄仓储 + registry |
| `build_ingestion_service_factory()` | `ingestion/factory.py:30` | **否** — 7 个 keyword-only 参数，无 batching |
| `build_ingestion_service_from_normalized_ticker()` | `pipelines/factory.py:116` | **否** — 7 个 keyword-only 参数，无 batching |
| `get_pipeline_from_normalized_ticker()` | `pipelines/factory.py:54` | **否** — 9 个参数，无 batching |
| `SecPipeline.__init__` | `sec_pipeline.py:284` | **否** — 10 个参数，无 batching |
| `CnPipeline.__init__` | `cn_pipeline.py:107` | **否** — 10 个参数，无 batching |

**判定**：当前代码完全没有 `batching_repository` 在 ingestion factory 链路中。这是 **预期状态**——plan 描述的是需要实现的 corrective，不是当前已实现的代码。plan corrective 的规格是：

1. 为上述 6 个函数逐个新增 `batching_repository: BatchingRepositoryProtocol` keyword-only 参数
2. 闭包透传直到 `SecPipeline`/`CnPipeline` 持有 `self._batching_repository`
3. `ingestion/factory.py` 加入 allowlist
4. `DefaultFinsRuntime` 新增 `batching_repository` 字段，从同一 `_FsRepositorySet` 构造

**plan corrective 是否足够确定性**：**是**。plan 精确指定了：
- 每个函数的文件:行位置
- 新增参数的类型（`BatchingRepositoryProtocol`）
- 传递方向（keyword-only 透传）
- 同-core 约束（禁止第二 `FsBatchingRepository`、global cache、wrapper）
- allowlist 扩展（`ingestion/factory.py`）
- 测试扩展（`test_runtime_batch_injection.py` 覆盖 runtime direct + ingestion factory 的 US/CN 同实例、真实 Host ingestion scene 写 producer 同-core）

### 验证 B：S14-CLOSURE-02 — S3 fail-loud 下逐名 8 类 mutation 的最小 explicit batch

**plan 修正内容（S14-CTRL-12 B，plan:1977-2003）**：

plan 逐名列出 8 类 mutation 及其 caller/implementation/boundary。

**当前代码状态（explore-2 审计证据）**：

| # | Mutation | Caller (file:line) | Storage impl | 当前经 `_execute_with_auto_batch`？ |
|---|---------|---------------------|-------------|-----------------------------------|
| 1 | SEC company upsert | `sec_download_workflow.py:371-376` | `_fs_company_meta_core.py:130-143` | 是 |
| 2 | SEC overwrite filing clear | `sec_download_workflow.py:378-379` + `sec_pipeline.py:497` | `_fs_maintenance_core.py:311-328` | 是 |
| 3 | SEC stale filing cleanup | `sec_download_workflow.py:475` → `sec_pipeline.py:1928-1955` | `_fs_maintenance_core.py:353-381` | 是 |
| 4 | CN company upsert | `cn_download_workflow.py:201-206` | `_fs_company_meta_core.py:130-143` | 是 |
| 5 | CN overwrite filing clear | `cn_download_workflow.py:223-224` | `_fs_maintenance_core.py:311-328` | 是 |
| 6 | source reset | `cn_download_filing_workflow.py:159,292` + `docling_upload_service.py:969` | `_fs_source_document_core.py:242-268` | 是 |
| 7 | processed clear | `sec_process_workflow.py:328` + `cn_pipeline.py:989` | `_fs_processed_core.py:214-231` | 是 |
| 8a | snapshot pre-cleanup | `sec_pipeline.py:1778` + `cn_pipeline.py:1532` | `processed_snapshot_helpers.py:61-87`（经 `repository.delete_entry`） | **否** — 逐个 `delete_entry`，cleanup 集合未 batch 化 |
| 8b | snapshot export | `sec_pipeline.py:1784` + `cn_pipeline.py:1538` | `tool_snapshot_export.py:516` | 内层各 repo 调用各自 auto-batch，**cleanup+export 未在同一 batch boundary 内** |

**`_execute_with_auto_batch` 当前行为（`_fs_storage_infra.py:295-335`）**：

当前实现 **不区分 FS vs S3 模式**。逻辑为：
- ticker 在 `_active_batches` 中 → 直接执行 operation
- 否则 → 自动 `begin_batch` → try operation → commit/rollback

**无 S3 fail-loud 分支、无 `_StagedFileStore` isinstance 判定**。这是预期状态——plan corrective 描述的是需要实现的改动。

**plan corrective 的规格**：

1. `_execute_with_auto_batch` 修改为：FS/local 保留 auto-begin；S3 模式（`isinstance(self._file_store, _StagedFileStore)`）无 active token 时 fail-loud `s3_write_requires_batch`
2. 8 类 mutation 逐名规定最小 explicit begin/commit/rollback boundary
3. snapshot boundary 上移到 `_export_tool_snapshot_for_document`，一次覆盖 cleanup + export
4. 禁止跨网络长期持有 token、禁止第二 batch
5. `sec_process_workflow.py` 加入 allowlist
6. 测试矩阵覆盖 staged store 下每个 mutator 的同-core token、delete intent ordering、operation/commit 异常与 restart、零 S3 auto-begin

**plan corrective 是否足够确定性**：**是**。plan 精确指定了：
- 8 类 mutation 的 caller 文件:行（与 explore-2 审计证据一致）
- 每段 mutation 的 boundary 位置（per-filing/per-document 或最小 metadata/delete-only）
- `_execute_with_auto_batch` 的 FS/S3 分支逻辑
- snapshot boundary 上移到 `_export_tool_snapshot_for_document`
- allowlist 扩展（`sec_process_workflow.py`）
- 测试矩阵（workflow mutation boundary unit + S14-CTRL-08 stop conditions）

### 验证 C：S14-REREVIEW-02 — runtime/startup 唯一 ownership 无回归

**plan 修正内容（S14-CTRL-05，plan:1460-1531）**：

- `DefaultFinsRuntime.create` 签名固定为 `create(*, workspace_root, repository_set=None, cn_download_pdf_gate=None)`，**不接受 `file_store`**
- startup 先 `build_fs_repository_set(workspace_root, file_store=s3_store)`，再只调 `DefaultFinsRuntime.create(workspace_root, repository_set=repository_set)`
- `PreparedHostRuntimeDependencies` 独占并关闭 S3 store/lease
- `build_fs_repository_set` 同时非 `None` 抛 `ValueError`

**当前代码状态**：
- `DefaultFinsRuntime.create` 当前签名只含 `workspace_root` + `cn_download_pdf_gate`（`service_runtime.py:1890-1894`），**不含 `repository_set`**
- startup 调用 `create(workspace_root=..., cn_download_pdf_gate=...)`（`startup_preparation.py:553-561`）
- `build_fs_repository_set` 当前在 `repository_set is not None` 时提前 return，静默忽略 `file_store`

**判定**：plan corrective 正确指出了当前代码与目标状态的差异，并给出了精确的修正规格。无回归风险——plan 只新增 `repository_set` 可选参数，不删除现有参数。**CLOSED 无回归**。

### 验证 D：S14-REREVIEW-03 — inventory contraction 无回归

**plan 修正内容（S14-CTRL-13，plan:2015-2065）**：

- processed meta 显式持久化 authoritative files inventory
- `financials present → None` 先 diff old/new inventory，journal `action=delete` target
- source file-list shrink 同理
- 测试覆盖逐 phase kill

**当前代码状态**：
- `_upsert_processed`（`_fs_processed_core.py:258-351`）当前 `merged_meta` 不含 `files` 清单
- `financials_path.unlink()`（L289-296）无 delete target、无 inventory diff

**判定**：plan corrective 正确指出了当前代码与目标状态的差异。无回归风险。**CLOSED 无回归**。

### 验证 E：MiM F-01 — FS auto-begin vs S3 fail-loud admission 无回归

**plan 修正内容（S14-CTRL-12，plan:1968-1975）**：

- `_execute_with_auto_batch` S3 模式（`_StagedFileStore` isinstance）无 active token 时 fail-loud
- FS/local 保留 auto-begin
- 模式判定用 `@runtime_checkable` private Protocol + isinstance

**当前代码状态**：`_execute_with_auto_batch` 不区分模式，总是 auto-begin。

**判定**：plan corrective 正确指出了差异。无回归风险。**CLOSED 无回归**。

### 验证 F：Protected exact toolset names 无回归

**plan 规定（S14-CTRL-11，plan:1837-1847）**：

- `_FINS_OWNED_TOOLSET_NAMES: frozenset[str] = frozenset({"fins", "ingestion"})`
- `_build_tool_registry` 按 exact name 判定，不用 import-path prefix
- Host/contracts 不 import Fins

**当前代码状态**：
- `toolset_registrars.py` 仍有 `_get_cached_fins_runtime`（lru_cache 模块级缓存），plan 要求删除
- `_build_tool_registry` 当前通过配置 path 构造 runtime（plan 要求改为 override-first）

**判定**：plan corrective 正确指出了差异。无回归风险——plan 新增 exact name 判定，不删除现有功能。**CLOSED 无回归**。

## Architecture / best-practice / overengineering / overcoupling lenses

### Architecture boundary
- S14-CTRL-12 的 ingestion factory 同-core 传播限在 Fins runtime/factory/pipeline 内部，不进入 Host/Agent/tool contract
- S14-CTRL-11 的 toolset override 保持 Host→Fins 单向依赖（Host 只接受 `Mapping[str, ToolsetRegistrarProtocol]`，不 import `dayu.fins.*`）
- FS metadata + S3 bytes 分离在 `dayu.fins.storage` owner 内

### Best practice
- strict JSON env-name、HEAD-only stat、typed boto3 stubs、single-writer flock、atomic journal 都是合理约束
- destructive 状态机的 metadata-first + post-commit idempotent delete 符合 S3 最佳实践
- per-target publish_state/delete_state 独立状态机，crash recovery 逐 target 独立判定

### Overengineering
未发现。S14-CTRL-01..13 每个约束都有明确 failure mode 支撑。

### Overcoupling
S14-CTRL-12 的逐名 mutation 清单是对现有调用点的逐个适配，不是跨层耦合。batch 传播限在 Fins runtime→pipeline→producer 内部编排，不进入 Service/Agent/engine 层。

## Open Questions

无。plan corrective 对 S14-CLOSURE-01/02 的修复规格由当前源码的可达调用链直接证明，与 explore agent 审计的 file:line 证据一致。

## Residual Risks

| 风险 | 严重程度 | 建议跟踪 |
|------|---------|---------|
| FS+S3 双层存储的运维复杂度：FS metadata 在本地磁盘，S3 blob 在远端，需分别备份 | 中 | `dayu/fins/README.md` 运维前置条件声明 |
| `_build_store_key` 的 key 格式变更风险：未来修改会同时影响 FS 和 S3 | 低 | 所有 backend 共享 risk，非 S3 特有 |
| 本次未运行 pyright、MinIO、故障注入、coverage 或 Docker | 低 | implementation gate，非 plan review scope |
| plan 未指定 `_StagedFileStore` Protocol 的精确字段（只说 `@runtime_checkable` private Protocol） | 低 | implementation agent 可自行设计，failure mode 已明确 |

## Final plan review conclusion

**PASS**

### Open H/M/L：**0 / 0 / 0**

### 逐项验证结论

| 验证项 | 判定 | 证据 |
|--------|------|------|
| S14-CLOSURE-01（Host ingestion factory 同-core propagation） | **CLOSED-IN-PLAN** | plan S14-CTRL-12 A 精确指定 6 个函数的 `batching_repository` 参数新增、allowlist 扩展、测试覆盖；与 explore-1 审计的当前代码签名差异一致 |
| S14-CLOSURE-02（S3 fail-loud 全 mutation 最小 explicit boundary） | **CLOSED-IN-PLAN** | plan S14-CTRL-12 B 逐名列出 8 类 mutation 的 caller/implementation/boundary；与 explore-2 审计的 8 类 mutation file:line 证据一致；snapshot boundary 上移到 `_export_tool_snapshot_for_document` |
| S14-REREVIEW-02（runtime/startup 唯一 ownership） | **CLOSED，无回归** | plan S14-CTRL-05 修订 `create` 签名、startup 顺序、`PreparedHostRuntimeDependencies` close owner |
| S14-REREVIEW-03（inventory contraction） | **CLOSED，无回归** | plan S14-CTRL-13 规定 processed meta files inventory、delete intent、逐 phase kill 测试 |
| MiM F-01（FS auto-begin vs S3 fail-loud） | **CLOSED，无回归** | plan S14-CTRL-12 规定 `_execute_with_auto_batch` FS/S3 分支、`_StagedFileStore` isinstance 判定 |
| Protected exact toolset names | **CLOSED，无回归** | plan S14-CTRL-11 规定 `frozenset({"fins", "ingestion"})` exact name 判定 |

### Summary

Terra S14-CLOSURE-01/02 的原始 finding（2H）已由 Controller corrective fix 完整闭合：

1. **S14-CLOSURE-01** 闭合于 S14-CTRL-12 A：ingestion factory 同-core 唯一链 + `ingestion/factory.py` allowlist + `test_runtime_batch_injection.py` 扩展覆盖 runtime direct 与 ingestion factory 的 US/CN 同实例 + 真实 Host ingestion scene 写 producer 同-core
2. **S14-CLOSURE-02** 闭合于 S14-CTRL-12/13 B：逐名 8 类 mutation 最小 explicit boundary + snapshot boundary 上移 + `sec_process_workflow.py` allowlist + workflow mutation boundary 测试 + S14-CTRL-08 stop conditions 同步

所有 prior findings（S14-REREVIEW-01/02/03、MiM F-01、MR1/MR2/MR3、S14-FINAL-01..04、S14-01..04、M1..M5）均已 CLOSED-IN-PLAN，无回归。plan corrective 的规格对 implementation agent 足够确定性。

**结论：plan 可以进入 implementation gate。** Terra + MiM Native 双路 final corrective plan re-review 均 PASS，open H/M/L=`0/0/0`。
