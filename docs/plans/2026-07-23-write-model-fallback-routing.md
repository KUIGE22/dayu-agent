# Explicit Write Model Fallback Routing

## Goal

Allow the write pipeline to switch from a configured primary model to one
explicit fallback model when the provider is unavailable, while preserving
budget, audit, replay, and resume correctness.

## Safety Boundary

- Fallback is disabled unless the caller passes a write-role or audit-role
  fallback model.
- Only stable provider-availability error types may trigger fallback.
- Authentication, quota, request validation, content policy, tool, parse, and
  cancellation failures never change the selected model.
- The primary and fallback attempts are separate budget reservations and usage
  ledger entries.
- Parse-repair replay stays on the model and conversation that produced the
  output.
- The resolved fallback plan is persisted and contributes to the resume
  signature.
- The route applies only to the write pipeline. Runner and ordinary chat
  behavior remain unchanged.

## Implementation

1. Preserve stable Engine error metadata in `AppResult.error_details`.
2. Centralize provider-availability and failover error classification.
3. Add explicit write and audit fallback CLI/config fields.
4. Resolve fallback models during write preflight, including environment and
   pricing checks for models that can execute in the requested mode.
5. Dispatch at most one fallback attempt for an eligible primary result.
6. Keep fallback replay, usage, cost, and model snapshots bound to the fallback
   scene.
7. Cover routing, denial, budget, replay, persistence, and signature behavior
   with focused tests.
8. Persist a credential-free `model_routing` receipt with deterministic route
   aggregates, stable trigger categories, and fallback call status. Keep the
   summary schema additive so older `write_run_summary_v3` files remain
   readable, and surface missing historical routing data as unknown rather
   than zero.

## Verification

- Focused Host, CLI, preflight, pipeline, and replay tests.
- Scoped Ruff and Pyright.
- Related test modules, followed by the full test suite.
- `git diff --check` and a credential-pattern scan.
- No live provider request is required for this change.
