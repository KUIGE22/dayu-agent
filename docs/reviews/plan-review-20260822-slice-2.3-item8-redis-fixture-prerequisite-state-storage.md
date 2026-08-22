# Slice 2.3 Item 8 Redis fixture prerequisite — state/storage plan review

## Review identity and scope

- **Role**: independent read-only plan reviewer; not writer or Gateflow controller.
- **Reviewed target**: `docs/plans/2026-08-22-slice-2.3-item8-redis-fixture-prerequisite.md`.
- **START identity**: `8bfe0b0b693be2c5ad013bc7e05e8ae4f36189490c8411a752c07b8aec39f49d / 341 / 24559`.
- **Repository identity**: branch `codex/investment-platform`; HEAD `71dde28989c315b198318916ad8473512fefa202`.
- **Implementation target baseline**: `tests/integration/investment/test_redis_queue_wakeup.py` = `a1f8691f8cd7773cd9f962121623e6605b7cdd8f0a3ed39abb89a78ff256f460 / 715 / 19783`.
- **Preserved Item 8 WIP**:
  - `.github/workflows/ci-mainline.yml` = `697a257de626e6f92515ebe1b13d6cee425ab2c1b6368c4b6b6b17e1b433302d / 288 / 9974`;
  - `.github/workflows/ci-pr-extended.yml` = `0c678198394999abf02e3a3779b22492d9ad8b4bc7d76ccb36cde44fa662f770 / 198 / 7199`;
  - `tests/README.md` = `798d9983d44f607466d789df8bf35512c39ed0052346c233dbf4274d292441dc / 612 / 133004`;
  - `tests/investment/test_platform_migrations.py` = `8bdf6085a2b32d6e510d903fad7d67e7b38c492a15272620a56db8487e6e0101 / 3178 / 109940`.
- **Inspection boundary**: plan, Redis integration fixture, real migration chain `0001/0003/0004/0005/0006`, PostgreSQL lifecycle fixture, and schedules/sources/jobs cleanup precedents. No implementation, integration test, PostgreSQL, Docker, network, stage, commit, push, PR, or Gateflow action was performed.

## Assumptions tested

1. **Motivation/root cause is supported.** The Redis fixture currently calls `run_alembic_downgrade()` directly after the tests. The second test enqueues and claims two jobs. `0006_job_request_identity.downgrade()` locks/catalog-checks and then rejects any nonempty `job_runs` table before destructive DDL. Because the migration chain then never reaches `0001`, its cluster-global app/audit roles remain and the next function database cannot recreate them.
2. **One implementation file is sufficient.** The migrated database fixture already owns the exact database name, bootstrap DSN, upgrade, and downgrade responsibility. A local helper in `test_redis_queue_wakeup.py` can clean test-owned job rows without modifying migrations, production code, shared fixtures, workflows, or the preserved Item 8 exact-four.
3. **The proposed ordering is FK-safe but the set is not ownership-minimal.** In the real schema, source durable rows, schedule occurrences, attempt receipts, leases, events, and correlations can precede `job_attempts`/`job_runs`; the proposed child-first order satisfies those FKs. `job_schedule_occurrences` references both `job_schedules` and optionally `job_runs`. In contrast, `job_schedules` references no Redis-owned job row and is not a descendant that must be removed to delete Redis-created jobs.
4. **Migration admissions remain the authoritative post-commit checks only for rows left for them to inspect.** `0006` reads `job_runs`; `0005` rejects its three new tables and durable source fields; `0004` explicitly counts both schedule tables; `0003` checks external dependencies before dropping its seven tables; `0001` checks members, sessions, and external shared dependencies before dropping schema and roles. A helper that deletes an unrelated schedule parent before `0004` prevents that admission from observing it.
5. **Transaction and engine sequencing is otherwise implementable.** A bootstrap `Engine`, one `engine.begin()` transaction, original SQLAlchemy errors, and `dispose()` in `finally` are consistent with `create_platform_engine()` and project fixtures. Successful transaction exit commits before Alembic opens the downgrade path.
6. **Login/role/database/container lifecycle is coherent.** The dependent `job_runtime` finalizer closes the Redis publisher, disposes the app engine, and drops the temporary LOGIN/membership before the migrated database finalizer runs. The latter can then clean and downgrade; `lifecycle_database` FORCE-drops the random database afterward. Redis and PostgreSQL containers/networks have independent exact-owner cleanup and the plan does not depend on sibling fixture teardown order.
7. **The validation gate correctly preserves contamination evidence.** One full-file pytest process with exact three collected tests is necessary: isolated tests or a successful rerun could hide the second-test teardown failure and third-test role collision. Static/type/lint/architecture checks and exact owner-label zero readbacks are appropriately separate.
8. **Review/commit separation and WIP staging are mechanically separable.** START index was empty; tracked working-tree changes were exactly the preserved exact-four and the plan was the sole untracked path. Explicit path staging can exclude the exact-four; `git add -A` and directory staging are correctly forbidden.

## Findings

### PR-SS-001-已修复-中-删除 `job_schedules` 会绕过 0004 的现成 fail-closed readback

- **位置**: §4.1 lines 103–120, §4.2 line 139, §4.4 line 159, §5.1, and S23-I8-RFP-01.
- **问题类型**: 范围漂移 / 架构边界 / 最佳实践偏离 / 测试缺口.
- **当前写法**: The frozen cleanup tuple ends with `job_schedules`, and the plan describes all listed tables as dependent tables needed to close the current migration chain. It also rejects a separate count/readback because the following migration admissions are said to be authoritative.
- **反例/失败场景**: A schema-valid regression or future Redis-path side effect inserts one `job_schedules` row with no occurrence. The proposed bootstrap sweep deletes that unrelated parent row, `0004` subsequently observes `0 + 0` schedule rows, and the exact-three full-file gate passes. Without the `job_schedules` DELETE, the real `0004` admission deterministically raises `downgrade 拒绝：0004 durable schedules 仍存在业务行`, exposing the cross-domain write at the owning boundary.
- **为什么有问题**: Redis tests only call JobService enqueue/claim. `job_schedules` is not an FK descendant of `job_runs` or `job_attempts`; only `job_schedule_occurrences` points from the schedules domain into both the schedule parent and an optional job run. Sweeping the parent therefore expands this Redis fixture's ownership and weakens the plan's own claim that migration fail-closed checks are the authoritative readback. The project-local jobs and sources fixtures clear `job_schedule_occurrences` as a possible job descendant but do not clear `job_schedules`; only the schedule-owned fixture deletes that parent.
- **直接证据**:
  - `0004_durable_schedules.py` defines occurrence FKs to `job_schedules` and `job_runs`, while `job_schedules` has no reverse dependency on Redis-owned job rows (lines 208–246).
  - The same migration counts `job_schedules + job_schedule_occurrences` and rejects any nonzero result before destructive DDL (lines 611–642).
  - `test_postgres_jobs.py::_downgrade_after` and `test_postgres_sources.py::source_harness` clear possible job descendants including `job_schedule_occurrences` but leave `job_schedules` for `0004` admission; `test_postgres_schedules.py::schedule_db` deletes the parent because that suite actually owns schedule rows.
  - The reviewed plan itself states that Redis currently creates only job rows (line 120).
- **影响**: A material cross-domain side effect can be erased before the migration guard sees it, so the validation lane may report `3 passed` while the Redis job path has silently acquired schedule-domain mutation. It also couples this fixture to a parent table it does not own and makes future cleanup-table growth easier to justify without an ownership proof.
- **建议改法和验证点**:
  1. Remove `job_schedules` from `_MIGRATED_DATABASE_CLEANUP_TABLES` and update §4.1/§4.4/§5.1 to describe the tuple as FK descendants required to delete Redis-owned jobs, not every migration business table.
  2. State explicitly that `0004`'s existing two-table count is the authoritative zero readback for the unrelated schedule parent. No duplicate helper-side count is needed after the parent DELETE is removed.
  3. Add a review oracle that the Redis cleanup tuple must not contain `job_schedules`; retain `job_schedule_occurrences` before `job_runs` because it is a real optional FK descendant.
- **修复风险（低/中/高）**: 低.
- **严重程度（低/中/高/严重）**: 中.

## Open questions

- None. The finding has a bounded documentation-only correction and does not require a second implementation file or a migration change.

## Residual risks

- A future migration may add another true FK descendant of job rows. The plan already assigns synchronization of lifecycle fixtures to that future migration owner; code review must still compare the tuple against the frozen current migration DAG.
- A setup-phase failure before `job_runtime` reaches its `yield` can expose pre-existing partial-resource cleanup behavior. This prerequisite is intentionally scoped to the reproduced post-yield teardown failure; such a distinct failure must remain visible rather than be converted to a skip or broad role cleanup.
- No integration execution was performed in this plan-review lane. The plan's exact-image, exact-three single-process, role-contamination, and owner-label gates remain mandatory implementation evidence.

## Final conclusion

- **Verdict**: `fail`.
- **Fresh open findings**: **H/M/L = 0/1/0**.
- The root cause, unique-file implementation boundary, child-first FK order, transaction/engine/login/database/container lifecycle, three-test gate, and WIP staging separation are otherwise handoff-ready. The plan must first remove the unrelated `job_schedules` parent from the Redis cleanup ownership boundary and then receive a fresh independent re-review with open H/M/L `0/0/0`.

## END identity

- **Reviewed plan unchanged**: `8bfe0b0b693be2c5ad013bc7e05e8ae4f36189490c8411a752c07b8aec39f49d / 341 / 24559`.
- **Repository unchanged**: branch `codex/investment-platform`; HEAD `71dde28989c315b198318916ad8473512fefa202`.
- **Redis implementation baseline unchanged**: `a1f8691f8cd7773cd9f962121623e6605b7cdd8f0a3ed39abb89a78ff256f460 / 715 / 19783`.
- **Preserved Item 8 WIP unchanged**: exact-four identities equal START (`697a257d… / 288 / 9974`; `0c678198… / 198 / 7199`; `798d9983… / 612 / 133004`; `8bdf6085… / 3178 / 109940`).
- **WIP boundary**: index empty; tracked working-tree mutations remain exactly the preserved exact-four; untracked paths are exactly the reviewed plan and this required review artifact.
