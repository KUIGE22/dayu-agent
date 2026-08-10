# Slice 1.4 S3-compatible Fins blob repository code review 裁决

- **Gate**：Gateflow / code review adjudication
- **Work unit**：Investment Platform Restoration
- **Slice**：1.4 S3-compatible Fins blob repository
- **状态**：CLOSED / DUAL RE-REVIEW PASS
  （此前：CORRECTIVE RE-REVIEW FAIL / ROUND-2 FIX REQUIRED）
- **Round-2 fix**：
  `docs/reviews/slice-1.4-code-review-round2-fix-20260811-codex.md`
  （S14-RR-01 / S14-RR-02 均已 REVIEW FIX APPLIED）
- **Implementation artifact**：
  `docs/reviews/slice-1.4-implementation-artifact-s3-blob-repository.md`
- **Terra review**：
  `docs/reviews/code-review-20260811-slice-1.4-s3-blob-repository-terra.md`
  （FAIL，4H/0M/0L）
- **MiM Native review**：
  `docs/reviews/code-review-20260811-053319.md`
  （FAIL，1H/2M/3L observations）
- **时间**：2026-08-11 05:38 +0800
- **Round-1 corrective re-review**：
  - `docs/reviews/code-rereview-20260811-slice-1.4-s3-blob-repository-terra.md`
    （FAIL，1H/1M/0L）
  - `docs/reviews/code-rereview-20260811-slice-1.4-s3-blob-repository-mim.md`
    （PASS，0H/0M/0L）

## 1. Accepted findings

### S14-CR-01 — accepted / High

`provider_download_timeout_seconds` 从 caller 传入
`run_cn_download_single_filing_stream()`，但阶段 A 直接 await
`asyncio.to_thread()`，没有 timeout/deadline 消费点；`except asyncio.TimeoutError`
不可达。配置 hard timeout 当前确实失效。

### S14-CR-02 — accepted / High

阶段 A/B 的 `to_thread` inner future 没有独立 owner、shield、completion callback 或
统一 finally。outer cancellation 抛 `asyncio.CancelledError`，不被当前自定义
`CancelledError`/`Exception` 捕获，slot 会永久 active。修复不得以取消时立即 release
代替，因为底层 worker 仍在运行；slot 与 owned temp PDF 必须绑定真实 inner completion。

### S14-CR-03 — accepted / High

正常模糊 Copy 与 startup recovery 都以 digest **或** size 任一匹配判成功。同-size/
different-SHA 对象可被持久为 `final_verified`，随后 FS metadata 指向错误 bytes。目标
身份必须同时匹配 SHA-256 与 size，且两条路径共用同一真源判断。

### S14-CR-04 — accepted / High

存在但损坏/非法的 remote journal 当前被 `read_journal()` 归一成 `None`，非法 target
又被部分跳过；startup 随后继续 FS orphan cleanup，可删除唯一 metadata recovery 路径。
缺失 journal 与损坏 journal 必须分离：仅真正不存在返回 `None`，存在但任何 schema/
phase/action/state/key/digest/size/uniqueness 非法都稳定 fail closed，并保留 journal、
staging metadata 与 remote objects。

## 2. Rejected findings

### MiM H — S3 directory delete intent — rejected-with-reason

`delete_entry` 的 accepted contract 是单个直系条目/final key；正常 Fins filename 经
`_normalize_entry_name()` 禁止路径分隔符，生产 rescue caller 跳过非文件项，snapshot
只产生固定直系文件。异常嵌套对象只会形成 virtual directory；当前 stage 不存在的目录
key 后会在 metadata swap 前 HEAD fail closed，不会出现 reviewer 所述“成功提交但留下
meta.json”。meta/manifest 还是 FS metadata，不属于 handle 下的远端 blob。S14-CTRL-13
同时禁止 prefix sweep，因此 reviewer 建议反而违反 accepted contract。Terra follow-up
独立核对后结论同为 REJECT。

### MiM M — staged delete drift — rejected-with-reason

S14-CTRL-13 明确要求 metadata swap 前 remote 缺失或 digest/size drift 必须 fail closed，
保留 journal 供人工恢复。不能把可能的 overwrite 猜测当作可忽略 drift；publish 与 delete
target 已有独立状态机。

### MiM M — bounded publish retry — rejected-with-reason

reviewer 自身确认当前一次 bounded retry + startup recovery 已满足 accepted contract。
网络不稳定时不允许在同步 commit 中无限退避；这属于非缺陷的策略建议。

### MiM L — runtime asserts — rejected-with-reason

当前 `isinstance(..., StagedFileStoreProtocol)` 是 accepted runtime capability guard，注入
错误实现仍会在随后协议调用处失败；review 没有证明可造成错误提交或静默降级。可读性
偏好不构成当前 Slice correctness finding。

### MiM L — cleanup state/journal window — rejected-with-reason

remote delete 明确幂等，journal 写前 crash 会在 startup 重放同一 delete 并收敛；这是
计划要求的 crash window，不是竞态缺陷。reviewer 也明确写了“无需修改”。

### MiM L — presign expires type — rejected-with-reason

public typed signature 已固定 `int`；违反类型契约的 Python caller 抛 `TypeError` 不会产生
错误 URL 或越权。没有运行时宽输入 schema 需要在此重复收窄。

## 3. Fix scope

fix 只处理 `S14-CR-01..04`，不得顺手实现被拒绝的 MiM observations。允许修改 accepted
Slice 1.4 owner 与其既有测试/README/artifact；不得增加 compatibility glue、reflection、
prefix sweep、第二 storage owner 或放宽 fail-closed 语义。

必须新增 adversarial tests：

1. CN 阶段 A 参数本身触发 timeout；late success/late exception 不进入 B/C，slot 仅在
   inner 完成后 release，容量 1 的第二 filing 在此前不能开始；outer cancel during A/B
   同样最终 cleanup/release 且不发布；
2. publish normal/recovery 对 same-size/different-SHA、same-SHA/different-size、完全匹配、
   staging 缺失矩阵；
3. corrupt JSON、partial/unknown target、unknown phase/state/action、duplicate key journal
   的 startup fail-closed，且 journal/staging/remote bytes 保留；真正 journal missing 的
   既有路径不回归。

production 改动后须重算所有本次再次修改生产文件的 statement coverage `>=80%`，运行
focused fault-injection、changed pyright、Ruff F/I/default、strict added-line forbidden
scan、`git diff --check`；能使用现有 MinIO 时复跑对应 integration，镜像不可用则如实记录，
不得伪称执行。fix artifact 完成后进入 Terra + MiM Native dual re-review。

当前未授权 commit、push、PR、merge 或 live。

## 4. Round-1 corrective re-review 裁决

MiM Native 复审确认原四项修复及既有回归均通过；Terra 进一步构造了两个此前测试未覆盖、
且能产生真实副作用的反例。Controller 以可复现的更强证据为准，接受以下两项，不以一条
PASS 抵消已证明的缺陷。

### S14-RR-01 — accepted / High

存在 `.dayu/remote_ops/<token_x>.json`，但 payload 中 `operation_id=token_y` 时，当前
`read_journal()` 只验证 payload ID 非空，没有把文件身份作为 expected ID 传入严格 parser。
恢复随后先按 payload publish target 写入 final remote key，直到使用 `token_y` 查找 FS
staging 才 fail closed。Terra 最小复现确认 `final_written_before_fail_closed=True`。

修复必须在任何 remote/FS 副作用前绑定并验证 filename ID == payload ID；mismatch 必须抛
`RemoteOpJournalError`，保留原 journal、batch staging、remote staging/final bytes。新增
restart fault test，明确断言零 publish/delete/FS swap。

### S14-RR-02 — accepted / Medium

`preparation_gate=None` 是公开协议与 standalone/FS `CnPipeline` 的允许路径。当前 late-inner
cleanup callback 只在 slot ownership 存在时绑定；无 gate 的 Stage A timeout/cancel 返回后，
provider 晚到的 `DownloadedReportAsset` 无 owner 回收 temp PDF。Terra 最小复现确认
`late_pdf_files=['A1_1.pdf']`。

修复必须把 inner task/temp asset owner 与可选的容量 slot owner 分离：所有 Stage A inner
均注册 late completion cleanup；有 gate 时再额外负责最后一个 inner 后恰好一次 release。
新增无 gate 的 parameter-timeout 与 outer-cancel tests，覆盖 late success/late exception、
零 B/C、零 repository publish、最终零 temp PDF。

### Round-1 其余结论

- `S14-CR-03` 的 SHA **且** size 单一真源已闭合；
- 写侧 duplicate delete intent 去重与严格 reader 已闭合；
- MinIO 在实现方及 MiM 环境中为 11 passed；Terra 环境缺固定镜像导致 setup fail-fast，属于
  独立复验环境差异，不改变上述两项代码裁决，也不得替代 round-2 的可用环境复跑；
- 旧 MiM rejected observations 维持关闭，无新直接反例。

## 5. Round-2 fix scope

只修 `S14-RR-01`、`S14-RR-02`，不得放宽 journal reader、引入兼容读取、prefix sweep、
第二资源 owner 或修改被拒绝的旧 observations。修后重跑对应 adversarial tests、Fins + MinIO、
所有再次修改生产文件 statement coverage `>=80%`、changed pyright 0、Ruff、strict added-line
forbidden scan 与 `git diff --check`，然后重新进入 Terra + MiM Native 双路复审。

## 6. Round-2 fix 应用状态（2026-08-11）

Round-2 fix 已应用，见
`docs/reviews/slice-1.4-code-review-round2-fix-20260811-codex.md`：

- **S14-RR-01**：`read_journal` 把文件名 operation id 作为期望身份传入
  `_journal_from_dict`（payload `operation_id` 必须精确相等），并校验每个 publish
  target 的 `staging_key` 属于 `.dayu-staging/{operation_id}/` 命名空间；mismatch
  在**任何远端/FS 副作用前**抛 `RemoteOpJournalError`。新增 restart fault tests
  （body operation_id mismatch、staging 命名空间 mismatch）断言零 publish/delete/
  FS swap、journal/batch staging/远端 bytes 全保留。
- **S14-RR-02**：`_PreparationSlotOwnership` 重构为 `_PreparationInnerOwner`
  （`gate: CnPreparationGate | None`）：inner task / temp asset owner 与可选的容量
  slot owner 分离，无论是否注入 `preparation_gate` 都绑定 late completion cleanup，
  有 gate 时 done callback 仍在最后一个 inner 完成后恰好 release 一次。新增无 gate
  的 parameter-timeout（late success / late exception）与 outer-cancel tests，
  断言零 B/C、零 repository batch/publish、late 临时 PDF 最终消失。
- 验证：focused 172 passed；完整 `tests/fins` + MinIO integration 11 case
  **2213 passed**；三生产文件 statement coverage
  `cn_download_filing_workflow.py 84.2%`、`_fs_storage_infra.py 88.0%`、
  `remote_op_journal.py 92.6%`（均 >=80%）；changed pyright 0 errors/0 warnings；
  Ruff F/I + default 0；strict added-line forbidden scan 0 新增 hits；
  `git diff --check` 干净。未 commit/push/PR/merge。等待 Terra + MiM Native
  双路复审。

## 7. Final dual re-review closure（2026-08-11）

- Terra：`docs/reviews/code-rereview-round2-20260811-slice-1.4-s3-blob-repository-terra.md`
  — **PASS / open H=0 M=0 L=0**；
- MiM Native：`docs/reviews/code-rereview-round2-20260811-slice-1.4-s3-blob-repository-mim.md`
  — **PASS / open H=0 M=0 L=0**；
- `S14-CR-01..04`、`S14-RR-01/02` 均 CLOSED；旧 MiM rejected observations 无回归；
- Controller accepted findings remaining：**0**，open H/M/L：**0/0/0**。

本 Slice code-review gate 已关闭，可形成 accepted 本地提交；仍未授权 push、PR、merge 或 live。
