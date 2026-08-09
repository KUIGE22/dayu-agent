# AAPL acceptance Slices 0–4 聚合深审裁决

- 日期：2026-08-09
- 角色：Codex Controller
- 分支 / HEAD：`feat/investment-agent-acceptance` / `c6e682f`
- 比较基线：`7c97c1f4e28af17d1a6d5c1b92706d793d9c7180`
- 状态：**CLOSED / DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**
- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**

## 审查来源

- Terra：`docs/reviews/aggregate-aapl-acceptance-deepreview-terra.md` — FAIL，open H/M/L=`1/0/0`
- MiM：`docs/reviews/aggregate-aapl-acceptance-deepreview-mim.md` — PASS，open H/M/L=`0/0/0`
- DeepSeek V4 Flash 修复：`docs/reviews/aggregate-aapl-acceptance-review-fix-20260809-deepseek-flash.md`
- Terra corrective：`docs/reviews/aggregate-aapl-acceptance-corrective-rereview-terra.md` — PASS，open H/M/L=`0/0/0`
- MiM corrective：`docs/reviews/aggregate-aapl-acceptance-corrective-rereview-mim.md` — PASS，open H/M/L=`0/0/0`

## Controller 裁决

### AGG-AAPL-001（Terra High）

**ACCEPTED / FIXED / CLOSED。** `run_acceptance()` 在 12 个 planned phases 通过且 `quality-review.json` 仍为 exact pending skeleton 时，会正确返回 `PENDING_MANUAL_REVIEW`，不执行 terminal，也不写 acceptance outputs；修复前 public live `verify_acceptance()` 只验证 receipt prefix，随后仍调用 evaluator，并写入 `source-inventory.json` 与 `acceptance-receipt.json`。这违反 accepted plan 与 runbook 的“人工完整填写后才运行独立 verify”边界。

该缺陷不仅适用于 exact skeleton：任何 `QualityReview.is_complete == False` 的部分填写状态都不得发布 acceptance outputs。Evaluator 仍保持 trusted post-ingress pure evaluator；拒绝必须位于 public live verify 的发布权限边界。

## 精确修复契约

1. Live `verify_acceptance()` 在调用 evaluator、写 `source-inventory.json` 或写 `acceptance-receipt.json` 前，只读并严格解析 canonical quality review。
2. 若 `quality_review.is_complete` 为 `False`，以稳定 `ContractError` fail closed；CLI exit `2`。
3. 拒绝路径不得调用 evaluator，不得创建或改写 `source-inventory.json`、`acceptance-receipt.json`，既有 planned phase receipts 必须保持逐字节不变。
4. 避免同一次 verify 重复读取 quality review；将已严格解析的 `QualityReview` 传入 live evaluator adapter，保持单一 ingress truth。
5. 完整人工 review 继续允许独立 verify：完整且达标可 PASS；完整但不达标可生成正式 FAIL receipt。Fixture verify 行为不变。
6. 补 exact pending skeleton、部分填写 incomplete、完整 PASS、完整 FAIL 的 public live verify 回归测试；至少锁定 evaluator 调用次数、两个 acceptance-owned 输出和 planned receipt bytes。
7. 仅修改 acceptance CLI、现有 acceptance tests 与本 finding 的 fix/closure artifacts；不修改 plan、contracts、evaluator、Fins formatter、fixtures、README/runbook 或其它生产模块。

## 修复与复审闭环

- Public live verify 现在于 evaluator 与任何 acceptance-owned output 之前，单次 strict 读取 canonical `QualityReview`；`is_complete == False` 时稳定抛出 `ContractError`，CLI exit `2`。
- Exact pending 与 partial incomplete 两态均锁定 evaluator 调用 `0`、`source-inventory.json`/`acceptance-receipt.json` 缺席、planned receipts 字节不变；complete PASS/FAIL 均继续生成正式 receipt；fixture verify 不变。
- Focused acceptance：`225 passed`；目标覆盖率 `88%`；目标 Pyright `0 errors / 0 warnings`；Ruff、owner tests、fixture verify、docs gates 与 diff-check 全部通过。
- Terra corrective：PASS，open H/M/L=`0/0/0`。
- MiM corrective：PASS，open H/M/L=`0/0/0`。
- 最终 Controller open H/M/L=`0/0/0`；AGG-AAPL-001 已 CLOSED。

## 其它观察

- MiM 对其审查范围内未报告开放 finding；其 PASS 不否定 Terra 的直接状态机证据。
- 修复已由 Terra 与 MiM 分别做 corrective re-review，双路均 PASS/open0；可以进入 aggregate accepted commit。
- 本裁决不授权任何 live、SEC、Web、外部模型或付费验收执行。
