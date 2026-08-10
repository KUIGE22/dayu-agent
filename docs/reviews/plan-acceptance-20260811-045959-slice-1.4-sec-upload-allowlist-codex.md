# Slice 1.4 SEC upload workflow allowlist 勘误接受记录

- **Gate**：Gateflow / accepted plan erratum
- **Work unit**：Investment Platform Restoration
- **Slice**：1.4 S3-compatible Fins blob repository
- **目标计划**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **状态**：ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **时间**：2026-08-11 04:59:59 +0800
- **冻结 implementation WIP hash**：`17b702deabf424a4f737a10965e5daae273b2090051f83cc402a8a019c986901`

## 1. Accepted scope

本勘误只把 `dayu/fins/pipelines/sec_upload_workflow.py` 加入 Slice 1.4 production
allowlist，允许删除 filing/material 两条 upload workflow 在
`DoclingUploadService.execute_upload` 前的 overwrite pre-reset 与因此未使用的 import。
overwrite reset 的唯一 owner 仍是 service 的同-core per-document explicit batch。

测试只在既有 filing/material workflow test owner 增加真实调用链回归：合法 company
upsert 短 AUTO 不计入 overwrite-reset 负向断言；每次 reset 必须在 service token active
期间发生；成功只能一次 commit，reset 后失败只能一次 rollback，并保留旧 source/blob。

## 2. Review closure

- Initial Terra：
  `docs/reviews/plan-review-20260811-044553-slice-1.4-sec-upload-allowlist-terra.md`，
  FAIL，唯一正式 finding `TERRA-S14-UPLOAD-ALLOWLIST-01`；
- Initial MiM Native：
  `docs/reviews/plan-review-20260811-044549-slice-1.4-sec-upload-allowlist-mimo-native.md`，
  PASS/open0；
- Corrective Terra：
  `docs/reviews/plan-review-20260811-045004-slice-1.4-sec-upload-allowlist-corrective-terra.md`，
  PASS/open0；
- Corrective MiM Native：
  `docs/reviews/plan-review-20260811-045007-slice-1.4-sec-upload-allowlist-corrective-mimo-native.md`，
  PASS/open0；
- Final Terra：
  `docs/reviews/plan-review-20260811-045322-slice-1.4-sec-upload-allowlist-final-terra.md`，
  PASS/open0；
- Final MiM Native：
  `docs/reviews/plan-review-20260811-045645-slice-1.4-sec-upload-allowlist-final-mimo-native.md`，
  PASS/open0。

最终 open H/M/L=`0/0/0`。唯一正式 finding 已修复。Controller 对 company-upsert AUTO
与 reset-induced AUTO 的计数域澄清是 post-review hardening，不是新增 reviewer finding。
错误地把中间分析写成第二个 Terra finding 的早期 MiM 草稿不属于 accepted evidence。

## 3. Controller decision

本勘误达到 handoff-ready/code-generation-ready，且没有扩大 public contract、owner、failure
semantics、production abstraction 或依赖。Slice 1.4 implementation 可恢复；实现仍须完成
两个真实 workflow 回归、focused/static/diff gates、临时项清理和 durable implementation
artifact 后才能进入 code review。

当前未授权 push、PR、live、merge 或外部动作。
