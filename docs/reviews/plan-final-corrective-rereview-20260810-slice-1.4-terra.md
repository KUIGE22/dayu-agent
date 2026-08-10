# Slice 1.4 final corrective closure 独立 plan re-review（Terra）

## Scope

- Mode: 独立计划复核（只读源码与计划）
- Branch: `codex/investment-platform`
- Base: `5d7e6bb`
- 本机时间: 2026-08-10 22:22:12 CST
- Output file: `docs/reviews/plan-final-corrective-rereview-20260810-slice-1.4-terra.md`
- 已读取: 根 `AGENTS.md`、master plan 当前 Slice 1.4、`plan-final-closure-rereview-20260810-slice-1.4-terra.md`、`plan-final-closure-rereview-20260810-slice-1.4-mimo-native.md`、`plan-fix-20260810-slice-1.4-final-closure-corrective-deepseek.md`，及 Slice 1.4 的 controller/corrective/final-corrective/final-closure fix 历史。
- Included scope: S14-CLOSURE-01/02；S14-REREVIEW-02/03、MiM F-01、exact toolset names 的无回归复验；真实 Fins mutation、下载与上传调用链。
- Excluded scope: plan/code/tests/README/既有 reviews 修改；MinIO、live/network/model/broker、commit/push/PR。
- Parallel review coverage: 无。

## Findings

### S14-CORRECTIVE-01-未修复-[高]-S3 fail-loud 的“全部真实 mutation”清单遗漏上传与 rejection registry 路径

- **入口/函数**: SEC `run_upload_filing_stream` / `run_upload_material_stream`，CN `upload_filing_stream` / `upload_material_stream`，以及 SEC `run_download_stream_impl` 的 rejection registry 保存。
- **文件(行号)**: `dayu/fins/pipelines/sec_upload_workflow.py:182-205,375-402`；`dayu/fins/pipelines/cn_pipeline.py:547-575,801-835`；`dayu/fins/pipelines/sec_download_workflow.py:464`；`dayu/fins/storage/_fs_company_meta_core.py:130-143`；`dayu/fins/storage/_fs_source_document_core.py:242-268`；`dayu/fins/storage/_fs_maintenance_core.py:65-88`。
- **输入场景**: S3 模式下执行 SEC/CN filing 或 material 的 create/update（尤其 `overwrite=True`），或 SEC 下载结束后保存 rejection registry。
- **实际分支**: 上传路径先调用 `upsert_company_meta_for_upload()`；overwrite 时紧随其后调用 `reset_upload_target_for_overwrite()`，而计划只规定稍后的 `DoclingUploadService.execute_upload` 才开启 per-document batch（plan:1947-1951）。SEC 下载的 per-filing boundary 被计划限定在 `sec_download_workflow.py:425-460`（plan:1925-1931），但 `save_rejection_registry()` 在循环后第 464 行执行。
- **预期行为**: 按 plan:1977-2003，任一真实 repository mutation 都必须有同一 runtime/core 的最小 explicit begin/commit/rollback；不得恢复 S3 auto-begin。
- **实际行为**: `upsert_company_meta`、`reset_source_document` 与 `save_download_rejection_registry` 都进入 `_execute_with_auto_batch`。S3 模式按 plan:1968-1975 改为无 active token 抛 `s3_write_requires_batch`，所以这些调用会在 Docling 的计划边界之前、或下载循环的计划边界之后确定性失败。
- **直接证据**:
  - plan:1988-1997 的八类表只列 SEC/CN 下载 company upsert、clear/cleanup、source reset、processed clear、snapshot；未列 `sec_upload_workflow.py` 的两条 SEC 上传、`cn_pipeline.py` 的两条 CN 上传，亦未列 SEC rejection registry 保存。
  - `sec_upload_workflow.py:182-199,375-392` 与 `cn_pipeline.py:547-564,801-818` 均严格按“company upsert -> source reset -> execute_upload”排序；`reset_upload_target_for_overwrite()` 在 `docling_upload_service.py:935-973` 最终调用 `reset_source_document`。
  - `sec_download_workflow.py:464` 的 registry 写位于 per-filing `async for` 结束后；其仓储实现 `save_download_rejection_registry()` 在 `_fs_maintenance_core.py:83-88` 调用 `_execute_with_auto_batch`。
  - Slice allowlist 未包含 `dayu/fins/pipelines/sec_upload_workflow.py` 或上传 stream 对应测试；故无法在计划允许范围内给 SEC 上传入口注入同 core 的最小 boundary。
- **影响**: S3 下真实上传/overwrite 和带 registry 更新的 SEC 下载不能完成；若实现者为保住现有上传测试而恢复 auto-begin，则直接回归 MiM F-01 并破坏 S14-CLOSURE-02 的 fail-loud 前提。
- **建议改法和验证点**: 将“八类”改为由 `_execute_with_auto_batch` public mutation 与真实 caller 交叉导出的完整清单。至少补入四条 upload company upsert、对应 upload overwrite reset、SEC `save_rejection_registry`，并加入 `sec_upload_workflow.py`、其 Host protocol/同-core 注入点、上传 stream 测试到 allowlist。每个 metadata/delete-only 操作使用同一 runtime batching repository 的独立最小 batch；不可把它包到既有 Docling batch 外层而触发嵌套 token。测试应在 staged store 下分别断言 SEC/CN filing/material upload、overwrite reset、SEC registry 保存的 same-core token、commit/rollback、异常与 restart 收敛、零 S3 auto-begin。
- **修复风险（低/中/高）**: 中；需要扩充计划的 mutation inventory、允许文件和测试矩阵，但不改变 Host/Agent 边界或 S3 admission 契约。
- **严重程度（低/中/高/严重）**: 高。

### S14-CORRECTIVE-02-未修复-[高]-producer 的计划 batch 起点仍跨越真实网络下载，和“不得长持 token”互相矛盾

- **入口/函数**: SEC `run_download_stream_impl` -> `run_download_single_filing_stream`；CN `run_cn_download_stream_impl` -> `run_cn_download_single_filing_stream`。
- **文件(行号)**: plan:1920-1966、1977-1985；`dayu/fins/pipelines/sec_download_workflow.py:425-462`；`dayu/fins/pipelines/sec_download_filing_workflow.py:243-253,404-432`；`dayu/fins/pipelines/cn_download_workflow.py:240-272`；`dayu/fins/pipelines/cn_download_filing_workflow.py:158-221,391-396`。
- **输入场景**: S3 模式下载任一需要远端枚举、HTTP 文件流或 CN PDF 下载/Docling 转换的 filing。
- **实际分支**: plan:1925-1945 要求在 SEC/CN per-ticker 下载循环外层 `begin_batch`，再调用单 filing workflow。该 workflow 在 token 已活跃时执行 SEC `await list_filing_files()` 和 `async for download_files_stream()`，以及 CN `await asyncio.to_thread(_download_report_pdf_with_gate)`、本地 PDF 读取和 Docling 转换。
- **预期行为**: plan:1981-1985 明确禁止跨网络下载长期持有 token；batch 应只覆盖已取得 bytes 后的 blob + metadata 原子写入，且只创建一个同-core storage batch。
- **实际行为**: 计划同时规定 token 在下载循环外层开启，因此网络请求、长文件传输、转换、取消和超时均发生在 active token 存在期间。仅把 `begin_batch` 从循环外层移到现有单 filing 函数开头也无效，因为上述网络 I/O 仍在其后的 `store_file` 之前。
- **直接证据**:
  - `sec_download_workflow.py:445-451` 在 per-filing loop 中进入单 filing async stream；该 stream 先在 `sec_download_filing_workflow.py:243-253` 访问远端 listing，并在 `:404-432` 让 downloader 网络流通过 `store_file` callback 写入。
  - CN loop 在 `cn_download_workflow.py:259-272` 调用单 filing stream；该 stream 在 `cn_download_filing_workflow.py:193-221` 下载并读取远端 PDF，在 `:391-396` 转换 Docling JSON。
  - 计划的唯一 batch 描述没有 fetch/stage 与 storage publish 的切分协议，也没有测试断言任意远端调用期间 active token 不存在；反而明确规定 per-ticker loop outer boundary（plan:1925-1945）。
- **影响**: 单 ticker 的慢源、超时、取消或大文件会长期占有 core 的 active token/锁，使同 ticker 的恢复与后续 mutation 被阻塞；这违反 S14-CLOSURE-02 已写明的约束。若为缓解阻塞把中途写入拆成第二 batch，又违反同一 producer 的 blob+metadata 原子性与“禁止第二 batch”。
- **建议改法和验证点**: 在计划中唯一规定 producer 的两阶段编排：网络枚举/下载（必要时写入 operation-owned 临时文件）必须在无 batch 状态完成；随后只对本地、已验证 bytes 开启一个 per-filing/per-document batch，执行 `store_file`/metadata/journal 并 commit 或 rollback。相应扩充 downloader/persistence/CN workflow allowlist，明确定义临时文件清理与取消/重启责任。测试应记录 batch 生命周期并断言 `list_filing_files`、SEC 下载流、CN PDF 下载和 Docling 转换期间无 active token；验证网络失败/取消零 batch，存储阶段异常只 rollback 唯一 batch，restart 不产生第二 batch或 auto-begin。
- **修复风险（低/中/高）**: 高；这是现有下载器 callback 与存储原子边界的结构性拆分，必须在 implementation 前先唯一化数据暂存、资源清理和故障恢复契约。
- **严重程度（低/中/高/严重）**: 高。

## Open Questions

- 无。两项 finding 均由当前源码调用顺序与 master plan 的明确约束在同一执行路径直接证明。

## Residual Risk

- 未运行 MinIO、故障注入、pyright 或测试；这是计划复核且 implementation gate 仍冻结。两项 High 修复后仍需以 staged-store unit 和真实 MinIO crash/restart matrix 证明闭环。

## Prior-closure regression check

| 项目 | 判定 | 直接计划证据 |
| --- | --- | --- |
| S14-CLOSURE-01 | CLOSED | plan:1197-1232 已纳入 `ingestion/factory.py` allowlist；plan:1890-1909 固定 `DefaultFinsRuntime.batching_repository -> ingestion factory -> pipeline factory -> US/CN pipeline` 的同一实例/同一 core 链；plan:1633-1646 要求 runtime direct、ingestion factory、真实 Host ingestion 写 producer 的 US/CN 测试。 |
| S14-REREVIEW-02 | CLOSED | plan:1462-1530 使 `DefaultFinsRuntime.create` 只接收 `repository_set`，startup 仅以该 set 构造 runtime，且由 `PreparedHostRuntimeDependencies` 唯一 close S3 store/lease。 |
| S14-REREVIEW-03 | CLOSED | plan:2015-2065 固定 processed `files` inventory、old/new diff、swap 前 delete intent、metadata-first delete/recovery 与逐 phase crash 测试。 |
| MiM F-01 | CLOSED | plan:1968-1975 固定 FS/local auto-begin、S3 无 token `s3_write_requires_batch`、同-core token 复用且禁止动态属性猜测；plan:1662-1665 有对应 unit 要求。 |
| protected exact toolset names | CLOSED | plan:1837-1847 固定 `frozenset({"fins", "ingestion"})` 的 exact-name fail-closed，alternate import path 不可绕过；plan:1666-1672 有测试要求。 |

## Final plan review conclusion

**FAIL**

**Open 2 H / 0 M / 0 L。** S14-CLOSURE-01 及之前 S14-REREVIEW-02/03、MiM F-01、exact toolset names 未见回归；但 S14-CLOSURE-02 尚未真实闭合。完成两项最小计划修复并重新复核前，Slice 1.4 不得进入 implementation gate。
