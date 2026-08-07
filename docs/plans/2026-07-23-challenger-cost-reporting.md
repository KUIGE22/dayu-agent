# Champion / Challenger Cost Reporting

## Goal

Extend deterministic write-run comparison so operators can compare quality,
usage, and unit cost directly from `dayu-cli write --summary`, optionally using
the current model catalog without changing historical receipts.

## Contract

- `write_run_comparison_v2` records a cost basis.
- Persisted comparisons use `persisted_run_summary`.
- Summary-time repricing uses `current_model_catalog` and rebuilds both sides
  from their source `run_summary.json` files.
- Repricing never rewrites either run summary or the comparison artifact.
- Incomplete pricing, mixed currencies, or quality regression cannot trigger a
  Challenger promotion recommendation.
- Cost reporting includes requests, scene calls, total tokens, total estimated
  cost, and estimated cost per passed chapter.

## Verification

- Pure comparison tests for current-catalog repricing and missing pricing.
- Artifact hash stability during report-time repricing.
- Legacy v1 comparison loading.
- Service report tests proving the model catalog is forwarded without Host or
  provider calls.
- Targeted static checks and tests, then the full regression suite.
