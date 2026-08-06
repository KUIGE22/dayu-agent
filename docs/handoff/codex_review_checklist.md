# Codex Review Checklist

Use this checklist after DeepSeek writes `docs/handoff/deepseek_outbox.md`.

## Review Stance

Treat the implementation as untrusted until verified. Do not rely on the outbox summary alone.

## Blocking Checks

- The implementation matches the current task in `docs/handoff/deepseek_inbox.md`.
- Handoff root shortcuts point to their canonical docs under `docs/handoff/`.
- Ready outbox `Message ID` and `Task` are concrete and match the assigned inbox.
- Ready inbox assignments use `CODEX_GATE: PASS`.
- Ready inbox required-reading entries are safe, unique, repository-relative paths.
- Ready inbox required-reading entries point to existing files.
- Ready inbox required-reading entries may include the canonical inbox, but not the mutable outbox or root shortcuts.
- Ready inbox `## Required Reading Before Editing` and `## Required Reading` list the same paths.
- Ready inbox required-reading sections include `AGENTS.md`, `spec.md`, `architecture.md`, `task.md`, and `docs/handoff/deepseek_inbox.md`.
- Ready inbox includes non-empty `## Input Contracts` and `## Output Contracts` sections.
- Ready inbox contract items cannot be empty stand-ins such as None, N/A, TBD, or unknown.
- Ready inbox path entries do not use empty stand-ins such as None, N/A, TBD, or unknown.
- Ready inbox path entries do not contain wildcards or glob metacharacters.
- Ready inbox path entries do not contain embedded whitespace.
- Ready inbox path entries do not target VCS, dependency, or cache directories.
- Ready inbox path entries do not contain embedded Markdown backticks or line breaks.
- Ready inbox includes a dedicated `## Required Outbox Evidence` section.
- Ready inbox `## Required Outbox Evidence` section lists changed files, verification commands, checked acceptance, scan, scope deviations, and unresolved questions or blockers.
- Ready inbox required outbox evidence entries are unique and listed as at least eight bullet items.
- Ready outbox summary uses at least two concrete bullet items and not generic completion wording.
- Ready outbox changed-file evidence must not list workflow control files.
- Ready inbox and ready outbox path entries do not contain `.` or `..` path segments.
- Only allowed files were modified.
- Ready inbox allowed scope does not include handoff control files or root shortcuts.
- Ready inbox allowed scope must not include workflow control files.
- Ready inbox allowed scope must not use broad top-level directory scopes.
- Ready inbox allowed and forbidden scope entries do not overlap entries in the same list.
- Ready inbox path entries do not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes.
- Review-ready workflow control file worktree changes must either appear in the assignment-time baseline or block Codex review.
- Forbidden files were not modified.
- The ready inbox includes `## Worktree Baseline` from assignment time.
- Ready inbox worktree baseline entries are safe, unique, and not mixed with `None`.
- Ready inbox worktree baseline entries do not overlap allowed files.
- Review-ready worktree baseline entries must still be dirty in git status.
- Ready inbox verification commands are parseable fenced commands or backticked bullet commands.
- Ready inbox verification commands are unique.
- Ready inbox verification commands use standalone command tokens and no shell control operators.
- Ready inbox verification commands start with direct command families, not shell wrappers.
- Ready inbox verification commands do not use shell redirection.
- Ready inbox verification commands do not use command substitution such as `$(...)` or backticks.
- Ready inbox verification commands do not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.
- Ready inbox verification commands do not use response-file or splatting arguments such as `@args.txt`.
- Ready inbox verification commands do not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.
- No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.
- Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.
- Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.
- Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.
- Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.
- Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.
- Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.
- Ready inbox verification commands mention each concrete allowed file as a path token.
- Ready inbox `git diff --check` commands mention every allowed file or directory scope as a path token.
- Ready inbox `git diff --check` commands with pathspecs use `--` before the path list.
- Ready inbox Anti-Placeholder scan command includes a concrete scanner expression.
- Ready inbox Anti-Placeholder scan command starts with `rg` or `rg.exe`.
- Ready inbox Anti-Placeholder scan command includes every configured scanner pattern.
- Ready inbox Anti-Placeholder scan command uses `--` before the path list.
- Ready inbox Anti-Placeholder scan command does not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.
- Ready inbox Anti-Placeholder scan command does not use response-file or splatting arguments such as `@args.txt`.
- Ready inbox Anti-Placeholder scan command mentions every allowed file as a path token.
- `python -m utils.codex_review_gate --json` compares outbox changed files against inbox allowed and forbidden scopes.
- Review-ready changed-file entries resolve to concrete files.
- Review-ready changed-file entries are safe, unique, repository-relative paths.
- Review-ready changed-file entries do not list handoff control files or root shortcuts as implementation changes.
- `python -m utils.codex_review_gate --json` rejects changed-file entries that list handoff control files.
- Review-ready changed-file entries appear in git worktree evidence.
- Review-ready git worktree changes inside allowed or forbidden scope are disclosed in the outbox.
- Review-ready changed-file evidence does not mix no-change stand-ins with real paths.
- Post-assignment worktree changes outside the recorded baseline are disclosed in the outbox.
- Handoff root shortcut changes are treated as control-plane changes, not implementation disclosure gaps.
- Review scans include changed files, the DeepSeek inbox, and the DeepSeek outbox for key-shaped strings.
- Review scans include handoff root shortcuts for key-shaped strings.
- Existing public interfaces and schemas were not changed unless explicitly allowed.
- No tests were deleted, weakened, skipped, or converted to test doubles without explicit approval.
- No blocked scanner terms from `utils.codex_review_gate` remain in changed implementation paths or the DeepSeek outbox.
- Error paths required by the task are handled.
- Database writes, filesystem writes, network calls, and external side effects are idempotent or explicitly guarded.
- `python -m utils.validate_handoff_docs --json` is ok.
- `python -m utils.codex_review_gate --json` is ok after DeepSeek marks the outbox ready.
- `python -m utils.dual_model_pipeline_check --require-ready --json` is ok.
- `python -m utils.validate_handoff_docs --json` rejects nonzero ready-outbox verification results.
- `.github/workflows/dual-model-gates.yml` remains wired to the focused tests and JSON gates.
- Pipeline check includes a scoped blocked-term scan over handoff utilities, focused tests, templates, `test_plan.md`, and `progress.md`.
- Ready inbox requirements are unique and include at least three numbered items.
- Ready inbox acceptance criteria are unique and include at least three unchecked items.
- Ready inbox stop conditions are unique and include at least three items.
- Ready inbox sections do not contain unresolved angle-bracket markers.
- Verification commands were actually run and their results match the outbox.
- Ready outbox verification evidence includes pytest, ruff, and `git diff --check` results.
- Ready outbox verification result lines use parseable backticked command entries.
- Ready outbox command-family evidence uses standalone command tokens and does not append shell control operators.
- Ready outbox verification evidence starts with direct command families, not shell wrappers.
- Ready outbox verification evidence includes every exact command assigned in the inbox.
- Ready outbox verification evidence uses parsed backticked commands, not substring matches.
- Exact assigned-command matching covers fenced commands and backticked bullet commands.
- Each assigned verification command has clean result evidence such as `exited 0`.
- Clean result markers inside the backticked command text do not count as verification evidence.
- Any failing result for an assigned verification command is a review issue, even if another result line is clean.
- Verification result evidence that says a command was dry-run, manual-only, simulated, synthetic, or fabricated is treated as failing.
- Ready outbox coverage-specific verification results are clean.
- Ready outbox verification evidence does not use shell redirection.
- Ready outbox verification evidence does not use command substitution such as `$(...)` or backticks.
- Ready outbox verification evidence does not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.
- Ready outbox verification evidence does not use response-file or splatting arguments such as `@args.txt`.
- Ready outbox verification evidence does not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.
- No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.
- Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.
- Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.
- Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.
- Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.
- Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.
- Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.
- Ready outbox `pytest` evidence mentions every changed test Python file as a path token.
- Ready outbox `ruff check` evidence mentions every changed Python file as a path token.
- Ready outbox `git diff --check` evidence mentions every changed file as a path token.
- Ready outbox `git diff --check` evidence with pathspecs uses `--` before the path list.
- Ready outbox changed files stay within ready inbox allowed scope and outside forbidden scope.
- Negated success wording such as `not successful` is not accepted as clean result evidence.
- Skipped or not-executed verification wording is not accepted as clean result evidence.
- Ready outbox acceptance criteria are listed as checked `- [x] ...` evidence items, not generic summaries.
- Ready outbox checked acceptance evidence covers every assigned inbox criterion.
- Ready outbox checked acceptance evidence starts with the assigned criterion before adding details.
- `python -m utils.validate_handoff_docs --json` rejects checked acceptance evidence with negative completion wording.
- Checked acceptance evidence must not contain negative completion wording.
- Checked acceptance evidence is not skipped or not-executed.
- Checked acceptance evidence is not unverified or untested.
- Checked acceptance evidence is not pending, deferred, or marked as not applicable.
- Ready outbox Anti-Placeholder evidence includes both scanner command and clean result.
- Ready outbox Anti-Placeholder evidence is not an empty stand-in such as None, N/A, or no scan.
- Ready outbox Anti-Placeholder clean result evidence says the scanner found no matches, not only an exit code.
- Ready outbox Anti-Placeholder evidence is not skipped, not-executed, or failing.
- Ready outbox Anti-Placeholder scan command uses exact command text without shell control operators.
- Ready outbox Anti-Placeholder scan command starts with `rg` or `rg.exe`.
- Ready outbox Anti-Placeholder scan command includes every configured scanner pattern.
- Ready outbox Anti-Placeholder scan command uses `--` before the path list.
- Ready outbox Anti-Placeholder scan command does not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.
- Ready outbox Anti-Placeholder scan command does not use response-file or splatting arguments such as `@args.txt`.
- Ready outbox Anti-Placeholder scan command does not include unresolved angle-bracket markers.
- Ready outbox Anti-Placeholder scan command mentions every changed file as a path token.
- `python -m utils.validate_handoff_docs --json` rejects non-None ready-outbox scope deviations.
- `## Scope Deviations` is explicit; anything other than `None` is treated as a review issue.
- `## Unresolved Questions or Blockers` is explicit; anything other than `None` blocks a clean handoff.
- Any generated artifact is deterministic or has an explicit reason not to be deterministic.

## Risk Review

Check for:

- silent failure
- partial writes without rollback
- duplicate execution
- race conditions
- data loss
- stale cache use
- swallowed exceptions
- hidden network behavior
- secret logging
- scope creep

## Output Format

Return:

```text
CODEX_REVIEW: PASS | BLOCKED

Blocking issues:
- ...

Non-blocking issues:
- ...

Verification performed:
- ...

Decision:
- accept / request changes / reassign task
```

Only mark `PASS` when the task acceptance criteria are directly verified.
