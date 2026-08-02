# Write-model configuration manual recovery incident dossier revalidation v1

## Goal

Revalidate one saved manual-recovery incident dossier against the current
strict internal recovery history.

The incident dossier is a self-contained evidence projection. Revalidation
answers whether that saved projection still matches the current semantic
incident state. It does not authorize a normal write, reopen a gate, issue a
clearance, consume an approval, mutate configuration, construct Host
dependencies, or call a model.

## Command

```text
dayu-cli write --ticker AAPL \
  --revalidate-write-model-configuration-manual-recovery-incident-dossier \
  --challenger-config-manual-recovery-incident-dossier-input \
    <audit/manual-recovery-incident-dossier.json>
```

To retain the self-contained revalidation receipt, add:

```text
  --challenger-config-manual-recovery-incident-dossier-revalidation-output \
    <audit/manual-recovery-incident-dossier-revalidation.json>
```

The mode is mutually exclusive with every write, preflight, routing, model
override, Challenger, manual recovery, gate check, gate verification, history
audit, and incident-inspection operation.

## Contract

Every result uses:

```text
write_model_configuration_manual_recovery_incident_dossier_revalidation_v1
```

Top-level fields:

```text
revalidated_at
ticker
transaction_id
status
action
source_dossier_path
source_dossier_file_fingerprint
source_dossier
fresh_dossier
saved_incident_state_fingerprint
fresh_incident_state_fingerprint
state_matches
changed_fields
reason_codes
normal_write_authorization_granted
configuration_mutation_performed
approval_consumed
model_execution_performed
revalidation_fingerprint
```

`source_dossier` is the exact saved dossier loaded from the external input.
`fresh_dossier` is rebuilt from a fresh strict
`write_model_configuration_manual_recovery_audit_timeline_v1` snapshot using
the same transaction ID.

The source dossier is read again after the fresh rebuild. Changed path, file
bytes, JSON payload, unsafe replacement, or malformed replacement fails closed
before a receipt is produced.

## Status

```text
current
stale
```

`current` means the saved incident dossier still matches the current semantic
incident state and returns `0`. `stale` means the selected transaction's
semantic state or the stable audited history changed and returns `4`.

The semantic comparison ignores natural volatility:

- saved and fresh dossier generation timestamps;
- dossier fingerprints;
- timeline generation timestamps;
- timeline fingerprints; and
- gate assessment timestamps and gate fingerprints.

It still compares the stable embedded timeline, selected events, incident
state, gate relation, normal-write impact, event count, reason codes, and
explicit safety flags.

## Export

Only the explicit revalidation-output option creates an audit artifact.
Export is immutable, idempotent for byte-equivalent JSON, rejects colliding
content, must remain outside both the configuration root and authoritative
`.dayu` evidence root, and rechecks the target around atomic-link creation to
reject symlink replacement.

## Exit codes

```text
0  saved dossier is current
2  invalid input, invalid arguments, or invalid/colliding export path
4  saved dossier is stale, input changed during revalidation, busy lock, or
   history changed during inspection
6  malformed or inconsistent fresh internal evidence
```

These codes report revalidation status only. They are not authorization,
operator approval, or a clearance decision.
