# Slice 1.4 implementation artifact：S3-compatible Fins blob repository

- **Gate**：implementation（accepted slice，待 code review）
- **Work-unit**：investment-platform-restoration
- **Slice**：1.4 S3-compatible Fins blob repository（corrective contract）
- **Status**：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**
  （此前：REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW）
- **Approved plan**：`docs/plans/2026-08-10-investment-platform-restoration.md`（Slice 1.4 ACCEPTED）
- **Errata（accepted）**：
  - runtime-factory test allowlist（`tests/fins/test_cn_download_runtime.py`，commit `df14ec2`）；
  - SEC upload allowlist（`dayu/fins/pipelines/sec_upload_workflow.py`，commit `2466859`，
    含 upload workflow 真实 overwrite 回归测试 owner）。
- **Code review fix closure**：
  `docs/reviews/slice-1.4-code-review-fix-20260811-codex.md`（S14-CR-01..04 全部
  REVIEW FIX APPLIED；MiM observations 全部 REJECTED 未改动）。
- **Round-2 code review fix closure**：
  `docs/reviews/slice-1.4-code-review-round2-fix-20260811-codex.md`（S14-RR-01 /
  S14-RR-02 全部 REVIEW FIX APPLIED；未改动已 REJECTED 的旧 MiM observations）。
- **冻结 WIP hash**：`17b702deabf424a4f737a10965e5daae273b2090051f83cc402a8a019c986901`
  - **原始计算方法**（按 acceptance review 记录）：非文档 tracked WIP binary diff 的
    SHA-256（Controller 在 sec-upload erratum accepted closure 冻结，plan L702）。
  - **最终验证**：本 repo 内无脚本化命令可直接复现该 hash 计算（算法细节由 Controller
    在 erratum 流程记录）；本次实测 `git diff --binary` 的 tracked 非文档 WIP 在
    accepted plan commit `87e8fc6` 与 `2466859` 前后均产出
    `2ffc30c5a80d73d7ad0a5b85e86f435c6d3b818f92ecaa24951d123f05e39fa1`，
    证明实现 WIP 未被 plan commit 改变，冻结标识保持有效；erratum 后 production 未再修改
    （仅两个 upload test owner 增加回归），因此该冻结标识覆盖至本 artifact。
  - **fix gate 后说明**：code-review fix（S14-CR-01..04）属于 implementation gate
    FIX 阶段允许的生产修改，已在本 artifact 第 3.x 节与 fix artifact 逐项记录。

## 1. Scope / non-goals / allowed files

按 approved plan Allowed 精确清单实施（含两份 erratum 追加的文件）；未扩大 allowlist。
冻结项（Fins/engine 公共协议签名与语义、`dayu/contracts/*`、investment domain、
`dayu/config/*`、Compose、API/UI、migration、四个 platform lock）保持只读。
`tests/fins/storage_testkit.py` 相对 HEAD 零 diff（`git diff` 为空）。

## 2. Changed files（63 个，均属 allowlist）

- **新增（storage）**：`dayu/fins/storage/s3_settings.py`、`s3_file_store.py`、
  `store_source.py`、`remote_op_journal.py`、`writer_lease.py`；
- **修改（storage / runtime / producer）**：`dayu/fins/storage/__init__.py`、
  `_fs_storage_infra.py`、`_fs_blob_core.py`、`_fs_source_document_core.py`、
  `_fs_processed_core.py`、`_fs_maintenance_core.py`、`_fs_company_meta_core.py`、
  `_fs_repository_factory.py`、`file_store.py`、`local_file_store.py`、
  `service_runtime.py`、`toolset_registrars.py`、`dayu/services/startup_preparation.py`、
  `dayu/host/scene_preparer.py`、`dayu/host/host.py`、
  `dayu/fins/pipelines/{factory,sec_pipeline,cn_pipeline,sec_download_workflow,
  cn_download_workflow,cn_download_filing_workflow,cn_download_protocols,
  docling_upload_service,tool_snapshot_export,sec_upload_workflow}.py`、
  `dayu/fins/ingestion/factory.py`、`rejected_6k_rescue.py`、`active_6k_retriage.py`；
- **新增测试**：`tests/fins/test_s3_settings.py`、`test_s3_file_store.py`、
  `test_store_source.py`、`test_remote_op_journal.py`、`test_writer_lease.py`、
  `test_runtime_batch_injection.py`、`test_batch_mode_admission.py`、
  `test_batch_admission_classification.py`、`test_destructive_inventory_contraction.py`、
  `test_rebuild_staged_store.py`、`test_per_filing_terminal_state.py`、
  `test_delete_entry_staged_delete.py`、`test_upload_overwrite_batch.py`、
  `test_cn_to_thread_boundary.py`、`test_cn_temp_pdf_ownership.py`、
  `tests/integration/investment/test_fins_s3_blob_repository_minio.py`；
- **修改测试**：`test_sec_pipeline_upload_filing_stream.py`、
  `test_sec_pipeline_upload_material_stream.py`（本次 overwrite 真实 workflow 回归）、
  `test_cn_download_runtime.py`（erratum）、`test_cn_download_workflow.py`、
  `test_storage_batch_recovery.py`、`test_service_startup_preparation.py`、
  `test_scene_execution.py`、`test_cli_running_config.py`、`test_docling_upload_service.py`、
  `test_docling_upload_service_integration.py`、`test_sec_pipeline_download.py`、
  `test_sec_downloader.py`、`test_tool_snapshot_export.py`、`test_rejected_6k_rescue.py`、
  `test_active_6k_retriage.py`、`test_sec_pipeline_upload_filing_stream.py`、
  `test_sec_pipeline_upload_material_stream.py`、`test_cn_pipeline.py`、
  `test_batch_admission_classification.py`；
- **文档/依赖**：`dayu/fins/README.md`、`dayu/host/README.md`、`dayu/README.md`、
  `pyproject.toml`、`constraints/min-py311.txt`、`constraints/lock-common-py311.txt`。

## 3. Implemented plan items（summary）

- S14-CTRL-01..13 全部契约落地：settings/secret boundary、startup 顺序与资源生命周期、
  byte-path matrix、remote-op journal 状态机/commit ordering/幂等恢复、staged-delete
  destructive 状态机与 inventory contraction、per-operation BatchAdmission 分类、
  同-core batch 唯一链与七条 producer 边界、网络三段边界与 per-filing terminal 状态机、
  CN to_thread 边界与临时 PDF owner（`CnPreparationGate`/stale-temp sweep）、单 writer
  lease、Host toolset override 唯一装配、exact toolset name fail-closed。
- 本次 follow-up（erratum 2466859 要求）：在既有两个 upload workflow test owner
  （`test_sec_pipeline_upload_filing_stream.py` / `test_sec_pipeline_upload_material_stream.py`）
  各新增 2 条真实 `SecPipeline` overwrite 回归：service explicit batch 恰好一次
  begin/commit（recording batching 只计 service batch）；每次真实 `reset_source_document`
  时经同-core 观察断言 token 已 active（负向区分 reset-induced pre-AUTO）；reset 后、
  commit 前注入失败 => 恰好一次 rollback、零 commit、旧 source/meta/blob bytes 仍可读；
  filing/material 各自覆盖；保留既有 action/status/document-id/event-order 断言。
  未新增生产 seam/wrapper/compat/second batch，未扩大 allowlist。

### 3.1 Code-review fix（S14-CR-01..04，2026-08-11）

按 Controller 裁决 `docs/reviews/code-review-adjudication-20260811-slice-1.4-s3-blob-repository-codex.md`
仅处理 accepted S14-CR-01..04；全部 MiM observations 已 REJECTED，未顺手改动。逐项
详情见 `docs/reviews/slice-1.4-code-review-fix-20260811-codex.md`，此处只列生产改动真源：

- **S14-CR-01/02（CN 阶段 A/B timeout 与 slot 绑定）**——
  `dayu/fins/pipelines/cn_download_filing_workflow.py`：阶段 A 以
  `asyncio.timeout(provider_download_timeout_seconds)` 包裹 outer 等待（参数真实消费）；
  各阶段 A/B 实际 inner future 经 `asyncio.create_task(asyncio.to_thread(...))` 建立、
  以 `asyncio.shield` 保护（`Task.cancel` 会级联取消 `_fut_waiter`，必须 shield），
  `_bind_preparation_inner` 用 completion callback 把 slot 与 inner 绑定：outer
  timeout/cancel/生成器关闭只停止消费，绝不提前 release、绝不取消 worker；最后一个真实
  inner 完成（含异常）时由 done callback 做 late 清理（unlink 临时 PDF）并恰好 release
  一次；`_PreparationSlotOwnership` 记录 pending/abandoned/released 状态，正常路径由阶段
  B 结束显式释放。阶段 B read/Docling 同样 shield + 绑定。
- **S14-CR-03（publish 匹配唯一真源）**——`dayu/fins/storage/_fs_storage_infra.py`：
  新增模块级 `_remote_matches_expected(remote, *, sha256, size)`，`_publish_one_target`
  模糊 Copy 判定与 `_recover_single_remote_op` recovery 判定统一改为 SHA-256 **且**
  size 同时匹配才可置 `final_verified`；`_head_expected` 复用同一真源。
- **S14-CR-04（journal 严格 fail-closed）**——
  `dayu/fins/storage/remote_op_journal.py`：`read_journal` 严格区分缺失（None）与损坏
  （存在但 JSON/schema/phase/action/state/key/digest/size/唯一性任一非法 =>
  `RemoteOpJournalError`）；`_journal_from_dict` 逐字段严格校验并检查 target 唯一性。
  `dayu/fins/storage/_fs_storage_infra.py`：`_recover_remote_ops` 不再把 `None`/损坏
  journal 静默跳过，损坏 journal 稳定 fail closed 且保留 journal/FS staging/远端 objects；
  `_stage_delete_one_key` 对同一 operation 内同一 key 的重复 delete intent 幂等收敛
  （`delete_entry` 与 inventory diff 可能各自记录），保证 write 侧不产生重复 target。

### 3.2 Round-2 code-review fix（S14-RR-01/02，2026-08-11）

按 Controller 裁决第 4/5 节（`code-review-adjudication-20260811-slice-1.4-s3-blob-repository-codex.md`）
只处理 accepted `S14-RR-01`（High）与 `S14-RR-02`（Medium）；已 REJECTED 的旧 MiM
observations 未改动，未引入 compat/glue/prefix sweep/放宽 reader。逐项详情见
`docs/reviews/slice-1.4-code-review-round2-fix-20260811-codex.md`：

- **S14-RR-01（journal 身份绑定 fail-closed）**——`dayu/fins/storage/remote_op_journal.py`：
  `read_journal` 把调用方传入的 `operation_id`（journal 文件名身份）作为期望身份传入
  `_journal_from_dict`；payload `operation_id` 必须精确相等，且每个 publish target 的
  `staging_key` 必须属于 `.dayu-staging/{operation_id}/` 命名空间；任一不一致抛
  `RemoteOpJournalError`。`_recover_remote_ops` 在 `_recover_orphan_batch_dirs` 之前枚举
  并读取，因此身份 mismatch 在任何远端 publish/delete 与 FS swap 之前 fail closed，
  保留原 journal、FS batch staging 与远端 staging/final bytes。
- **S14-RR-02（inner/temp owner 与可选 slot owner 分离）**——
  `dayu/fins/pipelines/cn_download_filing_workflow.py`：`_PreparationSlotOwnership`
  重构为 `_PreparationInnerOwner`（`gate: CnPreparationGate | None`），owner 始终存在
  并绑定所有阶段 A/B 实际 inner future 的 late completion cleanup；无 gate
  （standalone/FS `CnPipeline` 默认 `preparation_gate=None`）时 outer timeout/cancel 后
  late provider 完成即回收 exact 临时 PDF，不持有任何容量 slot；有 gate 时 done
  callback 仍在最后一个真实 inner 完成后恰好 release 一次 slot（gate 路径语义不变）。

## 4. Validation

- 聚焦 workflow/service 测试：两个 upload owner + `test_upload_overwrite_batch.py` +
  `test_docling_upload_service.py` + `test_cn_pipeline.py` 共 41 passed；
- 完整 `tests/fins/`：2126 -> 2138 ->（覆盖语料含 MinIO）**5967 passed / 2 skipped**（
  `tests/fins + tests/application + tests/engine + MinIO integration`，`env -u
  SERPER_API_KEY`）；
- changed prod/tests pyright：**0 errors**（全树仅 15×`test_web_tools.py` +
  2×`docling_processor.py` + 2×`test_docling_processor_helpers.py` 为既有无关错误，本
  Slice 文件未扩散）；
- Ruff F/I+default：changed 文件 current **0** / HEAD baseline **30**（delta **-30**，
  净改善）；strict added-line forbidden scan（`Any/object/cast/ignore/getattr/hasattr`）
  **0 hits**（scene_preparer/infra 两 import 行按 Controller 方案闭合：baseline exact 行
  + `Literal` 真实约束 / `typing.BinaryIO`；AST 语义使用 delta=0）；
- `git diff --check` 干净；`tests/fins/storage_testkit.py` 零 diff；
- **覆盖证据（复用，未重跑长语料）**：Controller 已从
  `workspace/tmp/coverage-changed-final.json` 机械核对全部 changed production modules
  **BELOW80=none**；此前三项低覆盖模块最终为 `_fs_blob_core.py` 89.47%、
  `_fs_maintenance_core.py` 89.19%、`s3_file_store.py` 87.34%（5967 passed / 2 skipped）；
- 依赖 lane：clean Python 3.11 venv 分别用 `constraints/min-py311.txt` 与
  `constraints/lock-macos-arm64-py311.txt` 安装 `.[test,dev]`，exact pins 解析无冲突，
  双 lane focused 166 tests 通过、pyright 0 errors；receipts 已记录（min: boto3 1.34.0/
  botocore 1.34.0/s3transfer 0.9.0/jmespath 1.0.1/stubs 1.34.0/1.34.0/1.34.0/0.9.0；
  current: 1.43.67/1.43.67/0.19.2/1.1.0/stubs 1.43.67/1.43.67/1.43.66/0.16.0）。

### 4.1 Fix-gate validation（S14-CR-01..04，2026-08-11 独立执行）

- focused fault-injection（本次新增/改写的 adversarial 测试）：
  - CN 阶段 A 参数 timeout / outer cancel during A/B / late success / late exception /
    容量 1 第二 filing 阻塞——`tests/fins/test_cn_to_thread_boundary.py` 9 passed；
  - publish 匹配矩阵（same-size/diff-SHA、same-SHA/diff-size、完全匹配、staging 缺失）
    与 startup fail-closed（corrupt JSON/partial target/unknown phase/duplicate key 且
    journal+staging+remote 全保留）——`tests/fins/test_storage_batch_recovery.py` +
    `test_remote_op_journal.py` 全部 passed；
  - delete intent 去重——`tests/fins/test_delete_entry_staged_delete.py`；
- 逐文件 statement coverage（`coverage run` 语料 = `tests/fins` 单测 + MinIO integration
  11 case）：`cn_download_filing_workflow.py` **84%**、`_fs_storage_infra.py` **88%**、
  `remote_op_journal.py` **92%**，全部 `>=80%`（三文件均为本次再次修改生产文件）；
- changed pyright：三生产文件 + 四个测试文件 **0 errors / 0 warnings**；全树 pyright 仅
  既有 13×`test_web_tools.py` + 2×`docling_processor.py` + 2×`test_docling_processor_helpers.py`
  （非本 Slice 文件，未扩散）；
- Ruff F/I + default：全部 changed 文件 **0**（另修复 `_fs_storage_infra.py` 与
  `test_storage_batch_recovery.py` 两处 import-order baseline I001）；
- strict added-line forbidden scan（`Any/object/cast/ignore/getattr/hasattr`）：本次新增行
  **0 hits**（`_fs_storage_infra.py` 既有 `Any` 行与 `test_storage_batch_recovery.py`
  既有 `object`/`ignore` 行为 baseline，非新增行）；
- `git diff --check` 干净；MinIO integration 11 case 全部 passed（镜像可用，真实执行）。

### 4.2 Round-2 fix-gate validation（S14-RR-01/02，2026-08-11 独立执行）

- focused fault-injection（本次新增/改写的 adversarial 测试）：
  - journal 身份绑定：`test_remote_op_journal.py` 新增
    `test_operation_id_mismatch_fails_closed` / `test_staging_key_namespace_mismatch_fails_closed`；
    `test_storage_batch_recovery.py` 新增 restart fault tests
    `test_startup_operation_id_mismatch_fails_closed_preserves_all` /
    `test_startup_staging_namespace_mismatch_fails_closed_preserves_all`，断言零
    publish/delete/FS swap 且 journal/batch staging/远端 bytes 全保留；
  - CN 无 gate 三段边界：`test_cn_to_thread_boundary.py` 新增
    `test_stage_a_param_timeout_no_gate_late_success_cleans_pdf` /
    `test_stage_a_param_timeout_no_gate_late_exception_stays_closed` /
    `test_outer_cancel_during_stage_a_no_gate_cleans_late_pdf`（`preparation_gate=None`
    路径的 late success/late exception、零 B/C、零 repository 写入、最终零临时 PDF）；
  - focused 全绿：上述文件 + 相关 CN/journal/recovery/delete 测试 **172 passed**；
- 完整 corpus：`tests/fins` + MinIO integration 11 case **2213 passed / 0 failed**
  （`env -u SERPER_API_KEY`；MinIO 镜像可用，真实执行）；
- 逐文件 statement coverage（pytest-cov broad source
  `--cov=dayu.fins --cov=dayu.host --cov=dayu.services` + JSON 机械核对，
  corpus = `tests/fins` + MinIO integration）：`cn_download_filing_workflow.py` **84.2%**
  （363/431）、`_fs_storage_infra.py` **88.0%**（718/816）、`remote_op_journal.py` **92.6%**
  （174/188），全部 `>=80%`（三文件均为本次再次修改生产文件）；
- changed pyright：三生产文件 + 三测试文件 **0 errors / 0 warnings**（全树 pyright 仅
  既有 13×`test_web_tools.py` + 2×`docling_processor.py` + 2×`test_docling_processor_helpers.py`
  于非本 Slice 文件，未扩散）；
- Ruff F/I + default：全部 changed 文件 **0**；
- strict added-line forbidden scan（`Any/object/cast/ignore/getattr/hasattr`）：本次新增行
  **0 hits**（`test_storage_batch_recovery.py` 既有 `object`/`ignore` 行为 baseline，
  round-1 已记录）；
- `git diff --check` 干净；`tests/fins/storage_testkit.py` 零 diff（未触碰）。

## 5. Docs decision

`dayu/fins/README.md` 新增 §8 S3-compatible blob 仓储全节（byte-path matrix、settings、
startup、journal/recovery、BatchAdmission 分类、producer 边界、三段边界/per-filing
terminal、CN to_thread/临时 PDF owner、destructive 状态机、单 writer 拓扑、测试命令）；
`dayu/host/README.md` 新增 §11.1 Fins toolset override 装配；`dayu/README.md` §3.5 补
startup 唯一 runtime 注入 override 装配边界。README 触发规则全部命中并同步。

## 6. Plan gaps / findings

- 实施期两处 allowlist gap（`test_cn_download_runtime.py`、`sec_upload_workflow.py`）均已
  经 Controller minimal erratum + Terra/MiM 双路 re-review PASS/open0 闭合（commit
  `df14ec2`、`2466859`）；
- 无其它未闭合 gap；无 deferred finding。

## 7. Residual risks（owner: Slice 1.4 / later work-unit）

- CN 阶段 B（`pdf_path.read_bytes` + 默认/注入 Docling 转换）为无界 CPU/IO 工作，占用
  执行单元容量但不持有 token/batch/repository；由外层 cancel_checker 边界与
  warning/metrics 观测（后续 phase/work unit 引入更强执行治理时可收敛）；
- 后续 filing 只在 `CnPreparationGate` slot 可用时可启动；阶段 C 无独立 hard timeout，
  失败按 commit-start 前后语义收敛；
- 跨主机共享 FS 上的 writer lease 视为 unsupported 且 fail closed（跨主机互斥归后续
  durable job owner）；
- MinIO integration lane 的 crash 窗口覆盖 staged 与 first-copy 两处代表性窗口；更细
  fault matrix（destructive 每 phase kill 等）由 unit journal/recovery 测试覆盖；
- 全树 pyright 既有 13+2+2 错误位于非本 Slice 文件（test_web_tools /
  docling_processor / test_docling_processor_helpers），未扩散；
- frozen WIP hash 的精确复现命令未内化到 repo（按 acceptance 记录引用；
  tracked non-doc diff 在 plan commit 前后一致，冻结标识有效）。

## 8. Completion / stop status

accepted plan 全部条目已完成（含两项 erratum 的测试补强），code-review fix gate
（S14-CR-01..04）与 round-2 code-review fix gate（S14-RR-01/02）全部 REVIEW FIX
APPLIED，validation 全绿，未降级任何 residual。
最终 corrective re-review：
`docs/reviews/code-rereview-round2-20260811-slice-1.4-s3-blob-repository-terra.md`
与 `docs/reviews/code-rereview-round2-20260811-slice-1.4-s3-blob-repository-mim.md`
均为 **PASS / open H=0 M=0 L=0**；S14-CR-01..04、S14-RR-01/02 全部 CLOSED，
无 accepted finding 剩余。
**Status: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**（不 push/PR/merge）。
