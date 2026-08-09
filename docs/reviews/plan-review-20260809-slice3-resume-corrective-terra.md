# Slice 3 resume corrective plan closure re-review（Terra）

## Reviewed target and scope

- Target: `docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- Source reviews: `plan-review-20260809-slice3-resume-codex.md`、`plan-review-20260809-slice3-resume-terra.md`
- Corrective fix: `plan-fix-20260809-slice3-resume-corrective-codex.md`
- Reviewed at: 2026-08-09 16:04:14 CST（本机时钟）
- Mode: closure-only adversarial plan re-review；对照 current acceptance CLI/contracts/evaluator/phase specs。
- Focus: strict live receipt ingress、trusted evaluator boundary、全 phase recovery、future same-plan recovery ownership、Slice 3 allowlist、Slice 2 accepted history与Slice 5 live gate。
- Excluded: implementation、code/test/plan修改、live/network/SEC/provider/model/paid、commit/push。
- Conclusion: **FAIL**
- Open findings: **High 0 / Medium 1 / Low 0**

## Initial finding closure

| Initial finding | Closure | Evidence |
|---|---|---|
| Codex S3R-001 / Terra M-001: raw evaluator vs untrusted receipt ingress | **CLOSED** | Plan §4.2 line 113 now names evaluator a trusted post-ingress pure evaluator. Slice 3 lines 407/415 require failed/signal/timeout/incomplete/non-passed persisted receipts to enter only through public live `verify_acceptance()`/strict loader and prove evaluator call count zero. Current production flow loads and validates receipts at `verify_acceptance():1753–1755` before `_evaluate_live_plan()` and `evaluate_acceptance()`; no duplicated evaluator lifecycle gate or expanded production allowlist is planned. |
| Codex S3R-002: all-phase recovery ownership | **PARTIAL / OPEN C-001** | §8.1 lines 273–285 now consistently preserve artifacts/receipts/journal and stop for download/import/process/preflight/write/materialize/validation/timeout; current executable recovery is a new run root, and future same-plan recovery is a separately authorized work unit with receipt/idempotency/budget/replay/fingerprint requirements. However line 146 still mandates recovery using the same run-id and existing manifest, directly contradicting that closure. |

## Findings

### C-001-未修复-中-§5.1 仍要求同一 run-id/manifest 恢复，与 corrective 全新 run root 状态机直接冲突

- **位置**: Plan §5.1 line 146，对照 §8.1 lines 273–285、Controller closure line 730 与 current gate line 892。
- **问题类型**: 状态机漏洞 / open question 未收敛 / 不可直接实施。
- **当前写法**: §8.1 已声明当前唯一可执行恢复是 operator 选择全新 run root、重新 prepare并从头开始；任何原 plan/run 的 same-plan retry/resume必须进入未来独立 work unit。可是 §5.1 仍写“恢复必须使用同一 run-id 和已存在的 manifest”。
- **反例/失败场景**: implementation agent或未来 runbook遵循 §5.1，尝试在失败 run root上使用同 run-id/manifest恢复；current `run_acceptance()` 会因任何已有 planned/terminal receipt在 process factory/Popen前拒绝。若人为删/改 receipt继续，又违反 §8.1 的现场保留与 receipt ownership。
- **为什么有问题**: 这是同一 plan 中两个互斥的恢复身份：同 run-id/manifest 与全新 run root/new plan fingerprint不能同时成立。S3R-002声称全阶段统一关闭，但该全局 contract句仍向实现与文档阶段授权旧路径。
- **直接证据**:
  - Plan line 146: “恢复必须使用同一 run-id 和已存在的 manifest”。
  - Plan line 284: “当前唯一可执行恢复”是全新 run root，并生成自己的 plan/fingerprint。
  - Plan line 285: future same-plan retry/resume要求独立 recovery work unit、新 operator authorization、receipt replace/append、phase selection、idempotency、budget/wall、replay与原 fingerprint绑定。
  - Current `_assert_no_existing_run_receipts()` 对任一 planned/terminal receipt fail closed，且 `run_acceptance()` 在任何 subprocess前调用。
- **影响**: Slice 3 recovery测试与后续 Slice 4 runbook可能选择相反路径；实现者可能越过 no-resume gate或错误描述已授权恢复，导致 receipt审计、预算授权与partial artifact ownership失真。
- **建议改法和验证点**:
  1. 删除 line 146 的“恢复必须使用同一 run-id 和已存在的 manifest”，或改成“当前失败 run只保留现场用于诊断；重新执行必须使用全新 run root，same-plan recovery见未来独立 work unit”。
  2. 全文检索 recovery/resume/rerun/retry，确认不存在未限定的同 run-id/current manifest执行授权。
  3. 保持 Slice 3 tests只证明 public live loader fail-before-evaluator、重复 run fail-before-Popen与新 run root边界；不要新增 production seam。
- **修复风险（低/中/高）**: 低；单句 plan-only一致性修正。
- **严重程度（低/中/高/严重）**: 中。

## Confirmed non-regressions

- Untrusted persisted receipts只经 public live verify/strict loader；loader要求完整、ordered、passed planned prefix，失败发生在 evaluator与acceptance receipt原子替换之前。
- Raw evaluator明确为 trusted pure component；计划禁止direct forged lifecycle assertions与重复production gate。
- 全部 phase在当前 runner内均 preserve+stop；download/import/process/write/materialize/validation/terminal没有当前态rerun授权。
- Future same-plan recovery统一进入独立 work unit，并要求新operator authorization、receipt replace/append ownership、phase selection、idempotency/duplicate effects、budget/wall continuation、replay policy与原 plan fingerprint绑定。
- Slice 3 allowlist仍精确为两份 tests；没有新增production owner、flag、action、schema、marker或evaluator gate。
- test-local authorization marker、resume command、receipt-cleanup workaround与绕过`--no-resume`均被明确禁止。
- Slice 0–2 accepted history未撤销；当前corrective状态不授权Slice 3 implementation。
- Slice 5保持 `LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN`，没有任何SEC/Web/model/network/paid授权。

## Special review lenses

- **Architecture boundary**: `untrusted receipt → strict live loader/repository closure → trusted frozen inputs → pure evaluator` 已闭合且与production一致。
- **Best practice / optimal solution**: tests-only Slice 3复用public composition boundary，不复制lifecycle规则到evaluator，是最小安全路径。
- **Overengineering**: future recovery未提前引入marker/schema/action；其复杂状态机正确留给独立work unit。
- **Overcoupling**: 除C-001旧句外，recovery、evaluator与tests职责没有新的跨层耦合。

## Open questions

- 无需用户决策；C-001可由Controller作单句plan-only修正。

## Residual risks and tracking destination

- Future recovery的durable authorization、receipt ownership、idempotency/replay与budget accounting继续由未来独立Gateflow recovery work unit承接。
- Failed run的partial output/journal仍只用于审计和read-only diagnosis；operator cleanup/runbook属于Slice 4，不由Slice 3测试发明执行路径。
- 未执行live/network/SEC/provider/model/paid；不影响本次deterministic closure判断。

## Final conclusion

**FAIL — open High/Medium/Low = 0 / 1 / 0.** S3R-001与duplicate Terra M-001已闭合；S3R-002在§8.1主体已修复，但§5.1仍保留相反的同run-id恢复要求。关闭C-001后再授权Slice 3 implementation。
