# Claude Inbox

**Updated:** 2026-07-12 05:37:20 +08:00
**Status:** READY
**Message ID:** codex-research-template-checklist-20260712-053720

CODEX_GATE: PASS

EXECUTE_RESEARCH_TEMPLATE_CHECKLIST

## Objective

Bridge the new executable research-template definitions into a practical analyst checklist artifact that can be previewed from the CLI and optionally materialized into a workspace.

## Allowed Scope

- Add a narrow checklist builder under `dayu/cli/` that consumes `ResearchTemplateDefinition`.
- Add one or two `research-template` CLI commands, such as `checklist` and/or `materialize-checklist`.
- The checklist must include scorecard dimensions, evidence requirements, red flags, output sections, and explicit analyst fill-in fields.
- Support JSON output for machine use and Markdown output for analyst use.
- If write/materialize support is added, it must be opt-in, use `--output` or an existing workspace-safe default, and protect existing files unless `--overwrite` is provided.
- Keep existing Markdown template, definition, workbook, bundle, monitoring, and write commands backward compatible.
- Update focused CLI tests and directly relevant README/docs.

## Hard Boundaries

- Do not change financial filing download logic, Docling processing, Fins storage, LLM runners, Web UI, WeChat UI, or model provider configuration.
- Do not introduce network calls or new runtime dependencies.
- Do not replace existing Markdown templates; the v2 definitions must complement them.
- Do not weaken existing rollback, manifest, source-map, or write pipeline behavior.
- Do not modify unrelated untracked files: `.codegraph/`, `docs/reviews/`, or `docs/review/CLAUDE_TESTEVAL_CHECKLIST.md`.
- Do not commit, push, or modify `docs/review/claude_status_last_hash.txt`.

## Acceptance Criteria

- `dayu-cli research-template list` continues to work.
- A user can preview a complete checklist for `consumer`, `cyclical`, `financial`, and `technology` without materializing a workspace.
- JSON checklist output must be stable enough for tests: include template name, scorecard items, evidence items, red flags, output sections, and analyst fields.
- Markdown checklist output must be readable and include checkbox-style analyst tasks.
- Unknown template and output-overwrite behavior must return clear errors.
- Focused tests cover happy path, unknown template, JSON output, Markdown output, write protection, overwrite, and backward compatibility with existing commands.
- Affected-source `ruff` and `pyright` pass, or the outbox explains a pre-existing blocker with exact command output.

## Required Outbox Evidence

After implementation:

- Update `docs/handoff/claude_outbox.md`.
- Include `READY_FOR_CODEX_REVIEW`.
- List changed files.
- List verification commands and results.
- State any scope deviations explicitly.
- Stop after writing the outbox.
