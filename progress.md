# Progress Entry Point

## 2026-08-06: Worktree Baseline Mixed None Render Gate

Tightened programmatic task rendering so assignment-time worktree baselines cannot mix explicit `None` with concrete paths. Previously `render_task()` silently discarded `None` and rendered the remaining paths, which could hide ambiguous baseline evidence before the ready inbox validator saw it.

Covered cases:

- task rendering rejects `worktree_baseline=("None.", "docs/notes.md")`
- task rendering still rejects loose baseline stand-ins such as `Clean`
- handoff validation covers empty ready-outbox `## Scope Deviations` sections through the existing empty-section gate

Latest focused verification:

- `uv run --no-project --with pytest python -m pytest tests/test_prepare_deepseek_task.py::test_render_task_rejects_mixed_none_worktree_baseline tests/test_prepare_deepseek_task.py::test_render_task_rejects_non_none_worktree_baseline_stand_in tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_without_scope_deviation_statement -q` -> 3 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 613 passed
- `F:\claude-workspace\dayu-agent\.venv\Scripts\ruff.exe check utils/prepare_deepseek_task.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py` -> ok
- `uv run --no-project python -m utils.validate_handoff_docs --json` -> ok
- `uv run --no-project python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `uv run --no-project python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\prepare_deepseek_task.py tests\test_prepare_deepseek_task.py tests\test_validate_handoff_docs.py test_plan.md progress.md` -> ok with line-ending warnings only

## 2026-08-06: Worktree Baseline Explicit None Guard

Tightened ready-inbox worktree baseline handling so a clean assignment-time baseline must be represented by explicit `None`. Loose stand-ins such as `Clean`, `Empty`, `N/A`, or `Not applicable` now fail validation instead of being treated as clean baseline evidence.

Covered cases:

- handoff validation rejects ready-inbox `## Worktree Baseline` entries that say `Clean`
- Codex review gate surfaces non-`None` baseline stand-ins through handoff validation
- task rendering rejects programmatic worktree baseline stand-ins before producing ready inbox text

Latest focused verification:

- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_non_none_worktree_baseline_stand_in tests/test_codex_review_gate.py::test_review_gate_rejects_non_none_worktree_baseline_stand_in tests/test_prepare_deepseek_task.py::test_render_task_rejects_non_none_worktree_baseline_stand_in -q` -> 3 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 611 passed
- `F:\claude-workspace\dayu-agent\.venv\Scripts\ruff.exe check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py` -> ok
- `uv run --no-project python -m utils.validate_handoff_docs --json` -> ok
- `uv run --no-project python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `uv run --no-project python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py utils\codex_review_gate.py utils\prepare_deepseek_task.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py tests\test_prepare_deepseek_task.py test_plan.md progress.md` -> ok with line-ending warnings only

## 2026-08-06: Ready Outbox Explicit None Evidence Guard

Tightened ready-outbox review gates so clean scope-deviation and unresolved-blocker evidence must use explicit `None`. Loose stand-ins such as `No scope deviations` or `No blockers` now fail validation instead of being treated as clean handoff evidence.

Covered cases:

- handoff validation rejects ready-outbox scope-deviation evidence that says `No scope deviations`
- handoff validation rejects ready-outbox unresolved-blocker evidence that says `No blockers`
- Codex review gate surfaces non-`None` scope-deviation stand-ins as review issues

Latest focused verification:

- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_non_none_scope_deviation_stand_in tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_non_none_blocker_stand_in tests/test_codex_review_gate.py::test_review_gate_rejects_non_none_scope_deviation_stand_in -q` -> 3 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 608 passed
- `F:\claude-workspace\dayu-agent\.venv\Scripts\ruff.exe check utils/validate_handoff_docs.py utils/codex_review_gate.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `uv run --no-project python -m utils.validate_handoff_docs --json` -> ok
- `uv run --no-project python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `uv run --no-project python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py utils\codex_review_gate.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok with line-ending warnings only

## 2026-08-06: Review Checklist Scan Evidence Snippet Guard

Tightened `python -m utils.validate_handoff_docs` so the Codex review checklist must retain the Anti-Placeholder scan bullet-result wording introduced for ready outbox evidence. This keeps future checklist/template edits from weakening the scan evidence gate.

Covered cases:

- removing the scan bullet-result wording from `docs/handoff/codex_review_checklist.md` fails handoff validation
- existing review checklist evidence warnings remain protected

Latest focused verification:

- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_preserves_review_checklist_evidence_warnings -q` -> 8 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 605 passed
- `F:\claude-workspace\dayu-agent\.venv\Scripts\ruff.exe check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py` -> ok
- `uv run --no-project python -m utils.validate_handoff_docs --json` -> ok
- `uv run --no-project python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `uv run --no-project python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py tests\test_prepare_deepseek_task.py test_plan.md progress.md` -> ok with line-ending warnings only

## 2026-08-06: Anti-Placeholder Scan Bullet Evidence Guard

Tightened `python -m utils.validate_handoff_docs` so Anti-Placeholder scan evidence is parsed from fenced or backticked bullet command entries only. Ordinary prose that mentions an `rg` command no longer counts as a task scan command or as clean ready-outbox scan evidence.

Covered cases:

- ready outbox scan prose such as `Evidence: rg ... returned no matches` is rejected as missing parseable scan result evidence
- ready inbox scan prose such as `Use rg ... before returning the outbox` is rejected as missing a parseable scan command
- existing fenced ready-inbox scan commands and bullet ready-outbox scan result entries remain valid

Latest focused verification:

- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_non_bullet_scan_result tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_prose_scan_command -q` -> 2 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_non_bullet_scan_result tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_prose_scan_command tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_scan_result_marker_detached_from_scan_command_line tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_scan_missing_changed_file tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_scan_missing_allowed_file -q` -> 5 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py -q` -> 337 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 604 passed
- `F:\claude-workspace\dayu-agent\.venv\Scripts\ruff.exe check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `uv run --no-project python -m utils.validate_handoff_docs --json` -> ok
- `uv run --no-project python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `uv run --no-project python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py docs\handoff\codex_review_checklist.md test_plan.md progress.md` -> ok

## 2026-08-06: Ready Outbox Bullet Verification Result Guard

Tightened `python -m utils.validate_handoff_docs` so review-ready verification results must be parseable Markdown bullet entries with a backticked command followed by clean result evidence such as `exited 0`. Ordinary prose that merely mentions a backticked command and a clean exit marker no longer counts as runnable local verification evidence.

Covered cases:

- ready outbox verification prose such as `Evidence: command exited 0` is rejected as unparseable result evidence
- assigned command result evidence still ignores success markers that appear inside the backticked command text
- existing unparseable result evidence still reports missing pytest, ruff, and `git diff --check`

Latest focused verification:

- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_unparseable_ready_outbox_verification_results tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_non_bullet_verification_results tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_success_marker_inside_assigned_command_text -q` -> 3 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py -q` -> 335 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 602 passed
- `F:\claude-workspace\dayu-agent\.venv\Scripts\ruff.exe check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `uv run --no-project python -m utils.validate_handoff_docs --json` -> ok
- `uv run --no-project python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `uv run --no-project python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py docs\handoff\codex_review_checklist.md test_plan.md progress.md` -> ok

Implementation progress for DeepSeek-assigned tasks is recorded in `docs/handoff/deepseek_outbox.md`.

Codex review decisions should use `CODEX_REVIEW.md` and `docs/handoff/codex_review_checklist.md`.
Use `docs/handoff/codex_review_template.md` when a persistent review record is needed.

Do not treat progress claims as accepted completion. Completion requires Codex verification against the current `task.md` / `docs/handoff/deepseek_inbox.md` acceptance criteria.

## 2026-08-06: Ready Inbox Render Gate

Tightened `utils.prepare_deepseek_task.render_task()` so reusable ready-inbox rendering cannot return `READY_FOR_DEEPSEEK` text from an invalid task spec.

Covered cases:

- direct `render_task()` rejects invalid assignment metadata before returning inbox text
- valid ready-inbox rendering still satisfies the ready-inbox validator
- `validate_spec()` uses an internal unchecked renderer for structural validation, avoiding recursive validation
- test-plan text records that programmatic ready-inbox rendering must reject invalid specs before returning text

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py::test_render_task_rejects_invalid_spec -q` -> 1 ok
- `python -m pytest tests/test_prepare_deepseek_task.py::test_render_task_creates_ready_inbox_text -q` -> 1 ok
- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 597 ok
- `python -m pytest tests/test_prepare_deepseek_task.py -q` -> 75 ok
- `python -m ruff check utils/prepare_deepseek_task.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\prepare_deepseek_task.py tests\test_prepare_deepseek_task.py test_plan.md progress.md` -> ok with line-ending warnings only

## 2026-08-06: Waiting Outbox Render Gate

Tightened `utils.prepare_deepseek_task.render_waiting_outbox()` so reusable waiting-outbox rendering cannot return `WAITING_FOR_DEEPSEEK` text from an invalid task spec.

Covered cases:

- direct `render_waiting_outbox()` rejects invalid assignment metadata before returning outbox text
- the rejected invalid spec reports the shared task-spec validation issue
- `write_waiting_outbox()` remains covered by the same shared validation path
- test-plan text records that programmatic waiting-outbox rendering must reject invalid specs before returning text

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py::test_render_waiting_outbox_rejects_invalid_spec -q` -> 1 ok
- `python -m pytest tests/test_prepare_deepseek_task.py::test_write_waiting_outbox_rejects_invalid_spec_before_writing -q` -> 1 ok
- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 596 ok
- `python -m pytest tests/test_prepare_deepseek_task.py -q` -> 74 ok
- `python -m ruff check utils/prepare_deepseek_task.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\prepare_deepseek_task.py tests\test_prepare_deepseek_task.py test_plan.md progress.md` -> ok with line-ending warnings only

## 2026-08-06: Programmatic Waiting Outbox Gate

Tightened `utils.prepare_deepseek_task.write_waiting_outbox()` so direct programmatic callers cannot publish a `WAITING_FOR_DEEPSEEK` outbox from an invalid task spec.

Covered cases:

- direct `write_waiting_outbox()` rejects invalid assignment metadata before creating the outbox
- the rejected invalid spec reports the shared task-spec validation issue
- both task and waiting-outbox writes now use the same shared validation helper
- test-plan text records that programmatic waiting-outbox writes must reject invalid specs before outbox creation

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py::test_write_waiting_outbox_rejects_invalid_spec_before_writing -q` -> 1 ok
- `python -m pytest tests/test_prepare_deepseek_task.py::test_write_task_rejects_invalid_spec_before_writing -q` -> 1 ok
- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 595 ok
- `python -m pytest tests/test_prepare_deepseek_task.py -q` -> 73 ok
- `python -m ruff check utils/prepare_deepseek_task.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\prepare_deepseek_task.py tests\test_prepare_deepseek_task.py test_plan.md progress.md` -> ok with line-ending warnings only

## 2026-08-06: Programmatic Task Write Gate

Tightened `utils.prepare_deepseek_task.write_task()` so direct programmatic callers cannot bypass the same task-spec validation used by the CLI before writing `docs/handoff/deepseek_inbox.md`.

Covered cases:

- direct `write_task()` rejects an invalid spec before creating the inbox
- the rejected invalid spec reports the shared task-spec validation issue
- test-plan text records that programmatic task writes must reject invalid specs before inbox creation

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 594 ok
- `python -m ruff check utils/prepare_deepseek_task.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\prepare_deepseek_task.py tests\test_prepare_deepseek_task.py test_plan.md progress.md` -> ok with line-ending warnings only

## 2026-08-06: Spec-file UTF-8 Gate

Tightened JSON task-spec loading so non-UTF-8 spec-file content returns a controlled `deepseek task spec invalid` diagnostic instead of exposing the lower-level Python codec message in assignment logs.

Covered cases:

- spec-file parsing rejects invalid UTF-8 bytes with a stable UTF-8 JSON text diagnostic
- task spec schema and test-plan text record that `--spec-file` content must be UTF-8 JSON text
- required-snippet mirrors keep the UTF-8 rule visible in reusable handoff docs

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 593 ok
- `python -m ruff check utils/prepare_deepseek_task.py utils/validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\prepare_deepseek_task.py utils\validate_handoff_docs.py docs\handoff\deepseek_task_spec_schema.md tests\test_prepare_deepseek_task.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok with line-ending warnings only

## 2026-08-06: Spec-file Readability Gate

Tightened JSON task-spec loading so `--spec-file` paths that resolve to directories or otherwise cannot be read are converted into a controlled `deepseek task spec invalid` error instead of leaking a filesystem exception into the assignment flow.

Covered cases:

- spec-file parsing rejects a repository-local directory path with a readable-file diagnostic
- task spec schema and test-plan text record that `--spec-file` must target a readable JSON file, not a directory
- required-snippet mirrors keep the readable-file rule visible in reusable handoff docs

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 592 ok
- `python -m ruff check utils/prepare_deepseek_task.py utils/validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\prepare_deepseek_task.py utils\validate_handoff_docs.py docs\handoff\deepseek_task_spec_schema.md tests\test_prepare_deepseek_task.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok with line-ending warnings only

## 2026-08-06: Spec-file List Item Diagnostics

Tightened JSON task-spec parsing so a non-string entry inside a list field reports the exact field and 1-based item index, for example `allowed_files[2]`. This makes malformed DeepSeek assignment specs easier to audit without guessing which list entry caused the failure.

Covered cases:

- spec-file parsing rejects a mixed-type `allowed_files` list with a field/index-specific error
- task spec schema and test-plan text record the indexed list-item diagnostic rule
- required-snippet mirrors keep the schema diagnostic wording visible in reusable handoff docs

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 591 ok
- `python -m ruff check utils/prepare_deepseek_task.py utils/validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\prepare_deepseek_task.py utils\validate_handoff_docs.py docs\handoff\deepseek_task_spec_schema.md tests\test_prepare_deepseek_task.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok with line-ending warnings only

## 2026-08-06: Task Text Stand-in Gate

Tightened DeepSeek assignment validation so task-defining text cannot use empty stand-ins such as `None`, `N/A`, `TBD`, `unknown`, or `pending`. The rule now applies before generated tasks are written and when hand-written ready inbox files are checked.

Covered cases:

- structured task specs reject stand-ins in message id, task, objective, requirements, acceptance criteria, verification commands, and stop conditions
- hand-written ready inbox files reject stand-ins in metadata, objective, requirements, acceptance criteria, verification commands, and stop conditions
- checklist, workflow, task template, JSON spec schema, and test-plan text preserve the task-text stand-in rule

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 590 ok
- `python -m ruff check utils/prepare_deepseek_task.py utils/validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\prepare_deepseek_task.py utils\validate_handoff_docs.py docs\handoff\codex_review_checklist.md docs\handoff\dual_model_development_workflow.md docs\handoff\deepseek_task_template.md docs\handoff\deepseek_task_spec_schema.md tests\test_prepare_deepseek_task.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-06: Review Gate Handoff Control Baseline Gate

Tightened Codex review gate so post-assignment handoff control file changes, such as `DEEPSEEK_INBOX.md` and `CODEX_REVIEW.md`, are treated like workflow control changes: they must either appear in the assignment-time `## Worktree Baseline` or block review. `docs/handoff/deepseek_outbox.md` remains exempt because it is the expected DeepSeek handoff output.

Covered cases:

- unbaselined root handoff shortcut mutation is rejected during Codex review
- baselined root handoff shortcut mutations remain allowed
- checklist, workflow, and test-plan text preserve the handoff-control baseline rule

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 588 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\codex_review_gate.py utils\validate_handoff_docs.py docs\handoff\codex_review_checklist.md docs\handoff\dual_model_development_workflow.md tests\test_codex_review_gate.py tests\test_validate_handoff_docs.py tests\test_prepare_deepseek_task.py test_plan.md progress.md` -> ok

## 2026-08-06: Task Artifact Broad Scope Snippet Gate

Tightened reusable assignment-artifact validation so both `docs/handoff/deepseek_task_template.md` and `docs/handoff/deepseek_task_spec_schema.md` must preserve the warning that `allowed_files` cannot use broad top-level directory scopes such as `dayu`, `docs`, `src`, `tests`, `utils`, `.github`, or `workspace`.

This keeps the already-enforced broad-scope rule visible in the reusable template and JSON spec schema instead of relying only on generated-task validation.

Covered cases:

- handoff docs validation rejects a task template that drops the broad allowed-scope warning
- handoff docs validation rejects a JSON task-spec schema that drops the broad `allowed_files` warning
- task generation and Codex review tests remain green with the stricter required-snippet list

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_preserves_task_template_broad_scope_warning tests/test_validate_handoff_docs.py::test_validate_handoff_docs_preserves_task_spec_broad_scope_warning -q` -> 2 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 329 ok
- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 239 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-06: Ready Inbox Main Required Outbox Category Gate

Tightened ready-inbox assignment validation so `## Required Outbox` must list the same required evidence categories as `## Required Outbox Evidence`. This closes the gap where a hand-written DeepSeek assignment could describe complete evidence in the dedicated section while leaving the main outbox instructions too weak for the implementer-facing handoff.

The reusable workflow guide, Codex review checklist, and test plan now document the main `## Required Outbox` category requirement, and fixture copies used by handoff validation, task preparation, and review-gate tests preserve the same text.

Covered cases:

- ready inbox with complete `## Required Outbox Evidence` but incomplete `## Required Outbox` is rejected
- duplicate and missing-category checks still apply to the dedicated `## Required Outbox Evidence` section
- checklist, workflow, and test-plan text preserve the main outbox evidence-category requirement

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_without_required_outbox_categories tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_without_required_outbox_evidence_categories tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_with_incomplete_required_outbox_evidence_section tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_duplicate_ready_inbox_required_outbox_evidence -q` -> 4 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 566 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-06: Ready Inbox Scan Same-Line Evidence Requirement

Tightened ready-inbox assignment validation so `## Required Outbox Evidence` must explicitly require Anti-Placeholder clean result evidence on the same line as the parseable scan command. This prevents hand-written DeepSeek tasks from omitting the same-line scan-result rule that the generated task template already emits.

The standing DeepSeek inbox guidance, reusable workflow guide, Codex review checklist, and test plan now document the assignment-side requirement.

Covered cases:

- handoff docs validation rejects a ready inbox that omits the same-line Anti-Placeholder scan-result evidence requirement
- required outbox evidence category checks now include the same-line scan-result rule
- test fixtures for generated tasks, Codex review gate, and handoff validation preserve the same requirement

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_without_same_line_scan_result_requirement tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_without_required_outbox_evidence_categories tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_with_incomplete_required_outbox_evidence_section tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 4 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 565 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py utils\prepare_deepseek_task.py docs\handoff\codex_review_checklist.md docs\handoff\dual_model_development_workflow.md docs\handoff\deepseek_task_template.md docs\handoff\deepseek_inbox.md tests\test_validate_handoff_docs.py tests\test_prepare_deepseek_task.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-06: Anti-Placeholder Scan Same-Line Result Gate

Tightened Anti-Placeholder scan evidence so a clean result marker must appear on the same line as a parseable scanner command. A DeepSeek outbox that lists an `rg` scan command on one line and a detached `returned no matches` claim on another line is now rejected.

Generated DeepSeek tasks, the reusable workflow guide, the Codex review checklist, the DeepSeek task template, and the test plan now document that Anti-Placeholder clean result evidence must be attached to the parseable scan command line.

Covered cases:

- handoff docs validation rejects detached scan-result prose that is not on a parseable scan command line
- handoff docs validation still rejects scan-result markers hidden inside the backticked scan command text
- generated DeepSeek tasks include the same-line scan-result evidence warning

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_scan_result_marker_detached_from_scan_command_line tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_scan_result_marker_inside_scan_command_text tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 3 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 564 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py utils\prepare_deepseek_task.py docs\handoff\codex_review_checklist.md docs\handoff\dual_model_development_workflow.md docs\handoff\deepseek_task_template.md tests\test_validate_handoff_docs.py tests\test_prepare_deepseek_task.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-06: Anti-Placeholder Scan Result Boundary Gate

Tightened Anti-Placeholder scan result parsing so clean and failing scan-result markers are read from evidence prose outside the backticked scan command text. A DeepSeek outbox scan line that only contains `returned no matches` inside the command literal is now treated as missing clean scan-result evidence.

Generated DeepSeek tasks, the reusable workflow guide, the Codex review checklist, the DeepSeek task template, and the test plan now document that clean scan result markers inside backticked scan command text do not count as scan result evidence.

Covered cases:

- handoff docs validation rejects scan evidence whose only clean marker appears inside the scan command literal
- task template and Codex checklist validation preserve the scan-result boundary warning
- generated DeepSeek tasks include the scan-result boundary warning

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 560 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py utils\prepare_deepseek_task.py docs\handoff\codex_review_checklist.md docs\handoff\dual_model_development_workflow.md docs\handoff\deepseek_task_template.md tests\test_validate_handoff_docs.py tests\test_prepare_deepseek_task.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-06: Verification Result Text Boundary Gate

Tightened assigned-command result parsing so clean or failing result markers are read from evidence prose outside the backticked command text. A DeepSeek outbox line that only contains `exited 0` inside the command literal is now treated as missing clean result evidence.

Generated DeepSeek tasks, the reusable workflow guide, the Codex review checklist, the DeepSeek task template, and the test plan now document that clean result markers inside backticked command text do not count as verification evidence.

Covered cases:

- handoff docs validation rejects an assigned command whose only success marker appears inside the command literal
- Codex review gate rejects the same command-literal success-marker case
- ready inbox Required Outbox Evidence requires the command-text boundary rule
- generated DeepSeek tasks include the command-text boundary warning

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_success_marker_inside_assigned_command_text tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_without_required_outbox_evidence_categories tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_with_incomplete_required_outbox_evidence_section tests/test_codex_review_gate.py::test_review_gate_rejects_success_marker_inside_assigned_command_text tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 5 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 557 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py utils\codex_review_gate.py utils\prepare_deepseek_task.py docs\handoff\codex_review_checklist.md docs\handoff\dual_model_development_workflow.md docs\handoff\deepseek_task_template.md tests\test_validate_handoff_docs.py tests\test_prepare_deepseek_task.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-06: Substitute Verification Evidence Gate

Added a stricter assigned-command evidence guard for DeepSeek outbox review. `utils.validate_handoff_docs` and `utils.codex_review_gate` now reject result lines that claim dry-run, manual-only, simulated, synthetic, fabricated, invented, estimated, or not-actually-run verification even when the same line also contains `exited 0`.

Generated DeepSeek tasks now require outbox verification evidence to avoid those substitute-result claims. The reusable workflow guide, Codex review checklist, task template, and test plan now document the rule so future hand-written assignments and reviews preserve the same gate.

Covered cases:

- handoff docs validation rejects substitute assigned-command evidence with a clean exit marker
- Codex review gate rejects substitute assigned-command evidence with a clean exit marker
- ready inbox Required Outbox Evidence requires the substitute-result guard
- generated DeepSeek tasks include the substitute-result evidence warning

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_substitute_assigned_verification_result -q` -> 14 ok
- `python -m pytest tests/test_codex_review_gate.py::test_review_gate_rejects_substitute_assigned_verification_result -q` -> 14 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 555 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-06: Cross-Platform Continuation Guide Gate

Added a required handoff continuation guide for resuming the dual-model workflow from GitHub on another computer. The new guide records the workflow branch, clone and checkout commands, macOS/Linux environment setup, Windows environment setup, required JSON gate commands, and the rule that machine-local absolute paths must not be reused in task contracts.

Updated the handoff validator so `docs/handoff/cross_platform_continuation.md` is part of the required document set and must keep the GitHub, macOS/Linux, Windows, and gate-command sections. The main workflow guide now links to this continuation guide.

Covered cases:

- handoff docs validation rejects a missing cross-platform continuation guide
- handoff docs validation rejects removing the GitHub branch or clone commands
- handoff docs validation rejects removing macOS/Linux or Windows environment setup commands
- handoff docs validation rejects removing the three JSON gate commands

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_missing_cross_platform_continuation_doc tests/test_validate_handoff_docs.py::test_validate_handoff_docs_preserves_cross_platform_continuation_guide -q` -> 16 ok
- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 303 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 527 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- docs\handoff\cross_platform_continuation.md docs\handoff\dual_model_development_workflow.md utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py tests\test_prepare_deepseek_task.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-02: Anti-Placeholder Scan Variable Guard

Extended the shell variable expansion guard to Anti-Placeholder scanner commands.
Generated DeepSeek tasks, ready inbox scan commands, ready outbox scan evidence,
and reusable handoff docs now explicitly reject `$env:...`, `$NAME`, `${NAME}`,
and `%NAME%` forms in scan commands. This keeps scanner path coverage tied to
the recorded command rather than hidden shell-provided arguments.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_scan_variable_expansion tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_scan_variable_expansion tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 3 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 306 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py utils\prepare_deepseek_task.py docs\handoff\codex_review_checklist.md docs\handoff\dual_model_development_workflow.md docs\handoff\deepseek_task_template.md docs\handoff\deepseek_task_spec_schema.md tests\test_validate_handoff_docs.py tests\test_prepare_deepseek_task.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-02: DeepSeek Pro Route And Shell Variable Guard

Rechecked the operator request to move DeepSeek write routing from Flash to Pro.
The package scene manifests already keep `write`, `overview`, `regenerate`,
`fix`, and `repair` on `deepseek-v4-pro`, and a package manifest scan reported
no `deepseek-v4-flash` default. Historical workspace live-smoke artifacts were
left unchanged as audit records.

Added shared verification-command coverage for shell variable expansion. Ready
inbox commands, ready outbox evidence, and generated task specs now reject
`$env:...`, `$NAME`, `${NAME}`, and `%NAME%` forms so verification cannot import
hidden shell-provided flags.

Latest focused verification:

- package write-route scan -> no violations
- `python -m pytest tests/engine/test_prompt_assets.py::test_package_scene_manifests_do_not_default_to_deepseek_flash tests/engine/test_prompt_assets.py::test_write_scene_manifest_loads_fact_rules_fragment tests/engine/test_prompt_assets.py::test_overview_scene_manifest_disables_tools tests/engine/test_prompt_assets.py::test_regenerate_scene_manifest_registers_its_own_contract tests/engine/test_prompt_assets.py::test_fix_scene_manifest_registers_its_own_tools_and_contract tests/engine/test_prompt_assets.py::test_load_scene_manifest_reads_repair_manifest tests/cli/test_init_command.py::TestPromptDeepSeekSubOption::test_default_first_option_is_pro tests/cli/test_init_command.py::TestPromptDeepSeekSubOption::test_explicit_choice_flash -q` -> 8 ok
- `python -m pytest tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_shell_variable_expansion tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_shell_variable_expansion tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_shell_variable_expansion tests/test_validate_handoff_docs.py::test_shell_control_operator_parser_rejects_variable_expansion -q` -> 5 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 303 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/engine/test_prompt_assets.py tests/cli/test_init_command.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py utils\prepare_deepseek_task.py docs\handoff\codex_review_checklist.md docs\handoff\dual_model_development_workflow.md docs\handoff\deepseek_task_template.md docs\handoff\deepseek_task_spec_schema.md tests\test_validate_handoff_docs.py tests\test_prepare_deepseek_task.py tests\test_codex_review_gate.py test_plan.md progress.md dayu\config\prompts\manifests\write.json dayu\config\prompts\manifests\overview.json dayu\config\prompts\manifests\regenerate.json dayu\config\prompts\manifests\fix.json dayu\config\prompts\manifests\repair.json tests\engine\test_prompt_assets.py tests\cli\test_init_command.py` -> ok with line-ending warnings only

## 2026-08-01: Local Dual-Model Workflow Gates

Added local validation utilities for the DeepSeek/Codex workflow:

- `python -m utils.validate_handoff_docs`
- `python -m utils.codex_review_gate`
- `python -m utils.dual_model_pipeline_check`

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py -q` -> 16 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py` -> ok
- `python -m utils.dual_model_pipeline_check` -> ok for the current waiting-state outbox
- scoped blocked-term scan -> no matches
- scoped `sk-...` scan -> no matches

## 2026-08-01: Assigned DeepSeek Task Quality Gate

Enhanced `python -m utils.validate_handoff_docs` so `Status: READY_FOR_DEEPSEEK` inbox tasks must include:

- concrete `Message ID` and `Task`
- `CODEX_GATE: PASS`
- 1 to 5 allowed files
- at least one forbidden path
- at least 3 unchecked acceptance criteria
- verification commands for pytest, ruff, and `git diff --check`
- required outbox evidence mentioning `READY_FOR_CODEX_REVIEW`

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py -q` -> 18 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py` -> ok
- `python -m utils.dual_model_pipeline_check` -> ok

## 2026-08-01: Codex Review Scope Gate

Enhanced `python -m utils.codex_review_gate` so a ready outbox is checked against the assigned inbox scope:

- changed files outside `## Allowed Files` are rejected
- changed files under `## Forbidden Files` are rejected
- a ready outbox now requires the inbox to be `READY_FOR_DEEPSEEK`
- allowed and forbidden directory scopes match descendants

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py -q` -> 20 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py` -> ok
- `python -m utils.dual_model_pipeline_check` -> ok

## 2026-08-01: DeepSeek Task Preparation CLI

Added `python -m utils.prepare_deepseek_task` to render or write a bounded `READY_FOR_DEEPSEEK` inbox task from structured CLI arguments.

Key behavior:

- validates message id, task code, allowed files, forbidden files, acceptance criteria, and verification commands before writing
- supports `--dry-run` preview mode
- writes to `docs/handoff/deepseek_inbox.md` only after validation succeeds
- renders task text that satisfies the ready-inbox validator

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_prepare_deepseek_task.py -q` -> 25 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.dual_model_pipeline_check` -> ok

## 2026-08-01: DeepSeek Outbox Reset on Task Assignment

Enhanced `python -m utils.prepare_deepseek_task` with `--reset-outbox`.

Use case:

- Codex prepares a new task after a previous DeepSeek submission.
- The canonical inbox is written as `READY_FOR_DEEPSEEK`.
- The canonical outbox is reset to `WAITING_FOR_DEEPSEEK` with the same message id and task code.
- Stale `READY_FOR_CODEX_REVIEW` state is removed.

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py -q` -> 7 ok
- `python -m ruff check utils/prepare_deepseek_task.py tests/test_prepare_deepseek_task.py` -> ok

## 2026-08-01: Handoff State Machine Validation

Enhanced `python -m utils.validate_handoff_docs` with inbox/outbox lifecycle validation.

Valid state pairs:

- inbox `WAITING_FOR_TASK` with outbox `WAITING_FOR_TASK`
- inbox `READY_FOR_DEEPSEEK` with outbox `WAITING_FOR_DEEPSEEK`
- inbox `READY_FOR_DEEPSEEK` with outbox `READY_FOR_CODEX_REVIEW`

For assigned tasks, inbox and outbox message id and task code must match.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_prepare_deepseek_task.py -q` -> 29 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.dual_model_pipeline_check` -> ok

## 2026-08-01: Repository Validation After Task Assignment

Enhanced `python -m utils.prepare_deepseek_task` with `--validate-repository`.

Use case:

- Codex writes a new `READY_FOR_DEEPSEEK` inbox.
- The tool immediately runs full handoff validation.
- If Codex forgot `--reset-outbox`, lifecycle validation fails and reports the stale outbox state.

Recommended assignment flow:

```powershell
python -m utils.prepare_deepseek_task --dry-run ...
python -m utils.prepare_deepseek_task ... --reset-outbox --validate-repository
python -m utils.dual_model_pipeline_check
```

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_prepare_deepseek_task.py -q` -> 31 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.dual_model_pipeline_check` -> ok

## 2026-08-01: Task Assignment Rollback on Validation Failure

Enhanced `python -m utils.prepare_deepseek_task --validate-repository` so failed post-write repository validation restores the previous inbox/outbox files captured by the command.

This prevents a failed assignment from leaving the repository in a half-updated handoff state.

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py -q` -> 9 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_prepare_deepseek_task.py -q` -> 31 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.dual_model_pipeline_check` -> ok

## 2026-08-01: Safe Scope Path Validation

Enhanced ready-inbox validation and task preparation validation for allowed and forbidden scopes.

Rejected scope shapes:

- absolute paths
- parent-directory traversal
- duplicate scopes
- overlapping allowed and forbidden scopes

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 19 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_prepare_deepseek_task.py -q` -> 33 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.dual_model_pipeline_check` -> ok

## 2026-08-01: Machine-Readable Gate Reports

Enhanced local gates with JSON output for automation and CI consumers.

Commands:

- `python -m utils.validate_handoff_docs --json`
- `python -m utils.codex_review_gate --json`
- `python -m utils.dual_model_pipeline_check --json`

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_prepare_deepseek_task.py -q` -> 39 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok

## 2026-08-01: Focused Dual-Model GitHub Action

Added `.github/workflows/dual-model-gates.yml` as a lightweight CI entry point for DeepSeek/Codex handoff changes.
Added `tests/test_dual_model_gates_workflow.py` to keep the workflow wired to the focused tests and JSON gate commands.

The workflow runs:

- focused gate tests
- focused ruff checks
- JSON handoff validation
- JSON Codex review gate
- JSON pipeline gate

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 41 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- YAML parse check for `.github/workflows/dual-model-gates.yml` -> ok

## 2026-08-01: DeepSeek Assignment Examples

Added `docs/handoff/deepseek_assignment_examples.md` with safe `prepare_deepseek_task` usage:

- preview first with `--dry-run`
- write with `--reset-outbox --validate-repository`
- verify using JSON handoff and pipeline gates
- review ready submissions using JSON review gates

The examples document is now part of `python -m utils.validate_handoff_docs`.
The total pipeline text-health scan now also covers `.github/workflows/dual-model-gates.yml` and `tests/test_dual_model_gates_workflow.py`.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 42 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-01: Codex Review Checklist JSON Gates

Updated `docs/handoff/codex_review_checklist.md` so Codex review uses the JSON gate commands:

- `python -m utils.validate_handoff_docs --json`
- `python -m utils.codex_review_gate --json`
- `python -m utils.dual_model_pipeline_check --require-ready --json`

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 42 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Required-Reading Section Parity Guard

Enhanced ready inbox validation so `## Required Reading Before Editing` and `## Required Reading` must contain the same normalized path list. This prevents a hand-written assignment from telling DeepSeek to read one set of files before editing and a different set inside the task body.

Covered cases:

- hand-written ready inbox tasks with mismatched required-reading sections are rejected
- generated task text keeps both required-reading sections aligned from the same spec input
- documentation and test plan record the parity rule

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 79 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 136 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Reserved Path Scope Guard

Added a reserved path-scope guard so DeepSeek assignments cannot point allowed, forbidden, required-reading, worktree-baseline path entries, or changed-file evidence at VCS, dependency, virtualenv, or cache directories such as `.git`, `.venv`, `node_modules`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, and `site-packages`.

The same repository-relative path validator now treats those segments as unsafe path scope, while normal project paths remain unaffected. Generated task text and handoff documentation now tell DeepSeek not to use VCS, dependency, or cache directories in path fields.

Covered cases:

- ready inbox allowed scope rejects `.git/config`
- ready inbox allowed scope rejects `src/__pycache__/module.py`
- ready inbox forbidden scope rejects `node_modules/pkg/index.js`
- ready inbox required-reading rejects `.venv/pyvenv.cfg`
- task spec validation rejects the same reserved path scopes before rendering

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_unsafe_scope_paths tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_unsafe_ready_inbox_required_reading_paths tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_unsafe_scope_paths tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_unsafe_required_reading_paths tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 5 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 294 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/engine/test_prompt_assets.py tests/cli/test_init_command.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok

## 2026-08-02: Empty Test Suite Verification Evidence Guard

Tightened ready-outbox verification evidence so assigned pytest commands cannot be reported as clean when they collected no tests or deselected the suite. The shared verification failure markers now reject evidence containing `collected 0`, `no tests ran`, `no tests collected`, `empty test suite`, or deselection wording before accepting `exit 0` / `exited 0` as a clean result.

Covered cases:

- handoff docs validation rejects assigned command evidence such as `collected 0 items, exited 0`
- handoff docs validation rejects assigned command evidence such as `no tests ran, exited 0`
- handoff docs validation rejects assigned command evidence such as `2 deselected, exited 0`
- Codex review gate surfaces the same failures for ready outbox review

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_empty_suite_assigned_verification_result tests/test_codex_review_gate.py::test_review_gate_rejects_empty_suite_assigned_verification_result -q` -> 12 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 344 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-02: Partial Verification Evidence Guard

Extended assigned-command verification evidence checks so partial local runs cannot be recorded as complete evidence. Ready outbox evidence now treats partial-run, subset-run, smoke-only, sample-only, and not-full-suite wording as failing evidence even when the same line claims `exit 0` or `exited 0`.

Used phrase-level markers instead of broad single words so normal file paths such as `tests/test_partial_parser.py` or `tests/test_subset_rules.py` are not rejected merely because of their names.

Covered cases:

- handoff docs validation rejects assigned command evidence that says partial local verification and `exited 0`
- handoff docs validation rejects assigned command evidence that says subset run and `exited 0`
- handoff docs validation rejects assigned command evidence that says smoke-only or sample-only and `exited 0`
- Codex review gate surfaces the same failures for ready outbox review

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_partial_assigned_verification_result tests/test_codex_review_gate.py::test_review_gate_rejects_partial_assigned_verification_result -q` -> 20 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 378 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-02: Stale Verification Evidence Guard

Extended assigned-command verification evidence checks so old or cached local run summaries cannot stand in for current evidence. Ready outbox evidence now treats cached-result, prior-run, earlier-run, stale-result, not-rerun, and reused-result wording as failing evidence even when the same line claims `exit 0` or `exited 0`.

Used phrase-level markers instead of broad words so normal cache-directory path validation and unrelated history text stay unaffected.

Covered cases:

- handoff docs validation rejects assigned command evidence that says cached result and `exited 0`
- handoff docs validation rejects assigned command evidence that says prior run or earlier run and `exited 0`
- handoff docs validation rejects assigned command evidence that says stale result, not rerun, or reused result and `exited 0`
- Codex review gate surfaces the same failures for ready outbox review

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_stale_assigned_verification_result tests/test_codex_review_gate.py::test_review_gate_rejects_stale_assigned_verification_result -q` -> 28 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 406 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-02: Speculative Verification Evidence Guard

Extended assigned-command verification evidence checks so guessed local run outcomes cannot stand in for observed evidence. Ready outbox evidence now treats assumed-success, expected-success, would-succeed, should-succeed, likely-succeeded, and planned-result wording as failing evidence even when the same line claims `exit 0` or `exited 0`.

Used phrase-level markers rather than broad words such as `should`, `would`, or `likely`, so normal explanatory prose is not rejected by itself.

Covered cases:

- handoff docs validation rejects assigned command evidence that says assumed success and `exited 0`
- handoff docs validation rejects assigned command evidence that says expected success or likely success and `exited 0`
- handoff docs validation rejects assigned command evidence that says planned result and `exited 0`
- Codex review gate surfaces the same failures for ready outbox review

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_speculative_assigned_verification_result tests/test_codex_review_gate.py::test_review_gate_rejects_speculative_assigned_verification_result -q` -> 26 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 432 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-02: Environment Mismatch Verification Evidence Guard

Extended assigned-command verification evidence checks so local run summaries from the wrong execution context cannot stand in for project-local evidence. Ready outbox evidence now treats wrong-environment, non-project-venv, wrong-interpreter, missing-PYTHONPATH, and wrong-working-directory wording as failing evidence even when the same line claims `exit 0` or `exited 0`.

Used phrase-level markers instead of broad words such as `env`, `python`, or `cwd`, so normal explanatory prose and ordinary command paths are not rejected by themselves.

Covered cases:

- handoff docs validation rejects assigned command evidence that says wrong environment and `exited 0`
- handoff docs validation rejects assigned command evidence that says non-project venv or system Python and `exited 0`
- handoff docs validation rejects assigned command evidence that says missing PYTHONPATH or wrong working directory and `exited 0`
- Codex review gate surfaces the same failures for ready outbox review

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_environment_mismatch_assigned_verification_result tests/test_codex_review_gate.py::test_review_gate_rejects_environment_mismatch_assigned_verification_result -q` -> 50 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 482 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-02: Local Tooling Failure Verification Evidence Guard

Extended assigned-command verification evidence checks so local tooling failures cannot be reported as clean command results. Ready outbox evidence now treats command-not-found, module-missing, dependency-missing, import-unavailable, no-such-file, and permission-denied wording as failing evidence even when the same line claims `exit 0` or `exited 0`.

Used phrase-level markers rather than broad words such as `module`, `dependency`, or `file`, so normal test names and ordinary project paths are not rejected by themselves.

Covered cases:

- handoff docs validation rejects assigned command evidence that says command not found or not recognized as a command and `exited 0`
- handoff docs validation rejects assigned command evidence that says module missing, dependency missing, or package missing and `exited 0`
- handoff docs validation rejects assigned command evidence that says import unavailable, no such file, or permission denied and `exited 0`
- Codex review gate surfaces the same failures for ready outbox review

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_tooling_failure_assigned_verification_result tests/test_codex_review_gate.py::test_review_gate_rejects_tooling_failure_assigned_verification_result -q` -> 28 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 510 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-02: DeepSeek Pro Default Menu Guard

Rechecked the operator request to switch DeepSeek Flash to Pro. No business configuration change was needed: the package write-side scene manifests already default to `deepseek-v4-pro`, and the package/document scan found no `model.default_name` entries pointing at `deepseek-v4-flash`.

Added a CLI init regression test for the interactive DeepSeek sub-menu so pressing Enter keeps the Pro pair selected: `deepseek-v4-pro` for non-thinking work and `deepseek-v4-pro-thinking` for thinking work. Flash remains available only when explicitly selected.

Latest focused verification:

- `python -m pytest tests/cli/test_init_command.py::TestPromptDeepSeekSubOption tests/engine/test_prompt_assets.py::test_package_scene_manifests_do_not_default_to_deepseek_flash tests/engine/test_prompt_assets.py::test_overview_scene_manifest_disables_tools tests/engine/test_prompt_assets.py::test_load_scene_manifest_reads_repair_manifest tests/engine/test_prompt_assets.py::test_write_scene_manifest_loads_fact_rules_fragment tests/engine/test_prompt_assets.py::test_regenerate_scene_manifest_registers_its_own_contract tests/engine/test_prompt_assets.py::test_fix_scene_manifest_registers_its_own_tools_and_contract -q` -> 11 ok
- `python -m ruff check tests/cli/test_init_command.py tests/engine/test_prompt_assets.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- package/document scan for `default_name` pointing at `deepseek-v4-flash` -> no matches

## 2026-08-02: Interrupted Scanner Evidence Guard

Aligned Anti-Placeholder scan evidence with the interrupted verification evidence rule. Ready-outbox scan parsing now treats timeout, timed out, cancelled, canceled, interrupted, error, and errored wording as failing scan evidence even when the same line also claims `returned no matches`.

Covered cases:

- handoff validation rejects ready-outbox Anti-Placeholder scan evidence that says timed out, timeout, cancelled, interrupted, or error
- Codex review gate surfaces the same interrupted scan evidence via the inherited handoff validation issue
- skipped, not-scanned, and interrupted scanner evidence now share the same failing-evidence path
- test plan records timed-out, cancelled, interrupted, and errored scan wording as rejected ready-outbox scan evidence

Latest verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_interrupted_scan_result tests/test_codex_review_gate.py::test_review_gate_rejects_interrupted_scanner_evidence -q` -> 10 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 332 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok

## 2026-08-02: Interrupted Verification Evidence Guard

Tightened ready-outbox verification evidence so interrupted executions cannot be presented as clean local validation. Assigned-command result parsing now treats timeout, timed out, cancelled, canceled, interrupted, error, and errored wording as failing evidence even when the same line also contains a clean marker such as `exited 0`.

Covered cases:

- handoff validation rejects assigned pytest evidence that says timed out, timeout, cancelled, interrupted, or error
- Codex review gate surfaces the same interrupted verification evidence as both failing and lacking clean result
- conflicting clean/failing evidence behavior still blocks review
- test plan now records timed-out, cancelled, interrupted, and errored result wording as rejected assigned-command evidence

Latest verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_interrupted_assigned_verification_result tests/test_codex_review_gate.py::test_review_gate_rejects_interrupted_assigned_verification_result -q` -> 10 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 322 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok

## 2026-08-02: Scope Path Shell Metacharacter Guard

Moved another assignment-safety check earlier in the DeepSeek/Codex workflow: repository path values now reject shell metacharacters before a task can be rendered. This prevents values such as `src/example.py#L12`, `src/example.py;extra`, or `src/$NAME.py` from entering allowed scope, forbidden scope, changed-file evidence, required-reading paths, or generated Anti-Placeholder scan commands.

The generated task text, handoff workflow, Codex review checklist, task template, task spec schema, and test plan now preserve the same rule with wording that avoids angle-bracket symbols inside ready inbox content.

Covered cases:

- ready inbox allowed scope rejects hash, semicolon, and dollar-sign path values
- ready inbox forbidden scope rejects hash path values
- task spec validation rejects hash, semicolon, and dollar-sign path values before rendering
- rendered ready inbox text remains free of unresolved angle-bracket markers
- required-snippet validation preserves the shell-metacharacter path rule across handoff docs and reusable fixtures

Latest verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_unsafe_scope_paths tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_unsafe_scope_paths tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 3 ok
- `python -m pytest tests/test_prepare_deepseek_task.py::test_render_task_creates_ready_inbox_text tests/test_prepare_deepseek_task.py::test_render_task_keeps_required_reading_sections_in_sync tests/test_prepare_deepseek_task.py::test_main_dry_run_prints_task_without_writing -q` -> 3 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 312 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok

## 2026-08-02: Response File Argument Guard

Confirmed the operator request to keep package write-side scenes on DeepSeek Pro: `write`, `overview`, `regenerate`, `fix`, and `repair` all default to `deepseek-v4-pro`; `deepseek-v4-flash` remains only as an explicit selectable model entry, not a package default.

Tightened the DeepSeek/Codex handoff gates so verification commands and Anti-Placeholder scan commands reject response-file or PowerShell splatting style arguments such as `@args.txt`. This prevents a short-looking command from hiding extra pytest, ruff, scanner, or diff arguments outside the visible evidence line.

Covered cases:

- generated task verification command validation rejects `@args.txt` style response-file arguments
- ready inbox verification commands reject response-file arguments
- ready outbox verification evidence rejects response-file arguments
- ready inbox Anti-Placeholder scan commands reject response-file arguments and then fail path-token coverage
- ready outbox Anti-Placeholder scan evidence rejects response-file arguments and then fails changed-file coverage
- scanner diagnostics continue after shell-control or response-file findings so unresolved `<pattern>` markers remain visible
- docs and reusable templates preserve the no response-file or splatting wording

Latest verification:

- `python -m pytest tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_response_file_verification_arguments tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements tests/test_validate_handoff_docs.py::test_response_file_argument_parser_rejects_at_file_tokens tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_response_file_verification_argument tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_response_file_verification_argument tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_scan_response_file_argument tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_scan_response_file_argument -q` -> 7 ok
- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_scan_command_angle_marker tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_scan_response_file_argument tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_scan_response_file_argument -q` -> 3 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 312 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok

## 2026-08-02: DeepSeek Pro Route Confirmation

Rechecked the operator request to move DeepSeek Flash usage to Pro. Package write-side scene manifests for `write`, `overview`, `regenerate`, `fix`, and `repair` all resolve `model.default_name` to `deepseek-v4-pro`. No workspace override config exists in this checkout, so runtime defaults come from the package manifests.

Flash remains in the model catalog and write-side `allowed_names` only as an explicit operator-selected override, not as the default write route. Historical plans, fixtures, and audit text may still mention Flash for traceability.

Latest focused verification:

- package write scene route scan -> `write`, `overview`, `regenerate`, `fix`, and `repair` all use `deepseek-v4-pro`
- `python -m pytest tests/engine/test_prompt_assets.py::test_package_scene_manifests_do_not_default_to_deepseek_flash tests/engine/test_prompt_assets.py::test_write_scene_manifest_loads_fact_rules_fragment tests/engine/test_prompt_assets.py::test_load_scene_manifest_reads_repair_manifest tests/engine/test_prompt_assets.py::test_regenerate_scene_manifest_registers_its_own_contract tests/engine/test_prompt_assets.py::test_fix_scene_manifest_registers_its_own_tools_and_contract -q` -> 5 ok

## 2026-08-02: Pytest Config Override Verification Guard

Added shared unsafe verification coverage for pytest config and import override flags. The handoff validator now rejects `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, and `--pyargs`, including separated, equals, and attached `-o...` forms. The task generator, handoff workflow, review checklist, task template, spec schema, and test plan now describe the same rule so assignments and review gates use one policy.

Covered cases:

- task spec validation rejects pytest config and import override verification commands
- ready outbox verification evidence rejects pytest config and import override commands
- ready inbox verification commands reject pytest config and import override commands
- unsafe flag parser covers separated, equals, and attached short-option forms
- required-snippet checks keep the docs and generated task wording aligned

Verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_pytest_config_or_import_override_flags tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_pytest_config_or_import_override_flags tests/test_validate_handoff_docs.py::test_unsafe_verification_flag_parser_allows_python_module_runner tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_pytest_config_or_import_override_verification_flags tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 5 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 295 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 314 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok

## 2026-08-02: Shell Command Substitution Verification Guard

Added shared shell-control coverage for verification command substitution. The handoff validator now treats `$(` and backtick command substitution as shell-control operators, so direct-looking pytest, ruff, and diff-check commands cannot run hidden shell work before or during local verification. The generated task text, handoff workflow, review checklist, task template, spec schema, and test plan now describe the command-substitution rule.

Covered cases:

- task spec validation rejects verification commands containing `$(` or backtick command substitution
- ready outbox verification evidence rejects command substitution in parseable result lines
- ready inbox verification commands reject command substitution
- shell-control parser coverage confirms plain pytest commands remain accepted while substitution forms are rejected
- required-snippet checks keep the docs and generated task wording aligned

Verification:

- `python -m pytest tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_shell_command_substitution tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_shell_command_substitution tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_shell_command_substitution tests/test_validate_handoff_docs.py::test_shell_control_operator_parser_rejects_command_substitution -q` -> 5 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 299 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 318 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok

## 2026-08-02: DeepSeek Flash To Pro Recheck

Rechecked the operator request to switch DeepSeek Flash to Pro. Configuration stayed unchanged during this check: the packaged write-side scene manifests already default `write`, `overview`, `regenerate`, `fix`, and `repair` to `deepseek-v4-pro`, and the packaged scene manifests avoid `deepseek-v4-flash*` defaults. The DeepSeek init submenu also keeps Pro as the first/default sub-option, with Flash only remaining as an explicit selectable option and in historical fixtures/tests.

Verification:

- package manifest scan over `dayu/config/prompts/manifests/*.json` -> no write-side Pro violations and no `deepseek-v4-flash*` defaults
- `python -m pytest tests\engine\test_prompt_assets.py::test_package_scene_manifests_do_not_default_to_deepseek_flash tests\engine\test_prompt_assets.py::test_overview_scene_manifest_disables_tools tests\engine\test_prompt_assets.py::test_load_scene_manifest_reads_repair_manifest tests\engine\test_prompt_assets.py::test_write_scene_manifest_loads_fact_rules_fragment tests\engine\test_prompt_assets.py::test_regenerate_scene_manifest_registers_its_own_contract tests\engine\test_prompt_assets.py::test_fix_scene_manifest_registers_its_own_tools_and_contract tests\cli\test_init_command.py::TestPromptDeepSeekSubOption -q` -> 10 ok

## 2026-08-02: Pytest Node Selection Verification Guard

Closed a pytest narrowing gap in the DeepSeek/Codex verification gates. A command such as `python -m pytest tests/example.py::test_happy_path -q` previously matched the required pytest family and could mention the changed test file while still running only one test node. The shared unsafe verification parser now rejects tokens containing pytest node selectors (`::`), and the task generator, handoff docs, reusable snippets, and test plan all describe the rule.

Covered cases:

- task spec validation rejects pytest node-selection verification targets
- ready inbox verification commands reject pytest node-selection targets
- ready outbox verification result evidence rejects pytest node-selection targets
- parser coverage confirms ordinary file-level pytest commands remain valid while `tests/example.py::test_happy_path` and `tests/example.py::TestCase::test_happy_path` are unsafe
- required-snippet validation preserves the checklist, workflow, template, and schema wording

Latest verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_pytest_node_selection_targets tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_pytest_node_selection_targets tests/test_validate_handoff_docs.py::test_unsafe_verification_flag_parser_allows_python_module_runner tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_pytest_node_selection_verification_targets tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 5 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 292 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 311 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok

## 2026-08-02: Rule-Selection Verification Flag Guard And DeepSeek Pro Default Check

Confirmed the requested DeepSeek routing boundary: write-side package scene manifests keep `deepseek-v4-pro` as their default model, and a package scan found no `default_name` entries pointing to `deepseek-v4-flash`. DeepSeek Flash remains available only as an explicit selectable model.

Closed a verification loophole where DeepSeek handoff commands could run `ruff check` with rule-selection or config-override flags and still look like valid lint evidence. Generated tasks, ready inbox validation, and ready outbox evidence now reject flags such as `--select`, `--extend-select`, `--extend-ignore`, `--lint.select`, `--lint.ignore`, `--config`, `-c`, and `--isolated`.

Covered cases:

- task spec validation rejects ruff rule-selection and config-override verification commands
- ready inbox verification commands reject ruff rule-selection and config-override flags
- ready outbox verification result evidence rejects ruff rule-selection and config-override flags
- the unsafe flag parser covers separated and equals-form options such as `--select F401`, `--select=F401`, `--lint.select F401`, `--lint.ignore=E501`, `--config ruff.toml`, and `--isolated`
- handoff docs, generated task text, reusable templates, and the test plan all describe the same rule
- DeepSeek prompt manifests default write-side scenes to `deepseek-v4-pro`

Latest verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_rule_selection_or_config_override_flags tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_rule_selection_or_config_override_flags tests/test_validate_handoff_docs.py::test_unsafe_verification_flag_parser_allows_python_module_runner tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_rule_selection_or_config_override_verification_flags tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 5 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 289 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 308 ok
- `python -m pytest tests/engine/test_prompt_assets.py -q` -> 61 ok
- `python -m pytest tests/cli/test_init_command.py::TestPromptDeepSeekSubOption -q` -> 4 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok
- package prompt manifest scan for `default_name.*deepseek-v4-flash` -> no matches

## 2026-08-02: Rerun-Only And Early-Stop Verification Flag Guard

Tightened DeepSeek/Codex handoff verification so pytest commands that rerun a
subset or stop before the full suite completes cannot count as valid
verification. The unsafe flag parser now rejects rerun-only flags such as
`--lf`, `--last-failed`, `--ff`, and `--failed-first`, plus early-stop flags
such as `-x`, `--exitfirst`, `--maxfail`, `--stepwise`, and their aliases.

Updated generated task text, review checklist, workflow docs, task template,
task spec schema, and `test_plan.md` so DeepSeek receives the rule at
assignment time and Codex review keeps it as a reusable gate.

Covered cases:

- ready inbox validation rejects rerun-only and early-stop pytest commands
- ready outbox verification evidence rejects rerun-only and early-stop pytest commands
- spec-file task preparation rejects rerun-only and early-stop pytest commands
- direct unsafe-flag parser catches `-x`, `--exitfirst`, `--maxfail`, `--maxfail=1`, `--lf`, `--last-failed`, `--stepwise`, and aliases
- required-snippet validation preserves the checklist, workflow, template, and schema wording

Latest verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_rerun_only_or_early_stop_flags tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_rerun_only_or_early_stop_flags tests/test_validate_handoff_docs.py::test_unsafe_verification_flag_parser_allows_python_module_runner tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_rerun_only_or_early_stop_verification_flags tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 5 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 286 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 305 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok

## 2026-08-02: No-Run Verification Flag Guard And Pro Route Confirmation

Reconfirmed the operator request to route DeepSeek Flash to Pro. Package prompt
manifests have no `deepseek-v4-flash` default, and the DeepSeek init submenu
keeps Pro as the first/default option while Flash remains explicit-only.

Tightened handoff verification policy so DeepSeek cannot satisfy assignment
verification with no-run or mutating flags. Ready inbox commands, ready outbox
evidence, and spec-file task preparation now reject pytest listing/setup flags
such as `--co`, `--fixtures`, `--setup-only`, and `--setup-plan`, plus ruff
inspection or mutation flags such as `--fix-only`, `--add-noqa`, `--show-files`,
and `--show-settings`.

Covered cases:

- generated task text documents no-run and mutating verification flags
- task spec validation rejects pytest no-run and ruff mutating verification flags
- ready inbox validation rejects pytest no-run and ruff mutating verification flags
- ready outbox evidence rejects pytest no-run and ruff mutating verification flags
- direct unsafe-flag parser catches help/version/listing/setup/mutation flags
- package default tests keep DeepSeek write-side defaults on `deepseek-v4-pro`

Latest verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_no_run_or_mutating_verification_flags tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_no_run_or_mutating_verification_flags tests/test_validate_handoff_docs.py::test_unsafe_verification_flag_parser_allows_python_module_runner tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_no_run_or_mutating_verification_flags tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements tests/engine/test_prompt_assets.py::test_package_scene_manifests_do_not_default_to_deepseek_flash tests/cli/test_init_command.py::TestPromptDeepSeekSubOption::test_default_first_option_is_pro -q` -> 7 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 283 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/engine/test_prompt_assets.py::test_package_scene_manifests_do_not_default_to_deepseek_flash tests/cli/test_init_command.py::TestPromptDeepSeekSubOption::test_default_first_option_is_pro tests/cli/test_init_command.py::TestPromptDeepSeekSubOption::test_explicit_choice_flash -q` -> 305 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok

## 2026-08-02: Direct Verification Command Guard

Closed a verification-evidence bypass where DeepSeek could wrap assigned checks
behind shell launchers such as `powershell -Command`, `cmd /c`, or `bash -lc`.
The handoff validator now only treats pytest, ruff, and `git diff --check` as
covering commands when the verification line starts with the direct command
family (`pytest` / `python -m pytest`, `ruff` / `python -m ruff`, or
`git diff --check`). Wrapper lines are reported as explicit review issues and
also no longer satisfy required-command coverage.

Updated `utils.prepare_deepseek_task` so spec-driven assignments reject wrapped
verification commands before rendering the DeepSeek inbox. The generated task
text, Codex review checklist, dual-model workflow guide, task template, task
spec schema, and `test_plan.md` now document that verification commands must
start with direct command families rather than shell wrappers.

Covered cases:

- ready inbox verification commands reject wrapper invocations such as
  `powershell -Command python -m pytest`
- ready outbox verification evidence rejects wrapped command results even when
  the line claims `exited 0`
- generated task spec validation rejects wrapped pytest, ruff, and diff-check
  commands
- command-family matching still accepts direct `python -m pytest`,
  `python.exe -m ruff`, `py -m pytest`, and `git diff --check`

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_wrapped_verification_commands tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_wrapped_ready_outbox_verification_command tests/test_validate_handoff_docs.py::test_required_verification_command_matcher_rejects_shell_wrappers tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_wrapped_verification_commands tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 5 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 280 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 299 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Attached Short Verification Flag Guard

Confirmed the operator request to keep DeepSeek write-side routing on Pro: all
package prompt manifests resolve their write-side defaults (`write`, `overview`,
`regenerate`, `fix`, and `repair`) to `deepseek-v4-pro`, and no package
manifest default points to `deepseek-v4-flash`.

Tightened verification-command validation so attached pytest short filter forms
such as `-kslow` and `-mslow` are blocked in the same way as separated `-k` and
`-m` filter flags. The parser still allows legitimate module execution through
`python -m pytest` and `python -m ruff`, while rejecting filtering flags once
they belong to the verification command itself.

Updated the generated DeepSeek task text, handoff workflow, Codex review
checklist, task template, task spec schema, and test plan so both DeepSeek
implementers and Codex reviewers see the same no-filter/no-exclusion
verification rule before claiming completion.

Covered cases:

- ready inbox verification commands reject attached short filtering forms such
  as `-kslow` and `-mslow`
- ready outbox verification evidence rejects unsafe filtered commands
- DeepSeek task spec validation rejects attached short filtering forms
- direct parser checks preserve valid `python -m pytest` and `python -m ruff`
  runners
- DeepSeek Pro remains the package write-side default while Flash remains only
  an explicit selectable model or historical audit reference

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_unsafe_verification_flag_parser_allows_python_module_runner tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_unsafe_verification_flags tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_unsafe_verification_flags tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_unsafe_verification_flags tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements tests/test_codex_review_gate.py::test_review_gate_rejects_suffixed_assigned_verification_command -q` -> 6 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/engine/test_prompt_assets.py::test_package_scene_manifests_do_not_default_to_deepseek_flash tests/cli/test_init_command.py::TestPromptDeepSeekSubOption::test_default_first_option_is_pro tests/cli/test_init_command.py::TestPromptDeepSeekSubOption::test_explicit_choice_flash -q` -> 298 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok

## 2026-08-02: DeepSeek Pro Route Recheck

Rechecked the operator request to switch DeepSeek Flash to Pro. The active package route already uses Pro for write-side defaults: `write`, `overview`, `regenerate`, `fix`, and `repair` all resolve to `deepseek-v4-pro`. The DeepSeek init submenu also keeps Pro as the first/default sub-option, while Flash remains available only as an explicit low-cost choice.

Historical workspace routing snapshots and live-smoke plans that mention Flash were left untouched as audit records.

Latest focused verification:

- `python -m pytest tests/engine/test_prompt_assets.py::test_package_scene_manifests_do_not_default_to_deepseek_flash tests/cli/test_init_command.py::TestPromptDeepSeekSubOption::test_default_first_option_is_pro tests/cli/test_init_command.py::TestPromptDeepSeekSubOption::test_explicit_choice_flash -q` -> 3 ok
- package default scan for `deepseek-v4-flash` defaults outside historical workspace and plans -> no matches

## 2026-08-02: Filtering Verification Flag Guard

Expanded the handoff verification-command guard so ready inbox assignments, ready outbox evidence, Codex review, and generated task specs reject filtering or exclusion flags that can make a command look green while skipping target coverage. The blocked forms now include pytest-style filtering such as `-k`, pytest marker filtering such as `-m`, deselection such as `--deselect`, and file exclusion flags such as `--ignore` and `--exclude`.

Fixed the parser so normal module execution remains valid: `python -m pytest ...` and `python -m ruff ...` are not confused with pytest marker filtering.

Covered cases:

- ready inbox verification commands reject `pytest -k` and `ruff --exclude`
- ready outbox verification evidence rejects `pytest --deselect=...`
- task spec validation rejects `pytest -k` and `ruff --ignore=...`
- Codex review rejects suffixed assigned command evidence that uses `--deselect=...`
- parser regression keeps `python -m pytest` and `python -m ruff` valid

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_unsafe_verification_flag_parser_allows_python_module_runner tests/test_validate_handoff_docs.py::test_validate_handoff_docs_accepts_bounded_ready_inbox tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_unsafe_verification_flags tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_unsafe_verification_flags tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_unsafe_verification_flags tests/test_codex_review_gate.py::test_review_gate_rejects_suffixed_assigned_verification_command -q` -> 6 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 276 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 295 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/engine/test_prompt_assets.py tests/cli/test_init_command.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Embedded Whitespace Path Guard

Added an embedded-whitespace path guard so handoff path fields reject values such as `src/example file.py`, `private/generated file.py`, and `docs/with space.md`. This keeps DeepSeek assignment paths as single repository-relative tokens that can be matched reliably by verification commands, Anti-Placeholder scans, and scope checks.

The guard is implemented in the shared unsafe path predicate, so it applies consistently to ready inbox allowed and forbidden scope paths, required-reading sections, task spec paths, worktree baseline path entries after baseline empty markers are removed, and review-ready changed-file evidence after no-change markers are removed.

Updated generated task text, workflow docs, checklist, template, spec schema, required-snippet mirrors, and the test plan to document this rule.

Covered cases:

- ready inbox allowed scope rejects `src/example file.py`
- ready inbox forbidden scope rejects `private/generated file.py`
- ready inbox required-reading rejects `docs/with space.md`
- task spec validation rejects embedded-whitespace paths before assignment rendering
- generated DeepSeek task text tells workers path values must not contain embedded whitespace

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_unsafe_scope_paths tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_unsafe_ready_inbox_required_reading_paths tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_unsafe_scope_paths tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_unsafe_required_reading_paths tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 5 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 294 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/engine/test_prompt_assets.py tests/cli/test_init_command.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Anti-Placeholder Scan Command-Family Guard

Tightened the DeepSeek handoff validation so Anti-Placeholder scan evidence must name an actual `rg` or `rg.exe` scanner command, not a different command that merely mentions the scanner text. The rule now applies to both ready inbox assignments and ready outbox evidence.

Updated the generated task text, checklist, workflow guide, task template, task spec schema, and test fixtures so the assignment contract and review gate describe the same scanner-command boundary.

Covered cases:

- ready inbox validation rejects a scan command that starts with `Write-Output` while mentioning `rg`
- ready outbox validation rejects scan evidence that starts with `Write-Output` while mentioning `rg`
- generated DeepSeek assignments explicitly require the scan command to start with `rg` or `rg.exe`

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 202 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 279 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- boundary-aware key-shaped scanner over scoped files -> no matches
- scoped trailing-whitespace check -> ok

## 2026-08-02: DeepSeek Pro Default Regression Guard

Confirmed the active package scene manifests do not default to
`deepseek-v4-flash` or `deepseek-v4-flash-thinking`. Added a prompt asset
regression test that scans every package scene manifest and fails if any
`model.default_name` points back to a DeepSeek Flash variant.

DeepSeek Pro remains the write-side default route, and the DeepSeek init
sub-menu still keeps Pro as the first option. Flash remains registered and
selectable only when explicitly requested.

Latest focused verification:

- `python -m pytest tests/engine/test_prompt_assets.py tests/cli/test_init_command.py::TestPromptDeepSeekSubOption -q` -> 65 ok
- `python -m ruff check tests/engine/test_prompt_assets.py` -> ok
- package manifest default scan -> no DeepSeek Flash defaults
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Inbox Contract Stand-In Guard

Rechecked the active DeepSeek write route before continuing: package write-side
manifests for `write`, `overview`, `regenerate`, `fix`, and `repair` resolve to
`deepseek-v4-pro` by default, with Flash remaining only as an explicit selectable
low-cost model.

Enhanced `python -m utils.validate_handoff_docs` so ready DeepSeek inbox input
and output contract items cannot be empty stand-ins such as None, N/A, TBD, or
unknown. This closes the hand-written assignment gap where an inbox could expose
the contract headings while still carrying no useful boundary.

Updated the review checklist, workflow guide, task template, task spec schema,
and task-generation fixtures so future DeepSeek assignments keep the same
contract wording. The generated/spec assignment path is covered by final
ready-inbox validation, so CLI-rendered tasks and hand-written inboxes use the
same rule.

Covered cases:

- ready inbox validation rejects input contract stand-ins
- ready inbox validation rejects output contract stand-ins
- task spec validation rejects contract stand-ins before assignment rendering
- required handoff docs preserve the contract stand-in rule

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 254 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 273 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Inbox Input and Output Contract Guard

Added a ready-inbox contract gate for DeepSeek assignments. A
`READY_FOR_DEEPSEEK` inbox now must include non-empty `## Input Contracts` and
`## Output Contracts` sections, and each section must use distinct bullet
items. This keeps hand-written assignments from reaching DeepSeek without an
explicit interface and artifact boundary.

Updated `utils.prepare_deepseek_task` so generated tasks render both sections by
default and can extend them through CLI arguments or JSON task specs. The
handoff checklist, workflow guide, task schema, focused fixtures, and
`test_plan.md` now document and protect the same contract.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 252 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 271 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- contract keyword check over scoped files -> expected references present
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: DeepSeek Write Default Confirmed on Pro

Confirmed the package write-side model route is on `deepseek-v4-pro` rather than
`deepseek-v4-flash`. The five write-side manifests resolve to Pro by default:
`write`, `overview`, `regenerate`, `fix`, and `repair`.

Also checked the DeepSeek init sub-option order: `pro` remains the first and
recommended DeepSeek choice, while `flash` remains available only as an explicit
low-cost option. Updated the stale plan text that still described Flash as the
write default, so the durable project notes match the current route.

Latest focused verification:

- `python -m pytest tests/engine/test_prompt_assets.py tests/cli/test_init_command.py::TestPromptDeepSeekSubOption -q` -> 64 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `rg '"default_name"\s*:\s*"deepseek-v4-flash' dayu docs tests README.md progress.md test_plan.md -g "*.json" -g "*.py" -g "*.md"` -> no matches
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Outbox Concrete Summary Evidence Guard

Confirmed the DeepSeek write-side route remains on `deepseek-v4-pro`, with `deepseek-v4-flash` still available only as an explicit selectable model. The write-side manifests for `write`, `overview`, and `regenerate` are defaulted to `deepseek-v4-pro`, and the DeepSeek init sub-option order keeps Pro first.

Enhanced `python -m utils.validate_handoff_docs` so a review-ready DeepSeek outbox must include a concrete `## Summary` section with at least two bullet items. Summary items that only state generic completion wording are rejected before Codex review starts.

Updated generated DeepSeek assignments, the task template, the task spec schema, the review checklist, the workflow guide, and the test plan so future tasks require the same concrete summary evidence.

Covered cases:

- ready outbox validation rejects a summary with fewer than two bullet items
- ready outbox validation rejects generic completion-only summary wording
- ready inbox required outbox evidence must mention a concrete ready-outbox summary
- generated DeepSeek tasks include concrete summary evidence requirements
- handoff docs require at least eight outbox evidence bullet items

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 248 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 267 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: DeepSeek Pro Write Route Confirmation

Confirmed the current package write-side route uses `deepseek-v4-pro` for write scenes while keeping Flash selectable for explicit low-cost runs. Updated the live-smoke planning note to use DeepSeek Pro artifact names and marked the older Flash-default plan as superseded audit context.

Covered cases:

- write-side scene manifests remain defaulted to `deepseek-v4-pro`
- DeepSeek init sub-option ordering keeps Pro as the default first option
- Flash remains available in allowed model lists instead of being removed
- current live-smoke planning docs no longer describe Flash as the active write route

Latest focused verification:

- `python -m pytest tests/engine/test_prompt_assets.py tests/cli/test_init_command.py::TestPromptDeepSeekSubOption -q` -> 64 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 265 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/engine/test_prompt_assets.py tests/cli/test_init_command.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Codex Review Stale Worktree Baseline Guard

Enhanced `python -m utils.codex_review_gate` so review-ready worktree baseline entries must still be dirty in git status before they can suppress worktree disclosure issues. A stale or hand-written baseline path that is not currently dirty now blocks Codex review instead of silently granting an exemption.

Updated the review checklist, workflow guide, and required-snippet fixtures to preserve the rule that review-ready baseline entries must still be dirty in git status.

Covered cases:

- Codex review rejects a baseline path that is not dirty in current git status
- existing baseline-ignore behavior still works for a non-assigned dirty path recorded in the baseline
- required handoff docs preserve the stale-baseline review rule

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 58 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 188 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 265 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Outbox Workflow-Control Changed-File Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready outbox changed-file evidence cannot list workflow control files such as `progress.md`, root task plans, handoff docs, gate utilities, or CI gates. Codex review already rejected these entries; the repository-level handoff validator now catches them earlier in the pipeline.

Generated DeepSeek tasks, the task template, the review checklist, and the workflow guide now tell DeepSeek that changed-file evidence must not list workflow control files.

Covered cases:

- ready outbox changed-file evidence rejects workflow control files
- generated task text includes the changed-file workflow-control evidence rule
- required handoff docs preserve the ready-outbox workflow-control changed-file rule

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 188 ok
- `python -m pytest tests/test_codex_review_gate.py -q` -> 57 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 264 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Worktree Baseline Allowed-Scope Guard

Enhanced ready inbox validation and DeepSeek task rendering so assignment-time worktree baseline paths cannot overlap the assigned allowed scope. This prevents a pre-existing dirty file from being assigned to DeepSeek in a way that could hide later implementation changes behind the baseline exemption.

Generated task text, the task template, the task spec schema, the review checklist, and the workflow guide now document that baseline entries must not overlap allowed files.

Covered cases:

- ready inbox validation rejects baseline entries that overlap exact allowed files or parent allowed directories
- task rendering rejects baseline paths that overlap assigned allowed files before writing the inbox
- dry-run task generation records unrelated dirty files in baseline but rejects dirty assigned files
- Codex review baseline-ignore coverage now uses a non-assigned dirty baseline path

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 187 ok
- `python -m pytest tests/test_codex_review_gate.py -q` -> 57 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 263 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: DeepSeek Pro Init And Temperature Guard

Aligned the init package-manifest role inference comment and README manifest example with the current `deepseek-v4-pro` write default. Flash remains listed as an explicit selectable write-side model.

Lowered `deepseek-v4-pro` and `deepseek-v4-pro-thinking` write temperature profiles to 0.8, matching the research-writing conservatism already enforced for Flash. Expanded the prompt asset test so both DeepSeek Pro and Flash variants stay covered by the same write-temperature guard.

Rewrote the context-overflow structured-error fallback in `dayu/engine/async_openai_runner.py` without a bare empty branch, preserving the same text fallback behavior while keeping the scoped handoff scanner quieter for future DeepSeek assignments.

Latest focused verification:

- `python -m pytest tests/engine/test_prompt_assets.py tests/engine/test_prompt_composer.py tests/cli/test_init_command.py -q` -> 239 ok
- `python -m pytest tests/engine/test_context_budget.py tests/engine/test_prompt_assets.py tests/engine/test_prompt_composer.py tests/cli/test_init_command.py -q` -> 302 ok
- `python -m ruff check dayu/cli/commands/init.py tests/engine/test_prompt_assets.py` -> ok
- `python -m ruff check dayu/engine/async_openai_runner.py dayu/cli/commands/init.py tests/engine/test_prompt_assets.py` -> ok
- JSON parse check for `llm_models.json` and write-side manifests -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: DeepSeek Pro Write Defaults

Switched the package write-side scene defaults from `deepseek-v4-flash` to `deepseek-v4-pro` for `write`, `overview`, `regenerate`, `fix`, and `repair`. Flash remains in each scene `allowed_names` list for explicit low-cost runs, while the default path now targets Pro quality.

Updated the prompt asset boundary test and user-facing configuration docs so they describe `deepseek-v4-pro` as the current write-side default. DeepSeek thinking examples for manual commands now use `deepseek-v4-pro-thinking`.

Latest focused verification:

- `python -m pytest tests/engine/test_prompt_assets.py tests/engine/test_prompt_composer.py -q` -> 93 ok
- `python -m pytest tests/engine/test_prompt_assets.py tests/engine/test_prompt_composer.py tests/cli/test_init_command.py -q` -> 239 ok
- `python -m ruff check dayu/engine/async_openai_runner.py tests/engine/test_prompt_assets.py tests/engine/test_prompt_composer.py` -> ok
- JSON parse check for the five write-side scene manifests and `llm_models.json` -> ok
- default Flash reference scan across active README, config, tests, handoff docs, and runner examples -> no matches

## 2026-08-02: Ready Inbox Diff-Check Directory Scope Guard

Enhanced ready inbox validation so assigned `git diff --check` commands must mention every allowed file or directory scope as a path token. This closes the gap where a directory-scoped DeepSeek task could include a diff-check for only an unrelated concrete file.

Updated generated-task docs, checklist fixtures, and Codex review fixtures so directory-scope assignments also report exact outbox command results that cover both the directory scope and concrete changed files.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_diff_check_missing_allowed_directory tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_diff_check_missing_allowed_directory -q` -> 2 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 255 ok
- `python -m ruff check tests/test_codex_review_gate.py utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Workflow Required-Snippet Parity Guard

Closed a documentation-gate parity gap by adding the ready inbox directory-scope diff-check wording to the workflow required snippets in `utils.validate_handoff_docs`. The real workflow guide already had the rule; this change makes future removal detectable by repository validation.

Added the same wording to the workflow-preservation regression so the required snippet itself stays covered.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_preserves_workflow_evidence_warnings -q` -> 8 ok
- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 131 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok

## 2026-08-02: Ready Outbox Scan Command Coverage Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready DeepSeek outbox Anti-Placeholder coverage is checked against the actual scanner command, not explanatory note text in the scan section. This prevents a scan over unrelated paths from satisfying changed-file coverage by mentioning the missing file only in prose.

Covered cases:

- ready outbox validation rejects scanner coverage when the changed file appears only in note text
- ready outbox validation still accepts one scanner command covering multiple changed files
- review checklist, generated-task contract snippets, and the test plan use command-specific scanner coverage wording

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 122 ok
- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 105 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 246 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Scan Command Safety Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready DeepSeek outbox Anti-Placeholder scan commands must be exact command entries without shell control operators, shell redirection, or unresolved angle-bracket markers. This closes the gap where scanner output could be hidden in side files or an assignment-style marker could remain in a claimed clean scan.

Covered cases:

- ready outbox validation rejects Anti-Placeholder scanner commands using shell redirection
- ready outbox validation rejects Anti-Placeholder scanner commands with unresolved angle-bracket markers
- generated DeepSeek tasks require exact Anti-Placeholder scan commands in both required outbox sections
- reusable checklist, workflow guide, task template, and test plan document scan-command safety

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 233 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 252 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Changed-File Existence Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready DeepSeek outbox changed-file entries must point to files when validation runs against a repository root. This moves directory and missing-file detection into the lightweight handoff validator instead of waiting for the Codex review gate.

Covered cases:

- ready outbox validation rejects a changed-file entry that points to a directory
- ready outbox validation rejects a changed-file entry that points to a missing file
- ready outbox validation still accepts the default concrete changed-file fixture

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 129 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 253 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Inbox Verification Coverage Guard

Enhanced `python -m utils.validate_handoff_docs` so ready DeepSeek inbox tasks must assign verification commands that mention every concrete allowed file as a path token. This catches under-scoped assignment commands before DeepSeek starts work, instead of waiting for Codex review of the outbox.

Updated the task generator, review checklist, workflow guide, task template, spec schema, and test plan so the new assignment-time coverage rule is protected by required snippets and visible in generated tasks.

Covered cases:

- ready inbox validation rejects `git diff --check` commands that omit an allowed file
- ready inbox validation rejects `ruff check` commands that omit an allowed Python file
- ready inbox validation rejects `pytest` commands that omit an allowed test file
- generated DeepSeek task validation inherits the same allowed-file coverage rule
- rendered DeepSeek task text includes the allowed-file command coverage instruction

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 157 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 231 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Verification Command Inline Comment Guard

Tightened verification command shape checks so `#` is treated as a shell control or comment operator. This prevents a task assignment from listing a required allowed path only in an inline comment while running a narrower command.

Covered cases:

- ready inbox validation rejects verification commands with inline comments
- generated DeepSeek task validation rejects verification commands with inline comments

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 159 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 233 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok

## 2026-08-02: Git Diff Pathspec Delimiter Guard

Tightened `git diff --check` command validation so assignment commands and review evidence that include pathspecs must use `--` before the path list. Commands missing the delimiter are removed from usable verification evidence and reported as issues.

Covered cases:

- ready inbox validation rejects `git diff --check` commands with pathspecs but no `--`
- ready outbox validation rejects `git diff --check` result evidence with pathspecs but no `--`
- generated DeepSeek task validation inherits the same diff-check delimiter rule

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 162 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 236 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok

## 2026-08-02: Unsafe Verification Flag Guard

Tightened verification command validation so unsafe flags such as `--collect-only`, `--exit-zero`, `--fix`, and `--unsafe-fixes` are rejected in ready inbox assignments, ready outbox evidence, and generated task specs. These commands are removed from usable verification evidence before required-command matching and coverage checks run.

Covered cases:

- ready inbox validation rejects unsafe verification flags
- ready outbox validation rejects unsafe verification flags
- generated DeepSeek task validation rejects unsafe verification flags
- ready inbox and outbox validation reject mutating verification flags
- generated DeepSeek task validation rejects mutating verification flags

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 168 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 242 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok

## 2026-08-02: Verification Command Redirection Guard

Tightened verification command validation so shell redirection operators are rejected in ready inbox assignments, ready outbox evidence, and generated task specs. This prevents verification output from being hidden in side files or commands from reading unexpected external input while still claiming a clean result.

Covered cases:

- ready inbox validation rejects redirected verification commands
- ready outbox validation rejects redirected verification commands
- generated DeepSeek task validation rejects redirected verification commands

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 171 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 245 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok

## 2026-08-02: Ready Outbox Coverage-Specific Clean Result Guard

Enhanced `python -m utils.validate_handoff_docs` so changed-file coverage evidence must be clean on the result line that covers the changed path. A clean result from another pytest, ruff, or diff-check command no longer offsets a failing result for the changed file itself.

Applied the coverage-specific clean-result check to:

- `pytest` evidence for changed test Python files
- `ruff check` evidence for changed Python files
- `git diff --check` evidence for all changed files

Updated the review checklist, workflow guide, required snippets, and test plan so coverage-specific clean results are part of the reusable handoff contract.

Covered cases:

- ready outbox validation rejects failing `pytest` evidence for a changed test Python file even when another pytest command is clean
- ready outbox validation rejects failing `ruff check` evidence for a changed Python file even when another ruff command is clean
- ready outbox validation rejects failing `git diff --check` evidence for a changed file even when another diff-check command is clean
- required snippets document coverage-specific clean-result wording

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 109 ok
- `python -m utils.validate_handoff_docs --json` -> ok

Latest full verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 227 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Path-Token Coverage Guard

Enhanced `python -m utils.validate_handoff_docs` so changed-file coverage evidence must mention files as path tokens, not merely as substrings inside longer filenames. This prevents `src/example.py.bak` or `tests/example.py.old` from satisfying evidence for `src/example.py` or `tests/example.py`.

Applied the stricter path-token matcher to:

- `pytest` evidence for changed test Python files
- `ruff check` evidence for changed Python files
- `git diff --check` evidence for all changed files
- Anti-Placeholder scan evidence for all changed files

Updated the review checklist, workflow guide, required snippets, and test plan so path-token coverage is part of the reusable handoff contract.

Covered cases:

- ready outbox validation rejects suffixed `pytest` paths for changed test Python files
- ready outbox validation rejects suffixed `ruff check` paths for changed Python files
- ready outbox validation rejects suffixed `git diff --check` paths for changed files
- ready outbox validation rejects suffixed Anti-Placeholder scan paths for changed files
- required snippets document path-token coverage wording

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 106 ok
- `python -m utils.validate_handoff_docs --json` -> ok

Latest full verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 224 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Pytest Coverage Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready DeepSeek outbox `pytest` evidence must mention every test Python file under `tests/` listed in `## Changed Files`. This closes the gap where a worker could change a test file while only reporting a clean pytest result for unrelated tests.

Updated the review checklist, workflow guide, required snippets, and test plan so pytest coverage for changed test files is part of the reusable handoff contract.

Covered cases:

- ready outbox validation rejects `pytest` evidence that omits a changed test Python file
- required snippets document pytest coverage for changed test Python files

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 102 ok
- `python -m utils.validate_handoff_docs --json` -> ok

Latest full verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 220 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Ruff Coverage Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready DeepSeek outbox `ruff check` evidence must mention every Python file listed in `## Changed Files`. This closes the gap where a worker could report a clean lint result for unrelated Python paths while submitting a different Python file.

Updated the review checklist, workflow guide, required snippets, and test plan so ruff coverage for changed Python files is part of the reusable handoff contract.

Covered cases:

- ready outbox validation rejects `ruff check` evidence that omits a changed Python file
- required snippets document ruff coverage for changed Python files

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 101 ok
- `python -m utils.validate_handoff_docs --json` -> ok

Latest full verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 219 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Diff-Check Coverage Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready DeepSeek outbox `git diff --check` evidence must mention every file listed in `## Changed Files`. This closes the gap where a worker could report a clean whitespace check for unrelated paths while submitting a different changed file.

Updated the review checklist, workflow guide, required snippets, and test plan so diff-check coverage for changed files is part of the reusable handoff contract.

Covered cases:

- ready outbox validation rejects `git diff --check` evidence that omits a changed file
- required snippets document diff-check coverage for changed files

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 100 ok
- `python -m utils.validate_handoff_docs --json` -> ok

Latest full verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 218 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Outbox Anti-Placeholder Scan Coverage Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready DeepSeek outbox Anti-Placeholder scan evidence must mention every file listed in `## Changed Files`. This prevents a clean scanner result for unrelated paths from satisfying the handoff.

Updated the review checklist, workflow guide, required snippets, and test plan so scan coverage for changed files is part of the reusable handoff contract.

Covered cases:

- ready outbox validation rejects Anti-Placeholder scan evidence that omits a changed file
- ready outbox validation accepts one scan command covering multiple changed files
- required snippets document scan coverage for changed files

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 99 ok
- `python -m utils.validate_handoff_docs --json` -> ok

Latest full verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 217 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Inbox Acceptance Uniqueness Guard

Enhanced `python -m utils.validate_handoff_docs` so ready DeepSeek inbox tasks reject duplicate unchecked acceptance criteria. This keeps the minimum acceptance-count rule meaningful when tasks are hand-written or rendered from a spec file.

Updated the review checklist, workflow guide, task template, and task spec schema so acceptance-criteria uniqueness is documented and protected by required snippets.

Covered cases:

- ready inbox validation rejects duplicate unchecked acceptance criteria
- generated task spec validation rejects duplicate acceptance criteria before writing
- reusable task template records acceptance-criteria uniqueness
- task spec schema records acceptance-criteria uniqueness

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 125 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 199 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Inbox Requirements Quality Guard

Enhanced `python -m utils.validate_handoff_docs` so ready DeepSeek inbox tasks must include at least three numbered requirements, and those requirements must be unique. `python -m utils.prepare_deepseek_task` now rejects generated task specs with fewer than three requirements or repeated requirement text before writing an assignment.

Updated the review checklist, workflow guide, task template, and task spec schema so the requirements count and uniqueness contract is documented and protected by required snippets.

Covered cases:

- ready inbox validation rejects fewer than three numbered requirements
- ready inbox validation rejects duplicate numbered requirements
- generated task spec validation rejects fewer than three requirements
- generated task spec validation rejects duplicate requirements
- reusable task template records requirements count and uniqueness wording
- task spec schema records requirements count and uniqueness wording

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 130 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 204 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Changed-File Scope Guard

Enhanced `python -m utils.validate_handoff_docs` so ready DeepSeek outbox changed files are checked against the assigned ready inbox scope. Changed files must stay within the ready inbox allowed files and must not touch any forbidden files, giving the document gate the same early scope protection as the Codex review gate.

Updated the review checklist, workflow guide, and required snippets so changed-file scope matching is part of the reusable handoff contract.

Covered cases:

- ready outbox validation rejects changed files outside assigned allowed scope
- ready outbox validation rejects changed files inside assigned forbidden scope
- required snippets document changed-file scope matching in the checklist and workflow guide

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 97 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 215 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Exact Assigned-Command Verification Guard

Enhanced `python -m utils.validate_handoff_docs` so a ready DeepSeek outbox must include result evidence for every exact verification command assigned in the ready inbox. Command-family evidence is still checked, but it no longer allows an outbox to replace `python -m pytest tests/assigned.py -q` with a different pytest command or hide a failing assigned command behind another clean line.

Updated the workflow guide and required snippets so exact assigned-command matching is part of the reusable handoff contract.

Covered cases:

- ready outbox validation rejects a missing exact assigned verification command result
- ready outbox validation rejects a failing exact assigned verification command result
- a clean alternate command in the same command family does not satisfy a failed assigned command
- required snippets document exact assigned-command verification evidence

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 95 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 213 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Assigned-Acceptance Coverage Guard

Enhanced `python -m utils.validate_handoff_docs` so a ready DeepSeek outbox is checked against the assigned ready inbox acceptance criteria. Each assigned inbox criterion must have checked `- [x] ...` outbox evidence that starts with that criterion, matching the stricter Codex review gate behavior earlier in the pipeline.

Updated the workflow guide and required snippets so checked outbox acceptance evidence must cover every assigned inbox criterion, not merely include some checked items.

Covered cases:

- ready outbox validation rejects missing checked evidence for an assigned inbox acceptance criterion
- ready outbox checked evidence still rejects generic summaries and negative completion wording
- required snippets document assigned-criterion coverage in the checklist and workflow guide

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 93 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 211 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Required Outbox Evidence Bullet Guard

Enhanced `python -m utils.validate_handoff_docs` so ready DeepSeek inbox `## Required Outbox Evidence` sections must contain at least six bullet items and each evidence bullet must be unique. The validator still checks that the section mentions changed files, verification commands, checked acceptance, scan evidence, scope deviations, and unresolved questions or blockers.

Updated the review checklist and workflow guide so required outbox evidence cannot be compressed into one vague line or repeated evidence entries.

Covered cases:

- ready inbox validation rejects fewer than six required outbox evidence bullet items
- ready inbox validation rejects duplicate required outbox evidence bullet items
- required snippets document the evidence bullet count and uniqueness contract

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 92 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 210 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Inbox Acceptance-Criteria Quality Guard

Enhanced `python -m utils.prepare_deepseek_task` so generated task specs reject repeated acceptance criteria before writing an assignment. The ready inbox validator already enforced at least three unchecked acceptance items and duplicate detection; this round adds focused coverage for too few ready inbox acceptance items and updates the reusable wording so the count and uniqueness contract is visible everywhere.

Updated the review checklist, workflow guide, task template, and task spec schema so acceptance criteria must be unique and include at least three unchecked items.

Covered cases:

- ready inbox validation rejects fewer than three unchecked acceptance criteria
- ready inbox validation rejects duplicate unchecked acceptance criteria
- generated task spec validation rejects fewer than three acceptance criteria
- generated task spec validation rejects duplicate acceptance criteria before writing
- reusable task template records acceptance-criteria count and uniqueness wording
- task spec schema records acceptance-criteria count and uniqueness wording

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 135 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 209 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Inbox Stop-Condition Quality Guard

Enhanced `python -m utils.validate_handoff_docs` so ready DeepSeek inbox tasks must include at least three stop conditions, and those stop conditions must be unique. `python -m utils.prepare_deepseek_task` now rejects generated task specs with fewer than three stop conditions or repeated stop-condition text before writing an assignment.

Updated the review checklist, workflow guide, task template, and task spec schema so the stop-condition count and uniqueness contract is documented and protected by required snippets.

Covered cases:

- ready inbox validation rejects fewer than three stop conditions
- ready inbox validation rejects duplicate stop conditions
- generated task spec validation rejects fewer than three stop conditions
- generated task spec validation rejects duplicate stop conditions
- reusable task template records stop-condition count and uniqueness wording
- task spec schema records stop-condition count and uniqueness wording

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 134 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 208 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Pipeline Blocked-Term Workflow-Test Coverage

Expanded `python -m utils.dual_model_pipeline_check` blocked-term scanning to include `tests/test_dual_model_gates_workflow.py`, matching the manual scoped scan and the broader text-health coverage.

Covered cases:

- blocked-term scan paths include the workflow regression test module
- focused pipeline path test protects this coverage

Latest focused verification:

- `python -m pytest tests/test_dual_model_pipeline_check.py -q` -> 13 ok
- `python -m ruff check utils/dual_model_pipeline_check.py tests/test_dual_model_pipeline_check.py` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Inbox Angle-Marker Guard

Enhanced `python -m utils.validate_handoff_docs` so ready DeepSeek inbox sections reject unresolved angle-bracket markers left from task templates. `python -m utils.prepare_deepseek_task` now rejects those markers in spec text fields before writing an assignment.

Updated the review checklist, workflow guide, task template, and task spec schema so marker removal is documented and protected by required snippets.

Covered cases:

- ready inbox validation rejects unresolved angle-bracket markers inside acceptance criteria
- generated task spec validation rejects angle-bracket markers before writing
- reusable task template records marker removal wording
- task spec schema records marker rejection wording

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 127 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 201 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Pipeline Blocked-Term Scan Guard

Enhanced `python -m utils.dual_model_pipeline_check` so the aggregate CI/local gate now includes a scoped blocked-term scan over the handoff utilities, focused tests, handoff templates, `test_plan.md`, and `progress.md`. This promotes the manual blocked-term scan into the machine-readable pipeline report without scanning current inbox/outbox instructional text that intentionally names forbidden implementation terms.

Covered cases:

- pipeline JSON includes a `blocked term scan` check
- blocked-term scan paths cover handoff utilities, focused tests, templates, `test_plan.md`, and `progress.md`
- blocked-term scan reports file, line, and preview
- aggregate pipeline results surface blocked-term scan hits as a failed check
- scan-hit tests construct forbidden text dynamically so the test source stays clean

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 197 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Generated Task Verification Command-Family Guard

Enhanced `python -m utils.prepare_deepseek_task` so task specs are rejected before writing when verification commands use suffixed command lookalikes or shell control operators. This mirrors the ready inbox validator and keeps bad assignments from being rendered into the handoff files.

Covered cases:

- task spec validation rejects `pytest` substring lookalikes such as `pytester`
- task spec validation rejects `ruff` substring lookalikes such as `ruffian`
- task spec validation rejects altered `git diff --check` command families
- task spec validation rejects shell control operators inside a single verification command
- schema documentation records the standalone command-token rule
- reusable DeepSeek task template records the uniqueness and standalone command-token rule

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 196 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Inbox Verification Command Guard

Enhanced `python -m utils.validate_handoff_docs` so ready inbox verification commands use the same standalone command-family matching as ready outbox verification evidence and must be unique. This prevents a hand-written DeepSeek assignment from satisfying required `pytest`, `ruff`, or `git diff --check` coverage with suffixed command names, shell-chained commands, or repeated entries.

Covered cases:

- ready inbox validation rejects `pytest` substring lookalikes such as `pytester`
- ready inbox validation rejects `ruff` substring lookalikes such as `ruffian`
- ready inbox validation rejects altered `git diff --check` command families
- ready inbox validation rejects duplicate verification commands
- ready inbox validation rejects shell control operators inside a single verification command
- chained verification commands are not counted toward required command-family coverage

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 196 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Acceptance Evidence Prefix Guard

Enhanced `python -m utils.codex_review_gate` so checked ready-outbox acceptance evidence must start with the assigned inbox criterion it covers. This keeps useful detail after the criterion while rejecting weak evidence that only mentions the criterion later in unrelated prose.

Updated the Codex review checklist and test plan to document the assigned-criterion prefix rule.

Covered cases:

- checked evidence such as `Error path verified. Covered by targeted regression.` remains valid
- checked evidence such as `Covered by targeted regression: Error path verified.` no longer satisfies `Error path verified.`
- checklist wording preserves the assigned-criterion prefix rule

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 55 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py -q` -> 170 ok
- `python -m ruff check utils/codex_review_gate.py utils/validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 186 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Outbox Command-Family Evidence Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready outbox verification evidence must use standalone command tokens for `pytest`, `ruff`, and `git diff --check`. The validator now rejects command-family evidence that relies on suffixed command names such as `ruffian`, and it rejects backticked result commands that append shell control operators such as `&&`.

Updated the Codex review checklist and test plan to document the command-family evidence rule.

Covered cases:

- ready outbox verification evidence with `python -m ruffian ...` does not satisfy the required `ruff` evidence
- ready outbox verification evidence with `python -m pytest ... && echo ok` is rejected as a chained command
- required checklist wording preserves the standalone command-token rule

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 78 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py -q` -> 169 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 185 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Assignment Examples Required-Reading Guard

Updated `docs/handoff/deepseek_assignment_examples.md` so the CLI and JSON spec examples explicitly say extra required-reading entries must not list mutable handoff control files. Added the wording to required snippet validation so the examples page cannot silently drift away from the generator and validator behavior.

Covered cases:

- assignment examples preserve the extra required-reading control-file warning
- Codex review gate fixtures include the same examples-page warning
- prepare-task fixtures include the same examples-page warning
- handoff validator fixtures include the same examples-page warning

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 167 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 183 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Generated Task Required-Reading Control File Guard

Enhanced `python -m utils.prepare_deepseek_task` so CLI and spec-file assignments reject required-reading entries that list mutable handoff control files before rendering or writing the inbox. The default canonical inbox required-reading entry remains allowed.

Updated the dual-model workflow, task spec schema, and test plan to record that generated task validation applies the same control-file required-reading rule as the repository handoff validator.

Covered cases:

- `validate_spec` rejects `docs/handoff/deepseek_outbox.md` as required reading
- `validate_spec` rejects `DEEPSEEK_INBOX.md` as required reading
- `validate_spec` rejects `CODEX_REVIEW.md` as required reading
- CLI assignment rejects `--required-reading docs/handoff/deepseek_outbox.md` before writing
- spec-file assignment rejects `DEEPSEEK_INBOX.md` before writing
- required handoff docs preserve the task spec schema warning for mutable control-file required reading

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py -q` -> 37 ok
- `python -m ruff check utils/prepare_deepseek_task.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 183 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Inbox Required-Reading Control File Guard

Enhanced `python -m utils.validate_handoff_docs` so ready inbox required-reading sections can include the canonical DeepSeek inbox but cannot list the mutable DeepSeek outbox or root shortcut control files. This keeps task context pointed at durable project inputs while preventing hand-written assignments from treating handoff control-plane files as implementation reading material.

Updated the Codex review checklist, dual-model workflow notes, and test plan to document the distinction between the canonical inbox and forbidden control files.

Covered cases:

- ready inbox validation accepts `docs/handoff/deepseek_inbox.md` as required reading
- ready inbox validation rejects `docs/handoff/deepseek_outbox.md` as required reading
- ready inbox validation rejects `DEEPSEEK_INBOX.md` as required reading
- ready inbox validation rejects `CODEX_REVIEW.md` as required reading
- required handoff docs preserve the new required-reading control-file guidance

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 110 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 180 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Workflow Evidence Snippet Guard

Added required-snippet coverage so `python -m utils.validate_handoff_docs` protects the dual-model workflow guide warnings for invalid checked acceptance evidence, invalid Anti-Placeholder evidence, and skipped verification evidence.

Synchronized workflow fixtures in validator, review-gate, and prepare-task tests with the required warning wording.

Covered cases:

- missing skipped/not-executed acceptance warning in `docs/handoff/dual_model_development_workflow.md` is rejected
- missing unverified/untested acceptance warning in `docs/handoff/dual_model_development_workflow.md` is rejected
- missing pending/deferred/not-applicable acceptance warning in `docs/handoff/dual_model_development_workflow.md` is rejected
- missing Anti-Placeholder command warning in `docs/handoff/dual_model_development_workflow.md` is rejected
- missing skipped verification warning in `docs/handoff/dual_model_development_workflow.md` is rejected

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 74 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 178 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Review Checklist Evidence Snippet Guard

Added required-snippet coverage so `python -m utils.validate_handoff_docs` protects the Codex review checklist warnings for invalid checked acceptance evidence and invalid Anti-Placeholder evidence.

Synchronized checklist fixtures in validator, review-gate, and prepare-task tests with the required warning wording.

Covered cases:

- missing skipped/not-executed acceptance warning in `docs/handoff/codex_review_checklist.md` is rejected
- missing unverified/untested acceptance warning in `docs/handoff/codex_review_checklist.md` is rejected
- missing pending/deferred/not-applicable acceptance warning in `docs/handoff/codex_review_checklist.md` is rejected
- missing empty Anti-Placeholder stand-in warning in `docs/handoff/codex_review_checklist.md` is rejected
- missing skipped/not-executed Anti-Placeholder warning in `docs/handoff/codex_review_checklist.md` is rejected

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 69 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 173 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Task Template Evidence Snippet Guard

Added required-snippet coverage so `python -m utils.validate_handoff_docs` protects the reusable DeepSeek task template evidence warnings for invalid checked acceptance evidence and invalid Anti-Placeholder scan evidence.

Synchronized test fixtures in review-gate and prepare-task tests with the updated template wording.

Covered cases:

- missing checked-acceptance warning in `docs/handoff/deepseek_task_template.md` is rejected
- missing Anti-Placeholder warning in `docs/handoff/deepseek_task_template.md` is rejected
- review-gate and prepare-task fixture docs preserve the same required snippets

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 64 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 168 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Generated Task Evidence Wording

Updated `utils.prepare_deepseek_task.render_task` and `docs/handoff/deepseek_task_template.md` so newly assigned DeepSeek tasks explicitly forbid skipped, unverified, deferred, not-applicable, and empty-scan evidence in the outbox.

Updated the prepare-task regression test and test plan so generated task instructions keep these evidence rules visible.

Covered cases:

- generated task text tells DeepSeek checked acceptance evidence cannot use invalid completion wording
- generated task text tells DeepSeek Anti-Placeholder evidence cannot use empty or unrun scan wording
- reusable DeepSeek task template mirrors the generated task evidence wording

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py -q` -> 34 ok
- `python -m ruff check utils/prepare_deepseek_task.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 166 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Review Gate Scan Failure Semantics

Added regression coverage that scan hits make Codex review gate fail closed in both structured JSON output and CLI exit behavior.

Updated the test plan to require JSON `ok` to be false when scan hits exist and the CLI to return nonzero when secret-shaped values are found.

Covered cases:

- blocked-term hits make `python -m utils.codex_review_gate --json` report `ok: false`
- secret-shaped values make the Codex review gate CLI return nonzero
- secret-shaped values remain redacted in CLI output

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 54 ok
- `python -m ruff check tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 166 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Review Gate Mismatch Surfacing

Added Codex review gate regression coverage for ready inbox/outbox task-code drift. Because the review gate starts with handoff validation, mismatch issues now have direct review-gate coverage as well as validator coverage.

Updated the test plan to state that Codex review gate surfaces ready inbox/outbox message id or task mismatch issues.

Covered cases:

- Codex review gate reports ready inbox/outbox task-code mismatch

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 52 ok
- `python -m ruff check tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 164 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Handoff Task Mismatch Coverage

Added regression coverage for ready inbox/outbox task-code mismatch. The validator already rejected metadata mismatches; tests now cover both message id drift and task code drift after assignment.

Updated the test plan to explicitly require ready inbox and outbox message id and task values to match.

Covered cases:

- outbox message id differing from the ready inbox is rejected
- outbox task code differing from the ready inbox is rejected

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 62 ok
- `python -m ruff check tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 163 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Inbox Codex Gate Coverage

Added regression coverage for ready DeepSeek inbox assignments that do not carry `CODEX_GATE: PASS`. This keeps waiting-state `CODEX_GATE: REQUIRED` from being accepted after the inbox status changes to `READY_FOR_DEEPSEEK`.

Updated the review checklist, workflow guide, and test plan to make the gate release requirement explicit.

Covered cases:

- ready inbox with `CODEX_GATE: REQUIRED` is rejected
- waiting inbox can still retain the required-gate marker before assignment

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 61 ok
- `python -m ruff check tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 162 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Root Shortcut Target Coverage

Added regression coverage for root handoff shortcuts so `DEEPSEEK_INBOX.md` and `CODEX_REVIEW.md` must keep pointing to their canonical docs under `docs/handoff/`.

Updated the review checklist and test plan to call out shortcut drift as a handoff validation concern.

Covered cases:

- `DEEPSEEK_INBOX.md` target drift is rejected
- `CODEX_REVIEW.md` target drift is rejected

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 60 ok
- `python -m ruff check tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 161 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Empty Anti-Placeholder Evidence Coverage

Expanded validator regression coverage for ready-outbox Anti-Placeholder evidence stand-ins. The validator already rejects empty scan evidence values; tests now cover `None`, `not applicable`, `n/a`, and `no scan`.

Updated the review checklist and test plan so empty Anti-Placeholder scan stand-ins are called out explicitly.

Covered cases:

- ready outbox Anti-Placeholder scan evidence rejects `None`
- ready outbox Anti-Placeholder scan evidence rejects `not applicable`
- ready outbox Anti-Placeholder scan evidence rejects `n/a`
- ready outbox Anti-Placeholder scan evidence rejects `no scan`

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 58 ok
- `python -m ruff check tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 159 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Deferred Acceptance Evidence Guard

Extended checked ready-outbox acceptance evidence validation so `pending`, `deferred`, `not applicable`, and `n/a` wording is rejected in both the handoff validator and the Codex review gate.

Updated the handoff checklist, dual-model workflow guide, and test plan to document that checked evidence cannot defer acceptance coverage.

Covered cases:

- ready outbox checked acceptance evidence rejects pending coverage wording
- ready outbox checked acceptance evidence rejects deferred coverage wording
- ready outbox checked acceptance evidence rejects not-applicable coverage wording
- Codex review applies the same rejection before accepting a DeepSeek handoff

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py -q` -> 106 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 156 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Anti-Placeholder Scan Failure Evidence Guard

Enhanced ready outbox Anti-Placeholder scan checks so skipped, not-scanned, not-executed, or failing scan evidence is rejected even if the line also claims no matches. This keeps the scanner gate from being satisfied by wording that says the scan did not actually run.

Covered cases:

- handoff docs validation rejects skipped Anti-Placeholder scan evidence
- handoff docs validation rejects not-scanned Anti-Placeholder scan evidence
- Codex review gate inherits the same failing scan evidence issue
- documentation and test plan record that skipped or failing scanner evidence is not clean

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 48 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py -q` -> 91 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 141 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Skipped Verification Result Guard

Enhanced ready outbox verification evidence checks so skipped or not-executed commands are treated as failing evidence, even when a clean exit marker is also present. This prevents DeepSeek from reporting a command as complete when the assigned verification did not actually run.

Covered cases:

- handoff docs validation rejects `skipped, exited 0` verification evidence
- Codex review gate rejects skipped evidence for an exact assigned command
- documentation and test plan record that skipped or not-executed wording is not clean verification evidence

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py -q` -> 89 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 139 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Dot-Segment Path Guard

Enhanced repository-relative path validation so `.` path segments are rejected alongside `..` traversal. This keeps task scope, required-reading, and review changed-file evidence from using alternate spellings such as `src/./example.py`.

Covered cases:

- task spec validation rejects `./src/example.py`
- task spec validation rejects `src/./example.py`
- handoff docs validation rejects dot-segment allowed scope entries
- Codex review gate surfaces dot-segment changed-file evidence through the raw handoff validator

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 121 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 137 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-01: DeepSeek Task Spec File Input

Enhanced `python -m utils.prepare_deepseek_task` with `--spec-file` so Codex can render or write a bounded DeepSeek inbox from a JSON task specification.

Key behavior:

- spec file paths are resolved from the repository root unless absolute
- invalid JSON and wrong field types fail before writing
- `--dry-run`, `--reset-outbox`, and `--validate-repository` continue to work with spec-file input
- `docs/handoff/deepseek_assignment_examples.md` now documents the spec-file variant

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 44 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-01: DeepSeek Task Spec Schema

Added `docs/handoff/deepseek_task_spec_schema.md` to document the JSON object accepted by `python -m utils.prepare_deepseek_task --spec-file`.

The schema document is now part of `python -m utils.validate_handoff_docs`.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 45 ok
- `python -m ruff check tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-01: DeepSeek Spec Unknown Field Guard

Enhanced `python -m utils.prepare_deepseek_task --spec-file` so unknown JSON fields fail before writing handoff files.

This prevents misspelled task fields from being silently ignored.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 46 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-01: Pipeline Text Health Coverage Guard

Added a regression test that keeps the aggregate text-health scan wired to:

- `.github/workflows/dual-model-gates.yml`
- `docs/handoff/deepseek_assignment_examples.md`
- `docs/handoff/deepseek_task_spec_schema.md`
- `tests/test_dual_model_gates_workflow.py`

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 47 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-01: Codex Review Changed-File Path Guard

Enhanced `python -m utils.codex_review_gate` so outbox changed-file entries reject:

- empty paths
- parent-directory traversal
- absolute paths or drive-like paths
- duplicate changed-file entries

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 49 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-01: URL Scope Rejection

Enhanced handoff path validation so URL-shaped paths are rejected in:

- ready inbox allowed and forbidden scopes
- ready outbox changed-file entries

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 50 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-01: Agent Rules Handoff Requirement

Added `AGENTS.md` to the required handoff document set checked by `python -m utils.validate_handoff_docs`.

Temporary repository fixtures now create a small `AGENTS.md` so task-generation and review-gate tests cover the same required file set as the real repository.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py -q` -> 37 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 50 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-01: DeepSeek Task Scope Entry Guards

Added focused task-generator tests proving both task-spec JSON input and CLI input reject unsafe scope paths before any inbox write.

Covered examples:

- URL-shaped allowed file scope
- parent-directory allowed file scope

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py -q` -> 15 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 52 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok

## 2026-08-01: DeepSeek Required Reading Path Guard

Added task-generator validation for required-reading paths so assignment specs cannot point DeepSeek at unsafe or duplicate required-reading entries.

Covered examples:

- URL-shaped required-reading path
- parent-directory required-reading path
- duplicate required-reading path

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py -q` -> 17 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 54 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok

## 2026-08-01: DeepSeek Verification Command Text Guard

Added task-generator validation so verification commands must be non-empty single-line strings and cannot contain Markdown code fences before rendering into the handoff inbox.

Covered examples:

- multiline verification command
- fenced verification command text
- empty verification command from task-spec JSON

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py -q` -> 19 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 56 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok

## 2026-08-01: DeepSeek Task Text Field Guard

Added task-generator validation so task narrative fields cannot inject extra Markdown sections into the rendered inbox.

Guarded fields:

- objective
- requirements
- acceptance criteria
- stop conditions

The task-spec schema now documents the single-line text rule and safe path rule.

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py -q` -> 41 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 58 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok

## 2026-08-01: DeepSeek Task Metadata Field Guard

Extended the single-line text guard to `message_id` and `task`, preventing generated inbox metadata from carrying extra top-level fields.

The task-spec schema now lists `message_id` and `task` under the same text rules as objective, requirements, acceptance criteria, stop conditions, and verification commands.

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py -q` -> 43 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 60 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok

## 2026-08-01: DeepSeek Spec File Path Guard

Restricted `python -m utils.prepare_deepseek_task --spec-file` to repository-relative JSON spec paths before any file read.

Rejected examples:

- parent-directory spec-file path
- URL-shaped spec-file path

The task-spec schema now states that spec-file input must stay repository-local.

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py -q` -> 45 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 62 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok

## 2026-08-01: Codex Review Directory Changed-File Guard

Enhanced `python -m utils.codex_review_gate` so review-ready outbox changed-file entries must resolve to concrete files.

This prevents a worker from listing a directory in `## Changed Files` and skipping file-level scans.

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 14 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 63 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok

## 2026-08-01: Codex Review Inbox Key-Shape Scan

Enhanced `python -m utils.codex_review_gate` so standalone Codex review scans include the DeepSeek inbox as well as changed files and the outbox.

Key-shaped values are still redacted in review output.

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 15 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 64 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok

## 2026-08-01: Handoff Test Plan Documentation Sync

Updated the handoff test plan, dual-model workflow, and Codex review checklist to document the current guard set:

- repository-local task spec files
- single-line task text and verification commands
- safe required-reading paths
- concrete changed-file entries
- inbox and outbox key-shape review scans

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py -q` -> 20 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 64 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok

## 2026-08-01: Codex Review Outbox Blocked-Term Scan

Enhanced `python -m utils.codex_review_gate` so blocked-term scans include the DeepSeek outbox in addition to changed files.

The DeepSeek inbox is intentionally excluded from blocked-term scanning because it contains the scanner rule text itself. Inbox key-shaped values are still redacted by the secret-shape scan.

The Codex review checklist now documents that blocked scanner terms are forbidden in changed implementation paths and the handoff outbox.

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 16 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 65 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok

## 2026-08-01: Top-Level Status Readiness Guard

Tightened readiness detection in `utils.validate_handoff_docs` and `utils.codex_review_gate` so lifecycle state is controlled only by top-level `Status:` metadata before the first section heading.

Body text containing review-ready markers or `Status:` lines no longer changes inbox or outbox readiness.

The handoff workflow and test plan now document this top-level metadata rule.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py -q` -> 29 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 67 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-01: Ready Outbox Evidence Placeholder Guard

Enhanced `utils.validate_handoff_docs` ready-outbox validation so:

- ready sections reject `Not run` case-insensitively
- ready `## Changed Files` rejects empty, none, no-change, or not-applicable evidence

The test plan now records these ready-outbox evidence checks.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 14 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 69 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-01: Handoff Metadata Uniqueness Guard

Added duplicate top-level metadata detection for canonical inbox and outbox files.

Guarded fields:

- inbox: `Status`, `Message ID`, `Task`, `CODEX_GATE`
- outbox: `Status`, `Message ID`, `Task`

Metadata extraction now keeps the first value, so a repeated field cannot silently override lifecycle state.

The workflow and test plan now document the unique top-level metadata rule.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py -q` -> 34 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 72 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Verification Command Guard

Enhanced ready-outbox validation so a `READY_FOR_CODEX_REVIEW` outbox must include verification evidence for:

- pytest
- ruff
- `git diff --check`

This keeps a DeepSeek handoff from reaching Codex review with only partial verification recorded.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 73 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Codex Review Scope-Deviation Gate

Enhanced `python -m utils.codex_review_gate` so a ready outbox must explicitly state scope deviations.

Review behavior:

- empty `## Scope Deviations` sections are rejected
- `None`, `None.`, `n/a`, and no-deviation wording are accepted as no-deviation evidence
- any other scope-deviation line is reported as a Codex review issue

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 20 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 75 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Checked Acceptance Evidence

Enhanced `python -m utils.validate_handoff_docs` so a `READY_FOR_CODEX_REVIEW` outbox must record acceptance criteria as checked evidence items.

Rejected examples:

- no checked acceptance evidence
- generic all-criteria summaries

The DeepSeek task template, workflow, test plan, and Codex review checklist now document the checked-evidence requirement.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py -q` -> 39 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 77 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Unresolved-Blocker Guard

Enhanced `python -m utils.validate_handoff_docs` so a `READY_FOR_CODEX_REVIEW` outbox must explicitly state unresolved questions or blockers.

Rejected examples:

- empty unresolved-blocker section
- any non-None blocker line

The DeepSeek task template, workflow, test plan, and Codex review checklist now document this clean-handoff requirement.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 21 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 79 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Codex Review Stand-In Marker Coverage

Expanded `python -m utils.codex_review_gate` blocked-term scanning to cover the additional stand-in marker already listed in the DeepSeek inbox and task template rule text.

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 21 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 80 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Anti-Placeholder Evidence Guard

Enhanced `python -m utils.validate_handoff_docs` so a `READY_FOR_CODEX_REVIEW` outbox must record Anti-Placeholder evidence with:

- scanner command evidence
- clean scan result evidence
- no empty scan-evidence stand-ins

The DeepSeek task template, workflow, test plan, and Codex review checklist now document the command-and-result evidence requirement.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py -q` -> 45 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 83 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: DeepSeek Task Generator Outbox Evidence Wording

Updated `python -m utils.prepare_deepseek_task` rendered inbox text so generated tasks now ask DeepSeek for:

- checked acceptance criteria evidence
- Anti-Placeholder scanner command and clean result
- explicit None when no unresolved questions or blockers remain

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py -q` -> 26 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 84 ok
- `python -m ruff check utils/prepare_deepseek_task.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Dual-Model CI Diff and Lint Coverage

Updated `.github/workflows/dual-model-gates.yml` so focused CI now:

- lints `tests/test_dual_model_gates_workflow.py`
- runs `git diff --check`

Added workflow regression tests for both checks.

Latest focused verification:

- `python -m pytest tests/test_dual_model_gates_workflow.py -q` -> 6 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 86 ok
- `python -m ruff check tests/test_dual_model_gates_workflow.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- YAML parse check for `.github/workflows/dual-model-gates.yml` -> ok

## 2026-08-02: Ready Outbox Changed-File Stand-In Normalization

Enhanced `python -m utils.validate_handoff_docs` so ready-outbox changed-file evidence normalizes punctuation before checking no-change stand-ins.

Covered example:

- `None.`

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 25 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 87 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Handoff Evidence Wording Drift Guard

Enhanced `python -m utils.validate_handoff_docs` so required handoff docs must retain current ready-outbox evidence wording.

Locked documents:

- `docs/handoff/deepseek_task_template.md`
- `docs/handoff/codex_review_checklist.md`

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py -q` -> 72 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 87 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Handoff Section Uniqueness Guard

Enhanced `python -m utils.validate_handoff_docs` so required handoff document section headings cannot be duplicated.

This prevents ambiguous evidence sections where automation reads the first section while a human sees later conflicting text.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 26 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 88 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Assigned Verification Command Guard

Enhanced `python -m utils.codex_review_gate` so a ready DeepSeek outbox must include every exact verification command assigned in the ready inbox.

This prevents replacing Codex-specified commands with nearby commands that do not cover the assigned files or scope.

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 22 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 89 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Spec-File Required-Reading File Guard

Extended the required-reading file guard coverage to JSON spec-file task assignment. `python -m utils.prepare_deepseek_task --spec-file ... --reset-outbox --validate-repository` now has a regression proving a non-file required-reading entry is caught by repository validation and previous handoff files are restored.

Covered cases:

- spec-file assignments inherit required-reading file checks
- spec-file assignments restore the previous waiting inbox and outbox when repository validation rejects a non-file required-reading entry
- schema documentation states that repository validation applies to JSON spec-file assignments

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py -q` -> 33 ok
- `python -m ruff check tests/test_prepare_deepseek_task.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 134 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Handoff Docs Verification Clean-Result Guard

Enhanced `python -m utils.validate_handoff_docs` so ready outbox verification evidence for pytest, ruff, and `git diff --check` must include clean result markers and must not include nonzero result markers.

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 27 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 94 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: DeepSeek Task Clean-Result Instruction

Updated `python -m utils.prepare_deepseek_task` and `docs/handoff/deepseek_task_template.md` so generated tasks explicitly require each assigned verification command result to include a clean marker such as `exited 0`.

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py -q` -> 52 ok
- `python -m ruff check utils/prepare_deepseek_task.py tests/test_prepare_deepseek_task.py utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok

## 2026-08-02: Task Template Scanner Noise Cleanup

Updated `docs/handoff/deepseek_task_template.md` so its Anti-Placeholder example references the scanner terms from `utils.codex_review_gate` instead of embedding the blocked vocabulary directly in the template text.

Latest focused verification:

- scoped Anti-Placeholder scan over changed gate, generator, tests, checklist, template, plan, and progress paths -> no matches
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 93 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Verification Command Clean-Result Guard

Enhanced `python -m utils.codex_review_gate` so every exact assigned verification command must have clean result evidence in the ready outbox.

Covered case:

- a listed assigned command with a nonzero result is rejected

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 26 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 93 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Verification Command Shape Guard

Enhanced `python -m utils.codex_review_gate` so assigned-command extraction covers both fenced command blocks and backticked bullet commands.

This keeps exact command matching stable if a future inbox task is written in bullet form instead of a PowerShell code block.

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 25 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 92 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Parsed Verification Command Result Guard

Enhanced `python -m utils.codex_review_gate` so ready outbox verification evidence parses the backticked command from each result line and compares it exactly to the assigned inbox command.

Covered case:

- a suffixed command that merely contains the assigned command text is rejected

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 29 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 97 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Conflicting Verification Result Guard

Enhanced `python -m utils.codex_review_gate` so an assigned verification command with any failing result line is surfaced, even if another matching line has clean evidence.

Covered case:

- duplicate assigned command result lines with both failing and clean evidence are rejected

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 30 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 98 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Worktree Baseline Path Validation Guard

Enhanced `python -m utils.validate_handoff_docs` so ready inbox worktree baselines must be explicit safe repository-relative entries, with no duplicate paths and no mixing of `None` with path entries.

Covered cases:

- ready inbox validation rejects a worktree baseline section without bullet entries
- ready inbox validation rejects unsafe baseline paths
- ready inbox validation rejects duplicate baseline paths
- ready inbox validation rejects a `None` marker mixed with path entries

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 30 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 105 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- `rg -n "sk-[A-Za-z0-9_-]{20,}" ...` -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Secret Shape False Positive Guard

Tightened the shared key-shaped string scanner so it still redacts standalone `sk-...` values while ignoring embedded selector text such as CSS `task-list` names.

Covered cases:

- Codex review scan redacts standalone key-shaped values in changed files
- Codex review scan ignores embedded `task-list` selector text
- aggregate pipeline text scan ignores embedded `task-list` selector text

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py -q` -> 43 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 107 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- repository key-shaped scan with boundary-aware pattern -> no matches

## 2026-08-02: Ready Inbox Required Reading Path Guard

Enhanced `python -m utils.validate_handoff_docs` so hand-written ready inbox tasks validate both required-reading sections with the same safe repository-relative path rules used by generated task specs.

Covered cases:

- unsafe `## Required Reading Before Editing` paths are rejected
- duplicate `## Required Reading Before Editing` paths are rejected
- unsafe `## Required Reading` paths are rejected
- duplicate `## Required Reading` paths are rejected
- DeepSeek task template uses bullet required-reading entries matching the validator

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 31 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 108 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Unverified Acceptance Evidence Guard

Extended checked ready-outbox acceptance evidence validation so `unverified` and `untested` wording is rejected in both the handoff validator and the Codex review gate.

Updated the handoff checklist, dual-model workflow guide, and test plan to document that checked evidence cannot claim absent verification or absent coverage.

Covered cases:

- ready outbox checked acceptance evidence rejects `unverified` wording
- ready outbox checked acceptance evidence rejects `untested` wording
- Codex review applies the same rejection before accepting a DeepSeek handoff

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py -q` -> 98 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 148 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Skipped Acceptance Evidence Guard

Enhanced `python -m utils.validate_handoff_docs` and `python -m utils.codex_review_gate` so checked ready-outbox acceptance evidence cannot claim skipped or not-executed verification while still using a checked item.

Updated the handoff checklist, dual-model workflow guide, and test plan so DeepSeek submissions and Codex review use the same rule.

Covered cases:

- ready outbox checked acceptance evidence rejects skipped verification wording
- Codex review rejects checked acceptance evidence that says verification was skipped
- documentation now calls out skipped or not-executed acceptance evidence as invalid

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py -q` -> 94 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 144 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Inbox Handoff-Control Scope Guard

Enhanced ready inbox scope validation so DeepSeek assigned `allowed_files` cannot include the handoff control files or root shortcuts. Directory scopes that cover those control files are rejected too, while `forbidden_files` can still name paths to protect them.

Covered cases:

- ready inbox validation rejects `docs/handoff/deepseek_inbox.md` in allowed scope
- ready inbox validation rejects `DEEPSEEK_INBOX.md` in allowed scope
- ready inbox validation rejects a parent directory scope that covers handoff control files
- task spec validation rejects handoff control files before rendering a DeepSeek assignment

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 76 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 133 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Handoff-Control Changed-File Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready outbox changed-file evidence cannot list handoff control files or root shortcuts as implementation changes.

Covered cases:

- ready outbox changed-file evidence rejects `docs/handoff/deepseek_outbox.md`
- ready outbox changed-file evidence rejects `DEEPSEEK_INBOX.md`
- ready outbox changed-file evidence rejects `CODEX_REVIEW.md`
- existing safe, unique, repository-relative path checks remain in place

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 39 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 122 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Checked Acceptance Negative Evidence Guard

Enhanced `python -m utils.codex_review_gate` so checked ready-outbox acceptance evidence is rejected when it contains negative completion wording.

Covered cases:

- checked acceptance evidence with `not verified` is rejected
- checked acceptance evidence may still include concrete follow-up detail after the assigned criterion

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 38 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 123 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Outbox Scope-Deviation Validation Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready outboxes cannot carry non-None scope deviations even before Codex semantic review.

Covered cases:

- ready outbox `## Scope Deviations` with an unapproved deviation is rejected
- ready outbox `## Scope Deviations` remains valid with `None`

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 40 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 124 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Outbox Changed-File Mixed Evidence Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready outbox changed-file evidence cannot mix no-change stand-ins with real paths.

Covered cases:

- ready outbox `## Changed Files` rejects `None` combined with a concrete path
- ready outbox `## Changed Files` still rejects no-change stand-ins when no paths are listed

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 41 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 125 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Outbox Acceptance Negative Evidence Validation Guard

Enhanced `python -m utils.validate_handoff_docs` so checked ready-outbox acceptance evidence with negative completion wording fails the base handoff docs gate before semantic Codex review.

Covered cases:

- checked acceptance evidence with `not verified` is rejected by handoff docs validation
- Codex review still checks assigned-criterion coverage separately

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 42 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 126 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Handoff Root Shortcut Worktree Disclosure Guard

Enhanced `python -m utils.codex_review_gate` so root shortcut handoff files are ignored by implementation worktree disclosure checks while remaining subject to the existing shortcut-target validation.

Covered cases:

- dirty `DEEPSEEK_INBOX.md` is not reported as an implementation disclosure gap
- dirty `CODEX_REVIEW.md` is not reported as an implementation disclosure gap
- shortcut files still need to point to their canonical handoff targets

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 39 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 127 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Review Gate Handoff-Control Changed-File Guard

Enhanced `python -m utils.codex_review_gate` so changed-file entries that name handoff control files are rejected directly by the review gate.

Covered cases:

- ready outbox changed-file evidence listing `DEEPSEEK_INBOX.md` is rejected by Codex review
- handoff control entries are not scanned or treated as implementation files

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 40 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 128 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Handoff Root Shortcut Secret Scan Guard

Enhanced `python -m utils.codex_review_gate` so handoff root shortcuts are included in key-shaped string scans.

Covered cases:

- key-shaped values in `DEEPSEEK_INBOX.md` are redacted and reported
- root shortcuts still need to include their canonical target paths

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 41 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 129 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Verification Result Negation Guard

Tightened ready-outbox verification evidence so negated success wording is treated as a failing command result rather than clean evidence.

Covered cases:

- assigned verification command evidence rejects `not successful`
- handoff docs validation rejects `not successful` for required ready-outbox commands
- broad `success` substring matching was removed from clean result markers

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py -q` -> 68 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 114 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Anti-Placeholder No-Match Evidence Guard

Tightened ready-outbox Anti-Placeholder scan evidence so an exit code alone is not accepted as a clean scan result. The outbox must say the scanner found no matches.

Covered cases:

- Anti-Placeholder scan evidence with only `exited 0` is rejected
- Anti-Placeholder scan evidence with command text and no-match wording remains accepted

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 34 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 115 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Inbox Verification Command Parse Guard

Enhanced `python -m utils.validate_handoff_docs` so ready inbox verification commands must be parseable command entries, not prose that merely mentions pytest, ruff, and `git diff --check`.

Covered cases:

- fenced PowerShell command blocks remain valid
- backticked bullet command entries remain valid
- prose-only verification sections are rejected even when they mention required tool names

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 36 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 117 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Outbox Verification Result Parse Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready verification results must be parseable backticked command result lines, not prose that merely mentions pytest, ruff, and `git diff --check`.

Covered cases:

- ready outbox verification result prose is rejected
- required pytest, ruff, and `git diff --check` evidence is matched from parsed command entries
- existing backticked command result evidence remains valid

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 37 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 118 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Assigned Acceptance Evidence Guard

Enhanced `python -m utils.codex_review_gate` so review-ready outboxes must include checked evidence for each acceptance criterion assigned in the ready inbox.

Covered cases:

- outbox evidence that omits an assigned criterion is rejected
- checked evidence may include extra detail after the assigned criterion

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 37 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 120 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Outbox Concrete Metadata Guard

Enhanced `python -m utils.validate_handoff_docs` so a review-ready outbox must set concrete `Message ID` and `Task` metadata before deeper Codex review.

Covered cases:

- ready outbox `Message ID: unassigned` is rejected
- ready outbox template task values are rejected

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 38 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 121 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Markdown Path Injection Guard

Enhanced shared scope-path validation so task path entries containing embedded Markdown backticks or line breaks are rejected before they can distort a rendered inbox or validation report.

Covered cases:

- hand-written ready inbox allowed paths with embedded backticks are rejected
- task-spec allowed paths with embedded backticks are rejected
- task-spec allowed paths with line breaks are rejected
- line-break path values are shown escaped in validation output

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 59 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 108 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Changed-File Code Span Path Guard

Enhanced `python -m utils.codex_review_gate` so ready outbox changed-file entries only unwrap a well-formed full code span and reject embedded Markdown backticks as unsafe path text.

Covered case:

- ready outbox changed-file paths containing an embedded backtick are rejected instead of being partially parsed

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 34 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 109 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Baseline Render Safety Guard

Enhanced `python -m utils.prepare_deepseek_task` so worktree baseline values are normalized and validated before rendering a ready inbox. Invalid baseline paths now return a clear CLI validation error instead of producing malformed Markdown.

Covered cases:

- task rendering rejects unsafe worktree baseline paths
- task rendering rejects duplicate worktree baseline paths
- dry-run reports invalid git baseline paths without writing inbox or outbox files

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py -q` -> 30 ok
- `python -m ruff check utils/prepare_deepseek_task.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 111 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Worktree Baseline Assignment Guard

Added `## Worktree Baseline` to generated ready inbox tasks so Codex records assignment-time git worktree paths before DeepSeek implementation begins.

Enhanced `python -m utils.codex_review_gate` so current git worktree paths not present in the baseline and not listed in the ready outbox are surfaced as post-assignment unreported changes.

Covered cases:

- generated inbox text includes an explicit baseline section
- CLI dry-run includes current git worktree paths in the rendered baseline
- ready inbox validation rejects missing baseline sections
- review ignores a baseline-listed worktree path
- review rejects a post-assignment worktree path omitted from outbox evidence

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 103 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- `rg -n "sk-[A-Za-z0-9_-]{20,}" ...` -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Changed-File Git Evidence Guard

Enhanced `python -m utils.codex_review_gate` so ready outbox changed-file entries are compared with `git status` worktree evidence when the review root is inside a git worktree.

Covered cases:

- claiming a clean tracked file as changed is rejected
- an actual dirty tracked file is accepted
- non-git temporary test roots keep the existing path and scope checks

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 24 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 91 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Scoped Worktree Disclosure Guard

Enhanced `python -m utils.codex_review_gate` so ready outboxes must disclose git worktree changes inside the assigned allowed scope, and any dirty forbidden-scope file is surfaced even when it is omitted from `## Changed Files`.

Covered cases:

- dirty allowed-scope file omitted from outbox is rejected
- dirty forbidden-scope file omitted from outbox is rejected
- handoff control files are ignored for implementation changed-file disclosure

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 28 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 96 ok
- `python -m ruff check utils/codex_review_gate.py tests/test_codex_review_gate.py` -> ok
- `python -m ruff check utils/validate_handoff_docs.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

## 2026-08-02: Ready Outbox Changed-File Path Guard

Enhanced `python -m utils.validate_handoff_docs` so review-ready outbox changed-file entries must be safe, unique, repository-relative paths before Codex review proceeds.

Covered cases:

- ready outbox changed-file entries reject parent traversal paths
- ready outbox changed-file entries reject URL-shaped paths
- ready outbox changed-file entries reject malformed Markdown code spans
- ready outbox changed-file entries reject duplicate paths
- worktree baseline path parsing unwraps only complete Markdown code spans

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py -q` -> 32 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 112 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Inbox Required-Reading File Guard

Enhanced `python -m utils.validate_handoff_docs` so ready inbox required-reading sections must point to actual files when repository validation runs with a root path. This catches hand-written or generated assignments that reference stale reading paths before DeepSeek begins implementation.

Added a `python -m utils.prepare_deepseek_task --reset-outbox --validate-repository` regression that proves invalid required-reading paths are caught after write and the previous inbox/outbox files are restored.

Covered cases:

- ready inbox validation rejects `## Required Reading Before Editing` entries that do not point to files
- ready inbox validation rejects `## Required Reading` entries that do not point to files
- task assignment rollback restores the prior waiting inbox and outbox when repository validation catches a non-file required-reading entry

Latest focused verification:

- `python -m pytest tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py -q` -> 74 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 131 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Ready Inbox Required-Outbox Evidence Guard

Enhanced `python -m utils.validate_handoff_docs` so ready DeepSeek inbox tasks must require a complete outbox evidence list, not only the `READY_FOR_CODEX_REVIEW` marker. This closes the hand-written assignment gap where DeepSeek could be told to submit without changed files, verification results, checked acceptance evidence, Anti-Placeholder scan evidence, scope deviations, or unresolved blocker status.

Updated the review checklist, workflow guide, and generated-task test fixtures so this evidence contract is protected by required snippets and repository validation.

Covered cases:

- ready inbox validation rejects a hand-written assignment that only requires `READY_FOR_CODEX_REVIEW`
- ready inbox validation requires changed-file evidence wording
- ready inbox validation requires verification-command result evidence wording
- ready inbox validation requires checked acceptance evidence wording
- ready inbox validation requires Anti-Placeholder scan evidence wording
- ready inbox validation requires scope-deviation evidence wording
- ready inbox validation requires unresolved-question or blocker evidence wording
- ready inbox validation rejects assignments missing a dedicated `## Required Outbox Evidence` section
- ready inbox validation rejects a dedicated `## Required Outbox Evidence` section that omits evidence categories
- generated DeepSeek task assignments remain compatible with repository validation

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/test_prepare_deepseek_task.py -q` -> 196 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: DeepSeek Assignment Workflow-Control Scope Guard

Added an assignment-scope guard so ready DeepSeek inbox tasks cannot list workflow control files under `Allowed Files`. The protected set covers handoff docs, root task plans, progress and verification records, gate utilities, and the dual-model CI gate. This prevents a worker task from granting itself permission to edit the rules, assignment surface, or local acceptance gates it is supposed to satisfy.

Applied the same validation through `utils.prepare_deepseek_task`, so both CLI/spec-file task generation and hand-written ready inbox files use one rule. Updated the checklist, workflow guide, task template, task spec schema, and fixture docs so future documentation drift is caught by required-snippet validation.

Covered cases:

- ready inbox validation rejects `progress.md`, `test_plan.md`, handoff task templates, and gate utilities in allowed scope
- task spec validation rejects the same workflow control paths before rendering
- rendered task text tells DeepSeek that allowed files must not include workflow control files
- test-spec data mutation now uses an explicit typed list before editing verification commands

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py -q` -> 184 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 258 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `python -m pyright utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py` -> remaining environment issue: `pytest` import is unresolved in targeted test files

## 2026-08-02: Codex Review Workflow-Control Worktree Guard

Enhanced `python -m utils.codex_review_gate` so review-ready outbox changed-file entries cannot claim workflow control files such as `progress.md`, and post-assignment dirty workflow control files now produce a dedicated Codex review issue unless they were recorded in the assignment-time worktree baseline. This makes assignment-control protection bidirectional: DeepSeek cannot be assigned those files, and Codex review also blocks newly changed control files that appear after assignment.

Updated the review checklist, workflow guide, and required-snippet fixtures so the review-time workflow-control baseline rule remains documented and validated.

Covered cases:

- ready outbox changed-file evidence rejects workflow control files
- Codex review rejects post-assignment workflow control file changes missing from the baseline
- required handoff docs preserve the review-time workflow-control baseline rule

Latest focused verification:

- `python -m pytest tests/test_codex_review_gate.py -q` -> 57 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 241 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 260 ok
- `python -m ruff check utils/codex_review_gate.py utils/prepare_deepseek_task.py utils/validate_handoff_docs.py utils/dual_model_pipeline_check.py tests/test_codex_review_gate.py tests/test_prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- Anti-Placeholder scanner over scoped files -> no matches
- boundary-aware key-shaped scanner over scoped files -> no matches
- `git diff --check -- ...` -> ok

## 2026-08-02: Anti-Placeholder Scanner Pattern Coverage Guard

Enhanced `python -m utils.validate_handoff_docs` so both ready inbox assignments and ready outbox submissions must use the complete configured Anti-Placeholder scanner expression. A command that only starts with `rg` or mentions a subset of blocked-term patterns is now rejected before DeepSeek work can be assigned or accepted.

Tightened scanner command extraction so explanatory snippets such as `` `rg` `` or `` `rg.exe` `` in the task instructions are not mistaken for runnable commands, while wrapped commands such as `Write-Output rg ...` are still parsed and rejected by the `rg` command-family guard.

Covered cases:

- ready outbox Anti-Placeholder scan commands reject missing configured scanner patterns
- ready inbox Anti-Placeholder scan commands reject missing configured scanner patterns
- generated DeepSeek task assignments tell workers that scanner commands must include every configured scanner pattern
- scanner command extraction ignores one-token explanatory code spans but still surfaces wrongly wrapped scan commands

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 262 ok

## 2026-08-02: DeepSeek Pro Route Confirmation

Confirmed the operator-requested DeepSeek Flash to Pro switch is already reflected in package routing: the built-in write-side scene manifests use `deepseek-v4-pro` as `model.default_name`, and DeepSeek init presents Pro as the first/default sub-option. Historical workspace live-smoke artifacts that recorded `deepseek-v4-flash` were left unchanged for audit integrity.

Latest final verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 281 ok
- `python -m pytest tests/engine/test_prompt_assets.py tests/cli/test_init_command.py::TestPromptDeepSeekSubOption::test_default_first_option_is_pro -q` -> 62 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/engine/test_prompt_assets.py tests/cli/test_init_command.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- boundary-aware key-shaped scanner over scoped files -> no matches
- trailing whitespace scanner over scoped files -> no matches

## 2026-08-02: Anti-Placeholder Scan Path Delimiter Guard

Enhanced ready inbox and ready outbox validation so Anti-Placeholder `rg` / `rg.exe` scan commands must include an independent `--` token before the path list. The generated DeepSeek task command already used this delimiter; the new guard catches hand-written assignments or outbox evidence where scanner expressions and paths are not separated cleanly.

Updated the review checklist, workflow guide, task template, task spec schema, generated task text, and focused fixtures so DeepSeek receives the delimiter rule before implementation and Codex enforces the same rule during review.

Covered cases:

- ready outbox Anti-Placeholder scan commands reject missing `--` path delimiters
- ready inbox Anti-Placeholder scan commands reject missing `--` path delimiters
- generated task text instructs DeepSeek to use `--` before the scan path list
- required-snippet validation preserves the delimiter rule in checklist, workflow, template, and schema docs

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 265 ok

Latest final verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 284 ok
- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_scan_missing_path_delimiter tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_scan_missing_path_delimiter tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 3 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- boundary-aware key-shaped scanner over scoped files -> no matches
- trailing whitespace scanner over scoped files -> no matches

## 2026-08-02: DeepSeek Pro Route Recheck and Broad Scope Guard

Rechecked the operator request to move DeepSeek Flash to Pro. The package write-side route already resolves `write`, `overview`, `regenerate`, `fix`, and `repair` to `deepseek-v4-pro`; no package manifest default points to `deepseek-v4-flash`. Historical workspace live-smoke artifacts remain unchanged as audit records.

Added a ready-inbox allowed-scope guard so DeepSeek assignments cannot use broad top-level directory scopes such as `dayu`, `docs`, `src`, `tests`, `utils`, `.github`, or `workspace`. Narrower directory scopes such as `src/example_pkg` remain valid, and task generation now documents the same rule before DeepSeek starts work.

Covered cases:

- ready inbox validation rejects broad top-level allowed directory scopes
- task spec validation rejects broad top-level allowed directory scopes
- generated DeepSeek task text describes the broad-scope rule
- directory-scope diff-check tests still cover narrow directory scopes
- DeepSeek write-side manifests and init default keep Pro as the current route

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_broad_top_level_allowed_scope tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_broad_top_level_allowed_scope tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_diff_check_missing_allowed_directory tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_diff_check_missing_allowed_directory tests/test_codex_review_gate.py::test_review_gate_rejects_unreported_allowed_scope_worktree_change tests/test_codex_review_gate.py::test_review_gate_rejects_changed_file_in_forbidden_scope tests/test_codex_review_gate.py::test_review_gate_rejects_malformed_changed_file_code_span tests/test_codex_review_gate.py::test_review_gate_rejects_directory_changed_file_entry -q` -> 14 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 273 ok
- `python -m pytest tests/engine/test_prompt_assets.py tests/cli/test_init_command.py::TestPromptDeepSeekSubOption::test_default_first_option_is_pro -q` -> 62 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- package default scan for `deepseek-v4-flash` defaults -> no matches

Latest final verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 292 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/engine/test_prompt_assets.py tests/cli/test_init_command.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok

## 2026-08-02: Raw Path Section Parser for Stand-Ins

Closed a parser gap where ready-inbox path sections could silently drop exact empty markers such as `None` or `Not applicable` before the path validator saw them. Ready inbox allowed-files, forbidden-files, required-reading, and required-reading parity extraction now use the raw path item parser, so empty path stand-ins are surfaced as explicit validation issues instead of being ignored.

This keeps the legitimate worktree-baseline `None` marker behavior intact because baseline parsing already separates empty baseline markers before validating actual path entries.

Covered cases:

- ready inbox allowed scope reports `None` as an empty path stand-in
- ready inbox forbidden scope reports `Not applicable` as an empty path stand-in
- both ready inbox required-reading sections report `None` as an empty path stand-in
- normal ready inbox parsing and allowed-scope coverage checks remain green

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_unsafe_scope_paths tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_unsafe_ready_inbox_required_reading_paths -q` -> 2 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 275 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 294 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/engine/test_prompt_assets.py tests/cli/test_init_command.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- boundary-aware key-shaped scanner over changed scope -> no matches

## 2026-08-02: Same-List Scope Overlap Guard

Aligned the handoff validator with the workflow documentation that already required overlapping allowed or forbidden scopes to be rejected. `docs/handoff/deepseek_inbox.md` validation now rejects overlap inside `allowed_files` and inside `forbidden_files`, not only overlap between the two lists. The task generator, task template, review checklist, and spec schema now state the same rule so DeepSeek gets the scope constraint before implementation.

Covered cases:

- ready inbox validation rejects overlapping allowed scope entries such as `src/example_pkg` and `src/example_pkg/module.py`
- ready inbox validation rejects overlapping forbidden scope entries such as `private` and `private/generated`
- task spec validation rejects overlapping entries inside both `allowed_files` and `forbidden_files`
- generated DeepSeek task text describes the same-list overlap rule
- required-snippet validation preserves the checklist, template, and schema wording

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_overlapping_scope_entries_in_same_list tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_overlapping_scope_entries_in_same_list -q` -> 2 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 275 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok

Latest final verification:

- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 294 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/engine/test_prompt_assets.py tests/cli/test_init_command.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok
- boundary-aware key-shaped scanner over changed scope -> no matches
- package default scan for `deepseek-v4-flash` defaults -> no matches

## 2026-08-02: Literal Scope Path Guard

Tightened DeepSeek task path validation so scope paths must stay literal repository-relative paths. Ready inbox and task spec validation now reject wildcard or glob-shaped entries such as `src/**/*.py` and `private/*` across allowed and forbidden scope paths, reusing the unsafe-path guard that also protects required-reading, worktree baseline, changed-file, and spec-file path fields.

Updated the task generator, workflow guide, review checklist, task template, task spec schema, and test plan so Codex assignments tell DeepSeek that path values must not use wildcards or glob metacharacters before implementation starts.

Rechecked the operator request to route DeepSeek Flash to Pro: the package scene manifests still keep write-side defaults on `deepseek-v4-pro`, and no real package prompt manifest has `default_name` set to `deepseek-v4-flash`. Flash remains present only as an explicit selectable model, tests, fixtures, or historical audit text.

Covered cases:

- ready inbox validation rejects wildcard and glob metacharacter scope entries such as `src/**/*.py`
- task spec validation rejects wildcard and glob metacharacter path fields
- generated DeepSeek task text describes the literal-path rule
- required-snippet validation preserves the checklist, workflow, template, and schema wording

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_unsafe_scope_paths tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_unsafe_scope_paths tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 3 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 275 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 294 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/engine/test_prompt_assets.py tests/cli/test_init_command.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok
- package prompt manifest scan for `default_name.*deepseek-v4-flash` -> no matches

## 2026-08-02: Path Stand-In Guard

Added a reusable path stand-in guard so DeepSeek task path lists cannot use values such as `N/A`, `TBD`, `unknown`, or `no files` as if they were repository paths. Ready inbox validation now reports explicit empty path stand-in issues for allowed scope, forbidden scope, required-reading, worktree baseline path entries after baseline empty markers are removed, changed-file path entries after no-change markers are removed, and other repository-relative path lists that use the shared validator.

Updated `utils.prepare_deepseek_task` so required-reading path validation rejects the same stand-ins before rendering a CLI or spec-file assignment. The generated task text, workflow guide, review checklist, task template, task spec schema, and test plan now document the rule.

Covered cases:

- ready inbox validation rejects `N/A` in allowed scope paths
- ready inbox validation rejects `TBD` in forbidden scope paths
- ready inbox required-reading sections reject `N/A` path stand-ins
- task spec validation rejects path stand-ins in `allowed_files`, `forbidden_files`, and `required_reading`
- generated DeepSeek task text tells workers not to use empty path stand-ins

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_unsafe_scope_paths tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_unsafe_ready_inbox_required_reading_paths tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_unsafe_scope_paths tests/test_prepare_deepseek_task.py::test_validate_spec_rejects_unsafe_required_reading_paths tests/test_prepare_deepseek_task.py::test_render_task_describes_ready_outbox_evidence_requirements -q` -> 5 ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 294 ok
- `python -m ruff check utils/validate_handoff_docs.py utils/prepare_deepseek_task.py utils/codex_review_gate.py utils/dual_model_pipeline_check.py tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py tests/engine/test_prompt_assets.py tests/cli/test_init_command.py` -> ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- <changed scope>` -> ok

## 2026-08-02: Soft Failure Verification Evidence Guard

Extended assigned-command verification evidence checks so pytest soft-failure summaries cannot be presented as clean completion. Ready outbox evidence now treats expected-failure, unexpected-green-status, and warning-output-alone wording as failing evidence even when the same line claims `exit 0` or `exited 0`.

Kept the warning rule narrow: generic warning counts are not rejected by this change, but claims that warning output alone proves success cannot stand in for actual green verification.

Covered cases:

- handoff docs validation rejects assigned command evidence such as `1 xfailed, exited 0`
- handoff docs validation rejects assigned command evidence such as `1 xpassed, exited 0`
- handoff docs validation rejects assigned command evidence that claims warning output alone and `exited 0`
- Codex review gate surfaces the same failures for ready outbox review

Latest focused verification:

- `python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_soft_failure_assigned_verification_result tests/test_codex_review_gate.py::test_review_gate_rejects_soft_failure_assigned_verification_result -q` -> 14 ok
- `python -m ruff check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py -q` -> 358 ok
- `python -m pytest tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 19 ok
- `python -m utils.validate_handoff_docs --json` -> ok
- `python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok

## 2026-08-06: Ready Outbox Metadata Stand-In Guard

Tightened `python -m utils.validate_handoff_docs` so review-ready DeepSeek outbox metadata cannot use empty task stand-ins such as `unknown` or `TBD` for `Message ID` and `Task`. This closes the review-state gap where mismatched inbox/outbox metadata could be surfaced, but the outbox's own stand-in metadata was not explicitly rejected as non-concrete delivery evidence.

Covered cases:

- ready outbox `Message ID` rejects `unknown` as an empty stand-in
- ready outbox `Task` rejects `TBD` as an empty stand-in
- existing inbox/outbox mismatch reporting remains intact

Latest focused verification:

- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_outbox_metadata_stand_ins -q` -> 1 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 598 passed
- `F:\claude-workspace\dayu-agent\.venv\Scripts\ruff.exe check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `uv run --no-project python -m utils.validate_handoff_docs --json` -> ok
- `uv run --no-project python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `uv run --no-project python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py test_plan.md` -> ok

## 2026-08-06: Waiting Outbox Blank Metadata Guard

Tightened ready-task lifecycle validation so a `READY_FOR_DEEPSEEK` inbox paired with a `WAITING_FOR_DEEPSEEK` outbox must still carry matching `Message ID` and `Task` metadata. Blank outbox metadata now reports an explicit mismatch using `<empty>`, instead of being skipped by truthy-only comparison.

Covered cases:

- ready inbox paired with waiting outbox blank `Message ID` reports `outbox=<empty>`
- ready inbox paired with waiting outbox blank `Task` reports `outbox=<empty>`
- existing non-empty message-id and task-code mismatch messages remain unchanged

Latest focused verification:

- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_ready_inbox_with_blank_waiting_outbox_metadata tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_message_id_mismatch tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_task_code_mismatch -q` -> 3 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 599 passed
- `F:\claude-workspace\dayu-agent\.venv\Scripts\ruff.exe check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `uv run --no-project python -m utils.validate_handoff_docs --json` -> ok
- `uv run --no-project python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `uv run --no-project python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py test_plan.md progress.md` -> ok

## 2026-08-06: Waiting State Metadata Reset Guard

Tightened waiting-state lifecycle validation so `WAITING_FOR_TASK` handoff docs must clear task assignment metadata back to `unassigned`. A waiting inbox or outbox that still carries an old `Message ID` or `Task` now fails validation, reducing the risk that a future assignment inherits stale task identity.

Covered cases:

- clean waiting inbox/outbox metadata still validates
- waiting outbox with stale `Message ID` and `Task` is rejected
- waiting inbox with stale `Message ID` and `Task` is rejected

Latest focused verification:

- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_accepts_waiting_state tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_waiting_state_with_stale_outbox_metadata tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_waiting_state_with_stale_inbox_metadata -q` -> 3 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 601 passed
- `F:\claude-workspace\dayu-agent\.venv\Scripts\ruff.exe check utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py` -> ok
- `uv run --no-project python -m utils.validate_handoff_docs --json` -> ok
- `uv run --no-project python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `uv run --no-project python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py tests\test_validate_handoff_docs.py test_plan.md progress.md` -> ok

## 2026-08-06: Nonzero Verification Exit Code Guard

Tightened ready-outbox verification result parsing so any nonzero command exit code, such as `exited 2` or `exit code 4`, is treated as failing evidence. The handoff validator and Codex review gate now share this protection, so an assigned command cannot hide a failed local run behind a later clean `exited 0` line.

Covered cases:

- handoff docs validation rejects an assigned command result that says `exited 2` even when another result line for the same command says `exited 0`
- Codex review gate surfaces the same nonzero-exit assigned-command failure
- Codex review still rejects unbulleted assigned-command result prose via the integrated handoff validator

Latest focused verification:

- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_nonzero_assigned_verification_exit_code tests/test_codex_review_gate.py::test_review_gate_rejects_nonzero_assigned_verification_exit_code -q` -> failed before implementation
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py::test_validate_handoff_docs_rejects_nonzero_assigned_verification_exit_code tests/test_codex_review_gate.py::test_review_gate_rejects_nonzero_assigned_verification_exit_code tests/test_codex_review_gate.py::test_review_gate_rejects_unbulleted_assigned_verification_result -q` -> 3 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py -q` -> 520 passed
- `uv run --no-project --with pytest python -m pytest tests/test_validate_handoff_docs.py tests/test_prepare_deepseek_task.py tests/test_codex_review_gate.py tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py -q` -> 616 passed
- `F:\claude-workspace\dayu-agent\.venv\Scripts\ruff.exe check utils/validate_handoff_docs.py utils/codex_review_gate.py tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py` -> ok
- `uv run --no-project python -m utils.validate_handoff_docs --json` -> ok
- `uv run --no-project python -m utils.codex_review_gate --allow-waiting --json` -> ok
- `uv run --no-project python -m utils.dual_model_pipeline_check --json` -> ok
- `git diff --check -- utils\validate_handoff_docs.py utils\codex_review_gate.py tests\test_validate_handoff_docs.py tests\test_codex_review_gate.py test_plan.md progress.md` -> ok
