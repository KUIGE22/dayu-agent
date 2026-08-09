# Slice 3 resume erratum — final textual plan fix

- 日期：2026-08-09
- Gate：Gateflow-governed final textual plan fix only
- 基线：`01b50a92f78f20e73143c3c898b73046101bd50d`
- Target：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- 状态：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- Slice 0–2：accepted history preserved
- Slice 3：**TESTS-ONLY PLAN HANDOFF-READY**
- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**

## Source corrective reviews

1. `docs/reviews/plan-review-20260809-slice3-resume-corrective-codex.md` — **PASS**，open High 0 / Medium 0 / Low 0。
2. `docs/reviews/plan-review-20260809-slice3-resume-corrective-terra.md` — **FAIL**，open High 0 / Medium 1 / Low 0；C-001。
3. Prior artifacts：`docs/reviews/plan-fix-20260809-slice3-resume-marker-codex.md`、`docs/reviews/plan-fix-20260809-slice3-resume-corrective-codex.md`。

在本 final fix 产生时尚不能宣称 dual plan re-review PASS；随后 Codex + Terra 已对同一 final revision 均给出 PASS/open H/M/L=0。Controller 已关闭 Terra C-001；Codex previous PASS 作为前一 revision 的闭合证据保留。

## Controller adjudication

| Finding | Decision / status | Final textual fix |
|---|---|---|
| Terra C-001 | **ACCEPTED / FIXED IN PLAN** | 删除 §5.1 当前态“恢复必须使用同一 run-id 和已存在 manifest”；统一为 failed run preserve+stop、manifest/receipts/partial artifacts 只读保留、current rerun 使用全新 run-id/root 并重新 prepare 生成新 plan/fingerprint |

Codex S3R-001、S3R-002 与 duplicate Terra M-001 保持 closed-in-plan，不因本次单句修正回归。

## Direct conflict and corrected contract

旧 §5.1 同时要求 run root 在 `prepare` 前不存在、成功后不允许 merge/overwrite，却又要求“恢复使用同一 run-id 和已存在 manifest”。这与 `run_acceptance()` 对任一 existing planned/terminal receipt 的 pre-Popen rejection，以及 §8.1 全新 run root恢复合同直接冲突。

修订后的唯一 current contract：

- `prepare` 仍只创建不存在的新 run root，不允许 `exist_ok`、merge 或 `--overwrite-research`。
- 正式 run root 任一阶段失败后完整 preserve+stop；existing manifest/receipts/partial artifacts 只供 read-only diagnosis。
- Current rerun 必须由 operator 选择全新 run-id/root、重新 `prepare`，并生成新 plan/fingerprint；涉及 live/费用时重新经过 Slice 5 authorization。
- 不得手工删除/覆盖/move receipts 后继续，也不得复用 existing manifest 或旧 partial artifact 作为成功证据。
- 同-run-id、existing-manifest 或 same-plan phase recovery 全部属于未来独立 recovery work unit；必须取得新 operator authorization，并明确 receipt replace/append、phase selection、idempotency/duplicate effects、budget/wall-clock、replay 与原 plan fingerprint绑定策略。

## Synonym audit

已全文检索 `resume/retry/re-run/rerun/recover/recovery/恢复/重试/重跑/重新执行/同一 run/same-plan/run-id/manifest`。唯一与 current recovery 状态机冲突的残留是 §5.1 C-001 句，现已修正。其余命中属于：

- 历史 changelog/review adjudication，不改写历史事实；
- 当前明确禁止 resume/retry/rerun 的合同；
- future independent recovery work unit 的 deferred ownership；
- run-id/manifest 的正常 identity、artifact inventory 或 completion-report用途；
- Slice 2 accepted history与旧 schema不可恢复 residual，不构成 current execution authorization。

## Scope and gates

- Slice 3 allowlist仍精确为 `tests/test_investment_agent_acceptance.py` 与 `tests/cli/test_research_template_command.py`。
- 未新增 production owner、flag、action、schema、marker、evaluator lifecycle gate或 recovery seam。
- 状态为 **ACCEPTED / DUAL PLAN RE-REVIEW PASS**；同一 final revision 的 Codex + Terra 双路 re-review 均 PASS，Controller 已关闭 open H/M/L。Slice 3 tests-only plan handoff-ready，但实现仍须进入 code/test/review gates。
- Slice 2 accepted history保持不变；Slice 5保持 **LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**。

## Accepted closure evidence

- `docs/reviews/plan-review-20260809-slice3-resume-final-codex.md`：PASS，open H/M/L=0。
- `docs/reviews/plan-review-20260809-slice3-resume-final-terra.md`：PASS，open H/M/L=0。
- S3R-001、duplicate Terra M-001、S3R-002、Terra C-001 全部 **CLOSED**。
- Durable acceptance：`docs/reviews/plan-acceptance-20260809-slice3-resume-codex.md`；Slice 3 tests-only handoff-ready，Slice 5 **NOT AUTHORIZED / NOT RUN**。

## Changed files and validation

- Modified：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- Modified：`docs/reviews/plan-fix-20260809-slice3-resume-marker-codex.md`
- Modified：`docs/reviews/plan-fix-20260809-slice3-resume-corrective-codex.md`
- Modified：`docs/reviews/plan-fix-20260809-slice3-resume-final-codex.md`
- Added：`docs/reviews/plan-acceptance-20260809-slice3-resume-codex.md`
- Validation：scoped diff-check、untracked no-index whitespace、LF final newline、C-001/status/path/synonym audit。
- 未修改 code、tests、README、Slice 2 artifacts 或 source reviews；final reviews 结果已记录，本 accepted-closure pass 未运行 pytest、pyright、Ruff、SEC/Web/模型/网络/付费调用；未 commit/push/PR。

## Residuals and open questions

- 无新 plan gap 或 blocking open question。
- Future same-plan recovery 的 schema/state machine/operator authorization/receipt ownership/idempotency/replay/budget 继续归属未来独立 Gateflow recovery work unit，不是 Slice 3 实现范围。
