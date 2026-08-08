# Architecture Entry Point

The canonical architecture document is `docs/architect.md`.

Development must preserve the repository's layered boundary:

```text
UI -> Service -> Host -> Agent
```

DeepSeek implementation tasks must not make architecture decisions on their own. If a task requires changing module boundaries, schemas, state machines, rollback behavior, concurrency behavior, model routing, or safety gates, Codex must design and approve the task before implementation.
