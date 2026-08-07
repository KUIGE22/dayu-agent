# Write Model Configuration Application Verification

## Objective

Provide an independent, model-free audit of a historical configuration
application receipt against the routing that the write service resolves now.

The application transaction already verifies its result before completing.
This command adds a repeatable later check for operators and creates the
minimum trustworthy input boundary for a future operator-initiated rollback
plan.

## Verification truth

The receipt stores the fingerprint of the complete routing snapshot produced by
the fresh post-operation preflight. Verification runs preflight again and
compares that complete fingerprint.

The snapshot covers:

- all nine primary and audit signature scenes;
- resolved model names, roles, temperatures, and route sources;
- every scene manifest path, file fingerprint, default, and allowed models;
- `run.json` and `llm_models.json`;
- primary and audit fallback routes; and
- request-level resolution context.

Checking only the operations listed in the receipt is insufficient because an
unapproved scene or configuration source could drift while every changed scene
still appears correct.

## CLI

```text
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-application-receipt-input <application-receipt.json>
```

This is a dedicated read-only preflight mode. It cannot be combined with model,
audit-model, fallback, or temperature overrides; partial write modes;
Challenger operations; application or pre-application artifacts; routing
proposals; approval operations; or research materialization.

## Results

- `current`: the full current snapshot and changed-operation evidence both
  match the receipt; exit code `0`.
- `routing_changed`: any part of the full routing snapshot differs; exit code
  `4`.
- `manual_recovery_required`: the receipt records `rollback_failed`, so no
  verified expected post-operation state exists; exit code `4`.

Malformed, tampered, or unreadable receipts fail with exit code `2`.

Only `current` with receipt status `applied` sets
`eligible_for_operator_rollback_plan=true`. A current `rolled_back` receipt is
valid historical evidence but has nothing left to roll back.

## Safety boundaries

- The verifier never mutates configuration or receipt artifacts.
- It never consumes or issues an approval.
- It never starts a write run or calls a model.
- A completed `applied` or `rolled_back` receipt must contain a post-operation
  snapshot fingerprint.
- A `rolled_back` receipt must bind that fingerprint to the original source
  snapshot.
- A `rollback_failed` receipt cannot claim a verified post-operation snapshot.
- Eligibility permits the separate operator rollback-plan export described in
  `2026-07-26-write-model-configuration-operator-rollback.md`; it is not
  rollback authorization.
