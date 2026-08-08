# Write model usage ledger implementation plan

## Goal

Preserve provider-reported model usage across the Host boundary and expose a
credential-free, auditable token and configured-cost ledger in
`run_summary.json` for dual-model write runs.

## Design

1. Add a stable `ModelUsage` contract that normalizes OpenAI- and
   Anthropic-style usage keys and supports deterministic aggregation.
2. Aggregate every `DONE` event usage payload in Host result collection,
   including replay runs, and return it in `AppResult`.
3. Add a thread-safe write-pipeline ledger. Record completed scene calls by
   scene, configured model, and primary/audit role.
4. Calculate cost only from optional pricing declared in `llm_models.json`.
   Never embed provider prices in code. Report partial or unavailable pricing
   coverage instead of presenting an incomplete total as authoritative.
5. Add the ledger to `run_summary.json`, bump its additive schema version, and
   document the optional pricing fields.

## Verification

- Contract normalization and aggregation unit tests.
- Host collection and replay usage tests.
- Concurrent ledger aggregation and pricing coverage tests.
- Execution summary integration tests.
- Ruff, Pyright, targeted tests, and the complete test suite.
- Independent DeepSeek and MiMo read-only reviews before final verification.
