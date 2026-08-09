# Slice 3 resume-marker erratum final closure plan review (Codex)

- Review time: 2026-08-09 16:11:23 CST
- Repository: `/Users/wsk/workspace/dayu-agent`
- HEAD: `01b50a92f78f20e73143c3c898b73046101bd50d`
- Review target: the current uncommitted Slice 3 resume-marker plan revision
- Review mode: closure-only; no production/test/plan mutation and no live, network, or paid action
- Inputs: repository `AGENTS.md`, current acceptance plan, Terra corrective review C-001, final fix artifact, prior Slice 3 resume reviews/fixes, and the frozen production acceptance CLI/contracts/phase-spec facts

## Verdict

**PASS**

- Open High: **0**
- Open Medium: **0**
- Open Low: **0**

No new H/M/L finding was found in the final textual correction.

## Closure result

### C-001 — CLOSED

Terra C-001 identified the remaining sentence in §5.1 that required recovery to reuse the same `run-id` and existing manifest, contradicting the already corrected fresh-run rule in §8.1. The current §5.1 now says that, after a formal run root exists, failure evidence is retained only for read-only diagnosis; a current re-execution must select a **new run-id and run root**, run `prepare` again, and create a **new plan/fingerprint**. It explicitly assigns same-run-id, existing-manifest, or same-plan phase recovery to a future independent work unit requiring new operator authorization and a defined receipt/idempotency/replay/budget strategy.

This is consistent with §8.1:

- every current download/import/process/preflight/write/materialize/validation/timeout failure preserves receipts, manifests, journals, and partial artifacts, then stops;
- current recovery creates a new run root, re-prepares from scratch, and creates a new plan/fingerprint;
- old partial evidence cannot be promoted into success evidence;
- any recovery on the original plan/run is future work and must define durable authorization, receipt replacement/append semantics, phase selection, idempotency/duplicate-side-effect handling, budget/wall continuation, and replay behavior.

The old active requirement to recover with the same `run-id`/manifest is gone. The only remaining matches for similar wording are either revision-history text or explicit prohibitions such as not re-executing the same plan/run root; neither creates an executable competing path.

## Prior finding regression check

| Prior item | Status | Current-plan evidence |
|---|---|---|
| S3R-001 / Terra M-001: untrusted receipt ingress | Closed, no regression | §4.2 and Slice 3 keep raw evaluator as a trusted post-ingress pure evaluator. Adversarial persisted receipts must pass through the public live verify/strict loader; rejection occurs before evaluator invocation, with evaluator call count required to remain zero and sentinels/receipts unchanged. |
| S3R-002: current same-plan retry language | Closed, no regression | §8.1 uniformly preserves evidence and stops. Download/import/process no longer permit current same-plan/root retry or overwrite. Original-plan recovery is future-only. |
| Slice 3 scope/allowlist | Preserved | The exact allowlist remains `tests/test_investment_agent_acceptance.py` and `tests/cli/test_research_template_command.py`. No production owner, CLI flag/action, schema, resume marker, or evaluator gate is authorized in Slice 3. |
| Slice 2 gate | Preserved | The plan retains Slice 0–2 as accepted history; this textual erratum does not reopen or alter Slice 2 implementation contracts. |
| Slice 5 gate | Preserved | Slice 5 remains `NOT AUTHORIZED / NOT RUN`; any new external or paid run requires fresh authorization, and this plan change performs no live action. |

## Adversarial consistency checks

1. **Partial artifact counterexample:** a failed phase leaves a manifest, receipts, journal, or partial output. The current plan permits read-only diagnosis only; it cannot be resumed, overwritten, deleted to continue, or converted to success evidence.
2. **Same identity counterexample:** an operator attempts the same `run-id`, existing root, existing manifest, or same plan fingerprint. §5.1 and §8.1 reject this as a current path; a fresh run identity, root, prepare, and plan/fingerprint are required.
3. **Implicit phase retry counterexample:** download/import/process is invoked again after failure. The phase-specific §8.1 rules require preserve-and-stop and contain no current retry route.
4. **Future recovery ownership counterexample:** same-plan/manifest/phase recovery is not left ownerless. It is explicitly an independent future work unit with new operator authorization and specified receipt, idempotency, replay, and budget design obligations.
5. **Trust-boundary counterexample:** a forged persisted failed/signal receipt is sent directly to the raw evaluator. The plan forbids this test construction and requires use of public live verify/loader ingress, with the evaluator not called on rejection.

## Executable/static evidence

- `git diff --check` — passed.
- Full case-insensitive search for `resume`, `retry`, `re-run`, `rerun`, `recover`, `recovery`, Chinese recovery synonyms, `same-plan`, `run-id`, and `manifest` — all active current-recovery references classify as preserve-and-stop/new-run requirements or future independent-work-unit requirements; no active contradictory recovery path remains.
- Exact search for the superseded same-run/same-plan phrases — no active positive recovery requirement remains; matches are revision history or negative prohibitions.
- Production/test diff check — the final C-001 correction is plan text only, so the previously verified public-loader boundary and no-resume production behavior are unchanged.

## Residual risk / future work

Same-plan, same-manifest, or phase-level recovery is intentionally unsupported now. If pursued, it must be planned and authorized as the independent work unit described by the plan; it is not a residual ambiguity or an authorization granted by this PASS.

## Final determination

The final correction closes C-001 and leaves S3R-001, Terra M-001, and S3R-002 closed. The current plan has one coherent recovery rule: preserve evidence, stop, and begin a newly prepared run with a new plan fingerprint. Slice 3 remains tests-only, while Slice 2 history and the Slice 5 authorization gate remain unchanged. The reviewed plan diff is ready to proceed through its stated gate.
