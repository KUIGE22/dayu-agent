# Write-model configuration manual recovery verification

## Goal

Independently verify an immutable manual recovery receipt against its complete
evidence chain and the current configuration before an independent operator
issues durable normal-write clearance.

Verification is read-only. It does not modify configuration, consume an
approval, write clearance, call a model, or start a write run.

## Command

```text
dayu-cli write --ticker AAPL \
  --verify-write-model-configuration-manual-recovery \
  --challenger-config-manual-recovery-verification-receipt-input \
    <recovery-receipt.json>
```

This is a dedicated mode. It cannot be combined with normal writes, routing
overrides, preflight, configuration application, rollback, evidence export,
manual recovery planning, approval issuance, or recovery execution.

## Evidence chain

Under the shared configuration-root transaction lock, verification checks:

1. The recovery receipt and every referenced artifact are immutable and have
   the recorded file and content fingerprints.
2. The plan, evidence, human selection, approval request, approval,
   single-use consumption record, and write-ahead intent all bind the same
   transaction and exact operation set.
3. Selection and approval identities, normalized timestamps, transaction ID,
   and consumption time are internally consistent.
4. Every target path remains confined to `prompts/manifests`, is not a
   symlink, and has stable bytes across repeated observations.

For a `recovered` receipt only, the command then builds a fresh complete
`write_scene_model_routing_snapshot_v1`. It observes target bytes once more
after that preflight and compares the full snapshot fingerprint with the
receipt.

For `starting_state_restored` and `recovery_failed`, no fresh preflight or Host
construction occurs. The starting configuration may be invalid, so only the
immutable chain and current target bytes are inspected.

## Results

| Verification status | Exit | Operator action |
|---|---:|---|
| `current` | `0` | The selected bytes and full runtime routing snapshot still match. The incident is eligible for a separate clearance decision; writes remain gated. |
| `routing_changed` | `4` | Selected target bytes or another full-routing input changed. Stop and review the current configuration. |
| `starting_state_current` | `4` | The transaction safely restored its exact starting bytes. Export new manual recovery evidence before another attempt. |
| `starting_state_changed` | `6` | Bytes changed after the starting-state receipt. Stop for manual intervention. |
| `manual_recovery_required` | `6` | The receipt records an unproven final state. Stop for manual intervention. |

Malformed receipt JSON and ordinary artifact I/O errors return `2`.
Fingerprint drift, source-chain mismatch, a busy transaction lock, or a
failed fresh routing gate returns `4`.

## Safety properties

- Verification never writes a recovery receipt or changes a manifest.
- Verification never consumes or reuses an approval.
- Verification never writes normal-write clearance.
- Verification never runs a model.
- Only `current` makes the incident eligible for independent clearance.
- Normal write preflight remains blocked until the latest recovery transaction
  has a valid durable clearance.
- `starting_state_current` is safe evidence of restoration, not authorization
  to resume writes.
- A changed source artifact blocks verification instead of being silently
  replaced by current data.

The clearance protocol is documented in
`docs/plans/2026-07-28-write-model-configuration-manual-recovery-clearance.md`.
