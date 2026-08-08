# Write Model Health Trends

## Goal

Provide a bounded, read-only view of recent write-model routing health from
persisted `run_summary.json` receipts. The feature must not call a model,
rewrite a historical artifact, or silently change a production model route.

## Contract

- New summaries keep the additive `completed_at` field in UTC.
- Legacy summaries without `completed_at` remain readable through file mtime,
  and the trend receipt reports how many timestamps used that fallback.
- `--routing-history-root` is valid only with `write --summary`.
- Discovery is recursive and deterministic. At most the latest 20 valid
  summaries are selected.
- The default recent window is five runs; the remaining selected runs form the
  baseline.
- Invalid JSON, unsupported schemas, and invalid explicit timestamps do not
  enter the selected window.
- Missing routing receipts remain unknown. They are never converted to zero
  fallback calls.
- Routing counters must agree with the aggregated `routes[]` details.

## Metrics

The read-only receipt reports:

- run and gate-pass counts;
- scene calls and total tokens;
- fallback switch share;
- fallback completion and error rates;
- persisted or repriced cost per scene;
- per-model observed calls, primary fallback share, and fallback error rate.

Cost deltas require complete costs in one matching currency. Supplying
`--reprice-costs` applies the current model catalog to every selected summary
in memory.

## Advisory Policy

The status is one of `healthy`, `watch`, `degraded`, or
`insufficient_data`. Trend direction is evaluated separately as `improved`,
`stable`, `regressed`, `mixed`, or `insufficient_data`.

Current acute failures may produce `degraded` even without a sufficient
baseline. A trend is never claimed until both recent and baseline windows have
at least three runs.

All recommendations use the `manual_review` action. The trend service cannot:

- swap a primary and fallback model;
- edit `llm_models.json`;
- modify a scene manifest or recovery signature;
- bypass preflight, budget, or circuit-breaker controls.

## Verification

- Pure aggregation tests cover regression, legacy timestamps, corrupt routing,
  mixed currencies, and safe formatting.
- CLI tests cover parsing, invalid argument combinations, and read-only service
  wiring.
- Existing write summary, Challenger comparison, and execution-summary tests
  remain part of the regression suite.
