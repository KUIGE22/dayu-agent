# Manual Recovery Clearance-Revocation Lineage v2

## Purpose

This protocol binds a recovery restarted after clearance revocation to the
exact revocation that required the newer transaction. It prevents evidence
export from becoming a one-time check whose identity is lost during later
selection, approval, execution, or verification.

The protocol is additive at the workflow level, not optional within a schema:

- Ordinary recovery from a `recovery_failed` rollback receipt uses strict v1
  artifacts.
- Recovery restarted from `clearance_revoked` uses strict v2 artifacts.
- Every v2 artifact must contain the exact same
  `clearance_revocation_lineage`.
- No v1 artifact may contain that field.

## Lineage schema

```json
{
  "schema_version": "write_model_configuration_manual_recovery_clearance_revocation_lineage_v1",
  "ticker": "AAPL",
  "revoked_transaction_id": "<revoked recovery transaction id>",
  "revoked_manual_recovery_receipt_fingerprint": "sha256:<receipt content fingerprint>",
  "manual_recovery_clearance_fingerprint": "sha256:<clearance fingerprint>",
  "manual_recovery_clearance_revocation_fingerprint": "sha256:<revocation fingerprint>",
  "source_revoked_manual_recovery_receipt": {
    "path": "<absolute authoritative internal receipt path>",
    "file_fingerprint": "sha256:<exact file bytes>",
    "content_fingerprint": "sha256:<receipt content fingerprint>"
  },
  "source_manual_recovery_clearance": {
    "path": "<absolute authoritative internal clearance path>",
    "file_fingerprint": "sha256:<exact file bytes>",
    "content_fingerprint": "sha256:<clearance content fingerprint>"
  },
  "source_manual_recovery_clearance_revocation": {
    "path": "<absolute authoritative internal revocation path>",
    "file_fingerprint": "sha256:<exact file bytes>",
    "content_fingerprint": "sha256:<revocation content fingerprint>"
  },
  "lineage_fingerprint": "sha256:<canonical unsigned lineage fingerprint>"
}
```

The restart bridge creates this object from authoritative internal artifacts.
Operators copy it; they do not construct, edit, re-sign, or substitute it.

## Artifact chain

The coordinated schema sequence is:

```text
write_model_configuration_manual_recovery_evidence_v2
  -> write_model_configuration_manual_recovery_selection_request_v2
  -> write_model_configuration_manual_recovery_plan_v2
  -> write_model_configuration_manual_recovery_approval_request_v2
  -> write_model_configuration_manual_recovery_approval_v2
  -> write_model_configuration_manual_recovery_intent_v2
  -> write_model_configuration_manual_recovery_consumption_v2
  -> write_model_configuration_manual_recovery_receipt_v2
  -> write_model_configuration_manual_recovery_verification_v2
  -> write_model_configuration_manual_recovery_clearance_request_v2
  -> write_model_configuration_manual_recovery_clearance_v2
```

Generated artifacts choose v2 automatically when their source is v2.
Operator-authored request objects must explicitly use v2.

## Selection request

Start with the ordinary selection request fields. Change `schema_version` to
`write_model_configuration_manual_recovery_selection_request_v2`, append
`reviewed_exact_clearance_revocation_lineage` to `acknowledgements`, and copy
the complete `clearance_revocation_lineage` object from evidence.

The plan builder rejects:

- a v1 selection for v2 evidence;
- missing or extra lineage fields;
- a changed lineage fingerprint;
- a valid but different lineage object;
- authoritative source bytes that changed after evidence export.

## Approval request

Start with the ordinary approval request fields. Change `schema_version` to
`write_model_configuration_manual_recovery_approval_request_v2`, append
`approved_exact_clearance_revocation_lineage` to `acknowledgements`, and copy
the complete `clearance_revocation_lineage` object from the plan.

Approval issuance rejects any difference among evidence, selection, plan, and
request lineages. It also reloads the authoritative source artifacts before
issuing the approval.

## Execution and verification

Execution preserves the lineage in intent, approval consumption, and receipt.
An interrupted consumed transaction verifies the same lineage before
restoring any target. Independent verification then:

1. Loads evidence, selection, plan, approval request, approval, consumption,
   and intent when present.
2. Requires exact lineage equality across the complete chain.
3. Reloads the authoritative revoked receipt, clearance, and revocation.
4. Verifies exact file bytes, content fingerprints, ticker, transaction
   relationships, and statuses `recovered`, `cleared`, and `revoked`.
5. Rejects verification if any authoritative source changed, even when all
   downstream artifacts remain internally self-consistent.

Reports for v2 evidence, plans, approvals, receipts, and verifications display
the revocation fingerprint so operators can correlate the chain.

The independent clearance operator must then use a strict v2 clearance
request that copies the same lineage. The resulting v2 clearance preserves it,
and the normal-write gate rechecks the three authoritative lineage artifacts
before every `cleared` result. See
`docs/plans/2026-07-29-write-model-configuration-manual-recovery-clearance-lineage-v2.md`.

## Safety boundaries

- Restart does not remove or weaken revocation.
- The revoked transaction can never be cleared again.
- Only the newer recovered transaction may receive a new clearance.
- Lineage is immutable data, not an authority or approval.
- No bridge, planning, approval, or verification command calls a model.
- No lineage validation modifies configuration, model catalogs, secrets, or
  environment variables.
- Cross-layer lineage substitution fails closed even when the substituted
  object has a valid internal fingerprint.
