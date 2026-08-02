# Write-model configuration manual recovery gate verification revalidation v1

## Goal

Provide a supported, read-only way to determine whether one saved gate
verification receipt, its exact source gate snapshot, and the gate state it
observed still agree with a fresh local assessment.

Revalidation checks liveness of audit evidence. It does not create or extend
normal-write authority.

## Command

```text
dayu-cli write --ticker AAPL \
  --revalidate-write-model-configuration-manual-recovery-gate-verification \
  --challenger-config-manual-recovery-gate-verification-input \
    <audit/manual-recovery-gate-verification.json>
```

An optional immutable receipt may be written outside the configuration root:

```text
  --challenger-config-manual-recovery-gate-verification-revalidation-output \
    <audit/manual-recovery-gate-verification-revalidation.json>
```

Revalidation export rejects a symlink target before persistence, rechecks the
target before existing-content acceptance and around atomic-link creation,
and fails if the target becomes a symlink during that interval.

The mode is mutually exclusive with every write, preflight, routing, model
override, Challenger, manual recovery, gate check, and gate verification
operation.

## Contract

Every result uses:

```text
schema_version =
  write_model_configuration_manual_recovery_gate_
  verification_revalidation_v1
```

The result contains:

```text
revalidated_at
ticker
status
action
source_verification_path
source_verification_file_fingerprint
source_verification
fresh_verification
saved_current_state_fingerprint
fresh_current_state_fingerprint
state_matches
changed_fields
reason_codes
normal_write_authorization_granted
configuration_mutation_performed
approval_consumed
model_execution_performed
revalidation_fingerprint
```

Both nested verification objects are complete strict
`write_model_configuration_manual_recovery_gate_verification_v1` payloads.
The revalidation fingerprint seals every result field except itself.

## Revalidation sequence

1. Load a regular, non-symlink verification receipt outside the configuration
   root.
2. Validate its exact schema, nested gates, semantic fingerprints, safety
   fields, and final verification fingerprint.
3. Hash the exact verification-receipt bytes and reject a future timestamp or
   ticker mismatch.
4. Re-run the existing gate-snapshot verifier using the exact
   `source_gate_path` recorded in the saved receipt.
5. Require the fresh source path, source-file fingerprint, and complete source
   gate to equal the saved receipt.
6. Read the verification receipt again and fail if its path, bytes, or payload
   changed while the fresh assessment ran.
7. Compare the saved and fresh `current_gate` semantic states.

The existing gate verifier independently reads the bound gate before and after
the local assessment. Revalidation therefore detects concurrent replacement
of either external input.

## Semantic comparison

Every strict gate v4 field participates except:

```text
assessed_at
gate_fingerprint
```

Those two fields identify a particular assessment. All status, action,
receipt, clearance, revocation, lineage, reason, and safety fields remain
significant. `changed_fields` is the sorted list of changed top-level semantic
fields.

## Status

```text
current
  saved current-gate state matches the fresh current-gate state
  action = saved_verification_matches_current_gate_state

stale
  one or more semantic gate fields changed
  action = repeat_gate_snapshot_verification
```

The nested source verification may itself have status `current` or `stale`.
A revalidation status of `current` means only that the saved verification
still accurately describes today's gate state relative to its unchanged
source snapshot.

It does not mean that normal writes are allowed.

## Exit codes

```text
0  saved verification still matches the fresh local gate state
2  malformed or unsafe external input, or invalid/colliding output
4  stale state, changed bound input, or busy configuration lock
6  fresh current internal gate evidence is malformed or inconsistent
```

## Integrity and authority

The exact verification-file, bound gate-file, semantic-state, nested
verification, and revalidation SHA-256 fingerprints provide deterministic
integrity checks. They are not public-key signatures, do not identify an
operator, and do not independently establish artifact authority.

The fresh local gate assessment remains the source of truth.

## Side-effect boundary

Revalidation and optional receipt export:

- do not modify routing or model configuration;
- do not issue, consume, revoke, or replace an approval;
- do not issue, revoke, or replace a clearance;
- do not construct Host dependencies;
- do not invoke a model; and
- do not authorize a normal write.

Only the explicit revalidation-output option creates an audit artifact.
