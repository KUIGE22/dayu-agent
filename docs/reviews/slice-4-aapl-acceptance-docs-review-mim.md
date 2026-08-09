# Code Review

## Scope

- Mode: current changes（Slice 4 AAPL acceptance 文档独立 code/docs review）。
- Review time: `2026-08-09 19:57:36 CST`。
- Branch: `feat/investment-agent-acceptance`。
- Base: `6129122`（accepted manual-review handoff commit）。
- Output file: `docs/reviews/slice-4-aapl-acceptance-docs-review-mim.md`。
- Included scope: 根 `AGENTS.md`、`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`、`docs/acceptance/investment-agent-aapl.md`、`README.md`、`tests/README.md`、`docs/reviews/slice-4-aapl-acceptance-docs-implementation-20260809-deepseek-flash.md`、`docs/reviews/slice-4-aapl-acceptance-docs-review-terra.md`、`docs/reviews/slice-4-aapl-acceptance-docs-review-fix-20260809-deepseek-flash.md`。逐项核对真实 CLI/parser/exit/status 与 `utils/investment_agent_acceptance*.py` 代码事实。
- Excluded scope: 不修改任何文件；不执行 `prepare`/`run`/live verify/SEC/Web/模型/网络/付费调用；不 commit/push/PR。
- Parallel review coverage: 无。

## Findings

### M-001-未修复-中-implementation artifact 测试计数与实际运行不一致

- **入口/函数**: `python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py -q`。
- **文件(行号)**: `docs/reviews/slice-4-aapl-acceptance-docs-implementation-20260809-deepseek-flash.md:73`；`docs/reviews/slice-4-aapl-acceptance-docs-review-fix-20260809-deepseek-flash.md:52`。
- **输入场景**: reviewer 在当前 worktree 执行与 implementation artifact 相同的 focused acceptance test 命令。
- **实际分支**: pytest 正常执行全部用例。
- **预期行为**: implementation artifact 应准确记录实测结果，使审查链可复现。
- **实际行为**: implementation artifact 声称 `220 passed`，当前实测为 `229 passed`。fix artifact 重申 "上一轮 focused acceptance 220 passed 保持有效"，但未给出基线 commit SHA 或 pytest --co 枚举以证明 220 是当时真实值。9 个用例差异未被解释。
- **直接证据**: 当前实测输出 `============================= 229 passed in 4.11s ==============================`；implementation artifact 第73行声称 `220 passed`。
- **影响**: 不影响 runbook 命令语义、评分规则或 live 隔离；但 implementation/fix artifact 的测试验证记录不可复现，削弱 Slice 4 文档审查链的可信度。若 229 是后续代码变更后的新基线，artifact 应更新为当前实测值并标注基线 SHA。
- **建议改法和验证点**: 将 implementation artifact 的测试计数更新为当前实测 `229 passed`，并注明实测基线 commit SHA。或在 artifact 中给出 `pytest --co -q` 的枚举以证明当时 220 是准确的。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### M-002-未修复-低-implementation artifact 未明确记录无子命令与顶层 --help 的区别

- **入口/函数**: `python -m utils.investment_agent_acceptance`（无子命令）与 `python -m utils.investment_agent_acceptance --help`。
- **文件(行号)**: `docs/reviews/slice-4-aapl-acceptance-docs-implementation-20260809-deepseek-flash.md:34-35`；`utils/investment_agent_acceptance.py:1843,1835`。
- **输入场景**: 两种顶层输入的实际错误文案不同。
- **实际分支**: 无子命令走 `main()` → `parse_cli_arguments(())` → fallback → `_command_parser().error("必须指定 prepare、run 或 verify")`（exit 2）；`--help` 走 `parse_cli_arguments(("--help",))` → argparse 子 parser `error("子命令必须是 prepare、run 或 verify")`（exit 2）。
- **预期行为**: implementation artifact 的零编辑核对表应区分两条命令的不同错误文案。
- **实际行为**: fix artifact 已将两行分开为精确事实（第34行"必须指定"、第35行"子命令必须是"），S4D-001 已修复。但 runbook `docs/acceptance/investment-agent-aapl.md` §3 和 §5 未提及无子命令与 `--help` 的区别，operator 按 runbook 复现时会看到两套不同错误文案，可能产生混淆。
- **直接证据**: 实测无子命令输出 `"error: 必须指定 prepare、run 或 verify"`；`--help` 输出 `"error: 子命令必须是 prepare、run 或 verify"`。fix artifact 第22-23行已分开记录。
- **影响**: 低。operator 面向的 runbook 不要求记录 CLI 内部错误文案差异；但这属于文档完整性边缘项。
- **建议改法和验证点**: 若 runbook 选择记录 CLI help 事实，可在 §3 或附录中补一句"顶层无子命令或 `--help` 均 exit 2 并提示子命令列表"。否则保持现状不构成 defect。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## 逐项核对（adversarial review 要求的全部 gate 项）

以下逐项列出直接证据，不使用间接迹象：

### 1. 五条 help 命令

| 命令 | 实测 exit | 实测输出摘要 | 文档记录 | 一致 |
|---|---|---|---|---|
| `python -m utils.investment_agent_acceptance`（无子命令） | 2 | `error: 必须指定 prepare、run 或 verify` | implementation artifact: exit 2; fix artifact: exit 2 | ✓ |
| `python -m utils.investment_agent_acceptance --help` | 2 | `error: 子命令必须是 prepare、run 或 verify` | implementation artifact: exit 2; fix artifact: exit 2 | ✓ |
| `prepare --help` | 0 | 完整参数面：`--ticker --company --template --as-of --run-root --price-snapshot --max-model-requests --max-total-tokens --max-estimated-cost --budget-currency --max-wall-seconds --json` | runbook §3 参数一致 | ✓ |
| `run --help` | 0 | `--plan --fingerprint --json` | runbook §4 参数一致 | ✓ |
| `verify --help` | 0 | `--fixture` / `--plan --fingerprint` + `--json` | runbook §5 参数一致 | ✓ |

### 2. fixture/lane 分离

- `--fixture` 与 `--plan/--fingerprint` 互斥：实测 `verify --fixture x --plan y --json` → exit 2，错误 `"--fixture 与 --plan/--fingerprint 严格互斥"`。runbook §1.1/§5 描述一致。✓
- fixture 目录 `tests/fixtures/investment_agent/aapl_acceptance/` 含 7 个文件（contract/price-snapshot/quality-review/report/run-summary/source-inventory/write-manifest），与 runbook §7 产物目录和 plan §5.4 一致。✓
- `verify --fixture` 实测返回 `verdict: PASS, total_score: 85, exit 0`。runbook §6 评分阈值 `>= 85` 一致。✓

### 3. 12 planned commands

代码 `PLANNED_PHASE_COMMAND_COUNTS = (("download", 3), ("price-snapshot-import", 1), ("process", 1), ("write-preflight", 1), ("write", 1), ("validations", 5))`，合计 3+1+1+1+1+5 = 12。runbook §4 标题"12 个 planned 命令"一致。`build_phase_specs()` 函数实际生成的 phase specs 与描述一致。✓

### 4. manual-review PENDING exit3 且无 terminal/output

代码 `utils/investment_agent_acceptance.py:1893-1901`：`run_result.pending_manual_review` 为 True 时输出 `{"status": "PENDING_MANUAL_REVIEW", "verdict": "PENDING_MANUAL_REVIEW", "completed_phases": [...], "terminal": None}` 并 `return 3`。`main()` 第1853行 docstring 记录 "3 表示等待人工复核"。runbook §4.5 描述一致：不写 `verify.json`、`source-inventory.json`、`acceptance-receipt.json`；terminal Popen=0；`succeeded` 恒 false。✓

### 5. 独立 verify

runbook §5 描述独立 verify 只运行 `verify --plan --fingerprint --json`，不创建/更新 phase receipt，只原子写 `source-inventory.json` 与 `acceptance-receipt.json`。代码 `verify_acceptance()` 函数（`utils/investment_agent_acceptance.py`）只读既有 artifacts，三态 verdict（PASS/FAIL/PENDING_MANUAL_REVIEW）与 runbook §5 一致。✓

### 6. 预算/timeout

runbook §3 `prepare` 参数 `--max-model-requests --max-total-tokens --max-estimated-cost --budget-currency --max-wall-seconds` 与 `prepare --help` 实测一致，全部 required。runbook §4.6 timeout 协议（共享 `max_wall_seconds`、`terminate → 10s grace → kill`）与代码 `SubprocessFactory` 和 `run_acceptance()` 中的 wall-clock 逻辑一致。✓

### 7. PII/secret

runbook §9 要求环境变量只记录名称与存在性、不记录值。代码 `REQUIRED_ENVIRONMENT_NAMES` 只含三个名称，`EnvironmentPresenceProvider` 只检查 `os.environ` 中 key 是否存在。runbook §9 要求 acceptance-owned outputs 无 secret shape 或绝对 home 路径时 fail closed。代码中有 `_REDACTED_SECRET` 和 `SECRET_KEY_PATTERN` sanitizer。✓

### 8. no-resume / new root

runbook §4.3 两条 write argv 都固定 `--no-resume`。代码 `build_phase_specs()` 第1391行 `--no-resume`（preflight）和第1400行 `--no-resume`（paid write）一致。runbook §8 要求失败后选择全新 run root 重新 prepare，不 resume。✓

### 9. 13 artifacts

代码 `REQUIRED_RESEARCH_ARTIFACTS` 列出 13 项，与 runbook §7 第268行清单逐项一致：`common-plus-technology.md`、`technology.research-workbook.json`、`technology.research-progress.md`、`technology.monitoring-rules.json`、`technology.source-map.json`、`research-template.manifest.json`、`technology.research-guide.md`、`technology.checklist.md`、`technology.bundle.json`、`technology.monitoring-plan.json`、`monitoring-status.json`、`research-workbook-status.json`、`research-workbook-report-status.json`。✓

### 10. score / monitoring residual

代码 `_TOTAL_POINTS=100`、`_MINIMUM_TOTAL_SCORE=85`、`_DIMENSION_MINIMUMS = (("source_traceability",20),("investment_research_completeness",24),("evidence_reasoning_quality",20),("reproducibility_recovery",0),("run_governance",0))`。runbook §6 记录"总分 100，通过阈值 >= 85；来源可追溯（25）、投资研究完整性（30）、证据与推理质量（25）各自不得低于维度的 80%（20/24/20）"一致。fixture verify residuals 输出 `monitoring_unbound_source=financial_statements/market_data/operating_metrics/product_release_notes` 等，与 runbook §7 第270行 residuals 清单一致。✓

### 11. CI 禁止 live

tests/README.md §2 第103行明确 "Live lane（`prepare`/`run`/live `verify`）涉及 SEC 下载与付费模型调用，**禁止进入 CI**"。README.md §3.8 第1742行 "live 涉及 SEC 下载与付费模型调用，**绝不进入 CI**"。runbook §1.2 "Live lane（opt-in、绝不进 CI）"。三处一致。✓

### 12. 入口与导航

README.md §3.8（第1730行）有最短入口（fixture verify 命令 + live 说明），§9（第2314行）有 runbook 导航链接。tests/README.md §1 第46行说明 fixture 非 freshness 真源，§2 第93-103行有验收命令和 CI 禁止 live 说明。符合 AGENTS.md 文档触发规则。✓

## Open Questions

- implementation artifact 的测试计数 `220 passed` 与当前实测 `229 passed` 之间的差异原因不明。可能是基线代码在 artifact 编写后有变更增加了 9 个用例，也可能是 artifact 记录有误。需要 artifact owner 核实。

## Residual Risk

- 未运行 live lane；这是明确禁止且未获授权的范围。runbook 中 live lane 的 source freshness、价格、预算与费用只在真实授权后的 download command evidence、显式 snapshot 和 plan fingerprint 中成立。
- fixture 中的 accession 与价格只用于 contract 回归，不证明今天的 freshness。
- runbook 中 download 等 Fins owner 命令的标题锚（如 `下载结果`）为当前 formatter 文案；owner 文案变更会导致验收可用性中断，属 plan §14 已记录 residual。

## Validation

| 命令 | 结果 |
|---|---|
| `python -m utils.investment_agent_acceptance`（无子命令） | exit 2；`error: 必须指定 prepare、run 或 verify` |
| `python -m utils.investment_agent_acceptance --help` | exit 2；`error: 子命令必须是 prepare、run 或 verify` |
| `prepare --help` | exit 0；完整参数面 |
| `run --help` | exit 0；`--plan --fingerprint --json` |
| `verify --help` | exit 0；`--fixture`/`--plan --fingerprint` + `--json` |
| `verify --fixture x --plan y --json` | exit 2；互斥校验 |
| `verify --fixture tests/fixtures/investment_agent/aapl_acceptance --json` | exit 0；PASS/85 |
| `prepare`（缺 --json） | exit 2 |
| `run`（缺 --json） | exit 2 |
| `python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py -q` | 229 passed |
| `python -m utils.validate_handoff_docs --json` | ok |

## Conclusion

**PASS。** Open High / Medium / Low：**0 / 1 / 1**。

- **M-001（Medium）**：implementation/fix artifact 测试计数 220 与当前实测 229 不一致，审查链不可完全复现。建议更新 artifact 或给出基线 SHA 证明 220 曾是准确值。
- **M-002（Low）**：runbook 未记录无子命令与 `--help` 的错误文案差异（fix artifact 已修复 implementation artifact，runbook 不要求此项）。

其余全部 gate 项（五条 help 命令、fixture/live lane、12 planned commands、manual-review PENDING exit3 无 terminal/output、独立 verify、预算/timeout、PII/secret、no-resume/new root、13 artifacts、score/monitoring residual、CI 禁止 live）均通过直接证据核对，文档准确、可执行、安全。未发现会诱导 live 调用、资金支出、预算默认化、价格默认化、fixture freshness 误用、PII/secret 泄漏或 resume 语义漂移的问题。完成即停止。
