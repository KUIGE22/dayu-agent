# Slice 2.3 Item 8 Redis fixture prerequisite — state/storage plan re-review

## Re-review identity and boundary

- **Role**: fresh independent plan re-reviewer; not writer or Gateflow controller.
- **Current gate**: bounded plan re-review of accepted finding `PR-SS-001` and fix-induced blockers only.
- **Post-fix plan**: `docs/plans/2026-08-22-slice-2.3-item8-redis-fixture-prerequisite.md` = `987c199fbe843ca59977227127981d2638fa62ea93ecb140fbd3df8d4e251610 / 340 / 25364`.
- **Fix artifact**: `docs/reviews/plan-fix-20260822-slice-2.3-item8-redis-fixture-prerequisite-codex.md` = `30b61cc80f747769c0687ea6ebe5b7301aa09a7d22f415f04603827a8e46462d / 54 / 4485`.
- **Source review START**: `docs/reviews/plan-review-20260822-slice-2.3-item8-redis-fixture-prerequisite-state-storage.md` = `a229e11d44b54d8525fcfca59105ffe5f0adba9d47fa981f42cfaf9c8ad1fa8c / 72 / 10604`.
- **Repository identity**: branch `codex/investment-platform`; HEAD `71dde28989c315b198318916ad8473512fefa202`.
- **Redis implementation baseline**: `tests/integration/investment/test_redis_queue_wakeup.py` = `a1f8691f8cd7773cd9f962121623e6605b7cdd8f0a3ed39abb89a78ff256f460 / 715 / 19783`.
- **Boundary observed**: no plan/fix/code/test mutation, implementation, integration test, PostgreSQL, Docker, network, Git mutation, stage, commit, push, PR, or Gateflow action. Persistent writes were limited to the authorized source-review title status and this re-review artifact.

## Accepted finding disposition

### PR-SS-001-已修复-中-删除 `job_schedules` 会绕过 0004 的现成 fail-closed readback

- **Final status**: `已修复 / closed`.
- **Plan fix verified**:
  1. The frozen cleanup tuple at plan lines 103–116 retains `job_schedule_occurrences` and no longer contains `job_schedules`.
  2. Plan line 119 now defines the set as true FK descendants required to delete Redis-owned jobs, explains the optional `job_run_id` edge, excludes the unrelated schedule parent, and assigns parent-row readback to real migration `0004`.
  3. Teardown sequencing, ownership rationale, implementation slice, and independent code-review oracle are synchronized at plan lines 158, 169, 190, and 286.
  4. The source finding title was updated from `未修复` to `已修复`; its evidence and original review conclusion remain historical evidence rather than being rewritten.
- **Real-schema verification**:
  - `0004_durable_schedules.py` defines `job_schedule_occurrences -> job_schedules` and optional `job_schedule_occurrences -> job_runs` restrictive FKs (lines 208–246). Keeping the occurrence in the child-first cleanup remains necessary; deleting the parent is not.
  - The same migration counts `job_schedules + job_schedule_occurrences` before destructive downgrade and fails on any nonzero result (lines 611–642). Leaving `job_schedules` untouched restores the exact hostile counterexample: a schema-valid schedule-parent row remains visible and fails closed.
  - Existing jobs and sources fixture precedents clear `job_schedule_occurrences` but not `job_schedules`, matching the corrected ownership boundary.
- **Count/readback**: no helper-side count is needed. The corrected plan no longer destroys the schedule parent before the authoritative `0004` count, so an extra query would duplicate rather than strengthen that guard.

## Fix-induced blocker scan

- **Second implementation path**: none. The allowlist remains the single Redis integration test file.
- **New helper, schema, or production ownership**: none beyond the already planned local helper and frozen tuple.
- **Migration safety weakening**: none. `0006` remains unchanged; `0004` regains visibility of unrelated schedule-parent rows; cleanup and downgrade errors remain unhandled and fail closed.
- **Stale plan truth**: none found. All remaining `job_schedules` mentions describe exclusion, non-deletion, migration authority, or the code-review oracle. No stale tuple, stale teardown claim, or stale implementation instruction still asks the Redis fixture to delete the parent.
- **Validation overreach**: none. Exact-three single-process integration evidence, static gates, owner-label cleanup, and exact-four preservation remain unchanged; no fourth test, helper count, or second implementation path was introduced.

## Findings

- No open findings. No new blocker was introduced by the accepted fix.

## Open questions

- None.

## Residual risks

- Future migrations can add a new true descendant of job rows; the existing frozen-DAG/code-review oracle remains the correct tracking point.
- This re-review did not execute implementation or tests. Exact-image, exact-three single-process, migration-role-contamination, and owner-label evidence remain mandatory after implementation and are not implied by this plan verdict.

## Final conclusion

- **Verdict**: `pass`.
- **Fresh open findings**: **H/M/L = 0/0/0**.
- `PR-SS-001` is closed. The post-fix plan is handoff-ready for Controller acceptance; this re-review does not itself accept, commit, or advance Gateflow.

## END identity

- **Plan unchanged**: `987c199fbe843ca59977227127981d2638fa62ea93ecb140fbd3df8d4e251610 / 340 / 25364`.
- **Fix artifact unchanged**: `30b61cc80f747769c0687ea6ebe5b7301aa09a7d22f415f04603827a8e46462d / 54 / 4485`.
- **Source review END after authorized title-only status update**: `bae9f0f98cb52e9de1e3fd0932902a5f16601871e236e478f52fe911bbdfc24a / 72 / 10604`.
- **Repository unchanged**: branch `codex/investment-platform`; HEAD `71dde28989c315b198318916ad8473512fefa202`.
- **Redis baseline unchanged**: `a1f8691f8cd7773cd9f962121623e6605b7cdd8f0a3ed39abb89a78ff256f460 / 715 / 19783`.
- **Item 8 exact-four unchanged**:
  - `.github/workflows/ci-mainline.yml` = `697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974`;
  - `.github/workflows/ci-pr-extended.yml` = `0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199`;
  - `tests/README.md` = `798d9983d44f607466d789df8bf35512c39ed0052346c233dbf4274d292441dc / 612 / 133004`;
  - `tests/investment/test_platform_migrations.py` = `8bdf6085a2b32d6e510d903fad7d67e7b38c492a15272620a56db8487e6e0101 / 3178 / 109940`.
