# Code Review

## Scope

- Mode: current changes（仅未提交的 Slice 1.4 WIP；不重审已提交的历史 Slice）
- Review time: 2026-08-11 05:34:30 CST (+0800)
- Branch or PR: `codex/investment-platform`
- Base: `HEAD`（工作区未提交差异）；计划与已接受 errata `df14ec2`、`2466859` 仅作为契约参照
- Output file: `docs/reviews/code-review-20260811-slice-1.4-s3-blob-repository-terra.md`
- Included scope: 当前 WIP 的 S3 FileStore/settings、remote-op journal 与 FS batch recovery、单 writer lease/startup/runtime 装配、S3/FS byte-path 与 destructive 状态机、SEC/CN/Docling producer batch 边界、CN timeout/cancellation/`to_thread`/temporary-PDF 路径、对应 tests、README、依赖，以及 `docs/reviews/slice-1.4-implementation-artifact-s3-blob-repository.md`。
- Excluded scope: 已提交的 Slice 1.1--1.3、投资平台其余功能、以及本次审查开始后出现的其他 review artifact；未修改生产代码、测试、README、计划、implementation artifact，也未 commit/push/PR。
- Parallel review coverage: 无（独立 Terra review；未启动 gateflow 或 subagent）。

## Findings

### S14-CR-01-未修复-[高]-CN 阶段 A 的配置 timeout 从未包裹 provider 调用
- **入口/函数**: `run_cn_download_single_filing_stream()` 的阶段 A provider download。
- **文件(行号)**: `dayu/fins/pipelines/cn_download_filing_workflow.py:230-245,251-270`；调用参数透传位于 `dayu/fins/pipelines/cn_download_workflow.py:265-280`。
- **输入场景**: S3 production runtime 传入任意有限的 `provider_download_timeout_seconds`，且 `discovery_client.download_report_pdf()` 阻塞、既不返回也不自行抛错。
- **实际分支**: 参数在函数签名接收，但阶段 A 只 `await asyncio.to_thread(...)`；没有 `asyncio.timeout`、deadline 或其他消费点。因此阻塞 worker 永远等待，`except asyncio.TimeoutError` 不可达。
- **预期行为**: Slice 1.4 已接受计划与 Fins README 都将该参数定义为仅约束 CN 阶段 A 的唯一 hard timeout；到期必须在开始阶段 C 前结束为失败，零 batch/token/publish。
- **实际行为**: timeout 配置静默失效；CN pipeline 卡在 provider future，不能产生该 filing 的失败终态，也不可能到达后续 filing。测试只能通过外部调用方另加 timeout 取消 outer task，不能证明配置参数有效。
- **直接证据**: `cn_download_workflow.py:280` 明确传入参数；`cn_download_filing_workflow.py:125` 接收它，但 `:222-245` 的唯一 await 未使用该变量，整个文件亦无 `asyncio.timeout`/`wait_for`。与此相对，SEC 路径在 `sec_download_workflow.py:498-508` 实际以 `asyncio.timeout(provider_download_timeout_seconds)` 包裹工作流。
- **影响**: 网络依赖退化时违反明确 timeout contract，CN ingestion 可无限挂起；运行时配置看似生效但实际没有约束，属于可用性与恢复治理缺陷。
- **建议改法和验证点**: 把阶段 A 的真实 inner future 建立为可追踪任务，以 `provider_download_timeout_seconds` 仅包裹 outer 等待；超时后不得把 worker 当作已停止。增加回归测试：只传很短的函数参数（不在测试外层另设 timeout），断言按时获得失败终态、零 begin/commit/rollback/publish，并验证 late completion 不进入 B/C。
- **修复风险（低/中/高）**: 高；必须与下一项一起实现，避免用会提前释放容量的表面 timeout 修复。
- **严重程度（低/中/高/严重）**: 高。

### S14-CR-02-未修复-[高]-CN outer cancellation 遗留 `to_thread` worker 时不保持或最终释放 preparation slot
- **入口/函数**: `run_cn_download_single_filing_stream()` 阶段 A/B 与 `CnPreparationGate`。
- **文件(行号)**: `dayu/fins/pipelines/cn_download_filing_workflow.py:225-250,292-446,829-843`；`dayu/fins/pipelines/cn_download_protocols.py:118-153`；`tests/fins/test_cn_to_thread_boundary.py:657-709`。
- **输入场景**: provider 正在线程中阻塞时，Host/调用方取消消费该 async generator，或阶段 A timeout 修复后取消 outer await。
- **实际分支**: `asyncio.to_thread()` 的 await 收到的是 `asyncio.CancelledError`（`BaseException`），而代码只捕获项目自定义的 `dayu.contracts.cancellation.CancelledError` 和 `Exception`。没有 `finally`、`asyncio.shield`、inner completion callback 或 slot ownership transfer。
- **预期行为**: 已接受计划要求 slot 绑定实际 inner future：outer cancel/阶段 A timeout 不能取消 provider worker，且不得提前 release；最后一个真实 inner 完成后才 release。这样后台 worker 的数量和 owned temp PDF 才始终受 gate 容量约束。
- **实际行为**: outer cancel 直接离开阶段 A，slot 永久保持 active；该 runtime 后续 CN filing 永远阻塞在 `gate.acquire()`。现有测试把这一已知缺陷当作期望：在解除 provider blocker 后仍断言 `gate.has_admitted_work() is True`，并没有等待 late worker 后收敛 slot。
- **直接证据**: 阶段 A 的 `try` 从 `:230` 到 `:290` 没有 `finally`，且 `:246` 捕获的不是 `asyncio.CancelledError`；`CnPreparationGate.release()` 只由显式 `_release_preparation_slot` 调用。`test_cn_to_thread_boundary.py:660-668` 文档化“已知缺陷”，`:698-709` 复现并断言 slot 仍被占用。实施 artifact 却声称该项已完成。
- **影响**: 一个取消/超时即可永久耗尽容量为 1 的 production gate，造成同一 runtime 的 CN/HK ingestion 停摆；若改为取消时立刻 release，又会违背 worker/temporary-PDF 上限并允许无限后台 worker。
- **建议改法和验证点**: 把阶段 A/B 各 inner future 的生命周期与 gate ownership 显式绑定：outer cancellation 只停止消费，completion callback 在实际 future 完成（包含异常）后清理 owned temp PDF、记录观测并 release 一次；正常路径也统一走同一 release ownership。覆盖 cancel during provider、configured stage-A timeout、cancel during read/Docling、late success/late exception，以及容量 1 下第二 filing 在前一 inner 真正结束前不能开始。
- **修复风险（低/中/高）**: 高；涉及 cancellation、线程与临时文件的 owner 状态机。
- **严重程度（低/中/高/严重）**: 高。

### S14-CR-03-未修复-[高]-remote publish 的恢复/模糊 Copy 判定接受“仅 size 相同”的错误对象
- **入口/函数**: `_publish_one_target()` 与 `_recover_single_remote_op()` 的 publish target 幂等判定。
- **文件(行号)**: `dayu/fins/storage/_fs_storage_infra.py:671-695,1030-1064`。
- **输入场景**: CopyObject 的响应模糊或进程在 first copy 后崩溃；此时 final key 已存在一个内容不同、但字节长度恰好等于 target `size` 的对象（或 SHA 相同而 size 不同）。
- **实际分支**: 代码以 `remote_meta.sha256 == target.sha256 OR remote_meta.size == target.size` 认定自己的 publish 已完成，并将该 target 持久化为 `final_verified`；恢复随后可 roll-forward FS metadata。
- **预期行为**: journal target 的 `sha256` 与 `size` 共同是该 operation 的内容身份。只有两者均匹配才可以把已有 final object 当作该 target 的已完成 copy；任一不匹配应继续从 staging 发布，或 staging 缺失时 fail closed。
- **实际行为**: 同大小但不同内容的远端对象被当成当前写入成功，FS source/processed metadata 会提交为新版本，但读取时 S3 adapter 只验证该错误对象自己的 metadata，不会再与 journal/metadata 中的期望 SHA 比较，造成静默指向错误 bytes。
- **直接证据**: `_publish_one_target()` 在 `:676-679` 使用两个独立的成功 `if`；recovery 在 `:1039-1046` 使用显式 `or`。Delete pre-swap 校验反而在 `:718-721` 要求 SHA 和 size 都匹配，表明 publish 分支不对称。计划和 README 均将恢复描述为以 target digest/size 为真值。
- **影响**: crash/retry 窗口可能提交错误财报/Docling/processed bytes，破坏 evidence 与 source fingerprint 的可信性；这是 S3 authoritative bytes 真源的完整性缺陷。
- **建议改法和验证点**: 提取单一 `matches_expected(sha256, size)` helper，并在正常模糊 Copy 与 recovery 都要求 SHA **且** size 匹配；添加同-size/different-SHA、same-SHA/different-size、二者都匹配、staging 缺失四个 fault-injection 测试，确认前三者不会错误 `final_verified`。
- **修复风险（低/中/高）**: 中；修改小，但需验证 crash recovery 与 overwrite 同 key 路径。
- **严重程度（低/中/高/严重）**: 高。

### S14-CR-04-未修复-[高]-损坏或部分非法 remote journal 被静默跳过，随后 FS orphan recovery 会丢弃可恢复 staging metadata
- **入口/函数**: remote journal 反序列化与 startup `recover_orphan_batches()`。
- **文件(行号)**: `dayu/fins/storage/remote_op_journal.py:152-175,265-318,321-399`；`dayu/fins/storage/_fs_storage_infra.py:969-1003,1417-1477`；`tests/fins/test_remote_op_journal.py:112-118`。
- **输入场景**: 已写入/已发布部分 target 后进程或磁盘故障损坏 `.dayu/remote_ops/{token}.json`，或者单个 target/state/phase 不完整、非法。
- **实际分支**: `read_journal()` 将 JSON error 和任何 `_journal_from_dict()` 失败统一返回 `None`；target 解析中非法项被 `continue` 丢弃、phase/state 不校验。`_recover_remote_ops()` 在 `journal is None` 时直接 `continue`，然后同次 `recover_orphan_batches()` 转入 `_recover_orphan_batch_dirs()`，它可按本地 `transaction.json` 清理 token staging 目录。
- **预期行为**: journal 是 S3 bytes 与 FS metadata 之间唯一 recovery 真源。无法可信解析时必须 fail closed、保留 remote objects 和 FS staging，停止该 workspace 的进一步恢复并提供稳定人工恢复错误；不能把“不可读”解释为“无 remote operation”。
- **实际行为**: 远端已发布的 final/staging bytes 不再被校验或重放，而本地 staging metadata 可被 orphan cleanup 删除/回退。结果是已完成或部分完成的操作丢失 metadata roll-forward 路径，留下不可审计的 orphan remote bytes；部分非法 target 还可能在后续 cleanup 被无声忽略。
- **直接证据**: `read_journal()` 的 `:169-175` 返回 `None`；`_journal_from_dict()` 的 `:298-309` 对非法 target 直接跳过，`:292` 仅要求 phase 是任意字符串。`_recover_remote_ops()` 的 `:992-1002` 对 `None` continue；`_recover_orphan_batch_dirs()` 随后从 `:1417` 遍历同一 token 并在 `:1473-1475` 删除 token 目录。现有测试 `test_read_invalid_json_returns_none` 明确锁定了该静默语义，没有 startup fail-closed 回归覆盖。
- **影响**: 断电/磁盘损坏这一恢复边界会从“保留并人工恢复”退化为自动丢弃 staging metadata，破坏 Slice 1.4 的 durability、atomicity 与审计性承诺。
- **建议改法和验证点**: 将 `read_journal` 的缺失、损坏、非法状态区分开；对存在但不可验证的 journal 由 recovery 抛稳定 fail-closed 错误并禁止同 token 的 FS orphan cleanup。严格校验 exact schema、phase/action/state、key、SHA/size 与 target 唯一性。增加“first-copy 后 corrupt JSON”“partial invalid target”“unknown phase”重启测试，断言 journal、staging metadata、remote objects 均保留且 startup 明确失败。
- **修复风险（低/中/高）**: 高；要定义可操作的人工恢复界面与避免阻塞无关 token 的范围。
- **严重程度（低/中/高/严重）**: 高。

## Open Questions

- 无。以上四项均可由当前代码、当前测试和已接受计划中的同一执行链直接证明。

## Residual Risk

- 关键 unit lane 已独立运行：117 passed（S3 settings/FileStore、remote journal、batch recovery、CN `to_thread`/temporary PDF、overwrite batch）；同一命令中的 11 个 MinIO integration case 因本机缺少固定 digest 的 `minio/minio` Docker image 而在 setup 阶段报错，未下载镜像或改变环境。因此真实 MinIO 行为、包括计划宣称的 crash/restart 窗口，未在本次 review 环境独立复验。
- 已运行受影响 production modules 的 pyright：0 errors, 0 warnings, 0 informations；`git diff --check` 干净。静态类型通过不覆盖上述状态机与 recovery 语义缺陷。
- 对 storage、startup/runtime、producer 和 CN/SEC 主链路已做真实入口走读；未把 implementation artifact 中的历史长语料、coverage 或 MinIO receipt 当作本次已独立执行的证据。

## Conclusion

**FAIL** — open **4 高 / 0 中 / 0 低**。不应进入 re-review 或 merge，直至上述 timeout/cancellation 与 remote journal durability/integrity 闭环被修复并以真实 fault-injection 与 MinIO integration 复验。
