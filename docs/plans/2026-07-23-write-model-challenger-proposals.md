# Write Model Challenger Proposals

## Goal

Turn historical fallback observations into a bounded, read-only proposal for
an isolated Champion/Challenger evaluation. A proposal must never be treated
as permission to change a production route or promote a model.

## Inputs

The proposal consumes only the recent window already selected by the model
health report:

- validated `model_routing.routes[]` receipts;
- actual model calls from `model_usage.by_scene`;
- publication gate observations;
- per-model recent health status.

It does not read credentials, call a model, edit configuration, or write a
new run artifact. An operator may separately request an advisory receipt
export.

## Candidate Gates

A role candidate requires:

- at least 3 recent runs;
- complete routing and publication receipts for every recent run;
- a publication gate pass rate of at least 80%;
- at least 5 observed calls for the current primary model;
- a combined primary fallback switch share of at least 20%;
- at least 3 fallback switches;
- fallback completion rate of at least 90%;
- fallback error rate no higher than 10%;
- observed fallback usage covering every completed fallback call;
- a fallback model that is not currently degraded.

If one role has multiple degraded primaries or multiple fallback candidates,
the proposal is `ambiguous`. If a degraded role fails any candidate gate, the
whole proposal is `blocked`. A healthy route is `not_needed`.

## Output Contract

`write_model_challenger_proposal_v2` returns:

- `status`: `ready`, `blocked`, `ambiguous`, or `not_needed`;
- `action`: `run_isolated_challenger`, `manual_review`, or `none`;
- role overrides with their historical evidence;
- a JSON argv array containing only Challenger model override arguments;
- deterministic reason codes and threshold values;
- an evidence window bound to the selected raw summaries by
  `history_fingerprint`;
- a `proposal_fingerprint` over the complete unsigned proposal;
- explicit safety requirements.

`ready` means only that the candidate has enough evidence to be evaluated.
The operator must still use:

1. Champion and Challenger preflight before either run;
2. an isolated Challenger output directory;
3. quality, routing, and cost comparison;
4. manual promotion after the comparison.

## Safety

The proposal service cannot:

- change `llm_models.json`;
- swap primary and fallback model settings;
- create a Host run;
- invoke a provider;
- bypass budgets or circuit breakers;
- promote a Challenger.

Model names are emitted as a JSON argv list instead of an executable shell
command, so the report remains an advisory receipt rather than an action.

## Explicit Export

`write --summary --routing-history-root <root>
--routing-proposal-output <path>` writes only the proposal JSON. The export:

- validates the proposal schema and fingerprint before writing;
- is idempotent when the existing JSON is identical;
- refuses to replace different content by default;
- requires `--overwrite-routing-proposal` for an intentional replacement;
- uses a same-directory temporary file, `fsync`, and atomic replacement.

The history fingerprint is computed from the selected raw `run_summary.json`
objects before optional current-catalog repricing. Repricing can therefore
change the displayed cost basis without changing source or proposal identity.

An exported receipt can be passed back with `--routing-proposal-input`. The
service validates the receipt and compares it with a proposal rebuilt from the
current history. It reports `current`, `stale_history`, or `policy_changed`;
only a current ready receipt exposes the non-executing argv preview.

## Verification

- pure policy tests cover ready, unstable, incomplete, and ambiguous routes;
- fingerprint tests cover tampering, source binding, and repricing stability;
- persistence tests cover atomic, idempotent, and no-clobber behavior;
- verification tests cover current, stale-history, and policy-change states;
- history aggregation tests cover primary and audit role argument mapping;
- write service, CLI, health, and Challenger comparison tests run together;
- static analysis and the full regression suite remain release gates.
