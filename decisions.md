# Decisions

## 2026-08-01: Supervised Dual-Model Development

Decision:

- Codex is the planner, architect, reviewer, debugger, and final acceptance gate.
- DeepSeek is a scoped implementation worker for low-cost coding tasks.
- DeepSeek work must enter through `DEEPSEEK_INBOX.md` and `docs/handoff/deepseek_inbox.md`.
- DeepSeek completion claims must be reviewed through `CODEX_REVIEW.md` and `docs/handoff/codex_review_checklist.md`.

Rationale:

- Low-cost models are useful for high-volume implementation, but they can drift, simplify requirements, or self-certify incomplete work.
- Persisted task files, scoped allowed paths, exact verification commands, and independent review reduce that risk.
