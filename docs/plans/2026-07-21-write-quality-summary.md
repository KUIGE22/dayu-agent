# Write Quality Summary Implementation Plan

> **For implementers:** execute this plan task-by-task and preserve deterministic summary semantics.

**Goal:** Extend the existing `run_summary.json` into a backward-compatible, deterministic quality receipt for DeepSeek primary writing and MiMo audit execution.

**Architecture:** Keep `ExecutionSummaryBuilder` as the only run-summary owner. Aggregate model roles from the resolved `WriteRunConfig.scene_models` and chapter quality facts from `ChapterResult` plus its persisted `process_state`; do not add model calls, change the audit gate, or modify the resume manifest.

**Tech Stack:** Python 3.11, dataclasses, JSON, pytest, pyright.

---

## Task 1: Specify backward-compatible quality fields

**Files:**
- Modify: `tests/engine/test_execution_summary_builder.py`

1. Preserve the existing `ticker`, `output_file`, `chapter_count`, `failed_count`, and `failed_chapters` contract.
2. Add expectations for `schema_version`, `gate_status`, model-role details, audit aggregates, and index-ordered chapter details.
3. Cover first-pass success, repaired success, blocked chapters, confirmation checks, and applied anchor rewrites.
4. Cover fast mode separately so a chapter that skipped audit is never reported as audit-passed.

## Task 2: Implement deterministic summary aggregation

**Files:**
- Modify: `dayu/services/internal/write_pipeline/execution_summary_builder.py`

1. Classify resolved scenes with the existing `PRIMARY_MODEL_WRITE_SCENES` and `AUDIT_WRITE_SCENES` constants.
2. Build stable, sorted model-role entries without exposing environment variables or credentials.
3. Normalize legacy or partially malformed `process_state` collections without failing report assembly.
4. Derive chapter outcomes as `passed_first_attempt`, `passed_after_repair`, `passed_without_audit`, or `blocked`.
5. Aggregate retries, audit attempts, evidence confirmation checks, and applied anchor rewrites.

## Task 3: Document and verify

**Files:**
- Modify: `README.md`
- Modify: `dayu/config/README.md`

1. Document `run_summary.json` as the dual-model quality receipt and explain fast-mode semantics.
2. Run the focused summary tests and write-pipeline tests.
3. Run Ruff, Pyright, and the full test suite.
4. Ask MiMo to review compatibility, gate semantics, and malformed-state handling; accept only findings consistent with the existing architecture.
