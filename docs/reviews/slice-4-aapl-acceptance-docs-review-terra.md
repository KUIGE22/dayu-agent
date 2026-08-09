# Code Review

## Scope

- Mode: current changes（Slice 4 docs）。
- Review time: `2026-08-09 19:46:40 CST`。
- Role: 独立 Terra Slice 4 docs reviewer；非 Controller，不实施修复。
- Branch: `feat/investment-agent-acceptance`。
- Base: `6129122d781c132a167ebf8be3e4575f5a7f4144`。
- Output file: `docs/reviews/slice-4-aapl-acceptance-docs-review-terra.md`。
- Included scope: 根 `AGENTS.md`、accepted AAPL plan、manual-review accepted code artifacts、Slice 4 implementation artifact；当前 `README.md`、`tests/README.md` 与 `docs/acceptance/investment-agent-aapl.md`。逐项对照真实 acceptance CLI help/parser、`build_phase_specs()`、contracts/evaluator、fixture verify、validators、package config/assets、测试索引及文档链接。
- Excluded scope: 不修改 README/runbook/tests/code/plan/既有 artifact；不执行 `prepare`、`run`、live verify、SEC/Web/模型/网络/付费调用、commit 或 push。
- Parallel review coverage: 无。

## Findings

### S4D-001-未修复-低-Slice 4 implementation artifact 错报顶层 CLI help 的实际结果

- **入口/函数**: `python -m utils.investment_agent_acceptance --help`。
- **文件(行号)**: `docs/reviews/slice-4-aapl-acceptance-docs-implementation-20260809-deepseek-flash.md:33`；`utils/investment_agent_acceptance.py:1846-1862,1835-1843`。
- **输入场景**: reviewer/operator 按 implementation artifact 的“零编辑核对”复现顶层 `--help`。
- **实际分支**: `main()` 将 `("--help",)` 交给 `parse_cli_arguments()`；它未匹配 `prepare`/`run`/`verify`，最后调用顶层 parser 的 `error("子命令必须是 prepare、run 或 verify")`。
- **预期行为**: artifact 应如实记录实测结果；若将顶层 `--help` 作为验证证据，则它应能列出子命令并以帮助语义退出，或 artifact 不应声称该验证已成功。
- **实际行为**: 实测输出为 `usage: investment-agent-acceptance [-h]` 后接“子命令必须是 prepare、run 或 verify”，退出码为 `2`；并未列出三个子命令。三个具体子命令的 `--help` 均正常退出 `0`。
- **直接证据**: artifact 第 33 行声称“`python -m utils.investment_agent_acceptance --help` / 无子命令 exit 2 | 仅 `prepare`、`run`、`verify`”。当前真实命令可直接复现上述 exit `2`，而 CLI 代码的 fallback 位于 1835–1843 行。
- **影响**: 不影响 runbook 中的 prepare/run/verify 实际命令、预算门禁或 live 隔离；但 implementation artifact 的验证记录不可复现，削弱审查链的准确性。
- **建议改法和验证点**: 仅在获授权的 artifact 更正中改为“顶层无子命令/`--help` 均 exit 2；以三个子命令 help 作为参数面证据”，或修复 CLI 后重新记录实际结果；对两种顶层输入与三个子命令 help 分别断言 exit/output。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## Open Questions

- 无。

## Residual Risk

- 未运行 live lane；这是明确禁止且未获授权的范围。live 的 source freshness、价格、预算与费用只在本次授权后的真实 download command evidence、显式 snapshot 和 plan fingerprint 中成立。
- 文档所述静态 contract 已用 fixture/解析器复核，但 fixture 不证明今天的 source freshness，也不授权外部数据或付费模型调用。

## Validation

- `python -m utils.validate_handoff_docs --json`：通过。
- `python -m utils.codex_review_gate --allow-waiting --json`：通过；状态 `WAITING_FOR_TASK`。
- `python -m utils.dual_model_pipeline_check --json`：通过。
- `python -m utils.investment_agent_acceptance verify --fixture tests/fixtures/investment_agent/aapl_acceptance --json`：exit 0，`PASS`、总分 85、13 个工件；运行后 fixture runtime/lock 无残留。
- acceptance 子命令 help、缺 `--json`、fixture/live 参数互斥、Fins command/validator help、`build_phase_specs()`、13 工件、评分/环境变量/脱敏/freshness/terminal-absent/no-resume 路径均已静态核对。
- README、tests README 与 runbook 的相对链接目标存在；测试索引列出的两个测试文件存在；`git diff --check` 通过。

## Conclusion

**FAIL。** Open High / Medium / Low：**0 / 0 / 1**。唯一开放项是 Slice 4 implementation artifact 对顶层 `--help` 的可复现性错误；未发现会诱导 live 调用、资金支出、预算默认化、价格默认化、fixture freshness 误用、PII/secret 泄漏、cleanup/resume 或 12 planned + pending 独立 verify 语义漂移的问题。完成即停止。
