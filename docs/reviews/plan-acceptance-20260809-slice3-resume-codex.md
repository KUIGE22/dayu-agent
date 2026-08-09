# Slice 3 resume erratum — durable accepted plan closure

- 日期：2026-08-09
- Gate：Gateflow plan acceptance closure only
- 基线：`01b50a92f78f20e73143c3c898b73046101bd50d`
- Target：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- 状态：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- Slice 3：**TESTS-ONLY PLAN HANDOFF-READY**
- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**

## Acceptance decision

Codex 与 Terra 已对同一 final Slice 3 resume revision 独立完成 closure-only plan re-review，均为 **PASS**，open High/Medium/Low = **0/0/0**。Controller 因而关闭 S3R-001、duplicate Terra M-001、S3R-002 与 Terra C-001，并将 Slice 3 tests-only plan 标为 handoff-ready。

该 closure 只接受计划，不代表 Slice 3 tests 已实现或通过 code review，也不授权 production 修改、SEC、Web、模型、网络或付费调用。Slice 5 仍须单独 live authorization。

## Complete FAIL / fix / re-review / PASS chain

1. `docs/reviews/plan-fix-20260809-slice3-resume-marker-codex.md` — 初始 resume-marker erratum candidate。
2. `docs/reviews/plan-review-20260809-slice3-resume-codex.md` — FAIL；S3R-001 High、S3R-002 Medium。
3. `docs/reviews/plan-review-20260809-slice3-resume-terra.md` — FAIL；M-001 Medium，duplicate of S3R-001。
4. `docs/reviews/plan-fix-20260809-slice3-resume-corrective-codex.md` — Controller corrective fix。
5. `docs/reviews/plan-review-20260809-slice3-resume-corrective-codex.md` — PASS；open H/M/L=0。
6. `docs/reviews/plan-review-20260809-slice3-resume-corrective-terra.md` — FAIL；C-001 Medium。
7. `docs/reviews/plan-fix-20260809-slice3-resume-final-codex.md` — Controller final textual fix。
8. `docs/reviews/plan-review-20260809-slice3-resume-final-codex.md` — **PASS；open H/M/L=0**。
9. `docs/reviews/plan-review-20260809-slice3-resume-final-terra.md` — **PASS；open H/M/L=0**。
10. `docs/reviews/plan-acceptance-20260809-slice3-resume-codex.md` — 本 durable accepted closure。

这条链承接 `docs/reviews/plan-acceptance-20260809-134500-codex.md` 中已关闭的 Slice 2 plan history，不撤销或重写其 accepted 事实。

## Final finding closure

| Finding | Final status | Closure evidence |
|---|---|---|
| Codex S3R-001 | **CLOSED** | Raw evaluator 是 trusted post-ingress pure evaluator；untrusted persisted receipts 只经 public live verify/strict loader，在 evaluator 调用前 fail closed |
| Terra M-001 | **CLOSED AS DUPLICATE** | 与 S3R-001 合并到同一 composition-boundary test contract；不复制 lifecycle gate到 evaluator |
| Codex S3R-002 | **CLOSED** | Current runner 对全 phase preserve+stop/no-resume；当前只允许全新 run root重新prepare，future same-plan recovery归独立 work unit |
| Terra C-001 | **CLOSED** | §5.1 已删除同 run-id/existing manifest当前恢复要求，并与§8.1的新 run-id/root + 新plan/fingerprint合同统一 |

最终 open High = **0**，open Medium = **0**，open Low = **0**；无 blocking open question 或新 plan gap。

## Accepted Slice 3 boundary

Slice 3 implementation allowlist 保持精确两文件：

1. `tests/test_investment_agent_acceptance.py`
2. `tests/cli/test_research_template_command.py`

Handoff contracts：

- Failed/signal/timeout/incomplete/non-passed persisted receipts 只通过 public live verify/strict loader测试，并在 trusted evaluator 前拒绝；evaluator call count=0，receipt bytes保持不变。
- 任一 existing planned/terminal receipt 使重复 `run` 在 process factory/Popen 前 fail closed。
- Write preflight 与 paid write argv 各精确一个 `--no-resume`；不得添加 resume marker、flag/action/schema、receipt cleanup workaround或production gate。
- Current recovery 只有全新 run-id/root、重新 `prepare`、新 plan/fingerprint；同-run-id/manifest/same-plan recovery属于未来独立且重新授权的 work unit。
- 实现完成后仍须运行 accepted plan 指定的 focused tests/validation并进入双路 code review；本 artifact 不预先判定 test/code acceptance。

## Residual risks and destinations

- Future same-plan recovery 的 durable authorization、receipt ownership、phase selection、idempotency/replay、budget/wall-clock accounting继续由未来独立 Gateflow recovery work unit承接；当前未授权。
- Failed-run partial output/journal只用于审计和read-only diagnosis；cleanup/runbook由后续既定 owner承接，Slice 3 tests不发明执行路径。
- Target plan 第14节其它 residual risks与tracking destinations全部保持有效。
- Slice 5 runtime inputs、exact plan fingerprint、费用/Token/wall与外部调用继续受显式 live gate阻塞。

## Changed files and validation

- Modified：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- Modified：`docs/reviews/plan-fix-20260809-slice3-resume-marker-codex.md`
- Modified：`docs/reviews/plan-fix-20260809-slice3-resume-corrective-codex.md`
- Modified：`docs/reviews/plan-fix-20260809-slice3-resume-final-codex.md`
- Added：`docs/reviews/plan-acceptance-20260809-slice3-resume-codex.md`
- Validation：scoped diff-check、untracked no-index whitespace、LF final newline、review-path/finding/status/path audit。
- 未修改 source reviews、code、tests、README 或 Slice 2 artifacts；未运行 pytest、pyright、Ruff、SEC/Web/模型/网络/付费调用；未 commit/push/PR。

## Final declaration

Target plan 状态为 **ACCEPTED / DUAL PLAN RE-REVIEW PASS**。Slice 3 tests-only plan handoff-ready；S3R-001、duplicate Terra M-001、S3R-002、Terra C-001 全部 CLOSED，open H/M/L=0。Slice 5 保持 **LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**。
