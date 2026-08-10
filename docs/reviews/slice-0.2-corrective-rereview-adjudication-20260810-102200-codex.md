# Slice 0.2 corrective re-review adjudication

- Work unit: `investment-platform-restoration`
- Branch: `codex/investment-platform`
- Base / predecessor accepted commit: `d5f024d`
- Terra re-review: `docs/reviews/code-rereview-20260810-101622-slice-0.2-terra.md`
- MiM Native re-review: `docs/reviews/code-rereview-20260810-101856-slice-0.2-mimo-native.md`
- Prior adjudication: `docs/reviews/slice-0.2-code-review-adjudication-20260810-094100-codex.md`
- Status: **CLOSED / DUAL RE-REVIEW PASS**

## Controller dispositions

| Finding | Disposition | Required closure |
| --- | --- | --- |
| Terra 001 unknown profile echoes candidate | **ACCEPTED / MEDIUM** | `load_platform_settings()` must reject unknown deployment profiles with a stable message naming `DAYU_PLATFORM_PROFILE` and the accepted values, without formatting the candidate. Add DSN-, auth-token-, and provider-key-shaped profile redaction cases that assert the original value is absent from the exception. |
| Terra 002 public `PlatformSettings` runtime boundary is not strict | **ACCEPTED / MEDIUM** | At the single `validate()` boundary, require exact `bool` for `enabled` and `use_in_memory_adapters`, require `PlatformDeploymentProfile` for `profile`, and require each infrastructure env-name to be `str | None` before regex matching. Every failure must use a stable message without candidate values. Add direct-constructor adversarial tests for `1`, `"yes"`, unknown string profiles, and non-string env-name values. |
| MiM Native PASS | **INSUFFICIENT TO CLOSE / NO NEW FINDING** | MiM verified the original accepted findings but did not exercise the two public settings counterexamples found by Terra. Its PASS remains valid for the covered boundaries but cannot override the reproducible open findings. |

## Scope decision

Both accepted findings are implementation defects inside the already accepted Slice 0.2
strict-settings contract. They require only `dayu/investment/config.py`,
`tests/investment/test_platform_config.py`, and Gateflow artifacts. No plan change,
new dependency, future repository, compatibility adapter, or README design expansion is
authorized. Existing README text becomes accurate once the fixes land.

## Required validation

- Focused Slice 0.2 tests and direct adversarial constructor/profile tests.
- Exact pyright for changed production/tests.
- Ruff F/I and default rules for changed Python files.
- Cold-import smoke and `git diff --check`.
- A fresh dual corrective re-review; both reviewers must report PASS with open H/M/L
  `0/0/0` before the accepted local commit.

## Current open count

Open H/M/L = **0/2/0**. Slice 0.2 is not accepted and Slice 1.1 must not start.

No commit, push, PR, network, live model, or broker action is authorized by this
adjudication.

## Round 3 final-review disposition

- Terra final review:
  `docs/reviews/code-rereview-20260810-102450-slice-0.2-terra-final.md`
  reports FAIL, open H/M/L `0/1/0`.
- MiM Native final review:
  `docs/reviews/code-rereview-20260810-102450-slice-0.2-mimo-native-final.md`
  reports PASS, but only inspected `str(error)` and therefore does not close Terra's
  reproducible traceback-level leak.
- Terra 001 round3 is **ACCEPTED / MEDIUM**: the stable top-level error still uses
  `raise ... from error`, so `traceback.format_exception()` includes the original
  secret-shaped enum candidate from `ValueError`. The minimum required fix is to
  suppress that untrusted cause (`from None`) and add DSN/auth/provider-key tests that
  assert the candidate is absent from `str(error)` and the complete formatted traceback,
  and that `error.__cause__ is None`.
- Round3 open H/M/L is **0/1/0**. All prior findings remain closed unless the fix
  regresses them. A fresh final dual re-review is still mandatory before commit.

## Final closure

The required round3 fix was independently verified by both final closure reviews:

- `docs/reviews/code-rereview-20260810-103114-slice-0.2-terra-closure.md`
- `docs/reviews/code-rereview-20260810-103114-slice-0.2-mimo-native-closure.md`

Both report PASS with open H/M/L **0/0/0**. All findings in this adjudication are
CLOSED; Slice 0.2 is ready for its accepted local commit.
