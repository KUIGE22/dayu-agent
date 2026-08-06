"""Validate the DeepSeek/Codex handoff control documents."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Sequence

READY_FOR_REVIEW = "READY_FOR_CODEX_REVIEW"
READY_FOR_DEEPSEEK = "READY_FOR_DEEPSEEK"
WAITING_FOR_TASK = "WAITING_FOR_TASK"
WAITING_FOR_DEEPSEEK = "WAITING_FOR_DEEPSEEK"
ANGLE_BRACKET_MARKER_PATTERN = re.compile(r"<[^>\r\n]+>")
NOT_RUN = "Not run"
INBOX_PATH = Path("docs/handoff/deepseek_inbox.md")
OUTBOX_PATH = Path("docs/handoff/deepseek_outbox.md")

REQUIRED_FILES: tuple[Path, ...] = (
    Path("AGENTS.md"),
    Path("DEEPSEEK_INBOX.md"),
    Path("CODEX_REVIEW.md"),
    Path("spec.md"),
    Path("architecture.md"),
    Path("task.md"),
    Path("progress.md"),
    Path("decisions.md"),
    Path("test_plan.md"),
    INBOX_PATH,
    OUTBOX_PATH,
    Path("docs/handoff/codex_review_checklist.md"),
    Path("docs/handoff/dual_model_development_workflow.md"),
    Path("docs/handoff/cross_platform_continuation.md"),
    Path("docs/handoff/deepseek_task_template.md"),
    Path("docs/handoff/deepseek_task_spec_schema.md"),
    Path("docs/handoff/deepseek_assignment_examples.md"),
    Path("docs/handoff/codex_review_template.md"),
)

REQUIRED_SNIPPETS: dict[Path, tuple[str, ...]] = {
    INBOX_PATH: (
        "# DeepSeek Inbox",
        "Status:",
        "Message ID:",
        "Task:",
        "CODEX_GATE:",
        "## Operating Role",
        "## Required Reading Before Editing",
        "## Current Task",
        "## Global Implementation Rules",
        "## Anti-Placeholder Scan",
        "## Required Outbox Evidence",
    ),
    OUTBOX_PATH: (
        "# DeepSeek Outbox",
        "Status:",
        "Message ID:",
        "Task:",
        "## Summary",
        "## Changed Files",
        "## Verification Commands and Results",
        "## Acceptance Criteria",
        "## Scope Deviations",
        "## Anti-Placeholder Scan",
        "## Unresolved Questions or Blockers",
    ),
    Path("docs/handoff/codex_review_checklist.md"): (
        "# Codex Review Checklist",
        "## Blocking Checks",
        "Ready outbox acceptance criteria are listed as checked `- [x] ...` evidence items",
        "Ready outbox checked acceptance evidence covers every assigned inbox criterion",
        "Ready outbox checked acceptance evidence starts with the assigned criterion",
        "Checked acceptance evidence is not skipped or not-executed",
        "Checked acceptance evidence is not unverified or untested",
        "Checked acceptance evidence is not pending, deferred, or marked as not applicable",
        "Ready outbox Anti-Placeholder evidence includes both scanner command and clean result",
        "Ready outbox Anti-Placeholder evidence is not an empty stand-in such as None, N/A, or no scan",
        "Ready outbox Anti-Placeholder evidence is not skipped, not-executed, or failing",
        "Ready outbox Anti-Placeholder clean result markers inside the backticked scan command text do not count as scan result evidence.",
        "Ready outbox Anti-Placeholder clean result evidence appears on the parseable scanner command line.",
        "Ready outbox Anti-Placeholder scan command uses exact command text without shell control operators.",
        "Ready outbox Anti-Placeholder scan command starts with `rg` or `rg.exe`.",
        "Ready outbox Anti-Placeholder scan command includes every configured scanner pattern.",
        "Ready outbox Anti-Placeholder scan command uses `--` before the path list.",
        "Ready outbox Anti-Placeholder scan command does not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Ready outbox Anti-Placeholder scan command does not use response-file or splatting arguments such as `@args.txt`.",
        "Ready outbox Anti-Placeholder scan command does not include unresolved angle-bracket markers.",
        "Ready outbox Anti-Placeholder scan command mentions every changed file as a path token.",
        "Ready outbox command-family evidence uses standalone command tokens",
        "Ready outbox verification evidence starts with direct command families, not shell wrappers.",
        "Ready outbox verification evidence does not use shell redirection.",
        "Ready outbox verification evidence does not use command substitution such as `$(...)` or backticks.",
        "Ready outbox verification evidence does not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Ready outbox verification evidence does not use response-file or splatting arguments such as `@args.txt`.",
        "Exact assigned-command matching covers fenced commands and backticked bullet commands.",
        "Each assigned verification command has clean result evidence such as `exited 0`.",
        "Clean result markers inside the backticked command text do not count as verification evidence.",
        "Any failing result for an assigned verification command is a review issue, even if another result line is clean.",
        "Verification result evidence that says a command was dry-run, manual-only, simulated, synthetic, or fabricated is treated as failing.",
        "Ready outbox coverage-specific verification results are clean.",
        "Ready outbox verification evidence does not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.",
        "No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.",
        "Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.",
        "Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.",
        "Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.",
        "Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.",
        "Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.",
        "Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.",
        "Ready outbox `pytest` evidence mentions every changed test Python file as a path token.",
        "Ready outbox `ruff check` evidence mentions every changed Python file as a path token.",
        "Ready outbox `git diff --check` evidence mentions every changed file as a path token.",
        "Ready outbox `git diff --check` evidence with pathspecs uses `--` before the path list.",
        "Ready outbox changed files stay within ready inbox allowed scope and outside forbidden scope.",
        "Ready outbox changed-file evidence must not list workflow control files.",
        "Pipeline check includes a scoped blocked-term scan over handoff utilities, focused tests, templates, `test_plan.md`, and `progress.md`.",
        "Ready inbox required-reading entries may include the canonical inbox",
        "Ready inbox required-reading sections include `AGENTS.md`, `spec.md`, `architecture.md`, `task.md`, and `docs/handoff/deepseek_inbox.md`.",
        "Ready inbox includes non-empty `## Input Contracts` and `## Output Contracts` sections.",
        "Ready inbox contract items cannot be empty stand-ins such as None, N/A, TBD, or unknown.",
        "Ready inbox path entries do not use empty stand-ins such as None, N/A, TBD, or unknown.",
        "Ready inbox path entries do not contain wildcards or glob metacharacters.",
        "Ready inbox path entries do not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes.",
        "Ready inbox path entries do not contain embedded whitespace.",
        "Ready inbox path entries do not target VCS, dependency, or cache directories.",
        "Ready inbox allowed scope must not include workflow control files.",
        "Ready inbox allowed and forbidden scope entries do not overlap entries in the same list.",
        "Review-ready workflow control file worktree changes must either appear in the assignment-time baseline or block Codex review.",
        "Ready inbox requirements are unique and include at least three numbered items.",
        "Ready inbox acceptance criteria are unique and include at least three unchecked items.",
        "Ready inbox stop conditions are unique and include at least three items.",
        "Ready inbox sections do not contain unresolved angle-bracket markers.",
        "Ready inbox includes a dedicated `## Required Outbox Evidence` section.",
        "Ready inbox `## Required Outbox Evidence` section lists changed files, verification commands, checked acceptance, scan, scope deviations, and unresolved questions or blockers.",
        "Ready inbox required outbox evidence entries are unique and listed as at least eight bullet items.",
        "Ready outbox summary uses at least two concrete bullet items and not generic completion wording.",
        "Ready inbox worktree baseline entries do not overlap allowed files.",
        "Review-ready worktree baseline entries must still be dirty in git status.",
        "Ready inbox verification commands are unique.",
        "Ready inbox verification commands use standalone command tokens and no shell control operators.",
        "Ready inbox verification commands start with direct command families, not shell wrappers.",
        "Ready inbox verification commands do not use shell redirection.",
        "Ready inbox verification commands do not use command substitution such as `$(...)` or backticks.",
        "Ready inbox verification commands do not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Ready inbox verification commands do not use response-file or splatting arguments such as `@args.txt`.",
        "Ready inbox verification commands do not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.",
        "No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.",
        "Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.",
        "Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.",
        "Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.",
        "Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.",
        "Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.",
        "Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.",
        "Ready inbox verification commands mention each concrete allowed file as a path token.",
        "Ready inbox `git diff --check` commands mention every allowed file or directory scope as a path token.",
        "Ready inbox `git diff --check` commands with pathspecs use `--` before the path list.",
        "Ready inbox Anti-Placeholder scan command includes a concrete scanner expression.",
        "Ready inbox Anti-Placeholder scan command starts with `rg` or `rg.exe`.",
        "Ready inbox Anti-Placeholder scan command includes every configured scanner pattern.",
        "Ready inbox Anti-Placeholder scan command uses `--` before the path list.",
        "Ready inbox Anti-Placeholder scan command does not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Ready inbox Anti-Placeholder scan command does not use response-file or splatting arguments such as `@args.txt`.",
        "Ready inbox Anti-Placeholder scan command mentions every allowed file as a path token.",
        "`## Unresolved Questions or Blockers` is explicit",
        "## Risk Review",
        "## Output Format",
    ),
    Path("docs/handoff/dual_model_development_workflow.md"): (
        "# Dual-Model Development Workflow",
        "Cross-platform continuation instructions live in `docs/handoff/cross_platform_continuation.md`.",
        "Ready outbox checked acceptance evidence must cover every assigned inbox criterion.",
        "Checked acceptance evidence that says verification was skipped or not executed is rejected",
        "Checked acceptance evidence that says coverage is unverified or untested is rejected",
        "Checked acceptance evidence that says coverage is pending, deferred, or not applicable is rejected",
        "Ready outbox Anti-Placeholder evidence must include the scanner command",
        "Ready outbox Anti-Placeholder clean result markers inside the backticked scan command text do not count as scan result evidence.",
        "Ready outbox Anti-Placeholder clean result evidence must appear on the parseable scanner command line.",
        "Ready outbox Anti-Placeholder scan command must not use shell control operators.",
        "Ready outbox Anti-Placeholder scan command must start with `rg` or `rg.exe`.",
        "Ready outbox Anti-Placeholder scan command must include every configured scanner pattern.",
        "Ready outbox Anti-Placeholder scan command must use `--` before the path list.",
        "Ready outbox Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Ready outbox Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`.",
        "Ready outbox Anti-Placeholder scan command must not include unresolved angle-bracket markers.",
        "Ready outbox Anti-Placeholder scan command must mention every changed file as a path token.",
        "Verification result evidence that says a command was skipped or not executed is treated as failing",
        "Verification result evidence that says a command was dry-run, manual-only, simulated, synthetic, or fabricated is treated as failing",
        "Clean result markers inside the backticked command text do not count as verification evidence.",
        "Ready outbox verification results must include every assigned inbox command with clean result evidence.",
        "Ready outbox coverage-specific verification results must be clean.",
        "Ready outbox verification evidence must start with direct command families, not shell wrappers.",
        "Ready outbox verification evidence must not use shell redirection.",
        "Ready outbox verification evidence must not use command substitution such as `$(...)` or backticks.",
        "Ready outbox verification evidence must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Ready outbox verification evidence must not use response-file or splatting arguments such as `@args.txt`.",
        "Ready outbox verification evidence must not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.",
        "No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.",
        "Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.",
        "Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.",
        "Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.",
        "Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.",
        "Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.",
        "Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.",
        "Ready outbox `pytest` evidence must mention every changed test Python file as a path token.",
        "Ready outbox `ruff check` evidence must mention every changed Python file as a path token.",
        "Ready outbox `git diff --check` evidence must mention every changed file as a path token.",
        "Ready outbox `git diff --check` evidence with pathspecs must use `--` before the path list.",
        "Ready outbox changed files must stay within ready inbox allowed scope and outside forbidden scope.",
        "Ready outbox changed-file evidence must not list workflow control files.",
        "Pipeline check includes a scoped blocked-term scan over handoff utilities, focused tests, templates, `test_plan.md`, and `progress.md`.",
        "Ready inbox required-reading paths may include the canonical inbox",
        "Both ready inbox required-reading sections must include `AGENTS.md`, `spec.md`, `architecture.md`, `task.md`, and `docs/handoff/deepseek_inbox.md`.",
        "Ready inbox tasks must include non-empty `## Input Contracts` and `## Output Contracts` sections.",
        "Ready inbox contract items must not be empty stand-ins such as None, N/A, TBD, or unknown.",
        "Ready inbox path entries must not use empty stand-ins such as None, N/A, TBD, or unknown.",
        "Ready inbox path entries must not contain wildcards or glob metacharacters.",
        "Ready inbox path entries must not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes.",
        "Ready inbox path entries must not contain embedded whitespace.",
        "Ready inbox path entries must not target VCS, dependency, or cache directories.",
        "Ready inbox allowed scope must not include workflow control files.",
        "Review-ready workflow control file worktree changes must either appear in the assignment-time baseline or block Codex review.",
        "Ready inbox requirements must be unique and include at least three numbered items.",
        "Ready inbox acceptance criteria must be unique and include at least three unchecked items.",
        "Ready inbox stop conditions must be unique and include at least three items.",
        "Ready inbox sections with unresolved angle-bracket markers are rejected.",
        "Ready inbox tasks must keep a dedicated `## Required Outbox Evidence` section.",
        "Ready inbox `## Required Outbox Evidence` section must list changed files, verification commands, checked acceptance, scan, scope deviations, and unresolved questions or blockers",
        "Ready inbox required outbox evidence entries must be unique and listed as at least eight bullet items.",
        "Ready outbox summary must use at least two concrete bullet items and not generic completion wording.",
        "Worktree baseline entries must not overlap allowed files.",
        "Review-ready worktree baseline entries must still be dirty in git status.",
        "Ready inbox verification commands must be unique",
        "Ready inbox verification commands must use standalone command tokens and no shell control operators",
        "Ready inbox verification commands must start with direct command families, not shell wrappers.",
        "Ready inbox verification commands must not use shell redirection.",
        "Ready inbox verification commands must not use command substitution such as `$(...)` or backticks.",
        "Ready inbox verification commands must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Ready inbox verification commands must not use response-file or splatting arguments such as `@args.txt`.",
        "Ready inbox verification commands must not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.",
        "No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.",
        "Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.",
        "Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.",
        "Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.",
        "Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.",
        "Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.",
        "Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.",
        "Ready inbox verification commands must mention each concrete allowed file as a path token.",
        "Ready inbox `git diff --check` commands must mention every allowed file or directory scope as a path token.",
        "Ready inbox `git diff --check` commands with pathspecs must use `--` before the path list.",
        "Ready inbox Anti-Placeholder scan command must include a concrete scanner expression.",
        "Ready inbox Anti-Placeholder scan command must start with `rg` or `rg.exe`.",
        "Ready inbox Anti-Placeholder scan command must include every configured scanner pattern.",
        "Ready inbox Anti-Placeholder scan command must use `--` before the path list.",
        "Ready inbox Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Ready inbox Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`.",
        "Ready inbox Anti-Placeholder scan command must mention every allowed file as a path token.",
        "## Flow",
        "## Task Size Rules",
        "## Required DeepSeek Task Template",
        "## Completion Is Not Self-Certifying",
    ),
    Path("docs/handoff/cross_platform_continuation.md"): (
        "# Cross-Platform Continuation Guide",
        "## GitHub Continuation",
        "codex/dual-model-research-mvp",
        "git clone https://github.com/KUIGE22/dayu-agent.git",
        "git checkout codex/dual-model-research-mvp",
        "git log -1 --oneline",
        "## macOS / Linux Setup",
        "python3.11 -m venv .venv",
        "source .venv/bin/activate",
        "## Windows Setup",
        "py -3.11 -m venv .venv",
        ".\\.venv\\Scripts\\Activate.ps1",
        "## Required Gate Commands",
        "python -m utils.validate_handoff_docs --json",
        "python -m utils.codex_review_gate --allow-waiting --json",
        "python -m utils.dual_model_pipeline_check --json",
        "Do not reuse absolute local paths from another computer.",
    ),
    Path("docs/handoff/deepseek_task_template.md"): (
        "# Current Task:",
        "Status: READY_FOR_DEEPSEEK",
        "CODEX_GATE: PASS",
        "## Objective",
        "## Required Reading",
        "`AGENTS.md`",
        "`spec.md`",
        "`architecture.md`",
        "`task.md`",
        "`docs/handoff/deepseek_inbox.md`",
        "## Input Contracts",
        "Do not use empty stand-ins such as None, N/A, TBD, or unknown as a contract.",
        "## Output Contracts",
        "## Allowed Files",
        "## Forbidden Files",
        "## Worktree Baseline",
        "Worktree baseline entries must not overlap allowed files.",
        "Requirements must be unique and include at least three numbered items.",
        "## Acceptance Criteria",
        "Acceptance criteria must be unique and include at least three unchecked items.",
        "Remove every angle-bracket marker before assigning the task.",
        "## Verification Commands",
        "Verification commands must be unique standalone command tokens and must not use shell control operators.",
        "Verification commands must start with direct command families, not shell wrappers.",
        "Verification commands must not use shell redirection.",
        "Verification commands must not use command substitution such as `$(...)` or backticks.",
        "Verification commands must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Verification commands must not use response-file or splatting arguments such as `@args.txt`.",
        "Verification commands must not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.",
        "No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.",
        "Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.",
        "Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.",
        "Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.",
        "Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.",
        "Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.",
        "Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.",
        "Verification commands must mention each concrete allowed file as a path token.",
        "Git diff-check commands must mention every allowed file or directory scope as a path token.",
        "Git diff-check commands with pathspecs must use `--` before the path list.",
        "Path values must not use wildcards or glob metacharacters.",
        "Path values must not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes.",
        "Path values must not use empty stand-ins such as None, N/A, TBD, or unknown.",
        "Path values must not contain embedded whitespace.",
        "Path values must not target VCS, dependency, or cache directories.",
        "Allowed files must not include workflow control files such as handoff docs, root task plans, gate utilities, or CI gates.",
        "Allowed and forbidden files must not contain overlapping scope entries within the same list.",
        "## Anti-Placeholder Scan",
        "Replace `BLOCKED_SCANNER_PATTERN` with the actual scanner expression before assigning the task.",
        "Anti-Placeholder scan command must start with `rg` or `rg.exe`.",
        "Anti-Placeholder scan command must include every configured scanner pattern.",
        "Anti-Placeholder scan command must use `--` before the path list.",
        "Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`.",
        "Anti-Placeholder scan command must mention every allowed file as a path token.",
        "## Stop Conditions",
        "Stop conditions must be unique and include at least three items.",
        "## Required Outbox",
        "concrete summary with at least two bullet items",
        "checked `- [x] ...` evidence items",
        "checked acceptance evidence must not say skipped, unverified, untested, pending, deferred, or not applicable",
        "Anti-Placeholder scan command and clean result",
        "Anti-Placeholder scan command must be exact and must not use shell control operators",
        "Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`",
        "Anti-Placeholder scan command must not include unresolved angle-bracket markers",
        "Anti-Placeholder clean result markers inside the backticked scan command text do not count as scan result evidence",
        "Anti-Placeholder clean result evidence must appear on the same line as the parseable scan command",
        "Anti-Placeholder evidence must not say skipped, not executed, not scanned, or no scan",
        "explicit `None` when no unresolved questions or blockers remain",
        READY_FOR_REVIEW,
    ),
    Path("docs/handoff/deepseek_task_spec_schema.md"): (
        "# DeepSeek Task Spec Schema",
        "python -m utils.prepare_deepseek_task --spec-file",
        "## Required Fields",
        "`message_id`",
        "`allowed_files`",
        "`requirements` entries must be unique and include at least 3 items.",
        "`acceptance_criteria` entries must be unique and include at least 3 items.",
        "`stop_conditions` entries must be unique and include at least 3 items.",
        "Spec values must not contain angle-bracket markers.",
        "`verification_commands`",
        "`input_contracts`",
        "`output_contracts`",
        "`input_contracts` and `output_contracts` entries cannot be empty stand-ins such as None, N/A, TBD, or unknown.",
        "Path values must not use wildcards or glob metacharacters.",
        "Path values must not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes.",
        "Path values must not use empty stand-ins such as None, N/A, TBD, or unknown.",
        "Path values must not contain embedded whitespace.",
        "Path values must not target VCS, dependency, or cache directories.",
        "`allowed_files` and `forbidden_files` must not contain overlapping scope entries within the same list.",
        "Verification commands must use standalone command tokens and no shell control operators.",
        "Verification commands must start with direct command families, not shell wrappers.",
        "Verification commands must not use shell redirection.",
        "Verification commands must not use command substitution such as `$(...)` or backticks.",
        "Verification commands must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Verification commands must not use response-file or splatting arguments such as `@args.txt`.",
        "Verification commands must not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.",
        "No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.",
        "Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.",
        "Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.",
        "Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.",
        "Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.",
        "Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.",
        "Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.",
        "Verification commands must mention each concrete allowed file as a path token.",
        "Git diff-check commands must mention every allowed file or directory scope as a path token.",
        "Git diff-check commands with pathspecs must use `--` before the path list.",
        "Generated assignments include a concrete Anti-Placeholder scan command over `allowed_files`.",
        "Generated Anti-Placeholder scan commands start with `rg`.",
        "Generated Anti-Placeholder scan commands include every configured scanner pattern.",
        "Generated Anti-Placeholder scan commands use `--` before the path list.",
        "Generated Anti-Placeholder scan commands do not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Generated Anti-Placeholder scan commands do not use response-file or splatting arguments such as `@args.txt`.",
        "`allowed_files` must not include workflow control files such as handoff docs, root task plans, gate utilities, or CI gates.",
        "Generated worktree baseline entries must not overlap `allowed_files`.",
        "## Optional Fields",
        "`required_reading`",
        "Generated assignments always include `AGENTS.md`, `spec.md`, `architecture.md`, `task.md`, and `docs/handoff/deepseek_inbox.md`.",
        "`stop_conditions`",
        "## Validation",
        "--dry-run",
        "--reset-outbox",
        "--validate-repository",
        "embedded Markdown backticks",
        "`required_reading` must not list mutable handoff control files",
    ),
    Path("docs/handoff/deepseek_assignment_examples.md"): (
        "# DeepSeek Assignment Examples",
        "## Preview First",
        "python -m utils.prepare_deepseek_task",
        "--dry-run",
        "## Write And Reset",
        "--reset-outbox",
        "--validate-repository",
        "## Spec File Variant",
        "--spec-file",
        "Extra required-reading entries must not list mutable handoff control files",
        "## Validate",
        "python -m utils.validate_handoff_docs --json",
        "python -m utils.dual_model_pipeline_check --json",
        "## Review",
        "python -m utils.codex_review_gate --json",
        "READY_FOR_CODEX_REVIEW",
    ),
    Path("docs/handoff/codex_review_template.md"): (
        "# Codex Review Record",
        "Status:",
        "Reviewed Message ID:",
        "Reviewed Task:",
        "## Blocking Issues",
        "## Acceptance Criteria Verification",
        "## Verification Performed by Codex",
        "## Anti-Placeholder Scan",
        "## Scope Check",
        "## Decision",
    ),
}

SHORTCUT_TARGETS: dict[Path, str] = {
    Path("DEEPSEEK_INBOX.md"): "docs/handoff/deepseek_inbox.md",
    Path("CODEX_REVIEW.md"): "docs/handoff/codex_review_checklist.md",
}

HANDOFF_CONTROL_FILE_PATHS = frozenset(
    {
        INBOX_PATH.as_posix(),
        OUTBOX_PATH.as_posix(),
        "CODEX_REVIEW.md",
        "DEEPSEEK_INBOX.md",
    }
)
HANDOFF_CONTROL_CHANGED_FILE_PATHS = HANDOFF_CONTROL_FILE_PATHS
REQUIRED_READING_CONTROL_FILE_PATHS = HANDOFF_CONTROL_FILE_PATHS - {INBOX_PATH.as_posix()}
READY_INBOX_CORE_REQUIRED_READING_PATHS: tuple[str, ...] = (
    "AGENTS.md",
    "spec.md",
    "architecture.md",
    "task.md",
    INBOX_PATH.as_posix(),
)
ASSIGNMENT_CONTROL_FILE_PATHS = frozenset(
    {
        *HANDOFF_CONTROL_FILE_PATHS,
        "AGENTS.md",
        "CLAUDE.md",
        "architecture.md",
        "decisions.md",
        "progress.md",
        "spec.md",
        "task.md",
        "test_plan.md",
        ".github/workflows/dual-model-gates.yml",
        "docs/handoff/codex_review_checklist.md",
        "docs/handoff/codex_review_template.md",
        "docs/handoff/deepseek_assignment_examples.md",
        "docs/handoff/deepseek_task_spec_schema.md",
        "docs/handoff/deepseek_task_template.md",
        "docs/handoff/dual_model_development_workflow.md",
        "utils/codex_review_gate.py",
        "utils/dual_model_pipeline_check.py",
        "utils/prepare_deepseek_task.py",
        "utils/validate_handoff_docs.py",
    }
)
BANNED_PATH_GLOB_CHARACTERS = frozenset("*?[]{}")
BANNED_PATH_SHELL_CHARACTERS = frozenset("#&;|<>\"'$")
RESERVED_PATH_SCOPE_SEGMENTS = frozenset(
    {
        ".cache",
        ".git",
        ".hg",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".tox",
        ".venv",
        "__pycache__",
        "node_modules",
        "site-packages",
        "venv",
    }
)
BROAD_ALLOWED_DIRECTORY_SCOPES = frozenset(
    {
        ".github",
        "dayu",
        "docs",
        "src",
        "tests",
        "utils",
        "workspace",
    }
)

READY_OUTBOX_SECTIONS: tuple[str, ...] = (
    "## Summary",
    "## Changed Files",
    "## Verification Commands and Results",
    "## Acceptance Criteria",
    "## Scope Deviations",
    "## Anti-Placeholder Scan",
)

READY_INBOX_SECTIONS: tuple[str, ...] = (
    "## Objective",
    "## Required Reading",
    "## Input Contracts",
    "## Output Contracts",
    "## Allowed Files",
    "## Forbidden Files",
    "## Worktree Baseline",
    "## Requirements",
    "## Acceptance Criteria",
    "## Verification Commands",
    "## Anti-Placeholder Scan",
    "## Stop Conditions",
    "## Required Outbox",
    "## Required Outbox Evidence",
)

READY_INBOX_REQUIRED_OUTBOX_EVIDENCE: tuple[str, ...] = (
    "concrete summary",
    "changed files",
    "changed-file evidence must not list workflow control files",
    "verification commands",
    "clean result markers inside the backticked command text",
    "verification evidence must not say dry-run",
    "checked acceptance",
    "Anti-Placeholder scan",
    "scope deviations",
    "unresolved questions or blockers",
)

REQUIRED_VERIFICATION_COMMANDS: tuple[str, ...] = (
    "pytest",
    "ruff",
    "git diff --check",
)
PYTHON_MODULE_RUNNER_PATTERN = r"(?:py(?:\.exe)?|python(?:\d+(?:\.\d+)?)?(?:\.exe)?)\s+-m\s+"
SHELL_CONTROL_OPERATORS: tuple[str, ...] = ("&&", "||", ";", "|", "#", ">", "<", "$(", "`")
SHELL_VARIABLE_EXPANSION_PATTERN = re.compile(
    r"(\$env:[A-Za-z_][A-Za-z0-9_]*|\$\{[^}\s]+}|\$[A-Za-z_][A-Za-z0-9_]*|(?<!%)%[A-Za-z_][A-Za-z0-9_]*%(?!%))"
)
RESPONSE_FILE_ARGUMENT_PATTERN = re.compile(r"(?<!\S)(?:['\"])?@[^\s`'\"]+")
UNSAFE_VERIFICATION_FLAGS: tuple[str, ...] = (
    "--collect-only",
    "--continue-on-collection-errors",
    "--co",
    "--confcutdir",
    "--config",
    "--fixtures",
    "--fixtures-per-test",
    "--funcargs",
    "--markers",
    "--setup-only",
    "--setup-plan",
    "--deselect",
    "--exit-zero",
    "--exitfirst",
    "--exclude",
    "--extend-exclude",
    "--extend-ignore",
    "--extend-select",
    "--failed-first",
    "--fix",
    "--fix-only",
    "--add-noqa",
    "--force-exclude",
    "--help",
    "--ignore",
    "--ignore-glob",
    "--import-mode",
    "--isolated",
    "--last-failed",
    "--lf",
    "--lint.extend-ignore",
    "--lint.extend-per-file-ignores",
    "--lint.extend-select",
    "--lint.ignore",
    "--lint.per-file-ignores",
    "--lint.select",
    "--maxfail",
    "--ff",
    "--override-ini",
    "--per-file-ignores",
    "--pyargs",
    "--rootdir",
    "--select",
    "--show-files",
    "--show-settings",
    "--stepwise",
    "--stepwise-skip",
    "--sw",
    "--sw-skip",
    "--unsafe-fixes",
    "--version",
    "-h",
    "-V",
    "-c",
    "-k",
    "-m",
    "-o",
    "-x",
)
UNSAFE_VERIFICATION_FLAG_PREFIXES: tuple[str, ...] = (
    "--confcutdir=",
    "--deselect=",
    "--config=",
    "--exclude=",
    "--extend-exclude=",
    "--extend-ignore=",
    "--extend-select=",
    "--ignore=",
    "--ignore-glob=",
    "--import-mode=",
    "--lint.extend-ignore=",
    "--lint.extend-per-file-ignores=",
    "--lint.extend-select=",
    "--lint.ignore=",
    "--lint.per-file-ignores=",
    "--lint.select=",
    "--maxfail=",
    "--override-ini=",
    "--per-file-ignores=",
    "--rootdir=",
    "--select=",
    "-k=",
    "-m=",
    "-o=",
)
UNSAFE_VERIFICATION_ATTACHED_SHORT_FLAG_PREFIXES: tuple[str, ...] = ("-k", "-m", "-o")
ANTI_PLACEHOLDER_SCANNER_PATTERNS: tuple[str, ...] = (
    r"\b[Tt][Oo][Dd][Oo]\b",
    r"\b[Ff][Ii][Xx][Mm][Ee]\b",
    r"\b[Pp][Aa][Ss][Ss]\b",
    r"\b[Nn][Oo][Tt][Ii][Mm][Pp][Ll][Ee][Mm][Ee][Nn][Tt][Ee][Dd]\b",
    r"\b[Mm][Oo][Cc][Kk]\b",
    r"\b[Pp][Ll][Aa][Cc][Ee][Hh][Oo][Ll][Dd][Ee][Rr]\b",
    r"\b[Ff][Aa][Kk][Ee]\b",
    r"\b[Dd][Uu][Mm][Mm][Yy]\b",
)
INBOX_SCAN_TEMPLATE_MARKERS: tuple[str, ...] = (
    "BLOCKED_SCANNER_PATTERN",
)
GENERIC_ACCEPTANCE_SUMMARIES: tuple[str, ...] = (
    "all criteria verified",
    "all criteria are verified",
    "all requirements verified",
)
GENERIC_SUMMARY_ITEMS: tuple[str, ...] = (
    "all done",
    "changed",
    "changes",
    "complete",
    "completed",
    "done",
    "finished",
    "fixed",
    "implemented",
    "see changed files",
    "task complete",
    "task completed",
    "updated",
)
ACCEPTANCE_FAILURE_EVIDENCE: tuple[str, ...] = (
    "not implemented",
    "not done",
    "not verified",
    "not covered",
    "not executed",
    "unverified",
    "untested",
    "pending",
    "deferred",
    "not applicable",
    "n/a",
    "incomplete",
    "missing",
    "omitted",
    "skipped",
    "skip",
    "unable to verify",
)
NO_BLOCKER_VALUES: tuple[str, ...] = (
    "none",
    "not applicable",
    "n/a",
    "no blockers",
    "no unresolved blockers",
    "no unresolved questions",
)
NO_CHANGED_FILE_VALUES: tuple[str, ...] = (
    "none",
    "no changes",
    "not applicable",
)
NO_SCAN_EVIDENCE_VALUES: tuple[str, ...] = (
    "none",
    "not applicable",
    "n/a",
    "no scan",
)
NO_SCOPE_DEVIATION_VALUES: tuple[str, ...] = (
    "none",
    "not applicable",
    "n/a",
    "no deviations",
    "no scope deviations",
)
NO_WORKTREE_BASELINE_VALUES: tuple[str, ...] = (
    "none",
    "not applicable",
    "n/a",
    "clean",
    "empty",
)
CONTRACT_STAND_IN_VALUES: tuple[str, ...] = (
    "none",
    "not applicable",
    "n/a",
    "tbd",
    "to be determined",
    "unknown",
    "pending",
)
PATH_STAND_IN_VALUES: tuple[str, ...] = (
    "none",
    "not applicable",
    "n/a",
    "tbd",
    "to be determined",
    "unknown",
    "pending",
    "no file",
    "no files",
    "no path",
    "no paths",
)
SCAN_COMMAND_EVIDENCE: tuple[str, ...] = (
    "rg",
    "select-string",
    "grep",
    "blocked terms",
)
SCAN_RESULT_EVIDENCE: tuple[str, ...] = (
    "no matches",
    "no_matches",
    "returned no matches",
)
SCAN_FAILURE_EVIDENCE: tuple[str, ...] = (
    "cancelled",
    "canceled",
    "error",
    "errored",
    "interrupted",
    "not executed",
    "not scanned",
    "not_scan",
    "not_run",
    "scan unavailable",
    "scanner unavailable",
    "skipped",
    "skip",
    "timed out",
    "timeout",
    "failed",
    "failure",
    "unsuccessful",
)
VERIFICATION_RESULT_EVIDENCE: tuple[str, ...] = (
    "exited 0",
    "exit 0",
    "-> ok",
    "succeeded",
)
VERIFICATION_FAILURE_EVIDENCE: tuple[str, ...] = (
    "all deselected",
    "assumed exit 0",
    "assumed exited 0",
    "assumed success",
    "assumed successful",
    "cache result",
    "cached result",
    "exited 1",
    "exit 1",
    "cancelled",
    "canceled",
    "collected 0",
    "access denied",
    "cannot import",
    "command not found",
    "could not import",
    "dependency missing",
    "deselected",
    "different cwd",
    "different env",
    "different environment",
    "different interpreter",
    "different python executable",
    "different working directory",
    "dry run",
    "dry-run",
    "empty test suite",
    "estimated result",
    "error",
    "errored",
    "expected failure",
    "expected to exit 0",
    "expected to succeed",
    "fabricated result",
    "interrupted",
    "invented result",
    "likely exit 0",
    "likely succeeded",
    "manual only",
    "manual verification",
    "manual-only",
    "manually verified",
    "missing dependency",
    "missing package",
    "module not found",
    "nonzero",
    "no module named",
    "no such file or directory",
    "no test ran",
    "no tests collected",
    "no tests ran",
    "failed",
    "failure",
    "from cache",
    "from earlier run",
    "from previous run",
    "not successful",
    "not succeeded",
    "not full suite",
    "not actually executed",
    "not actually run",
    "not executed",
    "not re-run",
    "not rerun",
    "not from repo root",
    "not from repository root",
    "not project env",
    "not project environment",
    "not project venv",
    "not recognized as",
    "old result",
    "outside project env",
    "outside project environment",
    "outside project venv",
    "outside repo root",
    "outside repository root",
    "package missing",
    "partial run",
    "partial result",
    "partial verification",
    "permission denied",
    "planned result",
    "previous result",
    "previous run",
    "prior result",
    "prior run",
    "reused result",
    "sample only",
    "sample-only",
    "simulated result",
    "simulated run",
    "skipped",
    "skip",
    "smoke only",
    "smoke-only",
    "subset only",
    "subset run",
    "stale result",
    "synthetic result",
    "timed out",
    "timeout",
    "unexpectedly passed",
    "unsuccessful",
    "unable to import",
    "used system python",
    "using system python",
    "without pythonpath",
    "would exit 0",
    "would succeed",
    "wrong cwd",
    "wrong env",
    "wrong environment",
    "wrong interpreter",
    "wrong python executable",
    "wrong working directory",
    "should exit 0",
    "should succeed",
    "warning-only",
    "warnings only",
    "warnings-only",
    "only warnings",
    "xfail",
    "xfailed",
    "xpass",
    "xpassed",
)


def validate_handoff_docs(root: Path) -> list[str]:
    """Return validation issues for the handoff document set under ``root``."""

    issues: list[str] = []
    texts: dict[Path, str] = {}

    for relative_path in REQUIRED_FILES:
        path = root / relative_path
        if not path.is_file():
            issues.append(f"missing required file: {relative_path.as_posix()}")
            continue
        texts[relative_path] = path.read_text(encoding="utf-8")

    for relative_path, snippets in REQUIRED_SNIPPETS.items():
        text = texts.get(relative_path)
        if text is None:
            continue
        for snippet in snippets:
            if snippet not in text:
                issues.append(f"{relative_path.as_posix()} is missing required text: {snippet}")
        headings = tuple(snippet for snippet in snippets if snippet.startswith("## "))
        if headings:
            issues.extend(_validate_section_uniqueness(relative_path=relative_path, text=text, headings=headings))

    for relative_path, target in SHORTCUT_TARGETS.items():
        text = texts.get(relative_path)
        if text is not None and target not in text:
            issues.append(f"{relative_path.as_posix()} must point to {target}")

    inbox = texts.get(INBOX_PATH)
    if inbox is not None:
        issues.extend(
            _validate_metadata_uniqueness(
                relative_path=INBOX_PATH,
                text=inbox,
                fields=("Status", "Message ID", "Task", "CODEX_GATE"),
            )
        )
    if inbox is not None and _is_ready_for_deepseek(inbox):
        issues.extend(_validate_ready_inbox(inbox, root=root))

    outbox = texts.get(OUTBOX_PATH)
    if outbox is not None:
        issues.extend(
            _validate_metadata_uniqueness(
                relative_path=OUTBOX_PATH,
                text=outbox,
                fields=("Status", "Message ID", "Task"),
            )
        )
    if outbox is not None and _is_ready_for_review(outbox):
        issues.extend(_validate_ready_outbox(outbox, root=root))
    if inbox is not None and outbox is not None:
        issues.extend(_validate_handoff_state(inbox_text=inbox, outbox_text=outbox))
        issues.extend(_validate_ready_outbox_changed_files_against_inbox_scope(inbox_text=inbox, outbox_text=outbox))
        issues.extend(_validate_ready_outbox_verification_against_inbox(inbox_text=inbox, outbox_text=outbox))
        issues.extend(_validate_ready_outbox_acceptance_against_inbox(inbox_text=inbox, outbox_text=outbox))

    return issues


def to_jsonable_report(issues: Sequence[str]) -> dict[str, object]:
    """Return a JSON-serializable handoff validation report."""

    return {
        "ok": not issues,
        "issues": list(issues),
    }


def _is_ready_for_review(text: str) -> bool:
    """Return whether the DeepSeek outbox is claiming Codex review readiness."""

    return _extract_metadata(text).get("Status") == READY_FOR_REVIEW


def _is_ready_for_deepseek(text: str) -> bool:
    """Return whether the DeepSeek inbox is claiming task readiness."""

    return _extract_metadata(text).get("Status") == READY_FOR_DEEPSEEK


def _validate_ready_outbox(text: str, *, root: Path | None = None) -> list[str]:
    """Validate stricter evidence requirements for a ready-for-review outbox."""

    issues: list[str] = []
    metadata = _extract_metadata(text)
    for field in ("Message ID", "Task"):
        value = metadata.get(field, "")
        if not value or value == "unassigned" or value.startswith("<"):
            issues.append(f"{OUTBOX_PATH.as_posix()} ready outbox must set a concrete {field}")

    for heading in READY_OUTBOX_SECTIONS:
        body = _section_body(text, heading)
        if not body:
            issues.append(f"docs/handoff/deepseek_outbox.md has empty ready section: {heading}")
            continue
        if NOT_RUN.lower() in body.lower():
            issues.append(f"docs/handoff/deepseek_outbox.md ready section cannot contain '{NOT_RUN}': {heading}")

    changed_files = _section_body(text, "## Changed Files")
    issues.extend(_validate_ready_outbox_summary(_section_body(text, "## Summary")))
    issues.extend(_validate_ready_outbox_changed_file_paths(changed_files, root=root))

    verification_body = _section_body(text, "## Verification Commands and Results")
    verification_lines = _normalized_section_lines(verification_body)
    verification_results = _extract_outbox_verification_results(verification_body)
    if verification_lines and not verification_results:
        issues.append(f"{OUTBOX_PATH.as_posix()} ready outbox verification must list parseable command result lines")
    usable_verification_results: list[tuple[str, str]] = []
    for result_command, line in verification_results:
        if _has_shell_control_operator(result_command):
            issues.append(
                f"{OUTBOX_PATH.as_posix()} ready outbox verification command must not include "
                f"shell control operators: {result_command}"
            )
            continue
        if _has_response_file_argument(result_command):
            issues.append(
                f"{OUTBOX_PATH.as_posix()} ready outbox verification command must not include "
                f"response-file arguments: {result_command}"
            )
            continue
        if _has_unsafe_verification_flag(result_command):
            issues.append(
                f"{OUTBOX_PATH.as_posix()} ready outbox verification command must not include "
                f"unsafe verification flags: {result_command}"
            )
            continue
        if _has_wrapped_required_verification_command(result_command):
            issues.append(
                f"{OUTBOX_PATH.as_posix()} ready outbox verification command must start with a direct "
                f"pytest, ruff, or git diff --check command, not a shell wrapper: {result_command}"
            )
            continue
        if _git_diff_check_uses_paths_without_delimiter(result_command):
            issues.append(
                f"{OUTBOX_PATH.as_posix()} ready outbox git diff --check command must use -- before pathspecs: "
                f"{result_command}"
            )
            continue
        usable_verification_results.append((result_command, line))
    issues.extend(
        _validate_ready_outbox_pytest_covers_changed_test_files(
            changed_files_body=changed_files,
            verification_results=usable_verification_results,
        )
    )
    issues.extend(
        _validate_ready_outbox_ruff_covers_changed_python_files(
            changed_files_body=changed_files,
            verification_results=usable_verification_results,
        )
    )
    issues.extend(
        _validate_ready_outbox_diff_check_covers_changed_files(
            changed_files_body=changed_files,
            verification_results=usable_verification_results,
        )
    )
    for required_command in REQUIRED_VERIFICATION_COMMANDS:
        matching_lines = [
            line
            for result_command, line in usable_verification_results
            if _matches_required_verification_command(result_command, required_command)
        ]
        if not matching_lines:
            issues.append(f"docs/handoff/deepseek_outbox.md ready outbox verification must include: {required_command}")
            continue
        if not any(_has_clean_verification_result(line) for line in matching_lines):
            issues.append(
                f"docs/handoff/deepseek_outbox.md ready outbox verification result must be clean for: "
                f"{required_command}"
            )

    acceptance_body = _section_body(text, "## Acceptance Criteria")
    checked_acceptance_items = _checked_acceptance_items(acceptance_body)
    if not checked_acceptance_items:
        issues.append("docs/handoff/deepseek_outbox.md ready outbox acceptance criteria must include checked evidence items")
    for item in checked_acceptance_items:
        item_text = _checked_acceptance_text(item)
        if _has_negative_acceptance_evidence(item_text):
            issues.append(
                "docs/handoff/deepseek_outbox.md ready outbox checked acceptance evidence is negative: "
                f"{item_text}"
            )
    acceptance_lower = acceptance_body.lower()
    for summary in GENERIC_ACCEPTANCE_SUMMARIES:
        if summary in acceptance_lower:
            issues.append("docs/handoff/deepseek_outbox.md ready outbox acceptance criteria must not use a generic summary")
            break

    scope_deviation_lines = _normalized_section_lines(_section_body(text, "## Scope Deviations"))
    deviation_lines = [
        line
        for line in scope_deviation_lines
        if _normalize_evidence_line(line) not in NO_SCOPE_DEVIATION_VALUES
    ]
    for line in deviation_lines:
        issues.append(f"docs/handoff/deepseek_outbox.md ready outbox lists scope deviation: {line}")

    blocker_lines = _normalized_section_lines(_section_body(text, "## Unresolved Questions or Blockers"))
    if not blocker_lines:
        issues.append("docs/handoff/deepseek_outbox.md ready outbox must explicitly state unresolved questions or blockers")
    unresolved_lines = [line for line in blocker_lines if _normalize_evidence_line(line) not in NO_BLOCKER_VALUES]
    for line in unresolved_lines:
        issues.append(f"docs/handoff/deepseek_outbox.md ready outbox lists unresolved blocker: {line}")

    scan_body = _section_body(text, "## Anti-Placeholder Scan")
    scan_lines = _normalized_section_lines(scan_body)
    scan_line_values = {_normalize_evidence_line(line) for line in scan_lines}
    if any(value in NO_SCAN_EVIDENCE_VALUES for value in scan_line_values):
        issues.append("docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must not use empty evidence")
    scan_lower = scan_body.lower()
    scan_result_evidence = _evidence_text_outside_backticks(scan_body)
    if any(marker in scan_result_evidence for marker in SCAN_FAILURE_EVIDENCE):
        issues.append("docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must not use failing evidence")
    if not any(marker in scan_lower for marker in SCAN_COMMAND_EVIDENCE):
        issues.append("docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must include command evidence")
    if not any(marker in scan_result_evidence for marker in SCAN_RESULT_EVIDENCE):
        issues.append("docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must include clean result evidence")
    if not _has_clean_scan_command_line(scan_body):
        issues.append(
            "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan clean result "
            "must appear on a parseable scan command line"
        )
    scan_commands = _extract_scan_commands(scan_body)
    for scan_command in scan_commands:
        if _has_shell_control_operator(scan_command):
            issues.append(
                "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan command "
                f"must not include shell control operators: {scan_command}"
            )
        if _has_response_file_argument(scan_command):
            issues.append(
                "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan command "
                f"must not include response-file arguments: {scan_command}"
            )
        if not _is_rg_scan_command(scan_command):
            issues.append(
                "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan command "
                f"must start with rg or rg.exe: {scan_command}"
            )
        if _rg_scan_command_missing_path_delimiter(scan_command):
            issues.append(
                "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan command "
                f"must use -- before the path list: {scan_command}"
            )
        missing_patterns = _missing_anti_placeholder_patterns(scan_command)
        if missing_patterns:
            issues.append(
                "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan command "
                f"must include all configured scanner patterns; missing: {', '.join(missing_patterns)}"
            )
        if _has_unresolved_angle_marker(scan_command):
            issues.append(
                "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan command "
                f"must not include unresolved angle-bracket markers: {scan_command}"
            )
    issues.extend(
        _validate_ready_outbox_scan_covers_changed_files(
            changed_files_body=changed_files,
            scan_body=scan_body,
        )
    )

    return issues


def _validate_ready_inbox(text: str, *, root: Path | None = None) -> list[str]:
    """Validate stricter task-quality requirements for an assigned DeepSeek inbox."""

    issues: list[str] = []
    metadata = _extract_metadata(text)

    if metadata.get("Status") != READY_FOR_DEEPSEEK:
        issues.append(f"{INBOX_PATH.as_posix()} ready inbox must set Status: {READY_FOR_DEEPSEEK}")
    if metadata.get("CODEX_GATE") != "PASS":
        issues.append(f"{INBOX_PATH.as_posix()} ready inbox must set CODEX_GATE: PASS")
    for field in ("Message ID", "Task"):
        value = metadata.get(field, "")
        if not value or value == "unassigned" or value.startswith("<"):
            issues.append(f"{INBOX_PATH.as_posix()} ready inbox must set a concrete {field}")

    for heading in READY_INBOX_SECTIONS:
        body = _section_body(text, heading)
        if not body:
            issues.append(f"{INBOX_PATH.as_posix()} ready inbox has empty section: {heading}")
        if _has_unresolved_angle_marker(body):
            issues.append(f"{INBOX_PATH.as_posix()} ready inbox has unresolved angle-bracket marker in section: {heading}")

    issues.extend(
        _validate_required_reading_section_paths(
            text=text,
            heading="## Required Reading Before Editing",
            label="required reading before editing",
            root=root,
        )
    )
    issues.extend(
        _validate_required_reading_section_paths(
            text=text,
            heading="## Required Reading",
            label="required reading",
            root=root,
        )
    )
    before_editing_paths = _normalized_required_reading_paths(text, "## Required Reading Before Editing")
    required_reading_paths = _normalized_required_reading_paths(text, "## Required Reading")
    if before_editing_paths and required_reading_paths and before_editing_paths != required_reading_paths:
        issues.append(f"{INBOX_PATH.as_posix()} ready inbox required-reading sections must match")
    issues.extend(
        _validate_required_reading_core_paths(
            paths=before_editing_paths,
            label="required reading before editing",
        )
    )
    issues.extend(
        _validate_required_reading_core_paths(
            paths=required_reading_paths,
            label="required reading",
        )
    )
    issues.extend(_validate_contract_section(text=text, heading="## Input Contracts", label="input contract"))
    issues.extend(_validate_contract_section(text=text, heading="## Output Contracts", label="output contract"))

    allowed_files = _raw_path_section_items(_section_body(text, "## Allowed Files"))
    if not allowed_files:
        issues.append(f"{INBOX_PATH.as_posix()} ready inbox must list allowed files")
    if len(allowed_files) > 5:
        issues.append(f"{INBOX_PATH.as_posix()} ready inbox must limit allowed files to 5 or fewer")

    forbidden_files = _raw_path_section_items(_section_body(text, "## Forbidden Files"))
    if not forbidden_files:
        issues.append(f"{INBOX_PATH.as_posix()} ready inbox must list forbidden files")
    issues.extend(_validate_scope_paths(allowed_files=allowed_files, forbidden_files=forbidden_files))

    baseline_body = _section_body(text, "## Worktree Baseline")
    issues.extend(_validate_worktree_baseline_paths(baseline_body, allowed_files=allowed_files))

    requirements_body = _section_body(text, "## Requirements")
    requirement_items = _numbered_section_items(requirements_body)
    if len(requirement_items) < 3:
        issues.append(f"{INBOX_PATH.as_posix()} ready inbox must include at least 3 numbered requirements")
    seen_requirements: set[str] = set()
    for item in requirement_items:
        normalized_item = " ".join(item.casefold().split())
        if normalized_item in seen_requirements:
            issues.append(f"{INBOX_PATH.as_posix()} ready inbox requirement is duplicated: {item}")
        seen_requirements.add(normalized_item)

    acceptance_body = _section_body(text, "## Acceptance Criteria")
    unchecked_acceptance_items = _unchecked_acceptance_items(acceptance_body)
    if len(unchecked_acceptance_items) < 3:
        issues.append(f"{INBOX_PATH.as_posix()} ready inbox must include at least 3 unchecked acceptance items")
    seen_acceptance_items: set[str] = set()
    for item in unchecked_acceptance_items:
        normalized_item = " ".join(item.lower().split())
        if normalized_item in seen_acceptance_items:
            issues.append(f"{INBOX_PATH.as_posix()} ready inbox acceptance criterion is duplicated: {item}")
        seen_acceptance_items.add(normalized_item)

    stop_condition_body = _section_body(text, "## Stop Conditions")
    stop_condition_items = _section_items(stop_condition_body)
    if len(stop_condition_items) < 3:
        issues.append(f"{INBOX_PATH.as_posix()} ready inbox must include at least 3 stop conditions")
    seen_stop_conditions: set[str] = set()
    for item in stop_condition_items:
        normalized_item = " ".join(item.casefold().split())
        if normalized_item in seen_stop_conditions:
            issues.append(f"{INBOX_PATH.as_posix()} ready inbox stop condition is duplicated: {item}")
        seen_stop_conditions.add(normalized_item)

    verification_body = _section_body(text, "## Verification Commands")
    verification_commands = _extract_verification_commands(verification_body)
    if not verification_commands:
        issues.append(
            f"{INBOX_PATH.as_posix()} ready inbox verification must list parseable commands "
            "in a fenced block or backticked bullet list"
        )
    usable_verification_commands: list[str] = []
    seen_verification_commands: set[str] = set()
    for command in verification_commands:
        if _has_shell_control_operator(command):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox verification command must not include "
                f"shell control operators: {command}"
            )
            continue
        if _has_response_file_argument(command):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox verification command must not include "
                f"response-file arguments: {command}"
            )
            continue
        if _has_unsafe_verification_flag(command):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox verification command must not include "
                f"unsafe verification flags: {command}"
            )
            continue
        if _has_wrapped_required_verification_command(command):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox verification command must start with a direct "
                f"pytest, ruff, or git diff --check command, not a shell wrapper: {command}"
            )
            continue
        if _git_diff_check_uses_paths_without_delimiter(command):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox git diff --check command must use -- before pathspecs: "
                f"{command}"
            )
            continue
        if command in seen_verification_commands:
            issues.append(f"{INBOX_PATH.as_posix()} ready inbox verification command is duplicated: {command}")
            continue
        seen_verification_commands.add(command)
        usable_verification_commands.append(command)
    for required_command in REQUIRED_VERIFICATION_COMMANDS:
        if not any(
            _matches_required_verification_command(command, required_command)
            for command in usable_verification_commands
        ):
            issues.append(f"{INBOX_PATH.as_posix()} ready inbox verification must include: {required_command}")
    issues.extend(
        _validate_ready_inbox_verification_covers_allowed_files(
            allowed_files_body=_section_body(text, "## Allowed Files"),
            verification_commands=usable_verification_commands,
        )
    )
    issues.extend(
        _validate_ready_inbox_scan_covers_allowed_files(
            allowed_files_body=_section_body(text, "## Allowed Files"),
            scan_body=_section_body(text, "## Anti-Placeholder Scan"),
        )
    )

    required_outbox_body = _section_body(text, "## Required Outbox")
    if READY_FOR_REVIEW not in required_outbox_body:
        issues.append(f"{INBOX_PATH.as_posix()} ready inbox required outbox must mention {READY_FOR_REVIEW}")
    required_outbox_evidence_body = _section_body(text, "## Required Outbox Evidence")
    required_outbox_evidence_items = _section_items(required_outbox_evidence_body)
    if len(required_outbox_evidence_items) < len(READY_INBOX_REQUIRED_OUTBOX_EVIDENCE):
        issues.append(
            f"{INBOX_PATH.as_posix()} ready inbox required outbox evidence must include at least "
            f"{len(READY_INBOX_REQUIRED_OUTBOX_EVIDENCE)} bullet items"
        )
    seen_required_outbox_evidence: set[str] = set()
    for item in required_outbox_evidence_items:
        normalized_item = " ".join(item.casefold().split())
        if normalized_item in seen_required_outbox_evidence:
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox required outbox evidence is duplicated: {item}"
            )
        seen_required_outbox_evidence.add(normalized_item)
    normalized_required_outbox_evidence = required_outbox_evidence_body.casefold()
    for required_evidence in READY_INBOX_REQUIRED_OUTBOX_EVIDENCE:
        if required_evidence.casefold() not in normalized_required_outbox_evidence:
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox required outbox evidence must mention: {required_evidence}"
            )

    return issues


def _validate_handoff_state(*, inbox_text: str, outbox_text: str) -> list[str]:
    """Validate the high-level lifecycle state across inbox and outbox."""

    issues: list[str] = []
    inbox_metadata = _extract_metadata(inbox_text)
    outbox_metadata = _extract_metadata(outbox_text)
    inbox_status = inbox_metadata.get("Status")
    outbox_status = outbox_metadata.get("Status")

    if inbox_status == WAITING_FOR_TASK:
        if outbox_status != WAITING_FOR_TASK:
            issues.append(f"{INBOX_PATH.as_posix()} waiting state requires {OUTBOX_PATH.as_posix()} Status: {WAITING_FOR_TASK}")
        return issues

    if inbox_status == READY_FOR_DEEPSEEK:
        if outbox_status not in {WAITING_FOR_DEEPSEEK, READY_FOR_REVIEW}:
            issues.append(
                f"{INBOX_PATH.as_posix()} ready task requires {OUTBOX_PATH.as_posix()} Status: "
                f"{WAITING_FOR_DEEPSEEK} or {READY_FOR_REVIEW}"
            )
            return issues
        for field in ("Message ID", "Task"):
            inbox_value = inbox_metadata.get(field)
            outbox_value = outbox_metadata.get(field)
            if inbox_value and outbox_value and inbox_value != outbox_value:
                issues.append(f"handoff {field} mismatch: inbox={inbox_value} outbox={outbox_value}")
        return issues

    if inbox_status:
        issues.append(f"{INBOX_PATH.as_posix()} has unknown Status: {inbox_status}")
    if outbox_status not in {WAITING_FOR_TASK, WAITING_FOR_DEEPSEEK, READY_FOR_REVIEW}:
        issues.append(f"{OUTBOX_PATH.as_posix()} has unknown Status: {outbox_status}")
    return issues


def _extract_metadata(text: str) -> dict[str, str]:
    """Extract top-level handoff metadata fields from markdown text."""

    metadata: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip()
        if normalized_key not in metadata:
            metadata[normalized_key] = value.strip()
    return metadata


def _validate_metadata_uniqueness(*, relative_path: Path, text: str, fields: Sequence[str]) -> list[str]:
    """Validate that top-level metadata fields are not duplicated."""

    issues: list[str] = []
    seen: set[str] = set()
    allowed_fields = set(fields)

    for line in text.splitlines():
        if line.startswith("## "):
            break
        if ":" not in line:
            continue
        key = line.split(":", 1)[0].strip()
        if key not in allowed_fields:
            continue
        if key in seen:
            issues.append(f"{relative_path.as_posix()} has duplicate metadata field: {key}")
        seen.add(key)

    return issues


def _validate_section_uniqueness(*, relative_path: Path, text: str, headings: Sequence[str]) -> list[str]:
    issues: list[str] = []
    counts = dict.fromkeys(headings, 0)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in counts:
            counts[stripped] += 1

    for heading, count in counts.items():
        if count > 1:
            issues.append(f"{relative_path.as_posix()} has duplicate section heading: {heading}")

    return issues


def _validate_ready_outbox_acceptance_against_inbox(*, inbox_text: str, outbox_text: str) -> list[str]:
    """Validate ready outbox acceptance evidence against the assigned inbox criteria."""

    if not _is_ready_for_deepseek(inbox_text) or not _is_ready_for_review(outbox_text):
        return []

    inbox_criteria = _unchecked_acceptance_items(_section_body(inbox_text, "## Acceptance Criteria"))
    checked_items = [
        _checked_acceptance_text(item)
        for item in _checked_acceptance_items(_section_body(outbox_text, "## Acceptance Criteria"))
    ]
    issues: list[str] = []
    for criterion in inbox_criteria:
        if not any(_acceptance_item_covers_criterion(item=item, criterion=criterion) for item in checked_items):
            issues.append(
                f"{OUTBOX_PATH.as_posix()} missing checked acceptance evidence for assigned criterion: {criterion}"
            )
    return issues


def _validate_ready_outbox_changed_files_against_inbox_scope(*, inbox_text: str, outbox_text: str) -> list[str]:
    """Validate ready outbox changed files against the assigned inbox scope."""

    if not _is_ready_for_deepseek(inbox_text) or not _is_ready_for_review(outbox_text):
        return []

    allowed_paths = tuple(
        _normalize_scope_path(path)
        for path in _section_items(_section_body(inbox_text, "## Allowed Files"))
    )
    forbidden_paths = tuple(
        _normalize_scope_path(path)
        for path in _section_items(_section_body(inbox_text, "## Forbidden Files"))
    )
    changed_paths = tuple(
        _normalize_scope_path(path)
        for path in _section_items(_section_body(outbox_text, "## Changed Files"))
    )

    issues: list[str] = []
    for changed_path in changed_paths:
        if not changed_path:
            continue
        if allowed_paths and not any(_scope_contains_path(scope=allowed_path, path=changed_path) for allowed_path in allowed_paths):
            issues.append(f"{OUTBOX_PATH.as_posix()} changed file is outside assigned allowed scope: {changed_path}")
        if any(_scope_contains_path(scope=forbidden_path, path=changed_path) for forbidden_path in forbidden_paths):
            issues.append(f"{OUTBOX_PATH.as_posix()} changed file touches assigned forbidden scope: {changed_path}")
    return issues


def _validate_ready_outbox_verification_against_inbox(*, inbox_text: str, outbox_text: str) -> list[str]:
    """Validate ready outbox command results against the exact assigned inbox commands."""

    if not _is_ready_for_deepseek(inbox_text) or not _is_ready_for_review(outbox_text):
        return []

    assigned_commands = _extract_verification_commands(_section_body(inbox_text, "## Verification Commands"))
    outbox_results = _extract_outbox_verification_results(_section_body(outbox_text, "## Verification Commands and Results"))
    issues: list[str] = []
    for command in assigned_commands:
        matching_lines = [line for result_command, line in outbox_results if result_command == command]
        if not matching_lines:
            issues.append(f"{OUTBOX_PATH.as_posix()} missing assigned verification command result: {command}")
            continue
        if any(_has_failing_verification_result(line) for line in matching_lines):
            issues.append(f"{OUTBOX_PATH.as_posix()} assigned verification command has failing result: {command}")
        if not any(_has_clean_verification_result(line) for line in matching_lines):
            issues.append(f"{OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: {command}")
    return issues


def _section_items(text: str) -> list[str]:
    """Return markdown bullet items from a section body."""

    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        if not value or value in {"None", "Not applicable"} or value.startswith("<"):
            continue
        items.append(value)
    return items


def _numbered_section_items(text: str) -> list[str]:
    """Return numbered markdown items from a section body."""

    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        match = re.fullmatch(r"\d+\.\s+(.+)", stripped)
        if not match:
            continue
        value = match.group(1).strip()
        if not value or value in {"None", "Not applicable"} or value.startswith("<"):
            continue
        items.append(value)
    return items


def _checked_acceptance_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [x] ") or stripped.startswith("- [X] "):
            items.append(stripped)
    return items


def _unchecked_acceptance_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ] "):
            item = stripped[6:].strip()
            if item:
                items.append(item)
    return items


def _checked_acceptance_text(item: str) -> str:
    if item.startswith("- [x] ") or item.startswith("- [X] "):
        return item[6:].strip()
    return item.strip()


def _has_negative_acceptance_evidence(value: str) -> bool:
    normalized = " ".join(value.strip().lower().split())
    return any(marker in normalized for marker in ACCEPTANCE_FAILURE_EVIDENCE)


def _normalize_acceptance_text(value: str) -> str:
    normalized = " ".join(value.strip().casefold().split())
    return normalized.rstrip(".:")


def _acceptance_item_covers_criterion(*, item: str, criterion: str) -> bool:
    normalized_item = _normalize_acceptance_text(item)
    normalized_criterion = _normalize_acceptance_text(criterion)
    if not normalized_item.startswith(normalized_criterion):
        return False
    if len(normalized_item) == len(normalized_criterion):
        return True
    next_character = normalized_item[len(normalized_criterion)]
    return not next_character.isalnum()


def _has_clean_verification_result(line: str) -> bool:
    normalized = _verification_result_evidence_text(line)
    if any(marker in normalized for marker in VERIFICATION_FAILURE_EVIDENCE):
        return False
    return any(marker in normalized for marker in VERIFICATION_RESULT_EVIDENCE)


def _has_failing_verification_result(line: str) -> bool:
    normalized = _verification_result_evidence_text(line)
    return any(marker in normalized for marker in VERIFICATION_FAILURE_EVIDENCE)


def _verification_result_evidence_text(line: str) -> str:
    """Return verification prose outside backticked command spans."""

    return _evidence_text_outside_backticks(line)


def _evidence_text_outside_backticks(text: str) -> str:
    """Return evidence prose outside backticked command spans."""

    return re.sub(r"`[^`\r\n]*`", " ", text).lower()


def _has_shell_control_operator(command: str) -> bool:
    return any(operator in command for operator in SHELL_CONTROL_OPERATORS) or bool(
        SHELL_VARIABLE_EXPANSION_PATTERN.search(command)
    )


def _has_response_file_argument(command: str) -> bool:
    return bool(RESPONSE_FILE_ARGUMENT_PATTERN.search(command))


def _is_python_executable_token(token: str) -> bool:
    normalized = token.strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return normalized in {"py", "py.exe", "python", "python.exe"} or normalized.startswith("python")


def _has_unsafe_verification_flag(command: str) -> bool:
    tokens = command.strip().split()
    for index, token in enumerate(tokens):
        if "::" in token:
            return True

        if token == "-m" and index > 0 and _is_python_executable_token(tokens[index - 1]):
            continue

        if (
            token in UNSAFE_VERIFICATION_FLAGS
            or token.startswith(UNSAFE_VERIFICATION_FLAG_PREFIXES)
            or any(
                token.startswith(prefix) and token != prefix
                for prefix in UNSAFE_VERIFICATION_ATTACHED_SHORT_FLAG_PREFIXES
            )
        ):
            return True

    return False


def _has_wrapped_required_verification_command(command: str) -> bool:
    return any(
        _contains_required_verification_command(command, required_command)
        and not _matches_required_verification_command(command, required_command)
        for required_command in REQUIRED_VERIFICATION_COMMANDS
    )


def _has_unresolved_angle_marker(value: str) -> bool:
    return ANGLE_BRACKET_MARKER_PATTERN.search(value) is not None


def _contains_required_verification_command(command: str, required_command: str) -> bool:
    normalized = " ".join(command.strip().split())
    if required_command == "git diff --check":
        return re.search(r"(?<!\S)git\s+diff\s+--check(?!\S)", normalized) is not None
    return (
        re.search(
            rf"(?<!\S)(?:{PYTHON_MODULE_RUNNER_PATTERN})?{re.escape(required_command)}(?!\S)",
            normalized,
        )
        is not None
    )


def _matches_required_verification_command(command: str, required_command: str) -> bool:
    normalized = " ".join(command.strip().split())
    if required_command == "git diff --check":
        return re.search(r"^git\s+diff\s+--check(?!\S)", normalized) is not None
    return (
        re.search(
            rf"^(?:{PYTHON_MODULE_RUNNER_PATTERN})?{re.escape(required_command)}(?!\S)",
            normalized,
        )
        is not None
    )


def _is_rg_scan_command(command: str) -> bool:
    tokens = command.strip().split()
    if not tokens:
        return False
    return tokens[0].casefold() in {"rg", "rg.exe"}


def _looks_like_scan_command(command: str) -> bool:
    tokens = command.strip().split()
    if len(tokens) < 2:
        return False
    command_lower = command.casefold()
    return any(marker in command_lower for marker in SCAN_COMMAND_EVIDENCE)


def _missing_anti_placeholder_patterns(command: str) -> tuple[str, ...]:
    return tuple(pattern for pattern in ANTI_PLACEHOLDER_SCANNER_PATTERNS if pattern not in command)


def _rg_scan_command_missing_path_delimiter(command: str) -> bool:
    return _is_rg_scan_command(command) and "--" not in command.strip().split()


def _git_diff_check_uses_paths_without_delimiter(command: str) -> bool:
    normalized = " ".join(command.strip().split())
    tokens = normalized.split()

    for index in range(len(tokens) - 2):
        if tokens[index : index + 3] != ["git", "diff", "--check"]:
            continue
        remaining_tokens = tokens[index + 3 :]
        return bool(remaining_tokens) and "--" not in remaining_tokens

    return False


def _mentions_path_token(text: str, path: str) -> bool:
    normalized_text = text.replace("\\", "/")
    normalized_path = _normalize_scope_path(path)
    if not normalized_path:
        return False
    return (
        re.search(
            rf"(?<![A-Za-z0-9_./-]){re.escape(normalized_path)}(?![A-Za-z0-9_./-])",
            normalized_text,
        )
        is not None
    )


def _extract_verification_commands(body: str) -> tuple[str, ...]:
    commands: list[str] = []
    in_fence = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            commands.append(line)
            continue
        if line.startswith("- "):
            match = re.fullmatch(r"-\s+`([^`]+)`(?:\s+-\s+.*)?", line)
            if match:
                commands.append(match.group(1).strip())
    return tuple(commands)


def _extract_outbox_verification_results(body: str) -> tuple[tuple[str, str], ...]:
    results: list[tuple[str, str]] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.search(r"`([^`]+)`", line)
        if match:
            results.append((match.group(1).strip(), line))
    return tuple(results)


def _extract_scan_commands(body: str) -> tuple[str, ...]:
    commands: list[str] = []

    for raw_line in body.splitlines():
        for match in re.finditer(r"`([^`]+)`", raw_line):
            command = match.group(1).strip()
            if _looks_like_scan_command(command):
                commands.append(command)

    return tuple(commands)


def _has_clean_scan_command_line(body: str) -> bool:
    for raw_line in body.splitlines():
        if not any(
            _looks_like_scan_command(match.group(1).strip())
            for match in re.finditer(r"`([^`]+)`", raw_line)
        ):
            continue
        evidence_text = _evidence_text_outside_backticks(raw_line)
        if any(marker in evidence_text for marker in SCAN_RESULT_EVIDENCE):
            return True
    return False


def _extract_inbox_scan_commands(body: str) -> tuple[str, ...]:
    commands: list[str] = []
    seen: set[str] = set()
    for command in (*_extract_verification_commands(body), *_extract_scan_commands(body)):
        if not _looks_like_scan_command(command):
            continue
        if command in seen:
            continue
        seen.add(command)
        commands.append(command)
    return tuple(commands)


def _normalized_section_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("-"):
            line = line[1:].strip()
        if line:
            lines.append(line)
    return lines


def _normalize_evidence_line(value: str) -> str:
    return value.strip().strip("`").strip().lower().rstrip(".")


def _validate_required_reading_section_paths(
    *,
    text: str,
    heading: str,
    label: str,
    root: Path | None = None,
) -> list[str]:
    """Validate a required-reading section in a ready inbox task."""

    raw_paths = _raw_path_section_items(_section_body(text, heading))
    if not raw_paths:
        return [f"{INBOX_PATH.as_posix()} ready inbox must list {label} paths"]

    normalized_paths = [_normalize_scope_path(path) for path in raw_paths]
    issues = _validate_path_list(label=label, raw_paths=raw_paths, normalized_paths=normalized_paths)

    for normalized_path in _unique_nonempty(normalized_paths):
        if normalized_path in REQUIRED_READING_CONTROL_FILE_PATHS:
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox {label} path must not list "
                f"handoff control file: {normalized_path}"
            )

    if root is None:
        return issues

    for raw_path, normalized_path in zip(raw_paths, normalized_paths, strict=True):
        if not normalized_path:
            continue
        if _is_unsafe_scope_path(raw_path=raw_path, normalized_path=normalized_path):
            continue
        if not (root / normalized_path).is_file():
            issues.append(f"{INBOX_PATH.as_posix()} ready inbox {label} path must point to a file: {normalized_path}")
    return issues


def _normalized_required_reading_paths(text: str, heading: str) -> tuple[str, ...]:
    """Return normalized required-reading paths for parity checks."""

    return tuple(_normalize_scope_path(path) for path in _raw_path_section_items(_section_body(text, heading)))


def _validate_required_reading_core_paths(*, paths: Sequence[str], label: str) -> list[str]:
    """Validate that ready inbox tasks keep the core reading contract."""

    path_set = set(paths)
    return [
        f"{INBOX_PATH.as_posix()} ready inbox {label} must include core path: {required_path}"
        for required_path in READY_INBOX_CORE_REQUIRED_READING_PATHS
        if required_path not in path_set
    ]


def _validate_contract_section(*, text: str, heading: str, label: str) -> list[str]:
    """Validate task input and output contract sections."""

    items = _section_items(_section_body(text, heading))
    issues: list[str] = []
    if not items:
        issues.append(f"{INBOX_PATH.as_posix()} ready inbox must include at least one {label} item")
        return issues

    seen_items: set[str] = set()
    for item in items:
        normalized_item = " ".join(item.casefold().split())
        if normalized_item.rstrip(".") in CONTRACT_STAND_IN_VALUES:
            issues.append(f"{INBOX_PATH.as_posix()} ready inbox {label} is an empty stand-in: {item}")
        if normalized_item in seen_items:
            issues.append(f"{INBOX_PATH.as_posix()} ready inbox {label} is duplicated: {item}")
        seen_items.add(normalized_item)
    return issues


def _validate_worktree_baseline_paths(body: str, *, allowed_files: Sequence[str] = ()) -> list[str]:
    """Validate assignment-time worktree baseline entries."""

    raw_items = _raw_section_items(body)
    if not raw_items:
        return [f"{INBOX_PATH.as_posix()} ready inbox worktree baseline must list None or paths"]

    empty_markers = [item for item in raw_items if _normalize_evidence_line(item) in NO_WORKTREE_BASELINE_VALUES]
    raw_paths = [item for item in raw_items if _normalize_evidence_line(item) not in NO_WORKTREE_BASELINE_VALUES]
    issues: list[str] = []

    if empty_markers and raw_paths:
        issues.append(f"{INBOX_PATH.as_posix()} ready inbox worktree baseline cannot mix None with paths")

    normalized_paths = [_normalize_scope_path(path) for path in raw_paths]
    issues.extend(
        _validate_path_list(
            label="worktree baseline",
            raw_paths=raw_paths,
            normalized_paths=normalized_paths,
        )
    )
    normalized_allowed_paths = [_normalize_scope_path(path) for path in allowed_files]
    for baseline_path in normalized_paths:
        if not baseline_path:
            continue
        for allowed_path in normalized_allowed_paths:
            if allowed_path and _scope_paths_overlap(baseline_path, allowed_path):
                issues.append(
                    f"{INBOX_PATH.as_posix()} ready inbox worktree baseline must not overlap "
                    f"allowed scope: {baseline_path} vs {allowed_path}"
                )
    return issues


def _validate_ready_outbox_changed_file_paths(body: str, *, root: Path | None = None) -> list[str]:
    """Validate changed-file evidence in a ready outbox."""

    raw_items = _raw_path_section_items(body)
    empty_markers = [item for item in raw_items if _normalize_evidence_line(item) in NO_CHANGED_FILE_VALUES]
    raw_paths = [item for item in raw_items if _normalize_evidence_line(item) not in NO_CHANGED_FILE_VALUES]
    issues: list[str] = []
    if empty_markers and raw_paths:
        issues.append(
            f"{OUTBOX_PATH.as_posix()} ready outbox changed files cannot mix no-change evidence with paths"
        )
    if not raw_paths:
        return [f"{OUTBOX_PATH.as_posix()} ready outbox must list changed files"]

    normalized_paths = [_normalize_scope_path(path) for path in raw_paths]
    issues.extend(
        _validate_repository_relative_path_list(
            owner=f"{OUTBOX_PATH.as_posix()} ready outbox",
            label="changed file",
            raw_paths=raw_paths,
            normalized_paths=normalized_paths,
        )
    )
    for normalized_path in normalized_paths:
        if normalized_path in HANDOFF_CONTROL_CHANGED_FILE_PATHS:
            issues.append(
                f"{OUTBOX_PATH.as_posix()} ready outbox changed files must not list "
                f"handoff control file: {normalized_path}"
            )
        elif normalized_path in ASSIGNMENT_CONTROL_FILE_PATHS:
            issues.append(
                f"{OUTBOX_PATH.as_posix()} ready outbox changed files must not list "
                f"workflow control file: {normalized_path}"
            )
    if root is None:
        return issues

    for raw_path, normalized_path in zip(raw_paths, normalized_paths, strict=True):
        if not normalized_path:
            continue
        if _is_unsafe_scope_path(raw_path=raw_path, normalized_path=normalized_path):
            continue
        if normalized_path in HANDOFF_CONTROL_CHANGED_FILE_PATHS:
            continue
        if normalized_path in ASSIGNMENT_CONTROL_FILE_PATHS:
            continue
        if not (root / normalized_path).is_file():
            issues.append(
                f"{OUTBOX_PATH.as_posix()} ready outbox changed file path must point to a file: "
                f"{normalized_path}"
            )
    return issues


def _ready_outbox_changed_paths(body: str) -> tuple[str, ...]:
    raw_paths = [
        item
        for item in _raw_path_section_items(body)
        if _normalize_evidence_line(item) not in NO_CHANGED_FILE_VALUES
    ]
    return tuple(_unique_nonempty([_normalize_scope_path(path) for path in raw_paths]))


def _ready_inbox_allowed_paths(body: str) -> tuple[str, ...]:
    raw_paths = _raw_path_section_items(body)
    allowed_paths: list[str] = []

    for raw_path in raw_paths:
        normalized_path = _normalize_scope_path(raw_path)
        if not normalized_path:
            continue
        if _is_unsafe_scope_path(raw_path=raw_path, normalized_path=normalized_path):
            continue
        if normalized_path in HANDOFF_CONTROL_FILE_PATHS:
            continue
        allowed_paths.append(normalized_path)

    return tuple(_unique_nonempty(allowed_paths))


def _ready_inbox_concrete_allowed_paths(body: str) -> tuple[str, ...]:
    return tuple(path for path in _ready_inbox_allowed_paths(body) if Path(path).suffix)


def _validate_ready_inbox_verification_covers_allowed_files(
    *,
    allowed_files_body: str,
    verification_commands: Sequence[str],
) -> list[str]:
    """Validate assignment commands against concrete allowed-file scope."""

    allowed_scope_paths = _ready_inbox_allowed_paths(allowed_files_body)
    allowed_paths = _ready_inbox_concrete_allowed_paths(allowed_files_body)
    issues: list[str] = []

    for allowed_path in allowed_scope_paths:
        if not _verification_commands_covering_path(
            verification_commands=verification_commands,
            required_command="git diff --check",
            path=allowed_path,
        ):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox git diff --check must mention allowed path: "
                f"{allowed_path}"
            )

    for allowed_path in allowed_paths:
        if not allowed_path.endswith(".py"):
            continue
        if not _verification_commands_covering_path(
            verification_commands=verification_commands,
            required_command="ruff",
            path=allowed_path,
        ):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox ruff check must mention allowed Python file: "
                f"{allowed_path}"
            )

    for allowed_path in allowed_paths:
        if not allowed_path.startswith("tests/") or not allowed_path.endswith(".py"):
            continue
        if not _verification_commands_covering_path(
            verification_commands=verification_commands,
            required_command="pytest",
            path=allowed_path,
        ):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox pytest must mention allowed test file: "
                f"{allowed_path}"
            )

    return issues


def _verification_commands_covering_path(
    *,
    verification_commands: Sequence[str],
    required_command: str,
    path: str,
) -> tuple[str, ...]:
    return tuple(
        command
        for command in verification_commands
        if _matches_required_verification_command(command, required_command)
        and _mentions_path_token(command, path)
    )


def _validate_ready_inbox_scan_covers_allowed_files(*, allowed_files_body: str, scan_body: str) -> list[str]:
    issues: list[str] = []
    allowed_files = [
        normalized_path
        for raw_path in _section_items(allowed_files_body)
        if (normalized_path := _normalize_scope_path(raw_path))
    ]
    scan_commands = _extract_inbox_scan_commands(scan_body)
    if not scan_commands:
        issues.append(f"{INBOX_PATH.as_posix()} ready inbox Anti-Placeholder scan must include a parseable command")
        return issues

    usable_scan_commands: list[str] = []
    seen_scan_commands: set[str] = set()
    for command in scan_commands:
        command_has_issue = False
        if _has_shell_control_operator(command):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox Anti-Placeholder scan command must not include "
                f"shell control operators: {command}"
            )
            command_has_issue = True
        if _has_response_file_argument(command):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox Anti-Placeholder scan command must not include "
                f"response-file arguments: {command}"
            )
            command_has_issue = True
        if _has_unresolved_angle_marker(command):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox Anti-Placeholder scan command must not include "
                f"unresolved angle-bracket markers: {command}"
            )
            command_has_issue = True
        if not _is_rg_scan_command(command):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox Anti-Placeholder scan command must start "
                f"with rg or rg.exe: {command}"
            )
            command_has_issue = True
        if _rg_scan_command_missing_path_delimiter(command):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox Anti-Placeholder scan command must use "
                f"-- before the path list: {command}"
            )
            command_has_issue = True
        if any(marker in command for marker in INBOX_SCAN_TEMPLATE_MARKERS):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox Anti-Placeholder scan command must include "
                f"a concrete scanner expression: {command}"
            )
            command_has_issue = True
        missing_patterns = _missing_anti_placeholder_patterns(command)
        if missing_patterns:
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox Anti-Placeholder scan command must include "
                f"all configured scanner patterns; missing: {', '.join(missing_patterns)}"
            )
            command_has_issue = True
        if command in seen_scan_commands:
            issues.append(f"{INBOX_PATH.as_posix()} ready inbox Anti-Placeholder scan command is duplicated: {command}")
            command_has_issue = True
        if command_has_issue:
            continue
        seen_scan_commands.add(command)
        usable_scan_commands.append(command)

    for allowed_path in allowed_files:
        if not any(_mentions_path_token(command, allowed_path) for command in usable_scan_commands):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox Anti-Placeholder scan command must mention "
                f"allowed file: {allowed_path}"
            )

    return issues


def _validate_ready_outbox_diff_check_covers_changed_files(
    *,
    changed_files_body: str,
    verification_results: Sequence[tuple[str, str]],
) -> list[str]:
    """Validate diff-check evidence against ready outbox changed files."""

    changed_paths = _ready_outbox_changed_paths(changed_files_body)

    issues: list[str] = []
    for changed_path in changed_paths:
        covering_lines = _verification_result_lines_covering_path(
            verification_results=verification_results,
            required_command="git diff --check",
            changed_path=changed_path,
        )
        if changed_path and not covering_lines:
            issues.append(
                f"{OUTBOX_PATH.as_posix()} ready outbox git diff --check must mention changed file: "
                f"{changed_path}"
            )
            continue
        issues.extend(
            _validate_covering_verification_results_clean(
                label="git diff --check",
                path_label="changed file",
                changed_path=changed_path,
                covering_lines=covering_lines,
            )
        )
    return issues


def _validate_ready_outbox_ruff_covers_changed_python_files(
    *,
    changed_files_body: str,
    verification_results: Sequence[tuple[str, str]],
) -> list[str]:
    """Validate ruff evidence against ready outbox changed Python files."""

    changed_python_paths = tuple(path for path in _ready_outbox_changed_paths(changed_files_body) if path.endswith(".py"))

    issues: list[str] = []
    for changed_path in changed_python_paths:
        covering_lines = _verification_result_lines_covering_path(
            verification_results=verification_results,
            required_command="ruff",
            changed_path=changed_path,
        )
        if not covering_lines:
            issues.append(
                f"{OUTBOX_PATH.as_posix()} ready outbox ruff check must mention changed Python file: "
                f"{changed_path}"
            )
            continue
        issues.extend(
            _validate_covering_verification_results_clean(
                label="ruff check",
                path_label="changed Python file",
                changed_path=changed_path,
                covering_lines=covering_lines,
            )
        )
    return issues


def _validate_ready_outbox_pytest_covers_changed_test_files(
    *,
    changed_files_body: str,
    verification_results: Sequence[tuple[str, str]],
) -> list[str]:
    """Validate pytest evidence against ready outbox changed test files."""

    changed_test_paths = tuple(
        path
        for path in _ready_outbox_changed_paths(changed_files_body)
        if path.startswith("tests/") and path.endswith(".py")
    )

    issues: list[str] = []
    for changed_path in changed_test_paths:
        covering_lines = _verification_result_lines_covering_path(
            verification_results=verification_results,
            required_command="pytest",
            changed_path=changed_path,
        )
        if not covering_lines:
            issues.append(
                f"{OUTBOX_PATH.as_posix()} ready outbox pytest must mention changed test file: "
                f"{changed_path}"
            )
            continue
        issues.extend(
            _validate_covering_verification_results_clean(
                label="pytest",
                path_label="changed test file",
                changed_path=changed_path,
                covering_lines=covering_lines,
            )
        )
    return issues


def _verification_result_lines_covering_path(
    *,
    verification_results: Sequence[tuple[str, str]],
    required_command: str,
    changed_path: str,
) -> tuple[str, ...]:
    return tuple(
        line
        for command, line in verification_results
        if _matches_required_verification_command(command, required_command)
        and _mentions_path_token(command, changed_path)
    )


def _validate_covering_verification_results_clean(
    *,
    label: str,
    path_label: str,
    changed_path: str,
    covering_lines: Sequence[str],
) -> list[str]:
    issues: list[str] = []
    if any(_has_failing_verification_result(line) for line in covering_lines):
        issues.append(
            f"{OUTBOX_PATH.as_posix()} ready outbox {label} result is failing for "
            f"{path_label}: {changed_path}"
        )
    if not any(_has_clean_verification_result(line) for line in covering_lines):
        issues.append(
            f"{OUTBOX_PATH.as_posix()} ready outbox {label} result must be clean for "
            f"{path_label}: {changed_path}"
        )
    return issues


def _validate_ready_outbox_scan_covers_changed_files(*, changed_files_body: str, scan_body: str) -> list[str]:
    """Validate scanner evidence against ready outbox changed files."""

    changed_paths = _ready_outbox_changed_paths(changed_files_body)
    normalized_scan_commands = "\n".join(
        command
        for command in _extract_scan_commands(scan_body)
        if not _has_shell_control_operator(command)
        and not _has_response_file_argument(command)
    ).replace("\\", "/")

    issues: list[str] = []
    for changed_path in changed_paths:
        if changed_path and not _mentions_path_token(normalized_scan_commands, changed_path):
            issues.append(
                f"{OUTBOX_PATH.as_posix()} ready outbox Anti-Placeholder scan must mention changed file: "
                f"{changed_path}"
            )
    return issues


def _validate_ready_outbox_summary(body: str) -> list[str]:
    """Validate that ready outbox summaries carry review-useful detail."""

    summary_items = _section_items(body)
    issues: list[str] = []

    if len(summary_items) < 2:
        issues.append(
            f"{OUTBOX_PATH.as_posix()} ready outbox summary must include at least "
            "2 concrete bullet items"
        )

    for item in summary_items:
        normalized_item = _normalize_evidence_line(item)
        if normalized_item in GENERIC_SUMMARY_ITEMS:
            issues.append(
                f"{OUTBOX_PATH.as_posix()} ready outbox summary item is too generic: "
                f"{item}"
            )

    return issues


def _raw_section_items(text: str) -> list[str]:
    """Return raw markdown bullet item values, unwrapping a backticked value when present."""

    return _raw_path_section_items(text)


def _raw_path_section_items(text: str) -> list[str]:
    """Return bullet values, unwrapping only a complete backticked path token."""

    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        value = _unwrap_path_item(value)
        if value:
            items.append(value)
    return items


def _unwrap_path_item(value: str) -> str:
    if "`" not in value:
        return value
    match = re.fullmatch(r"`([^`]+)`(?:\s+-\s+.*)?", value)
    if match:
        return match.group(1).strip()
    return value


def _validate_scope_paths(*, allowed_files: Sequence[str], forbidden_files: Sequence[str]) -> list[str]:
    """Validate allowed/forbidden scope path safety."""

    issues: list[str] = []
    allowed_paths = [_normalize_scope_path(path) for path in allowed_files]
    forbidden_paths = [_normalize_scope_path(path) for path in forbidden_files]

    for label, raw_paths, normalized_paths in (
        ("allowed", allowed_files, allowed_paths),
        ("forbidden", forbidden_files, forbidden_paths),
    ):
        issues.extend(_validate_path_list(label=label, raw_paths=raw_paths, normalized_paths=normalized_paths))
        issues.extend(_validate_overlapping_scope_entries(label=label, normalized_paths=normalized_paths))

    for allowed_path in _unique_nonempty(allowed_paths):
        if not allowed_path:
            continue
        if _is_broad_allowed_directory_scope(allowed_path):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox allowed scope must not use "
                f"broad top-level directory: {allowed_path}"
            )
        if any(_scope_paths_overlap(allowed_path, control_path) for control_path in HANDOFF_CONTROL_FILE_PATHS):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox allowed scope must not include "
                f"handoff control file: {allowed_path}"
            )
        if any(_scope_paths_overlap(allowed_path, control_path) for control_path in ASSIGNMENT_CONTROL_FILE_PATHS):
            issues.append(
                f"{INBOX_PATH.as_posix()} ready inbox allowed scope must not include "
                f"workflow control file: {allowed_path}"
            )
        for forbidden_path in _unique_nonempty(forbidden_paths):
            if not forbidden_path:
                continue
            if _scope_paths_overlap(allowed_path, forbidden_path):
                issues.append(
                    f"{INBOX_PATH.as_posix()} ready inbox has overlapping allowed and forbidden scope: "
                    f"{allowed_path} vs {forbidden_path}"
                )
    return issues


def _validate_overlapping_scope_entries(*, label: str, normalized_paths: Sequence[str]) -> list[str]:
    issues: list[str] = []
    unique_paths = _unique_nonempty(normalized_paths)
    for index, left_path in enumerate(unique_paths):
        for right_path in unique_paths[index + 1 :]:
            if left_path == right_path:
                continue
            if _scope_paths_overlap(left_path, right_path):
                issues.append(
                    f"{INBOX_PATH.as_posix()} ready inbox has overlapping {label} scope: "
                    f"{left_path} vs {right_path}"
                )
    return issues


def _validate_path_list(*, label: str, raw_paths: Sequence[str], normalized_paths: Sequence[str]) -> list[str]:
    return _validate_repository_relative_path_list(
        owner=f"{INBOX_PATH.as_posix()} ready inbox",
        label=label,
        raw_paths=raw_paths,
        normalized_paths=normalized_paths,
    )


def _validate_repository_relative_path_list(
    *,
    owner: str,
    label: str,
    raw_paths: Sequence[str],
    normalized_paths: Sequence[str],
) -> list[str]:
    issues: list[str] = []
    seen: set[str] = set()
    for raw_path, normalized_path in zip(raw_paths, normalized_paths, strict=True):
        if _is_path_stand_in(raw_path):
            issues.append(f"{owner} has empty {label} path stand-in: {_display_scope_path(raw_path)}")
            continue
        if not normalized_path:
            issues.append(f"{owner} has empty {label} path")
            continue
        if _is_unsafe_scope_path(raw_path=raw_path, normalized_path=normalized_path):
            issues.append(f"{owner} has unsafe {label} path: {_display_scope_path(raw_path)}")
        if normalized_path in seen:
            issues.append(f"{owner} has duplicate {label} path: {normalized_path}")
        seen.add(normalized_path)
    return issues


def _normalize_scope_path(path: str) -> str:
    value = _strip_wrapping_backticks(path).replace("\\", "/")
    while "//" in value:
        value = value.replace("//", "/")
    return value.strip().rstrip("/")


def _display_scope_path(path: str) -> str:
    return _strip_wrapping_backticks(path).replace("\r", "\\r").replace("\n", "\\n")


def _is_unsafe_scope_path(*, raw_path: str, normalized_path: str) -> bool:
    value = _strip_wrapping_backticks(raw_path)
    if _is_path_stand_in(value):
        return True
    if any(character.isspace() for character in value):
        return True
    normalized_parts = tuple(part for part in normalized_path.split("/") if part)
    if any(part in RESERVED_PATH_SCOPE_SEGMENTS for part in normalized_parts):
        return True
    if "`" in value:
        return True
    if any(character in value for character in BANNED_PATH_GLOB_CHARACTERS):
        return True
    if any(character in value for character in BANNED_PATH_SHELL_CHARACTERS):
        return True
    if "\n" in value or "\r" in value:
        return True
    if Path(value).is_absolute():
        return True
    if value.startswith(("/", "\\")):
        return True
    if "://" in value:
        return True
    if ":" in value:
        return True
    return any(part in {"..", "."} for part in normalized_path.split("/"))


def _is_path_stand_in(path: str) -> bool:
    return _normalize_evidence_line(_strip_wrapping_backticks(path)) in PATH_STAND_IN_VALUES


def _strip_wrapping_backticks(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped.count("`") == 2 and stripped.startswith("`") and stripped.endswith("`"):
        return stripped[1:-1].strip()
    return stripped


def _scope_paths_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")


def _is_broad_allowed_directory_scope(path: str) -> bool:
    return path in BROAD_ALLOWED_DIRECTORY_SCOPES


def _scope_contains_path(*, scope: str, path: str) -> bool:
    return bool(scope) and (path == scope or path.startswith(f"{scope}/"))


def _unique_nonempty(paths: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if not path or path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def _section_body(text: str, heading: str) -> str:
    """Return the body for a markdown heading, stopping at the next same-or-higher heading."""

    lines = text.splitlines()
    target_level = _heading_level(heading)
    if target_level is None:
        return ""

    body_lines: list[str] = []
    in_section = False

    for line in lines:
        stripped = line.strip()
        if not in_section:
            if stripped == heading:
                in_section = True
            continue

        level = _heading_level(stripped)
        if level is not None and level <= target_level:
            break
        body_lines.append(line)

    return "\n".join(body_lines).strip()


def _heading_level(line: str) -> int | None:
    """Return markdown heading level for a line, or ``None`` when it is not a heading."""

    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None

    level = len(stripped) - len(stripped.lstrip("#"))
    if len(stripped) == level or stripped[level] != " ":
        return None

    return level


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description="Validate DeepSeek/Codex handoff documents.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root containing the handoff documents. Defaults to the current directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable JSON report.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point."""

    args = _parse_args(argv)
    issues = validate_handoff_docs(args.root)
    if args.json:
        print(json.dumps(to_jsonable_report(issues), ensure_ascii=False, indent=2))
        return 1 if issues else 0

    if issues:
        print("handoff docs validation failed:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1

    print("handoff docs ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
