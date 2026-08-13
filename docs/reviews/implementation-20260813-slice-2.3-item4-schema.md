# Slice 2.3 Item 4 schema implementation evidence

Date: 2026-08-13

Repository: `/Users/wsk/workspace/dayu-agent`

Branch: `codex/investment-platform`

Baseline/HEAD: `595564ebcbd398fb84a4eab21e0cd9e045f56dd5`

Accepted plan: `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
Gate: Slice 2.3 Item 4 only; this artifact does not claim an independent review pass.

## Scope and changed paths

The implementation stayed inside the Item 4 allowlist. `postgres_identity.py`,
`tests/investment/test_identity_repositories.py`, storage exports/protocols,
database/session fixtures, migrations 0001--0004, and all Item 1--3/source
repository/service/startup paths have zero diff.

Production changes:

- `dayu/investment/storage/migrations/versions/0005_source_connectors_health.py`
- `dayu/investment/storage/models_identity.py`
- `dayu/cli/workspace_migrations/platform_jobs.py`

Owner-test changes:

- `tests/investment/test_platform_migrations.py`
- `tests/integration/investment/test_platform_migrations_postgres.py`
- `tests/integration/investment/test_identity_repositories_postgres.py`
- `tests/cli/workspace_migrations/test_platform_jobs.py`

Evidence-only change:

- `docs/reviews/implementation-20260813-slice-2.3-item4-schema.md`
- `docs/reviews/code-review-20260813-104658.md` (status metadata only)
- `docs/reviews/fix-20260813-slice-2.3-item4-schema.md`

No file was staged, committed, pushed, or submitted as a PR.

## Implemented DDL, ORM, guards, and catalog contract

- Added Alembic revision `0005_source_connectors_health`, down-revision
  `0004_durable_schedules`. A real PostgreSQL upgrade moves the platform catalog
  from 24 to 27 tables, and the exact downgrade returns it to 24.
- Added `source_sync_operations`, `source_health_states`, and
  `source_health_alert_outbox` with the accepted columns, types,
  nullability/defaults, PK/UQ/index/check/FK names, ordered composite lineage,
  and `RESTRICT` actions. The outbox timestamp and health-state version retain
  the required no-default semantics.
- Extended `source_sync_runs` by exactly 14 nullable/no-default columns, the
  three v1 closed-shape checks, three parent uniques, two partial uniques, and
  the strong `(tenant_id, job_run_id, job_attempt_id)` attempt lineage.
- Extended `source_health_snapshots` with the nullable/no-default
  `health_state_version`, v2 closed-shape check, two parent uniques, one partial
  unique, and the strong tenant/subscription/run FK. Upgrade validates the
  strong FK before removing the legacy weak FK.
- Replaced the three subscription partial unique indexes in place so tenant,
  company, and security target identities all include `source_definition_id`.
- Kept `PlatformBase.metadata` at exactly 18 mapped tables. Raw jobs/schedules
  are absent. The two ORM attempt-lineage FKs use actual `Column` objects from a
  private independent `_RAW_REFERENCE_METADATA`; raw `job_attempts` is neither
  mapped, exported, added to platform metadata, nor reachable by `create_all`.
- Added the exact 11 PL/pgSQL functions and 11 trigger bindings: four initial
  insert guards, three append-only guards, two transition guards, and two
  delete guards. The operation and health-head state machines enforce closed
  transitions, monotonic generation/version/time, immutable identity/payload,
  exact lineage, and null-safe comparisons.
- Added tenant-isolation RLS with `ENABLE` and `FORCE` only to the three new
  tables. App/audit/PUBLIC grants match the accepted table- and column-level
  matrix; existing run/snapshot RLS and grants remain untouched.
- Upgrade performs a single-transaction lock and fail-closed preflight before
  mutation. It distinguishes new-absent names from the three baseline-present
  subscription indexes and compares the exact 21-policy manifest, full
  owner/app/audit relation ACL set, and all explicit column ACL tuples.
  Same-count policy, table SELECT-to-DELETE, and column status-to-id
  substitutions, PUBLIC column grants, or grants to another role all fail
  before the first 0005 mutation.
- Downgrade starts with one seven-table `ACCESS EXCLUSIVE NOWAIT` request and
  requires READ COMMITTED before any catalog/data/dependency read. A busy
  runtime writer therefore fails immediately without entering either a
  repository parent-first or direct-DML child-first lock wait graph. If all
  locks are obtained, they remain held by the same Alembic transaction through
  reverse DDL and the revision update.
- The 0005 self-check compares all 51 constraint identities and all 28 physical
  index definitions across the five affected tables, not only known names. It
  also compares nine CHECK definitions through PostgreSQL's deparser and all
  11 non-internal affected-table triggers by name/table/function
  schema/function name/event bitmap/enabled state. Arbitrary extra CHECK,
  index, or trigger objects therefore fail closed instead of being implicitly
  removed by `DROP TABLE` or `DROP COLUMN`.
- The same terminal self-check expands every relation ACL and explicit column
  ACL on the three new tables through `aclexplode`, without filtering grantee,
  privilege, or grant option. It compares the exact 30-row owner/app/audit
  relation set and exact 14-row app column-UPDATE set. Extra roles, PUBLIC
  column grants, extra privileges, and `WITH GRANT OPTION` therefore fail
  before destructive downgrade DDL.
- After catalog proof, downgrade rejects new business rows, populated added
  columns, legacy-index conflicts, or external view/role dependencies. It
  revokes/drops in exact reverse order without `CASCADE`, recreates and
  validates the weak snapshot FK before dropping the strong FK, drops partial
  indexes before their columns, and self-checks the restored 24-table
  catalog/ACL/RLS state.
- Updated the workspace migration head documentation to include 0005. No Item
  5 source repository/state-machine implementation was added.

## PostgreSQL candidate history

Failed development candidates are retained as evidence; later success does not
rewrite or mask them.

1. Pre-freeze development attempt: 29 passed, 24 failed. The first failure was
   an intermediate-0001 test incorrectly expecting the expanded 27-table head
   and not excluding the three new tables; it failed before cleanup and caused
   23 `role dayu_platform_app already exists` cascades. This was not a frozen
   candidate, no candidate SHA was recorded, and there is no complete durable
   tee/JUnit/exit evidence bundle. It is development history, not gate evidence.
2. Candidate 2: migration SHA `4f372101...`, PG-owner SHA
   `1832115866bf7dc1f5312794f7d2fcd63f80186151b04b3f507fc3ff24620261`;
   exit 1, 44 passed, 9 failed. First cause was an
   `execution_options(AUTOCOMMIT)` call after SQLAlchemy autobegin, followed by
   eight role-cleanup cascades. The exact pytest completion output was not
   durably captured and was reconstructed fail-closed from the available
   terminal/coverage evidence; its 93.2249% coverage is failed-candidate data,
   not final evidence.
3. Candidate 3: migration SHA `4f372101...`, PG-owner SHA
   `6e16738b7538752bc52198bf4150255d5d9765603d3d116b431b4a560d0aa6c1`;
   exit 1, 45 passed, 8 failed. A second repeated-autocommit path failed, then
   seven role cascades. `/tmp/dayu-s23-item4-candidate3.GEP4mn` retained only a
   partial evidence set rather than the final required tee/JUnit/exit bundle;
   it is not gate-quality evidence.
4. Candidate 4: migration SHA `4f372101...`, PG-owner SHA
   `919929a3dc74603b2950fb2b5fa2f03484f1bcfc24eea7a21db5a65d48892ecf`;
   exit 1, 52 passed, 1 failed. The single failure correctly rejected a terminal
   update whose hard-coded `updated_at` preceded the insert's default timestamp.
   Evidence: `/tmp/dayu-s23-item4-candidate4.jf4ml9`.
5. Candidate 5: migration SHA `4f372101...`, PG-owner SHA
   `63b969c1b4c1aad4ee68196ee9ecdd2ec429022f23a072e1554d743d8f588886`;
   exit 1, 52 passed, 1 failed. The first test hit a host-side bootstrap
   `OperationalError` after container-internal readiness; the remaining 52
   tests passed. Evidence: `/tmp/dayu-s23-item4-candidate5.IZTN3r`.
6. Candidate 6 added a module-scoped, test-only host SQL readiness barrier. It
   makes exactly three attempts, creates a fresh engine with
   `connect_timeout=1` for each `SELECT 1`, always disposes it, catches only
   `OperationalError`, propagates other database errors immediately, uses no
   sleep, and raises a sanitized `PlatformIntegrationError` after exhaustion.
   Unit fakes cover two failures then success, three failures, and immediate
   `ProgrammingError`. The function-scoped fail-safe reaper and its lifecycle
   teardown ordering remain unchanged.
7. Candidate 6 then passed its historical migration owner lane: 53 passed and
   raw migration coverage 93.22493224932249%. The subsequent formal review
   accepted five findings, so those successful bytes are superseded. They do
   not prove the corrective production/test candidate.
8. Corrective Candidate 7 implements all accepted H1/H2/M1/M2/M3 findings.
   Its migration/PG-owner/unit-owner SHA triple is
   `1bb85da9...` / `fe0cc539...` / `8cec523c...`. Independent M3 catalog review
   passed on that exact triple. Its authorized once-only owner lane collected
   56 tests and ended exit 1: 3 passed / 53 failed in 63.04s. The first and all
   53 failures were the same production preflight error, `baseline column ACL
   exact manifest 漂移`; there was no later role-cleanup cascade. Evidence:
   `/tmp/dayu-s23-item4-pg-candidate.fnZSCm`.
9. A separate pinned disposable diagnostic upgraded only through 0004 and
   queried `pg_attribute.attacl` through `aclexplode`. It proved exactly 37
   rows, all `(dayu_platform_app, UPDATE, is_grantable=false)`, and no implicit
   owner table rights materialized as per-column ACL entries. Evidence:
   `/tmp/dayu-s23-item4-acl-diagnostic.KCKt7h`; the diagnostic downgraded and
   left no pinned-image container.
10. Candidate 8 removes only Candidate 7's invented owner column-ACL tuples and
    adds an AST guard that freezes explicit-`attacl` semantics. Its
    migration/PG-owner/unit-owner triple is `a5cbcac7...` / `5eb7fbb7...` /
    `d9e494a2...`. Independent M3+ACL incremental review passed the frozen
    Candidate 8 bytes. Its authorized migration owner then passed 56/56, and
    the separately authorized plain identity owner passed 17/17.
11. Candidate 8 re-review artifact
    `docs/reviews/code-review-20260813-item4-schema-candidate8.md`, immutable
    SHA `0c0c833f...`, found one accepted medium issue: the terminal 0005 ACL
    self-check filtered known grantees and discarded grant-option identity.
    Candidate 9 replaces it with complete `relacl`/`attacl` exact sets and
    extends the independent PG oracle plus four fail-closed ACL drifts. Its
    frozen migration/PG-owner/unit-owner triple is `90b66245...` /
    `1ea9b84c...` / `5595d2b2...`. A separate read-only ACL audit passed these
    exact bytes. Its subsequently authorized once-only migration owner passed
    56/56 with raw exact-singleton migration coverage
    `94.46902654867256`; Candidate 8 evidence was not reused to prove it.

## Historical Candidate 8 PostgreSQL evidence

Pinned image inspection immediately before each Candidate 8 lane resolved
exactly:

```text
["postgres@sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8"]
```

The once-only Candidate 8 migration-owner evidence directory is
`/tmp/dayu-s23-item4-pg-candidate8.gBNdYO`. The exact process was:

```text
PYTHONDONTWRITEBYTECODE=1 COVERAGE_FILE=<evidence>/.coverage \
  .venv/bin/python -m coverage run --branch \
  --include=dayu/investment/storage/migrations/versions/0005_source_connectors_health.py \
  -m pytest -p no:cacheprovider -m integration --timeout=120 \
  --junitxml=<evidence>/junit.xml \
  tests/integration/investment/test_platform_migrations_postgres.py
```

Result: exit 0, **56 passed in 83.33s**; it was not followed by a plain rerun.
JUnit reports 56 tests, zero failures/errors/skips. The same coverage data has
`branch_coverage=true`, exact singleton
`dayu/investment/storage/migrations/versions/0005_source_connectors_health.py`,
371 statements, 357 covered lines, 14 missing lines, 78 branches, 63 covered
branches, 15 missing branches, and raw combined coverage
**93.54120267260579%**. JSON/shape/report exit codes are all zero. Pre/post
migration/PG-owner/unit-owner hashes match and no pinned-image container
remained.

The Candidate 8 identity evidence directory is
`/tmp/dayu-s23-item4-identity-c8.uC3QFD`. Because the test changed while
`postgres_identity.py` remained zero diff, its exact plain owner command ran
once:

```text
.venv/bin/python -m pytest -p no:cacheprovider -m integration --timeout=120 \
  tests/integration/investment/test_identity_repositories_postgres.py
```

Result: exit 0, **17 passed in 24.11s**. JUnit reports zero
failures/errors/skips; pre/post test and production hashes match, the production
file remains zero diff, and no pinned-image container remained.

## Candidate 9 current validation evidence

The Candidate 9 migration-owner evidence directory is
`/tmp/dayu-s23-item4-pg-candidate9.BRYp5m`. A fresh read-only local image
inspection resolved exactly the accepted pinned digest, and prehash confirmed
the frozen migration/PG-owner/unit-owner triple. The only pytest process was:

```text
PYTHONDONTWRITEBYTECODE=1 COVERAGE_FILE=<evidence>/.coverage \
  .venv/bin/python -m coverage run --branch \
  --include=dayu/investment/storage/migrations/versions/0005_source_connectors_health.py \
  -m pytest -p no:cacheprovider -m integration --timeout=120 \
  --junitxml=<evidence>/junit.xml \
  tests/integration/investment/test_platform_migrations_postgres.py
```

Result: exit zero, **56 passed in 111.46s**. It was not followed by a plain or
second pytest run. JUnit reports 56 tests and zero failures/errors/skips. The
same coverage data reports `branch_coverage=true`, exact singleton migration
file, 374 statements, 362 covered lines, 12 missing lines, 78 branches, 65
covered branches, 13 missing branches, and raw combined coverage
**94.46902654867256%**. Coverage JSON/shape/report exits are zero. Pre/post
frozen hashes match, resolved digest remains exact, and pinned-ancestor
container cleanup is empty.

Candidate 9 refreshed model coverage with the exact singleton include and the
model owner plus the unchanged identity unit coverage input:

```text
COVERAGE_FILE=/tmp/dayu-s23-item4-models-c9.eYa6yw/.coverage \
  .venv/bin/python -m coverage run --branch \
  --include=dayu/investment/storage/models_identity.py -m pytest \
  -p no:cacheprovider tests/investment/test_platform_migrations.py \
  tests/investment/test_identity_repositories.py
```

Result: **77 passed in 4.87s**. The durable evidence directory is
`/tmp/dayu-s23-item4-models-c9.eYa6yw`; run/json/shape/report exit codes
are all zero. JSON reports `branch_coverage=true`, exact singleton
`dayu/investment/storage/models_identity.py`, 174/174 statements, and raw
combined coverage **100.0%**.

Fresh CLI coverage used the exact singleton owner tuple:

```text
COVERAGE_FILE=/tmp/dayu-s23-item4-cli-coverage.p9WBCS/.coverage \
  .venv/bin/python -m coverage run --branch \
  --include=dayu/cli/workspace_migrations/platform_jobs.py -m pytest \
  -p no:cacheprovider tests/cli/workspace_migrations/test_platform_jobs.py
```

Result: **6 passed in 1.42s**. The durable evidence directory is
`/tmp/dayu-s23-item4-cli-coverage.p9WBCS`; run/json/shape/report exit codes are
all zero. JSON reports `branch_coverage=true`, exact singleton
`dayu/cli/workspace_migrations/platform_jobs.py`, 30/30 statements, 6/6
branches, and raw combined coverage **100.0%**.

## Other validation

- Focused unit plus CLI owner command: **48 passed in 2.55s**.
- Models exact-owner coverage command: **77 passed in 4.87s**.
- CLI exact-owner coverage command: **6 passed in 1.42s**.
- Integration collect-only: exactly **73 tests**: 56 migration owner and 17
  identity owner; collect-only did not start Docker or PostgreSQL.
- Setup plan proves session cluster, then module host-readiness, then function
  database/reaper/lifecycle; teardown is lifecycle, reaper, database, module
  readiness, then cluster.
- Pyright on all seven changed production/test paths: 0 errors, 0 warnings,
  0 informations.
- Ruff default and `--select F,I` on all seven paths: all checks passed.
- `git diff --check`: passed. All changed Python files are UTF-8/LF and have a
  final newline. Index is empty; branch and HEAD remained exact.
- Candidate 9's complete once-only PostgreSQL migration owner passed on the
  independently reviewed ACL bytes. Candidate 8's pass was not reused as
  current proof.
- Static acceptance covers exact 27-table catalog and 18-table ORM metadata,
  manifest presence/absence, 14+1 column shape, parent-before-child and reverse
  downgrade ordering, partial predicates, 63-byte identifiers, closed
  run/head/snapshot/outbox checks, strong snapshot lineage, full baseline
  security identities, all affected constraints/indexes/triggers, and the
  NOWAIT/READ COMMITTED downgrade gate. Candidate 9's fresh real-PG owner lane
  passed.
- Advisory `ruff format --check` would bulk-reformat six legacy/large files, so
  it was not applied. Advisory `ruff check --select ALL` found 2,593
  full-rule/docstring/test-assert findings; the required default and F/I gates
  remain clean, and no broad legacy formatting or lint rewrite was performed.

## Corrective production/test candidate paths

The following Candidate 9 production/test bytes are FINAL FROZEN after the
authorized migration-owner lane. Line counts and SHA-256 values are exact; any
byte change invalidates the evidence and requires a new candidate:

| Path | Lines | SHA-256 |
| --- | ---: | --- |
| `dayu/cli/workspace_migrations/platform_jobs.py` | 114 | `c397d00531caf4e98bfe6e5947aedbc61475d1c2228ea91593e06e6453966b89` |
| `dayu/investment/storage/models_identity.py` | 908 | `d3e034f88aac1575637b1eb8bc36d44395279455a17a90de34408fb9b84f16fd` |
| `dayu/investment/storage/migrations/versions/0005_source_connectors_health.py` | 2674 | `90b66245012ea33eb97fa7f222b8744b48b4d9cf12a2ff5a51c9d2ff04e23b09` |
| `tests/cli/workspace_migrations/test_platform_jobs.py` | 176 | `9d303e05289b900deed0879bc042af0a5e6345680abb7ddd26bba3fae64e98a4` |
| `tests/integration/investment/test_identity_repositories_postgres.py` | 2102 | `91370d76725aabc363e247cfa0bbf077c80e9352a246f5bafaaefd89c132b145` |
| `tests/integration/investment/test_platform_migrations_postgres.py` | 6785 | `1ea9b84c8edf2a9a5b947c05dc08e0512a689102c85f928676259c883d315cd9` |
| `tests/investment/test_platform_migrations.py` | 2770 | `5595d2b25eb7a7dfe58e5d78d8d4a37c0e725735844975065eb854b01f3fb625` |

## Residuals and STOP status

No plan/catalog/ORM constructibility gap remains. The private raw-table ORM
reference compiles without polluting `PlatformBase.metadata`; Candidate 9
non-PG/static and once-only migration-owner gates are green. Old Candidate 6/
Candidate 8 success and Candidate 7 failure remain historical rather than
substitutes for Candidate 9 evidence. The unchanged identity test retains its
Candidate 8 17-pass evidence and was not rerun. The only other noted residuals
are the non-gating repository-wide/
full-rule formatting and lint debt recorded above. Item 5 remains intentionally
unimplemented by this Item 4 writer. Formal re-review remains pending, so this
artifact does not claim review pass.
