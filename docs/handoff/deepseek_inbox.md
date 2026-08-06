# DeepSeek Inbox

Status: WAITING_FOR_TASK
Message ID: unassigned
Task: unassigned

CODEX_GATE: REQUIRED

## Operating Role

DeepSeek is the low-cost implementation worker for scoped coding tasks. DeepSeek must not act as project owner, architect, final reviewer, release manager, or safety approver.

Codex owns planning, architecture, task slicing, review, difficult debugging, and final acceptance.

## Required Reading Before Editing

1. `AGENTS.md`
2. `spec.md` if it exists for the current task
3. `architecture.md` if it exists for the current task
4. This inbox file
5. The current task section below

If any required file or interface is missing, stop and record the blocker in `docs/handoff/deepseek_outbox.md`. Do not invent missing contracts.

## Current Task

No task assigned.

When Codex assigns a task, replace this section with one small task that includes:

- objective
- allowed files
- forbidden files
- input contracts
- output contracts
- acceptance criteria
- exact verification commands

## Global Implementation Rules

1. Complete only the current task. Do not start the next task.
2. Modify only the files listed under allowed files.
3. Do not delete, weaken, skip, or rewrite tests to make a failure pass.
4. Do not use TODO, FIXME, pass, NotImplemented, mock, placeholder, fake data, or hardcoded demo outputs as implementation.
5. Do not claim completion unless every acceptance criterion is satisfied.
6. Run the verification commands listed in the task.
7. Update `docs/handoff/deepseek_outbox.md` with changed files, test results, blockers, and residual risks.
8. Stop after writing the outbox.

## Anti-Placeholder Scan

Before writing `READY_FOR_CODEX_REVIEW`, run a scoped scan over changed source and test files for:

```text
TODO|FIXME|pass|NotImplemented|mock|placeholder|fake|dummy
```

If any hit is intentional, explain why in the outbox with the exact file and line.

## Required Outbox Evidence

The outbox must include:

- `READY_FOR_CODEX_REVIEW`
- changed files
- verification commands and exact results
- acceptance criteria checklist
- scope deviations, if any
- unresolved questions or blockers
- anti-placeholder scan result
- anti-placeholder clean result evidence on the same line as the scan command
