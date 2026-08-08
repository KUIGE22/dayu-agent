# Champion / Challenger Write Runs

## Goal

Add an opt-in, side-effect-isolated Challenger run to `dayu-cli write`. The
existing run remains the Champion and keeps its normal output directory. The
Challenger executes the same resolved template and chapter selection in a
separate directory, then a deterministic comparator evaluates both
`run_summary.json` files.

## Safety boundary

- Challenger mode is explicit and disabled by default.
- A full experiment requires a current, exact, single-use run approval.
- The run approval is verified and consumed before Host initialization.
- Champion and Challenger output directories must differ.
- Authorized output directories must be new descendants of the workspace.
- Both model plans are preflighted before the Champion write starts.
- The Challenger never replaces, merges, or materializes the Champion report.
- A comparison can recommend promotion, but cannot perform promotion.
- Missing audit coverage, incompatible chapter sets, incomplete cost data, or
  mixed quality changes require manual review.

## Comparison rules

The comparator validates ticker, summary schema family, chapter identity, and
non-empty chapter coverage. Quality is compared using release gate status,
failed chapters, failed audits, gate-blocked chapters, first-pass chapters,
and total retries. Chapter-level gate and audit regressions are also reported.

Configured cost is comparable only when both summaries report complete cost
coverage in the same currency. Promotion is recommended only when quality is
non-regressing, the model plan actually changed, audit coverage is present,
and the Challenger is cheaper without losing quality or is better without
costing more. The comparison is written to
`champion_output/challenger_comparison.json`.

## Verification

- Pure comparator unit tests for promotion, rejection, and manual review.
- CLI parsing and validation tests.
- Command orchestration tests proving dual preflight, isolated output, and no
  automatic promotion.
- Ruff, Pyright, targeted tests, and full regression suite.
