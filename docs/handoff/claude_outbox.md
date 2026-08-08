# Claude Outbox

Status: READY_FOR_CODEX_REVIEW
Message ID: codex-research-template-checklist-bundle-20260712-055653
Task: EXECUTE_RESEARCH_TEMPLATE_CHECKLIST_BUNDLE

READY_FOR_CODEX_REVIEW

## Summary

Integrated the analyst checklist artifact into the research-template
materialization/bundle workflow. Every materialized bundle now carries a
deterministic `research_checklist` artifact alongside the workbook, progress
report, monitoring rules, source-map, manifest, and guide. Bundle validation
recomputes the checklist from the bundle's own template definition, so a
missing, hand-edited (stale), or wrong-template checklist fails validation
clearly. Standalone `checklist` / `materialize-checklist` commands are
unchanged.

## Changed Files

- `dayu/cli/commands/research_template.py`
  - Added `research_checklist` to `_BUNDLE_ARTIFACT_KEYS` (now a required
    bundle artifact; existence enforced by the existing required-artifact loop).
  - `build_research_template_bundle_descriptor` / `write_research_template_bundle_descriptor`:
    new required keyword-only `checklist_file: Path`; descriptor `artifacts`
    now includes `research_checklist`.
  - `materialize_research_template_bundle`: generates the checklist via the
    existing `materialize_research_checklist` helper, passes it to the
    descriptor, and returns `checklist_file`. (All bundle-producing paths —
    `materialize_research_workspace`, `materialize_research_bundle_from_write_manifest`,
    `materialize_research_portfolio` — route through this function, so they
    inherit the checklist for free.)
  - `_materialization_artifact_paths`: added `{template}.checklist.md` so the
    existing snapshot/rollback boundary covers the checklist on failure.
  - New `_recompute_bundle_checklist_integrity` helper + call in
    `validate_research_template_bundle_descriptor` to detect stale/wrong-template
    checklists by re-rendering the expected markdown from the bundle template
    definition and comparing byte-for-byte.
- `tests/cli/test_research_template_command.py`
  - Updated `test_build_and_validate_research_template_bundle_descriptor` to
    supply `checklist_file` and assert `artifact_count == 7` + `research_checklist`.
  - Updated `test_run_materialize_command_can_select_template_from_manifest`
    artifact_count `7 -> 8` and asserted `checklist_file` exists.
  - Updated `test_materialize_research_template_bundle_writes_all_artifacts`
    to cover `checklist_file` and the bundle's `research_checklist` entry.
  - Added focused tests: checklist matches template definition; missing
    checklist failure; stale checklist failure; wrong-template checklist
    failure; rollback removes checklist on failure; standalone
    `materialize_research_checklist` produces no bundle (backward compatibility).
- `dayu/assets/research_templates/README.md`
  - Documented that `materialize` also writes `<name>.checklist.md`, registers
    it as the `research_checklist` bundle artifact, and that validation fails on
    missing/edited/wrong-template checklists; noted the standalone commands are
    unaffected.

## Verification Commands and Results

All run under `source .venv/Scripts/activate` (Windows venv layout).

- `python -m pytest tests/cli/test_research_template_command.py -q`
  → `212 passed in ~11s`.
- `python -m pytest tests/cli/test_research_template_command.py -q -k "checklist or rollback_removes or matches_template_definition"`
  → `20 passed, 192 deselected`.
- `python -m ruff check dayu/cli/commands/research_template.py tests/cli/test_research_template_command.py`
  → `All checks passed!`.
- `python -m pyright dayu/cli/commands/research_template.py`
  → `0 errors, 0 warnings, 0 informations`.
- `python -m pyright dayu/cli/commands/research_template.py tests/cli/test_research_template_command.py`
  → `25 errors` (all in the test file). Pre-existing baseline on the unmodified
    test file is `26 errors`; my changes introduce zero new pyright errors (net
    one fewer). The remaining errors are the file's long-standing
    `payload["..."]` indexing on `dict[str, object]` returns on lines I did not
    touch — not introduced or spread by this task.

## Scope Deviations

None. Changes are confined to the research-template CLI module, its focused
test file, and the directly relevant `dayu/assets/research_templates/README.md`.
No changes to filing download, Docling, Fins storage, LLM runners, Web/WeChat
UI, provider config, network behavior, Markdown templates, or template
definition JSON assets. No new runtime dependencies. No commit/push. Untracked
files (`.codegraph/`, `docs/reviews/`, `docs/review/CLAUDE_TESTEVAL_CHECKLIST.md`,
`docs/review/claude_status_last_hash.txt`) were not modified.
