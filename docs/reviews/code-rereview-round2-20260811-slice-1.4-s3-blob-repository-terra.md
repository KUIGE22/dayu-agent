# Code Re-review

## Scope

- Mode: current changes 的定向 round-2 corrective re-review
- Review time: 2026-08-11 06:49:21 CST (+0800)
- Branch or PR: `codex/investment-platform`
- Base: `main`；本轮以当前未提交 Slice 1.4 WIP 为被审对象
- Output file: `docs/reviews/code-rereview-round2-20260811-slice-1.4-s3-blob-repository-terra.md`
- Included scope: 完整读取根 `AGENTS.md`、Controller adjudication、Terra/MiM round-1 corrective re-review、`slice-1.4-code-review-round2-fix-20260811-codex.md` 与 implementation artifact；独立走读 `remote_op_journal.py`、`_fs_storage_infra.py`、`cn_download_filing_workflow.py` 及对应 fault-injection tests。
- Excluded scope: 已被 Controller 拒绝且 round-2 未触及的 MiM observations、live data/model/broker、无关历史 WIP；不修改实现、测试或既有 artifact。
- Parallel review coverage: 无。

## Findings

未发现实质性问题。

## S14-RR-01 独立复核

`read_journal()` 以文件名枚举得到的 `operation_id` 调用 `_journal_from_dict(..., expected_operation_id=operation_id)`（`remote_op_journal.py:174-205`）。严格 parser 在解析 target 前拒绝 payload ID 不相等（`:318-325`），并在加入 publish target 前拒绝不属于 `.dayu-staging/{operation_id}/` 的 `staging_key`（`:335-356`）。

真实启动入口先执行 `_recover_remote_ops()`，仅其正常返回后才会调用 `_recover_orphan_batch_dirs()`（`_fs_storage_infra.py:980-1003`）；前者逐 filename 调 `read_journal()`（`:1028-1042`）。因此两个 mismatch 都在远端 publish/delete、FS swap 与 orphan cleanup 前以 `RemoteOpJournalError` 终止。

独立执行的 restart fault tests 直接确认该顺序：`test_startup_operation_id_mismatch_fails_closed_preserves_all` 与 `test_startup_staging_namespace_mismatch_fails_closed_preserves_all` 均断言 journal/batch staging 仍存在、`fake.publish_calls == []`、远端 object 字典逐字不变（`test_storage_batch_recovery.py:1977-2041`）。这覆盖了零 remote/FS 副作用与证据保留，而非仅验证 parser 抛错。

## S14-RR-02 独立复核

`run_cn_download_single_filing_stream()` 无条件创建 `_PreparationInnerOwner(gate=active_gate)`（`cn_download_filing_workflow.py:238-248`）；阶段 A 的 provider task 无论 gate 是否存在均经 `_bind_preparation_inner()` 绑定 cleanup（`:252-275`）。timeout/cancel 只将 owner 标记为 `abandoned` 并立即停止消费，未进入阶段 B/C（`:276-302`）。

done callback 在最后一个真实 inner 完成后才调用 late cleanup；有 gate 时才由 `release()` 实际释放，且 `released` 在调用 gate 前置位，保证恰好一次（`:971-987, 1024-1042`）。无 gate 时 `release()` 为空操作，但 callback 仍调用 `_cleanup_late_provider_asset()`，它只对成功返回的精确 `DownloadedReportAsset.pdf_path` 执行幂等 unlink（`:1045-1063`）。因此没有把临时 PDF 生命周期错误绑定到可选容量 slot。

独立执行的无 gate tests 覆盖 parameter-timeout late success、late exception 和 outer cancel：三者均验证零 B/C（converter 零调用）、零 begin/commit/rollback、最终零临时 PDF（`test_cn_to_thread_boundary.py:1047-1167`）。已有 gate 的 A timeout late exception、A cancel、B cancel tests 同时保持 gate 最终无 active slot 与零仓储批处理（`:909-1043`）。`CnPreparationGate.release()` 本身对 active 为零抛错（`cn_download_protocols.py:135-153`），所以这些测试与 owner 的 `released` 守卫共同证明不存在 silent double release。

## S14-CR-01..04 与旧裁决无回归

- CR-01：`asyncio.timeout(provider_download_timeout_seconds)` 直接包裹 shielded provider await（`cn_download_filing_workflow.py:270-297`），参数真实生效；focused timeout/cancel tests 通过。
- CR-02：A、read 与 Docling 的实际 `to_thread` task 都在同一 owner 下绑定；提前放弃只由最后完成的 inner 收敛（`:340-356, 472-492, 990-1042`）。
- CR-03：publish/recovery 的 SHA-256 与 size 仍由 `_remote_matches_expected()` 的 `and` 判断统一（`_fs_storage_infra.py:120-139`）；恢复矩阵测试包含 same-size/different-SHA、same-SHA/different-size、exact-match、staging-missing。
- CR-04：存在但非法的 journal 仍抛错，只有真正缺失才返回 `None`（`remote_op_journal.py:196-205`）；严格读取发生在 orphan recovery 前。重复 delete intent 的既有 regression suite 也通过。
- Controller 已拒绝的六项 MiM observations 未被 round-2 修改重新引入；本轮没有发现 prefix sweep、兼容读取、第二 owner 或 fail-closed 放宽。

## Verification

- `pytest -q tests/fins/test_remote_op_journal.py tests/fins/test_storage_batch_recovery.py tests/fins/test_cn_to_thread_boundary.py`：**105 passed**。
- `pytest -q tests/fins/test_delete_entry_staged_delete.py`：**14 passed**。
- 受影响 3 个生产文件与 3 个测试文件的 `pyright`：**0 errors, 0 warnings, 0 informations**。
- 全树 `pyright`：**17 个既有无关错误**（`dayu/engine/processors/docling_processor.py` 2、`tests/engine/test_docling_processor_helpers.py` 2、`tests/engine/test_web_tools.py` 13）；本 Slice 未新增或扩散。
- 受影响文件 `ruff check`：通过。
- `git diff --check`：通过。
- `pytest -q tests/integration/investment/test_fins_s3_blob_repository_minio.py`：固定 MinIO digest 镜像缺失，11 项均在 setup fail-fast；未拉取镜像，未将其表述为已通过。

## Open Questions

- 无。

## Residual Risk

- 本机缺少 `minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`，故本轮不能独立验证 11 项真实 MinIO 协议/crash-restart 集成覆盖；这是环境未覆盖项，不构成已证实的代码缺陷。
- 阶段 B 的 Python thread 不可强制取消，仍是已记录的 bounded-by-ownership residual；其 worker 不持有 repository/batch/token，且本轮未发现该边界回归。
- 全树既有 pyright 17 errors 未在本只读复审中修复。

## Conclusion

**PASS** — open **H=0 / M=0 / L=0**。

S14-RR-01/02 均以真实入口、状态转换和 fault-injection 独立验证闭合；S14-CR-01..04 无回归。MinIO 因固定镜像缺失未能独立复跑，已作为 residual risk 如实保留。
