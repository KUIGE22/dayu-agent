# Slice 3 plan-only erratum — resume marker scope closure

- 日期：2026-08-09
- Gate：Gateflow-governed Slice 3 plan fix only
- 基线：`01b50a92f78f20e73143c3c898b73046101bd50d`
- Target：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- 状态：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- Slice 0–2：accepted history preserved
- Slice 3：**TESTS-ONLY PLAN HANDOFF-READY**
- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**

## Gap and direct evidence

Accepted plan 的 Slice 3 原要求“write partial receipt 不会被 PASS；resume 使用同一 plan 且需要新的 operator authorization marker”。前半句与现有 contract 一致，后半句却暗示 Slice 3 可以在只改两份 tests 的范围内构造或消费 marker，而 production 没有该 action/schema。这会迫使 implementation agent 发明 test-local 协议或越过 allowlist，属于真实的可实施歧义。

直接代码事实：

1. `utils/investment_agent_acceptance.py::build_phase_specs` 对 write preflight 与 paid write 两条 argv 都无条件加入 `--no-resume`；没有由 plan、CLI 或测试切换的 resume 分支。
2. `utils/investment_agent_acceptance.py::run_acceptance` 在第一个 phase 前调用 `_assert_no_existing_run_receipts`；后者拒绝任一已存在的 planned phase receipt 或 terminal `verify.json`，因此同一 run root 不能从 partial prefix 重新进入。
3. `utils/investment_agent_acceptance_contracts.py::_validate_phase_record_prefix` 只允许完整 passed records 构成 passed phase；failed/signal/timeout 只能作为执行前缀的最后 record，不能被提升为 PASS。
4. `utils/investment_agent_acceptance.py::_validate_terminal_receipt` 要求全部 planned phases passed，persisted terminal 必须精确单 record passed；partial/non-passed receipt 使 live verify fail closed。
5. `tests/test_investment_agent_acceptance.py::test_slice2_persisted_nonpassed_terminal_is_rejected_without_resume` 已证明 failed/signal/timeout terminal 不会被 verify 接受或覆盖 acceptance receipt。仓库不存在 acceptance-owned resume marker schema/action。

## Controller adjudication

采用最小裁决，不扩大 Slice 3 allowlist：

- 当前 acceptance runner 是明确的 **no-resume** runner。Slice 3 只通过 public live verify/strict receipt loader 验证 partial/non-passed persisted receipt 在 trusted evaluator 调用前 fail closed、后续阶段不执行、重复 `run` 因已有 receipt 在任何 subprocess 前拒绝；raw evaluator 是 post-ingress pure evaluator，不测试不存在的 direct lifecycle gate 或 resume success path。
- 删除“本 Slice 的 resume 必须同一 plan + 新 operator authorization marker”这一可实施歧义。Slice 3 不得创建 test-local marker fixture、monkeypatch marker consumer、resume command 或 production flag/action。
- 任何未来 resume 完全 out-of-scope，必须另立 work unit 与 plan，定义新的 schema/action（或 durable authorization marker），引用并绑定原 acceptance plan fingerprint，取得新的 operator authorization，并重新经过 plan/code review。现有 owner 的通用 resume 能力不能被推导为本验收已授权。
- Slice 3 允许文件保持不变：仅 `tests/test_investment_agent_acceptance.py` 与 `tests/cli/test_research_template_command.py`。

## Exact Slice 3 test contract after re-review

- 构造当前 v3 的 write failed/signal/timeout receipt 与不完整 phase prefix，只通过 public live `verify_acceptance()`/strict loader 进入，断言 evaluator 调用计数为 0、`ContractError` 且既有 `acceptance-receipt.json` 不被覆盖；不得 direct-call evaluator 注入任意伪造 lifecycle input。
- 断言首个 non-passed record 后没有后续 command/phase，partial output/manifest/receipt 保留。
- 对同一 plan/fingerprint/run root 再调用 `run`，断言 `_assert_no_existing_run_receipts` 在 process factory/Popen 调用前拒绝。
- 锁定 planned write preflight 与 paid write argv 各自精确包含一次 `--no-resume`，且没有 `--resume`、marker 或授权 token。
- 不增加 production CLI action/flag/schema，不修改 acceptance runner/contracts，也不伪造 test-local resume marker。

## Status and gates

- Slice 2 accepted review/implementation history不变；本 erratum 只影响尚未实施的 Slice 3 测试说明。
- Target plan 状态为 **ACCEPTED / DUAL PLAN RE-REVIEW PASS**。Codex + Terra final reviews 对同一 revision 均 PASS/open H/M/L=0；Slice 3 tests-only plan handoff-ready。
- Slice 5 保持 **LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**。

## Corrective review addendum

Source reviews：

1. `docs/reviews/plan-review-20260809-slice3-resume-codex.md` — FAIL，S3R-001 High / S3R-002 Medium。
2. `docs/reviews/plan-review-20260809-slice3-resume-terra.md` — FAIL，M-001 Medium（duplicate of S3R-001）。

Controller mapping：

| Finding | Decision / status | Closure |
|---|---|---|
| Codex S3R-001 | **ACCEPTED / FIXED IN PLAN** | raw evaluator 是 trusted post-ingress pure evaluator；untrusted persisted receipt 只经 public live verify/strict loader，在 evaluator 调用前拒绝 |
| Terra M-001 | **DUPLICATE / FIXED BY S3R-001** | 合并为同一 composition-boundary test contract，不复制 lifecycle gate到 evaluator |
| Codex S3R-002 | **ACCEPTED / FIXED IN PLAN** | §8.1 全 phase 统一 no-rerun/no-resume；当前只允许新 run root 重启，future same-plan recovery 单独定义授权、receipt/idempotency/fingerprint 合同 |

Durable corrective mapping 见 `docs/reviews/plan-fix-20260809-slice3-resume-corrective-codex.md`。本 artifact 不宣称 corrective dual plan re-review 已通过。

## Final textual addendum

- `docs/reviews/plan-review-20260809-slice3-resume-corrective-codex.md`：PASS，open H/M/L=0。
- `docs/reviews/plan-review-20260809-slice3-resume-corrective-terra.md`：FAIL，C-001 Medium。
- Controller **ACCEPTED / FIXED IN PLAN** Terra C-001：§5.1 已删除“同 run-id + existing manifest”当前恢复要求，改为 failed run 只读保留、全新 run-id/root 重新 `prepare` 并产生新 plan/fingerprint；same-plan phase recovery 仍归未来独立 work unit。
- Durable final mapping：`docs/reviews/plan-fix-20260809-slice3-resume-final-codex.md`。

## Accepted closure evidence

- `docs/reviews/plan-review-20260809-slice3-resume-final-codex.md`：PASS，open H/M/L=0。
- `docs/reviews/plan-review-20260809-slice3-resume-final-terra.md`：PASS，open H/M/L=0。
- S3R-001、Terra M-001（duplicate）、S3R-002、Terra C-001 全部 **CLOSED**。
- Durable acceptance：`docs/reviews/plan-acceptance-20260809-slice3-resume-codex.md`。Slice 3 tests-only plan handoff-ready；Slice 5 仍 **NOT AUTHORIZED / NOT RUN**。

## Changed files and validation

- Modified：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- Modified：`docs/reviews/plan-fix-20260809-slice3-resume-marker-codex.md`
- Modified：`docs/reviews/plan-fix-20260809-slice3-resume-corrective-codex.md`
- Modified：`docs/reviews/plan-fix-20260809-slice3-resume-final-codex.md`
- Added：`docs/reviews/plan-acceptance-20260809-slice3-resume-codex.md`
- Validation：scoped diff-check、whitespace、LF final newline、status/path audit；corrective 与 final reviews 结果均已记录。本 accepted-closure pass 未运行 pytest、pyright 或 Ruff。
- 未修改 code、tests、README、Slice 2 artifacts 或 source reviews；未 commit、push、PR；未运行 SEC/Web/模型/网络/付费调用。

## Residuals / open questions

- 当前没有新 plan gap 或 blocking open question。
- Future same-plan retry/resume 的 schema、state transition、phase selection、budget accounting、receipt replace/append ownership、idempotency、operator authorization durability 与 replay policy 均刻意不在本 work unit 设计；其 destination 是未来独立 Gateflow recovery work unit，而不是 Slice 3。§5.1/§8.1 已统一：当前唯一恢复是人工选择全新 run-id/root 重新 `prepare` 并生成新 plan/fingerprint。
