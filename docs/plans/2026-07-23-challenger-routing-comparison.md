# Champion / Challenger Routing Comparison

## Goal

Extend the deterministic write-run comparison with fallback-routing evidence
from each run's additive `model_routing` receipt.

## Contract

- Keep `write_run_comparison_v2`; routing is an additive comparison field.
- Report fallback switches, fallback call errors, call completion rate, and the
  fallback share of all recorded scene calls.
- Lower switch and error counts are operationally preferable, but routing
  evidence comes from sequential runs and does not redefine model quality.
- A routing regression or mixed routing change blocks automatic promotion and
  requires operator review.
- Missing routing in a legacy run remains backward-compatible and does not
  alter the existing quality-and-cost verdict.
- An internally inconsistent routing receipt is different from missing legacy
  data and blocks automatic promotion.
- Reporting and comparison remain read-only and never invoke a model.

## Verification

- Pure comparator tests for improved, regressed, mixed, missing, and invalid
  routing receipts.
- Service report tests for current and legacy comparison artifacts.
- Ruff, Pyright, focused comparison tests, and the full regression suite.
