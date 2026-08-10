# Slice 1.4 runtime-factory 测试 allowlist 勘误验收

- **时间**：2026-08-11T02:57:37+0800
- **目标计划**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **状态**：`ACCEPTED / DUAL PLAN RE-REVIEW PASS`
- **Controller fix**：
  `docs/reviews/plan-fix-20260811-025009-slice-1.4-cn-runtime-factory-allowlist-codex.md`
- **Terra review**：
  `docs/reviews/plan-review-20260811-slice-1.4-cn-runtime-factory-allowlist-terra.md`
- **MiM Native review**：
  `docs/reviews/plan-review-20260811-slice-1.4-cn-runtime-factory-allowlist-mimo-native.md`

## 验收结论

本次唯一 plan gap 已关闭：`tests/fins/test_cn_download_runtime.py` 获准在测试边界更新
`_RuntimeCnPipelineFactory.build_pipeline`，显式接收并原样转发 runtime 的唯一
`batching_repository` 与共享 `preparation_gate`，并以 identity 断言证明传播。

Terra 与 MiM Native 均独立结论 `PASS`，open H/M/L=`0/0/0`。Terra 实测完整
`tests/fins/` 共 2126 项，现有 2 个失败均来自这一旧 fake 签名；不存在第二类失败。
两路均确认不需要修改 production，也禁止反射、`TypeError` fallback、compat wrapper
或条件性漏传。

## 冻结与后续 gate

plan-fix/re-review 前后的非文档 tracked WIP binary diff SHA-256 均为
`505100a132c97e8a1210bc8b923cbbd26f870a1c5f0796c92108d7b891696727`；生产、测试、
README 与依赖 WIP 在 plan gate 中未被修改。Controller 现在恢复 Slice 1.4
implementation：先修目标测试 fake 并重跑目标文件和完整 `tests/fins/`，然后继续
MinIO integration、clean Python 3.11 lanes、coverage/static/README 等原剩余门禁。
本验收不授权 push、PR、live、联网数据源或外部付费动作。
