# Write Model Challenger Proposal Verification

## Objective

Allow an operator or automation gate to prove that an exported Challenger
proposal is intact and still derived from the current selected run history,
without turning the receipt into an execution mechanism.

## Input Contract

Verification requires all three arguments:

```text
write --summary
  --routing-history-root <history-root>
  --routing-proposal-input <receipt.json>
```

The input option is mutually exclusive with `--routing-proposal-output`.

## Validation

Before comparison, the loader requires:

- `write_model_challenger_proposal_v2`;
- a valid proposal SHA-256;
- a valid history SHA-256;
- consistent selected, recent, and baseline run counts;
- a known proposal status and action;
- only `--challenger-model-name` and
  `--challenger-audit-model-name` flag/value pairs;
- role overrides matching those bounded arguments.

Non-ready proposals cannot contain model overrides.

## Freshness States

- `current`: history and proposal fingerprints both match;
- `stale_history`: selected raw summaries changed;
- `policy_changed`: history matches but current policy rebuilt different
  proposal content.

Only `current` and `ready` exposes a JSON argv preview. The program never
executes the preview. Stale or changed identity returns `4`; invalid input
returns `2`.

## Safety Boundary

Verification does not create a Host session, invoke a provider, call a model,
edit `llm_models.json`, alter fallback routing, start a Challenger run, or
promote a model. The next allowed action remains an explicit, human-triggered
Champion/Challenger common preflight.

## Verification

- unit tests cover strict receipt validation and unsafe argv rejection;
- file round-trip tests cover export, load, and current verification;
- identity tests cover current, stale-history, and policy-change states;
- CLI tests cover required arguments and input/output exclusion;
- service tests cover return codes `0`, `2`, and `4`.
