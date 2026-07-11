# Claude Inbox

**Updated:** 2026-07-12 05:15:03 +08:00
**Status:** READY
**Message ID:** codex-research-template-v2-20260712-051503

CODEX_GATE: PASS

EXECUTE_RESEARCH_TEMPLATE_V2

## Objective

Upgrade the research-template feature from Markdown-only guidance into a lightweight executable template definition layer that can expose each industry's scorecard, evidence requirements, red flags, and output sections through CLI commands.

## Allowed Scope

- Add typed template definition models and loaders under `dayu/cli/` or a similarly narrow existing package boundary.
- Add packaged JSON or YAML assets under `dayu/assets/research_templates/` for `common`, `consumer`, `cyclical`, `financial`, and `technology`.
- Extend the existing `research-template` CLI with read-only commands such as `scorecard`, `schema`, `evidence`, or equivalent names.
- Keep existing Markdown template commands backward compatible.
- Update focused CLI tests for new commands and asset validation.
- Update only directly relevant README/docs sections.

## Hard Boundaries

- Do not change financial filing download logic, Docling processing, Fins storage, LLM runners, Web UI, WeChat UI, or model provider configuration.
- Do not introduce network calls or new runtime dependencies.
- Do not replace existing Markdown templates; the v2 definitions must complement them.
- Do not weaken existing rollback, manifest, source-map, or write pipeline behavior.
- Do not modify unrelated untracked files: `.codegraph/`, `docs/reviews/`, or `docs/review/CLAUDE_TESTEVAL_CHECKLIST.md`.

## Acceptance Criteria

- `dayu-cli research-template list` continues to work.
- A user can inspect a template's scorecard and evidence requirements from the CLI without materializing a workspace.
- The loader validates malformed or incomplete template definition assets with clear errors.
- Packaged wheel/source discovery includes the new definition assets.
- Focused tests cover at least: happy-path load, unknown template, malformed definition, CLI scorecard/evidence output, and backward compatibility with Markdown templates.
- Affected-source `ruff` and `pyright` pass, or the outbox explains a pre-existing blocker with exact command output.

## Required Outbox Evidence

After implementation:

- Update `docs/handoff/claude_outbox.md`.
- Include `READY_FOR_CODEX_REVIEW`.
- List changed files.
- List verification commands and results.
- State any scope deviations explicitly.
- Stop after writing the outbox.
