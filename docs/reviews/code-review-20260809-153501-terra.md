# Slice 2 AAPL Acceptance Round-3 Corrective Re-review (Terra)

## Scope

- Mode: independent, read-only re-review of the current Slice 2 worktree relative to `1c7e16160b23704558508e9c25522a116d67ad84`.
- Inputs read: `code-review-20260809-152500-codex.md`, `code-review-20260809-152501-terra.md`, `slice-2-aapl-acceptance-round3-review-fix-20260809-153000-codex.md`, and updated implementation/adjudication/review-fix/final-fix artifacts.
- Target: R3-1 shared `CommandRecord` stream-SHA lifecycle, plus CR-1/CR-2/CR-3 regression sampling.
- Excluded: live/network/SEC/provider/model/paid activity, commit/push, and any production/test/plan modification.
- Verdict: **PASS**.
- Open findings: **High 0 / Medium 0 / Low 0**.

## R3-1 lifecycle closure

**CLOSED.** The shared contract invokes `_validate_command_record_streams()` from `_validate_command_record_status()` after validating phase status/exit/termination facts. The helper has the required two exclusive unstarted representations:

- `failed`, null exit, `process_start_failed`; and
- `timeout`, `termination_action=not_started`.

Both require double-null stream SHA and forbid summaries/evidence. Every other lifecycle is considered started and requires both SHA-256 values; neither a double-null nor a single-null pair is accepted. Empty output is still represented by the ordinary SHA-256 of empty bytes.

Independent direct construction verified all requested boundary cases:

| Lifecycle | Double-null / single-null result |
|---|---|
| started `passed` | rejected |
| started `failed` | rejected |
| started `timeout` (`kill`) | rejected |
| started `signal` | rejected |
| real `process_start_failed` | double-null accepted; adding either SHA rejected |
| real timeout `not_started` | double-null accepted; adding either SHA rejected |

The focused canonical-mutation test additionally changes both, only stdout, and only stderr SHA for each passed `verify`, `write`, and `validations` receipt (nine cases). All reject through the shared receipt contract rather than only a terminal-specific loader gate. The legal start-failure record strict-round-trips.

## Earlier corrective findings

| Finding | Verdict | Evidence |
|---|---|---|
| CR-1 pre-persistence sanitizer | **No regression** | `_stream_summary()` still sanitizes before fragment construction/truncation, and CLI error paths use the same function. A fresh local ingress sample of colon/equals Authorization/Cookie and underscore/hyphen API keys over 12 receipt summaries (`stderr_present`, `prefix_noise`, `structure_reject`) plus 4 CLI errors retained no raw values. |
| CR-2 non-passed terminal/no-resume | **No regression** | terminal loader remains passed-only, one-record, exit-zero, no stop/termination/partial, null-evidence. The focused failed/signal/timeout terminal mutation test still rejects before independent verify can overwrite its sentinel receipt. |
| CR-3 material plan SHA binding | **No regression** | persisted material evidence continues to compare JSON and material SHA separately with their plan truths. Each of the two canonical tamper cases is included in the targeted suite and rejects. |

## Static/scope checks

- `git diff --name-only <base>` remains confined to the accepted five tracked production/test paths; the untracked acceptance runner is the sixth allowlisted file. No scope expansion is present.
- R3-1 is one shared contract helper, so terminal/write/validation and future records receive the same lifecycle rule. It does not copy evaluator scoring into runner code or alter terminal-wall behavior.
- The formatter production delta is still the exact one status line; no R3 change introduced a new `Any`/`object` escape, cast, ignore, or wrapper seam.

## Verification

All activity was local; only this review artifact was written.

```text
direct stream lifecycle matrix
started passed/failed/timeout/signal reject both/single null;
start-failure/not-started accept only double null

targeted R3-1 + CR-1/CR-2/CR-3 tests
16 passed, 170 deselected

python -m pytest tests/test_investment_agent_acceptance.py \
  tests/fins/test_cli_formatters_coverage.py -q -p no:randomly
195 passed in 3.52s

pyright <exact six allowlist files>
0 errors, 0 warnings, 0 informations

ruff check <exact six allowlist files>
All checks passed!

git diff --check
exit 0

CR-1 ingress sample
12 receipt summaries + 4 CLI errors redacted
```

## Residual risk

No live/SEC/Web/provider/model/paid workflow was run; it remains unauthorized and is unnecessary for deterministic receipt-contract closure. No new H/M/L issue was found.

## Conclusion

**PASS — open High/Medium/Low = 0 / 0 / 0.** R3-1 is closed centrally for passed, failed, timeout, signal, start-failure, and not-started lifecycle states. CR-1/CR-2/CR-3 remain closed.
