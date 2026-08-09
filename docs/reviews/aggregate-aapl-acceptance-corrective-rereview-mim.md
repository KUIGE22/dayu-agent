# Code Review — AGG-AAPL-001 Corrective Re-Review (MiM)

## Scope

- Mode: current changes（corrective re-review of AGG-AAPL-001 fix）
- Gate: AGG-AAPL-001（Terra High）— ACCEPTED / FIX REQUIRED → FIX APPLIED → CORRECTIVE DUAL RE-REVIEW
- Branch: `feat/investment-agent-acceptance`
- Base: `7c97c1f4e28af17d1a6d5c1b92706d793d9c7180`
- HEAD: `c6e682fe` + 2 unstaged file modifications (fix from DeepSeek V4 Flash)
- Output file: `docs/reviews/aggregate-aapl-acceptance-corrective-rereview-mim.md`
- Included scope: AGG-AAPL-001 fix — `utils/investment_agent_acceptance.py` (production), `tests/test_investment_agent_acceptance.py` (regression), 本 artifact；Controller adjudication 与 DeepSeek fix artifact 为已读取上下文
- Excluded scope: plan, contracts, evaluator, Fins formatter, fixtures, README/runbook、其它 production 模块；Slice 5 / live lane 未授权
- Review time: 2026-08-09 20:29 CST（本机系统时钟）

## Findings

未发现实质性问题。

### 修复结构验证

**AGG-AAPL-001 根因确认与修复对齐：**

1. **原始缺陷**：`verify_acceptance()` 在 `_load_and_validate_receipt_prefix()` 后直接调用 `_evaluate_live_plan()`，后者内部虽 strict 读取 quality review 但仅做 malformed/secret/PII 检查，不要求 `is_complete`。随后无条件写 `acceptance-receipt.json`，`_evaluate_live_plan()` 还会发布 `source-inventory.json`。exact pending skeleton 与任何 `is_complete == False` 状态都可通过此路径发布 acceptance outputs。

2. **修复方案**：新增 `_load_completed_quality_review(plan)` 函数（L2470-2492），在 `verify_acceptance()` 的 receipt prefix 加载后、evaluator 调用前调用（L1774）。该函数 strict 读取 quality review 并检查 `is_complete`，未完成时抛 `ContractError`。`_evaluate_live_plan()` 签名增加 `quality: QualityReview` 参数，删除内部 `_read_quality_review_canonical` 重复读取，保持单一 quality ingress。

3. **与 Controller 修复契约对齐**：

| 契约项 | 实现 | 证据 |
|---|---|---|
| verify 前 strict 读取 quality review | `_load_completed_quality_review(plan)` 在 L1774 调用，使用 `_read_quality_review_canonical` strict parse | L2470-2492 |
| is_complete == False → ContractError/exit 2 | L2490-2491: `if not quality.is_complete: raise ContractError` | L1774→L2490 |
| 拒绝路径不调用 evaluator | `_load_completed_quality_review` 在 `_evaluate_live_plan` 之前，异常短路 | L1774 vs L1775 |
| source-inventory/acceptance-receipt 不创建不改写 | 异常在任何写入前抛出，`_atomic_replace_bytes` 未执行 | L1776-1777 被短路 |
| planned receipts 逐字节不变 | receipt prefix loader 在 quality check 之前完成，拒绝路径无副作用 | L1770 vs L1774 |
| 单次 quality ingress | 已解析 `QualityReview` 传入 `_evaluate_live_plan(plan, receipts, quality=quality, clock=clock)` | L1775, L4541 |
| 完整人工 review 允许 verify | complete_pass/complete_fail 四态测试断言 evaluator 调用 1 次、receipt 写入 | test_agg_aapl_001_live_verify_four_quality_states_public_boundary |
| fixture verify 不变 | `_verify_fixture()` 不读取 quality review，fixture 模式走独立路径 | L1761-1764 |

### 独立验证证据

**exact pending / partial incomplete fail-closed 验证：**
- 测试 `test_agg_aapl_001_live_verify_four_quality_states_public_boundary[exact_pending]`：ContractError("人工质量复核")，evaluator spy `call_count == 0`，`source-inventory.json` 不存在，`acceptance-receipt.json` 不存在，`verify.json` 不存在
- 测试 `test_agg_aapl_001_live_verify_four_quality_states_public_boundary[partial_incomplete]`：同上全部断言
- 5 个指定测试全部通过（220 deselected / 5 selected / 5 passed）

**CLI exit 2 验证：**
- 测试 `test_agg_aapl_001_main_live_verify_pending_skeleton_exits_2`：exit_code == 2，stdout 为空，stderr 含 "人工质量复核"，无 acceptance outputs

**evaluator 0 调用验证：**
- exact_pending / partial_incomplete 状态下 evaluator spy `call_count == 0`
- `_evaluate_live_plan` 函数体内无 `_read_quality_review_canonical` 或 `parse_quality_review` 调用（grep 验证 0 matches）

**source-inventory / acceptance-receipt 不创建不改写验证：**
- 四态测试断言 `not (run_root / "source-inventory.json").exists()` 和 `not (run_root / "acceptance-receipt.json").exists()`（incomplete states）

**planned receipts 字节不变验证：**
- `receipt_snapshot` 在 verify 前捕获所有 `phase-receipts/*.json` 的 `(name, bytes)` 元组
- verify 后断言 `tuple(...) == receipt_snapshot`（四态 + 重复 verify 测试）

**单次 quality ingress 验证：**
- `_load_completed_quality_review` 调用 `_read_quality_review_canonical` → `parse_quality_review`，结果传入 `_evaluate_live_plan(plan, receipts, quality=quality, clock=clock)`
- `_evaluate_live_plan` 内部不再重复读取（L4567 无 quality disk read）

**完整 PASS/FAIL 与 fixture 不回归验证：**
- `test_agg_aapl_001_live_verify_four_quality_states_public_boundary[complete_pass]`：evaluator 1 call，verdict PASS，acceptance-receipt 等于 `canonical_bytes()`
- `test_agg_aapl_001_live_verify_four_quality_states_public_boundary[complete_fail]`：evaluator 1 call，verdict FAIL，acceptance-receipt 等于 `canonical_bytes()`
- fixture verify：PASS（total_score 85，verdict PASS，13 research artifacts）

### Gate 验证矩阵

| Gate | Command | Result |
|---|---|---|
| Focused 225 | `pytest tests/test_investment_agent_acceptance.py -q` | **225 passed** in 4.69s |
| Coverage | `pytest ... --cov=utils.investment_agent_acceptance --cov-report=term-missing` | **88%** ≥ 80% |
| Pyright | `pyright utils/investment_agent_acceptance*.py dayu/fins/cli_formatters.py tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py` | **0 errors, 0 warnings** |
| Ruff F,I | `ruff check --select F,I utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | **All checks passed** |
| Ruff default | `ruff check utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | **All checks passed** |
| Owner tests | `pytest tests/fins/test_cli_formatters_coverage.py tests/cli/test_research_template_command.py -q` | **225 passed** |
| Fixture verify | `python -m utils.investment_agent_acceptance verify --fixture tests/fixtures/investment_agent/aapl_acceptance --json` | **PASS**（total_score 85，13 research artifacts（7 fixture input files）不变） |
| Diff check | `git diff --check -- utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | **clean** |

## Open Questions

无。

## Residual Risk

- Slice 5 / live lane 未授权；本次 review 不覆盖真实 SEC 网络、外部模型或当天价格 freshness。
- `_load_completed_quality_review` 拒绝消息 "live verify 要求人工质量复核已完成" 为新稳定 contract 文本，被四态测试与 CLI exit-2 测试锁定。
- evaluator 不承载 quality completion gate，拒绝完全位于 public live verify 的发布权限边界——架构正确。

## Conclusion

**PASS。AGG-AAPL-001 CLOSED。** Open H/M/L: **0 / 0 / 0**。Fix 修复了 public live `verify_acceptance()` 在 incomplete quality review 下发布 acceptance outputs 的缺陷；`_load_completed_quality_review` 在 evaluator 调用前 strict 读取并验证完成状态，未完成时 `ContractError`/exit 2，evaluator 0 调用，source-inventory/acceptance-receipt 不创建不改写，planned receipts 字节不变，单次 quality ingress；完整 PASS/FAIL 继续正式 verify，fixture verify 不变（13 research artifacts）。225 focused passed、coverage 88%、pyright 0 errors、Ruff 全通过、owner 测试无回归。
