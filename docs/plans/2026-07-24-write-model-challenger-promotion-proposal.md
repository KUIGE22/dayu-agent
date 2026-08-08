# Write Model Challenger Promotion Review Proposal

## Objective

Convert a completed Champion/Challenger comparison recommendation into a
tamper-evident artifact that an operator can review without changing runtime
configuration or authorizing promotion.

## Evidence boundary

The proposal binds exactly three local artifacts:

- the Champion `run_summary.json`;
- the Challenger `run_summary.json`;
- the persisted `challenger_comparison.json`.

Each source is recorded with its resolved absolute path and SHA-256. Proposal
creation also recomputes the comparison from the two summaries and requires an
exact match with the persisted comparison. A proposal can be created only when
that original comparison uses `write_run_comparison_v2` and its verdict is
`promote_challenger`.

The run summaries describe the configured scene model plan. Fallback execution
is represented separately by `model_routing`; it is not treated as the current
runtime configuration. The proposal therefore records scene-level plans and
always requires an operator to verify current configuration before any change.
A changed role is marked ambiguous when either side has multiple configured
models, missing scene evidence, duplicate scenes, or unequal scene coverage.

## Safety properties

- Review only.
- No model or API execution.
- No runtime or model-catalog mutation.
- No promotion authorization.
- No generated configuration patch.
- Identical persistence is idempotent; different content cannot overwrite the
  same path.
- Verification fails closed when any source fingerprint, recomputed
  comparison, or proposal fingerprint changes.

## CLI

Export:

```text
dayu-cli write --ticker AAPL --summary \
  --output <champion-output> \
  --challenger-promotion-proposal-output <proposal.json>
```

Verify:

```text
dayu-cli write --ticker AAPL --summary \
  --challenger-promotion-proposal-input <proposal.json>
```

The two options are mutually exclusive and valid only with `--summary`.
Verification status `current` still means `human_review_only`. Stale evidence
returns exit code `4`; malformed files or schemas return `2`.

Current model-catalog repricing remains a display-only operation. Promotion
proposal identity always uses the original persisted comparison and cannot be
changed by `--reprice-costs`.
