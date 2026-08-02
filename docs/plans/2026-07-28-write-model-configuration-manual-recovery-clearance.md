# Write-model configuration manual recovery clearance

## Goal

Close one successfully recovered routing incident through a separate,
explicit, independently attributable decision. The resulting immutable
clearance reopens normal write preflight without changing configuration,
consuming an approval, calling a model, or starting a write run.

Read-only receipt verification is necessary but not sufficient. A `current`
verification makes an incident eligible for clearance; only a valid clearance
for the latest internal recovery transaction opens the normal-write gate.

## Clearance request

Create a
`write_model_configuration_manual_recovery_clearance_request_v1` object:

```json
{
  "schema_version": "write_model_configuration_manual_recovery_clearance_request_v1",
  "clearance_type": "write_scene_model_routing_manual_recovery",
  "scope": "close_one_verified_manual_recovery_incident",
  "ticker": "AAPL",
  "transaction_id": "<transaction id from recovery receipt>",
  "manual_recovery_receipt_fingerprint": "sha256:<receipt fingerprint>",
  "cleared_by": "clearer@example.com",
  "clearance_reference": "CAB-CLOSE-2026-0728",
  "clearance_reason": "Current routing and exact recovered bytes were independently reviewed.",
  "cleared_at": "2026-07-28T08:30:00Z",
  "acknowledgements": [
    "reviewed_manual_recovery_receipt_and_current_verification",
    "recovery_receipt_is_latest_internal_transaction",
    "current_verification_status_is_current",
    "clearance_closes_only_this_recovery_incident",
    "clearance_does_not_modify_configuration",
    "clearance_does_not_consume_approval",
    "clearance_does_not_execute_models",
    "normal_writes_still_require_normal_preflight"
  ]
}
```

`cleared_by` must differ case-insensitively from both the state selector and
manual recovery approver. `cleared_at` must follow the recovery receipt, must
not be in the future, and may be at most four hours old when issued.

The request above is for an ordinary v1 recovery receipt. A recovery restarted
after clearance revocation produces a v2 receipt. Its request must use
`write_model_configuration_manual_recovery_clearance_request_v2`, copy the
receipt's exact `clearance_revocation_lineage`, and append
`reviewed_exact_clearance_revocation_lineage` to `acknowledgements`. Issuance
then creates `write_model_configuration_manual_recovery_clearance_v2` with the
same lineage. Mixed versions are rejected. See
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-clearance-lineage-v2.md`.

## Command

```text
dayu-cli write --ticker AAPL \
  --clear-write-model-configuration-manual-recovery \
  --challenger-config-manual-recovery-clearance-receipt-input \
    <recovery-receipt.json> \
  --challenger-config-manual-recovery-clearance-request \
    <clearance-request.json> \
  --challenger-config-manual-recovery-clearance-output \
    <clearance.json>
```

All four options are required. This is a dedicated mode and cannot be mixed
with normal writes, preflight, summary, routing overrides, Challenger
operations, configuration application, rollback, recovery planning, approval,
execution, or read-only verification.

## Issuance checks

Under the shared configuration-root transaction lock, issuance:

1. Loads the externally supplied receipt and discovers all authoritative
   internal manual recovery transactions.
2. Fails closed on an incomplete internal transaction or an unsafe,
   malformed, or fingerprint-invalid receipt.
3. Requires the supplied receipt to be byte-identical to the latest internal
   receipt and requires that receipt to have status `recovered`.
4. Checks the request ticker, transaction ID, receipt fingerprint, timestamp,
   acknowledgements, and independent operator identity.
5. Replays the complete receipt source chain and observes exact target bytes.
6. Builds a fresh complete runtime routing snapshot and requires verification
   status `current`.
7. Writes the internal clearance immutably, then exports the same artifact to
   the requested output path.

For v2, issuance also requires exact lineage equality among the request,
receipt, and fresh verification, and reloads all three authoritative lineage
sources before persistence.

The authoritative internal artifacts are:

```text
workspace/.dayu/
  write-model-configuration-manual-recoveries/
    transactions/<transaction-id>/receipt.json
  write-model-configuration-manual-recovery-clearances/
    <transaction-id>.json
```

An identical retry may re-export an existing internal clearance. The
four-hour request window applies to first issuance; an exact re-export may
occur later because it neither creates a new clearance nor reruns routing or
model work. Different content cannot replace the internal record. A newer
recovery transaction automatically makes an older clearance irrelevant
because the gate only accepts clearance bound to the latest internal receipt.

The shared immutable writer rechecks each target for symlink replacement
before accepting existing content and after atomic-link creation or
collision. This applies to internal clearance and revocation receipts as well
as external Gate, verification, and timeline exports.

## Exit codes

| Exit | Meaning |
|---:|---|
| `0` | The latest recovered incident was freshly verified and cleared, or its identical existing internal clearance was re-exported. |
| `2` | Request, path, JSON, schema, timestamp, or ordinary input failure. |
| `4` | The latest transaction is not recoverable for clearance, evidence or routing changed, the operator is not independent, or the shared lock is busy. |
| `6` | Clearance is already recorded internally but cannot be exported to the requested path. |

## Normal-write gate

Before any normal non-summary write or preflight command can consume a
Challenger approval, construct Host dependencies, or call a model, the gate
examines the internal transaction history under the shared lock. Its
ephemeral result uses
`write_model_configuration_manual_recovery_gate_v4` and binds every status
to the command ticker, assessment time, lineage status, and full-result
fingerprint:

| Gate status | Normal write | Meaning |
|---|---|---|
| `not_required` | Allowed | No manual recovery transaction exists. |
| `cleared` | Allowed | The latest receipt is `recovered` and has an exact valid clearance. |
| `clearance_required` | Blocked | The latest receipt is `recovered`, but no clearance exists. |
| `clearance_revoked` | Blocked | The latest exact clearance has an immutable revocation. A newer recovery transaction is required. |
| `manual_recovery_required` | Blocked | A transaction is incomplete, restored only its starting state, or records an unproven final state. |

Malformed, tampered, unsafe, or unreadable internal evidence fails closed.
For a `cleared` result, the gate also rechecks that:

- the latest receipt ticker matches the command ticker;
- the clearance routing fingerprint equals the recovered receipt's expected
  selected-routing fingerprint;
- `cleared_at` follows the receipt's `completed_at`;
- the bound recovery plan and approval paths, file fingerprints, and content
  fingerprints remain exact; and
- the clearance operator still differs case-insensitively from both the
  selector and approver.

For every v2 receipt-backed result, the gate reloads the authoritative revoked
receipt, prior clearance, and revocation before returning. This includes
`clearance_required`, so source drift fails closed before a new clearance is
issued. When a v2 clearance exists, the gate also requires exact lineage
equality between receipt and clearance.

The gate itself performs no configuration mutation, approval consumption,
Host construction, or model execution.

An operator can immutably revoke a valid latest clearance. The revocation
immediately changes the gate to `clearance_revoked`; re-exporting or reissuing
the same clearance cannot reopen it. See
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-clearance-revocation.md`
for the request schema, dedicated command, and exit codes.

Read-only `write --summary` remains available during an incident. Dedicated
configuration application, operator rollback, evidence export, recovery
planning, approval, execution, verification, and clearance modes remain
available so operators can resolve the incident.

## Read-only gate check

Operators can inspect the same fail-closed gate without entering normal
preflight:

```text
dayu-cli write --ticker AAPL \
  --check-write-model-configuration-manual-recovery-gate
```

An operator may also export the exact timestamped and fingerprinted result:

```text
dayu-cli write --ticker AAPL \
  --check-write-model-configuration-manual-recovery-gate \
  --challenger-config-manual-recovery-gate-output \
    <audit/manual-recovery-gate.json>
```

This dedicated mode cannot be combined with any recovery artifact operation,
summary, preflight, routing or model override, Challenger operation,
configuration application, rollback, or partial write option. It exits before
execution-option construction, Host dependency construction, approval
consumption, or model work. Audit output must be outside the configuration
root. Identical content may be re-exported idempotently; different content
cannot replace an existing artifact. A valid blocked result is exported before
exit `4`. Ordinary write gate checks do not create audit files.

| Exit | Meaning |
|---:|---|
| `0` | Gate status is `not_required` or `cleared`; normal controls may continue. |
| `2` | No configuration root is available, or the requested audit output path is invalid, collides, or cannot be written. |
| `4` | A valid incident remains blocked, including a revoked clearance, or the shared configuration lock is busy. |
| `6` | Internal evidence is malformed, unsafe, unreadable, or semantically inconsistent and requires intervention. |

## Safety properties

- Verification and clearance are separate operator actions.
- The selector, recovery approver, and clearance operator are three
  independent identities.
- Clearance is bound to one exact latest receipt and fresh full routing
  snapshot.
- Clearance cannot replace normal write preflight or Challenger approvals.
- Incomplete and non-recovered transactions cannot be cleared.
- Internal clearance is persisted before external export.
- No configuration, model catalog, run configuration, secret, or environment
  variable is modified.
- No approval is consumed and no model is called.
