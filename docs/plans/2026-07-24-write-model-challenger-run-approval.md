# Write Model Challenger Run Approval

## Objective

Authorize exactly one bounded, isolated Champion/Challenger write experiment
after an approved common preflight succeeds. The authorization is distinct
from proposal verification and common-preflight approval.

## Three-Stage Flow

1. An approved common preflight succeeds for both model plans and exports
   `write_model_challenger_run_plan_v1`.
2. A human request embeds that exact plan. A subsequent successful common
   preflight issues `write_model_challenger_run_approval_v1`.
3. A full write command verifies the current proposal, history, plan, time
   window, and output boundaries, then atomically consumes the approval before
   Host initialization.

The full command still performs the normal Champion and Challenger preflights
after Host initialization and before any write-stage model execution.

## Exact Run Plan

The plan binds:

- ticker;
- template absolute path and SHA-256 content fingerprint;
- distinct Champion and Challenger output directories;
- explicit current-model overrides;
- exact Challenger role override argv;
- explicit fallback overrides;
- write retry count, Web provider, temperature, and `resume=false`;
- per-run request, token, estimated-cost, and currency limits;
- the full experiment estimated-cost ceiling, exactly twice the per-run
  ceiling.

Both output directories must be new descendants of the workspace. Authorized
runs require explicit template, outputs, provider, budgets, and at least one
current Champion model override. They prohibit resume, fast, force, chapter
filters, research-template routing, and research materialization.

## Human Request

`write_model_challenger_run_approval_request_v1` contains:

- declarative operator identity and approval reference;
- UTC `approved_at` and `expires_at`, with at most four hours of validity;
- proposal, history, and common-preflight approval fingerprints;
- the complete exported execution plan;
- the exact fixed acknowledgement list.

The request is supplied by an operator. The application does not infer consent
from a plan export or a successful preflight.

## Issuance

Issuance is accepted only in approved common-preflight mode. The CLI:

1. builds the plan from the current explicit command before Host;
2. verifies that both outputs are new workspace descendants;
3. verifies the common-preflight approval before Host;
4. initializes Host and preflights both model plans;
5. refuses issuance unless both preflights pass;
6. rebuilds the proposal from current history;
7. checks the request, proposal, preflight approval, exact plan, and time
   window;
8. persists an immutable approval using no-clobber publication.

Plan-only export is allowed after the same successful approved preflight.

## Consumption

The full Challenger command requires
`--routing-challenger-run-approval-input`. Before Host initialization it:

1. rebuilds the exact plan from the actual command;
2. rechecks output boundaries;
3. rebuilds the current proposal from selected history;
4. validates the approval and exact plan equality;
5. verifies the active time window and current proposal identity;
6. atomically creates
   `.dayu/approvals/challenger-runs/<approval-digest>.consumed.json`.

The hard-link no-clobber operation is the single-use boundary. A second use
returns policy exit code `4`. Consumption is conservative: later Host,
preflight, or write failures do not restore the authorization.

After Host initialization, the CLI rebuilds the plan once more and stops if it
changed before running the normal pair preflight.

## Safety Boundary

- A preflight approval never authorizes model execution.
- A run approval authorizes one Champion run and one Challenger run only.
- Budgets apply independently to each run.
- No receipt changes model configuration or authorizes promotion.
- The Challenger remains isolated and comparison remains advisory.
- SHA-256 fingerprints detect content changes; they are not public-key
  signatures and do not cryptographically authenticate the named operator.
- No credentials, prompts, model responses, or API calls are stored in the
  approval or consumption receipt.

## Failure Semantics

- Policy, history, proposal, time, plan, output, or replay rejection returns
  `4` when represented by a valid but unauthorized receipt.
- Malformed JSON, invalid schema or fingerprint, missing files, invalid plan,
  and persistence errors return `2`.
- Pair preflight failure returns `2` and cannot export or issue a run
  authorization.

## Verification

- plan tests cover template, output, model, execution, and budget binding;
- request tests cover exact fields, acknowledgements, and four-hour validity;
- issuance tests cover successful preflight, current identity, and exact-plan
  equality;
- verification tests cover current, changed plan, stale history, and expiry;
- persistence tests cover immutable no-clobber behavior;
- consumption tests cover atomic one-use semantics;
- CLI tests cover required flag combinations and pre-Host blocking;
- orchestration tests prove authorization precedes Host and pair preflight
  precedes both model runs.
