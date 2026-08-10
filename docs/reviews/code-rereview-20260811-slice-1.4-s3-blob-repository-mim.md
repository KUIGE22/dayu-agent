# Code Re-Review — Slice 1.4 S3 blob repository code-review fix（corrective independent re-review）

## Scope

- **Mode**: corrective re-review（验证 S14-CR-01..04 fix 真实闭合；不重做 full code review）
- **Branch**: `codex/investment-platform`
- **Base**: `HEAD`（当前 WIP）
- **Output file**: `docs/reviews/code-rereview-20260811-slice-1.4-s3-blob-repository-mim.md`
- **Included scope**: 三份 fix 生产文件（`cn_download_filing_workflow.py`、`_fs_storage_infra.py`、`remote_op_journal.py`）+ 四份 fix 测试文件（`test_cn_to_thread_boundary.py`、`test_remote_op_journal.py`、`test_storage_batch_recovery.py`、`test_delete_entry_staged_delete.py`）+ 原始 MiM review（`code-review-20260811-053319.md`）+ Terra review（`code-review-20260811-slice-1.4-s3-blob-repository-terra.md`）+ Controller adjudication（`code-review-adjudication-20260811-slice-1.4-s3-blob-repository-codex.md`）+ fix artifact（`slice-1.4-code-review-fix-20260811-codex.md`）+ implementation artifact（`slice-1.4-implementation-artifact-s3-blob-repository.md`）
- **Excluded scope**: 非 fix 范围的生产文件、已有历史 review、README、plan；不 commit/push/PR/merge
- **Parallel review coverage**: 无

## Verification methodology

逐项追踪 S14-CR-01..04 的 accepting evidence：从原始 Terra/MiM review finding → Controller adjudication → fix artifact 的声称修复 → 当前生产代码真实执行路径 → adversarial tests 的直接证据。验证 Controller 已 rejected 的 MiM observations 未被重复引入；验证无 regression / HML 新增。

---

## S14-CR-01 — CN 阶段 A 配置 timeout 从未消费

### 原始 finding

Terra review（`code-review-20260811-slice-1.4-s3-blob-repository-terra.md` S14-CR-01）：阶段 A 以 `asyncio.to_thread()` 建立 inner future，但没有 `asyncio.timeout`/deadline 消费点；`except asyncio.TimeoutError` 不可达；配置 hard timeout 当前确实失效。

### 修复验证

**生产代码**：`cn_download_filing_workflow.py:267-290`

```python
async with asyncio.timeout(provider_download_timeout_seconds):  # L267
    asset = await asyncio.shield(provider_inner)               # L268
except asyncio.TimeoutError:                                    # L269
    ownership.abandoned = True                                  # L274
    yield DownloadEvent(FILING_FAILED, reason="provider download timeout")  # L284-290
    return                                                     # L290
```

- `provider_download_timeout_seconds` 真实消费：`asyncio.timeout` 包裹 outer 等待（等待 slot 不计时）
- `except asyncio.TimeoutError` 真实可达：超时产出 `FILING_FAILED`，零 begin/commit/rollback/零 publish
- `asyncio.shield` 保护 provider inner future：outer timeout/cancel 只取消 shield 包装与 outer 等待，不取消 worker

**Adversarial tests**（全部 `test_cn_to_thread_boundary.py` passed）：
- `test_stage_a_param_timeout_yields_failed_then_slot_released`：参数 timeout → 按时失败终态、零 begin、converter 零调用、slot 在 inner 完成前不释放、完成后释放
- `test_stage_a_param_timeout_second_filing_blocks_until_inner_done`：容量 1，第二 filing 在 late inner 完成前停在 `gate.acquire()`
- `test_stage_a_param_timeout_late_exception_releases_slot`：late exception 后 slot 随 inner 完成释放
- `test_outer_cancel_during_stage_a_eventually_releases_slot`：outer cancel 不取消 worker、不提前 release、零 publish

**结论**：CLOSED — timeout 配置真实生效，late completion 不进入 B/C，slot 绑定真实 inner completion。

---

## S14-CR-02 — outer cancellation 遗留 slot 永久 active

### 原始 finding

Terra review（S14-CR-02）：`to_thread` inner future 没有独立 owner、shield、completion callback 或统一 finally；outer cancel 抛 `CancelledError` 不被捕获，slot 永久 active。

### 修复验证

**生产代码**：`cn_download_filing_workflow.py:238,245-262,951-1034`

1. `_PreparationSlotOwnership` dataclass（L951-982）：`pending_inner`/`abandoned`/`released` 三状态；`release()` 幂等（`released` flag 保证恰好一次）
2. `_bind_preparation_inner`（L985-1034）：`ownership.pending_inner += 1` → 注册 `add_done_callback` → 最后一个 inner 完成时 `pending_inner == 0 && abandoned && !released` → `late_cleanup` + `_release_preparation_slot`
3. 阶段 A（L245-262）：`asyncio.create_task(asyncio.to_thread(...))` → `_bind_preparation_inner` 绑定 ownership → `asyncio.shield` 保护 → outer timeout/cancel 只标记 `abandoned = True`
4. 阶段 B（L335-346）：同样 `asyncio.create_task` → `_bind_preparation_inner` → `asyncio.shield`
5. Late provider cleanup（L1037-1056）：只做 exact temp PDF unlink，禁止进入 B/C/repo

**Adversarial tests**（全部 passed）：
- `test_outer_cancel_during_stage_b_docling_eventually_releases_slot`：Docling worker 阻塞时 outer cancel → late 结果不进入 C → worker 完成后 slot 收敛
- `test_outer_cancel_during_stage_a_eventually_releases_slot`：slot 最终 `has_admitted_work() is False`，core 无残留 active batch

**结论**：CLOSED — slot 绑定真实 inner future completion；outer cancel 不提前 release，最后一个 inner 完成后收敛释放。

---

## S14-CR-03 — publish 判定仅 size 或仅 SHA 匹配即成功

### 原始 finding

Terra review（S14-CR-03）：publish 与 recovery 都以 digest **或** size 任一匹配判成功；同-size/different-SHA 对象可被持久为 `final_verified`。

### 修复验证

**生产代码**：`_fs_storage_infra.py:120-139`

```python
def _remote_matches_expected(remote: FileObjectMeta, *, sha256: str, size: int) -> bool:
    return str(remote.sha256 or "") == sha256 and int(remote.size or 0) == size
```

- 模块级单一真源：SHA-256 **且** size 同时匹配才返回 `True`
- `_publish_one_target`（L708-712）复用本真源
- `_recover_single_remote_op` publish path（L1082-1086）复用本真源
- `_head_expected` delete pre-swap 校验（L752-756）复用本真源
- 三条路径共用同一判断，消除了原始 OR 逻辑的不对称

**Adversarial tests**（全部 `test_storage_batch_recovery.py` passed）：
- `test_publish_one_target_same_size_diff_sha_republishes`：same-size/different-SHA → 必须从 staging 重发布
- `test_publish_one_target_same_sha_diff_size_not_accepted`：same-SHA/different-size → 同前
- `test_publish_one_target_exact_match_skips_retry`：完全匹配 → 幂等 verified
- `test_publish_one_target_staging_missing_fails_closed`：staging 缺失 → `RuntimeError` fail closed
- `test_recovery_publish_same_size_diff_sha_republishes_from_staging`：recovery same-size/different-SHA → 重发布
- `test_recovery_publish_same_sha_diff_size_republishes_from_staging`：recovery same-SHA/different-size → 重发布
- `test_recovery_publish_exact_match_verifies_without_republish`：recovery 完全匹配 → 幂等
- `test_recovery_publish_staging_missing_fails_closed_preserves_remote`：recovery staging 缺失 → fail closed 保留 remote

**结论**：CLOSED — SHA-256 且 size 同时匹配为唯一真源；publish/recovery/delete 三条路径共用。

---

## S14-CR-04 — 损坏 journal 被归一为 None 后 FS orphan cleanup 丢元数据

### 原始 finding

Terra review（S14-CR-04）：`read_journal()` 将 JSON error 和 `_journal_from_dict()` 失败统一返回 `None`；`_recover_remote_ops()` 在 `journal is None` 时直接 `continue`；随后 `_recover_orphan_batch_dirs()` 可清理 token staging 目录。

### 修复验证

**生产代码**：

1. `remote_op_journal.py:172-197` — `read_journal`：
   - 文件不存在 → `return None`（L189-190）
   - 文件存在但 JSON 解析失败 → `raise RemoteOpJournalError`（L193-194）
   - 顶层非字典 → `raise RemoteOpJournalError`（L195-196）
   - `_journal_from_dict` 内部逐字段严格校验

2. `remote_op_journal.py:287-341` — `_journal_from_dict`：
   - phase 白名单校验（L307-308）
   - action 白名单校验（L319-320）
   - publish state 白名单校验（L397-398）
   - delete state 白名单校验（L436-437）
   - SHA-256 64 位 hex 校验（L381-382, L431-432）
   - size 非负校验（L383-384, L433-434）
   - metadata 键值必须 str→str（L392-394）
   - publish final_key 唯一性（L323-325）
   - delete final_key 唯一性（L329-331）

3. `_fs_storage_infra.py:1028-1035` — `_recover_remote_ops`：
   - `read_journal` 正常返回 → 处理
   - `read_journal` 返回 `None` → `continue`（文件真正不存在）
   - `read_journal` 抛 `RemoteOpJournalError` → 向上传播，**在 `_recover_orphan_batch_dirs` 之前 fail closed**
   - journal、FS staging metadata、远端 objects 全部保留

4. `_fs_storage_infra.py:418-424` — `_stage_delete_one_key` deduplication：
   - 同一 operation 内同一 key 的重复 delete intent 幂等收敛（`delete_entry` 与 inventory diff 可能各自记录同一 key）

**Adversarial tests**：

`test_remote_op_journal.py`（21 passed）：
- `test_read_invalid_json_fails_closed`：corrupt JSON → `RemoteOpJournalError`
- `test_read_top_level_non_dict_fails_closed`：顶层非字典 → `RemoteOpJournalError`
- `test_unknown_phase_fails_closed`：unknown phase → `RemoteOpJournalError`
- `test_unknown_target_action_fails_closed`：unknown action → `RemoteOpJournalError`
- `test_unknown_publish_state_fails_closed`：unknown publish_state → `RemoteOpJournalError`
- `test_unknown_delete_state_fails_closed`：unknown delete_state → `RemoteOpJournalError`
- `test_bad_publish_sha_fails_closed`：bad sha → `RemoteOpJournalError`
- `test_negative_publish_size_fails_closed`：负 size → `RemoteOpJournalError`
- `test_missing_operation_id_fails_closed`：缺 operation_id → `RemoteOpJournalError`
- `test_empty_ticker_fails_closed`：空 ticker → `RemoteOpJournalError`
- `test_duplicate_publish_key_fails_closed`：重复 publish key → `RemoteOpJournalError`
- `test_duplicate_delete_key_fails_closed`：重复 delete key → `RemoteOpJournalError`
- `test_metadata_non_string_value_fails_closed`：metadata 非字符串值 → `RemoteOpJournalError`
- `test_missing_journal_still_returns_none`：真正 missing → `None`（无回归）

`test_storage_batch_recovery.py`（68 passed）：
- `test_startup_corrupt_json_journal_fails_closed_preserves_all`：corrupt JSON → fail closed，journal/staging/remote 全保留
- `test_startup_partial_invalid_target_journal_fails_closed_preserves_all`：partial target → fail closed
- `test_startup_unknown_phase_journal_fails_closed_preserves_all`：unknown phase → fail closed
- `test_startup_duplicate_key_journal_fails_closed_preserves_all`：duplicate key → fail closed

`test_delete_entry_staged_delete.py`（14 passed）：
- `test_s3_repeated_delete_intent_same_key_is_deduplicated`：同 key 重复 delete intent → 收敛为一条

**结论**：CLOSED — 损坏 journal 严格 fail closed 保留全部证据；去重防止重复 delete target。

---

## MiM observations 重复验证

以下6项为原始 MiM review（`code-review-20260811-053319.md`）中被 Controller rejected 的 observations，逐项验证未在 fix 中重复引入：

### MiM H — S3 directory delete intent — REJECTED-NO-REGRESSION

- `_delete_entry_impl_s3`（`_fs_blob_core.py:240-264`）：只对单个 `final_key` 调用 `_stage_delete_one_key`；`_normalize_entry_name` 禁止路径分隔符（L255）；无 prefix sweep
- fix artifact 未改动 `_delete_entry_impl_s3` 行为
- **无回归**

### MiM M — staged delete drift — REJECTED-NO-REGRESSION

- S14-CTRL-13 要求 metadata swap 前 remote drift 必须 fail closed，保留 journal
- `_recover_single_remote_op`（L1128-1135）：`_remote_matches_expected` 不匹配 → `raise RuntimeError` fail closed
- **无回归**

### MiM M — bounded publish retry — REJECTED-NO-REGRESSION

- 一次 bounded retry + startup recovery 已满足 accepted contract
- fix 未增加无限退避
- **无回归**

### MiM L — runtime asserts — REJECTED-NO-REGRESSION

- `isinstance(self._file_store, StagedFileStoreProtocol)` 存在于 `_head_expected`（L745）、`_recover_single_remote_op`（L1059）等位置；均为 baseline 代码（`git diff` 非新增行）
- fix artifact 未改动这些 assert 行
- **无回归**

### MiM L — cleanup state/journal window — REJECTED-NO-REGRESSION

- remote delete 幂等；journal 写前 crash 在 startup 重放同一 delete 并收敛
- fix 未改变 cleanup 幂等语义
- **无回归**

### MiM L — presign expires type — REJECTED-NO-REGRESSION

- `s3_file_store.py:414-439` 的 `get_presigned_url` typed signature 固定 `int`
- fix 未改动此接口
- **无回归**

---

## Regression / HML 检查

### 新增 H/M/L：无

| 检查项 | 结果 |
|--------|------|
| pyright（三生产文件） | 0 errors / 0 warnings / 0 informations |
| pyright（四测试文件） | 0 errors / 0 warnings |
| pyright（全树） | 仅既有 13+2+2 错误（非本 Slice 文件，未扩散） |
| Ruff F/I + default（三生产文件） | 0 |
| Ruff F/I + default（四测试文件） | 0 |
| strict added-line forbidden scan（三生产文件） | 新增行 0 hits（`Any`/`object`/`cast`/`ignore`/`getattr`/`hasattr`） |
| git diff --check | 干净（无 whitespace 错误） |

### 无回归

| 检查项 | 结果 |
|--------|------|
| MiM observations 重复引入 | 0（6 项全部 REJECTED-NO-REGRESSION） |
| 既有 closure 回归 | 无（S14-CTRL-03/04/05/08/09/10/11/12/13 保持 closed） |
| MinIO integration 11 case | 全部 passed（镜像可用，真实执行） |

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
- frozen WIP hash 的精确复现命令未内化到 repo（按 acceptance 记录引用，冻结标识有效）
- `tests/application`/`tests/engine` 的 `--cov` 语料因本机 numpy 二进制扩展与 coverage import 顺序冲突无法合并（既有环境问题）

---

## Conclusion

**PASS** — open **H=0 / M=0 / L=0**

S14-CR-01..04 全部闭合验证通过：timeout 配置真实生效（L267-290），slot 绑定 inner completion（L951-1034），SHA+size 双重匹配唯一真源（L120-139），journal 严格 fail-closed 保留全部证据（L172-197, L287-341）。全部6项 MiM rejected observations 未重复引入。三生产文件 pyright 0 / Ruff 0 / forbidden scan 0。MinIO integration 11 case 真实全绿。无新增 regression / HML。
