# Exact Manual Write-Model Configuration Recovery

## Purpose

This workflow handles only an operator-rollback receipt whose status is
`recovery_failed`. The runtime may be in a mixed or otherwise unproven routing
state. The system therefore never chooses between the applied and
preapplication states.

The controlled sequence is:

1. Export immutable factual evidence.
2. Have one human explicitly select exactly one state.
3. Build an immutable exact-byte plan.
4. Have a different human issue a short-lived one-use approval.
5. Run the dedicated recovery transaction.

Planning and approval do not modify configuration. Execution calls no model and
does not start a write run.

## 1. Export evidence

```text
dayu-cli write --ticker AAPL \
  --challenger-config-manual-recovery-receipt-input <recovery-failed.json> \
  --challenger-config-manual-recovery-evidence-output <evidence.json>
```

`complete` evidence contains exact applied and preapplication bytes.
`partial` evidence contains exact preapplication bytes but deliberately marks
applied bytes unavailable. Applied bytes are never reconstructed or guessed.

### Revoked-clearance restart evidence

The command above is the ordinary v1 path. When recovery is restarted after a
clearance revocation, use the dedicated restart bridge documented in
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-restart.md`.
It emits
`write_model_configuration_manual_recovery_evidence_v2` with strict
`clearance_revocation_lineage`.

For that v2 path:

- The selection request schema is
  `write_model_configuration_manual_recovery_selection_request_v2`.
- The approval request schema is
  `write_model_configuration_manual_recovery_approval_request_v2`.
- Both requests must copy `clearance_revocation_lineage` from their source
  artifact exactly.
- The selection acknowledgement adds
  `reviewed_exact_clearance_revocation_lineage`.
- The approval acknowledgement adds
  `approved_exact_clearance_revocation_lineage`.
- Generated plans, approvals, execution artifacts, receipts, and
  verifications use their corresponding v2 schemas automatically.

Do not add the lineage field to a v1 request and do not remove it from a v2
request. The complete v2 contract is in
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-revocation-lineage-v2.md`.

## 2. Record the human selection

Create a `write_model_configuration_manual_recovery_selection_request_v1`
object:

```json
{
  "schema_version": "write_model_configuration_manual_recovery_selection_request_v1",
  "selection_type": "write_scene_model_routing_manual_recovery_selection",
  "scope": "human_choice_of_one_exact_state_for_future_manual_recovery",
  "selected_state": "preapplication",
  "selected_by": "selector@example.com",
  "selection_reference": "INC-2026-0728",
  "selection_reason": "Restore the independently reviewed preapplication state.",
  "selected_at": "2026-07-28T08:10:00Z",
  "manual_recovery_evidence_fingerprint": "sha256:<evidence fingerprint>",
  "source_transaction_id": "<transaction id from evidence>",
  "acknowledgements": [
    "reviewed_recovery_failed_receipt_and_manual_recovery_evidence",
    "selected_state_is_an_explicit_human_decision",
    "selection_binds_one_exact_complete_configuration_state",
    "selection_does_not_authorize_or_modify_configuration",
    "separate_independent_short_lived_approval_required",
    "separate_single_use_recovery_command_required",
    "no_recovery_command_generated",
    "no_model_execution"
  ]
}
```

`selected_state` must be exactly `applied` or `preapplication`. Selecting
`applied` requires `complete` evidence. Selecting `preapplication` is allowed
when the evidence is `complete` or `partial`, because the verified rollback
plan always preserves those exact bytes.

Build the immutable plan:

```text
dayu-cli write --ticker AAPL \
  --challenger-config-manual-recovery-evidence-input <evidence.json> \
  --challenger-config-manual-recovery-selection-request <selection.json> \
  --challenger-config-manual-recovery-plan-output <recovery-plan.json>
```

The command rebuilds the evidence and reads every target again. Any source,
transaction, target-path, or current-byte drift blocks the plan. The plan
embeds the selected exact bytes and the observed current fingerprint for every
target. It authorizes nothing and consumes no approval.

## 3. Issue an independent approval

The approver must differ from `selected_by`, compared case-insensitively.
Create a
`write_model_configuration_manual_recovery_approval_request_v1` object:

```json
{
  "schema_version": "write_model_configuration_manual_recovery_approval_request_v1",
  "approval_type": "write_scene_model_routing_manual_recovery",
  "scope": "one_future_exact_manual_recovery_subject_to_byte_match",
  "approved_by": "approver@example.com",
  "approval_reference": "CAB-2026-0728",
  "approval_reason": "Independently approved the exact selected state and bytes.",
  "approved_at": "2026-07-28T08:20:00Z",
  "expires_at": "2026-07-28T09:20:00Z",
  "manual_recovery_plan_fingerprint": "sha256:<plan fingerprint>",
  "manual_recovery_evidence_fingerprint": "sha256:<evidence fingerprint>",
  "selected_state": "preapplication",
  "acknowledgements": [
    "reviewed_manual_recovery_plan_and_exact_selected_bytes",
    "reviewed_current_observed_target_fingerprints",
    "approved_selected_state_matches_manual_selection",
    "approver_is_independent_from_state_selector",
    "approval_is_short_lived_and_single_use",
    "execution_requires_exact_current_byte_match",
    "failure_must_restore_exact_observed_starting_bytes",
    "issuance_does_not_modify_configuration",
    "issuance_does_not_execute_models"
  ]
}
```

The approval window must be positive and no longer than four hours. Issue the
credential:

```text
dayu-cli write --ticker AAPL \
  --challenger-config-manual-recovery-plan-input <recovery-plan.json> \
  --challenger-config-manual-recovery-approval-request <approval-request.json> \
  --challenger-config-manual-recovery-approval-output <recovery-approval.json>
```

Issuance revalidates the evidence, selection, plan, and current target bytes.
It does not consume the approval or modify configuration.

## 4. Execute exactly once

```text
dayu-cli write --ticker AAPL \
  --recover-write-model-configuration \
  --challenger-config-manual-recovery-plan-input <recovery-plan.json> \
  --challenger-config-manual-recovery-approval-input <recovery-approval.json> \
  --challenger-config-manual-recovery-receipt-output <recovery-receipt.json>
```

Under the same configuration-root lock used by normal application and
operator rollback, execution:

1. Revalidates the plan, approval, evidence, and every current target byte.
2. Writes an immutable intent containing exact starting and selected bytes.
3. Stages all selected manifests.
4. Consumes the approval once before the first replacement.
5. Atomically replaces each target.
6. Builds a fresh complete routing snapshot only after all replacements.

No normal preflight runs against the potentially broken starting state.

If replacement or the post-recovery preflight fails, the transaction restores
the exact starting bytes captured in the intent. It never switches to the
other candidate state. A retry of a consumed transaction never applies again:
it re-exports the internal receipt or restores the exact starting state from
the intent.

## Results

| Receipt status | Exit | Meaning |
|---|---:|---|
| `recovered` | `0` | The exact human-selected state passed fresh full routing validation. |
| `starting_state_restored` | `4` | Recovery failed, but the exact starting bytes were restored; export new evidence before another attempt. |
| `recovery_failed` | `6` | Exact starting-state recovery could not be proven; stop for manual intervention. |

Malformed artifacts and ordinary I/O errors before approval consumption return
`2`. A stale, expired, drifted, or busy recovery gate returns `4`. Failure to
export an internally recorded result returns `6`.

## Independent receipt verification

After execution, independently verify the immutable receipt before resuming
normal writes:

```text
dayu-cli write --ticker AAPL \
  --verify-write-model-configuration-manual-recovery \
  --challenger-config-manual-recovery-verification-receipt-input \
    <recovery-receipt.json>
```

The verifier replays the exact plan/evidence/selection/approval/consumption/
intent chain and observes target bytes under the shared transaction lock. A
`recovered` receipt also requires a fresh full routing snapshot. A
`starting_state_restored` or `recovery_failed` receipt never starts preflight,
because the starting configuration may be invalid.

Only `current` exits `0` and makes the incident eligible for a separate
independent clearance decision. It does not reopen normal writes. The
`starting_state_current` result exits `4` and requires new recovery evidence;
it does not authorize writes. Changed or unproven states require operator
review. See
`docs/plans/2026-07-28-write-model-configuration-manual-recovery-verification.md`
for the complete status and exit-code contract.

After a `current` verification, issue durable normal-write clearance by
following
`docs/plans/2026-07-28-write-model-configuration-manual-recovery-clearance.md`.
The clearance operator must differ from both the selector and approver. Until
that clearance exists for the latest internal recovery transaction, normal
write and preflight commands fail closed before Host or model execution.

## Fixed boundaries

- The system never selects a recovery state.
- The selector and approver must be different people.
- Approval is short-lived and usable once.
- Current bytes must match twice before approval consumption.
- Intent and receipts are immutable and fingerprinted.
- Immutable plan and receipt persistence rechecks targets around atomic-link
  creation and rejects a symlink replacement observed during that interval.
- Target symlinks and paths outside `prompts/manifests` are rejected.
- Execution changes only approved manifest files.
- `run.json`, `llm_models.json`, secrets, and environment variables are not
  modified.
- No model is called and no write run starts.
- A revoked-clearance restart preserves one exact current revocation lineage
  through evidence, selection, planning, approval, execution, receipt, and
  verification.
