# Slice 1.4 S3-compatible Fins blob repository final-closure 独立 plan re-review（Terra）

## 审查目标与边界

- **本机时间**：2026-08-10（Asia/Shanghai；按任务指定 artifact 名输出）
- **基线**：`5d7e6bb`；分支：`codex/investment-platform`
- **目标**：`docs/plans/2026-08-10-investment-platform-restoration.md` 的当前 Slice 1.4，重点复核 S14-CTRL-04/05/08/10/11/12/13。
- **已完整读取**：根 `AGENTS.md`、master plan 当前 Slice 1.4、Terra 213617、MiM Native 213634、final-closure fix，以及 Slice 1.4 的既有 controller/corrective/final-corrective fix artifacts。
- **只读边界**：未改 plan、代码、测试、README 或既有 review；未运行 live/MinIO/model/broker，未安装依赖、commit、push 或 PR。

## 已验证 assumptions

| 假设 | 直接证据与判定 |
| --- | --- |
| S14-REREVIEW-02 的 runtime/startup 唯一 owner 已闭合 | **已闭合**。S14-CTRL-05 将 `DefaultFinsRuntime.create` 固定为只接收可选 `repository_set`，startup 先构造 S3-backed set 再只传该 set；`PreparedHostRuntimeDependencies` 是唯一 store/lease close owner。该调用顺序、`file_store` 禁入 `create`、单次 recovery 和 exact-once close 均有明确测试要求。 |
| S14-REREVIEW-03 的 processed/source authoritative inventory contraction 已闭合 | **已闭合**。S14-CTRL-13 明确 processed `files` inventory、`financials present -> None` 与 source files shrink 的 old/new diff、swap 前 delete intent、post-commit delete、逐 phase crash/restart 测试；没有第二 inventory 真源或 prefix sweep。 |
| MiM F-01 的 FS auto-begin 与 S3 admission 已闭合 | **核心歧义已闭合**。S14-CTRL-12 明确 FS/local 保留 auto-begin，`_StagedFileStore` S3 模式无 active token 必须抛 `s3_write_requires_batch`，并要求零 begin/commit 副作用测试。该正确契约同时暴露了 finding 02 中所有真实 S3 mutator 都必须显式拥有边界的要求。 |
| protected exact toolset names 可防 alternate import-path 旁路 | **已闭合**。S14-CTRL-11 使用 frozen exact-name 集合 `{fins, ingestion}`，override 缺失即稳定 fail-closed，不依赖 `dayu.fins.*` import path；Host/contracts 仍只依赖 registrar protocol，不反向 import Fins。 |
| S14-REREVIEW-01 的同-core 传播覆盖真实 Host ingestion route | **未闭合，见 finding 01**。当前 plan 仅覆盖 runtime direct `_build_pipeline_for_ticker` 链，遗漏 runtime 实际交给 ingestion toolset 的 factory 链。 |
| 七 producer 的显式 boundary 覆盖同一 workflow 内的前置/后置 destructive 和 metadata mutation | **未闭合，见 finding 02**。计划指向的循环位置晚于真实 `upsert`/overwrite clear，且早于 stale cleanup；S3 fail-loud 会将它们变成确定性失败。 |

## Findings

### S14-CLOSURE-01-未修复-[高]-Host ingestion factory 绕过计划规定的唯一 batching 传播链

- **位置**: S14-CTRL-12 的“同-core BatchToken 唯一来源/逐层显式传递”（plan:1772-1796）与 Slice 1.4 Allowed（plan:1152-1170）。
- **问题类型**: 架构边界 / 不可直接实施 / allowlist 缺口 / 同-core 状态机漏洞。
- **当前写法**: plan 规定 `DefaultFinsRuntime._build_pipeline_for_ticker -> _build_pipeline -> get_pipeline_from_normalized_ticker -> SecPipeline/CnPipeline` 传递唯一 `batching_repository`，并断言 Host scene 的 `ingestion` 使用同一 repository set；同时明确 `FinsToolService` 不持有 batching。
- **反例/失败场景**: 真实 Host `ingestion` toolset 不走 `_build_pipeline_for_ticker`。它调用 `runtime.build_ingestion_service_factory()`；runtime 再调用 `dayu.fins.ingestion.factory.build_ingestion_service_factory()`，后者只闭包捕获五个窄仓储和 processor registry，并调用 `build_ingestion_service_from_normalized_ticker()`。该函数再调用 pipeline factory，却没有 `batching_repository` 参数。按 plan 改造后，pipeline 收到已注入的五窄仓储但没有同-core batch capability；它要么得到 `None` 并在 producer 处失败，要么重新建 core/猜测私有字段，后二者直接违反 S14-CTRL-12。
- **为什么有问题**: 这是 S14-CTRL-11 要求保留的真实 `ingestion` Host tool path，而不是 standalone CLI 旁路。它使“真实 Host scene ingestion 同一 repository_set”的 S14-CTRL-08 black-box 无法按计划实施，并重新打开 S14-REREVIEW-01 的同-core保证。
- **直接证据**:
  - `DefaultFinsRuntime.build_ingestion_service_factory()` 只传五窄仓储和 registry，当前 `dayu/fins/service_runtime.py:2497-2508`；
  - `dayu/fins/ingestion/factory.py:30-39, 91-101` 的签名和闭包均没有 batching 参数；
  - `dayu/fins/pipelines/factory.py:116-160` 的 `build_ingestion_service_from_normalized_ticker` 也没有该参数，最终只传五窄仓储给 `get_pipeline_from_normalized_ticker`；
  - Allowed 包含 `dayu/fins/pipelines/factory.py`，但不包含 `dayu/fins/ingestion/factory.py`（plan:1152-1170）；S14-CTRL-12 的指定传播链亦不含它（plan:1779-1787）。
- **影响**: S3 模式下 Host scene ingestion 不能获得 active same-core token；实现者若为让它可运行而在 pipeline/ingestion factory 建第二 `FsBatchingRepository`，blob 与 metadata 会落在不同 `_active_batches` 空间；若不建则触发 `s3_write_requires_batch` 或运行期空 capability。该缺口阻断 final-closure gate。
- **建议改法和验证点**: 将 `dayu/fins/ingestion/factory.py` 加入 allowlist，并唯一化链路为 `DefaultFinsRuntime.batching_repository -> build_ingestion_service_factory(..., batching_repository) -> build_ingestion_service_from_normalized_ticker(..., batching_repository) -> get_pipeline_from_normalized_ticker(..., batching_repository)`。该 capability 仍只停留在 Fins runtime/factory/pipeline 内部，不进入 Host、Agent、tool contract 或 global wrapper。扩展 `test_runtime_batch_injection.py` 断言 runtime 的 ingestion factory 对 US/CN 都传入同一实例/同一 core；真实 Host `ingestion` scene 测试须执行一条写 producer 并断言无第二 core、无无-token admission。
- **修复风险（低/中/高）**: 低；是现有 Fins-internal factory 的一条显式参数传播和 allowlist/test 补全，不需新增事务 API。
- **严重程度（低/中/高/严重）**: 高。

### S14-CLOSURE-02-未修复-[高]-S3 fail-loud 与真实下载/快照工作流的 boundary 顺序矛盾，非 producer mutation 会在 token 前后失败

- **位置**: S14-CTRL-12 七 producer boundary（plan:1798-1844）及 S3 admission（plan:1846-1853）；S14-CTRL-13 destructive paths。
- **问题类型**: 状态机漏洞 / 顺序错误 / 测试缺口 / 不可直接实施。
- **当前写法**: SEC/CN 的 explicit batch 被定位在当前下载循环的外层（SEC `425-460`、CN `259-264`）；tool snapshot 的 explicit batch 被定位为 `export_tool_snapshot` 内的 per-document boundary。S3 模式则让任何 `_execute_with_auto_batch` 在无 active token 时 fail-loud。
- **反例/失败场景**: 当前真实 SEC workflow 在指定 SEC 循环之前调用 `host._upsert_company_meta`（`sec_download_workflow.py:371-376`）和 overwrite `clear_filing_documents`（`:378-379`），并在循环之后调用 `cleanup_stale_filing_documents`（`:475`，helper `sec_pipeline.py:1951-1955`）。CN 在指定 candidate 循环之前调用 overwrite clear（`cn_download_workflow.py:224`）。这些 repository mutator 当前都经 `_execute_with_auto_batch`；S3 admission 生效后，没有 active token 就确定性抛 `s3_write_requires_batch`。同样，SEC/CN 都先执行 `_cleanup_processed_snapshot_dir`，再调用计划指定的 `export_tool_snapshot`（SEC `sec_pipeline.py:1777-1799`；CN `cn_pipeline.py:1531-1552`）；若 cleanup 是 delete mutation，它也发生在 snapshot batch 之前。
- **为什么有问题**: 这不是要求恢复 S3 auto-begin。S14-CTRL-13 已规定 clear/stale cleanup 必须经 journal 化 metadata-first delete，正需要显式 same-core batch。计划却只规定七个 `store_file` producer 的边界，未给所有其前后发生的真实 metadata/delete mutation 一个不跨网络、可验证的 explicit boundary。若把一个 token 粗暴包住完整下载网络循环，又会不必要地长期占有 ticker lock；若不补边界，production S3 overwrite/cleanup 直接 fail-loud。
- **直接证据**:
  - `_execute_with_auto_batch` 当前是 company/source/processed/maintenance mutator 的共同分发点（`dayu/fins/storage/_fs_company_meta_core.py:143`、`_fs_maintenance_core.py:83,324,375`、`_fs_processed_core.py:48,69,90,182,227`），其现行为无 token 自动 begin（`_fs_storage_infra.py:295-335`）；
  - S14-CTRL-12 修订后明确 S3 无 active token 禁自动 begin/commit（plan:1846-1853）；
  - 计划自身把 SEC/CN begin 位置限定为 `425-460`/`259-264`（plan:1803-1821），但上述真实 mutator 位于该区间之外；
  - S14-CTRL-08 只要求 generic destructive fault matrix 和七 producer crash matrix，未要求真实 SEC/CN overwrite（company upsert + clear + filing + stale cleanup）及 snapshot pre-cleanup 在 S3 admission 下完成（plan:1601-1614）。
- **影响**: S3 mode 的正常 download overwrite、stale cleanup 与 process overwrite 可能在第一个前置 mutation 就中止；或者实现者为通过测试而重新允许 auto-begin，反向破坏 MiM F-01 的 fail-loud 契约和 producer-controlled atomicity。两种结果都不满足 final closure。
- **建议改法和验证点**: 在 S14-CTRL-12/13 逐一列出所有 S3-mode mutating orchestration boundary，而非仅列 `store_file` producer：为 company upsert、filing clear、stale cleanup、source reset、processed clear 和 snapshot pre-cleanup 各规定最小 explicit begin/commit/rollback 边界；blob+其 metadata 仍使用既有 producer boundary。不得跨网络下载持有一个大 token，不得让 Host/Agent 接触 batch。补充 plan 到实际 owner 的测试：SEC 与 CN `overwrite=True`、snapshot 含旧文件 cleanup、source/processed destructive branches，在 staged store 下断言每一 mutator 有同-core token、journal delete intent/commit ordering 正确、零 S3 auto-begin，并覆盖 operation/commit exception 与 restart。
- **修复风险（低/中/高）**: 中；需要精确收缩每段 mutation 的原子范围并扩展已有 workflow 测试，但不需要新 storage 真源或 wrapper。
- **严重程度（低/中/高/严重）**: 高。

## 其余 lenses

- **Architecture / ownership**：S14-CTRL-05 的 `repository_set` 注入和唯一 close owner 已无 `file_store` 双参或第二 ownership；S14-CTRL-11 的 protected exact names 保持 Host→Fins 单向依赖。finding 01 的修复应留在 Fins 内部，不能借由 Host wrapper 传递 repository。
- **Recovery / authoritative inventory**：S14-CTRL-04/13 的 publish/delete per-target journal、processed inventory contraction、metadata-first delete 和 fail-closed recovery 具有明确真源，未发现第二 inventory 或 recovery owner。
- **Best practice / optimality**：FS metadata + S3 blobs、复用既有 `BatchingRepositoryProtocol`、不新增事务 API 是最小且正确的方向。finding 02 建议最小 mutation boundary，避免为方便而把下载网络过程长期包在一个 batch。
- **Overengineering / overcoupling**：未发现需要增加新 protocol、facade、全局 cache 或第二 repository set 的证据；两项修复均为现有调用图的显式 Fins-internal 传播/排序补全。

## Open questions

无。两个 finding 均由当前源码的可达调用链、当前 Slice allowlist 与明确 S3 admission 契约直接证明。

## Residual risks

- 未运行 MinIO、故障注入、resolver、pyright 或 coverage；它们是修复后的 implementation gate，不能替代本次静态 callgraph finding 的关闭。
- FS metadata 与 S3 blobs 需要独立备份仍是已知运维风险，应按既有 `dayu/fins/README.md` 责任在实现后验证；不构成此轮新 finding。

## Conclusion

**FAIL**。

Open H/M/L：**2 / 0 / 0**。

S14-REREVIEW-02、S14-REREVIEW-03、MiM F-01 的 admission 定义以及 protected exact toolset names 均已在 plan 中具体闭合；但 Host ingestion factory 的遗漏和 S3 fail-loud 下 workflow boundary 的顺序缺口会使真实生产路径无法安全实施。完成两项最小修复并补齐上述 host/workflow tests 后，才可重新进入 final-closure re-review。
