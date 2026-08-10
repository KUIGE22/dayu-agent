# Code Re-review

## Scope

- Mode: current changes（Slice 1.4 S3 blob repository 的 code-review fix 独立 corrective re-review）
- Review time: 2026-08-11 06:24:14 CST (+0800)
- Branch or PR: `codex/investment-platform`
- Base: `HEAD`（审查当前未提交 WIP；`87e8fc6` / `df14ec2` / `2466859` 仅作已接受计划与 erratum 参照）
- Output file: `docs/reviews/code-rereview-20260811-slice-1.4-s3-blob-repository-terra.md`
- Included scope: 完整读取 `AGENTS.md`、恢复计划、Slice 1.4 implementation artifact、Controller adjudication、fix artifact 与原 Terra review；走读 S14-CR-01..04 的 CN 阶段 A/B、remote-op journal、S3 commit/recovery 和 staged-delete 调用链，以及相关 tests。
- Excluded scope: 已被 Controller 拒绝的 MiM observations（directory delete intent、staged-delete drift、bounded retry、runtime assert、cleanup window、presign type）；无新的同链直接反例，故不重新裁决。未修改 production/tests/plan/既有 artifact，未 commit/push/PR。
- Parallel review coverage: 无（独立 Terra re-review）。

## Findings

### S14-RR-01-未修复-[高]-合法格式但 operation_id 与 journal 文件名不一致时，recovery 在 fail-closed 前发布远端对象
- **入口/函数**: `FsStorageCore.recover_orphan_batches()` -> `_recover_remote_ops()` -> `read_journal()` -> `_recover_single_remote_op()`。
- **文件(行号)**: `dayu/fins/storage/remote_op_journal.py:172-197,287-341`；`dayu/fins/storage/_fs_storage_infra.py:1028-1042,1070-1139,1191-1216`。
- **输入场景**: 崩溃后存在 `.dayu/remote_ops/<token_x>.json`；该文件的 JSON 仍满足当前所有字段、枚举、digest、size 与唯一性校验，但 `operation_id` 被损坏为另一个非空值 `token_y`。
- **实际分支**: `read_journal(..., token_x)` 只验证 `operation_id` 非空，接受 `token_y`；recovery 先按该 journal 的 publish target 从 staging 发布 final，再用 body 内的 `token_y` 取 `repo_batches/token_y/<ticker>` 做 metadata roll-forward，因目录不存在才抛 fail-closed。
- **预期行为**: journal 文件名的 operation id 与 payload 的 operation id 是同一 batch 的双重身份。任一不一致都是 S14-CR-04 所说的存在但非法/损坏 journal，必须在任何远端或 FS 副作用前稳定 fail closed，并保留 journal、staging metadata 与 remote objects。
- **实际行为**: 结构性 corruption 被当作可恢复 operation；远端 final 可在报错前被写入，随后恢复因为错误 token 的 staging 目录缺失而失败。此时既没有原子 roll-forward，也不满足“损坏 journal 全保留、零自动重放”的修复目标。
- **直接证据**: `read_journal()` 没有把调用方传入的 `operation_id` 传给 `_journal_from_dict()` 比对（`remote_op_journal.py:188-197,301-341`）；`_recover_remote_ops()` 从文件名 `operation_id` 枚举、却把 body journal 传入 recovery（`_fs_storage_infra.py:1028-1042`）；后续 `_roll_forward_recovered_meta()` 使用 `journal.operation_id` 定位 staging（`:1211-1216`）。独立最小复现把真实 journal body 的 `operation_id` 改为 `other-valid-operation-id`：`ensure_batch_recovery()` 报 `FS batch staging 目录缺失/损坏 ... other-valid-operation-id`，但 final key 已被发布；现有 `test_remote_op_journal.py:232-235` 仅覆盖缺失 id，未覆盖 mismatch。
- **影响**: 磁盘损坏边界可在 recovery 失败前改变 authoritative S3 bytes，留下 journal、metadata staging 与 final bytes 不可安全自动对齐；破坏 S3/FS 原子性与审计恢复链。
- **建议改法和验证点**: `read_journal` 必须把期望 operation id 作为 schema identity 传入 parser，要求 payload 精确相等；并在 recovery 前验证与 journal 内 staging namespace/FS token 的一致关系。新增 restart fault test：仅改写 body `operation_id` 为另一合法 id，断言 `RemoteOpJournalError`、零 `publish_staged`/delete/FS swap，且原 journal、batch dir、remote staging/final 均不变。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

### S14-RR-02-未修复-[中]-无 preparation gate 的允许调用路径在阶段 A timeout/cancel 后没有 late-inner 临时 PDF owner
- **入口/函数**: `run_cn_download_single_filing_stream()` 的阶段 A provider inner task。
- **文件(行号)**: `dayu/fins/pipelines/cn_download_filing_workflow.py:245-296,546-551,985-1055`；`dayu/fins/pipelines/cn_download_protocols.py:321-330`；`dayu/fins/pipelines/cn_pipeline.py:125-181`。
- **输入场景**: standalone/FS `CnPipeline` 或直接调用单-filing workflow 时保持公开默认 `preparation_gate=None`，provider 在 `provider_download_timeout_seconds` 后才返回带临时 PDF 的 `DownloadedReportAsset`，或 outer 在阶段 A 取消。
- **实际分支**: provider inner task 虽由 `create_task(asyncio.to_thread(...))` 创建并以 `shield` 等待，但 `_bind_preparation_inner()`（唯一的 late provider PDF cleanup callback）只在 `ownership is not None` 时注册；`ownership` 只在 gate 非空时创建。timeout/cancel 路径因此返回/抛出后没有 callback 接收 late asset 并调用 `_unlink_temp_pdf()`。
- **预期行为**: `preparation_gate` 只负责容量 slot，不能成为 `to_thread` inner task 与它所创建临时 PDF 的唯一 owner。无 gate 的已允许 FS/standalone 路径同样必须在 outer timeout/cancel 后阻止 B/C/repository 写入，并在 late provider completion 时回收 exact owned temp PDF。
- **实际行为**: late provider 正常返回后临时 PDF 永久留在临时目录；重复 timeout/cancel 可累积文件和后台 work。当前 production runtime 注入 gate 时 slot 收敛正确，但可选 gate 的真实调用面未闭合。
- **直接证据**: protocol 明确 `preparation_gate -> CnPreparationGate | None`（`cn_download_protocols.py:327-330`），`CnPipeline.__init__` 默认 `None` 并直接保存（`cn_pipeline.py:140,172`；其 standalone/FS 自建路径在 `:173-181`）。workflow 的 bind 被 `if ownership is not None` 包住（`cn_download_filing_workflow.py:254-262`），timeout 仅标记 ownership（`:269-296`），最终 `finally` 对 `None` 无操作（`:546-551`）。独立最小复现以 `preparation_gate=None` 和 `0.05s` timeout 返回 `filing_failed` 后释放 provider：目录仍有 `A1_1.pdf`。现有 117 项 focused tests 全部传递，是因为所有 timeout/cancel 用例都注入了 gate。
- **影响**: standalone/FS CN ingestion 的 timeout/cancel 会留下未受治理的本地 PDF；长时间重复发生可耗尽临时磁盘，并违背 S14-CR-01/02 的 inner-task/temp ownership 修复目标。
- **建议改法和验证点**: 将 late-inner completion cleanup 从 slot owner 中拆出，所有阶段 A provider inner 均注册精确 asset cleanup callback；gate 存在时该 callback 再额外承担“最后一个 inner 后 release 一次”。至少新增无 gate 的 parameter-timeout 与 outer-cancel tests，断言 late success/late exception 不进入 B/C、零 repository batch/publish、late PDF 最终消失。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。

## S14-CR-01..04 逐项复核

| 项目 | 结论 | 直接证据 |
| --- | --- | --- |
| S14-CR-01 Stage A 配置 timeout | 部分通过 | `asyncio.timeout(provider_download_timeout_seconds)` 已实际包裹 shielded outer wait（`cn_download_filing_workflow.py:267-268`）；但无 gate 路径的 late PDF owner 缺口见 S14-RR-02。 |
| S14-CR-02 inner task / slot / temp ownership | 部分通过 | 有 gate 时 callback、`abandoned` 和一次性 release 的正常/timeout/cancel 路径成立（`:951-1055`）；无 gate 路径不注册 late cleanup，见 S14-RR-02。 |
| S14-CR-03 publish/recovery SHA **且** size | 通过 | `_remote_matches_expected()` 使用 `and`（`_fs_storage_infra.py:120-139`），commit ambiguity 与 recovery 均调用它（`:708-712,1082-1086`）；same-size/different-SHA、same-SHA/different-size、exact match、staging missing focused tests 全绿。 |
| S14-CR-04 corrupt/partial journal fail-closed | 未通过 | JSON/枚举/size/重复 key 的结构性非法已 fail closed，且不会进入 orphan cleanup；但 operation id 与文件身份未绑定，合法格式 corruption 可在 fail-closed 前远端发布，见 S14-RR-01。 |
| 写侧 duplicate delete intent 去重 / 严格读 | 通过 | `_stage_delete_one_key()` 对同 operation/pending 同 key 早退（`_fs_storage_infra.py:417-444`）；reader 仍拒绝 duplicate publish/delete final key（`remote_op_journal.py:313-332`），对应 tests 通过。 |

## Open Questions

- 无。

## Residual Risk

- Focused unit/fault-injection 已独立执行：`117 passed`（CN timeout/cancel/temporary-PDF、journal、batch recovery、staged delete）。
- 受影响文件 pyright：`0 errors, 0 warnings, 0 informations`；Ruff：通过；`git diff --check`：干净。
- MinIO integration 未能执行：固定 digest 的 `minio/minio` 镜像在本机缺失，11 个 case 均在 setup fail-fast；未拉取镜像、未伪称已验证。因此真实 MinIO 协议行为和 crash/restart lane 未获本次独立复验。
- 未运行 live data/model/broker；这不属于本 Slice 已授权范围。

## Conclusion

**FAIL** — open **1 高 / 1 中 / 0 低**。S14-CR-03 与写侧 duplicate delete intent 去重已闭合；S14-CR-01/02 在 runtime gate 路径成立但 standalone 的 late temp owner 未闭合，S14-CR-04 的 operation identity corruption 仍可在 fail-closed 前产生远端副作用。不得进入 accepted/merge，直至两个 finding 修复并补齐上述回归与可用环境下的 MinIO recheck。
