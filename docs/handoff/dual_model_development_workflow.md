# Dual-Model Development Workflow

This repository supports a supervised dual-model workflow:

- Codex: planner, architect, reviewer, debugger, and final gatekeeper.
- DeepSeek: scoped implementation worker for low-cost, high-volume coding tasks.

DeepSeek should write code only from a bounded inbox task. Codex should prepare the task, verify the output, and decide whether the change can move forward.
Before assigning a task, Codex may run `python -m utils.dual_model_pipeline_check` to verify the workflow files are healthy. Automation and CI can use `python -m utils.validate_handoff_docs --json`, `python -m utils.codex_review_gate --json`, or `python -m utils.dual_model_pipeline_check --json` for machine-readable reports.
Cross-platform continuation instructions live in `docs/handoff/cross_platform_continuation.md`.
Codex can prepare a bounded task with `python -m utils.prepare_deepseek_task --dry-run ...`, then rerun without `--dry-run` to write the canonical inbox. For longer assignments, Codex can store the task input as repository-local JSON and call `python -m utils.prepare_deepseek_task --spec-file <path> --dry-run`; the schema is documented in `docs/handoff/deepseek_task_spec_schema.md`.
Use `--reset-outbox --validate-repository` when assigning a new task after a previous DeepSeek submission.
When `docs/handoff/deepseek_inbox.md` is marked `Status: READY_FOR_DEEPSEEK`, `python -m utils.validate_handoff_docs` also enforces concrete task metadata, allowed and forbidden files, acceptance criteria, verification commands, and required outbox evidence.
Ready inbox tasks must keep a dedicated `## Required Outbox Evidence` section.
Ready inbox `## Required Outbox` section must list the same evidence categories required from DeepSeek.
Ready inbox `## Required Outbox Evidence` section must list changed files, verification commands, checked acceptance, scan, scope deviations, and unresolved questions or blockers.
Ready inbox required outbox evidence must say Anti-Placeholder clean result evidence appears on the same line as the parseable scan command.
Ready inbox required outbox evidence entries must be unique and listed as at least eight bullet items.
Ready outbox summary must use at least two concrete bullet items and not generic completion wording.
Ready outbox changed-file evidence must not list workflow control files.
Allowed, forbidden, required-reading, and spec-file paths must be repository-relative. URLs, drive names, absolute paths, wildcards, glob metacharacters, embedded whitespace, VCS/dependency/cache directories, `.` or `..` path segments, duplicate paths, and overlapping allowed or forbidden scopes are rejected.
Ready inbox required-reading paths must point to existing files when repository validation runs after assignment.
Ready inbox required-reading paths may include the canonical inbox, but must not list the mutable outbox or root shortcut files.
Task preparation applies the same control-file required-reading rule before rendering CLI or spec-file assignments.
The two ready inbox required-reading sections must list the same paths.
Both ready inbox required-reading sections must include `AGENTS.md`, `spec.md`, `architecture.md`, `task.md`, and `docs/handoff/deepseek_inbox.md`.
Ready inbox tasks must include non-empty `## Input Contracts` and `## Output Contracts` sections.
Ready inbox contract items must not be empty stand-ins such as None, N/A, TBD, or unknown.
Ready inbox task text values must not use empty stand-ins such as None, N/A, TBD, or unknown.
Ready inbox path entries must not use empty stand-ins such as None, N/A, TBD, or unknown.
Path entries that contain embedded Markdown backticks, line breaks, wildcards, or glob metacharacters are rejected before task rendering.
Ready inbox path entries must not contain embedded whitespace.
Ready inbox path entries must not target VCS, dependency, or cache directories.
Ready inbox allowed scope must not include the DeepSeek inbox, DeepSeek outbox, or root shortcut files.
Ready inbox allowed scope must not include workflow control files.
Ready inbox allowed scope must not use broad top-level directory scopes.
Ready inbox path entries must not contain wildcards or glob metacharacters.
Ready inbox path entries must not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes.
Review-ready workflow control file worktree changes must either appear in the assignment-time baseline or block Codex review.
Review-ready handoff control file worktree changes must either appear in the assignment-time baseline or block Codex review.
Ready inbox assignments require `CODEX_GATE: PASS`; waiting inbox files can keep `CODEX_GATE: REQUIRED`.
Generated ready inbox tasks include `## Worktree Baseline`, a git-status snapshot taken before assignment so review can distinguish pre-existing local changes from new implementation changes.
Worktree baseline entries must be safe repository-relative paths, unique, and not mixed with `None`.
Worktree baseline entries must not overlap allowed files.
Review-ready worktree baseline entries must still be dirty in git status.
Generated task metadata, narrative fields, stop conditions, and verification commands must stay non-empty single-line text.
Ready inbox verification commands must be unique.
Ready inbox verification commands must use standalone command tokens and no shell control operators.
Ready inbox verification commands must start with direct command families, not shell wrappers.
Ready inbox verification commands must not use shell redirection.
Ready inbox verification commands must not use command substitution such as `$(...)` or backticks.
Ready inbox verification commands must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.
Ready inbox verification commands must not use response-file or splatting arguments such as `@args.txt`.
Ready inbox verification commands must not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.
No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.
Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.
Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.
Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.
Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.
Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.
Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.
Ready inbox verification commands must mention each concrete allowed file as a path token.
Ready inbox `git diff --check` commands must mention every allowed file or directory scope as a path token.
Ready inbox `git diff --check` commands with pathspecs must use `--` before the path list.
Ready inbox Anti-Placeholder scan command must include a concrete scanner expression.
Ready inbox Anti-Placeholder scan command must start with `rg` or `rg.exe`.
Ready inbox Anti-Placeholder scan command must include every configured scanner pattern.
Ready inbox Anti-Placeholder scan command must use `--` before the path list.
Ready inbox Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.
Ready inbox Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`.
Ready inbox Anti-Placeholder scan command must mention every allowed file as a path token.
Inbox and outbox lifecycle state is controlled only by the top-level `Status:` metadata before the first section heading.
Top-level metadata fields must not be repeated.
The inbox/outbox lifecycle is state-checked: `WAITING_FOR_TASK` pairs with `WAITING_FOR_TASK`, while `READY_FOR_DEEPSEEK` pairs with `WAITING_FOR_DEEPSEEK` or `READY_FOR_CODEX_REVIEW` using the same message id and task code.
Ready outbox changed files must stay within ready inbox allowed scope and outside forbidden scope.
Ready outbox acceptance criteria must be recorded as checked `- [x] ...` evidence items; generic summaries are rejected.
Ready outbox checked acceptance evidence must cover every assigned inbox criterion.
Ready outbox verification results must include every assigned inbox command with clean result evidence.
Checked acceptance evidence that says verification was skipped or not executed is rejected.
Checked acceptance evidence that says coverage is unverified or untested is rejected.
Checked acceptance evidence that says coverage is pending, deferred, or not applicable is rejected.
Ready outboxes must explicitly state unresolved questions or blockers, and non-None entries keep the handoff from being considered clean.
Ready outbox Anti-Placeholder evidence must include the scanner command and a clean result such as no matches or exit code 0. Scan evidence that says it was skipped, not executed, or failing is rejected.
Ready outbox Anti-Placeholder scan command must not use shell control operators.
Ready outbox Anti-Placeholder scan command must start with `rg` or `rg.exe`.
Ready outbox Anti-Placeholder scan command must include every configured scanner pattern.
Ready outbox Anti-Placeholder scan command must use `--` before the path list.
Ready outbox Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.
Ready outbox Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`.
Ready outbox Anti-Placeholder scan command must not include unresolved angle-bracket markers.
Ready outbox Anti-Placeholder scan command must mention every changed file as a path token.
Ready outbox Anti-Placeholder clean result markers inside the backticked scan command text do not count as scan result evidence.
Ready outbox Anti-Placeholder clean result evidence must appear on the parseable scanner command line.
Verification result evidence that says a command was skipped or not executed is treated as failing even when an exit code is also present.
Verification result evidence that says a command was dry-run, manual-only, simulated, synthetic, or fabricated is treated as failing.
Clean result markers inside the backticked command text do not count as verification evidence.
Ready outbox coverage-specific verification results must be clean.
Ready outbox verification evidence must start with direct command families, not shell wrappers.
Ready outbox verification evidence must not use shell redirection.
Ready outbox verification evidence must not use command substitution such as `$(...)` or backticks.
Ready outbox verification evidence must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.
Ready outbox verification evidence must not use response-file or splatting arguments such as `@args.txt`.
Ready outbox verification evidence must not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.
No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.
Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.
Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.
Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.
Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.
Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.
Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.
Ready outbox `pytest` evidence must mention every changed test Python file as a path token.
Ready outbox `ruff check` evidence must mention every changed Python file as a path token.
Ready outbox `git diff --check` evidence must mention every changed file as a path token.
Ready outbox `git diff --check` evidence with pathspecs must use `--` before the path list.
The focused GitHub Actions entry point is `.github/workflows/dual-model-gates.yml`.
Pipeline check includes a scoped blocked-term scan over handoff utilities, focused tests, templates, `test_plan.md`, and `progress.md`.
Ready inbox requirements must be unique and include at least three numbered items.
Ready inbox acceptance criteria must be unique and include at least three unchecked items.
Ready inbox stop conditions must be unique and include at least three items.
Ready inbox sections with unresolved angle-bracket markers are rejected.

## Flow

1. Codex writes or updates `docs/handoff/deepseek_inbox.md`, preferably using `python -m utils.prepare_deepseek_task`.
2. DeepSeek reads `DEEPSEEK_INBOX.md`, then implements only the assigned task.
3. DeepSeek writes `docs/handoff/deepseek_outbox.md` with `READY_FOR_CODEX_REVIEW`.
4. Run `python -m utils.validate_handoff_docs` to verify the handoff files are complete.
5. Run `python -m utils.codex_review_gate` or `python -m utils.dual_model_pipeline_check --require-ready` to build the local review gate report. Use `--json` on either command when another tool needs structured output.
6. Codex reviews using `CODEX_REVIEW.md` and `docs/handoff/codex_review_checklist.md`.
7. Codex runs verification and either accepts, requests changes, or slices a smaller follow-up task.

Use `docs/handoff/deepseek_task_template.md` when assigning a new DeepSeek task, `docs/handoff/deepseek_task_spec_schema.md` for JSON task files, and `docs/handoff/deepseek_assignment_examples.md` for safe CLI examples. Use `docs/handoff/codex_review_template.md` when recording Codex review results.

## Task Size Rules

Each DeepSeek task should usually:

- modify 1 to 5 files
- have explicit allowed and forbidden paths
- record the pre-assignment worktree baseline
- have input and output contracts
- have concrete acceptance criteria
- include exact verification commands
- avoid cross-module redesign

If a task needs architecture decisions, schema changes, concurrency design, security review, or production trading behavior, Codex must design the task before DeepSeek implements it.

## Good DeepSeek Tasks

- CRUD endpoints
- repository methods
- small database models
- deterministic data cleaning scripts
- adapter glue code
- focused unit tests
- local refactors with unchanged interfaces
- fixture generation
- documentation updates from current behavior

## Tasks Codex Must Own

- architecture and module boundaries
- state machines
- recovery and rollback semantics
- database uniqueness and concurrency design
- trading, order, or safety-critical decisions
- secret handling
- model routing policy
- prompt safety boundaries
- final acceptance

## Required DeepSeek Task Template

````markdown
# Current Task: <short title>

## Objective

<one paragraph>

## Allowed Files

- `path/to/file.py`
- `tests/path/test_file.py`

## Forbidden Files

- `path/not/allowed.py`

## Requirements

1. ...
2. ...

## Acceptance Criteria

- [ ] ...
- [ ] ...

## Verification Commands

```powershell
python -m pytest ...
python -m ruff check ...
```

## Stop Conditions

- Stop if an interface is missing or ambiguous.
- Stop if implementation requires files outside allowed scope.
- Stop if tests require deleting or weakening existing assertions.
````

## Completion Is Not Self-Certifying

DeepSeek may say a task is complete, but completion is only accepted after Codex verifies:

- changed files
- diff scope
- `python -m utils.codex_review_gate`
- test behavior
- Anti-Placeholder command and result evidence
- checked acceptance criteria evidence
- unresolved questions or blockers
- residual risks
