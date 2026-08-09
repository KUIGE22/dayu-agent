# Slice 3 resume-marker erratum 独立 plan review

## Reviewed target and scope

- Target: `docs/plans/2026-08-09-investment-agent-aapl-acceptance.md` 当前未提交 erratum diff
- Fix artifact: `docs/reviews/plan-fix-20260809-slice3-resume-marker-codex.md`
- Base / HEAD: `01b50a92f78f20e73143c3c898b73046101bd50d`
- Reviewed at: 2026-08-09 15:55:52 CST
- Review scope: 仅 Slice 3 resume-marker erratum；当前 no-resume/fail-closed 测试可生成性、future resume ownership/authorization、Slice 3 allowlist、Slice 2/Slice 5 gate 回归
- Code facts checked: current acceptance phase specs、`run_acceptance()` fresh-run gate、v3 `PhaseReceipt` prefix contract、live terminal loader、evaluator runtime receipt handling、owner `--resume/--no-resume` surface
- Excluded: plan/code/tests 修改、live/network/SEC/provider/model/paid、commit/push/PR
- Conclusion: **FAIL**
- Open findings: **High 1 / Medium 1 / Low 0**

## Assumptions tested

1. Slice 3 的“evaluator/live verify 均不把 failed/signal/timeout/incomplete prefix 判为 PASS”可只通过两份 tests 落地。
2. 当前 runner 确实是 fresh-run/no-resume runner，重入在任何 subprocess 前拒绝。
3. 两条 write argv 始终精确包含一次 `--no-resume`，Slice 3 无需新增 flag/action/schema/marker。
4. future resume 已统一分配给独立 work unit，并绑定原 acceptance plan fingerprint 与新的 operator authorization。
5. erratum 不撤销 Slice 2 accepted history，也不越过 Slice 5 live authorization gate。

## Findings

### S3R-001-未修复-高-tests-only allowlist 无法满足 direct evaluator 的 failed/signal 拒绝断言

- **位置**: Slice 3 变更内容与预期断言，plan `:403`、`:409-410`；允许文件 `:394-397`
- **问题类型**: 不可直接实施 / 测试缺口 / 架构边界
- **当前写法**: plan要求 write partial/non-passed receipt 不会被“evaluator 或 live verify”判 PASS，并限定测试构造 v3 failed/signal/timeout/incomplete prefix，断言“evaluator/live verify 拒绝”；Slice 3 同时只允许修改两份 tests，禁止 production change。
- **反例/失败场景**: 将完整 happy deterministic inputs 的 `RuntimeEvidence.phase_receipts` 替换为 lifecycle-valid 的 v3 `status=failed` 或 `status=signal` receipt，直接调用 `evaluate_acceptance()`。两种输入当前均返回 `PASS` 且 findings为空。只有 timeout/`partial_by_timeout` 被 `_evaluate_wall_clock()`显式转成 High finding。
- **为什么有问题**: live composition 是安全的，因为 `_load_and_validate_receipt_prefix()` / `_validate_terminal_receipt()` 在 evaluator 之前要求全部 planned phases passed；但 direct evaluator 并不承担完整 phase lifecycle gate。实现 Agent若逐字满足本 plan，只能：(1) 修改 `utils/investment_agent_acceptance_evaluator.py`，越过 Slice 3 allowlist；(2) 弱化 failed/signal assertions；或 (3) 在 test 中伪造 seam。三者都违反当前 plan。
- **直接证据**:
  - `utils/investment_agent_acceptance_evaluator.py:1088-1124` 只按 findings决定 verdict；`phase_receipts` 在此只进入 sanitizer。
  - `utils/investment_agent_acceptance_evaluator.py:1406-1427` 仅对 timeout/partial 与 wall drift产生 finding，不检查 failed/signal。
  - 独立可执行复现：`failed PASS []`、`signal PASS []`。
  - 相对地，`utils/investment_agent_acceptance.py:3858-3862` 的 live loader明确拒绝不完整或任一 non-passed planned prefix。
- **影响**: Slice 3 无法按精确 allowlist code-generate；implementer会被迫扩 scope、复制 loader lifecycle规则到 evaluator，或写不符合计划的弱测试。若直接把 loader规则复制进 evaluator，还会形成两个 phase lifecycle真源和不必要的过度耦合。
- **建议改法和验证点**: 采用更窄且符合现有架构的测试合同：failed/signal/timeout/incomplete prefix 全部通过 `verify_acceptance(live)` 进入 strict loader，断言 loader拒绝、evaluator未被调用、sentinel acceptance receipt字节不变；direct evaluator仅保留其既有 timeout/partial wall finding测试，不声称它是未信任 receipt loader。可通过 monkeypatch evaluator调用计数证明 fail发生在 composition boundary。若 Controller坚持 direct evaluator必须拒绝所有 non-passed receipts，则必须显式扩大 Slice 3 production allowlist并先定义 lifecycle单一真源，不能继续称 tests-only erratum。
- **修复风险（低/中/高）**: 低；推荐方案只改 plan表述，不改 production架构。
- **严重程度（低/中/高/严重）**: 高

### S3R-002-未修复-中-全局 no-resume 裁决未统一收口 download/import/process 的同 plan 重试文案

- **位置**: 恢复章节 plan `:272-276`；Slice 3 future-resume ownership `:403-404`
- **问题类型**: 状态机漏洞 / open question 未收敛 / ownership 边界
- **当前写法**: 新 erratum在 write 中断段声明当前 runner拒绝任何既有 execution receipt，任何 future resume必须进入独立 plan/schema/action（或 durable marker）并绑定原 fingerprint + 新 operator authorization；但相邻旧段仍写 download“重新执行同一 plan”、price import“重试仅能用同一 plan”、process在同一 plan下“可人工重跑”。
- **反例/失败场景**: download/import/process任一阶段已写 receipt 后，operator或后续实现按这些旧段尝试同 plan重跑；`_assert_no_existing_run_receipts()` 会对任一 planned receipt直接拒绝。若绕过 runner手动调用 owner，又没有本 erratum要求的独立 recovery schema、receipt ownership、预算和授权闭包。
- **为什么有问题**: 本次 diff把 fresh-run/no-resume定义为全 runner事实，而不是 write-only事实；只修改 write段留下三种看似已授权的恢复动作，使“任何未来 resume进入独立 work unit”的 ownership不再唯一。当前 fail-closed code降低即时风险，但 plan仍会把 future implementer/operator引向两个互斥恢复语义。
- **直接证据**:
  - plan `:272-274` 保留同 plan重新执行/重试/人工重跑；`:276` 才声明任何 future resume独立立项。
  - `utils/investment_agent_acceptance.py:3698-3727` 不区分 phase，只要任一 planned/terminal receipt存在就拒绝新的 run。
  - `run_acceptance()` 在 `:1667-1670` 于任何 process-factory/Popen前执行该 gate。
- **影响**: future recovery ownership不清，可能导致 scope越界、无 receipt的手工 owner重放、预算/授权绕过，或后续 plan再次返工。
- **建议改法和验证点**: 同步改写 download/import/process三段：当前 work unit只保留现场并允许 read-only recovery assessment，不授权任何执行；所有阶段的 rerun/resume均进入同一 future recovery work unit，新的 recovery plan/marker必须引用原 acceptance plan fingerprint、记录新 operator authorization，并定义 phase选择、receipt ownership、预算、幂等与 replay policy。验证 plan全文不再存在未限定的“同一 plan重试/人工重跑”当前态措辞。
- **修复风险（低/中/高）**: 低；仅统一计划状态机与ownership文本。
- **严重程度（低/中/高/严重）**: 中

## Confirmed closures / non-regressions

- 当前代码的两条 write specs分别精确包含一次 `--no-resume`，没有 acceptance-owned `--resume`、marker或authorization token。
- `run_acceptance()` 在重建/执行 phase前调用 `_assert_no_existing_run_receipts()`；该 gate不触发 process factory/Popen。
- v3 contract要求 passed phase必须完整且全部 records passed；failed/signal/timeout只能作为前缀末条停止 record。
- live terminal loader要求全部 planned receipts passed，persisted terminal也必须精确单 record passed；现有 targeted tests中 non-passed terminal与每个 nonzero prefix均 fail closed（16 passed）。
- Slice 3 allowlist维持两份 tests且“不新增 production flag/action/schema/marker”的方向本身合理；S3R-001修正文案后即可与代码边界自洽。
- future recovery文本已包含原 acceptance plan fingerprint、新 operator authorization、独立 plan/code review三个必要 gate；S3R-002只要求把该 ownership统一到其它失败阶段。
- Slice 2 accepted evidence/closure未被撤销；当前 plan明确降级的仅是 Slice 3 erratum gate。
- Slice 5仍为 `LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN`，本 diff没有授权任何 live/network/paid动作。

## Special review lenses

- **Architecture boundary**: live receipt真实性由 CLI loader闭合，evaluator消费已验证 runtime facts；推荐不在 Slice 3复制 phase lifecycle规则到 evaluator。
- **Best practice / optimal solution**: 对 non-passed persisted receipt，应测试 composition boundary fail-before-evaluator，而不是为了测试文字扩 production surface。
- **Overengineering**: 删除 test-local marker是正确收窄；当前没有理由在 Slice 3发明 authorization schema/action。
- **Overcoupling**: S3R-001若以 evaluator重复规则修复会把 loader与评分器绑定；tests-only plan应只验证既有边界。

## Executable evidence

```text
git diff --check
exit 0

python -m pytest tests/test_investment_agent_acceptance.py -q -p no:randomly \
  -k 'persisted_nonpassed_terminal_is_rejected_without_resume or runner_nonzero_stops_at_every_exact_allowed_prefix'
16 passed, 170 deselected

independent direct-evaluator v3 reproduction
failed PASS []
signal PASS []
```

## Open questions

- 无需用户决策。两项都可由 Controller以窄 plan-only edit闭合：收窄 evaluator断言到 live composition boundary，并统一所有失败阶段的 future recovery ownership。

## Residual risks and tracking destination

- future resume/recovery的 schema、phase selection、budget accounting、authorization durability、receipt ownership、idempotency与 replay policy继续明确留给独立 Gateflow work unit；本 Slice不得提前设计或实现。
- owner production CLI仍有通用 `--resume`，但 acceptance phase specs固定 `--no-resume`；该差异继续由 exact argv tests和 future recovery authorization gate跟踪。
- 本轮未执行 live/network/SEC/provider/model/paid；不影响 deterministic plan可实施性判断。

## Final conclusion

**FAIL — open High/Medium/Low = 1/1/0.** Erratum正确识别了当前 runner的 no-resume/fresh-run事实，并保持 Slice 2/Slice 5 gates；但 direct evaluator断言与 tests-only allowlist不可同时实现，且全局 future recovery ownership尚未覆盖 download/import/process旧重试文案。关闭 S3R-001/S3R-002 后再进入 Slice 3 implementation。
