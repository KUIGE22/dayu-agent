# Code Review — Corrective

## Scope

- Mode: corrective re-review of `docs/reviews/slice-4-aapl-acceptance-docs-review-mim.md`。
- Review time: `2026-08-09 20:00:05 CST`。
- Branch: `feat/investment-agent-acceptance`。
- Base: `6129122`。
- Output file: `docs/reviews/slice-4-aapl-acceptance-docs-review-corrective-mim.md`。
- Included scope: 原 review artifact M-001/M-002 两项 findings、Terra final PASS（`docs/reviews/slice-4-aapl-acceptance-docs-final-rereview-terra.md`）、implementation artifact、fix artifact。只读复核，不修改原 review 或其它文件。
- Excluded scope: 不执行 live/network/paid/commit/push/PR。

## 原 findings 复核

### M-001 — 测试计数不一致（原 Medium）

**Controller 复证**：implementation artifact 的 pytest 精确命令是 `python -m pytest tests/test_investment_agent_acceptance.py -q`，不含 `tests/fins/test_cli_formatters_coverage.py`。当前复测该精确命令：`220 passed`，与 artifact 记录一致。

我原 review 的错误前提：执行了 `python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py -q`（多加了 `test_cli_formatters_coverage.py`），产出 229 passed（= 220 + 9），误判为 same command 不一致。

**复核结论**：**M-001 = measurement/command-scope error。CLOSED。** implementation artifact 的 220 passed 记录准确。

### M-002 — runbook 未记录 --help 错误文案差异（原 Low）

**Controller 复证**：我原 review 已注明 "runbook 不要求此项" 且 "不构成 defect"。runbook `docs/acceptance/investment-agent-aapl.md` 的职责是 operator 操作指引，不要求记录 CLI 内部错误文案的细微差异。

**复核结论**：**M-002 = non-defect。CLOSED。**

### Terra final PASS

Terra final review（`docs/reviews/slice-4-aapl-acceptance-docs-final-rereview-terra.md`）为 PASS/open H/M/L=0/0/0，S4D-001 Low 已由 fix artifact 修复并经 Controller ACCEPT。与本次 corrective 复核结论一致。

## 结论

**PASS。** Open High / Medium / Low：**0 / 0 / 0**。

M-001 = measurement/command-scope error CLOSED；M-002 = non-defect CLOSED。原 review 的全部核对项（五条 help 命令、fixture/live lane、12 planned commands、manual-review PENDING exit3 无 terminal/output、独立 verify、预算/timeout、PII/secret、no-resume/new root、13 artifacts、score/monitoring residual、CI 禁止 live）均通过直接证据验证，文档准确、可执行、安全。完成即停止。
