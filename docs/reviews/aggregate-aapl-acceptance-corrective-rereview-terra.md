# AGG-AAPL-001 Corrective Aggregate Re-review（Terra）

## Scope

- Gate: `AGG-AAPL-001 corrective aggregate re-review`。
- Mode: current workspace corrective review；独立复核 `utils/investment_agent_acceptance.py` 与 `tests/test_investment_agent_acceptance.py` 当前 diff。
- Branch: `feat/investment-agent-acceptance`。
- Base context: `7c97c1f4e28af17d1a6d5c1b92706d793d9c7180`；本次仅审查 AGG-AAPL-001 allowlist 中的两处代码/测试改动。
- Required reading completed: `AGENTS.md`、Terra/MiM 初审、Controller adjudication 与修复 artifact；并沿 `verify_acceptance -> _load_completed_quality_review -> _evaluate_live_plan -> evaluator/output` 真实调用链复核。
- Excluded: 未运行 live、SEC/Web/模型/网络或付费调用；未读取密钥；未 commit、push 或创建 PR。未修改生产代码、测试、fixture、README 或既有 review artifact。

## Findings

未发现实质性问题。

## Corrective Contract Evidence

- Public live verify 在 `utils/investment_agent_acceptance.py:1770-1775` 先完成 plan/receipt prefix 的只读闭合，再调用 `_load_completed_quality_review()`；该调用位于 `_evaluate_live_plan()`、`source-inventory.json` 写入及 `acceptance-receipt.json` 原子替换之前。
- `_load_completed_quality_review()`（:2470-2492）复用 canonical、非 symlink、secret/PII 严格 ingress，并在 `QualityReview.is_complete == False` 时稳定抛出 `ContractError("live verify 要求人工质量复核已完成")`。因此 exact pending skeleton 与任意 strict-valid partial incomplete 都不能进入 evaluator 或任一 output 写路径。
- 已解析 `QualityReview` 作为显式 `quality` 参数传入 `_evaluate_live_plan()`（:4537-4543）；adapter 内不再读取 quality review，故一次 live verify 只有一次 quality 文件 ingress，且 evaluator 消费的正是该 ingress 产生的对象。
- CLI `main()`（:1917-1929）将 `ContractError` 映射到 stderr 与 exit `2`；不会 emit JSON stdout。
- 回归测试 `test_agg_aapl_001_live_verify_four_quality_states_public_boundary`（`tests/test_investment_agent_acceptance.py:7360-7461`）覆盖 exact pending、partial incomplete、complete PASS、complete FAIL：前两态锁定 evaluator `0` 次、两个 acceptance-owned 输出缺席与 planned receipts 字节不变；后两态锁定单次 evaluator、预期 PASS/FAIL 与正式 receipt。CLI 测试（:7465-7506）锁定 pending 的 exit `2`、空 stdout 与两个输出缺席。重复 verify 测试（:5547-5637）锁定 complete PASS 的 receipt 原子替换和 planned receipts 不变。

## Verification Evidence

| Gate | Command / check | Result |
|---|---|---|
| Focused acceptance | `python -m pytest tests/test_investment_agent_acceptance.py -q` | PASS: 225 passed |
| Coverage | `python -m pytest tests/test_investment_agent_acceptance.py -q --cov=utils.investment_agent_acceptance --cov-report=term-missing` | PASS: 225 passed; 88% |
| Target type check | `pyright utils/investment_agent_acceptance.py utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py dayu/fins/cli_formatters.py tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py` | PASS: 0 errors, 0 warnings |
| Ruff | `ruff check --select F,I utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` and default check | PASS |
| Owner regression | `python -m pytest tests/fins/test_cli_formatters_coverage.py tests/cli/test_research_template_command.py -q` | PASS: 225 passed |
| Fixture regression | `python -m utils.investment_agent_acceptance verify --fixture tests/fixtures/investment_agent/aapl_acceptance --json` | PASS: verdict PASS, total score 85, 13 artifacts |
| Docs / workflow gates | `python -m utils.validate_handoff_docs --json`; `python -m utils.codex_review_gate --allow-waiting --json`; `python -m utils.dual_model_pipeline_check --json` | PASS: all `ok: true` |
| Diff check | `git diff --check -- utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` and full `git diff --check` | PASS: clean |

## Open Questions

- 无。

## Residual Risk

- 这是离线、确定性 corrective re-review；它不证明未授权 live lane 的外部数据 freshness 或第三方服务可用性。该 lane 未执行且不属于本 gate。
- 工作区另有未跟踪的既有/并发 review artifact，不属于本次 allowlist，未修改，也不影响对两处 corrective diff 的结论。

## Conclusion

**PASS。** AGG-AAPL-001 的 accepted corrective contract 已满足。Open High / Medium / Low：**0 / 0 / 0**。
