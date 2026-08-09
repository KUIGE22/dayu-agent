# Code Review

## Scope

- Mode: current changes（aggregate deepreview）。
- Review time: `2026-08-09 20:11:57 CST`（本机系统时钟）。
- Branch / HEAD: `feat/investment-agent-acceptance` / `c6e682fe618c9e267f5d4804df92d4bddb82a46f`。
- Base: `7c97c1f4e28af17d1a6d5c1b92706d793d9c7180`。
- Output file: `docs/reviews/aggregate-aapl-acceptance-deepreview-terra.md`。
- Included scope: `base...HEAD` 的全部 115 个变更文件（production、tests、fixtures、runbook/README），accepted plan `docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`，以及 Slice 0–4 的 implementation、adjudication、fix、re-review/closure artifacts。重点沿 `prepare -> run -> manual handoff -> independent verify`、phase receipt、fingerprint、budget/timeout、owner formatter ingress、评分真源、13 artifacts 与 CLI 边界走读。
- Excluded scope: 未执行 `prepare`、`run`、live verify，未访问 SEC/Web/模型/网络，未读取 secret 值，未发生付费调用、commit、push 或 PR 操作。
- Parallel review coverage: 无（由主 reviewer 复核完整状态链）。工作区已有未跟踪的 `docs/reviews/aggregate-aapl-acceptance-deepreview-mim.md` 不属于本次输出，未读取或修改。

## Findings

### 001-未修复-高-Exact pending handoff 可被独立 verify 提前发布 acceptance outputs
- **入口/函数**: `verify_acceptance()` 的 live 分支；触发命令为 `python -m utils.investment_agent_acceptance verify --plan ... --fingerprint ... --json`。
- **文件(行号)**: `utils/investment_agent_acceptance.py:1746-1774`；关联 pending 判定在 `utils/investment_agent_acceptance.py:1707-1717`、`2446-2463`。
- **输入场景**: 12 个 planned phases 已全部 passed，`quality-review.json` 仍是 prepare 写入的 exact `PENDING_MANUAL_REVIEW` skeleton，operator 尚未填写任何人工 rubric。
- **实际分支**: `run_acceptance()` 正确在 :1710 命中 exact-pending shortcut 并不写 terminal/acceptance outputs；但随后任意调用 live `verify_acceptance()` 时，:1769-1771 仅加载完整 planned prefix 后就执行 `_evaluate_live_plan()`，没有调用 `_quality_review_is_exact_pending()` 或要求 `QualityReview.is_complete`。:1772-1773 无条件覆盖写入 `acceptance-receipt.json`；`_evaluate_live_plan()` 还会发布 `source-inventory.json`。
- **预期行为**: exact pending 是人工 handoff 的吸收态；在人工完整填写 quality review 前，独立 verify 必须 fail closed，且不得创建任何 acceptance-owned output。只有完整人工复核后才允许独立 verify 写 `source-inventory.json` 与 `acceptance-receipt.json`。
- **实际行为**: pending skeleton 可被独立 verify 评估为 `PENDING_MANUAL_REVIEW`（exit 3），但同时把本应在手工复核后才出现的 source inventory 与 normalized acceptance receipt 发布到 run root，破坏 pending handoff 的 receipt truth 与人工受理边界。
- **直接证据**: runbook 明确要求“填写完成后只运行独立 live verify”（`docs/acceptance/investment-agent-aapl.md:213-225`），并明确 pending handoff 不写 `source-inventory.json`/`acceptance-receipt.json`（:193-205）。反而现有测试 `tests/test_investment_agent_acceptance.py:5540-5625` 构造 pending `EvaluationResult` 并两次调用 `verify_acceptance()`，断言 receipt 被写入；这证明该路径是已接受、可复现的实际行为，而非推测。
- **影响**: 在未完成人工质量复核时，operator 可得到并持久化看似正式的 acceptance receipt/source inventory。虽然 verdict 是 pending 而非 PASS，但系统已失去“pending 无 acceptance outputs”的强边界；下游或人工流程若按文件存在性受理，会把未完成 review 的 run 误当作已完成 verify，且之后无法区分文件是在合法人工 review 后还是提前产生。
- **建议改法和验证点**: 在 live `verify_acceptance()` 的 receipt loader 之后、任何 `_evaluate_live_plan()`/写入之前，严格读取 quality review；若其 canonical bytes 等于 exact pending skeleton，抛 `ContractError`（exit 2）并断言 `source-inventory.json`、`acceptance-receipt.json` 与 phase receipts 均保持缺席/原字节。保留现有“完整 PASS/FAIL review、terminal absent”的独立 verify 测试，并删除或改写当前允许 pending verify 写 receipt 的测试。不要把该拒绝下沉到 evaluator：这是 runner 的 state-transition/发布权限，而非评分规则。
- **修复风险（低/中/高）**: 低；边界是单一 live verify 入口，且已有 strict pending helper 与 handoff tests 可直接复用。
- **严重程度（低/中/高/严重）**: 高。

## Open Questions

- 无。上述状态跃迁、写入副作用与文档契约均可由同一 live verify 数据路径直接证明。

## Residual Risk

- 未执行任何 live lane；这是用户明确禁止且尚未授权的范围。离线测试无法证明 SEC、外部模型或当天价格/文档 freshness。
- 已运行离线验证：`pytest -q tests/test_investment_agent_acceptance.py`（220 passed）、关联 research-template/formatter tests（225 passed）、相关 Pyright（0 errors）、Ruff（pass）、handoff/docs gates（pass）、fixture verify（PASS，13 artifacts）；这些结果不覆盖本 finding 所需的“pending live verify 必须拒绝”行为，现有测试反而锁定了错误行为。
- receipt/formatter 对 owner 输出文案仍为 fail-closed 可用性边界；package/owner drift 会停止运行，需重新 prepare/review。

## Conclusion

**FAIL。** Open High / Medium / Low：**1 / 0 / 0**。在修复 finding 001 并补齐 pending live verify 不发布输出的回归测试前，不应通过 aggregate acceptance deepreview。
