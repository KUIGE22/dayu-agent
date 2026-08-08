# Write Model Configuration Operator Rollback

## Objective

Provide a fail-closed, model-free control plane for preparing, approving, and
transactionally executing an operator-initiated rollback of an applied
write-model routing change.

The workflow produces three immutable artifacts:

1. an exact-byte rollback plan derived from the applied application receipt;
2. a short-lived, single-use human approval bound to that exact plan; and
3. a transaction receipt recording exact rollback, applied-state recovery, or
   a manual-recovery requirement.

## Evidence chain

The rollback plan is accepted only when all of the following remain true:

- the application receipt is valid, immutable, and has status `applied`;
- a fresh complete routing snapshot matches the receipt's application result;
- the receipt's source pre-application plan file and content fingerprints still
  match;
- every receipt operation matches the corresponding pre-application transition
  and rollback entry;
- every target manifest is inside the current configuration manifest directory;
- every target manifest still has the applied file fingerprint; and
- each embedded restore payload hashes to the original pre-application file
  fingerprint and contains the expected restore model.

The plan never reconstructs old configuration from model names. It copies the
exact original manifest bytes already preserved by the pre-application plan.

## Export a rollback plan

```text
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-application-receipt-input <application-receipt.json> \
  --challenger-config-rollback-plan-output <rollback-plan.json>
```

The command first performs the normal independent application-receipt
verification. A plan is written only when the full fresh routing snapshot is
current and the receipt is eligible for operator rollback.

## Verify a rollback plan

```text
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-application-receipt-input <application-receipt.json> \
  --challenger-config-rollback-plan-input <rollback-plan.json>
```

`current` returns exit code `0`. Source evidence, runtime routing, or manifest
drift returns exit code `4`. Malformed or tampered artifacts return exit code
`2`.

## Human approval request

The operator creates a
`write_model_configuration_operator_rollback_approval_request_v1` document:

```json
{
  "schema_version": "write_model_configuration_operator_rollback_approval_request_v1",
  "approval_type": "write_scene_model_routing_operator_rollback",
  "scope": "one_future_exact_operator_rollback_subject_to_runtime_match",
  "approved_by": "operator@example.com",
  "approval_reference": "ROLLBACK-APPROVAL-42",
  "rollback_reason": "Restore the verified preapplication routing.",
  "approved_at": "2026-07-26T08:00:00Z",
  "expires_at": "2026-07-26T10:00:00Z",
  "rollback_plan_fingerprint": "sha256:<64 hex characters>",
  "application_receipt_fingerprint": "sha256:<64 hex characters>",
  "acknowledgements": [
    "reviewed_exact_restore_operations",
    "current_runtime_matches_applied_receipt",
    "restore_exact_preapplication_bytes",
    "rollback_requires_separate_single_use_command",
    "approval_is_single_use",
    "issuance_and_verification_do_not_modify_configuration",
    "issuance_and_verification_do_not_execute_models"
  ]
}
```

The approval window must be positive and no longer than four hours.

## Issue approval

```text
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-application-receipt-input <application-receipt.json> \
  --challenger-config-rollback-plan-input <rollback-plan.json> \
  --challenger-config-rollback-approval-request <human-request.json> \
  --challenger-config-rollback-approval-output <rollback-approval.json>
```

The plan is independently reverified before approval issuance. The approval
embeds the exact rollback plan, binds both plan and application-receipt
fingerprints, permits one future use, and records that no rollback has occurred.

## Verify approval

```text
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-application-receipt-input <application-receipt.json> \
  --challenger-config-rollback-plan-input <rollback-plan.json> \
  --challenger-config-rollback-approval-input <rollback-approval.json>
```

Only `approved` is eligible for a future single-use rollback command. Expiry,
source changes, routing drift, manifest drift, or an approval/plan mismatch
returns exit code `4`.

## Execute the rollback

```text
dayu-cli write --ticker AAPL \
  --rollback-write-model-configuration \
  --challenger-config-rollback-plan-input <rollback-plan.json> \
  --challenger-config-rollback-approval-input <rollback-approval.json> \
  --challenger-config-rollback-receipt-output <rollback-receipt.json>
```

The dedicated command acquires the same configuration-root lock used by the
application transaction. Before consuming approval, it runs a fresh complete
routing preflight, verifies the approval and all source evidence, checks every
target path and applied file fingerprint, writes an intent containing the exact
applied and restore bytes, and stages all restore files.

The approval is then consumed exactly once before the first atomic manifest
replacement. A second fresh preflight must reproduce the plan's complete
preapplication routing fingerprint before the rollback is accepted.

| Receipt status | Exit | Meaning |
|---|---:|---|
| `rolled_back` | `0` | Exact preapplication bytes and routing were restored. |
| `rolled_forward` | `4` | Rollback failed, exact applied bytes were restored, and a new approval is required. |
| `recovery_failed` | `6` | Exact applied-state recovery could not be proven; stop and recover manually. |

If the process stops after approval consumption, rerunning the same command
does not attempt the rollback again. It exports an existing internal receipt,
or first restores the exact applied bytes from the write-ahead intent and
records `rolled_forward`. The consumption record points to the original
transaction directory, so this recovery remains idempotent when the retry uses
a different workspace or receipt output path.

## Verify the rollback receipt

After execution, independently compare the immutable rollback receipt with a
fresh complete routing preflight:

```text
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-rollback-receipt-input <rollback-receipt.json>
```

The verifier checks both the complete routing snapshot fingerprint and every
scene changed by the transaction.

| Receipt state | Verification result | Exit | Next action |
|---|---|---:|---|
| `rolled_back`, exact restored state still current | `current` | `0` | Stop; the preapplication state remains restored. |
| `rolled_forward`, exact applied state still current | `current` | `0` | A new rollback cycle is eligible, but it needs a new plan and approval. |
| Either proven state has changed | `routing_changed` | `4` | Stop and investigate the new routing state. |
| `recovery_failed` | `manual_recovery_required` | `4` | Stop and recover configuration manually. |

Malformed or tampered artifacts, or an inability to complete the fresh
preflight, return exit code `2`. Receipt verification never performs another
rollback, consumes no approval, starts no write run, and calls no model.

## Export evidence after `recovery_failed`

A `recovery_failed` receipt means the runtime cannot prove either complete
configuration state. Do not run normal preflight against that potentially
mixed configuration. Export an immutable evidence bundle instead:

```text
dayu-cli write --ticker AAPL \
  --challenger-config-manual-recovery-receipt-input <recovery-failed.json> \
  --challenger-config-manual-recovery-evidence-output <manual-recovery-evidence.json>
```

This dedicated path:

- requires a valid `recovery_failed` receipt for the command ticker;
- revalidates the source rollback plan, consumed approval, consumption record,
  application receipt, transaction identity, routing identities, and exact
  operations by file and content fingerprint;
- uses applied candidate bytes only when the transaction-bound write-ahead
  intent remains valid;
- always preserves the exact preapplication candidate bytes from the verified
  rollback plan;
- observes every target twice and blocks if any target changes during export;
- classifies targets as `applied`, `preapplication`, `unexpected`, `missing`,
  `unsafe_symlink`, or `unreadable`;
- summarizes the current state as `exact_applied`, `exact_preapplication`,
  `mixed_known`, or `indeterminate`.

When the intent is valid, `evidence_completeness` is `complete` and each
operation contains both exact candidates. When the intent is missing or
invalid, evidence is `partial`; applied bytes are explicitly unavailable and
are never reconstructed or guessed. The bundle is factual evidence for an
independent human review. It deliberately contains no automatic state choice
and no executable recovery command.

Successful export returns `0`. A wrong receipt status, ticker mismatch, changed
source chain, unsafe target path identity, or target drift during export
returns `4`.
Malformed JSON, an existing output containing different content, or other I/O
failure returns `2`. The mode runs before Host initialization, performs no
preflight or model call, consumes no new approval, and changes no
configuration, secrets, run config, or model catalog.

The subsequent human-selection, independent-approval, and single-use execution
workflow is specified in
`docs/plans/2026-07-28-write-model-configuration-manual-recovery.md`.
The system never selects a candidate state automatically.

## Start a new cycle after `rolled_forward`

When verification reports a current `rolled_forward` receipt, export a new
rollback plan directly from that receipt:

```text
dayu-cli write --ticker AAPL --preflight-only \
  --challenger-config-rollback-receipt-input <rolled-forward-receipt.json> \
  --challenger-config-rollback-plan-output <retry-plan.json>
```

This read-only retry gate revalidates the rolled-forward receipt against the
fresh routing snapshot, then checks the original rollback plan, consumed
approval, approval-consumption record, and application receipt by both file
and content fingerprint. Their transaction identities, routing fingerprints,
and exact operations must agree. The new plan must be created after the
rolled-forward receipt and must have a new plan fingerprint while preserving
the exact original restore operations.

A `rolled_back`, `recovery_failed`, or non-current receipt cannot produce a
retry plan. The consumed approval from the failed cycle is bound to the old
plan path and fingerprint and cannot authorize the retry plan. Issue a new
short-lived approval through the normal plan-verification workflow, then run
the dedicated rollback command with the retry plan and new approval.

Retry-plan export changes no configuration, consumes no approval, starts no
write run, and calls no model.

## Safety boundaries

- Planning, approval, verification, and execution use write preflight without
  calling a model.
- The first four commands are read-only and do not consume approval.
- Approval issuance and verification do not consume the approval.
- The plan and approval are immutable and tamper-evident.
- The application receipt is always an explicit input; a plan cannot silently
  switch to another receipt.
- Execution restores only exact bytes embedded in the approved plan.
- Application and rollback transactions share one cross-process lock.
- Run configuration, model catalog, secrets, and model execution remain
  outside the rollback transaction.
- Rollback-receipt verification is a dedicated read-only preflight mode and
  can only be combined with retry-plan output; approval, application,
  rollback, routing override, Challenger, partial-write, and research
  materialization options remain forbidden.
- Model, fallback, temperature, Challenger, partial-write, and research
  materialization options are forbidden in this workflow.
