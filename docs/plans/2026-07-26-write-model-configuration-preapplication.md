# Write Model Configuration Pre-application Gate

## Objective

Add the last read-only gate before the separately implemented model-routing
application command:

1. export an immutable snapshot of the currently resolved write-scene routing;
2. require every approved transition to match the observed Champion model;
3. build an immutable pre-application plan with exact rollback bytes; and
4. verify that plan against a newly resolved routing snapshot.

This phase does not consume an approval, change configuration, initialize a
model request, or call a model or external API.

## Runtime truth

The current routing truth is the result of the existing write preflight, after
CLI/request overrides, scene manifests, model catalog entries, and temperature
profiles have been resolved. Reading `run.json` or `llm_models.json` alone is
not sufficient.

The snapshot records all nine write signature scenes:

- primary: `write`, `regenerate`, `fix`, `repair`, `overview`;
- audit: `infer`, `decision`, `audit`, `confirm`.

For each scene it binds:

- role, scene name, resolved model, and temperature;
- whether the route came from the scene manifest or a request-level override;
- the active manifest path, file SHA-256, default model, and allowed models.

It also binds the active `run.json` and `llm_models.json` files. Request-level
overrides may be snapshotted, but a persistent pre-application plan fails
closed when an approved transition currently depends on such an override.

## Rollback boundary

For every approved scene transition, the pre-application plan stores:

- the exact target manifest path and pre-change SHA-256;
- JSON pointer `/model/default_name`;
- expected current and proposed model names;
- the exact original manifest bytes, base64 encoded;
- the rollback reference from the human approval.

The original bytes allow the application transaction or a future operator
rollback command to restore the file exactly, including formatting. This phase
only records and verifies those bytes.

## Safety properties

- The approval and promotion evidence must still be current and unexpired.
- Every approved scene/role/model must exactly match the fresh routing snapshot.
- Every changed route must currently come from its scene manifest.
- Every proposed model must be both allowed by that manifest and present in the
  current model catalog.
- Source files and generated artifacts are SHA-256 bound.
- Identical persistence is idempotent; different content cannot overwrite an
  existing artifact.
- Verification uses a newly resolved preflight snapshot, so CLI overrides and
  source-file changes cannot be hidden by an old snapshot.
- No approval consumption, configuration application, model execution, secret
  mutation, or generated credential is implemented here.

## CLI workflow

Export the current routing snapshot:

```text
dayu-cli write --ticker AAPL --preflight-only \
  --write-routing-snapshot-output <routing-snapshot.json>
```

Build a pre-application plan:

```text
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-change-approval-input <approval.json> \
  --write-routing-snapshot-output <routing-snapshot.json> \
  --challenger-config-preapplication-plan-output <preapplication-plan.json>
```

Verify the plan against a fresh runtime resolution:

```text
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-change-approval-input <approval.json> \
  --challenger-config-preapplication-plan-input <preapplication-plan.json>
```

Status `current` means only that the evidence, current routing, and rollback
material are ready for the separate atomic application gate. It does not
authorize or perform that application by itself.
