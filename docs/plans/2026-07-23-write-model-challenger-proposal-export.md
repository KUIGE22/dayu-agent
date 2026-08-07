# Write Model Challenger Proposal Export

## Objective

Make the existing advisory Challenger proposal portable and auditable without
turning it into an execution path.

## CLI Contract

The export is available only through:

```text
write --summary
  --routing-history-root <history-root>
  --routing-proposal-output <receipt.json>
```

`--overwrite-routing-proposal` is valid only when an output path is present.
Normal summary reporting remains read-only.

An existing receipt can be checked with:

```text
write --summary
  --routing-history-root <history-root>
  --routing-proposal-input <receipt.json>
```

Input and output are mutually exclusive.

## Receipt Identity

The `write_model_challenger_proposal_v2` receipt contains:

- `history_fingerprint`: SHA-256 over the ordered selected raw summaries;
- selected, recent, and baseline run counts;
- `proposal_fingerprint`: SHA-256 over the complete unsigned proposal;
- bounded JSON argv overrides, evidence, thresholds, and safety requirements.

Current-catalog cost repricing happens after raw summary fingerprinting, so it
cannot silently change receipt identity.

## Persistence

Persistence validates the proposal first, serializes canonical JSON, writes a
same-directory temporary file, flushes it with `fsync`, and publishes it with
an atomic replace. Identical content is idempotent. Different existing content
fails closed unless overwrite was explicitly requested.

## Non-Goals

The export does not call a model, invoke a provider, edit model configuration,
launch a Challenger run, bypass preflight, or promote a model.

## Read-Only Verification

Verification validates the receipt structure and fingerprint, rebuilds the
current proposal from the same history root, and compares both identities:

- `current`: history and proposal fingerprints match;
- `stale_history`: the selected raw history changed;
- `policy_changed`: history matches but the rebuilt proposal differs.

Only `current` plus a `ready` proposal exposes the bounded JSON argv preview.
The preview is never executed. Stale or changed receipts return exit code `4`;
malformed, tampered, or unsafe receipts return `2`.

## Verification

- proposal tampering is rejected;
- history and proposal fingerprints remain stable under repricing;
- identical exports are idempotent;
- conflicting exports fail without overwrite;
- CLI invalid combinations return argument error code `2`;
- service export failures return code `2`.
