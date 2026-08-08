# Write Model Configuration Change Request And Approval

## Objective

Turn one current, unambiguous Challenger promotion review proposal into:

1. an immutable, scene-level configuration change request; and
2. a short-lived human approval credential for one future change.

This phase does not apply configuration, consume the approval, initialize a
model host, or call any model or external API.

## Evidence boundary

The configuration change request binds the exported promotion proposal by:

- resolved absolute path;
- file SHA-256; and
- promotion proposal content fingerprint.

The request records only model transitions observed in the completed Champion
and Challenger run summaries. Those observations are not treated as proof of
the current runtime configuration. A request can be created only when the
promotion proposal remains `current` and every changed role has an unambiguous,
equal scene set with one configured model on each side.

Before a future application step, the current runtime configuration must still
match every observed Champion scene/model pair.

## Human approval

The human confirmation binds the exact change request fingerprint and source
promotion proposal fingerprint. It includes:

- approver identity and external approval reference;
- rollback-plan reference;
- UTC effective and expiry timestamps;
- the exact acknowledgement list.

Validity cannot exceed four hours. The issued credential embeds the reviewed
request and also binds the request artifact path and file SHA-256.

The credential is eligible for one future application only after a separate
command:

- verifies all evidence again;
- checks the current runtime configuration against the observed Champion;
- validates the rollback plan;
- atomically consumes the approval; and
- applies only the approved scene transitions.

No such application or consumption path is part of this phase.

## Safety properties

- No model or API execution.
- No mutation of `llm_models.json`, `run.json`, prompt assets, environment
  variables, secrets, or runtime routing.
- No generated provider credentials.
- Ambiguous model roles fail closed.
- Stale proposal or request evidence fails closed.
- Identical persistence is idempotent; different content cannot overwrite an
  existing artifact.
- SHA-256 fingerprints provide tamper evidence, not public-key signatures or
  approver authentication.

## CLI workflow

Export a change request:

```text
dayu-cli write --ticker AAPL --summary \
  --challenger-promotion-proposal-input <promotion.json> \
  --challenger-config-change-request-output <change-request.json>
```

Verify a change request:

```text
dayu-cli write --ticker AAPL --summary \
  --challenger-config-change-request-input <change-request.json>
```

Issue a short-lived approval:

```text
dayu-cli write --ticker AAPL --summary \
  --challenger-config-change-request-input <change-request.json> \
  --challenger-config-change-approval-request <human-confirmation.json> \
  --challenger-config-change-approval-output <approval.json>
```

Verify an approval:

```text
dayu-cli write --ticker AAPL --summary \
  --challenger-config-change-approval-input <approval.json>
```

Human confirmation example:

```json
{
  "schema_version": "write_model_challenger_configuration_change_approval_request_v1",
  "approval_type": "write_model_challenger_configuration_change",
  "scope": "one_future_write_scene_routing_change_subject_to_runtime_match",
  "approved_by": "operator@example.com",
  "approval_reference": "OPS-2026-0726-01",
  "rollback_reference": "ROLLBACK-2026-0726-01",
  "approved_at": "2026-07-26T08:00:00Z",
  "expires_at": "2026-07-26T10:00:00Z",
  "configuration_change_request_fingerprint": "sha256:<64 hex digits>",
  "promotion_proposal_fingerprint": "sha256:<64 hex digits>",
  "acknowledgements": [
    "reviewed_exact_scene_model_transitions",
    "promotion_proposal_and_change_request_must_remain_current",
    "runtime_configuration_must_match_observed_champion_before_application",
    "rollback_plan_is_ready",
    "approval_is_single_use",
    "issuance_and_verification_do_not_apply_configuration",
    "issuance_and_verification_do_not_execute_models",
    "separate_application_command_required"
  ]
}
```

Status `approved` means only that the credential remains eligible for a
separate, future single-use application step. The command never applies the
change.
