# Slice 3 resume corrective plan closure re-review

## Reviewed target and scope

- Target: `docs/plans/2026-08-09-investment-agent-aapl-acceptance.md` 当前 corrective revision
- Corrective fix: `docs/reviews/plan-fix-20260809-slice3-resume-corrective-codex.md`
- Initial reviews: `plan-review-20260809-slice3-resume-codex.md`、`plan-review-20260809-slice3-resume-terra.md`
- Base / HEAD: `01b50a92f78f20e73143c3c898b73046101bd50d`
- Reviewed at: 2026-08-09 16:04:36 CST
- Scope: closure-only 核验 Codex S3R-001/S3R-002 与 duplicate Terra M-001；不扩展其它 plan scope
- Production facts checked: public `verify_acceptance()` 顺序、strict persisted-receipt loader、trusted evaluator call boundary、fresh-run existing-receipt gate、phase specs、v3 prefix contract
- Excluded: plan/code/tests 修改、live/network/SEC/provider/model/paid、commit/push/PR
- Conclusion: **PASS**
- Open findings: **High 0 / Medium 0 / Low 0**

## Assumptions tested

1. 不可信 persisted receipts 只通过 public live verify/strict loader，且在 trusted evaluator 前 fail closed。
2. raw evaluator 明确是 post-ingress pure evaluator，不再承担任意 persisted schema/lifecycle ingress。
3. 所有 current phase failure 都统一 preserve-and-stop，不存在已有 run root 的 retry/resume。
4. 当前唯一恢复是新 run root 重新 prepare/from-scratch；任何同-plan recovery进入独立 work unit。
5. future recovery明确绑定原 plan fingerprint、新 operator authorization、receipt策略、phase选择、幂等/replay与预算/wall续算。
6. Slice 3仍为 tests-only allowlist，Slice 2 accepted history与 Slice 5 live gate不回归。

## Findings

未发现新的 H/M/L finding。

## Initial finding closure

| Finding | Closure | Independent evidence |
|---|---|---|
| Codex S3R-001 | **CLOSED** | Plan §4.2 将 evaluator精确定位为 trusted post-ingress pure evaluator；Slice 3只允许 persisted failed/signal/timeout/incomplete/non-passed prefix经 public live `verify_acceptance()`/strict loader，禁止 direct-call evaluator伪造 lifecycle要求。production `verify_acceptance()`先执行 `_load_and_validate_receipt_prefix()`，成功后才调用 `_evaluate_live_plan()`；loader要求完整 planned prefix全部 passed。 |
| Terra M-001 | **CLOSED as duplicate** | 与 S3R-001使用同一 trust-boundary修复；不复制 lifecycle gate到 evaluator、不扩大 production allowlist。独立 monkeypatch复现证明 non-passed terminal触发 `ContractError` 时 evaluator调用数为 0。 |
| Codex S3R-002 | **CLOSED** | Plan §8.1 先统一声明 download/import/process/write-preflight/write/materialize/validators/terminal任一失败均保留 receipt/journal/output/partial artifacts并停止；明确禁止覆盖/删除/改名 receipt继续。download/import/process旧的同-plan rerun/retry/人工重跑措辞已全部改为 read-only诊断。当前唯一可执行恢复是全新 run root重新 prepare/from-scratch。 |

## Trust-boundary and test code-generatability

当前 plan 的单一数据流已与 production一致：

```text
untrusted persisted receipts
  → public live verify
  → strict receipt loader + repository closure
  → frozen trusted AcceptanceInputs / RuntimeEvidence
  → pure evaluator
```

- `verify_acceptance()` 在加载 bound plan 后先调用 `_load_and_validate_receipt_prefix()`；只有成功才进入 `_evaluate_live_plan()`，最后才写 acceptance receipt。
- `_validate_terminal_receipt()` 对缺少完整 planned prefix或任一 non-passed phase统一抛 `ContractError`；failed/signal/timeout共享同一个 `status != passed` gate。
- 独立复现将完整 terminal canonical改为 failed，并把 module-level `evaluate_acceptance`替换为调用即失败的 sentinel：public live verify仍由 loader拒绝，evaluator调用数为 0，既有 acceptance sentinel与全部 phase receipt bytes不变。
- 现有参数化 test覆盖 failed/signal/timeout terminal no-resume，runner prefix test覆盖每个 nonzero停止点；targeted结果 16 passed。
- Slice 3预期测试可只在 `tests/test_investment_agent_acceptance.py` 与 `tests/cli/test_research_template_command.py` 内完成：构造 persisted prefixes、调用 public API、统计 evaluator/process-factory调用、比较 bytes与 exact argv；无需新增 seam、production gate或 marker。

## Recovery and future ownership closure

- Current runner对全部 phase统一 fresh-run/no-resume；`_assert_no_existing_run_receipts()` 不区分 phase，任一 planned/terminal receipt都会在 process factory/Popen前拒绝重复 run。
- 两条 write phase specs继续各精确包含一次 `--no-resume`；plan禁止 `--resume`、authorization token、receipt cleanup workaround、test-local marker与新增 production action/schema/gate。
- 当前恢复只允许 operator保留/检查旧现场后选择全新 run root，重新 prepare并产生新 plan/fingerprint；不得复制旧 partial artifacts作为成功证据。
- 若新 run涉及 SEC/模型/网络/费用，必须重新经过 Slice 5 live authorization；“新 run root”没有绕过 live gate。
- Future same-plan recovery对所有 phase统一属于独立 recovery work unit，必须取得显式新 operator authorization，并定义 receipt replace/append ownership、phase selection、幂等/重复副作用、预算与 wall续算、replay policy；durable recovery action/marker必须绑定原 acceptance plan fingerprint。不存在无主 recovery风险。

## Scope and gate regression

- Slice 3允许文件仍精确为两份 tests；没有新增 production owner、flag、action、schema、marker或 evaluator lifecycle gate。
- Slice 0–2 accepted plan/code history明确保留；本 corrective revision只控制 Slice 3 entry gate。
- 当前状态保持 `REVIEW OBSERVATIONS FIXED / AWAITING CORRECTIVE DUAL PLAN RE-REVIEW`，未提前授权 implementation。
- Slice 5保持 `LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN`；未授权 SEC/Web/模型/网络/付费动作。
- Architecture/best-practice/optimality/overengineering/overcoupling lenses均未发现残余问题：loader保持唯一 untrusted receipt ingress，evaluator没有复制 lifecycle规则，future recovery没有提前扩 schema。

## Executable evidence

```text
independent public-boundary reproduction
PUBLIC_LIVE_LOADER_REJECT=YES
EVALUATOR_CALLS=0
ACCEPTANCE_SENTINEL_UNCHANGED=True
PHASE_RECEIPTS_UNCHANGED=True

python -m pytest tests/test_investment_agent_acceptance.py -q -p no:randomly \
  -k 'persisted_nonpassed_terminal_is_rejected_without_resume or runner_nonzero_stops_at_every_exact_allowed_prefix'
16 passed, 170 deselected

git diff --check
exit 0
```

## Open questions

- 无。三项 initial observations已由当前 plan与production facts直接闭合。

## Residual risks and tracking destination

- Future recovery的具体 schema/state machine/authorization durability仍刻意留给独立 Gateflow recovery work unit；当前 plan已列出其最小必备契约，因此不是 Slice 3 blocker。
- owner CLI仍有通用 resume能力，但 acceptance specs固定 `--no-resume`；Slice 3 exact argv与public-boundary tests继续守卫该隔离。
- 未执行 live/network/SEC/provider/model/paid；不影响 closure-only deterministic判断。

## Final conclusion

**PASS — open High/Medium/Low = 0/0/0.** S3R-001、duplicate Terra M-001 与 S3R-002均已真实闭合；tests-only Slice 3已恢复 code-generation-ready，且 Slice 2 accepted history与 Slice 5 live authorization gate无回归。
