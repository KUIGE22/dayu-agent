# Write-model configuration manual recovery clearance lineage v2

## Goal

Keep the revoked-clearance lineage explicit when a recovery restarted from a
revoked incident reaches its new normal-write clearance boundary.

The recovery receipt fingerprint already binds the lineage transitively. The
v2 clearance contract additionally requires the independent clearance
operator to review the exact lineage and makes the normal-write gate recheck
its authoritative sources before every allowed write.

## Version boundary

The receipt and clearance artifacts must use one coordinated version:

```text
manual_recovery_receipt_v1
  -> clearance_request_v1
  -> clearance_v1

manual_recovery_receipt_v2
  -> clearance_request_v2
  -> clearance_v2
```

A v1 request cannot clear a v2 receipt. A v2 request cannot clear a v1
receipt. Existing ordinary failed-rollback recovery remains on v1.

## Clearance request v2

Start with every v1 request field, change `schema_version` to
`write_model_configuration_manual_recovery_clearance_request_v2`, copy the
receipt's complete `clearance_revocation_lineage` object without modification,
and append this acknowledgement:

```text
reviewed_exact_clearance_revocation_lineage
```

The request validator rejects missing or extra fields, malformed lineage, and
mixed schemas. Issuance rejects a structurally valid but different lineage.

## Clearance v2

Successful issuance creates
`write_model_configuration_manual_recovery_clearance_v2`. It preserves the
same lineage and appends this safety boundary:

```text
clearance_revocation_lineage_bound_and_current
```

Before first issuance and an immutable clearance re-export, the service:

1. Requires exact lineage equality among request, receipt, and fresh
   verification.
2. Reloads the authoritative revoked receipt, old clearance, and old
   revocation.
3. Verifies their paths, file bytes, content fingerprints, ticker,
   transaction relationships, and recovered/cleared/revoked statuses.
4. Fails before clearance persistence or export if any source changed.

The operator report displays the prior revocation fingerprint for correlation.

## Normal-write gate

For a v2 latest receipt, every receipt-backed gate status first:

1. Rechecks all three authoritative lineage sources.
2. Embeds the exact lineage and records its status as `current`.

This also applies to `clearance_required`, before a new clearance exists. If
the gate can return `cleared`, it additionally:

1. Requires exact lineage equality between the latest receipt and clearance.
2. Continues the existing receipt, routing, timestamp, and independent
   operator checks.

Source drift therefore blocks normal writes even when the current receipt and
clearance files remain internally self-consistent. Gate v4 also fingerprints
the complete assessed result.

## Revocation compatibility

The existing revocation request and revocation schemas remain valid. They bind
the exact new receipt and clearance fingerprints; the v2 clearance fingerprint
already includes the complete lineage. A later restart creates a fresh lineage
for that newly revoked transaction.

## Safety properties

- Clearance remains a separate independent human action.
- Lineage is evidence, not authority by itself.
- No model is called during issuance, re-export, or gate assessment.
- No configuration, model catalog, secret, or environment variable is
  modified.
- No approval is consumed.
- Existing v1 recovery and clearance artifacts remain valid.
- Cross-version downgrade and valid-but-different lineage substitution fail
  closed.
