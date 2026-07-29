# Write-model configuration manual recovery gate v4

## Goal

Turn the read-only manual recovery gate result into an auditable snapshot
without changing its authority or side-effect boundary.

Gate v4 records when the assessment happened, carries the complete revoked
clearance lineage when the latest receipt has one, and seals the complete
result with a SHA-256 fingerprint. Operators may explicitly export that
snapshot outside the configuration root.

## Contract

Every result uses:

```text
schema_version = write_model_configuration_manual_recovery_gate_v4
```

It retains all v3 status, action, receipt, clearance, revocation, reason, and
safety fields and adds:

```text
assessed_at
clearance_revocation_lineage
clearance_revocation_lineage_status
gate_fingerprint
```

`assessed_at` is a timezone-aware UTC timestamp. The lineage status is:

```text
not_applicable  latest receipt has no revoked-clearance lineage
current         complete lineage was structurally validated and its
                authoritative sources were current at assessed_at
```

The gate never emits a lineage status of `current` without embedding the
complete lineage object.

## Integrity

`gate_fingerprint` is the canonical SHA-256 fingerprint of every gate field
except `gate_fingerprint` itself. Validation is strict:

1. No missing or extra fields are accepted.
2. The assessment timestamp must be timezone-aware.
3. Embedded lineage must pass its strict schema and fingerprint validation.
4. Lineage status and presence must agree.
5. Gate ticker and lineage ticker must agree.
6. Existing status-dependent paths, fingerprints, and safety flags must agree.
7. The final gate fingerprint must match the complete unsigned payload.

This is an integrity fingerprint, not a public-key signature.

## Current-lineage assessment

After loading the latest complete receipt, the gate extracts its
`clearance_revocation_lineage` and replays the authoritative source checks
before returning any receipt-backed status.

This includes:

```text
manual_recovery_required
clearance_required
cleared
clearance_revoked
```

For a v2 recovered receipt, source drift therefore fails closed even before a
new clearance exists. If a clearance exists, exact lineage equality between
the receipt and clearance remains mandatory.

No-receipt and incomplete-transaction results have no lineage and use
`not_applicable`.

## Stable transaction assessment time

Internal workflows may assess the gate twice under one configuration
transaction lock. They pass one normalized timestamp to both assessments.
The timestamp and gate fingerprint therefore remain equal when all
authoritative state remains equal; a real state change still changes the
result.

## Optional immutable export

The dedicated read-only command may export the exact gate snapshot:

```text
dayu-cli write --ticker AAPL \
  --check-write-model-configuration-manual-recovery-gate \
  --challenger-config-manual-recovery-gate-output \
    <audit/manual-recovery-gate.json>
```

The output:

- must be outside the configuration root;
- must not be a symlink;
- is written with the existing immutable artifact writer;
- may be re-exported idempotently only when content is identical; and
- cannot be replaced with a different assessment.

A valid blocked gate is exported before the command returns exit `4`, so the
operator retains evidence of the blocking decision. Output path and collision
errors return exit `2`. Internal gate evidence corruption still returns exit
`6`.

The output option is invalid without the dedicated gate-check flag.

## Side-effect boundary

Gate assessment and export:

- do not modify model or routing configuration;
- do not consume an approval;
- do not construct Host dependencies;
- do not invoke a model;
- do not issue, revoke, or replace a clearance; and
- do not create audit files during ordinary normal-write gate checks.

Only the explicit output option writes the exported audit artifact.

## Compatibility

The gate itself is ephemeral unless explicitly exported, so newly generated
results move directly from v3 to strict v4. Existing v1 recovery receipts
remain valid and produce `not_applicable` lineage. Existing v2 receipts expose
and revalidate their full lineage.

## Independent verification

An explicitly exported v4 snapshot can be compared with a fresh local
assessment through the dedicated verification mode. That comparison excludes
only `assessed_at` and `gate_fingerprint` from semantic state, binds the exact
source-file bytes, detects source changes during assessment, and may emit an
immutable self-contained verification receipt.

The verification contract and CLI are documented in
`2026-07-29-write-model-configuration-manual-recovery-gate-verification-v1.md`.

## Complete history audit

The gate summarizes the latest controlling state. Operators who need the
complete receipt, clearance, revocation, and incomplete-transaction history
can use the dedicated strict audit timeline. It embeds a fresh gate v4 result
and validates that result against every authoritative internal artifact.

The timeline contract and CLI are documented in
`2026-07-29-write-model-configuration-manual-recovery-audit-timeline-v1.md`.
