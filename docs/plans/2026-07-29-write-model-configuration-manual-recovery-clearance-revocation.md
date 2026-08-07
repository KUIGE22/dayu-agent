# Write-model configuration manual recovery clearance revocation

## Goal

Immediately fail closed when an operator discovers that the latest manual
recovery clearance should no longer authorize normal writes. Revocation is a
blocking action: it changes no configuration, consumes no approval, constructs
no Host dependencies, and calls no model.

A revocation is immutable for its recovery transaction. Re-exporting or
reissuing the same clearance cannot restore normal writes. Operators must
complete a newer manual recovery transaction and issue a new clearance for
that newer transaction.

## Revocation request

Create a
`write_model_configuration_manual_recovery_clearance_revocation_request_v1`
object:

```json
{
  "schema_version": "write_model_configuration_manual_recovery_clearance_revocation_request_v1",
  "revocation_type": "write_scene_model_routing_manual_recovery_clearance_revocation",
  "scope": "revoke_one_manual_recovery_clearance_and_block_normal_writes",
  "ticker": "AAPL",
  "transaction_id": "<latest recovery transaction id>",
  "manual_recovery_receipt_fingerprint": "sha256:<latest receipt fingerprint>",
  "manual_recovery_clearance_fingerprint": "sha256:<latest clearance fingerprint>",
  "revoked_by": "incident-commander@example.com",
  "revocation_reference": "INC-REVOKE-2026-0729",
  "revocation_reason": "The prior clearance requires immediate operator review.",
  "revoked_at": "2026-07-29T08:40:00Z",
  "acknowledgements": [
    "reviewed_latest_manual_recovery_receipt_and_clearance",
    "revocation_binds_the_exact_latest_clearance",
    "revocation_immediately_blocks_normal_writes",
    "revocation_cannot_be_removed_for_this_transaction",
    "newer_manual_recovery_transaction_required_for_future_clearance",
    "revocation_does_not_modify_configuration",
    "revocation_does_not_consume_approval",
    "revocation_does_not_execute_models"
  ]
}
```

`revoked_by` must be a non-empty auditable identity. It does not need to be a
fourth identity distinct from the selector, recovery approver, and clearer:
revocation only removes authority and should remain available during an
incident. `revoked_at` must follow clearance issuance, must not be in the
future, and may be at most four hours old for first issuance.

## Command

```text
dayu-cli write --ticker AAPL \
  --revoke-write-model-configuration-manual-recovery-clearance \
  --challenger-config-manual-recovery-clearance-revocation-receipt-input \
    <recovery-receipt.json> \
  --challenger-config-manual-recovery-clearance-revocation-clearance-input \
    <clearance.json> \
  --challenger-config-manual-recovery-clearance-revocation-request \
    <revocation-request.json> \
  --challenger-config-manual-recovery-clearance-revocation-output \
    <revocation.json>
```

All five options are required. The mode cannot be combined with normal writes,
summary, preflight, routing or model overrides, Challenger operations,
configuration application, rollback, or any other manual recovery control.
It exits before execution-option or Host construction.

## Issuance checks

Under the shared configuration-root transaction lock, revocation:

1. Requires the supplied receipt to be byte-identical to the latest internal
   recovery receipt with status `recovered`.
2. Requires an authoritative internal clearance for the same transaction.
3. Requires the supplied clearance to be byte-identical to that authoritative
   internal clearance.
4. Revalidates the normal-write gate as `cleared`.
5. Binds ticker, transaction, receipt fingerprint, clearance fingerprint,
   operator, reason, reference, timestamp, and exact source files.
6. Persists the internal revocation before exporting the requested copy.

The authoritative path is:

```text
workspace/.dayu/
  write-model-configuration-manual-recovery-clearance-revocations/
    <transaction-id>.json
```

An identical retry can re-export the immutable record after the four-hour
window. Different content cannot replace it. A malformed, tampered, unreadable,
or symlinked internal revocation fails closed.

## Gate behavior

Gate schema
`write_model_configuration_manual_recovery_gate_v4` reports:

```text
status = clearance_revoked
clearance_present = true
clearance_revoked = true
normal_write_allowed = false
```

It binds both the clearance and revocation fingerprints and paths. The
read-only gate check returns `4` for a valid revoked clearance. Corrupt
revocation evidence returns `6`. Normal writes stop before approval
consumption, Host construction, preflight, or model execution.

Every gate v4 result also records `assessed_at`, lineage presence/status, and
a fingerprint over the complete result. The dedicated check can immutably
export that exact blocked result outside the configuration root with
`--challenger-config-manual-recovery-gate-output`.

A newer manual recovery transaction supersedes an older revocation because
the gate evaluates only the latest internal recovery transaction. That newer
transaction remains blocked as `clearance_required` until it receives its own
valid clearance.

## Starting the required newer recovery transaction

Use the dedicated read-only bridge instead of manually locating the original
rollback receipt inside nested evidence:

```text
dayu-cli write --ticker AAPL \
  --restart-write-model-configuration-manual-recovery-after-clearance-revocation \
  --challenger-config-manual-recovery-restart-receipt-input \
    <latest-recovery-receipt.json> \
  --challenger-config-manual-recovery-restart-clearance-input \
    <authoritative-clearance.json> \
  --challenger-config-manual-recovery-restart-revocation-input \
    <authoritative-revocation.json> \
  --challenger-config-manual-recovery-restart-evidence-output \
    <new-recovery-evidence.json>
```

Under the shared configuration lock, the bridge requires the current gate to
remain `clearance_revoked`, compares all three supplied artifacts with the
latest internal receipt, clearance, and revocation byte for byte, validates
their complete current source chains, and follows
`source_manual_recovery_evidence` to the exact original
`source_rollback_receipt`. It then invokes the existing read-only evidence
builder and exports fresh
`write_model_configuration_manual_recovery_evidence_v2`.

The output can be passed directly to the existing human selection and
manual-recovery planning commands. The bridge does not remove the revocation:
normal writes remain blocked until that evidence leads to a newer recovered
transaction and a new clearance for that transaction. It does not select a
state, issue or consume approval, modify configuration, construct Host
dependencies, or call a model.

The v2 evidence embeds strict `clearance_revocation_lineage`. Human-authored
selection and approval requests must copy that object exactly into their v2
schemas. Plans, issued approvals, intents, approval consumption, receipts, and
verification then carry the same lineage unchanged and recheck its
authoritative source files. Ordinary failed-rollback recovery remains on the
strict v1 schemas. See
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-restart.md`
and
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-revocation-lineage-v2.md`.

## Exit codes

| Exit | Meaning |
|---:|---|
| `0` | Revocation was recorded, or the identical internal revocation was re-exported. |
| `2` | Path, JSON, schema, timestamp, or ordinary input failure. |
| `4` | Receipt or clearance identity is not current and exact, no open clearance exists, or the shared lock is busy. |
| `6` | Revocation is recorded internally but cannot be exported. |

## Safety properties

- Revocation only removes normal-write authority.
- Revocation cannot be reversed for the same recovery transaction.
- Internal persistence occurs before external export.
- Current configuration files and model routing are unchanged.
- No recovery or Challenger approval is consumed.
- No model, preflight, write pipeline, or Host dependency is started.
