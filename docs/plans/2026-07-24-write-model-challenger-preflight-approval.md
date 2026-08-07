# Write Model Challenger Preflight Approval

## Objective

Turn a human review of one current, ready Challenger proposal into an
immutable, tamper-evident approval receipt whose only authority is entering
Champion/Challenger common preflight.

## CLI Contract

Approval issuance requires all five inputs:

```text
write --summary
  --routing-history-root <history-root>
  --routing-proposal-input <proposal.json>
  --routing-preflight-approval-request <request.json>
  --routing-preflight-approval-output <approval.json>
```

The command remains in summary mode. It does not execute the approved argv.

Approval consumption requires the exported proposal, current history, the
approval receipt, exact Challenger overrides, and explicit Champion model
overrides for every role changed by the proposal:

```text
write --preflight-only
  --model-name <current-primary>                 # when primary is changed
  --audit-model-name <current-audit>             # when audit is changed
  --challenger-model-name <approved-primary>     # when present in proposal
  --challenger-audit-model-name <approved-audit> # when present in proposal
  --routing-history-root <history-root>
  --routing-proposal-input <proposal.json>
  --routing-preflight-approval-input <approval.json>
```

The consumption gate runs before `_prepare_cli_host_dependencies`.

## Human Request

The strict
`write_model_challenger_preflight_approval_request_v1` object contains:

- operator identity and an external approval reference;
- `approved_at` and `expires_at` UTC timestamps ending in `Z`;
- a maximum validity period of 24 hours;
- the proposal and selected-history SHA-256 fingerprints;
- an exact acknowledgement of the common-preflight-only safety boundary.

Unknown fields, control characters, leading or trailing identity whitespace,
unsafe time windows, and incomplete acknowledgements are rejected.

## Approval Gate

Issuance rebuilds the proposal from current history and requires:

- valid proposal and request schemas;
- verification status `current`;
- proposal status `ready`;
- an active approval time window;
- request fingerprints equal to the current proposal and history;
- only bounded Challenger role override arguments.

Stale identity, inactive time, or a non-ready proposal returns `4`. Malformed
JSON, schema errors, or persistence conflicts return `2`.

At consumption time the CLI rebuilds the proposal again and requires:

- the exported proposal to remain current against the selected history;
- the approval history and proposal fingerprints to match that current
  proposal;
- the receipt argv to remain equal to the current proposal argv;
- the actual Challenger argv to exactly equal the receipt argv;
- explicit current Champion model identities to exactly match every role
  override in the proposal;
- the approval window to still be active.

Policy, history, time, or command mismatches return `4` without initializing
Host. Malformed receipts and invalid files return `2`.

## Receipt

`write_model_challenger_preflight_approval_v1` binds:

- human approval provenance;
- request, proposal, and history fingerprints;
- exact `["--preflight-only", ...]` argv;
- the expiry time and fixed safety boundaries;
- a SHA-256 over the complete receipt.

Persistence uses a same-directory temporary file, flush, `fsync`, and atomic
no-clobber publication. Identical content is idempotent. Different content can
never overwrite the same approval path, including a concurrent publisher.

## Safety Boundary

The receipt does not authenticate the human cryptographically; identity and
reference are declarative operator provenance, while SHA-256 detects receipt
content changes. Issuance does not create a Host session, invoke a model,
change configuration, authorize a Challenger experiment, or authorize model
promotion.

The approval input is accepted only with `--preflight-only`. Ordinary approved
preflight cannot use a custom Challenger output, `--fast`, or `--chapter`.
A custom output is accepted only while exporting or issuing an exact bounded
run plan. Ordinary Champion-only preflight remains unchanged. A full
Challenger experiment requires the separate single-use run authorization
defined in
`docs/plans/2026-07-24-write-model-challenger-run-approval.md`; this preflight
receipt can never authorize model execution by itself.

## Verification

- policy tests cover current, stale, non-ready, mismatched, future, and expired
  requests;
- schema tests cover unknown fields, maximum validity, tampering, and unsafe
  argv;
- persistence tests cover atomic, idempotent, immutable round trips;
- consumption tests cover exact argv, current Champion identity, stale
  history, policy change, inactive time, and malformed files;
- CLI tests cover argument dependencies, file loading, and fail-closed
  verification before Host initialization;
- service tests cover successful issuance and policy exit code `4`.
