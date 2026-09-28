# Code Review — S31-A three-finding rereview

## Findings

Fresh open H/M/L: **0/0/0, PASS for the three named fixes only**. No new actionable finding arose from the bounded rereview. This does not upgrade the whole S31-A or later S31-B to Gate acceptance.

## Scope and frozen identity

- Mode: independent, nonauthor, read-only rereview of the three findings in `docs/reviews/code-review-20260927-215415-s31-a-final.md` (SHA-256 `5402722dc48cfb5434ec05525d202841067166770ad0529f5033bf0b8b594baa`). Repository HEAD `b6444ae16aa524a717e396160bacc855faa2049f`, branch `codex/investment-platform`; target is uncommitted S31-A disk, not a branch-wide review.
- Accepted V9: `docs/plans/2026-09-27-slice-3.1-strict-evidence.md` SHA-256 `d3b658297a75c21a74b821f63166b3ccbf41762f56cf0d21123ff7ad686b59e2`.
- Changed target identities, all LF-terminated:

| Path | SHA-256 | Bytes | LF |
| --- | --- | ---: | ---: |
| `dayu/investment/domain/evidence.py` | `76b09d0909a2ee989a0c880ae39c2bf5fe3717b21804c16f0ba187ae249d5a9d` | 75957 | 2320 |
| `tests/investment/test_evidence_domain.py` | `cd2f599472d905e63c2c976aad3ee0bf9024053de7438724327694a6186b6955` | 28813 | 812 |
| `tests/integration/investment/test_postgres_evidence.py` | `4ce4951e8e83f3440908eae98736d1d7cbaeec33ec4d3d90fb0ce9907e626158` | 29337 | 554 |

- Read-only corroborating identities: `dayu/investment/storage/models_evidence.py` SHA-256 `3462acfccb745b8f04f3112ae71f51a190327c8eb7f730c2adbfb467958b0791`; `dayu/investment/storage/migrations/versions/0007_strict_evidence.py` SHA-256 `640e4101c61004ee115b7f7ed66303168fe11fb78c704fc37f14994277f8bd52`; `dayu/investment/storage/_evidence_review_auth.py` SHA-256 `08c239848fd82f125dc5159bbcb3d91dbfcbb8a0c904f16753146d59f1a50e06`.

## Rereview decisions

1. **Reviewer witness reconstruction mismatch: fixed at the structural contract.** `ReviewWitness` at `dayu/investment/domain/evidence.py:1650-1685` now contains `reviewer_user_id`, `reviewer_token_id`, `user_role_id`, `role_permission_id`, `permission_id`, permission key, check time, policy and reason; it no longer requires `role_id`. These fields correspond to the immutable columns in `ClaimVersionRow` and `ClaimConflictRow` at `models_evidence.py:162-171,252-261`. The auth helper may still return `role_id` for its current authentication result; the durable domain projection does not require that revocable row. `test_evidence_domain.py:683-706` constructs both review fields and rejects zero grant IDs. Historical readback after grant deletion awaits S31-B repository tests; this rereview proves field-level reconstructability, not an implemented readback path.
2. **Fact PIT single-sided period: fixed.** `FactPitTimes.__post_init__` at `domain/evidence.py:925-935` rejects exactly one NULL period endpoint before range comparison, matching `ck_facts_period_shape` in 0007. `test_evidence_domain.py:336-354` covers both missing-start and missing-end cases, both NULL, valid range, reversed range and time checks. The period validator leaves the separately specified `effective_at` independence intact.
3. **0007 downgrade NOWAIT PG acceptance: fixed and executed.** `test_postgres_evidence.py:113-139` holds `ACCESS SHARE` in a second connection, separately on `facts` and `securities`, while the Alembic connection downgrades 0007. It asserts SQLSTATE `55P03`, elapsed time below 3 seconds, unchanged Alembic revision, table and securities constraint; after releasing each blocker, the same test completes empty `downgrade -1` and `upgrade head`. Production `_preflight_downgrade` at `0007_strict_evidence.py:550-572` uses `ACCESS EXCLUSIVE MODE NOWAIT` in that path. The targeted PostgreSQL 16 test passed in this rereview.

## Verification actually run

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest tests/investment/test_evidence_domain.py -q` | 38 passed |
| `.venv/bin/python -m pytest tests/integration/investment/test_postgres_evidence.py::test_0007_empty_upgrade_downgrade_upgrade -q -m integration --timeout=120` | PostgreSQL 16: 1 passed (3.57 s) |
| `.venv/bin/pyright --pythonpath .venv/bin/python dayu/investment/domain/evidence.py tests/investment/test_evidence_domain.py tests/integration/investment/test_postgres_evidence.py` | 0 errors, 0 warnings |
| `.venv/bin/ruff check dayu/investment/domain/evidence.py tests/investment/test_evidence_domain.py tests/integration/investment/test_postgres_evidence.py` | all checks passed |
| fallback Git `git diff --check` | pass |

Pytest used the pinned fallback Git directory first in `PATH` because `/usr/bin/git` is blocked by the host Xcode license prompt. No credential was read or printed. No production file, test file, plan or prior review was changed by this reviewer.

## Open Questions

None for these three repairs. S31-B must still demonstrate actual repository persistence/readback after grant revocation and the V9 transaction/CAS behaviors when implemented.

## Residual Risk and boundary

This is not a repeat of the whole 13-path S31-A review. Other S31-A schema, ORM, ACL, RLS, locator and decimal paths retain their prior independent review evidence; this turn did not rerun the full PG migration suite, full unit suite or all repository behavior. Fins freshness belongs to Slice 3.2 and the ten-shape recursive closure remains a separate OPEN track. No commit, stage, Gate grant or trading action occurred.
