# DeepSeek Task Spec Schema

This schema describes the repository-local JSON object accepted by `python -m utils.prepare_deepseek_task --spec-file`.

## Required Fields

- `message_id`: string, concrete Codex-generated id.
- `task`: string, concrete task code.
- `objective`: string, one bounded implementation objective.
- `input_contracts`: optional extra list of input contracts appended after the default preservation contract.
- `output_contracts`: optional extra list of output contracts appended after the default preservation contract.
- `allowed_files`: list of repository-relative file or directory scopes, 1 to 5 entries.
- `forbidden_files`: non-empty list of repository-relative file or directory scopes.
- `requirements`: list of at least 3 unique concrete implementation requirements.
- `acceptance_criteria`: list of at least 3 unique criteria.
- `verification_commands`: list containing pytest, ruff, and `git diff --check` commands.

Generated assignments require the ready outbox summary to include at least two concrete bullet items. Avoid generic completion-only wording such as "done" or "implemented" without detail.

## Optional Fields

- `required_reading`: extra list of repository-relative reading paths appended after default reading.
  Generated assignments always include `AGENTS.md`, `spec.md`, `architecture.md`, `task.md`, and `docs/handoff/deepseek_inbox.md`.
- `stop_conditions`: extra list of stop conditions appended after default stop conditions.

Unknown fields are rejected so misspelled field names cannot be silently ignored.
When writing with `--validate-repository`, every default and extra required-reading path must point to an existing file.

## Text Rules

- `message_id`, `task`, `objective`, `requirements`, `acceptance_criteria`, `stop_conditions`, and `verification_commands` must use non-empty single-line strings.
- `input_contracts` and `output_contracts` entries must use non-empty unique single-line strings.
- `input_contracts` and `output_contracts` entries cannot be empty stand-ins such as None, N/A, TBD, or unknown.
- Spec-file list-type errors report the field name and 1-based item index for a non-string entry.
- Task text values must not use empty stand-ins such as None, N/A, TBD, or unknown.
- `requirements` entries must be unique and include at least 3 items.
- `acceptance_criteria` entries must be unique and include at least 3 items.
- `stop_conditions` entries must be unique and include at least 3 items.
- Spec values must not contain angle-bracket markers.
- Verification commands must use standalone command tokens and no shell control operators.
- Verification commands must start with direct command families, not shell wrappers.
- Verification commands must not use shell redirection.
- Verification commands must not use command substitution such as `$(...)` or backticks.
- Verification commands must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.
- Verification commands must not use response-file or splatting arguments such as `@args.txt`.
- Verification commands must not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.
- No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.
- Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.
- Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.
- Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.
- Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.
- Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.
- Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.
- Verification commands must mention each concrete allowed file as a path token.
- Git diff-check commands must mention every allowed file or directory scope as a path token.
- Git diff-check commands with pathspecs must use `--` before the path list.
- Generated assignments include a concrete Anti-Placeholder scan command over `allowed_files`.
- Generated Anti-Placeholder scan commands start with `rg`.
- Generated Anti-Placeholder scan commands include every configured scanner pattern.
- Generated Anti-Placeholder scan commands use `--` before the path list.
- Generated Anti-Placeholder scan commands do not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.
- Generated Anti-Placeholder scan commands do not use response-file or splatting arguments such as `@args.txt`.
- Text values must not contain Markdown code fences.
- `required_reading`, `allowed_files`, and `forbidden_files` must use repository-relative paths.
- Path values must not use URLs, drive names, absolute paths, wildcards, glob metacharacters, shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes, embedded whitespace, VCS/dependency/cache directories, `.` or `..` path segments, embedded Markdown backticks, line breaks, empty entries, empty stand-ins such as None, N/A, TBD, or unknown, or duplicates.
- Path values must not use wildcards or glob metacharacters.
- Path values must not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes.
- Path values must not use empty stand-ins such as None, N/A, TBD, or unknown.
- Path values must not contain embedded whitespace.
- Path values must not target VCS, dependency, or cache directories.
- `allowed_files` and `forbidden_files` must not contain overlapping scope entries within the same list.
- `required_reading` must not list mutable handoff control files: `docs/handoff/deepseek_outbox.md`, `DEEPSEEK_INBOX.md`, or `CODEX_REVIEW.md`.
- `allowed_files` must not include `docs/handoff/deepseek_inbox.md`, `docs/handoff/deepseek_outbox.md`, `DEEPSEEK_INBOX.md`, `CODEX_REVIEW.md`, or a parent scope that covers them.
- `allowed_files` must not include workflow control files such as handoff docs, root task plans, gate utilities, or CI gates.
- `allowed_files` must not use broad top-level directory scopes such as `dayu`, `docs`, `src`, `tests`, `utils`, `.github`, or `workspace`.
- Generated worktree baseline entries must not overlap `allowed_files`.

## Example

```json
{
  "message_id": "codex-20260801-example",
  "task": "HANDOFF_EXAMPLE",
  "objective": "Add one focused repository method and its unit test.",
  "allowed_files": [
    "src/storage/post_repository.py",
    "tests/test_post_repository.py"
  ],
  "forbidden_files": [
    "src/crawler/",
    "src/api/"
  ],
  "requirements": [
    "Keep the public repository interface stable.",
    "Add deterministic unit coverage for the new behavior.",
    "Surface storage errors instead of hiding them."
  ],
  "acceptance_criteria": [
    "New records are stored once.",
    "Duplicate records return the existing row.",
    "Verification commands are recorded in the outbox."
  ],
  "verification_commands": [
    "python -m pytest tests/test_post_repository.py -q",
    "python -m ruff check src/storage/post_repository.py tests/test_post_repository.py",
    "git diff --check -- src/storage/post_repository.py tests/test_post_repository.py"
  ]
}
```

## Validation

Preview before writing:

```powershell
python -m utils.prepare_deepseek_task --spec-file docs/handoff/example-task.json --dry-run
```

The `--spec-file` value must be a repository-relative path. It cannot use URLs, drive names, absolute paths, or parent-directory traversal.
The `--spec-file` value must be a readable JSON file, not a directory.
The `--spec-file` content must be UTF-8 JSON text.
Repository validation after write also checks required-reading entries point to files; if not, the command restores the previous handoff files and returns nonzero.
The same repository validation applies when the assignment comes from a JSON spec file.

Write only after preview:

```powershell
python -m utils.prepare_deepseek_task --spec-file docs/handoff/example-task.json --reset-outbox --validate-repository
```
