# Code Review

## Scope

- Mode: current changes
- Branch: `feat/investment-agent-acceptance`
- Base: `4d91a16`
- Output file: `docs/reviews/manual-review-handoff-code-review-terra.md`
- Included scope: `utils/investment_agent_acceptance.py`、`tests/test_investment_agent_acceptance.py` 的 manual-review handoff 变更；对照根 `AGENTS.md`、accepted plan、plan-fix、plan acceptance、Terra plan review 与 implementation artifact；沿 `run_acceptance()`、`main()`、receipt loader、`_evaluate_live_plan()`、evaluator 的 quality/sanitizer 链路走读。
- Excluded scope: Slice 4 文档、Slice 5/live、未改动的 contracts/evaluator 实现本身；未执行外部调用、修复、提交、推送或 PR 操作。
- Parallel review coverage: 无。

## Findings

### MRH-001-未修复-中-quality-review 的 PII 未在 strict ingress 拒绝，非 exact run 仍会启动 terminal
- **入口/函数**: `run_acceptance()` → `_quality_review_is_exact_pending()` → `_read_quality_review_canonical()` / `_assert_quality_review_sanitized()`
- **文件(行号)**: `utils/investment_agent_acceptance.py:1709-1728, 2388-2410`
- **输入场景**: operator 在 canonical、schema 合法的 review 中将 `reviewer_id_label` 填为邮箱（例如 `alice@example.com`），或在同类字段中写入 evaluator 定义的 PII。
- **实际分支**: strict parser 接受该字符串；新 sanitizer 只匹配 secret/home-path pattern，不匹配 `@`。因载荷不再是 exact skeleton，函数返回 `False`，随后构造并执行 terminal verify。
- **预期行为**: accepted plan §4 / §Slice 4 与 plan-fix 要求 secret/PII shape 在 handoff/terminal 前 fail closed；operator 标签只允许非 PII 角色/代号。
- **实际行为**: PII 不会抛出 `ContractError`。直接复现：对现有 `quality-review-v1.json` 仅设置 `reviewer_id_label="alice@example.com"` 后，`_assert_quality_review_sanitized()` 正常返回。evaluator 的既有真源反而明确把 reviewer role/id 中的 `@` 判为 `rubric.reviewer_pii`。
- **直接证据**: CLI sanitizer pattern 列表见 2402-2408；evaluator `_evaluate_reviewer_metadata()` 在 `utils/investment_agent_acceptance_evaluator.py:2047-2059` 额外检查 `@`。计划在 `docs/plans/2026-08-09-investment-agent-aapl-acceptance.md:258,446` 以及 plan-fix:37,40 要求非 PII 与 pre-output fail-closed。新增 tests 仅覆盖 `secret`，未覆盖 reviewer email/PII（`tests/test_investment_agent_acceptance.py:6615-6674`）。
- **影响**: 含 PII 的人工 review 可以进入 terminal subprocess；在独立 verify 中还会继续到后续输出路径，违背已接受的隐私边界与 fail-closed lifecycle。
- **建议改法和验证点**: 让 CLI ingress 使用与 evaluator acceptance-owned/reviewer metadata 相同的敏感形状真源，至少在 reviewer role/id 与 evidence paths 上拒绝 evaluator 已定义的 PII 形状；新增 canonical email/PII 的 run 与 verify 测试，断言 terminal process factory、evaluator 与 acceptance-owned outputs 均为零。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。

### MRH-002-未修复-中-live verify 在 repository/artifact/evaluator 闭合前发布 source inventory
- **入口/函数**: `verify_acceptance()` → `_evaluate_live_plan()`
- **文件(行号)**: `utils/investment_agent_acceptance.py:1768-1773, 4505-4530, 4531-4575`
- **输入场景**: planned receipt prefix 与 quality JSON 均严格合法，但 price material identity、write manifest/run summary、report、research artifact 或 evaluator safety gate 发生 drift/失败。
- **实际分支**: `_evaluate_live_plan()` 先构建并 strict round-trip inventory，随即在 4527-4530 原子写 `source-inventory.json`；之后才验证 price/material identity、contract、manifest、summary、report、research artifacts、runtime 并调用 evaluator。
- **预期行为**: repository/artifact drift（以及 evaluator 安全检查）必须在任一 acceptance-owned output 发布前 fail closed。
- **实际行为**: 上述任一后续检查失败时，函数已留下本次 `source-inventory.json`。该行为也与 implementation artifact 声称“plan/receipt/repository/artifact drift 均在任何输出前拒绝”不符。
- **直接证据**: 写入调用在 4527-4530，后续 closure/evaluator 输入在 4531-4575；计划明确要求见 `docs/plans/2026-08-09-investment-agent-aapl-acceptance.md:226,446` 和 plan-fix:40,63。新增 verify 失败测试只注入 malformed/secret quality（`tests/test_investment_agent_acceptance.py:6678-6741`），没有覆盖 repository/artifact drift 后 source inventory 不存在。
- **影响**: verification 失败可产生看似已发布的 acceptance-owned inventory；重复 verify 还可能因已有 inventory 与新 inventory 不同而在更早位置失败，降低恢复和审计可信度。
- **建议改法和验证点**: 将 source inventory 的原子发布移到所有 repository/artifact/runtime/evaluator safety ingress 成功之后，并保证与 acceptance receipt 的发布语义一致；为每个关键 drift 注入 sentinel，断言 source inventory、acceptance receipt 与 phase receipts 均不新增/不变。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。

### MRH-003-未修复-低-新增测试对 evaluator 与独立 PASS/FAIL 路径的观测不真实
- **入口/函数**: `test_manual_review_verify_bad_quality_fails_closed_before_source_inventory()` 与 `test_manual_review_independent_verify_pass_and_fail_preserve_planned_receipts_without_terminal()`
- **文件(行号)**: `tests/test_investment_agent_acceptance.py:6515-6612, 6677-6741`
- **输入场景**: future change 将 `_evaluate_live_plan()` 中的实际 evaluator 调用提前，或破坏独立 verify 的真实 PASS/FAIL 计算链。
- **实际分支**: 前者 patch 的是 `acceptance_evaluator_module.evaluate_acceptance`，但 CLI 在模块导入时已绑定并调用自己的 `acceptance_cli_module.evaluate_acceptance`；因此 `evaluator.call_count == 0` 观测的是未被真实路径调用的 mock。后者直接 monkeypatch 整个 `_evaluate_live_plan()` 返回预造 `EvaluationResult`，绕过 quality ingress、repository/artifact closure 与真实 evaluator。
- **预期行为**: 测试应观测真实 consumer，并证明 evaluator=0 的 pre-output 拒绝，以及 complete PASS/FAIL review 的真实独立 verify 仍不写 terminal、不改 planned receipts。
- **实际行为**: 两项测试均可通过而真实 evaluator 调用时序或真实 PASS/FAIL 计算链已经回归。
- **直接证据**: CLI import 绑定位于 `utils/investment_agent_acceptance.py:77-89`，真实调用位于 4575；测试 patch 位于 6730-6731，整函数替换位于 6584。实现 artifact:121-123 将这些测试表述为真实 PASS/FAIL 与 evaluator-before-output 证据，超出了其实际覆盖。
- **影响**: gate 的关键安全/状态机断言没有被有效回归保护，尤其无法防止 MRH-001/MRH-002 类顺序回归。
- **建议改法和验证点**: patch `acceptance_cli_module.evaluate_acceptance` 或在其真实调用点设置 sentinel；PASS/FAIL 用最小真实 live 输入链或显式 integration seam 验证，而非替换 `_evaluate_live_plan()`。同时断言 planned receipt bytes 与所有 acceptance outputs 的精确前后状态。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

### MRH-004-未修复-低-implementation artifact 的工作树事实不准确
- **入口/函数**: implementation artifact 的变更范围与 validation 声明
- **文件(行号)**: `docs/reviews/manual-review-handoff-implementation-20260809-deepseek-flash.md:11-17,132-135`
- **输入场景**: controller 依赖 artifact 判定 allowlist 和未跟踪文件状态。
- **实际分支**: artifact 声称无未跟踪文件；当前 `git status --short` 实际为两处 `M` 加 `?? docs/reviews/manual-review-handoff-implementation-20260809-deepseek-flash.md`。
- **预期行为**: review handoff artifact 应如实记录自身为 untracked（若它尚未被纳入索引），不得将此工作区事实省略。
- **实际行为**: artifact 的 status/validation 记录与当前工作树不一致。
- **直接证据**: 当前 status 输出：`M tests/test_investment_agent_acceptance.py`、`M utils/investment_agent_acceptance.py`、`?? docs/reviews/manual-review-handoff-implementation-20260809-deepseek-flash.md`；与 artifact 第 17、135 行直接矛盾。
- **影响**: controller 无法仅凭 artifact 正确判断工作区范围，削弱 gate 审计的可追溯性；不改变生产行为。
- **建议改法和验证点**: 在 implementation artifact 中如实列出自身 untracked 状态，并在最终 handoff 前重新执行 status/path allowlist 审计。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## Open Questions

- 无。上述问题均可由当前代码、测试和工作区状态直接证实。

## Validation

- `source .venv/bin/activate && python -m pytest tests/test_investment_agent_acceptance.py -q`：207 passed。
- `source .venv/bin/activate && pyright utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py`：0 errors, 0 warnings, 0 informations。
- `git diff --check 4d91a16 -- utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py`：通过。
- 仅进行静态/本地验证；未执行 live、网络、密钥读取、修复、commit、push 或 PR 操作。

## Residual Risk

- exact canonical pending comparison、terminal argv/wall/process-factory 之前的 early return、passed-only terminal、terminal-absent loader 与 same-plan no-resume 的实现路径经走读未发现额外 material finding；但 MRH-001 和 MRH-002 未修复前，不应接受本 code correction。
- H/M/L open：**0 / 2 / 2**。

## Conclusion

**NOT PASS — FIX REQUIRED。** 存在两项中等问题，分别违反 quality PII 的 fail-closed 边界和 live verify 的 pre-output ordering；另有测试真实性与 implementation artifact 工作区事实问题。此 review worker 已停止，未进入修复或后续 gate。
