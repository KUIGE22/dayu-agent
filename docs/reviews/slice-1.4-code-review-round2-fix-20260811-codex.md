# Slice 1.4 S3-compatible Fins blob repository round-2 code-review fix（DeepSeek Flash fix agent）

- **Gate**：Gateflow / code review ROUND-2 FIX gate（S14-RR-01 / S14-RR-02）
- **Worker**：DeepSeek Flash fix agent（非 controller；不启动 gateflow、不重做
  plan/review、不 commit/push/PR/merge、不进入 re-review）
- **日期**：2026-08-11
- **裁决**：`docs/reviews/code-review-adjudication-20260811-slice-1.4-s3-blob-repository-codex.md`
  （Round-1 corrective re-review 裁决：accepted **S14-RR-01 High** 与 **S14-RR-02 Medium**；
  S14-CR-03 与写侧 duplicate delete intent 已闭合；旧 MiM observations 维持 REJECTED）
- **Round-1 re-review**：
  - `docs/reviews/code-rereview-20260811-slice-1.4-s3-blob-repository-terra.md`（FAIL，1H/1M/0L）
  - `docs/reviews/code-rereview-20260811-slice-1.4-s3-blob-repository-mim.md`（PASS，0H/0M/0L）
- **Round-1 fix artifact**：`docs/reviews/slice-1.4-code-review-fix-20260811-codex.md`
- **状态**：**CLOSED / DUAL RE-REVIEW PASS**
- **Implementation artifact 状态**：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**

## Scope / 约束

- 只修 accepted `S14-RR-01`（High）与 `S14-RR-02`（Medium）；已 REJECTED 的旧 MiM
  observations（S3 directory delete intent、staged delete drift、bounded publish retry、
  runtime asserts、cleanup state/journal window、presign expires type）严禁顺手改。
- 未新增 `Any`/`object`/`cast`/`ignore`/`getattr`/`hasattr`（新增行扫描 0）、未新增
  glue/compat/prefix sweep/第二资源 owner、未放宽 journal reader、未放宽 fail-closed
  语义。
- 未清理或覆盖其他 WIP；`tests/fins/storage_testkit.py` 零 diff。
- 若 CN 生命周期需要计划外公共契约或现有 allowlist 无法闭合 => STOP；本次未触发
  （修复仅在既有 allowlist 文件内完成）。

## 逐 finding 状态 / 验证 / 残余

### S14-RR-01 — [高] 合法格式但 operation_id 与 journal 文件名不一致时，recovery 在 fail-closed 前发布远端对象 — FIXED

- **生产改动**：`dayu/fins/storage/remote_op_journal.py`
  - `read_journal(dayu_root, operation_id)` 把调用方传入的 `operation_id`（journal
    文件名身份）作为期望身份传入严格 parser `_journal_from_dict(payload,
    expected_operation_id=operation_id)`；
  - `_journal_from_dict` 校验 payload `operation_id` 必须精确等于文件名身份，且每个
    publish target 的 `staging_key` 必须属于 `.dayu-staging/{operation_id}/` 命名空间；
    任一不一致即抛 `RemoteOpJournalError`（结构性损坏，fail closed）。
  - `_recover_remote_ops` 在 `_recover_orphan_batch_dirs`（FS orphan cleanup）之前按
    文件名枚举并 `read_journal`，因此身份 mismatch 在**任何远端 publish/delete 与
    FS swap 之前**稳定失败，保留原 journal、FS batch staging 目录与远端
    staging/final bytes。
- **验证**：
  - `test_remote_op_journal.py`：`test_operation_id_mismatch_fails_closed`（body
    `operation_id` 改为另一合法非空值 => `RemoteOpJournalError`）、
    `test_staging_key_namespace_mismatch_fails_closed`（staging_key 引用其它
    operation 命名空间 => `RemoteOpJournalError`）；
  - `test_storage_batch_recovery.py` restart fault tests：
    `test_startup_operation_id_mismatch_fails_closed_preserves_all` 与
    `test_startup_staging_namespace_mismatch_fails_closed_preserves_all`——崩溃后改写
    journal body，`ensure_batch_recovery` 稳定抛 `RemoteOpJournalError`，断言
    `fake.publish_calls == []`、远端 objects 逐字不变（零 publish/delete）、journal
    文件与 `repo_batches/{token}` 目录均保留（零 FS swap）。
- **残余**：损坏 journal 需人工处置（保留证据，不自动重建）；跨 token 的 fail-closed
  会停止整个 workspace 的 startup recovery（计划认可的语义）。

### S14-RR-02 — [中] 无 preparation gate 的允许调用路径在阶段 A timeout/cancel 后没有 late-inner 临时 PDF owner — FIXED

- **生产改动**：`dayu/fins/pipelines/cn_download_filing_workflow.py`
  - `_PreparationSlotOwnership` 重构为 `_PreparationInnerOwner`（`gate:
    CnPreparationGate | None`）：inner task / temp asset owner 与可选的容量 slot
    owner 分离；`release()` 无 gate 时为空操作；
  - `run_cn_download_single_filing_stream` 无论是否注入 `preparation_gate` 都创建
    owner 并为阶段 A provider / 阶段 B read / Docling 各实际 inner future 注册
    `_bind_preparation_inner`（late completion cleanup 恒注册）；outer timeout/cancel
    只标记 `abandoned`，最后一个真实 inner 完成（含异常）时回收 exact 临时 PDF；
    有 gate 时 done callback 仍在最后一个 inner 完成后恰好 release 一次 slot
    （gate 路径语义不变，S14-CR-02 不回退）。
- **验证**（`test_cn_to_thread_boundary.py`，全部 passed）：
  - `test_stage_a_param_timeout_no_gate_late_success_cleans_pdf`：`preparation_gate=None`
    + 0.05s 参数 timeout，provider 先写临时 PDF 再阻塞 => `FILING_FAILED`、零
    begin/commit/rollback、converter 零调用；释放 blocker 后临时 PDF 被 done
    callback 精确回收（最终零 PDF），零 repository 写入；
  - `test_stage_a_param_timeout_no_gate_late_exception_stays_closed`：late exception
    不进入 B/C，零 begin/commit/rollback、converter 零调用、最终零临时 PDF；
  - `test_outer_cancel_during_stage_a_no_gate_cleans_late_pdf`：无 gate outer cancel
    传播 `TimeoutError`，late result 不进入 B/C，释放 blocker 后临时 PDF 回收、零
    begin/commit/rollback。
- **残余**：无（阶段 A hard timeout 契约在无 gate 路径同样真实生效；outer cancel
  不回收已运行的 Python thread 为计划认可 residual，worker 零 repo/batch/token
  句柄，仓储一致性由契约保护）。

## 验证汇总（round-2 fix gate）

- focused fault-injection：journal 身份绑定 + CN 无 gate 边界 + 相关回归
  **172 passed**；
- 完整 corpus：`tests/fins` + MinIO integration 11 case **2213 passed / 0 failed**
  （`env -u SERPER_API_KEY`；MinIO 固定 digest 镜像可用，真实执行，未伪称）；
- 逐文件 statement coverage（pytest-cov broad source `--cov=dayu.fins
  --cov=dayu.host --cov=dayu.services` + JSON 机械核对，corpus = `tests/fins` +
  MinIO integration）：`cn_download_filing_workflow.py` **84.2%**（363/431）、
  `_fs_storage_infra.py` **88.0%**（718/816）、`remote_op_journal.py` **92.6%**
  （174/188），全部 `>=80%`（三文件均为本次再次修改生产文件）；
- changed pyright：三生产文件 + 三测试文件 **0 errors / 0 warnings**；全树 pyright
  仅既有 13×`test_web_tools.py` + 2×`docling_processor.py` + 2×
  `test_docling_processor_helpers.py` 于非本 Slice 文件（未扩散）；
- Ruff F/I + default：changed 文件 **0**；
- strict added-line forbidden scan（`Any/object/cast/ignore/getattr/hasattr`）：本次
  新增行 **0 hits**（`test_storage_batch_recovery.py` 既有 `object`/`ignore` 行为
  baseline，round-1 已记录）；
- `git diff --check` 干净；`tests/fins/storage_testkit.py` 零 diff。

## Changed files（round-2 fix gate）

- 生产：`dayu/fins/storage/remote_op_journal.py`、
  `dayu/fins/pipelines/cn_download_filing_workflow.py`
- 测试：`tests/fins/test_remote_op_journal.py`、
  `tests/fins/test_storage_batch_recovery.py`、`tests/fins/test_cn_to_thread_boundary.py`
- 文档：`dayu/fins/README.md`（§8.3 journal 身份绑定、§8.6 临时 PDF owner 与可选
  slot owner 分离）、`docs/reviews/slice-1.4-implementation-artifact-s3-blob-repository.md`
  （状态 => ROUND-2 FIX APPLIED，新增 §3.2 与 §4.2）、
  `docs/reviews/code-review-adjudication-20260811-slice-1.4-s3-blob-repository-codex.md`
  （状态 => ROUND-2 FIX APPLIED，新增 §6）、本 round-2 fix artifact。

## Residual / 未覆盖项

- 全树 pyright 既有 13+2+2 错误位于非本 Slice 文件，未扩散、未修复；
- CN 阶段 B 为无界 CPU/IO 工作（计划认可 residual）；outer cancel 不回收 Python
  thread（契约保护仓储一致性）；
- coverage 通过 pytest-cov broad source（`--cov=dayu.fins --cov=dayu.host
  --cov=dayu.services`）执行（本机 numpy 二进制扩展与 `coverage run --source` /
  pytrace core 冲突为既有环境问题，round-1 已记录）；
- 未运行 live data/model/broker；未 push/PR/merge。
- Final corrective re-review：Terra 与 MiM Native 均 PASS/open H/M/L=0/0/0；
  S14-RR-01/02 CLOSED，且 S14-CR-01..04 无回归。
