# Write-model configuration manual recovery audit timeline v1

## Goal

Provide one supported, read-only view of the complete authoritative manual
recovery history and the current normal-write gate.

The timeline closes an operational gap between individual receipts and the
latest gate. It does not create, extend, or imply normal-write authority.

## Command

```text
dayu-cli write --ticker AAPL \
  --audit-write-model-configuration-manual-recovery-history
```

An optional immutable snapshot may be written outside configuration and the
authoritative `.dayu` evidence root:

```text
  --challenger-config-manual-recovery-audit-timeline-output \
    <audit/manual-recovery-audit-timeline.json>
```

The mode is mutually exclusive with every write, preflight, routing, model
override, Challenger, and other manual-recovery operation.

## Authoritative inputs

The audit reads:

```text
<workspace>/.dayu/write-model-configuration-manual-recoveries/transactions
<workspace>/.dayu/write-model-configuration-manual-recovery-clearances
<workspace>/.dayu/write-model-configuration-manual-recovery-clearance-revocations
```

Each complete transaction contributes its strict `receipt.json`. A
transaction directory without a receipt is retained in
`incomplete_transaction_ids`. Clearance and revocation roots may contain only
regular, non-symlink `.json` files whose file name exactly matches their
embedded transaction identity.

Unexpected entries, symlink ancestors, malformed JSON, invalid strict
schemas, or file/payload identity mismatches fail closed.

## Locking and race detection

The command acquires the shared write-model configuration transaction lock
before reading history.

Under that one lock it:

1. scans and validates all three authoritative roots;
2. runs the existing locked gate-v4 assessment;
3. scans and validates all three roots again; and
4. compares the complete first and second states.

The comparison includes paths, embedded payloads, exact file-byte
fingerprints, event ordering, evidence roots, and incomplete transaction IDs.
Any difference aborts the audit. The lock is always released.

## Timeline contract

Every result uses:

```text
schema_version =
  write_model_configuration_manual_recovery_audit_timeline_v1
```

Top-level fields:

```text
generated_at
ticker
evidence_roots
current_gate
events
receipt_count
clearance_count
revocation_count
incomplete_transaction_ids
history_complete
normal_write_authorization_granted
configuration_mutation_performed
approval_consumed
model_execution_performed
timeline_fingerprint
```

`current_gate` is a complete strict
`write_model_configuration_manual_recovery_gate_v4` payload assessed at the
same `generated_at`.

Each event contains:

```text
sequence
event_type
event_at
transaction_id
artifact_path
artifact_file_fingerprint
artifact_content_fingerprint
artifact
```

Supported event types:

```text
manual_recovery_receipt
manual_recovery_clearance
manual_recovery_clearance_revocation
```

The embedded artifact is the complete strict internal payload. The file
fingerprint covers the exact authoritative bytes read by the audit. The
content fingerprint is the artifact's own receipt, clearance, or revocation
fingerprint.

Events are ordered by UTC event time, artifact type, and transaction ID, then
assigned a contiguous sequence beginning at one.

## Cross-artifact validation

The timeline validator requires:

- one receipt, clearance, and revocation at most per transaction;
- no clearance without a matching recovered receipt;
- no revocation without the matching receipt and clearance;
- exact ticker and transaction identity across each chain;
- exact receipt and clearance fingerprints across linked artifacts;
- exact authoritative source path and file fingerprint links;
- clearance routing identity equal to the receipt's expected recovered
  routing snapshot;
- clearance time strictly after recovery completion;
- revocation time strictly after clearance issuance;
- identical clearance-revocation lineage where lineage v2 applies;
- counts equal to the embedded events; and
- sorted, unique incomplete transaction IDs that have no completed receipt.

The current gate must agree with the complete history about the latest
transaction, receipt status and fingerprint, clearance, revocation, lineage,
reason codes, paths, and fingerprints.

## Integrity and authority

`timeline_fingerprint` seals every timeline field except itself. Nested
artifacts and the gate retain their own fingerprints.

These SHA-256 fingerprints provide deterministic integrity checks. They are
not public-key signatures, do not identify an operator, and do not establish
authority independently of the local authoritative roots.

Immutable export rechecks the target before accepting existing content and
after atomic-link creation or collision. If the target is observed as a
symlink during that interval, export fails rather than treating it as an
idempotent artifact.

## Exit codes

```text
0  a strict timeline was generated, regardless of embedded gate status
2  missing config root or invalid, unsafe, or colliding export path
4  busy configuration lock or internal history changed during the audit
6  malformed, unsafe, orphaned, or semantically inconsistent evidence
```

Exit `0` never means normal writes are allowed. Operators must inspect
`current_gate.normal_write_allowed`, and normal writes still pass through the
existing gate and all ordinary preflight and approval controls.

## Side-effect boundary

The audit and optional export:

- do not modify routing or model configuration;
- do not issue, consume, revoke, or replace an approval;
- do not issue, revoke, replace, or remove a clearance;
- do not modify any authoritative recovery artifact;
- do not construct Host dependencies;
- do not invoke DeepSeek, MiMo, or any other model; and
- do not authorize a normal write.

Only the explicit timeline-output option creates an immutable external audit
artifact.
