# Slice 2.3 Item 8 Redis fixture prerequisite — code review acceptance

## Controller decision

- **Work unit**: `Slice 2.3 Item 8 Redis fixture prerequisite`.
- **Gate**: accepted slice checkpoint.
- **Repository / branch**: `/Users/wsk/workspace/dayu-agent` / `codex/investment-platform`.
- **Accepted-plan commit**: `9ad3720b5f3c04fabca1be0602b4b6a79d080f33`.
- **Decision**: `ACCEPTED LOCALLY`.
- **Final open findings**: `H/M/L = 0/0/0`.
- **Boundary**: local prerequisite commit only; no push, PR, merge, Item 8 completion, D0 acceptance, or investment P0/F0 advance.

## Accepted implementation

- Code path: `tests/integration/investment/test_redis_queue_wakeup.py`.
- START: `a1f8691f8cd7773cd9f962121623e6605b7cdd8f0a3ed39abb89a78ff256f460 / 715 / 19783`.
- END: `f8656f9ca1eceb3e63f70ec41df12fb1b8ca39422092a511c13ec8be7fab0d55 / 776 / 22178`.
- Final candidate diff: `26f7cf4e93910be684f925790a570487dcb428f31d48a86f3e2c28b1f852ad46`.

The fixture now removes only the expected JobService enqueue/claim descendants and roots owned by the exact `(_TENANT_UUID, _JOB_TYPE)` identity. Child and root deletes use the same composite owner predicate and the existing definition composite join. Foreign tenant/type roots remain for the real `0006` empty-table admission; unexpected source, schedule, or correlation descendants are not swept and therefore make the root delete fail and roll back the whole cleanup transaction. Production migrations remain unchanged and fail closed.

## Validation evidence

- Redis integration file, one process, exact existing catalog: `3 passed`.
- Pinned PostgreSQL 16 and Redis image identities: present and exact; no pull or network fallback.
- Post-test owner cleanup: `dayu-slice11.owner` and `dayu-slice22.redis-owner` containers/networks all `0/0`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- Ruff default / `F` / `I`: all exit `0`.
- Architecture suite: `171 passed`.
- Exact-three collection, composite owner-predicate static oracle, `git diff --check`, UTF-8, final LF, CR/NUL, allowlist, index and candidate identities: passed.
- README decision: `NO CHANGE`; the public command, test layering and maintenance contract did not change.

The implementation artifact also records a mechanical harness error in which a zsh `path` variable hid `git`; no product gate failed, and the Controller re-dispatched only the mechanical finish. This acceptance does not rewrite that history as a first-run pass.

## Review lineage and findings

1. State/storage initial code review: `PASS`, open `0/0/0` for the first candidate.
2. Domain/ownership initial code review: `FAIL`, `CR-DOM-001` medium — blanket table deletes could erase non-Redis job evidence.
3. Fix round 1: replaced blanket deletion with job-rooted child/root deletion and left cross-domain tables untouched.
4. First re-review: both reviewers found the same remaining owner-key defect; the predicate used `job_type` but omitted tenant identity. Domain marked `CR-DOM-001` partially repaired and state/storage recorded `CRR-SS-001`.
5. Fix round 2: both child and root predicates now bind `_TENANT_UUID` and `_JOB_TYPE`.
6. Final domain re-review: `PASS`, open `0/0/0`, `CR-DOM-001` closed.
7. Final state/storage re-review: `PASS`, open `0/0/0`, `CRR-SS-001` closed.

No finding is rejected or deferred. No unclassified residual risk remains in this prerequisite. The exact-three catalog was intentionally preserved; hostile ownership behavior is proven by the closed SQL predicates, transaction rollback path, executable normal lifecycle, and two independent final re-reviews rather than by adding a fourth catalog test outside the accepted boundary.

## Preserved Item 8 WIP

The following files remained byte-identical through planning, implementation, fixes and reviews, and must remain unstaged in the prerequisite commit:

- `.github/workflows/ci-mainline.yml` = `697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974`.
- `.github/workflows/ci-pr-extended.yml` = `0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199`.
- `tests/README.md` = `798d9983d44f607466d789df8bf35512c39ed0052346c233dbf4274d292441dc / 612 / 133004`.
- `tests/investment/test_platform_migrations.py` = `8bdf6085a2b32d6e510d903fad7d67e7b38c492a15272620a56db8487e6e0101 / 3178 / 109940`.

## Accepted commit allowlist

The local accepted slice commit may stage only:

- the Redis integration test above;
- the implementation artifact;
- both initial code reviews;
- both fix artifacts;
- both first re-review artifacts;
- both final Round 2 re-review artifacts;
- this acceptance artifact.

It must not use `git add -A` or directory staging. After the local commit, the preserved exact-four remains the only working-tree WIP and Item 8 resumes from its remaining aggregate/full validation gate.
