# Slice 1.4 S3-compatible Fins blob repository code-review fix（DeepSeek Flash fix agent）

- **Gate**：Gateflow / code review FIX gate（S14-CR-01..04）
- **Worker**：DeepSeek Flash fix agent（非 controller；不启动 gateflow、不重做
  plan/review、不 commit/push/PR/merge、不进入 re-review）
- **日期**：2026-08-11
- **裁决**：`docs/reviews/code-review-adjudication-20260811-slice-1.4-s3-blob-repository-codex.md`
  （accepted S14-CR-01..04；MiM observations 全部 REJECTED）
- **Terra review**：`docs/reviews/code-review-20260811-slice-1.4-s3-blob-repository-terra.md`
- **MiM review**：`docs/reviews/code-review-20260811-053319.md`
- **Round-2 fix**（S14-RR-01/02，独立 artifact）：
  `docs/reviews/slice-1.4-code-review-round2-fix-20260811-codex.md`
- **状态**：**CLOSED / DUAL RE-REVIEW PASS**
- **Implementation artifact 状态**：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**

## Scope / 约束

- 只修 accepted `S14-CR-01..04`；全部 MiM observations 已 REJECTED，严禁顺手改
  （含 S3 directory delete intent、staged delete drift、bounded publish retry、
  runtime asserts、cleanup state/journal window、presign expires type）。
- 未新增 `Any`/`object`/`cast`/`ignore`/`getattr`/`hasattr`（新增行扫描 0）、
  未新增 glue/compat/prefix sweep/第二 storage owner、未放宽 fail-closed 语义。
- 未清理或覆盖其他 WIP；`tests/fins/storage_testkit.py` 零 diff。
- 若 CN 生命周期需要计划外公共契约或现有 allowlist 无法闭合 => STOP；
  本次未触发（修复仅在既有 allowlist 文件内完成）。

## 逐 finding 状态 / 验证 / 残余

### S14-CR-01 — CN 阶段 A 配置 timeout 从未消费 — FIXED

- **生产改动**：`dayu/fins/pipelines/cn_download_filing_workflow.py` 阶段 A 以
  `asyncio.timeout(provider_download_timeout_seconds)` 只包裹 outer 等待（等待
  slot 不计时）；`except asyncio.TimeoutError` 真实可达，超时产出
  `FILING_FAILED`（reason `pdf_download_failed` / "provider download timeout"）、
  零 begin/commit/rollback/零 publish。
- **验证**：
  - `test_stage_a_param_timeout_yields_failed_then_slot_released`：只传函数参数
    （0.1s），provider 阻塞 => 按时失败终态、零 begin、converter 零调用
    （late success 不进入 B/C）、slot 在 inner 完成前不释放、完成后释放、
    临时 PDF 被 late cleanup 删除；
  - `test_stage_a_param_timeout_second_filing_blocks_until_inner_done`：容量 1，
    第二 filing 在 late inner 完成前停在 `gate.acquire()`、provider 零调用；
  - `test_stage_a_param_timeout_late_exception_releases_slot`：late exception
    后 slot 随 inner 完成释放；
  - `test_outer_cancel_during_stage_a_eventually_releases_slot`：
    outer cancel 不取消 worker、不提前 release、零 publish。
- **残余**：无（阶段 A hard timeout 契约真实生效；阶段 B/C 语义不变）。

### S14-CR-02 — outer cancellation 遗留 slot 永久 active — FIXED

- **生产改动**：`cn_download_filing_workflow.py` 新增 `_PreparationSlotOwnership`
  （pending/abandoned/released）与 `_bind_preparation_inner`：阶段 A/B 各 inner
  future 经 `asyncio.create_task(asyncio.to_thread(...))` 建立并以
  `asyncio.shield` 保护（实测 `Task.cancel()` 会级联取消 `_fut_waiter`，即被
  await 的子任务，必须 shield 才能让 worker 继续）；done callback 在**最后一个
  真实 inner 完成（含异常）**时执行 late 清理并**恰好 release 一次**；outer
  timeout/cancel/生成器关闭只停止消费（`finally` 标记 abandoned 兜底），
  绝不提前 release；正常路径由阶段 B 结束显式释放。late provider 完成只做
  exact 临时 PDF unlink + warning，禁止进入 read/Docling/repo。
- **验证**：
  - `test_outer_cancel_during_stage_b_docling_eventually_releases_slot`：Docling
    worker 阻塞时 outer cancel，late 结果不进入 C，worker 完成后 slot 收敛；
  - `test_stage_a_param_timeout_yields_failed_then_slot_released` /
    `test_outer_cancel_during_stage_a_eventually_releases_slot`：slot 最终
    `has_admitted_work() is False`，core 无残留 active batch；
  - 既有 `test_cn_to_thread_boundary.py` 中锁定旧缺陷的断言
    （"gate slot 不会被释放"）已按修复后行为改写；
- **残余**：outer cancel 不回收已运行的 Python thread（计划认可的 residual：
    worker 零 repo/batch/token 句柄，仓储一致性由契约保护）。

### S14-CR-03 — publish 判定仅 size 或仅 SHA 匹配即成功 — FIXED

- **生产改动**：`dayu/fins/storage/_fs_storage_infra.py` 新增模块级真源
  `_remote_matches_expected(remote, *, sha256, size)`（SHA-256 **且** size 同时
  匹配）；`_publish_one_target` 模糊 Copy 判定与 `_recover_single_remote_op`
  recovery 判定统一复用；`_head_expected` 复用同一真源（delete pre-swap 校验
  与 publish 分支对称）。
- **验证**（`tests/fins/test_storage_batch_recovery.py` fault-injection 矩阵）：
  - same-size/different-SHA：commit 与 recovery 均不得置 verified，必须从
    staging 重发布（最终 bytes = staging 真值）；
  - same-SHA/different-size（伪造 HEAD metadata）：同前；
  - 完全匹配：commit/recovery 幂等 verified、不重复发布（`publish_calls == 0/1`）；
  - staging 缺失 + 不匹配：commit/recovery fail closed（`RuntimeError`），
    journal 保留、错误 final 不被 verified。
- **残余**：无。

### S14-CR-04 — 损坏 journal 被归一为 None 后 FS orphan cleanup 丢元数据 — FIXED

- **生产改动**：
  - `dayu/fins/storage/remote_op_journal.py`：`read_journal` 严格区分缺失
    （文件不存在 => `None`）与损坏（存在但 JSON 解析失败 / 顶层非字典 /
    schema/phase/action/state/key/digest/size/唯一性任一非法 =>
    `RemoteOpJournalError` fail closed）；`_journal_from_dict` 逐字段严格校验
    （phase 白名单、action 白名单、publish/delete state 白名单、SHA-256 64 位
    hex、size/expected_size 非负、metadata 必须 str->str、publish/delete
    final_key 各自唯一）；
  - `dayu/fins/storage/_fs_storage_infra.py`：`_recover_remote_ops` 不再把
    `None`/损坏 journal 静默 `continue`，`RemoteOpJournalError` 向上传播 =>
    `recover_orphan_batches` 在 `_recover_orphan_batch_dirs`（FS orphan cleanup）
    之前 fail closed，journal/FS staging metadata/远端 objects 全部保留；
  - `_stage_delete_one_key` 对同一 operation 内同一 key 的重复 delete intent
    幂等收敛（`delete_entry` 与 inventory diff 可能各自记录同一 key），保证
    write 侧不产生重复 delete target（MinIO 真实流程暴露，修复后
    read 侧唯一性校验保持严格）。
- **验证**：
  - `test_remote_op_journal.py`：corrupt JSON / 顶层非字典 / unknown phase /
    unknown action / unknown publish_state / unknown delete_state / bad sha /
    负 size / 缺 operation_id / 空 ticker / duplicate publish key / duplicate
    delete key / metadata 非字符串值 全部 `RemoteOpJournalError`；真正 missing
    仍返回 `None`（无回归）；
  - `test_storage_batch_recovery.py`：corrupt JSON、partial/unknown target、
    unknown phase、duplicate key 的 startup `ensure_batch_recovery` 稳定
    `RemoteOpJournalError`，且 journal 文件、FS `repo_batches/{token}` 目录、
    远端 objects 全部保留；
  - `test_delete_entry_staged_delete.py`：同 key 重复 delete intent 收敛为一条；
  - MinIO integration：`test_minio_delete_entry_staged_delete_commit_removes_after_swap`
    真实流程（delete_entry + update_filing diff）通过；11 case 全绿。
- **残余**：损坏 journal 需人工处置（保留证据，不自动重建）；跨 token 的
  fail-closed 会停止整个 workspace 的 startup recovery（计划认可的
  "停止该 workspace 的进一步恢复" 语义）。

## 验证汇总（fix gate）

- focused fault-injection：上述全部 adversarial 测试 passed；
- 逐文件 statement coverage（`tests/fins` 单测 + MinIO integration 11 case）：
  `cn_download_filing_workflow.py` 84%、`_fs_storage_infra.py` 88%、
  `remote_op_journal.py` 92%（>=80% 全部达标）；
- changed pyright 0 errors / 0 warnings；全树 pyright 仅既有 13+2+2 错误于
  非本 Slice 文件（未扩散）；
- Ruff F/I + default：changed 文件 0（另修复两处 baseline I001 import-order）；
- strict added-line forbidden scan（`Any/object/cast/ignore/getattr/hasattr`）：
  本次新增行 0 hits；
- `git diff --check` 干净；
- MinIO integration：本机 `minio/minio` 固定 digest 镜像**可用**，11 case 真实
  执行全部 passed（未伪称执行）。

## Changed files（fix gate）

- 生产：`dayu/fins/pipelines/cn_download_filing_workflow.py`、
  `dayu/fins/storage/_fs_storage_infra.py`、`dayu/fins/storage/remote_op_journal.py`
- 测试：`tests/fins/test_cn_to_thread_boundary.py`、
  `tests/fins/test_remote_op_journal.py`、`tests/fins/test_storage_batch_recovery.py`、
  `tests/fins/test_delete_entry_staged_delete.py`
- 文档：`docs/reviews/slice-1.4-implementation-artifact-s3-blob-repository.md`
  （状态 => REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW，新增 §3.1 与 §4.1）、
  本 fix artifact。
- README：`dayu/fins/README.md` §8.6 描述的三段边界契约与修复后实现一致
  （修复使代码符合已记录契约），无内容不一致，未改动。

## Residual / 未覆盖项

- 全树 pyright 既有 13+2+2 错误位于非本 Slice 文件，未扩散、未修复；
- CN 阶段 B 为无界 CPU/IO 工作（计划认可 residual）；outer cancel 不回收
  Python thread（契约保护仓储一致性）；
- `tests/application`/`tests/engine` 的 `--cov` 语料因本机 numpy 二进制扩展与
  coverage import 顺序冲突无法合并（既有环境问题）；coverage 以 `tests/fins` +
  MinIO integration 语料独立执行，逐文件 >=80% 达标；
- 未运行 live data/model/broker；未 push/PR/merge。
- Round-2 final Terra + MiM Native re-review 均 PASS/open H/M/L=0/0/0；本 round-1
  fix 的四项 finding 与后续两项 corrective finding 全部 CLOSED。
