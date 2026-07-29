# Restart Manual Recovery After Clearance Revocation

## Goal

Make the revocation contract operationally complete. A
`clearance_revoked` gate says that only a newer manual recovery transaction
and its own clearance may reopen normal writes. This command deterministically
finds the original `recovery_failed` rollback receipt through the latest
recovered transaction's evidence chain and exports fresh v2 manual recovery
evidence bound to the exact revoked clearance lineage.

The command is read-only with respect to configuration and internal incident
state. It does not remove revocation, select a recovery state, issue or consume
approval, construct Host dependencies, start a write run, or call a model.

## Command

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

All five options are required. This is a dedicated mode and cannot be combined
with normal writes, summaries, preflight, routing or model overrides,
Challenger operations, configuration application or rollback, another manual
recovery control, or research materialization. It exits before execution
options and Host dependencies are built.

## Validation

All checks occur while holding the shared configuration-root transaction lock:

1. The gate must currently be `clearance_revoked`.
2. The supplied recovered receipt must be byte-identical to the latest
   internal manual recovery receipt.
3. The supplied clearance must be byte-identical to the authoritative
   internal clearance for that transaction.
4. The supplied revocation must be byte-identical to the authoritative
   internal revocation for that transaction.
5. The recovered receipt's bound `source_manual_recovery_evidence` path, file
   fingerprint, and evidence fingerprint must remain exact.
6. That evidence's bound `source_rollback_receipt` path, file fingerprint, and
   receipt fingerprint must remain exact.
7. The original rollback receipt must still have status `recovery_failed`, and
   the existing evidence builder must validate its complete plan, approval,
   application-receipt, consumption, intent, and current-target chain.
8. Current target bytes are observed twice by the existing builder.
9. The revoked gate, all supplied artifacts, and both source artifacts are
   checked again before immutable output persistence.
10. The output binds the authoritative receipt, clearance, and revocation
    sources in one strict `clearance_revocation_lineage` object whose
    fingerprint is independently verified by every downstream v2 boundary.

Inputs and output must be regular non-symlink paths outside the configuration
root. The authoritative internal paths are also checked for symlink
components.

## Output and next steps

The output is the strict restart schema:

```text
write_model_configuration_manual_recovery_evidence_v2
```

It contains the normal failed-rollback evidence plus
`clearance_revocation_lineage`. It is immediately consumable by the existing
commands, but human-authored selection and approval requests must use their
v2 schemas and copy that lineage object exactly:

```text
evidence_v2
  -> selection_request_v2
  -> plan_v2
  -> approval_request_v2
  -> approval_v2
  -> intent_v2
  -> consumption_v2
  -> receipt_v2
  -> verification_v2
  -> clearance_request_v2
  -> clearance_v2
```

The old revocation remains authoritative while these steps run. Only a newer
internal manual recovery receipt can supersede it, and that newer receipt
still leaves normal writes blocked until its own valid clearance exists.
Every build, currentness, execution, recovery, and verification boundary
requires byte-for-byte lineage equality. Currentness checks reload the three
authoritative source artifacts and verify their file and content fingerprints,
statuses, transaction relationships, and lineage fingerprint.

Clearance issuance keeps the same version boundary. Its human-authored v2
request copies the exact lineage from the recovered receipt, the generated v2
clearance preserves it, and every subsequent normal-write gate check reloads
the authoritative lineage sources.

## Exit codes

| Exit | Meaning |
|---:|---|
| `0` | Fresh standard manual recovery evidence was exported. |
| `2` | A path, JSON, schema, output collision, or ordinary I/O input failed. |
| `4` | The gate is not revoked, an artifact or source identity changed, current bytes drifted, or the configuration lock is busy. |

## Version boundary

The revoked-clearance restart always enters the coordinated v2 chain. A v2
artifact cannot omit `clearance_revocation_lineage`, and a v1 artifact cannot
add it. This keeps both contracts strict and prevents a partially upgraded
chain.

Ordinary manual recovery that starts directly from a `recovery_failed`
operator-rollback receipt remains fully compatible with the v1 evidence,
selection, plan, approval, execution, receipt, and verification schemas. See
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-revocation-lineage-v2.md`
for the complete nested schema and operator-authored request requirements.

## Safety properties

- Revocation remains immutable and normal writes remain blocked.
- No recovery state is selected automatically.
- No configuration file is changed.
- No new approval is issued or consumed.
- No internal clearance or revocation artifact is modified.
- No execution options, Host dependencies, preflight, write pipeline, or
  model call is started.
- The exact revocation identity remains bound through independent
  verification of the newer recovery receipt.
- The existing recovery workflow remains the only path that can create the
  newer transaction required by the gate.
