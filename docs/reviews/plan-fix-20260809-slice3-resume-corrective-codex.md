# Slice 3 resume erratum — corrective plan fix

- 日期：2026-08-09
- Gate：Gateflow-governed corrective plan fix only
- 基线：`01b50a92f78f20e73143c3c898b73046101bd50d`
- Target：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- 状态：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- Slice 0–2：accepted history preserved
- Slice 3：**TESTS-ONLY PLAN HANDOFF-READY**
- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**

## Source reviews

1. `docs/reviews/plan-review-20260809-slice3-resume-codex.md` — FAIL，open High 1 / Medium 1 / Low 0。
2. `docs/reviews/plan-review-20260809-slice3-resume-terra.md` — FAIL，open High 0 / Medium 1 / Low 0。
3. Prior artifact：`docs/reviews/plan-fix-20260809-slice3-resume-marker-codex.md`。

两份 reviews 均确认 current runner 的 fresh-run/`--no-resume` 事实，但共同证伪了“raw evaluator 本身是不可信 receipt lifecycle ingress”的假设；Codex review 另发现 §8.1 的 download/import/process 仍残留同-plan rerun 文案，与全 runner existing-receipt rejection 矛盾。

## Controller adjudication and fix mapping

| Finding | Decision / status | Corrective fix |
|---|---|---|
| Codex S3R-001 | **ACCEPTED / FIXED IN PLAN** | raw evaluator 定位为 trusted post-ingress pure evaluator；untrusted persisted receipts 只通过 public live `verify_acceptance()`/strict loader/composition boundary，并在 evaluator 调用前 fail closed |
| Terra M-001 | **DUPLICATE / FIXED BY S3R-001** | 与 S3R-001 合并；不在 evaluator 复制 schema/lifecycle gate，不扩大 production allowlist |
| Codex S3R-002 | **ACCEPTED / FIXED IN PLAN** | §8.1 全面移除 download/import/process 当前态的同-plan rerun/retry；所有 phase 失败保留现场并停止，当前只允许新 run root 从头开始 |

## Corrected trust boundary

数据流唯一为：

`untrusted persisted receipt → public live verify / strict receipt loader + repository closure → frozen trusted AcceptanceInputs/RuntimeEvidence → pure evaluator`

- Slice 3 通过 public live verify/receipt loader 构造 failed/signal/timeout/incomplete/non-passed persisted prefix，断言 `ContractError`、evaluator 调用计数为 0、acceptance receipt sentinel 与 phase receipts byte-identical。
- raw evaluator 不承担任意 persisted receipt 的 schema、prefix completeness 或 phase lifecycle 解析；不得 direct-call evaluator 注入伪造 `RuntimeEvidence` 后要求通用 FAIL。
- 不新增 evaluator lifecycle gate、production flag/action/schema/marker，也不扩大 Slice 3 tests-only allowlist。

## Corrected recovery contract

- Current acceptance run 不支持任何 phase 的 automatic/implicit/manual receipt-based resume 或 existing-run-root rerun。
- Download/import/process/preflight/write/materialize/validation/terminal 任一失败均保留 receipts、journal、output/manifest 与 partial artifacts 并停止；只读 recovery assessment 只用于诊断，不授权 owner replay。
- 不得手工覆盖、删除、移动 receipt 后继续，也不得把旧 partial artifact 复制成成功证据。
- 当前唯一恢复是 operator 选择全新 run root、重新 `prepare` 并从头开始；涉及 SEC/模型/网络/付费调用时必须重新经过 Slice 5 live authorization。
- Future same-plan retry/resume 对所有 phase 一视同仁，全部进入独立 recovery work unit；必须取得显式新的 operator authorization，定义 receipt replace/append ownership、phase selection、idempotency/duplicate side effects、budget/wall-clock accounting、replay policy，并让 durable recovery action/marker 绑定原 acceptance plan fingerprint。

## Slice 3 scope and tests after corrective re-review

允许文件保持精确不变：

1. `tests/test_investment_agent_acceptance.py`
2. `tests/cli/test_research_template_command.py`

Required assertions：

- Public live verify/strict loader 对 failed/signal/timeout/incomplete/non-passed persisted prefix 在 evaluator 前 fail closed；evaluator call count 0，receipt bytes不变。
- 任一已有 planned/terminal receipt 使同一 plan 的重复 `run` 在 process factory/Popen 前拒绝。
- Write preflight 与 paid write argv 各精确包含一次 `--no-resume`，且不存在 `--resume`、marker、authorization token 或 receipt-cleanup workaround。
- Partial/non-passed receipt 永不被提升为 PASS，首个停止 record 后没有后续 command/phase。
- 不 direct-call evaluator 测任意伪造 lifecycle input，不新增 production gate/flag/action/schema/marker。

## Final textual addendum

Corrective reviews：

1. `docs/reviews/plan-review-20260809-slice3-resume-corrective-codex.md` — PASS，open H/M/L=0。
2. `docs/reviews/plan-review-20260809-slice3-resume-corrective-terra.md` — FAIL，C-001 Medium。

Controller 接受 Terra C-001。Target plan §5.1 残留的“恢复必须使用同一 run-id 和已存在 manifest”已改为：failed run root/manifest/receipts/partial artifacts 只读保留；current rerun 必须全新 run-id/root、重新 `prepare` 并生成新 plan/fingerprint；same-run-id/existing-manifest/same-plan recovery 继续由未来独立 work unit承接新 operator authorization与 receipt/幂等/replay/预算策略。Durable mapping 见 `docs/reviews/plan-fix-20260809-slice3-resume-final-codex.md`。

该 corrective artifact 的后续 final dual plan re-review 已通过；durable closure 见下节。

## Accepted closure evidence

- `docs/reviews/plan-review-20260809-slice3-resume-final-codex.md`：PASS，open H/M/L=0。
- `docs/reviews/plan-review-20260809-slice3-resume-final-terra.md`：PASS，open H/M/L=0。
- S3R-001、duplicate Terra M-001、S3R-002、Terra C-001 全部 **CLOSED**；Slice 3 tests-only plan handoff-ready。
- Durable acceptance：`docs/reviews/plan-acceptance-20260809-slice3-resume-codex.md`。Slice 5 保持 **LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**。

## Changed files and validation

- Modified：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- Modified：`docs/reviews/plan-fix-20260809-slice3-resume-marker-codex.md`
- Modified：`docs/reviews/plan-fix-20260809-slice3-resume-corrective-codex.md`
- Modified：`docs/reviews/plan-fix-20260809-slice3-resume-final-codex.md`
- Added：`docs/reviews/plan-acceptance-20260809-slice3-resume-codex.md`
- Validation：scoped diff-check、untracked no-index whitespace、LF final newline、finding/status/path audit。
- 未修改 code、tests、README、Slice 2 artifacts 或 source reviews；corrective 与 final reviews 结果均已记录，本 accepted-closure pass 未运行 pytest、pyright、Ruff、SEC/Web/模型/网络/付费调用；未 commit/push/PR。

## Residuals and open questions

- 无新 plan gap 或 blocking open question。
- Future recovery 的完整 schema/state machine/authorization durability/idempotency/replay/budget 仍明确归属未来独立 Gateflow recovery work unit；本次只定义 current no-resume 边界与 destination，不提前设计实现。
- Slice 5 保持 **LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**。
