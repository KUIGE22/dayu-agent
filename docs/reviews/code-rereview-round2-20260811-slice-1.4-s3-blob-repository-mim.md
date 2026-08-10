# Code Re-Review — Slice 1.4 S3 blob repository round-2 final corrective re-review

## Scope

- **Mode**: round-2 final corrective re-review（独立验证 S14-RR-01/02 fix 真实闭合 + 原 S14-CR-01..04 无回归 + 新 H/M/L 检查）
- **Branch**: `codex/investment-platform`
- **Base**: `HEAD`（当前 WIP）
- **Output file**: `docs/reviews/code-rereview-round2-20260811-slice-1.4-s3-blob-repository-mim.md`
- **Included scope**:
  - 三份 round-2 fix 生产文件（`remote_op_journal.py`、`cn_download_filing_workflow.py`、`_fs_storage_infra.py`）
  - 三份 fix 测试文件（`test_remote_op_journal.py`、`test_cn_to_thread_boundary.py`、`test_storage_batch_recovery.py`）
  - Round-1 re-reviews（`code-rereview-20260811-slice-1.4-s3-blob-repository-terra.md`、`code-rereview-20260811-slice-1.4-s3-blob-repository-mim.md`）
  - Controller adjudication（`code-review-adjudication-20260811-slice-1.4-s3-blob-repository-codex.md`）
  - Round-2 fix artifact（`slice-1.4-code-review-round2-fix-20260811-codex.md`）
  - Implementation artifact（`slice-1.4-implementation-artifact-s3-blob-repository.md`）
- **Excluded scope**: 非 fix 范围的生产文件、历史 review、README、plan；不 commit/push/PR/merge
- **Parallel review coverage**: 无（独立 MiM re-review）

## Verification methodology

1. 独立验证 S14-RR-01：filename/payload operation_id + staging namespace mismatch 在任何 remote/FS 副作用前 fail closed/preserve
2. 独立验证 S14-RR-02：preparation_gate=None timeout/cancel 的 late success/exception 清 PDF、零 B/C/repo，gate 路径一次 release
3. 验证原 S14-CR-01..04 无回归
4. 检查新 H/M/L
5. 运行 focused tests、pyright、ruff、git diff --check

---

## S14-RR-01 — journal 身份绑定 fail-closed

### 原始 finding

Terra round-1 re-review（`code-rereview-20260811-slice-1.4-s3-blob-repository-terra.md` S14-RR-01）：存在 `.dayu/remote_ops/<token_x>.json`，但 payload 中 `operation_id=token_y` 时，当前 `read_journal()` 只验证 payload ID 非空，没有把文件身份作为 expected ID 传入严格 parser。恢复随后先按 payload publish target 写入 final remote key，直到使用 `token_y` 查找 FS staging 才 fail closed。Terra 最小复现确认 `final_written_before_fail_closed=True`。

### 修复验证

**生产代码**：`remote_op_journal.py:174-205, 295-371`

1. `read_journal(dayu_root, operation_id)` (L174-205)：
   - 文件不存在 → `return None` (L197-198)
   - 文件存在但 JSON 解析失败 → `raise RemoteOpJournalError` (L201-202)
   - 顶层非字典 → `raise RemoteOpJournalError` (L203-204)
   - 调用 `_journal_from_dict(payload, expected_operation_id=operation_id)` (L205)

2. `_journal_from_dict(payload, expected_operation_id=...)` (L295-371)：
   - L318-325: `operation_id = _require_nonempty_text(payload, "operation_id")`
   - L319-325: `if operation_id != expected_operation_id: raise RemoteOpJournalError(...)`
   - L335-352: `staging_namespace = f"{_STAGING_NAMESPACE_PREFIX}{operation_id}/"`
   - L348-352: `if not parsed.staging_key.startswith(staging_namespace): raise RemoteOpJournalError(...)`

3. `_fs_storage_infra.py:1028-1035` — `_recover_remote_ops`：
   - `read_journal` 正常返回 → 处理
   - `read_journal` 返回 `None` → `continue`（文件真正不存在）
   - `read_journal` 抛 `RemoteOpJournalError` → 向上传播，**在 `_recover_orphan_batch_dirs` 之前 fail closed**
   - journal、FS staging metadata、远端 objects 全部保留

**Adversarial tests**（全部 passed）：

`test_remote_op_journal.py`：
- `test_operation_id_mismatch_fails_closed` (L238-247)：payload `operation_id` 改为另一合法非空值 → `RemoteOpJournalError`
- `test_staging_key_namespace_mismatch_fails_closed` (L250-262)：staging_key 引用其它 operation 命名空间 → `RemoteOpJournalError`

`test_storage_batch_recovery.py`：
- `test_startup_operation_id_mismatch_fails_closed_preserves_all` (L1977-2009)：崩溃后改写 journal body operation_id → `ensure_batch_recovery()` 抛 `RemoteOpJournalError`，断言 `fake.publish_calls == []`、远端 objects 逐字不变（零 publish/delete）、journal 文件与 `repo_batches/{token}` 目录均保留（零 FS swap）
- `test_startup_staging_namespace_mismatch_fails_closed_preserves_all` (L2013-2041)：staging_key 引用其它 operation 命名空间 → 同上 fail closed 且全保留

**结论**：**CLOSED** — filename/payload operation_id 必须精确相等，staging namespace 必须属于本 operation；mismatch 在任何远端/FS 副作用前 fail closed，保留原 journal、batch staging、remote bytes。

---

## S14-RR-02 — preparation_gate=None timeout/cancel 的 late PDF owner

### 原始 finding

Terra round-1 re-review（`code-rereview-20260811-slice-1.4-s3-blob-repository-terra.md` S14-RR-02）：`preparation_gate=None` 是公开协议与 standalone/FS `CnPipeline` 的允许路径。当前 late-inner cleanup callback 只在 slot ownership 存在时绑定；无 gate 的 Stage A timeout/cancel 返回后，provider 晚到的 `DownloadedReportAsset` 无 owner 回收 temp PDF。Terra 最小复现确认 `late_pdf_files=['A1_1.pdf']`。

### 修复验证

**生产代码**：`cn_download_filing_workflow.py:246, 262-269, 274-297, 301-302, 344-351, 479-486, 952-988, 990-1042, 1045-1080`

1. `_PreparationInnerOwner` (L952-988)：
   - `gate: CnPreparationGate | None = None` (L966)
   - `pending_inner: int = 0` (L967)
   - `abandoned: bool = False` (L968)
   - `released: bool = False` (L969)
   - `release()` (L971-987)：无 gate 时为空操作 (`if self.released or self.gate is None: return`)

2. `_bind_preparation_inner` (L990-1042)：
   - `ownership.pending_inner += 1` (L1024)
   - `_on_inner_done` callback (L1026-1040)：
     - `ownership.pending_inner -= 1` (L1027)
     - `if not ownership.abandoned or ownership.released: return` (L1028-1029)
     - `if ownership.pending_inner > 0: return` (L1030-1031)
     - `late_cleanup(task, module)` (L1033)
     - `_release_preparation_slot(ownership)` (L1035)
   - `inner.add_done_callback(_on_inner_done)` (L1042)

3. 阶段 A（L252-269）：
   - `provider_inner = asyncio.create_task(...)` (L253-261)
   - `_bind_preparation_inner(provider_inner, ownership=ownership, late_cleanup=_cleanup_late_provider_asset, ...)` (L262-269)
   - 无论 `ownership.gate` 是否为 None，都注册 late completion cleanup

4. `_cleanup_late_provider_asset` (L1045-1063)：
   - `if task.cancelled() or task.exception() is not None: return` (L1059)
   - `asset = task.result()` (L1061)
   - `if isinstance(asset, DownloadedReportAsset): _unlink_temp_pdf(asset.pdf_path, module=module)` (L1062-1063)

5. 阶段 A timeout (L276-297)：
   - `asyncio.TimeoutError` → `ownership.abandoned = True` (L281)
   - yield `FILING_FAILED` (L291-296)
   - `return` (L297)
   - late provider 完成后 done callback 精确回收临时 PDF

6. 阶段 A cancel (L298-302)：
   - `asyncio.CancelledError` → `ownership.abandoned = True` (L301)
   - `raise` (L302)

**Adversarial tests**（全部 passed，`test_cn_to_thread_boundary.py`）：

- `test_stage_a_param_timeout_no_gate_late_success_cleans_pdf` (L1047-1082)：
  - `preparation_gate=None` + 0.05s timeout
  - provider 先写临时 PDF 再阻塞 → `FILING_FAILED`、零 begin/commit/rollback、converter 零调用
  - 释放 blocker 后临时 PDF 被 done callback 精确回收（最终零 PDF），零 repository 写入

- `test_stage_a_param_timeout_no_gate_late_exception_stays_closed` (L1085-1116)：
  - `preparation_gate=None` + 0.05s timeout
  - late exception 不进入 B/C，零 begin/commit/rollback、converter 零调用
  - 最终零临时 PDF

- `test_outer_cancel_during_stage_a_no_gate_cleans_late_pdf` (L1119-1167)：
  - 无 gate outer cancel 传播 `TimeoutError`
  - late result 不进入 B/C
  - 释放 blocker 后临时 PDF 回收、零 begin/commit/rollback

**有 gate 路径验证**（既有 tests passed）：

- `test_stage_a_param_timeout_yields_failed_then_slot_released` (L810-857)：
  - 有 gate，参数 timeout → 按时失败终态、零 begin、converter 零调用
  - slot 在 inner 完成前不释放、完成后释放

- `test_stage_a_param_timeout_second_filing_blocks_until_inner_done` (L860-906)：
  - 容量 1，第二 filing 在 late inner 完成前停在 `gate.acquire()`

- `test_stage_a_param_timeout_late_exception_releases_slot` (L909-943)：
  - late exception 后 slot 随 inner 完成释放

- `test_outer_cancel_during_stage_a_eventually_releases_slot` (L946-993)：
  - outer cancel 不取消 worker、不提前 release、零 publish

- `test_outer_cancel_during_stage_b_docling_eventually_releases_slot` (L996-1043)：
  - Docling worker 阻塞时 outer cancel → late 结果不进入 C → worker 完成后 slot 收敛

**结论**：**CLOSED** — inner task / temp asset owner 与可选的容量 slot owner 分离；无论是否注入 `preparation_gate`，每个阶段 A/B 实际 inner future 都注册 late completion cleanup；无 gate 时 late provider 完成即回收 exact 临时 PDF；有 gate 时 done callback 仍在最后一个 inner 完成后恰好 release 一次 slot。

---

## S14-CR-01..04 回归验证

| 项目 | 结论 | 直接证据 |
| --- | --- | --- |
| S14-CR-01 Stage A 配置 timeout | **无回归** | `asyncio.timeout(provider_download_timeout_seconds)` (L274) 真实消费；focused tests 全绿 |
| S14-CR-02 inner task / slot / temp ownership | **无回归** | 有 gate 时 callback、`abandoned` 和一次性 release 的正常/timeout/cancel 路径成立；无 gate 路径由 S14-RR-02 修复闭合 |
| S14-CR-03 publish/recovery SHA **且** size | **无回归** | `_remote_matches_expected()` 使用 `and`（`_fs_storage_infra.py:120-139`）；publish/recovery/delete 三条路径共用；focused tests 全绿 |
| S14-CR-04 corrupt/partial journal fail-closed | **无回归** | JSON/枚举/size/重复 key 的结构性非法已 fail closed；S14-RR-01 增强 operation_id/staging namespace 身份绑定 |
| 写侧 duplicate delete intent 去重 / 严格读 | **无回归** | `_stage_delete_one_key()` 对同 operation/pending 同 key 早退；reader 仍拒绝 duplicate publish/delete final key |

---

## MiM rejected observations 回归验证

| 项目 | 结论 | 直接证据 |
| --- | --- | --- |
| MiM H — S3 directory delete intent | **无回归** | `_delete_entry_impl_s3` 只对单个 `final_key` 调用 `_stage_delete_one_key`；`_normalize_entry_name` 禁止路径分隔符；无 prefix sweep |
| MiM M — staged delete drift | **无回归** | S14-CTRL-13 要求 metadata swap 前 remote drift 必须 fail closed；`_recover_single_remote_op` `_remote_matches_expected` 不匹配 → `raise RuntimeError` |
| MiM M — bounded publish retry | **无回归** | 一次 bounded retry + startup recovery 已满足 accepted contract；fix 未增加无限退避 |
| MiM L — runtime asserts | **无回归** | `isinstance(..., StagedFileStoreProtocol)` 为 baseline 代码；fix 未改动这些 assert 行 |
| MiM L — cleanup state/journal window | **无回归** | remote delete 幂等；journal 写前 crash 在 startup 重放同一 delete 并收敛 |
| MiM L — presign expires type | **无回归** | typed signature 固定 `int`；fix 未改动此接口 |

---

## 新 H/M/L 检查

| 检查项 | 结果 |
|--------|------|
| 新增 H（高） | 0 |
| 新增 M（中） | 0 |
| 新增 L（低） | 0 |
| pyright（三生产文件） | 0 errors / 0 warnings / 0 informations |
| pyright（三测试文件） | 0 errors / 0 warnings / 0 informations |
| Ruff F/I + default（生产文件） | All checks passed |
| strict added-line forbidden scan（`Any`/`object`/`cast`/`ignore`/`getattr`/`hasattr`） | 新增行 0 hits（`_fs_blob_core.py` 的 `object` 在字符串字面量中，为 baseline） |
| git diff --check | 干净（无 whitespace 错误） |

---

## Focused test results

```
tests/fins/test_remote_op_journal.py::test_operation_id_mismatch_fails_closed PASSED
tests/fins/test_remote_op_journal.py::test_staging_key_namespace_mismatch_fails_closed PASSED
tests/fins/test_storage_batch_recovery.py::test_startup_operation_id_mismatch_fails_closed_preserves_all PASSED
tests/fins/test_storage_batch_recovery.py::test_startup_staging_namespace_mismatch_fails_closed_preserves_all PASSED
tests/fins/test_cn_to_thread_boundary.py::test_stage_a_param_timeout_no_gate_late_success_cleans_pdf PASSED
tests/fins/test_cn_to_thread_boundary.py::test_stage_a_param_timeout_no_gate_late_exception_stays_closed PASSED
tests/fins/test_cn_to_thread_boundary.py::test_outer_cancel_during_stage_a_no_gate_cleans_late_pdf PASSED
```

Full test suite for affected files:
```
tests/fins/test_remote_op_journal.py ....................... [ 21%]
tests/fins/test_cn_to_thread_boundary.py ............ [ 33%]
tests/fins/test_storage_batch_recovery.py .............................. [100%]
105 passed in 4.11s
```

---

## Findings

未发现实质性问题。

---

## Open Questions

无。

---

## Residual Risk

- CN 阶段 B（`pdf_path.read_bytes` + 默认/注入 Docling 转换）为无界 CPU/IO 工作（计划认可 residual，非 fix scope）
- 全树 pyright 既有 13+2+2 错误位于非本 Slice 文件，未扩散
- frozen WIP hash 的精确复现命令未内化到 repo（按 acceptance 记录引用）
- `tests/application`/`tests/engine` 的 `--cov` 语料因本机 numpy 二进制扩展与 coverage import 顺序冲突无法合并（既有环境问题）

---

## Conclusion

**PASS** — open **H=0 / M=0 / L=0**

S14-RR-01/02 全部闭合验证通过：
- **S14-RR-01**：journal 身份绑定 fail-closed — filename/payload operation_id 精确相等校验 (L319-325)、staging namespace 归属校验 (L348-352)、restart fault tests 断言零 publish/delete/FS swap 且全保留
- **S14-RR-02**：inner/temp owner 与可选 slot owner 分离 — `_PreparationInnerOwner` (L952-988)、`_bind_preparation_inner` (L990-1042)、无 gate 路径 late success/exception 清 PDF tests

原 S14-CR-01..04 无回归。全部6项 MiM rejected observations 无回归。三生产文件 pyright 0 / Ruff 0 / forbidden scan 0。Focused tests 7/7 passed，full test suite 105/105 passed。无新增 regression / HML。

**Round-2 final corrective re-review verdict: PASS**
