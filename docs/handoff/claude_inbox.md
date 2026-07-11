# Claude Inbox

**Updated:** 2026-07-12 05:56:53 +08:00
**Status:** READY
**Message ID:** codex-research-template-checklist-bundle-20260712-055653

CODEX_GATE: PASS

EXECUTE_RESEARCH_TEMPLATE_CHECKLIST_BUNDLE

## Objective

Integrate the analyst checklist artifact into the existing research-template materialization/bundle workflow so a generated workspace can carry the checklist alongside the workbook, progress report, monitoring plan, guide, and status artifacts.

## Allowed Scope

- Extend existing `research-template materialize` / bundle materialization helpers so they can generate a checklist artifact from the selected template definition.
- Add the checklist path to the bundle descriptor `artifacts` section using a clear key such as `research_checklist`.
- Extend bundle inspection/validation to detect a missing, invalid, or stale checklist artifact where practical.
- Keep standalone `checklist` and `materialize-checklist` commands backward compatible.
- Preserve existing bundle/workbook/progress/monitoring/status behavior and rollback semantics.
- Update focused CLI tests and directly relevant README/docs.

## Hard Boundaries

- Do not change filing download, Docling processing, Fins storage, LLM runners, Web UI, WeChat UI, provider config, or external network behavior.
- Do not introduce new runtime dependencies.
- Do not alter existing Markdown templates or template definition JSON assets unless a test proves a concrete inconsistency.
- Do not weaken existing rollback, manifest, source-map, write pipeline, or portfolio behavior.
- Do not modify unrelated untracked files: `.codegraph/`, `docs/reviews/`, or `docs/review/CLAUDE_TESTEVAL_CHECKLIST.md`.
- Do not commit, push, or modify `docs/review/claude_status_last_hash.txt`.

## Acceptance Criteria

- `research-template materialize <name>` writes a checklist artifact by default.
- Bundle descriptor includes the checklist artifact path.
- Bundle validation fails clearly if the checklist file is missing or inconsistent with the bundle template.
- Existing materialize rollback still removes checklist output on failure.
- Existing `checklist` and `materialize-checklist` commands continue to pass.
- Focused tests cover materialize output, bundle validation happy path, missing checklist failure, stale/wrong-template checklist failure if feasible, rollback cleanup, and backward compatibility.
- Affected-source `ruff` and `pyright` pass, or the outbox explains a pre-existing blocker with exact command output.

## Required Outbox Evidence

After implementation:

- Update `docs/handoff/claude_outbox.md`.
- Include `READY_FOR_CODEX_REVIEW`.
- List changed files.
- List verification commands and results.
- State any scope deviations explicitly.
- Stop after writing the outbox.
