# Write Model Configuration Application Gate

## Objective

Transactionally apply one approved write-scene routing change while preserving
an exact, testable rollback path.

This gate:

1. accepts one immutable pre-application plan and its exact human approval;
2. re-resolves the current runtime routing before any approval consumption;
3. consumes that approval exactly once;
4. atomically updates only the approved scene manifest defaults;
5. runs a fresh post-application preflight; and
6. restores the original bytes if any post-consumption step fails.

It does not start a write run, execute a model, change the model catalog, change
`run.json`, mutate environment variables, or handle secret values.

## Required evidence

The command requires all four inputs:

- `--apply-write-model-configuration`;
- `--challenger-config-application-plan-input <plan>`;
- `--challenger-config-change-approval-input <approval>`;
- `--challenger-config-application-receipt-output <receipt>`.

The plan must be a current
`write_model_challenger_configuration_preapplication_plan_v1`. The approval
must be the exact, unexpired single-use approval bound by that plan. The fresh
runtime snapshot must still match every source fingerprint, observed Champion
route, manifest default, allowed-model set, model catalog entry, run
configuration, and fallback route captured before application.

## Transaction protocol

The application runs under a single-instance lock derived from the resolved
configuration root:

1. load and validate the plan, approval, and source routing snapshot;
2. detect a prior immutable receipt or interrupted transaction;
3. run a fresh preflight with newly constructed dependencies;
4. verify the plan against that fresh snapshot;
5. verify every target manifest still has its approved original bytes;
6. persist a transaction intent containing exact original and applied bytes;
7. stage every target file;
8. atomically persist the approval-consumption marker;
9. atomically replace each target manifest;
10. run another fresh preflight and verify the complete resulting routing;
11. persist the internal and operator-facing immutable receipt.

Only JSON pointer `/model/default_name` changes. The generated JSON preserves
all other structured manifest content. `run.json`, `llm_models.json`, audit
routes not present in the plan, fallback routes, and unchanged scenes must
remain identical to the approved source snapshot.

## Rollback and recovery

Any exception after approval consumption triggers reverse-order restoration
using the exact original bytes stored in the plan and transaction intent. A
fresh preflight must then reproduce the original routing snapshot before the
rollback is considered exact.

If execution is interrupted after approval consumption, rerunning the same
plan and approval first resolves the original transaction. When its internal
completion receipt is already durable, the command only re-exports that
historical receipt. When no completion receipt exists, it restores the original
configuration before returning a recovery receipt. The consumed approval is
never reused for a second application attempt.

The approval-consumption marker is stored beside the approval artifact rather
than under the selected workspace, so changing `--workspace` cannot bypass
single-use enforcement.

## CLI

```text
dayu-cli write --ticker AAPL \
  --apply-write-model-configuration \
  --challenger-config-application-plan-input <preapplication-plan.json> \
  --challenger-config-change-approval-input <approval.json> \
  --challenger-config-application-receipt-output <application-receipt.json>
```

This is a dedicated mode. It cannot be combined with summary, preflight-only,
model or temperature overrides, fallback overrides, Challenger operations,
research materialization, or partial write modes.

## Outcomes

- `applied`: all changes and post-application checks passed; exit code `0`.
- `rolled_back`: exact rollback and rollback preflight passed; exit code `4`;
  a new approval is required before another application.
- `rollback_failed`: exact restoration could not be proven; exit code `6`;
  stop and perform manual recovery.

The receipt uses strict schema validation and a content fingerprint. Repeating
the command after a completed transaction returns the historical receipt
idempotently and does not rewrite configuration.

## Independent verification

An application receipt can be checked later against a newly resolved full
routing snapshot:

```text
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-application-receipt-input <application-receipt.json>
```

The verifier compares the complete post-operation snapshot fingerprint, not
only the changed operations. Drift in an unchanged scene, manifest metadata,
`run.json`, `llm_models.json`, fallback routing, temperature, or request-level
resolution context therefore fails closed as `routing_changed`. A receipt with
status `rollback_failed` always produces `manual_recovery_required`.

Only `current` plus historical receipt status `applied` is eligible to enter
the separate operator rollback-planning gate documented in
`2026-07-26-write-model-configuration-operator-rollback.md`. Verification
itself is read-only and does not authorize rollback, consume approval, start
writing, or call a model.

## Verification coverage

Automated tests cover:

- exact application of only the approved primary manifests;
- source drift before approval consumption;
- replacement failure after partial application;
- post-application preflight failure;
- interruption before receipt persistence and recovery on retry;
- single-use behavior across different workspace directories;
- immutable, tamper-evident receipts; and
- CLI isolation from normal write-pipeline execution.
