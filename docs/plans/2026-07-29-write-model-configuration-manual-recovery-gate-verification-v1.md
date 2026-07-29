# Write-model configuration manual recovery gate verification v1

## Goal

Provide a supported, read-only way to decide whether one explicitly exported
manual recovery gate v4 snapshot still describes the current local gate state.

The verifier is an audit tool. It does not turn a gate snapshot into an
authorization artifact and does not bypass any normal write control.

## Command

```text
dayu-cli write --ticker AAPL \
  --verify-write-model-configuration-manual-recovery-gate \
  --challenger-config-manual-recovery-gate-input \
    <audit/manual-recovery-gate.json>
```

An optional immutable receipt may be written outside the configuration root:

```text
  --challenger-config-manual-recovery-gate-verification-output \
    <audit/manual-recovery-gate-verification.json>
```

The verification mode is mutually exclusive with gate assessment, recovery,
clearance, revocation, restart, write, preflight, routing, model override, and
Challenger operations.

## Contract

Every result uses:

```text
schema_version =
  write_model_configuration_manual_recovery_gate_verification_v1
```

The result contains:

```text
verified_at
ticker
status
action
source_gate_path
source_gate_file_fingerprint
source_gate
current_gate
source_state_fingerprint
current_state_fingerprint
state_matches
changed_fields
reason_codes
normal_write_authorization_granted
configuration_mutation_performed
approval_consumed
model_execution_performed
verification_fingerprint
```

Both embedded gates are complete strict v4 payloads. The verification
fingerprint seals every result field except itself.

## Source identity and stability

The source snapshot:

1. must be a regular UTF-8 JSON file;
2. must not be a symlink;
3. must be outside the configuration root by both lexical and resolved path;
4. must pass the complete gate v4 schema and fingerprint validation;
5. must match the command ticker; and
6. must not have an assessment time later than verification time.

The verifier hashes the exact source bytes, obtains a fresh local gate
assessment, and reads the source again. A changed path, changed bytes,
disappearing file, malformed replacement, or unsafe replacement fails closed
instead of producing a comparison receipt.

## Semantic comparison

The stable gate state contains every gate v4 field except:

```text
assessed_at
gate_fingerprint
```

Those fields identify each assessment and naturally change when the same state
is assessed later. All status, action, receipt, clearance, revocation, lineage,
reason, and safety fields remain part of the semantic comparison.

Each stable state is canonically serialized and SHA-256 fingerprinted.
`changed_fields` is the sorted list of top-level semantic fields whose values
differ.

## Status

```text
current
  source and current semantic-state fingerprints match
  action = historical_gate_matches_current_state

stale
  one or more semantic fields changed
  action = use_current_gate_assessment
```

`current` returns exit `0`. `stale` returns exit `4`.

Neither status grants normal-write authorization. In particular, an embedded
current gate may report `normal_write_allowed = true`, but the verification
receipt still records:

```text
normal_write_authorization_granted = false
```

Normal writes must run the ordinary live gate and every existing preflight,
approval, and execution control.

## Exit codes

```text
0  source semantic state matches the fresh local assessment
2  malformed or unsafe external input, or invalid/colliding output
4  stale state, source changed during verification, or lock busy
6  fresh current internal gate evidence is malformed or inconsistent
```

## Integrity and authority

The source-file, semantic-state, gate, and verification SHA-256 fingerprints
provide deterministic integrity checks. They are not public-key signatures,
do not identify an operator, and do not independently establish artifact
authority.

The current local assessment remains the source of truth.

## Side-effect boundary

Verification and optional receipt export:

- do not modify routing or model configuration;
- do not issue, consume, revoke, or replace an approval;
- do not issue, revoke, or replace a clearance;
- do not construct Host dependencies;
- do not invoke a model; and
- do not authorize a normal write.

Only the explicit verification-output option creates an audit artifact.

## Saved receipt revalidation

A saved verification receipt can later be checked against both its exact
bound gate snapshot and a new local assessment through the dedicated
revalidation mode. The revalidator also reads the saved receipt again after
the fresh assessment to detect concurrent replacement.

The command, strict nested contract, statuses, and side-effect boundary are
documented in
`2026-07-29-write-model-configuration-manual-recovery-gate-verification-revalidation-v1.md`.
