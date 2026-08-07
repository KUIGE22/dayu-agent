# Research Template Checklist Codex Review

**Reviewed:** 2026-07-12 05:56:24 +08:00
**Inbox Message:** codex-research-template-checklist-20260712-053720
**Claude Status:** READY_FOR_CODEX_REVIEW
**Codex Gate:** PASS

## Scope Check

- Allowed files changed: CLI parser/command, new checklist builder, focused research-template CLI tests, README examples, and handoff files.
- Forbidden areas not touched: filing download, Docling processing, Fins storage, LLM runners, Web UI, WeChat UI, provider config, rollback/manifest/source-map/write pipeline behavior.
- Unrelated untracked files were left untouched: `.codegraph/`, `docs/reviews/`, `docs/review/CLAUDE_TESTEVAL_CHECKLIST.md`.
- `docs/review/claude_status_last_hash.txt` remains local-only and is not part of the commit.

## Verification

- `python -m pytest tests/cli/test_research_template_command.py tests/cli/test_research_template_definitions.py -q`: 221 passed.
- `python -m ruff check dayu/cli/research_template_checklist.py dayu/cli/commands/research_template.py dayu/cli/arg_parsing.py tests/cli/test_research_template_command.py`: passed.
- `python -m pyright dayu/cli/research_template_checklist.py dayu/cli/commands/research_template.py dayu/cli/arg_parsing.py`: 0 errors.
- `git diff --check`: no whitespace errors; only expected CRLF normalization warnings.
- `python -m dayu.cli research-template checklist consumer`: rc 0, Markdown checklist emitted.
- `python -m dayu.cli research-template checklist technology --json`: rc 0, stable checklist keys and section counts emitted.
- `python -m dayu.cli research-template materialize-checklist financial --base <temp> --json`: rc 0 on first write, rc 1 on existing file without `--overwrite`, rc 0 with `--overwrite`.
- Full repository test run from repo root: `5439 passed, 83 skipped, 8 warnings in 225.63s`.

## Findings

No actionable P1/P2/P3 findings.

Residual notes:
- Test-file pyright still has the pre-existing `tests/cli/test_research_template_command.py` baseline debt described by Claude; production files are clean.
- Markdown smoke output appears mojibaked in the PowerShell transcript because of terminal encoding, while tests and file writes use UTF-8 and validate the expected Chinese content.
