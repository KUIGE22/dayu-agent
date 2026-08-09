# AAPL acceptance manual-review handoff plan-fix

- 日期：2026-08-09
- Gate：Gateflow plan-only fix / Slice 4 pre-doc blocker
- 分支：`feat/investment-agent-acceptance`
- 基线：`504d74730d9ffc099c07d7732804d51152972875`
- Target：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- 状态：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- Code correction：**PLAN HANDOFF-READY**
- Slice 4：**WAITING FOR CODE CORRECTION ACCEPTANCE**
- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**

## Gap and direct evidence

当前 `run_acceptance()` 在六个 planned phases 全部 passed 后无条件构建并启动 terminal `verify` subprocess。`verify_acceptance()` 正确把 evaluator 的 `PENDING_MANUAL_REVIEW` 映射为 exit 3，但 outer runner 将该非零结果写成 non-passed terminal receipt；strict receipt loader 又只接受 persisted terminal `status=passed`、精确一个 passed record、exit 0。因此 prepare 生成的正常 pending skeleton 会形成不可由 operator 填写后独立 verify 的 terminal stop state。

仓库已有足够 owner contract 支持最小修正：

- evaluator `build_pending_quality_review(fixture_id)` 生成唯一 null rubric skeleton，并由 `parse_quality_review()` strict round-trip；`prepare` 已使用 `live-{fingerprint[:16]}` 调用该 builder并写 canonical JSON。
- `Verdict` 已含 `PENDING_MANUAL_REVIEW`，顶层 verify CLI 已将该 verdict映射为 exit 3；无需改 contracts/evaluator schema。
- `_load_and_validate_receipt_prefix()` 已允许完整 passed planned prefix 后 terminal receipt 缺席；`_validate_terminal_receipt()` 对已存在 terminal 继续要求 passed-only。
- `RunResult`、run dispatch JSON与 exit-code mapping均由 `utils/investment_agent_acceptance.py` owner；最小 correction不需要进入 contracts/evaluator。

结论：无新 plan gap。修正可严格限于 acceptance CLI 与其现有测试 owner。

## Controller contract

### Exact pending handoff

1. `prepare` 行为不变：写 evaluator builder 生成并 strict round-trip 的 exact pending quality skeleton。
2. `run` 完成全部 planned phases后，在派生 terminal argv、terminal wall check或调用 process factory/Popen前，strict读取 `quality-review.json`；只在其 canonical bytes精确等于同一 `build_pending_quality_review(f"live-{plan.fingerprint[:16]}")` 结果时进入 handoff。
3. handoff输出 canonical JSON，`status`/`verdict` 均表达 `PENDING_MANUAL_REVIEW`，退出码3；planned receipts保持 passed和字节稳定。
4. handoff不得派生或启动 terminal verify，不创建 `phase-receipts/verify.json`，不写 `source-inventory.json`/`acceptance-receipt.json`，也不得把 pending编码成 failed/signal/timeout receipt。

### Independent verify after operator review

1. operator只修改既有 `quality-review.json`，完整填入非PII reviewer role/id label、所有维度项与finding状态；不得再次运行同一plan的 `run`，不得创建、删除或覆盖任何 phase receipt。
2. operator只运行独立 `verify --plan --fingerprint --json`。完整 passed planned prefix + terminal absent是合法输入；独立 verify不创建terminal receipt、不修改planned receipts。
3. 完整达标 review生成canonical PASS inventory/receipt；完整但未达标的strict-valid review生成canonical FAIL inventory/receipt。
4. malformed/unknown/missing/type/schema/non-canonical quality、secret/PII shape、plan/receipt/repository/artifact drift均在发布 acceptance-owned outputs前fail closed。
5. 若quality在 `run` 前已是strict-valid但非 exact pending skeleton，不能使用handoff shortcut；保持当前terminal strict path。partial pending、人工预填或重排后的载荷不能伪装成prepare skeleton。

### Persisted terminal and recovery invariants

- terminal persisted receipt仍为passed-only；无schema兼容分支。旧failed/signal/timeout/incomplete/non-passed terminal继续在evaluator调用前拒绝，既有sentinel output和receipt bytes不变。
- handoff后的planned receipts使重复 `run` 继续在process factory/Popen前fail closed；same-plan no-resume与Slice 3 accepted恢复合同不变。
- 该修正不新增 flag、action、schema、marker、第二pending builder或evaluator lifecycle gate。

## Minimal future implementation allowlist

只允许：

1. `utils/investment_agent_acceptance.py`
2. `tests/test_investment_agent_acceptance.py`

明确冻结：`utils/investment_agent_acceptance_contracts.py`、`utils/investment_agent_acceptance_evaluator.py`、全部 `dayu/`、README与Slice 4 docs。若实现证明需要任一冻结owner，必须STOP并重新plan，不得自行扩scope。

## Required state-machine tests

- planned phases全成功 + exact pending skeleton → run exit3/canonical pending JSON；terminal command derivation/process factory/Popen计数为0；无terminal/source inventory/acceptance receipt；planned receipt bytes不变。
- operator填入完整PASS review → 独立verify PASS；完整planned receipts字节不变；terminal仍不存在。
- operator填入完整但不达标的strict-valid review → 独立verify FAIL/canonical receipt；planned receipts字节不变；terminal仍不存在。
- malformed、unknown/missing、secret/PII、plan/receipt/artifact drift → fail closed且不发布新的acceptance outputs。
- non-exact partial pending或预填review不触发handoff shortcut；strict owner path不可绕过。
- persisted failed/signal/timeout/incomplete/non-passed terminal仍在evaluator前拒绝，sentinel outputs与receipt bytes不变。
- pending handoff后再次 `run` 仍因existing planned receipts在任何process factory/Popen前拒绝；无隐式resume。

## History and gate impact

Slice 2 durable closure `docs/reviews/plan-acceptance-20260809-134500-codex.md` 与 Slice 3 durable closure `docs/reviews/plan-acceptance-20260809-slice3-resume-codex.md` 保持accepted。用户明确授权的 Codex Controller review `docs/reviews/plan-review-20260809-173027.md` 为 PASS-WITH-RISKS/open H/M/L=0，独立 Terra review `docs/reviews/plan-review-20260809-manual-review-handoff-terra.md` 为 PASS/open H/M/L=0；Controller durable closure 为 `docs/reviews/plan-acceptance-20260809-manual-review-handoff-codex.md`。MiM provider 401 未参与本 gate，不得记为 MiM PASS。manual-review production correction plan现已handoff-ready，但Slice 4 docs仍等待code correction accepted；Slice 5仍未获SEC、Web、DeepSeek、MiMo、网络或付费授权。

## Changed files and validation

- Modified：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- Modified/closed：`docs/reviews/plan-fix-20260809-manual-review-handoff-codex.md`
- Added closure：`docs/reviews/plan-acceptance-20260809-manual-review-handoff-codex.md`
- Review evidence：`docs/reviews/plan-review-20260809-173027.md` 与 `docs/reviews/plan-review-20260809-manual-review-handoff-terra.md`；source review artifacts未修改。
- Validation：scoped `git diff --check`、whitespace/final-LF/path/status/review-path审计；未运行pytest、pyright、Ruff、code review或任何live调用。

## Open questions and residuals

- Open plan question：无；现有owners足够实现最小修正。
- Dual plan re-review closure：Codex Controller PASS-WITH-RISKS/open 0 + independent Terra PASS/open 0；状态 **ACCEPTED / DUAL PLAN RE-REVIEW PASS**。MiM 401仅记录为未参与，不构成第三路通过证据。
- evaluator非确定性时间字段、owner formatter漂移、fixture lock、future same-plan recovery与第14节其它residual destinations保持不变。
- No live authorization：未读取密钥、未调用SEC/Web/模型/网络、未产生费用。
