# Project Spec

This repository builds Dayu, a buy-side financial report analysis agent. The system provides financial filing storage, research-template materialization, LLM-assisted writing, audit/review gates, and controlled handoff workflows.

## Current Development Contract

- Requirements must be written before broad implementation.
- Large work must be split into bounded tasks.
- DeepSeek may implement scoped tasks from `task.md`.
- Codex remains responsible for task slicing, architecture, review, difficult debugging, and final acceptance.
- No model may define completion for its own work without independent verification.

## Canonical References

- User and CLI behavior: `README.md`
- Agent execution rules: `AGENTS.md`
- Architecture overview: `architecture.md`
- Current task handoff: `task.md`
- Progress handoff: `progress.md`
- Verification policy: `test_plan.md`
