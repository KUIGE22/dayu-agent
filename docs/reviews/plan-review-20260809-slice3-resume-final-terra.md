# Slice 3 resume final closure-only plan re-review（Terra）

## Reviewed target and scope

- Target: `docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- Prior Terra review: `docs/reviews/plan-review-20260809-slice3-resume-corrective-terra.md`
- Final fix artifact: `docs/reviews/plan-fix-20260809-slice3-resume-final-codex.md`
- Reviewed at: 2026-08-09 16:12:04 CST（本机时钟）
- Mode: final closure-only adversarial plan re-review；只核验 Terra C-001 的最终修复、S3R-001/S3R-002 不回归及既有 gates。
- Focus: §5.1 与全文 current recovery 状态机、future same-plan/manifest/phase recovery ownership、strict receipt ingress、Slice 3 tests-only allowlist、Slice 2 accepted history、Slice 5 live authorization gate。
- Excluded: implementation、code/test/plan修改、live/network/SEC/provider/model/paid、commit/push。
- Conclusion: **PASS**
- Open findings: **High 0 / Medium 0 / Low 0**

## Finding closure

| Finding | Closure | Evidence |
|---|---|---|
| Terra C-001: §5.1 同 run-id/existing manifest 与 §8.1 全新 run root 冲突 | **CLOSED** | Plan §5.1 line 147 已删除旧的 current-recovery 授权，并明确 failed formal run root 的 manifest/receipts/partial artifacts 只供只读诊断；当前重新执行必须选择全新 run-id/run root、重新 `prepare`、生成新 plan/fingerprint。line 147 同时把同-run-id、existing-manifest、same-plan phase recovery 限定为 §8.1 的未来独立 recovery work unit。 |
| Codex S3R-001 / Terra M-001: untrusted receipt 可绕过 strict ingress 直达 raw evaluator | **CLOSED / NO REGRESSION** | Plan §4.2 line 114 继续将 evaluator 定义为 trusted post-ingress pure evaluator；Slice 3 lines 408、415–416 继续要求 failed/signal/timeout/incomplete/non-passed persisted receipts 只经 public live `verify_acceptance()`/strict loader，并在 evaluator 前 `ContractError`、evaluator call count 0、artifacts byte-stable。Current production `verify_acceptance()` lines 1753–1757 先 `_load_and_validate_receipt_prefix()`，后 `_evaluate_live_plan()`，再写 acceptance receipt。 |
| Codex S3R-002: recovery scope/ownership 未覆盖全 phase | **CLOSED / NO REGRESSION** | Plan §8.1 lines 273–286 对 prepare、download、price import、process、write preflight、write、materialize、validation/quality、timeout/terminal 统一 preserve+stop/no-resume；current recovery 只有全新 run root，从头 re-prepare，并生成独立 plan/fingerprint。future same-plan retry/resume 明确另立 work unit、新 operator authorization、receipt replace/append、phase selection、idempotency/duplicate effects、budget/wall、replay 与 original fingerprint binding。 |

## Final contract verification

### Current recovery is one coherent state machine

- `prepare` 只允许创建尚不存在的精确 run root；不允许 `exist_ok`、merge 或 `--overwrite-research`（plan line 147）。
- 任一正式 run phase 失败后，output/manifest、command records、phase receipts、repository journal 与 partial artifacts 原样 preserve，并立即 stop；禁止自动/隐式 resume、已有 receipt 上 rerun，以及删除、覆盖、改名 receipt 后继续（lines 274–284）。
- Operator 若要重新执行，必须选择全新 run-id/run root、重新 `prepare`、从头运行并生成新 plan/fingerprint；涉及 SEC/model/network/paid 时重新通过 Slice 5 authorization（line 285）。
- 旧 run 的 receipts/partial artifacts 仅供 read-only diagnosis，明确不得复制为新 run 的成功证据（lines 147、285）。
- Current implementation 与此一致：`run_acceptance()` line 1670 在构建/启动任何 subprocess 前调用 `_assert_no_existing_run_receipts()`；该 guard lines 3698–3727 对任何已有 planned 或 terminal receipt fail closed。两条 write argv 仍各精确包含一个 `--no-resume`（lines 1383–1396）。

### Future recovery remains a separate work unit

- Plan lines 147、286 没有把 same-run-id、existing-manifest 或 same-plan phase recovery 重新授权给 Slice 3。
- Future work 必须先取得新的 operator authorization，并独立定义 durable recovery action/marker、receipt replace-or-append ownership、phase selection、idempotency/重复副作用、budget/wall-clock continuation、replay policy 与原 acceptance-plan fingerprint binding。
- Slice 3 明确不创建 test-local marker，不新增 production flag/action/gate，不调用 owner 通用 resume 路径（lines 286、409–417）。

### Synonym/adversarial audit

全文检索了 `resume/retry/re-run/rerun/recover/recovery/恢复/重试/重跑/重新执行/同一 run/same-plan/run-id/manifest`。除历史 changelog/adjudication、identity/artifact 描述、明确禁止 current rerun，以及 future independent work unit 外，没有发现把 existing run root、manifest、receipt 或 phase 暗中恢复为当前可执行路径的残留。重点反例均已封闭：

- 删除 receipt 后续跑：plan lines 274、409、417 明确禁止，current runner inventory guard fail closed。
- 从 failed/timeout/signal/partial receipt 得到 PASS：Slice 3 lines 408、415–416 要求 public loader 在 evaluator/receipt write 前拒绝。
- 把旧 manifest/partial output 当新 run 成功证据：line 285 明确禁止。
- 换 run root 却复用旧 fingerprint：lines 133、147、285、290 要求 canonical run root 属 fingerprint，重新 prepare 生成新 plan/fingerprint。
- 失败后借 owner 的通用 resume 能力继续：两条 write spec 固定 `--no-resume`，Slice 3 禁止新增 marker/flag/action或调用 resume 路径。

## Scope and gate non-regressions

- **Slice 3 allowlist**: lines 399–402 仍精确只有 `tests/test_investment_agent_acceptance.py` 与 `tests/cli/test_research_template_command.py`；没有 production owner、flag、action、schema、marker、evaluator gate 或 recovery seam。
- **S3R-001 assertions**: persisted lifecycle tests 仍必须走 public live verify/strict loader，证明 `ContractError`、evaluator call count 0、acceptance receipt sentinel与phase receipts不变、后续command/phase为0；没有退回 direct evaluator forged-input测试。
- **Slice 2 history**: heading/changelog、gate与current entry point继续保留 Slice 0–2 accepted history；本 erratum不重开或撤销 Slice 2 accepted evidence。
- **Slice 5 gate**: lines 104、285、438、663、881–898 继续为 `LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN`；final plan re-review不授权SEC、Web、model、network或paid执行。
- **Implementation gate**: 当前状态仍是 `REVIEW OBSERVATION FIXED / AWAITING FINAL DUAL PLAN RE-REVIEW`，本 Terra PASS 本身不提前标记Slice 3 accepted或授权实施。

## Special review lenses

- **Architecture boundary**: `untrusted persisted receipt → public strict loader/repository closure → trusted frozen inputs → pure evaluator` 保持单向，未复制 lifecycle gate到evaluator。
- **State-machine completeness**: current fresh-run与future recovery分属两个互斥work unit；run identity、receipt ownership、预算授权与partial artifact ownership不再有双重解释。
- **Overengineering**: 本修复是plan-only合同校正，没有为未授权future recovery预埋production marker/schema/action。
- **Overcoupling**: Slice 3只增加owner集成/恢复场景测试，未扩展production allowlist或把test seam耦合进runner/evaluator。

## Validation performed

- Read the current target plan、prior Terra C-001 review与final fix artifact。
- 对current plan执行全文recovery同义词审计，并逐项核对§5.1、§8.1、Slice 3、Controller adjudication、residuals与current gate。
- 对current production只读核对`--no-resume` phase specs、pre-Popen existing-receipt guard、public live verify loader-before-evaluator顺序。
- `git diff --check`：PASS。
- 未运行pytest/pyright/Ruff：本次是single textual plan closure，静态合同与production-fact核验足以覆盖目标；未执行live/network/paid。

## Residual risks and tracking destination

- Future same-plan recovery仍需独立Gateflow work unit解决durable authorization、receipt ownership、idempotency/replay、phase selection与budget/wall continuation；它不是当前open finding，也未获实现授权。
- Failed run partial output/journal仍只用于审计和read-only diagnosis；operator cleanup/runbook由后续既定owner承接，不由Slice 3测试发明执行路径。
- Slice 5 runtime inputs、exact fingerprint、费用/Token/wall与live调用仍全部deferred并受显式授权gate阻塞。

## Final conclusion

**PASS — open High/Medium/Low = 0 / 0 / 0.** Terra C-001已在§5.1闭合；S3R-001、S3R-002与duplicate Terra M-001均未回归。Current recovery全文统一为preserve+stop后使用全新run-id/root重新prepare并生成新plan/fingerprint；任何same-plan/manifest/phase recovery仍只属于未来独立、重新授权的work unit。Slice 3 tests-only allowlist、Slice 2 accepted history与Slice 5 live gate均保持不变。
