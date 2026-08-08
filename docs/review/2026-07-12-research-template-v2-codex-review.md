# Research Template V2 Codex Review

**Reviewed:** 2026-07-12 05:36:52 +08:00
**Inbox Message:** codex-research-template-v2-20260712-051503
**Claude Status:** READY_FOR_CODEX_REVIEW
**Codex Gate:** PASS

## Scope Check

- Allowed files changed: CLI parser/command, research-template definition loader, packaged template assets, focused tests, README, pyproject package-data, and handoff files.
- Forbidden areas not touched: filing download, Docling processing, Fins storage, LLM runners, Web UI, WeChat UI, provider config, rollback/manifest/source-map/write pipeline code.
- Unrelated untracked files were left untouched: `.codegraph/`, `docs/reviews/`, `docs/review/CLAUDE_TESTEVAL_CHECKLIST.md`.

## Verification

- `python -m pytest tests/cli/test_research_template_definitions.py -q`: 15 passed.
- `python -m pytest tests/cli/test_research_template_command.py -q`: 192 passed.
- `python -m ruff check dayu/cli/research_template_definitions.py dayu/cli/commands/research_template.py dayu/cli/arg_parsing.py tests/cli/test_research_template_definitions.py`: passed.
- `python -m pyright dayu/cli/research_template_definitions.py dayu/cli/commands/research_template.py dayu/cli/arg_parsing.py`: 0 errors.
- `python -m pyright ... tests/cli/test_research_template_definitions.py`: one `pytest` missing-import baseline in the local pyright environment; production code remains clean.
- `python -m dayu.cli research-template scorecard consumer`: rc 0, printed the consumer scorecard.
- `python -m dayu.cli research-template evidence nope`: rc 1 with a clear available-template error.
- `python -m dayu.cli research-template schema technology --json`: returned expected keys and scorecard weights.
- `uv build --wheel --out-dir workspace/tmp/codex-wheel-check`: built successfully with existing setuptools license deprecation warnings.
- Wheel inspection confirmed `common/consumer/cyclical/financial/technology.definition.json` and the existing Markdown templates are packaged.
- Full repository test run from the repo root: `5425 passed, 83 skipped, 8 warnings in 229.33s`.

## Findings

No actionable P1/P2/P3 findings.

Residual notes:
- Full pyright over tests remains affected by the existing local pytest import-resolution baseline.
- Build emits existing setuptools license deprecation warnings unrelated to this phase.
- A first attempted full pytest command accidentally ran from `F:\claude-workspace` and collected unrelated repositories; the valid run was repeated from `F:\claude-workspace\dayu-agent`.
