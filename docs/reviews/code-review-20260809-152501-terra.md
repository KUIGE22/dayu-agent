# Slice 2 AAPL Acceptance Round-2 Corrective Re-review (Terra)

## Scope

- Mode: current uncommitted Slice 2 diff, independent corrective re-review.
- Base / HEAD: `1c7e16160b23704558508e9c25522a116d67ad84` / current worktree.
- Reviewed at: 2026-08-09 15:25 CST.
- Inputs read: `code-review-20260809-151500-codex.md`, `code-review-20260809-151501-terra.md`, `slice-2-aapl-acceptance-corrective-review-fix-20260809-152000-codex.md`, and the updated implementation/adjudication/review-fix/final-review-fix artifacts.
- Target: CR-1/CR-2/CR-3 closure plus regression sampling of H1/M1/M2/L1. No live, network, SEC, provider/model, paid call, commit, push, or production/test/plan/artifact modification was performed.
- Verdict: **PASS**.
- Open findings: **High 0 / Medium 0 / Low 0**.

## Corrective finding closure

| Finding | Verdict | Independent evidence |
|---|---|---|
| CR-1 static pre-persistence sanitizer | **CLOSED** | `_STATIC_SECRET_FIELD_PATTERN` is a single case-insensitive pattern accepting `[:=]`, optional whitespace, hyphen/underscore variants of proxy authorization, set-cookie, API key and access-token/key/token/secret/password shapes. `_stream_summary()` calls `_redact_cli_text()` before it forms or truncates a receipt fragment; `ArgumentParser` help/usage/error and `main()` errors use the same sanitizer. A local 21-case receipt matrix (7 field variants × `stderr_present`/`prefix_noise`/`structure_reject`) and 7 CLI `ContractError` invocations each proved no raw value survives. It covered colon/equals Authorization and Cookie, `api_key`, `api-key`, and `X-API-Key`; provider/home, `sk-`, and `AIza` remain covered by the following static rules. |
| CR-2 persisted non-passed terminal / no-resume | **CLOSED** | `_validate_terminal_receipt()` now requires a complete passed planned prefix, terminal phase `passed`, exactly one record, record `passed`, exit code zero, null stop/termination, `partial_by_timeout=false`, and null command evidence. The focused test canonically mutates independently generated terminal receipts to `failed`, `signal`, and `timeout`, then verifies loader rejection while byte-identical sentinel `acceptance-receipt.json` remains untouched. This rejects failed/signal/timeout before runtime construction or evaluator scoring, so independent verify cannot resume or promote the run. |
| CR-3 material plan SHA evidence tamper | **CLOSED** | `_validate_persisted_material_evidence()` now requires both `evidence.price_json_sha256 == plan.price_snapshot_sha256` and `evidence.price_material_sha256 == plan.price_material_sha256`, in addition to existing document ID/report-date/repository closures. The parameterized focused test mutates each field separately to a canonical valid 64-hex value and observes loader rejection. |

## Regression sampling

| Earlier item | Verdict | Evidence |
|---|---|---|
| H1 source-date truth / truthful failure | **No regression** | source-kind-specific date handling remains present; material requires report date while filing requires filing date. The corrective changes only touch the sanitizer, terminal loader gate, plan SHA equality, and tests. |
| M1 timeout partial stream handling | **No regression** | timeout code still captures `TimeoutExpired` bytes and bounded drain; focused terminate/kill/unconfirmed test asserts expected digest and verifies partial/complete Authorization/Cookie values do not enter persisted receipts. |
| M2 original terminal wall and Popen deadline | **No regression** | child timeout is recomputed from the monotonic deadline after `Popen`; runtime wall is still derived from persisted first receipt start to terminal/end receipt. The stricter terminal gate prevents invalid lifecycle data from entering that calculation. |
| L1 Git pattern truth | **No regression** | CLI imports contracts' exported `GIT_OBJECT_ID_PATTERN`; focused test asserts object identity and 40/64 lowercase acceptance with invalid case/length rejection. |
| Formatter grammar | **No regression** | production formatter delta remains precisely one `- status: {result.status}` line between ticker and summary; coverage locks unique exact ordering for `ok` and `cancelled`. |

## Static/scope audit

- Production/test changes remain within the accepted six-file allowlist; `utils/investment_agent_acceptance.py` is untracked but is one of those six. The only formatter production delta is the claimed one line.
- New acceptance code contains no `Any`, `object` escape, `cast`, type-ignore, `getattr`/`hasattr`, or glue wrapper. The existing formatter's generic coercion types and the pre-existing formatter-test cast are outside this corrective delta.
- No evaluator scoring rule was copied into the runner; failed terminal states are rejected by the receipt loader before evaluator runtime evidence is built.

## Verification record

All commands were local and read-only except writing this review artifact.

```text
python -m pytest tests/test_investment_agent_acceptance.py \
  tests/fins/test_cli_formatters_coverage.py -q -p no:randomly
185 passed in 2.67s

pyright <exact six allowlist files>
0 errors, 0 warnings, 0 informations

ruff check <exact six allowlist files>
All checks passed!

git diff --check
exit 0

sanitizer ingress matrix
21 receipt summaries + 7 CLI errors, no raw values
```

## Residual risk

- No live/SEC/Web/provider/model/paid workflow was run; that remains explicitly unauthorized and is not needed to determine these deterministic closure properties.
- Focused tests and static checks cannot prove third-party owner behavior beyond the strict receipt/parser boundary; no new H/M/L issue was found within that boundary.

## Conclusion

**PASS — open High/Medium/Low = 0 / 0 / 0.** CR-1, CR-2, and CR-3 are closed on the current tree, and the sampled H1/M1/M2/L1 plus formatter/repository/typing guardrails show no corrective regression.
