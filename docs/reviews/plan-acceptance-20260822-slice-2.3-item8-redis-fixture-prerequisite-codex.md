# Slice 2.3 Item 8 Redis fixture prerequisite — plan acceptance

## Controller decision

- **Work unit**: `Slice 2.3 Item 8 Redis fixture prerequisite`.
- **Gate**: accepted plan checkpoint.
- **Repository**: `/Users/wsk/workspace/dayu-agent`.
- **Branch / pre-commit HEAD**: `codex/investment-platform` / `71dde28989c315b198318916ad8473512fefa202`.
- **Decision**: `ACCEPTED FOR IMPLEMENTATION`.
- **Open findings**: `H/M/L = 0/0/0`.
- **External actions**: none; this acceptance does not authorize push, PR, merge, or Item 8 completion.

## Accepted target

- Plan: `docs/plans/2026-08-22-slice-2.3-item8-redis-fixture-prerequisite.md` = `987c199fbe843ca59977227127981d2638fa62ea93ecb140fbd3df8d4e251610 / 340 / 25364`.
- Implementation scope: exactly `tests/integration/investment/test_redis_queue_wakeup.py`.
- Implementation baseline: `a1f8691f8cd7773cd9f962121623e6605b7cdd8f0a3ed39abb89a78ff256f460 / 715 / 19783`.
- Non-goals: no migration, production, shared fixture, workflow, README, provider, network, push, or PR change.

The accepted solution preserves the production downgrade safety contract. The Redis-owned database fixture must delete only the current migration chain's true FK descendants required to remove Redis-created jobs, in one bootstrap transaction, before running the real downgrade. It must retain `job_schedule_occurrences` as a possible job descendant and must not delete the unrelated `job_schedules` parent; the existing `0004` admission remains the authoritative cross-domain contamination readback.

## Review lineage

- Initial independent plan review: `docs/reviews/plan-review-20260822-slice-2.3-item8-redis-fixture-prerequisite-state-storage.md`.
- Initial verdict: `FAIL`, fresh `H/M/L = 0/1/0`.
- Accepted finding: `PR-SS-001` — deleting `job_schedules` would erase unrelated schedule-domain evidence before the `0004` fail-closed admission.
- Plan fix: `docs/reviews/plan-fix-20260822-slice-2.3-item8-redis-fixture-prerequisite-codex.md`.
- Re-review: `docs/reviews/plan-rereview-20260822-slice-2.3-item8-redis-fixture-prerequisite-state-storage.md`.
- Final reviewer status: `PR-SS-001-已修复`; verdict `PASS`; fresh open `H/M/L = 0/0/0`.

## Preserved Item 8 WIP

The following paths must remain unstaged and byte-identical throughout the prerequisite implementation and accepted slice commit:

- `.github/workflows/ci-mainline.yml` = `697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974`.
- `.github/workflows/ci-pr-extended.yml` = `0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199`.
- `tests/README.md` = `798d9983d44f607466d789df8bf35512c39ed0052346c233dbf4274d292441dc / 612 / 133004`.
- `tests/investment/test_platform_migrations.py` = `8bdf6085a2b32d6e510d903fad7d67e7b38c492a15272620a56db8487e6e0101 / 3178 / 109940`.

## Implementation entry gate

Before writing, the implementation agent must re-read the accepted plan and verify the branch, accepted-plan commit, empty index, implementation baseline, and all four preserved WIP identities. Any drift or need for a second implementation path is a STOP. After the exact Redis file, Pyright, Ruff, architecture, mechanics, and owner-label cleanup gates pass, implementation must produce its durable artifact and stop for independent code review.

The accepted plan checkpoint stages only this acceptance and the four plan/review artifacts. It explicitly excludes the preserved Item 8 WIP.
