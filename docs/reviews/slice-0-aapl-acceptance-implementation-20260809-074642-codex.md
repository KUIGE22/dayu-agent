# Slice 0 AAPL Acceptance Implementation

- Work unit：`investment-agent-aapl-acceptance`
- Slice：`0 — Characterization 与固定 contract`
- Baseline accepted plan commit：`5b5494e`
- Branch：`feat/investment-agent-acceptance`
- Implementer：Codex implementation worker
- Status：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**

## Scope

本 slice 只新增固定 AAPL deterministic fixture 与 production owner characterization tests。没有实现 Slice 1 contracts/evaluator，没有进入 Slice 1+，没有修改 `dayu/`、`utils/` 或 README，也没有运行 SEC、Web、DeepSeek、MiMo 或其它外部调用。

固定语料明确为脱敏回归 fixture，不声明 live freshness，不构成投资建议。contract 固定：

- `AAPL` / `Apple Inc.`；
- research template 为 `technology`；
- 双模型角色为 DeepSeek 主写、MiMo 审计；
- 总分 `85/100` 且前三个质量维度满足各自 80% 下限；
- 10 个 hard gates；
- 五类报告内容、四段式引用、唯一且精确的 `valuation_reference_price`；
- 稳定示例 filing/material ID、primary SHA-256、processed source/state fingerprint；
- 明确 `external_calls_allowed=false`、`live_freshness_claimed=false`。

## Changed Files

1. `tests/fixtures/investment_agent/aapl_acceptance/contract-v1.json`
2. `tests/fixtures/investment_agent/aapl_acceptance/source-inventory-v1.json`
3. `tests/fixtures/investment_agent/aapl_acceptance/report-v1.md`
4. `tests/fixtures/investment_agent/aapl_acceptance/price-snapshot-v1.json`
5. `tests/fixtures/investment_agent/aapl_acceptance/quality-review-v1.json`
6. `tests/fixtures/investment_agent/aapl_acceptance/write-manifest-v1.json`
7. `tests/fixtures/investment_agent/aapl_acceptance/run-summary-v1.json`
8. `tests/test_investment_agent_acceptance.py`
9. `docs/reviews/slice-0-aapl-acceptance-implementation-20260809-074642-codex.md`

## Production Owner Characterization

测试直接调用当前 owner，而不是复制未来验收实现：

- `build_research_workbook_payload("technology")`：证明 10 个 category、37 个 item；
- `_materialization_artifact_paths(..., "technology")`：证明 byte-exact rollback 边界包含且只包含计划列出的 13 个产物；
- `materialize_research_template_bundle` + `build_monitoring_execution_plan` + `validate_monitoring_execution_plan`：证明生成计划恒为 `dry_run`、`automated_execution_allowed=false`，并证明 validator 拒绝修改为 live/automation true；
- `ExecutionSummaryBuilder.build_summary`：证明 `write_run_summary_v3` 直接包含 `model_usage`、`budget` 与 `audit` receipt；
- `RunManifest.from_dict`：证明固定 write manifest 可由当前 production owner 直接恢复，并闭合 AAPL/technology/双模型职责。

## Validation

所有命令均在 `/Users/wsk/workspace/dayu-agent` 且激活 `.venv` 后执行：

1. `python -m pytest tests/test_investment_agent_acceptance.py -q`
   - Exit：`0`
   - Result：`7 passed`
2. `pyright tests/test_investment_agent_acceptance.py`
   - Exit：`0`
   - Result：`0 errors, 0 warnings, 0 informations`
3. `ruff check --select F,I tests/test_investment_agent_acceptance.py`
   - Exit：`0`
   - Result：`All checks passed!`
4. `ruff check tests/test_investment_agent_acceptance.py`
   - Exit：`0`
   - Result：`All checks passed!`；相对 HEAD 的新增 Python 文件没有 full-rule delta。
5. `python -m pytest tests/test_investment_agent_acceptance.py -q --cov=tests.test_investment_agent_acceptance --cov-report=term-missing --cov-fail-under=80`
   - Exit：`0`
   - Result：`7 passed`；`tests/test_investment_agent_acceptance.py` 为 `226 statements / 0 missed / 100%`。该数字只表示测试模块自身的执行路径证据，不是生产代码覆盖率证据；本 slice 没有新增或修改生产 Python 文件。
6. `git diff --check`，并对 9 个未跟踪白名单文件逐个执行等价的 `git diff --no-index --check /dev/null <exact-file>`
   - Exit：`0`
   - Result：无 whitespace error。
7. exact allowed-path audit：合并 `git diff --name-only HEAD` 与 `git ls-files --others --exclude-standard`，排序去重后逐项匹配 Slice 0 精确白名单
   - Exit：`0`
   - Result：`ALLOWED_PATH_AUDIT PASS (9 paths)`；仅包含 7 个 fixture、1 个测试文件和本实施 artifact。

### Review-fix validation

源审查 `code-review-20260809-075007.md` 与 `code-review-20260809-075509.md` 经 Controller 裁决后的定向修复，验证结果如下：

1. `python -m pytest tests/test_investment_agent_acceptance.py -q`
   - Exit：`0`
   - Result：`7 passed`
2. `pyright tests/test_investment_agent_acceptance.py`
   - Exit：`0`
   - Result：`0 errors, 0 warnings, 0 informations`
3. `ruff check --select F,I tests/test_investment_agent_acceptance.py` 与 `ruff check tests/test_investment_agent_acceptance.py`
   - Exit：`0`
   - Result：两条命令均为 `All checks passed!`
4. `python -m pytest tests/test_investment_agent_acceptance.py -q --cov=tests.test_investment_agent_acceptance --cov-report=term-missing --cov-fail-under=100`
   - Exit：`0`
   - Result：`7 passed`；测试模块自身 `327 statements / 0 missed / 100%`。该值仍只作为测试执行路径证据，不代表生产覆盖率。

## Code Review Adjudication

- 接受并修复：DS-001、DS-002、DS-003 的 assertion-specificity 部分、DS-004，以及 MiMo-1（DS-002 duplicate）。
- 拒绝为非缺陷：DS-005、DS-006 的“覆盖率代表生产覆盖”解读、MiMo-2。
- MiMo-3 的 monitoring 指纹/bound-source tamper 行为测试按 Controller 裁决留在 Slice 1 strict evaluator 范围；Slice 0 仅刻画 `dry_run`/automation false 及其精确拒绝原因。
- `tests/README.md` 明确延期至 Slice 4；`PENDING_MANUAL_REVIEW`/`FAIL` 质量状态与 price max-age evaluator 明确属于 Slice 1。
- 逐项证据与修复映射见 `docs/reviews/slice-0-aapl-acceptance-fix-20260809-080022-codex.md`。

### Dual re-review closure

- DeepSeek re-review：`docs/reviews/code-review-20260809-080255.md`，verdict **PASS**；accepted DS-001..004 全部经 mutation probe 复核关闭。新 Low 001 按 Controller 裁决为 `DEFERRED-WITH-OWNER = Slice 1`，不阻断 Slice 0。
- MiMo re-review：`docs/reviews/code-review-20260809-080616.md`，verdict **PASS**；Open High/Medium/Low = `0/0/0`。
- Slice 0 最终 closure：双路 re-review 通过；已接受 findings 全部关闭；新 Low 001 有明确后续 owner、目标文件和验证入口；当前状态为 **READY FOR ACCEPTED COMMIT**。

## Docs Decision

不修改 README。虽然新增 tests 通常触发 `tests/README.md` 检查，但 accepted plan 对 Slice 0 的精确白名单不包含 README；项目级验收 runbook、根 README 与 `tests/README.md` 明确属于后续 Slice 4。本 slice 不能越权提前修改。

## Residual Risks

- `run_summary.budget` / `model_usage` 内部 shape 与真实 `WriteModelUsageLedger.build_budget_summary()` / `build_summary()` 的 owner-binding：`DEFERRED-WITH-OWNER = Slice 1`。目标为 `utils/investment_agent_acceptance_contracts.py` 的严格解析与 `utils/investment_agent_acceptance_evaluator.py` 的 budget/usage hard-gate 语义；Slice 1 必须在 `tests/test_investment_agent_acceptance.py` 构造真实 ledger receipt，与 fixture 的 nested shape/字段语义闭合，并通过入口 `python -m pytest tests/test_investment_agent_acceptance.py -q` 验证 owner 漂移可被捕获。
- fixture 只证明 deterministic contract 与当前 owner 事实，不证明 AAPL live freshness、真实模型质量或外部服务可用性。
- 本 slice 不提供 strict parser/evaluator；未知字段拒绝、评分聚合、monitoring 指纹/bound-source tamper、`PENDING_MANUAL_REVIEW`/`FAIL` 与 price max-age 判定属于 Slice 1。
- characterization 会在 packaged technology 模板、13 产物边界、monitoring 安全开关或 summary v3 contract 有意变化时失败；届时必须重新审查计划与 fixture，不能静默放宽。
- `tests/README.md` 同步仍为 `DEFERRED-WITH-OWNER = Slice 4`，必须在 Slice 4 docs gate 验收。
- pytest 输出包含既有 `RequestsDependencyWarning`（urllib3/chardet/charset_normalizer 版本提示）；不影响本 slice 7 个测试通过，且依赖修整不在本 slice 白名单。

## Stop Status

- Plan gap：无。
- Live authorization：未请求、未使用。
- Worktree scope：初始实现 `ALLOWED_PATH_AUDIT PASS (9 paths)`；review-fix delta 只允许测试文件、本实施 artifact 与新 fix artifact，最终复核记录见 fix artifact。
- Final implementation status：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**。
