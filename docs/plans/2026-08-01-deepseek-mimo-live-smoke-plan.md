# DeepSeek Pro + MiMo Thinking Live Smoke Gate

Date: 2026-08-01

## Goal

Prepare the first bounded live write smoke run for the current dual-model setup:

- primary writing scenes use `deepseek-v4-pro`
- audit/review scenes use `mimo-v2.5-pro-thinking`
- the plan export performs no model calls
- no secret values are recorded
- the operator must explicitly run the exported command

## Non-Goals

- Do not call DeepSeek or MiMo during preflight.
- Do not mutate model routing configuration.
- Do not apply approval artifacts.
- Do not run a full multi-chapter write.
- Do not resume or overwrite an existing draft.

## Gate

The live smoke plan requires:

- `--preflight-only`
- explicit `--chapter`
- explicit `--template`
- explicit `--output`
- `--no-resume`
- explicit `--write-max-model-requests`
- explicit `--write-max-total-tokens`
- explicit `--write-max-estimated-cost`
- explicit `--write-budget-currency`

The gate rejects:

- `--fast`
- `--force`
- `--infer`
- dependency chapters: `投资要点概览`, `是否值得继续深研与待验证问题`
- budgets smaller than 64 model requests or 800000 total tokens
- research materialization
- config application or approval operations
- Challenger promotion operations

## Verified Command

```powershell
Set-Location -LiteralPath 'F:\claude-workspace\work\dayu-dual-model-mvp'
$env:PYTHONPATH = (Get-Location).Path
$workspace = '.\workspace\e2e-deepseek-mimo-1138-20260722-220431'
$template = (Resolve-Path -LiteralPath '.\dayu\assets\定性分析模板.md').Path
$output = '.\workspace\e2e-deepseek-mimo-1138-20260722-220431\draft\1138-live-smoke-business-20260801'
$snapshot = '.\workspace\e2e-deepseek-mimo-1138-20260722-220431\output\routing-snapshots\deepseek-pro-mimo-standard-live-smoke-business-20260801.json'
$plan = '.\workspace\e2e-deepseek-mimo-1138-20260722-220431\output\live-smoke-plans\deepseek-pro-mimo-standard-live-smoke-business-20260801.json'
& 'F:\claude-workspace\dayu-agent\.venv\Scripts\python.exe' -m dayu.cli write `
  --workspace $workspace `
  --ticker 1138 `
  --template $template `
  --output $output `
  --chapter '公司做的是什么生意' `
  --no-resume `
  --preflight-only `
  --write-max-model-requests 64 `
  --write-max-total-tokens 800000 `
  --write-max-estimated-cost 2.5 `
  --write-budget-currency CNY `
  --write-routing-snapshot-output $snapshot `
  --write-live-smoke-plan-output $plan
```

## Artifacts

- Routing snapshot: `workspace/e2e-deepseek-mimo-1138-20260722-220431/output/routing-snapshots/deepseek-pro-mimo-standard-live-smoke-business-20260801.json`
- Live smoke plan: `workspace/e2e-deepseek-mimo-1138-20260722-220431/output/live-smoke-plans/deepseek-pro-mimo-standard-live-smoke-business-20260801.json`

The exported plan records:

- execution scene count: 7
- signature scene count: 9
- fallback scene count: 0
- required environment variable names: `DEEPSEEK_API_KEY`, `MIMO_API_KEY`
- budget: 64 model requests, 800000 total tokens, 2.5 CNY estimated cost
- model execution flag: false
- secret recording flag: false

## Live Run Observation

The first attempted live smoke used `投资要点概览` and stopped before chapter generation because that chapter depends on prior chapter artifacts. This is now encoded as a gate rule, and the smoke target was changed to `公司做的是什么生意`.

The second attempted live smoke reached the standalone chapter, but the request-count budget of 8 was exhausted after MiMo infer and before DeepSeek write admission. A later run with 32 requests exercised DeepSeek write, MiMo audit, regenerate, and repair, but hit the repair/replay boundary at projected 38 requests.

The 32-request run also showed that `repair` inherited write-side tool access even though the repair contract is local patch generation. The repair manifest now sets `tool_selection.mode = none`, matching the config README and preventing spurious tool calls from a repair-only scene.

A subsequent 48-request / 600000-token run with repair tools disabled exercised MiMo infer, DeepSeek write, MiMo audit, MiMo confirm, and DeepSeek regenerate. It stopped before the next regenerate retry at projected 54 requests against the 48-request limit, after recording 45 budgeted requests, 490856 total tokens, and an estimated 0.40416236 CNY cost. The remaining failure was quality-driven rather than a missing route: the regenerated chapter was still rejected by audit, so the DeepSeek Flash write temperature was lowered from 1.3 to 0.8 for research writing scenes while keeping overview at 1.0.

The first temp=0.8 live run used the 48-request / 600000-token plan and reached MiMo infer, DeepSeek write, and MiMo audit. It stopped before MiMo confirm admission at projected 52 requests against the 48-request limit, after recording 39 budgeted requests, 275745 total tokens, and an estimated 0.214587 CNY cost. Because MiMo infer request counts vary by source traversal depth, the gate now requires at least 64 model requests and 800000 total tokens before exporting a live smoke plan intended to reach confirm and any follow-up repair/regenerate boundary.

The 64-request / 800000-token temp=0.8 live run completed successfully for `公司做的是什么生意`. It exercised MiMo infer, DeepSeek write, MiMo audit, and MiMo confirm, then exited with code 0 without repair or regenerate. Budget status was `within_budget`: 28 budgeted model requests, 240044 total tokens, and 0.19590304 CNY estimated cost. The final audit returned a successful audit flag and `class=ok`; confirm resolved two evidence suspicions as supported with anchor refinement needed rather than unsupported.

## Pricing Sources

DeepSeek Pro pricing is present in the local catalog using the same CNY-style cost-budget convention already used by the project. The public reference source is DeepSeek's official API pricing page: https://api-docs.deepseek.com/quick_start/pricing/

MiMo domestic and overseas pricing is documented by Xiaomi MiMo's official pay-as-you-go page: https://mimo.mi.com/docs/en-US/price/pay-as-you-go

This gate only records the MiMo required environment variable name and does not change MiMo pricing.

## Verification

Focused tests:

```powershell
python -m pytest tests/application/test_write_model_configuration_preapplication.py::test_cli_preflight_live_smoke_plan_export_is_configuration_read_only tests/application/test_write_model_configuration_preapplication.py::test_live_smoke_plan_rejects_dependency_chapters tests/engine/test_cli_running_config.py::test_parse_arguments_supports_write_live_smoke_plan_output tests/engine/test_cli_running_config.py::test_validate_live_smoke_plan_rejects_unbounded_modes tests/engine/test_cli_running_config.py::test_validate_live_smoke_plan_accepts_bounded_single_chapter tests/engine/test_prompt_assets.py::test_deepseek_flash_models_have_cost_budget_pricing -q
```

Broader regression:

```powershell
python -m pytest tests/application/test_write_service.py::test_write_service_preflight_resolves_full_dual_model_scene_plan tests/application/test_write_service.py::test_write_service_preflight_rejects_unpriced_models_for_cost_budget tests/engine/test_prompt_assets.py -q
```

Static checks:

```powershell
python -m ruff check dayu/services/write_model_live_smoke_plan.py dayu/cli/arg_parsing.py dayu/cli/commands/write.py tests/application/test_write_model_configuration_preapplication.py tests/engine/test_cli_running_config.py tests/engine/test_prompt_assets.py
git diff --check
```
