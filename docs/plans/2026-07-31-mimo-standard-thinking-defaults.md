# MiMo standard thinking defaults

## Context

The package write-side defaults now use `deepseek-v4-pro`. A model-free
write preflight proved that the review-side defaults still required
`MIMO_PLAN_API_KEY`, while this deployment is configured with the standard
MiMo credential referenced by `MIMO_API_KEY`.

## Goal

Make the package defaults runnable as a dual-model route:

- DeepSeek Pro for write-side generation.
- Standard MiMo Thinking for reasoning, review, and conversation scenes.

## Changed scenes

- `prompt`
- `prompt_mt`
- `interactive`
- `infer`
- `decision`
- `audit`
- `confirm`
- `wechat`
- `conversation_compaction`

Each scene changes only `model.default_name`, from
`mimo-v2.5-pro-thinking-plan` to `mimo-v2.5-pro-thinking`.

## Non-goals

- Do not read, print, persist, or rotate API key values.
- Do not call DeepSeek, MiMo, Claude, or any other model.
- Do not remove Token Plan models from `allowed_names`.
- Do not change provider endpoints, pricing, fallback routes, or runtime
  temperature profiles.
- Do not mutate existing copied workspace manifests automatically.

## Verification

- Prompt asset tests cover all nine thinking-side defaults.
- Write preflight must resolve five write-side scenes to
  `deepseek-v4-pro` and four write-signature review scenes to
  `mimo-v2.5-pro-thinking`.
- Required environment variable names must be `DEEPSEEK_API_KEY` and
  `MIMO_API_KEY`.
- A routing snapshot is exported without creating a Host run or calling a
  model.

## Residual risk

Existing workspaces with copied manifests retain their current defaults until
they are reinitialized or changed through the governed configuration workflow.
Live quality, latency, and cost still require a separately approved and
budgeted model run.
