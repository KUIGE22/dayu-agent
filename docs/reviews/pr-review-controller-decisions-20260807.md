# Pull Request 1 Controller Decisions — 2026-08-07

## Gate context

- Pull Request: `KUIGE22/dayu-agent` Pull Request 1
- Base: `origin/main` at `2115c86d5a9027bb51cbbc8a4d0175080732e4e6`
- Accepted pushed head before CI follow-up: `61d7a0b1b5c4d9046268a3dbf4626addfb45f2b7`
- Pushed CI ratchet head: `21492fa1dfa99c8d0e83067c066ba0326e45fe1f`
- Current follow-up: one uncommitted cross-platform pytest assertion fix pending final commit/push
- Gate: Draft PR review/fix/re-review
- Review sources:
  - `docs/reviews/pr-review-deepseek-20260807.md`
  - `docs/reviews/pr-review-mimo-20260807.md`
  - `docs/reviews/pr-review-mimo-warning-adjudication-20260807.md`
  - `docs/reviews/pr-rereview-deepseek-p0-20260807.md`
  - `docs/reviews/pr-rereview-mimo-p0-20260807.md`
  - `docs/reviews/pr-rereview-deepseek-f13-20260807.md`
  - `docs/reviews/pr-rereview-mimo-f13-20260807.md`
  - `docs/reviews/pr-fix-ci-min-compat-deepseek-20260807.md`
  - `docs/reviews/pr-1-review-20260807-101233.md`
  - `docs/reviews/pr-1-review-20260807-101258.md`
  - `docs/reviews/pr-1-rereview-ci-pytest-deepseek-20260807-105645.md`
  - `docs/reviews/pr-1-rereview-ci-pytest-mimo-20260807-105746.md`

## Accepted blockers

| ID | Decision | Evidence | Required gate |
|---|---|---|---|
| DeepSeek F1 | Accepted — security/correctness | `DayuCliArgumentParser` can place an unknown secret-shaped argument in argparse error output without redaction, while the handoff CLI already treats the same shape as sensitive. | Fix with error/usage/help/prog regression coverage; DeepSeek and MiMo re-review. |
| MiMo C10 | Accepted — runtime correctness | Seven business-state guards in `WriteService.print_report()` use `assert`, so the guard disappears under `python -O` and produces non-actionable `AssertionError` otherwise. | Replace with explicit diagnostic guards and regression coverage; DeepSeek and MiMo re-review. |
| MiMo W26 / remote `pr-required min-compat` | Accepted after remote evidence — CI viability | The bare full-repo `pyright` command failed on GitHub Actions for accepted head `61d7a0b`; [run 31134578738, job 92730990951](https://github.com/KUIGE22/dayu-agent/actions/runs/31134578738/job/92730990951) is direct evidence that the required check cannot pass as configured. | Replace the bare gate with a fail-closed full-repo BASE/HEAD diagnostic ratchet, remove the 86 PR-introduced diagnostics in the four affected test files, add edge-case tests, and require independent DeepSeek/MiMo re-review. |
| Remote `pr-required min-compat` pytest lane | Accepted after remote and local evidence — cross-platform correctness | On pushed head `21492fa`, the new Pyright ratchet step passed, then [run 31141645853, job 92752613913](https://github.com/KUIGE22/dayu-agent/actions/runs/31141645853/job/92752613913) failed in the required pytest lane. Exact Python 3.11/minimum-constraints reproduction showed that `test_comparison_can_load_directories_and_persist_artifact` hard-coded the Windows `\` path separator and fails on Unix. | Replace only the hard-coded suffix with `str(Path("champion") / "run_summary.json")`, reproduce the full required lane in a clean environment, and require independent DeepSeek/MiMo re-review. |

## Rejected findings

| ID | Decision | Evidence |
|---|---|---|
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
- Remote CI diagnosis: complete. The accepted head `61d7a0b` exposed a real `pr-required min-compat` failure in the bare full-repo Pyright step; W26 was therefore upgraded from rejected warning to accepted blocker on observed evidence.
- CI follow-up implementation: complete. The workflow now runs a full-repo BASE/HEAD diagnostic ratchet; the four affected test files remove all 86 PR-introduced diagnostics without weakening assertions.
- Controller validation: scoped Pyright reports 0 diagnostics; ratchet suite reports 51 passed; real BASE/HEAD comparison reports 219 HEAD diagnostics, 219 BASE diagnostics, and all 219 matched as pre-existing; the 12-file related suite reports 1497 passed; all three project gates report `ok: true`; `git diff --check` is clean.
- Required CI follow-up re-review: ACCEPTED independently by DeepSeek and MiMo; no remaining review blocker.
- CI ratchet commit/push: complete at `21492fa`. In the resulting run, the ratchet step, `pr-required lock-smoke`, and `dual-model gates` passed; the later required pytest lane exposed the cross-platform assertion defect.
- Cross-platform pytest follow-up: complete. The one-line assertion now uses `pathlib.Path` to generate the platform-native suffix while retaining the original `endswith` semantics.
- Exact minimum-compat validation: Python 3.11 with `constraints/min-py311.txt` and the workflow extras reports `6935 passed, 5 skipped, 9 deselected` after clearing the local Serper/proxy environment variables; scoped Pyright reports 0 diagnostics; Ruff and `git diff --check` are clean.
- Cross-platform pytest re-review: ACCEPTED independently by DeepSeek and MiMo; no remaining review blocker.
- Final follow-up commit/push: authorized by the Draft PR gate after final local validation; pending at the time of this artifact update.
- Merge, approval, Ready-for-Review transition, reviewer requests, and PR comments: out of scope.
