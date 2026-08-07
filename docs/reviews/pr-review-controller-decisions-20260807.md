# Pull Request 1 Controller Decisions — 2026-08-07

## Gate context

- Pull Request: `KUIGE22/dayu-agent` Pull Request 1
- Base: `origin/main` at `2115c86d5a9027bb51cbbc8a4d0175080732e4e6`
- Reviewed head: `6e22cb57ac180ab69483baf0af1b45efefad3233`
- Gate: Draft PR review/fix/re-review
- Review sources:
  - `docs/reviews/pr-review-deepseek-20260807.md`
  - `docs/reviews/pr-review-mimo-20260807.md`
  - `docs/reviews/pr-review-mimo-warning-adjudication-20260807.md`
  - `docs/reviews/pr-rereview-deepseek-p0-20260807.md`
  - `docs/reviews/pr-rereview-mimo-p0-20260807.md`
  - `docs/reviews/pr-rereview-deepseek-f13-20260807.md`
  - `docs/reviews/pr-rereview-mimo-f13-20260807.md`

## Accepted blockers

| ID | Decision | Evidence | Required gate |
|---|---|---|---|
| DeepSeek F1 | Accepted — security/correctness | `DayuCliArgumentParser` can place an unknown secret-shaped argument in argparse error output without redaction, while the handoff CLI already treats the same shape as sensitive. | Fix with error/usage/help/prog regression coverage; DeepSeek and MiMo re-review. |
| MiMo C10 | Accepted — runtime correctness | Seven business-state guards in `WriteService.print_report()` use `assert`, so the guard disappears under `python -O` and produces non-actionable `AssertionError` otherwise. | Replace with explicit diagnostic guards and regression coverage; DeepSeek and MiMo re-review. |

## Rejected findings

| ID | Decision | Evidence |
|---|---|---|
| MiMo W26 | Rejected — false positive | `.github/workflows/ci-pr-required.yml` runs `pyright` for every pull request targeting `main`; duplicating it in the path-scoped dual-model workflow is not a missing PR type gate. |
| DeepSeek F2 | Rejected as defect | Anthropic extended thinking intentionally omits `temperature` to satisfy the provider request contract. A warning may be a usability enhancement, but the request builder is not silently sending an invalid payload. |
| DeepSeek F3 | Rejected — intended shared state | `README.md`, `dayu/config/README.md`, and `dayu/engine/README.md` explicitly define provider health as shared by stable `model_name`, including cross-worker SQLite state. Per-run isolation would contradict the documented circuit-breaker design. |
| DeepSeek F4 | Rejected — intended aggregate regeneration | The package manifest enumerates all installed templates and is regenerated inside the materialization snapshot/rollback transaction. It is not a per-template user registry that should be merged entry-by-entry. |
| DeepSeek F5 | Rejected as merge blocker | Sections 7–10 are not required by the current structured template-definition consumer; no failing consumer or data-loss path was demonstrated. |
| DeepSeek F7 | Rejected as defect | Monitoring-variable extraction consumes project-owned Chinese template headings. No supported localized/custom-heading contract was identified. |
| MiMo C12 | Rejected as defect | The test-local monkeypatch is scoped and restored by pytest; no cross-test leak was reproduced. |
| MiMo C13 | Rejected as defect | The split literal is test/gate fixture maintenance, not a runtime behavior path. |
| MiMo C14 | Rejected as defect | The repository does not impose a Chinese-only README contract; language consistency is editorial, not correctness. |

## Deferred, non-blocking risks

These items remain visible but do not block the current Draft PR gate because no direct correctness/security failure was demonstrated. They must not be silently relabeled as fixed.

| IDs | Owner | Next gate |
|---|---|---|
| DeepSeek F6 | Engine lifecycle owner | Reassess synchronous `CancellationBridge.stop().join()` with a reproducible event-loop latency test before the PR is made ready for merge. |
| MiMo C1–C5 | CLI/write architecture owner (DeepSeek implementation) | Architecture refactor plan before Ready-for-Review; split only in behavior-preserving slices with dedicated tests. |
| MiMo C6–C9, C11 and W4/W5 | Type-safety owner (DeepSeek implementation) | Diff-scoped type-contract cleanup before Ready-for-Review where feasible; all current and future edits still must pass full Pyright. |
| MiMo W12/W15/W16 | CLI/write architecture owner | Extract repeated/nested helpers in a later behavior-preserving slice; see MiMo warning adjudication artifact. |
| MiMo W24/W25 | Model configuration owner | Add product/config rationale and comparative evidence before changing the affected model defaults again. |
| Remaining MiMo warnings | Owners recorded in `pr-review-mimo-warning-adjudication-20260807.md` | Follow the per-item decision; no W1–W30 item is a current merge blocker after evidence adjudication. |

## Current controller state

- P0 implementation: complete. DeepSeek fixed CLI secret redaction and replaced the seven runtime `assert` guards with explicit diagnostic guards plus regression coverage.
- Follow-up F1.3 compatibility cleanup: complete. Redaction symbols now have one canonical source in `dayu.redaction`, and utils consumers import them directly.
- Required independent re-review: ACCEPTED by DeepSeek and MiMo; no remaining review blocker.
- Commit/push: authorized by the Draft PR gate after final local validation.
- Merge, approval, Ready-for-Review transition, reviewer requests, and PR comments: out of scope.
