# DeepSeek Flash write defaults

Status: Superseded by the DeepSeek Pro write default.

This historical work unit is retained for audit context only. The current
package write-side default is `deepseek-v4-pro`, with `deepseek-v4-flash`
remaining selectable in `allowed_names` for explicit low-cost runs.

## Reference

This work unit follows the engineering-control idea from `noho/code-is-cheap`:
keep a narrow goal, define non-goals, leave durable artifacts, and validate the
changed boundary before continuing.

## Goal

Make DeepSeek Flash the package default for write-side generation scenes.

Affected write-side scenes:

- `write`
- `overview`
- `regenerate`
- `fix`
- `repair`

## Non-goals

- Do not change thinking, audit, decision, confirm, prompt, interactive,
  WeChat, infer, or conversation-compaction defaults.
- Do not store or rewrite API keys.
- Do not call DeepSeek, MiMo, Claude, or any other model.
- Do not consume challenger approvals or mutate manual-recovery artifacts.
- Do not change fallback, pricing, or provider catalog semantics.

## Boundary

The minimal durable configuration change is limited to each write-side scene
manifest's `model.default_name`.

`deepseek-v4-flash` was already present in the write-side `allowed_names`, so no
public model catalog expansion is required.

## Historical success signals

- At the time of this superseded work unit, write-side manifest tests expected
  `deepseek-v4-flash`; current package tests expect `deepseek-v4-pro`.
- Thinking-side defaults remain unchanged.
- Documentation states that DeepSeek Pro is the write-side default and that
  thinking/review gates remain separate.
- Focused tests succeed without external model calls.

## Residual risks

- Existing workspaces keep their copied manifest defaults until the operator
  runs the existing governed configuration-change path or reinitializes with a
  chosen provider.
- DeepSeek Flash runtime quality and latency still need live evaluation in an
  explicit, budgeted write run.
