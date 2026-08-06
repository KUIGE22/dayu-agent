# Current Task: <short title>

Status: READY_FOR_DEEPSEEK
Message ID: <codex-generated-id>
Task: <task-code>

CODEX_GATE: PASS

## Objective

<Describe one bounded implementation goal. Keep the scope small enough that DeepSeek can complete it without architecture decisions.>

## Required Reading

- `AGENTS.md`
- `spec.md`
- `architecture.md`
- `task.md`
- `docs/handoff/deepseek_inbox.md`
- `<task-specific file>`

## Allowed Files

- `<path/to/source.py>`
- `<path/to/test.py>`

## Forbidden Files

- `<path/not/allowed.py>`
- `<directory/not/allowed/>`

## Worktree Baseline

- `<preexisting dirty path from git status before assignment>`
- Or `None` when the worktree is clean.

Baseline entries must be safe repository-relative paths from assignment-time git status. Use either path entries or `None`, never both.
Worktree baseline entries must not overlap allowed files.

## Input Contracts

- <Function, CLI, schema, file, or API inputs that must be preserved.>

Do not use empty stand-ins such as None, N/A, TBD, or unknown as a contract.

## Output Contracts

- <Expected return values, artifacts, logs, schema, or behavior.>

## Requirements

1. <Concrete implementation requirement.>
2. <Concrete implementation requirement.>
3. <Required error path or edge case.>

Requirements must be unique and include at least three numbered items.

## Acceptance Criteria

- [ ] <Happy path verified.>
- [ ] <Duplicate / empty / failure / concurrency path verified when relevant.>
- [ ] <No forbidden files modified.>
- [ ] <No tests deleted, weakened, skipped, or replaced with test doubles.>
- [ ] <Anti-Placeholder scan completed and explained.>
- [ ] <Verification commands succeed or blocker is recorded exactly.>

Acceptance criteria must be unique and include at least three unchecked items.
Remove every angle-bracket marker before assigning the task.

## Verification Commands

```powershell
Set-Location -LiteralPath '<repo-root>'
$env:PYTHONPATH = (Get-Location).Path
python -m pytest <focused tests> -q
python -m ruff check <changed python files>
git diff --check -- <allowed files>
```

Verification commands must be unique standalone command tokens and must not use shell control operators.
Verification commands must start with direct command families, not shell wrappers.
Verification commands must not use shell redirection.
Verification commands must not use command substitution such as `$(...)` or backticks.
Verification commands must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.
Verification commands must not use response-file or splatting arguments such as `@args.txt`.
Verification commands must not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.
No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.
Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.
Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.
Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.
Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.
Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.
Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.
Verification commands must mention each concrete allowed file as a path token.
Git diff-check commands must mention every allowed file or directory scope as a path token.
Git diff-check commands with pathspecs must use `--` before the path list.
Path values must not use wildcards or glob metacharacters.
Path values must not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes.
Path values must not use empty stand-ins such as None, N/A, TBD, or unknown.
Path values must not contain embedded whitespace.
Path values must not target VCS, dependency, or cache directories.
Allowed files must not include workflow control files such as handoff docs, root task plans, gate utilities, or CI gates.
Allowed files must not use broad top-level directory scopes such as `dayu`, `docs`, `src`, `tests`, `utils`, `.github`, or `workspace`.
Allowed and forbidden files must not contain overlapping scope entries within the same list.

## Anti-Placeholder Scan

Run this over changed implementation and test files:

```powershell
rg -n "BLOCKED_SCANNER_PATTERN" -- <allowed files>
```

Replace `BLOCKED_SCANNER_PATTERN` with the actual scanner expression before assigning the task.
Record the exact command in the outbox.
Anti-Placeholder scan command must start with `rg` or `rg.exe`.
Anti-Placeholder scan command must include every configured scanner pattern.
Anti-Placeholder scan command must use `--` before the path list.
Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.
Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`.
Anti-Placeholder scan command must mention every allowed file as a path token.
Do not report empty stand-ins such as None, N/A, or no scan as completed scanner evidence.

## Stop Conditions

- Stop if an interface, schema, or expected behavior is missing.
- Stop if implementation needs files outside `Allowed Files`.
- Stop if the task requires architecture, state-machine, concurrency, safety, trading, or model-routing decisions not already specified here.
- Stop if tests can only succeed by weakening assertions.

Stop conditions must be unique and include at least three items.

## Required Outbox

Write `docs/handoff/deepseek_outbox.md` with:

- `READY_FOR_CODEX_REVIEW`
- concrete summary with at least two bullet items
- changed files
- changed-file evidence must not list workflow control files
- verification commands and exact results
- every assigned verification command result includes a clean marker such as `exited 0`
- verification evidence must not say dry-run, manual-only, simulated, synthetic, or fabricated
- acceptance checklist as checked `- [x] ...` evidence items
- checked acceptance evidence must not say skipped, unverified, untested, pending, deferred, or not applicable
- Anti-Placeholder scan command and clean result
- Anti-Placeholder scan command must be exact and must not use shell control operators
- Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`
- Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`
- Anti-Placeholder scan command must not include unresolved angle-bracket markers
- Anti-Placeholder evidence must not say skipped, not executed, not scanned, or no scan
- scope deviations
- explicit `None` when no unresolved questions or blockers remain
