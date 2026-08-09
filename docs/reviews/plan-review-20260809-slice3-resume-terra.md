# Slice 3 resume-marker erratum 独立 Plan Review（Terra）

## Reviewed target and scope

- Target: `docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- Erratum: `docs/reviews/plan-fix-20260809-slice3-resume-marker-codex.md`
- Review time: 2026-08-09 15:55:29 CST（本机时钟）
- Mode: adversarial plan review；只读对照当前 acceptance CLI、contracts、evaluator 与 phase specs。
- Focus: no-resume/fail-closed、partial/non-passed receipt 不可 PASS、future resume 独立 work unit/原 fingerprint 绑定/新 operator authorization、test-local marker 禁令、Slice 3 allowlist，以及 Slice 2/Slice 5 gates。
- Excluded: implementation、live/SEC/Web/provider/model/付费调用、commit/push。
- Conclusion: **FAIL**
- Open findings: **High 0 / Medium 1 / Low 0**

## Goal、boundary 与 assumptions tested

本 erratum 的目标是删除 Slice 3 “用测试伪造 resume marker”的歧义，同时保持当前 runner 的 fresh-run/no-resume 事实。评审核验了以下 assumptions：

1. 两条 write argv 都固定且仅使用 `--no-resume`；成立，见 runner `build_phase_specs()`。
2. 同一 run root 存在任一 planned/terminal receipt 时，重复 `run` 在首次 `Popen` 前拒绝；成立，`run_acceptance()` 在 phase loop 前调用 `_assert_no_existing_run_receipts()`。
3. live receipt loader 对 incomplete、failed、signal、timeout planned prefix fail closed；成立，`_validate_terminal_receipt()` 要求所有 planned receipts 完整 passed。
4. shared v3 contract 不允许 partial/non-passed phase 自称 passed；成立，`_validate_phase_record_prefix()` 将 passed 绑定到完整 passed records，并将非 passed 聚合绑定到末条停止 record。
5. raw evaluator 自身也会拒绝 failed/signal/incomplete receipt；**不成立**，见 M-001。
6. Future resume 只作为独立 work unit，引用原 plan fingerprint并取得新的 operator authorization；plan 已明确，未把未来 marker/action 提前放入 Slice 3。
7. Slice 3 只改两份 tests，禁止 test-local marker/consumer/command；plan 已明确。Slice 5 live gate仍独立 blocked。

## Findings

### M-001-未修复-中-Slice 3 要求 evaluator 拒绝 non-passed receipt，但当前 evaluator 会对 failed/signal/空前缀返回 PASS，且 allowlist 不允许修复

- **位置**: Target plan Slice 3 “变更内容”第 403 行、“预期断言”第 410 行，以及 Slice 3 精确允许文件第 394–397 行。
- **问题类型**: 契约缺失 / 不可直接实施 / 测试缺口 / 架构边界。
- **当前写法**: 计划要求“write partial/non-passed receipt 不会被 evaluator 或 live verify 当 PASS”，并要求对 v3 failed/signal/timeout/不完整前缀“断言 evaluator/live verify 拒绝”；但 Slice 3 只允许修改两份测试文件。
- **反例/失败场景**: 用完整合法 happy fixture 构造 `AcceptanceInputs`，只把 `runtime.phase_receipts` 替换为一个 schema/lifecycle 合法的 `write` failed receipt、signal receipt，或空的不完整 prefix，然后直接调用 `evaluate_acceptance()`。三种输入均得到 `PASS` 且 findings 为空。
- **为什么有问题**: 当前 live 安全边界实际在 CLI loader：`_load_and_validate_receipt_prefix()` / `_validate_terminal_receipt()` 先拒绝不完整或 non-passed prefix，之后才构造 evaluator inputs。evaluator 的 `_evaluate_wall_clock()` 仅对 timeout/`partial_by_timeout` 产生 finding，不检查 failed/signal，也不要求 phase prefix 完整。因而计划把 loader responsibility 错写成 evaluator contract。implementation agent 无法在两份 test-only allowlist 内同时满足该断言；它只能写一个必失败测试、削弱断言，或越权修改 evaluator。
- **直接证据**:
  - Plan `403/410` 明确写 evaluator 与 live verify 都拒绝；allowlist `394–397` 仅两份 tests。
  - `utils/investment_agent_acceptance.py:3859–3862` 要求 live verify 收到全部 planned phases 且均 passed，否则抛 `ContractError`；这是当前真实 fail-closed owner。
  - `utils/investment_agent_acceptance_evaluator.py:1406–1427` 只检查 wall 超限、remaining 非法与 timeout/partial，不检查 failed/signal/incomplete。
  - 本轮纯本地可执行复现：`incomplete-empty-prefix PASS []`、`failed PASS []`、`signal PASS []`。
- **影响**: Slice 3 不是 code-generation-ready；测试职责与生产 trust boundary 冲突，容易导致越过 allowlist、为了过 gate 写假测试，或把“public live verify 安全”误表述为“raw evaluator 自证安全”。
- **建议改法和验证点**:
  1. 最小且架构一致的修订：把 Slice 3 两处 “evaluator/live verify” 改为 public live `verify_acceptance()`/receipt loader 边界，明确 **untrusted phase receipt 必须先经 live loader，raw evaluator 不是 receipt ingress**；Slice 3 不直接向 evaluator 注入 partial receipts。
  2. tests 对 failed/signal/timeout 与不完整 prefix 调用 live verify，断言 `ContractError`、既有 `acceptance-receipt.json` byte-identical、phase receipts 不变；再调用同一 plan/fingerprint 的 `run`，断言 process factory/Popen 调用数仍为 0。
  3. 分别锁定 preflight/paid write argv 中 `--no-resume` 精确一次且无 `--resume`/marker/token。
  4. 如果 Controller 确实要求 raw evaluator 成为独立防御边界，则必须另行扩大 production allowlist并定义 fixture lane 与 live lane 的完整-prefix差异；这比当前 tests-only erratum更宽，不应由 implementation agent自行推导。
- **修复风险（低/中/高）**: 低；推荐方案只澄清已有 loader ownership并收窄测试入口，不改 production。
- **严重程度（低/中/高/严重）**: 中。

## Architecture / best-practice / optimality / coupling review

- **Architecture boundary**: fresh-run gate、receipt loading与evaluator职责本应单向为 `untrusted persisted receipts → strict live loader → frozen evaluator inputs`。除 M-001 外，erratum 对此边界是清晰的；future resume没有泄漏进当前 schema。
- **Best practice**: no-resume runner拒绝隐式 retry，保留失败现场与 receipt，未来恢复要求新授权/新 review，符合审计与费用治理。测试应贴 public trust boundary，而不是绕过 loader直接构造不受其约束的 evaluator inputs。
- **Optimal solution**: 继续使用现有 `_assert_no_existing_run_receipts()` 和 live loader 是最小安全路径；为 Slice 3 发明 marker、resume action或兼容 wrapper都更差，plan已正确禁止。
- **Overengineering**: 未发现为 future resume 提前引入抽象。未来 schema/action/budget/replay policy保持独立 work unit是合理 deferred boundary。
- **Overcoupling**: Slice 3 两份 tests allowlist本身足够窄；M-001 的错误 evaluator断言会迫使 tests耦合到错误层，修订为 public live verify 后可消除此风险。

## Confirmed closures

- write preflight 与 paid write 当前各含一次 `--no-resume`，没有 resume分支。
- `run_acceptance()` 在任何 process creation 前检查 existing planned/terminal receipts。
- v3 phase contract保证 non-passed prefix不能机械变成 passed phase；live verify要求完整 passed planned prefix。
- Slice 3明确禁止 authorization-marker fixture、marker consumer、resume command、production flag/action/schema与 owner wrapper。
- Future resume必须独立 work unit，引用原 acceptance plan fingerprint并取得新 operator authorization，再单独 plan/code review；当前 plan没有把新授权暗示为已有授权。
- Slice 0–2 accepted history保持不变；当前 candidate状态不授权 Slice 3 implementation。
- Slice 5仍为 `LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN`，本 erratum不授权任何外部调用。

## Open questions

- 无需 implementation agent回答。M-001 需要 Controller 在 plan 层选择“澄清 loader trust boundary”（推荐）或显式扩大 future production scope。

## Residual risks and tracking

- Future resume 的 schema、budget accounting、receipt ownership、authorization durability、replay/idempotency仍属于未来独立 Gateflow work unit；本次不设计是正确的，继续留在该 future work unit 跟踪。
- 当前 no-resume失败现场可能含 partial output/journal；Slice 3只验证保留与不可提升，operator恢复/cleanup仍按 Slice 4 runbook与未来授权流程跟踪。
- 未运行 live、SEC、Web、provider/model或付费调用；不影响本次确定性 plan矛盾与代码事实。

## Final plan review conclusion

**FAIL — open High/Medium/Low = 0 / 1 / 0.** Erratum 已正确关闭 test-local marker 与隐式 resume，但 Slice 3 对 raw evaluator 的拒绝断言与当前代码及 tests-only allowlist直接矛盾。修订 M-001 后可重新 plan review；修订前不应授权 Slice 3 implementation。
