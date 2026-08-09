# Manual-review handoff code re-review（Terra）

## Scope

- Mode: current changes re-review
- Role: independent Terra code re-review worker; no controller decision and no fix
- Branch: `feat/investment-agent-acceptance`
- Base: `4d91a16`
- Output file: `docs/reviews/manual-review-handoff-code-rereview-terra.md`
- Included scope: `utils/investment_agent_acceptance.py`、`tests/test_investment_agent_acceptance.py`；完整对照根 `AGENTS.md`、accepted manual-review plan/plan-fix/plan-acceptance、source review `manual-review-handoff-code-review-terra.md`、implementation artifact 与 review-fix artifact。沿 `run_acceptance()`、`_read_quality_review_canonical()`、`_evaluate_live_plan()`、`verify_acceptance()`、真实 evaluator consumer 与新增测试走读。
- Excluded scope: 未改动 contracts/evaluator/dayu/ 文档；未执行 live、网络、密钥/付费调用、commit 或 push。
- Worktree fact at review completion before writing this artifact: 两个修改文件为 `tests/test_investment_agent_acceptance.py`、`utils/investment_agent_acceptance.py`；三个既有未跟踪 review artifacts 为 source review、implementation artifact、fix artifact。该 artifact 是本次唯一新增文件。
- MRH closure matrix:

| 项目 | 结论 | 直接证据 |
|---|---|---|
| MRH-001 | **未闭合** | reviewer role/id 的 email 已在 CLI ingress 拒绝，但 evidence paths 的 email 仍可进入 terminal/evaluator/output。 |
| MRH-002 | **闭合** | inventory 仅在 repository/artifact/runtime closure 与 `evaluate_acceptance()` 成功后写入；drift/evaluator sentinel 测试覆盖真实路径。 |
| MRH-003 | **闭合** | pre-output 测试 patch 真实的 `acceptance_cli_module.evaluate_acceptance`；PASS/FAIL 测试不再整体替换 `_evaluate_live_plan()`，而是走真实仓储与 evaluator 链。 |
| MRH-004 | **闭合** | implementation artifact 如实列出当时两个 `M` 与三个 `??`，且状态为 awaiting re-review；未把自身或已有 artifact 隐去。 |

## Findings

### MRH-001-仍未修复-中-evidence path 的 email/PII 未在 run 与独立 verify 的 ingress fail closed
- **入口/函数**: `run_acceptance()` → `_quality_review_is_exact_pending()` → `_read_quality_review_canonical()`；以及 `verify_acceptance()` → `_evaluate_live_plan()`。
- **文件(行号)**: `utils/investment_agent_acceptance.py:2381-2433, 2451-2453, 4526-4528, 4593-4600`；`utils/investment_agent_acceptance_evaluator.py:2047-2059, 2371-2384`。
- **输入场景**: 在 canonical、schema 合法的 `quality-review.json` 的 rubric item 或 manual finding `evidence_paths` 写入 `alice@example.com`；该字段是完整 review 的必填非 PII evidence locator。
- **实际分支**: strict parser 只把 evidence path 收窄为 string tuple，不限制 email（contracts:3202-3207、3242-3247）。CLI 全载荷扫描仅检查 secret/home-path；附加 `@` 检查只覆盖 `reviewer_role` 与 `reviewer_id_label`。因此该 review 通过 ingress、非 exact 后 `run` 派生 terminal；独立 verify 也继续构建 inventory 并调用 evaluator。evaluator 的 `_sensitive_strings()` 同样只匹配 secret/home-path，`@` 判断仍只检查 role/id，故不会阻断这条 evidence-path email。
- **预期行为**: accepted plan 要求 evidence path 为非 PII（`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md:257`），并要求 secret/PII shape 在 terminal/evaluator/acceptance outputs 之前 fail closed（226、446）。修复 artifact 所称的 reviewer metadata/evidence paths PII fail-close 必须覆盖该合法可写的 evidence 字段。
- **实际行为**: 该邮箱既不触发 `ContractError`，也不命中新增测试：`tests/test_investment_agent_acceptance.py:6973-6979` 只测 role/id email 与 evidence path home path。于是 email 可使 run 启动 terminal，或使独立 verify 到达 evaluator 与 source-inventory/acceptance receipt 发布路径，违反 MRH-001 的安全时序。
- **直接证据**: CLI 的 `@` 分支是 `reviewer_role/reviewer_id_label` 的穷尽元组（2432）；evaluator 的 email 分支同样是该元组（2054-2056），而 `evidence_paths` 仅由 `_sensitive_strings()` 处理（2047-2054），其 pattern 集不含 email（2371-2374）。
- **影响**: 人工 review 中的个人邮箱可跨越明确的 fail-closed 边界，并可能触发 terminal 或在验收输出前被处理；operator 不能依赖该 gate 避免 PII 进入后续 lifecycle。
- **建议改法和验证点**: 将 reviewer/evidence 元数据的 email 检查覆盖所有 `RubricItem.evidence_paths` 与 `ManualFinding.evidence_paths`（若 notes/summary 也属于允许的人填字段，应按同一 PII policy 明确覆盖范围），并让 CLI ingress 与 evaluator 共享同一个可测试的敏感形状契约。新增 run 与 independent verify 的 canonical evidence-path email 反例，分别断言 terminal process factory、真实 evaluator、source inventory、acceptance receipt 均保持零调用/缺席或 sentinel byte-identical。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。

### RER-001-未修复-低-新增真实链测试引入项目明令禁止的 `object` 宽类型
- **入口/函数**: `_seed_real_live_chain()` 测试 helper。
- **文件(行号)**: `tests/test_investment_agent_acceptance.py:1166,1197`。
- **输入场景**: 类型检查或后续修改该 test fixture 的 metadata payload。
- **实际分支**: 新 helper 将可变 JSON payload 标为 `dict[str, object]`，把字典内元素的严格类型边界抹平。
- **预期行为**: 根 `AGENTS.md` 明确禁止 `object` 与无法严格类型检查的签名设计；accepted plan 4.2 也将 `object` 列为 acceptance 模块禁止项。测试本身是本 correction 的新增变更，不能用既有 owner 宽类型作例外。
- **实际行为**: 两处新增 `dict[str, object]` 已进入本次变更；pyright 可通过但不改变该项目级约束已被违反的事实。
- **直接证据**: 新增 helper 的声明见上述行号；`rg` 在本次修改范围仅命中这两处。
- **影响**: 低；当前 fixture 行为正确，但 metadata 结构漂移会失去静态约束，且违反本仓库的明确实现约束。
- **建议改法和验证点**: 采用现有严格 `JsonObject`/`JsonValue` 类型或拆分为精确 TypedDict，随后重跑本文件 pytest、pyright 与 Ruff。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## Open Questions

- 无。MRH-001 的触发输入、实际分支与缺失检查均由同一条 quality-review 数据路径直接证明。

## Validation

- `source .venv/bin/activate && python -m pytest tests/test_investment_agent_acceptance.py -q`：**216 passed**。
- `source .venv/bin/activate && pyright utils/investment_agent_acceptance.py utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py tests/test_investment_agent_acceptance.py`：**0 errors, 0 warnings, 0 informations**。
- `source .venv/bin/activate && ruff check --select F,I utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py`：**All checks passed**。
- `git diff --check 4d91a16 -- utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py`：通过。
- `git diff --name-only 4d91a16` 与 unstaged diff：仅两个 allowlisted production/test 文件；仅本 artifact 被新增。未执行 live/network/paid 操作。

## Residual Risk

- MRH-002 的 source-inventory 发布移至 strict inventory、price material、manifest/summary/report/research artifact/runtime closure和真实 evaluator 成功之后，且 drift/evaluator sentinel 与 planned receipt bytes 的测试可证，未发现该项残留缺口。
- MRH-003 的真实 consumer patch 与真实 PASS/FAIL live-chain 测试已可证；MRH-004 的 artifact status 记录在其声明的复核时点与工作树一致。
- focused 测试全绿不能覆盖未参数化的 evidence-path email 反例，正是本次中等 finding 的回归缺口。
- Open H/M/L：**0 / 1 / 1**。

## Conclusion

**FAIL。** MRH-002、MRH-003、MRH-004 已闭合；MRH-001 仍因 evidence-path email/PII 可跨过 run/verify 的 fail-closed ingress 而未闭合。除该中等安全边界问题外，还有一项新增 `object` 宽类型的低优先级项目约束违反。未实施修复，完成即停止。
