# DeepSeek Assignment Examples

Use this page when Codex prepares a bounded DeepSeek implementation task.

## Preview First

Always preview the generated inbox before writing repository state.

```powershell
python -m utils.prepare_deepseek_task `
  --message-id codex-20260801-example `
  --task HANDOFF_EXAMPLE `
  --objective "Add one focused repository method and its unit test." `
  --allowed-file src/storage/post_repository.py `
  --allowed-file tests/test_post_repository.py `
  --forbidden-file src/crawler/ `
  --forbidden-file src/api/ `
  --requirement "Keep the public repository interface stable." `
  --requirement "Add deterministic unit coverage for the new behavior." `
  --requirement "Surface storage errors instead of hiding them." `
  --acceptance "New records are stored once." `
  --acceptance "Duplicate records return the existing row." `
  --acceptance "Verification commands are recorded in the outbox." `
  --verification-command "python -m pytest tests/test_post_repository.py -q" `
  --verification-command "python -m ruff check src/storage/post_repository.py tests/test_post_repository.py" `
  --verification-command "git diff --check -- src/storage/post_repository.py tests/test_post_repository.py" `
  --dry-run
```

## Write And Reset

After the preview is correct, write the canonical inbox and reset stale outbox state.

```powershell
python -m utils.prepare_deepseek_task `
  --message-id codex-20260801-example `
  --task HANDOFF_EXAMPLE `
  --objective "Add one focused repository method and its unit test." `
  --allowed-file src/storage/post_repository.py `
  --allowed-file tests/test_post_repository.py `
  --forbidden-file src/crawler/ `
  --forbidden-file src/api/ `
  --requirement "Keep the public repository interface stable." `
  --requirement "Add deterministic unit coverage for the new behavior." `
  --requirement "Surface storage errors instead of hiding them." `
  --acceptance "New records are stored once." `
  --acceptance "Duplicate records return the existing row." `
  --acceptance "Verification commands are recorded in the outbox." `
  --verification-command "python -m pytest tests/test_post_repository.py -q" `
  --verification-command "python -m ruff check src/storage/post_repository.py tests/test_post_repository.py" `
  --verification-command "git diff --check -- src/storage/post_repository.py tests/test_post_repository.py" `
  --reset-outbox `
  --validate-repository
```

## Spec File Variant

For longer tasks, store structured task input in a JSON file and preview it first.
Extra required-reading entries must not list mutable handoff control files such as `docs/handoff/deepseek_outbox.md`, `DEEPSEEK_INBOX.md`, or `CODEX_REVIEW.md`.

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

```powershell
python -m utils.prepare_deepseek_task `
  --spec-file docs/handoff/example-task.json `
  --dry-run
```

## Validate

Run the local gates after writing the task.

```powershell
python -m utils.validate_handoff_docs --json
python -m utils.dual_model_pipeline_check --json
```

## Review

After DeepSeek marks the outbox `READY_FOR_CODEX_REVIEW`, run:

```powershell
python -m utils.codex_review_gate --json
python -m utils.dual_model_pipeline_check --require-ready --json
```
