# Write-model configuration manual recovery incident dossier v1

## Goal

Provide one supported, read-only incident view for an exact manual-recovery
transaction.

The complete audit timeline answers whether all authoritative history is
valid. The incident dossier answers which events belong to one transaction,
how that transaction relates to the current gate, and whether it currently
blocks normal writes. It does not introduce another recovery, clearance,
verification, or authorization layer.

## Command

```text
dayu-cli write --ticker AAPL \
  --inspect-write-model-configuration-manual-recovery-incident \
  --challenger-config-manual-recovery-incident-transaction-id \
    <transaction-id>
```

An optional immutable dossier may be written outside configuration and the
authoritative `.dayu` evidence root:

```text
  --challenger-config-manual-recovery-incident-dossier-output \
    <audit/manual-recovery-incident-dossier.json>
```

The inspection flag and transaction ID are required together. The output
option is valid only in this dedicated mode. The mode is mutually exclusive
with write, preflight, routing, model override, Challenger, and every other
manual-recovery operation.

## Source of truth

The inspector does not scan recovery roots independently. It first invokes
the strict full-history builder described by:

```text
write_model_configuration_manual_recovery_audit_timeline_v1
```

That builder owns the shared transaction lock, validates all authoritative
artifacts, embeds a fresh gate v4 assessment, scans the roots a second time,
and rejects concurrent history changes. The dossier builder accepts only a
fully validated timeline.

This reuse keeps one definition of authoritative history and one race
boundary.

## Operator discovery

The existing full-history audit report displays:

```text
Gate subject
Complete IDs
Incomplete
```

Complete IDs are sorted and bounded to eight entries with a remaining count.
Incomplete IDs retain the existing explicit report. This is enough to select
an exact incident without adding a second index schema or artifact.

When a requested transaction is absent, the incident builder reports the
same bounded preview over all complete and incomplete transaction IDs. It
never includes an unbounded transaction list in an error message.

## Dossier contract

Every result uses:

```text
schema_version =
  write_model_configuration_manual_recovery_incident_dossier_v1
```

Top-level fields:

```text
generated_at
ticker
transaction_id
incident_state
gate_relation
normal_write_impact
selected_events
event_count
source_timeline
source_timeline_fingerprint
reason_codes
normal_write_authorization_granted
configuration_mutation_performed
approval_consumed
model_execution_performed
dossier_fingerprint
```

`source_timeline` is the complete strict timeline, not a reference to an
external path. Embedding it intentionally preserves the proof needed to
decide whether the selected transaction is current, incomplete, or
historical. `source_timeline_fingerprint` must equal the embedded timeline's
fingerprint.

`selected_events` is the exact ordered subset whose `transaction_id` matches
the requested transaction. Complete transactions include their receipt and,
when present, clearance and revocation. An incomplete transaction has no
events and is selected from `incomplete_transaction_ids`.

## Incident states

The deterministic incident state is one of:

```text
incomplete
recovery_failed
starting_state_restored
recovered_clearance_required
recovered_cleared
recovered_clearance_revoked
```

The state is derived only from the embedded strict timeline. Callers cannot
provide or override it.

## Gate relation

The selected transaction has exactly one relation:

```text
current_incomplete_blocker
current_complete_subject
historical
```

An incomplete transaction contributes to the current incomplete-history
gate. A complete transaction is current only when its identity equals the
fresh gate's latest transaction identity. Every other complete transaction
is historical.

## Normal-write impact

The derived impact is one of:

```text
blocks_current_normal_writes
current_gate_allows_normal_writes
historical_only
```

This field describes the fresh gate state. It is not an authorization
decision created by the dossier. The explicit
`normal_write_authorization_granted` field is always `false`.

## Validation and integrity

Validation:

1. requires the exact v1 field set;
2. revalidates the entire embedded timeline;
3. binds ticker and generation time to that timeline;
4. compares the embedded timeline fingerprint;
5. reselects and rederives all incident fields;
6. compares selected events, count, state, gate relation, impact, and reason
   codes;
7. requires every safety evidence flag to remain `false`; and
8. recomputes the dossier fingerprint.

`dossier_fingerprint` seals every dossier field except itself, including the
complete source timeline. SHA-256 fingerprints provide deterministic
integrity evidence. They are not signatures, operator identity, or authority.

The operator-facing dossier report includes both deterministic reason codes.
Those codes are rederived during validation and are not free-form advice or
authorization.

## Saved dossier revalidation

A saved dossier can be checked later against current strict internal history:

```text
dayu-cli write --ticker AAPL \
  --revalidate-write-model-configuration-manual-recovery-incident-dossier \
  --challenger-config-manual-recovery-incident-dossier-input \
    <audit/manual-recovery-incident-dossier.json>
```

The revalidator reloads the saved dossier, rebuilds a fresh strict timeline,
creates a fresh dossier for the same transaction, and compares stable
semantic state while ignoring natural timestamp and fingerprint volatility.
`current` returns `0`; `stale` returns `4`. It remains read-only and is
documented in
`2026-07-30-write-model-configuration-manual-recovery-incident-dossier-revalidation-v1.md`.

## Immutable export

Explicit export:

- validates the complete dossier before writing;
- rejects symlink targets;
- rechecks the target immediately before existing-content acceptance and
  after atomic-link creation or collision;
- rejects a target that becomes a symlink during that interval;
- rejects lexical or resolved paths under configuration or the workspace
  `.dayu` root;
- writes through a temporary file, flushes and fsyncs it, then creates the
  destination without replacement;
- treats an existing byte-equivalent JSON artifact as idempotent; and
- rejects an existing path with different content.

No audit file is created unless the output option is supplied.

## Exit codes

```text
0  a strict dossier was generated, regardless of incident or gate state
2  missing config root, invalid selector, arguments, or export path
4  unknown transaction, busy lock, or history changed during inspection
6  malformed, unsafe, orphaned, or inconsistent internal evidence
```

An unresolved incident can therefore return `0`: command success means the
dossier was built safely, not that recovery is complete or normal writes are
allowed.

## Side-effect boundary

Inspection and optional export:

- do not modify routing or model configuration;
- do not issue, consume, revoke, or replace an approval;
- do not issue, revoke, replace, or remove a clearance;
- do not modify authoritative recovery evidence;
- do not construct Host dependencies;
- do not invoke DeepSeek, MiMo, or any other model; and
- do not authorize a normal write.

The feature is an operator evidence projection over the existing strict
timeline, not a new control-plane transition.
