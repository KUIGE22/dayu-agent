# Research Template Checklist Bundle Codex Review

**Reviewed:** 2026-07-12 06:17:19 +08:00
**Inbox Message:** codex-research-template-checklist-bundle-20260712-055653
**Claude Status:** READY_FOR_CODEX_REVIEW
**Codex Gate:** PASS

## Scope Check

- Allowed files changed: research-template CLI materialization/validation code, focused CLI tests, packaged template README, and handoff files.
- Forbidden areas not touched: filing download, Docling processing, Fins storage, LLM runners, Web UI, WeChat UI, provider config, network behavior, Markdown templates, and definition JSON assets.
- Unrelated untracked files were left untouched: `.codegraph/`, `docs/reviews/`, `docs/review/CLAUDE_TESTEVAL_CHECKLIST.md`.
- `docs/review/claude_status_last_hash.txt` remains local-only and is not part of the commit.

## Verification

- `python -m pytest tests/cli/test_research_template_command.py -q`: 212 passed.
- `python -m ruff check dayu/cli/commands/research_template.py tests/cli/test_research_template_command.py`: passed.
- `python -m pyright dayu/cli/commands/research_template.py dayu/cli/research_template_checklist.py dayu/cli/research_template_definitions.py`: 0 errors.
- `git diff --check`: no whitespace errors; only expected CRLF normalization warnings.
- End-to-end smoke: `research-template materialize consumer --base <temp>` wrote `checklist_file`, registered `artifacts.research_checklist`, and passed `validate-bundle`.
- End-to-end smoke after tampering with the checklist: `validate-bundle` returned rc 1 with `checklist integrity` error.
- Full repository test run from repo root: `5445 passed, 83 skipped, 8 warnings in 245.10s`.

## Findings

No actionable P1/P2/P3 findings.

Residual notes:
- Existing bundle descriptors without `research_checklist` now validate as incomplete. This is an intentional schema-tightening for this phase and matches the acceptance criteria.
- Test-file pyright debt remains pre-existing; production files are clean.
