# Slice 2.3 Item 6 job-request-identity prerequisite implementation evidence

Date: 2026-08-14

Repository: `/Users/wsk/workspace/dayu-agent`

Branch: `codex/investment-platform`

Gate / work unit / slice: Gateflow implementation artifact / Item 6
job-request-identity corrective prerequisite / Slice 2.3 source connectors and
health.

Accepted implementation base: `addd8cbebfda8399e67528ea9d970609f933d64d`
(`gateflow: accept item6 prerequisite architecture scope correction`, parent
`e58e63c785646950dce297e6f50b152f6a0e49a1`).

Status: **READY FOR CODE REVIEW**. The implementation, focused/static checks,
and the exact four prerequisite PostgreSQL owner lanes are complete on the
frozen bytes below. This artifact does not claim formal code-review acceptance,
the future Item 6 main work, the final nine-lane gate, staging, a local accepted
commit, push, PR, deployment, or any external action.

Artifact path:
`docs/reviews/implementation-20260814-slice-2.3-item6-job-request-identity-prerequisite.md`.

## Accepted plan and commit identities

The local accepted-plan commit contains the architecture-owner correction that
expanded the implementation allowlist from the unconstructible exact twelve
paths to exact thirteen paths. The sole added implementation owner is
`tests/investment/test_architecture_boundaries.py`, and its sole authorized
semantic change is the existing PostgreSQL Source owner function-count truth
ratchet from 85 to 87. The prerequisite twelve named tests, 44 mappings, 174
final catalog names, six migration/PG owners, Item 6 main ownership, and Item 8
deferral remain unchanged.

The committed truth sources at the accepted base are:

| Truth source | SHA-256 | Lines |
|---|---:|---:|
| `docs/plans/2026-08-10-investment-platform-restoration.md` | `a758d614bc7f9c794509a548bc7c2dead75440a870669ef4085c5cc347e3b1ec` | 4572 |
| `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `2068515fb0b4bc14d85c35de1d9433541504dcedf100c7cca82ecd6d665c9327` | 3612 |
| `docs/reviews/plan-fix-20260814-slice-2.3-item6-prerequisite-architecture-owner-codex.md` | `0d22137e501f5d336a245635455311f41b013e6eef1bcf24567b45878c56a4b6` | 173 |
| `docs/reviews/plan-acceptance-20260814-slice-2.3-item6-prerequisite-architecture-owner-codex.md` | `4aa84222384103b7fa1a46f306d79e41b6c3b0fb51e9705119a7d5bc3e54a943` | 139 |

The accepted architecture-plan Round 2 DeepSeek V4 Pro and MiMo reviews both
returned `PASS / open H/M/L = 0/0/0`. Those plan results authorize
implementation; they do not substitute for the code review that follows this
artifact.

## Scope, non-goals, and write boundary

The accepted implementation allowlist is exactly these thirteen paths:

1. `dayu/investment/storage/migrations/versions/0006_job_request_identity.py`
2. `dayu/cli/workspace_migrations/platform_jobs.py`
3. `dayu/investment/storage/postgres_jobs.py`
4. `dayu/investment/storage/postgres_sources.py`
5. `tests/cli/workspace_migrations/test_platform_jobs.py`
6. `tests/investment/test_platform_migrations.py`
7. `tests/investment/test_architecture_boundaries.py`
8. `tests/integration/investment/test_platform_migrations_postgres.py`
9. `tests/integration/investment/test_job_request_identity_migration_postgres.py`
10. `tests/integration/investment/test_postgres_jobs.py`
11. `tests/integration/investment/test_postgres_sources.py`
12. `tests/README.md`
13. `dayu/investment/README.md`

This implementation-artifact step is separately authorized to create only this
fourteenth path. It does not retroactively widen the implementation allowlist.

Non-goals remain closed: no change to `dayu/investment/domain/jobs.py`, storage
protocols, Services, provider/composition, schedule owners, identity owners,
Source execution handlers, `test_source_sync_job.py`, CI workflows, root
`README.md`, accepted plan/review bytes, MinIO, Redis, public lookup surfaces,
network/provider calls, staging, commit, push, PR, or deployment.

## Frozen exact-thirteen implementation identities

| Path | SHA-256 | Lines | Responsibility |
|---|---:|---:|---|
| `dayu/cli/workspace_migrations/platform_jobs.py` | `a5a7ddb2b7dd1740af828bc46e99faba39710a7596f25410a205c7dcc076f382` | 114 | Workspace migration head and linear 0006 admission |
| `dayu/investment/README.md` | `a0420ba3ce4b5ed0e7ef2ec9f910d600e650e180c6b234dd4156dfe3e4ff46a7` | 333 | Schema/head, repository, and prerequisite/future-lane responsibilities |
| `dayu/investment/storage/migrations/versions/0006_job_request_identity.py` | `33dd4f9ba71c4aed2e167a6887979324dad1b5651f60a56b2c3bb3f75c4bd01d` | 1594 | Linear 0006 migration and migration-local proof/backfill/catalog oracle |
| `dayu/investment/storage/postgres_jobs.py` | `283860c9485fce3567f6bb852fa8179e7978fade3185c31224e2289a23e93dce` | 5405 | New-enqueue identity admission/persistence/reconstruction and lease release floor |
| `dayu/investment/storage/postgres_sources.py` | `4104d4ed6b4fbdd973368cd4188c321917ad7322ed35ef945bcbe2de00ecc84d` | 3004 | Manual/scheduled/existing provenance reads original availability |
| `tests/README.md` | `16e2bcdc783b2a4af580f4f4a97e22f3fdb47b7b464e528cf7e4200f733be69c` | 612 | Dedicated owner commands and prerequisite versus future-lane ledger |
| `tests/cli/workspace_migrations/test_platform_jobs.py` | `2dfa3837e8b8288245d37401e0728dd836e6eb774e13c9e6748e04edff22bc84` | 176 | CLI head 0006 contract |
| `tests/integration/investment/test_job_request_identity_migration_postgres.py` | `4d373a0a10d8b56fcf0b90ee8b723b2c3311ce8ae4f79596d68fbd4d07d19b85` | 1073 | Dedicated 0006 PG owner, seven exact named tests / 24 cases |
| `tests/integration/investment/test_platform_migrations_postgres.py` | `8aece2a4f76af66f610f65aca96357e22855280c16832a20252102a9da87282f` | 6827 | Existing 0005 owner and full-chain cycle |
| `tests/integration/investment/test_postgres_jobs.py` | `eaf39672da9387e03949e2230346854d89c82057daa01b22adac13d377e96716` | 4632 | Strict enqueue, retry/original identity, clock-skew, and coverage closure |
| `tests/integration/investment/test_postgres_sources.py` | `26092014cfa0e64afc4a7e30256e636260f78d557cf2c5937b317c731cbe5ad6` | 4519 | Manual/scheduled hostile provenance tests and existing Source owner |
| `tests/investment/test_architecture_boundaries.py` | `d20dfdf7cc8af216f7a8caceca5a6a731b3969df0057129a79b6cb40e0d3c3d9` | 3842 | Existing function/doc/type/adversarial collector truth 85 -> 87 |
| `tests/investment/test_platform_migrations.py` | `b600d5552f19894d75bcd912323d0431230e61faa0f7f7b48f70dda76979cc23` | 2978 | Pure migration/domain-equivalence and Alembic loader regression owner |

All four accepted PG lanes retained matching pre/post identities for their
production and owner files. Lane 1 and Lane 2 ran before later, unrelated Jobs
owner changes; their migration/owner bytes are identical to the final table.
Lane 3 and Lane 4 ran on the final exact-thirteen identities.

## Implemented contract mapping

### Linear 0006 migration

- `0006_job_request_identity` follows only `0005_source_connectors_health` and
  imports no domain helper. It adds final non-null
  `original_available_at`, `request_payload_schema_name`, and
  `request_payload_schema_version` to `job_runs`.
- The exact five new catalog objects are three checks
  (`ck_job_runs_original_deadline_after_available`,
  `ck_job_runs_request_payload_schema_name_nonempty`, and
  `ck_job_runs_request_payload_schema_version_positive`), the
  `guard_job_runs_request_identity_immutable` function, and its
  `_trigger` trigger. The catalog oracle pins definitions, validation flags,
  function shape/body/security, trigger shape, table/column ACLs, owner, RLS,
  policy permissiveness, persistence, indexes, constraints, and the affected
  0005 baseline.
- Upgrade and downgrade take `ACCESS EXCLUSIVE NOWAIT` locks in the fixed
  `job_runs` then `job_definitions` order and repeat admission under lock. There
  is no waiting fallback and no `CASCADE`.
- Upgrade uses a migration-local strict UTF-8 canonical JSON admission. It
  rejects raw-SHA drift before parsing, duplicates, floats, NaN/Infinity, BOM,
  trailing bytes, noncanonical key order/separators/Unicode, and recursive
  case-insensitive sensitive keys. Valid scalar roots, arrays, nested objects,
  and canonical Unicode remain admitted.
- Backfill is validate-all then mutate-all. It proves every legacy row from its
  current `available_at`, definition schema, raw payload SHA/canonical bytes,
  and exact migration-local fingerprint before any identity UPDATE; it then
  revalidates the written rows before setting non-null constraints and creating
  the five objects.
- Downgrade requires an empty `job_runs`, validates all three columns plus all
  five objects and inbound/shared/outbound extension dependencies, and restores
  the exact affected 0005 catalog/security shape. Alembic revision timing is
  checked at the command boundary rather than falsely expecting the version
  table to change inside `downgrade()`.

### Runtime repository behavior

- `PostgresJobStore.enqueue` verifies the top-level DTO and strictly reparses
  and re-encodes the public payload before session creation, fingerprinting,
  SQL, persistence, or wakeup publication. Bytes and supplied SHA must exactly
  match the public canonical result. Legal request payload schema identity may
  differ from the handler descriptor schema.
- New jobs persist all three original-request columns. Claim, recovery, lease,
  and reconciliation reconstruction reads the persisted request schema rather
  than guessing it from the descriptor. Retry continues to mutate only current
  `available_at`; original availability and request schema identity stay fixed.
- `_release_lease_cas` is the sole lease-release convergence point. It floors
  only `released_at` at the locked persisted `acquired_at`, preserving CAS,
  reason, version, and all receipt/job/attempt business timestamps. The existing
  clock-skew owner proves both the backward floor and forward passthrough.
- `PostgresSourceSyncRepository` now reads `original_available_at` for manual
  validation, existing-operation provenance, scheduled first acquisition, and
  generation takeover. Eligibility/retry logic continues to read mutable
  `available_at`; cross-UTC and pre-acquire retries can no longer shift source
  provenance.

### Tests, architecture, CLI, and docs

- The exact twelve prerequisite FunctionDefs remain uniquely assigned
  `1 / 7 / 2 / 2` across pure migration, dedicated 0006 PG, Jobs PG, and Source
  PG owners. Parameterization creates no aliases, wrappers, dynamic names, or
  duplicate FunctionDefs.
- The dedicated migration matrix covers canonical/progressed/null/array success;
  float, NaN, invalid UTF-8, SHA drift, key order, duplicates, BOM, trailing
  bytes, `token`, and recursive `ToKeN` rejection; retry-mutated availability;
  legacy schema mismatch; dirty/dependent downgrade; both NOWAIT lock targets;
  and a clean 0005 -> 0006 -> 0005 cycle.
- The strict enqueue owner proves invalid document and wrong top-level DTO paths
  through the Store and real `JobService`, with session, fingerprint,
  `Session.execute`, persistence, publisher, and real job-row count all zero.
- The architecture owner retains every collector, documentation, type, direct
  assert, and adversarial rule. Only its exact Source-owner count changed from
  85 to the observed 87 functions (60 non-nested plus 27 nested).
- CLI and both local READMEs name 0006 as current head and distinguish the four
  prerequisite PG processes from existing manual owner commands and the future
  final nine lanes.

## Final pre-PG static and structural evidence

Durable directory:
`/tmp/dayu-s23-item6-prepg-coveragefix.QpJtoN`.

The accepted manifest reports `21/21` exits zero; manifest SHA-256 is
`d55085ea12c9249e82d6a3bb3cdbac785f9fb4ae23e08c92d7cb186452a911b4`.
The final identity log SHA-256 is
`29eca8a44db4dc10dda6bb34823290d2993e1b2facf31693da24e8498e8eb7ca`.

- Focused Jobs-owner `py_compile`, Ruff default, Ruff `--select F,I`, exact
  Pyright, and collect-only all passed; collection was exactly 86.
- All eleven exact Python paths passed `py_compile`, Ruff default, Ruff
  `--select F,I`, and Pyright with `0 errors / 0 warnings / 0 informations`.
- Pure migration plus CLI owners passed 49/49.
- The complete architecture owner passed 171/171; its focused integration
  docstring gate passed 1/1.
- Four PG owner collect-only processes reported exactly 56 / 24 / 86 / 30.
- Exact named-test AST mapping was `1 / 7 / 2 / 2 = 12`.
- Source-owner AST was `60 top + 27 nested = 87`, with zero documentation/type
  violations. The lease-release floor and no-new-helper coverage seams passed.
- Branch, accepted base HEAD, exact-thirteen status, empty index, LF/no-CR/final
  newline, `git diff --check`, README responsibilities, and the sole
  architecture 85 -> 87 semantic delta were all verified.
- A bounded internal migration/owner red-team inspection of the final bytes
  reported open H/M/L `0/0/0`. It is supporting evidence, not the formal code
  review requested by this artifact.

## Accepted PostgreSQL prerequisite evidence

Every lane used only the already-present local image
`postgres@sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8`.
No image pull occurred. The four owners ran sequentially in independent pytest
processes; no accepted owner was rerun on the same bytes.

| Lane | Durable evidence | Exact result | Coverage | Final cleanup |
|---|---|---|---|---|
| 1: existing 0005 migration owner, plain | `/tmp/dayu-s23-item6-lane1-0005-sqlfix.uPqy0L` | 56 collected, 56 passed in 40.86s, pytest exit 0 | Intentionally uninstrumented; no coverage claim | owned containers 0, networks 0, processes 0, index 0, diff check 0 |
| 2: dedicated 0006 migration owner | `/tmp/dayu-s23-item6-lane2-0006-coveragefix.eMnSgf` | 24 collected, 24 passed in 19.56s, all evidence exits 0 | branch true; exact singleton 0006 file; 292/337 lines, 75/116 branches; raw 81.01545253863135% | owned containers 0, networks 0, processes 0, index 0, diff check 0 |
| 3: `PostgresJobStore` owner | `/tmp/dayu-s23-item6-lane3-jobs-coveragefix.MJCgS4` | 86 collected, 86 passed in 113.00s; pytest/JSON/shape/report exits 0 | branch true; exact singleton `postgres_jobs.py`; 827/999 lines, 215/302 branches, 1042/1301 combined; raw 80.09223674096849% | pre/post exact thirteen unchanged; owned containers 0, networks 0, processes 0, index 0, diff check 0 |
| 4: `PostgresSourceSyncRepository` owner | `/tmp/dayu-s23-item6-lane4-sources.tFflFh` | 30 collected, 30 passed in 30.40s; pytest/JSON/shape/report exits 0 | branch true; exact singleton `postgres_sources.py`; 700/792 lines, 228/292 branches, 928/1084 combined; raw 85.60885608856088% | pre/post exact thirteen unchanged; owned containers 0, networks 0, processes 0, index 0, diff check 0 |

Lane 3 retained `.coverage` SHA-256
`42a663bf574eb92a663434c83b5c25cb805a8ce304db9c670e4e1344ffe95ced`,
coverage JSON SHA-256
`7fa8585fe7133c8afa2bf06e6ff5afc8f9b2cab0092a01a79d956a81b3603dbc`,
and evidence-manifest SHA-256
`53aff6a23e6ae061387d6739b696e974ca8ff98d365f5270de3ab68b570ae8dc`.
Lane 4 retained `.coverage` SHA-256
`733dcf724e508018740316441d0f2ca5256713ca904c7e49958562d19b989511`,
coverage JSON SHA-256
`8af6695ee1e97a92b2fe5f1259ad013d56850f91bd5a3aaa5cf8246aaaf08e23`,
and evidence-manifest SHA-256
`e20a545e23f17cb250c802671fb16f546b784a8f5c5ab400e18ecd6076f7ecfc`.

## Rejected candidates and no-rerun ledger

Rejected evidence remains rejected; later green candidates do not rewrite it.
Each changed candidate used a new directory and process. None of the following
bytes was rerun after rejection.

| Candidate / evidence | Result and root cause | Disposition |
|---|---|---|
| `/tmp/dayu-s23-item6-lane1-0005.wEQ24X`; migration `d67272c…/1597` | 2 passed / 54 failed. Alembic loads revision modules without registering the transient module in `sys.modules`; module-level frozen/slots dataclasses dereferenced a missing module and raised `AttributeError`. | Replaced both migration-local value carriers with closed `NamedTuple` classes and added a real `ScriptDirectory` loader regression. Cleanup v2 was zero; never rerun. |
| `/tmp/dayu-s23-item6-lane1-0005-namedtuple.Xa20HF`; migration `00a51013…/1594` | 55 passed / 1 failed. A migration SQL string omitted its `f` prefix, sending literal `{_JOB_TABLE}` to PostgreSQL. | Added the prefix and an AST fail-closed check for unresolved upper-case placeholders. Cleanup v2 was zero; never rerun. |
| `/tmp/dayu-s23-item6-lane2-0006-coverage.KvZB7Y`; owner `cbe9b6ca…/1061` | 20 failed. Owner snapshot concatenated PostgreSQL internal `"char"` values without `::text`, and its expected function body did not preserve exact whitespace/text. Instrumented raw coverage was 75.71743929359823%. | Test-owner-only exact casts/body repair; cleanup zero; never rerun. |
| `/tmp/dayu-s23-item6-lane2-0006-charfix.FuqfYe`; owner `852d6ec0…/1061` | 17 passed / 3 failed. Parameterized `SET LOCAL` used syntax PostgreSQL rejects, and lock blockers held a mode that also blocked catalog preflight, causing two 120-second timeouts. Raw coverage was 79.47019867549669%. | Switched to parameterized `set_config`, deterministic `ACCESS SHARE` conflict, and exact `LockNotAvailable`; cleanup zero; never rerun. |
| `/tmp/dayu-s23-item6-lane2-0006-nowaitfix.uRV2gs`; owner `dbb3d358…/1063` | 20/20 functional pass, but exact-singleton raw coverage was 79.47019867549669%, below the 80% gate. | Added substantive real-PG null/array/finite-float/NaN admission cases inside the existing named matrix; cleanup zero; never rerun. |
| `/tmp/dayu-s23-item6-lane3-jobs.WCPCKV`; Jobs production `ebfd6554…/5401`, owner `cb0473ea…/4494` | 85 passed / 1 failed. A worker/PG clock rollback produced lease `released_at < acquired_at`, rejected by the database invariant. Coverage derivation was not used. | Added the release-only persisted-acquired floor at the sole CAS convergence and exact backward/forward tests; cleanup zero; never rerun. |
| `/tmp/dayu-s23-item6-lane3-jobs-h01.xUvnez`; production `283860c9…/5405`, owner `23d55257…/4588` | 86/86 functional pass, but branch singleton was 826/999 lines plus 214/302 branches: 1040/1301, raw 79.93850883935434%. | Added the accepted changed-code wrong-top-level DTO public Store/Service admission proof inside the existing named test; cleanup zero; never rerun. |
| `/tmp/dayu-s23-item6-lane3-jobs-coveragefix.0fpIFN` | Read-only preflight exit 1 before any PG process. The evidence script used `.strip()` on `git status --short`, removed the first status column's leading space, and misparsed `dayu/...` as `ayu/...`. | Preserved as preflight-only rejection. Repo bytes did not move; PG/process/container/network counts were zero. A new fresh evidence directory used newline-only trimming. |

Additional pre-PG adversarial freezes were rejected without launching PostgreSQL:
the catalog expectation around SQL `trim` deparse, non-set-returning function
`prorows`, affected-table exactness, outbound extension dependencies, RLS policy
permissiveness, and relation persistence were all closed before the final
migration freeze. They are not represented as green execution evidence.

The only Lane 4 candidate is the accepted `tFflFh` run. There was no Lane 4
failure or rerun. No plain pytest rerun followed any instrumented Lane 2, 3, or
4 owner process.

## Documentation decision

Both docs paths in the accepted implementation scope were updated because the
public local runbook changed materially: 0006 is now the current schema head,
there is a new dedicated migration owner, Postgres Jobs and Sources own new
identity/provenance obligations, and the prerequisite gate is exactly four
independent PG processes. Existing identity, schedule, and Redis manual owner
commands remain documented; they were not deleted or misrepresented as current
prerequisite evidence.

The root `README.md`, CI workflows, plan truth sources, and final nine-lane
documentation remain unchanged. Their update belongs to Item 8 after Item 6
main materializes its future owners.

## Deviations and evidence interpretation

- The accepted migration/owner contract did not require a public
  `get_by_idempotency_key` surface. The prerequisite deliberately persists and
  reconstructs identity only through existing repository paths; lookup,
  protocol, and Service expansion remains Item 6 main.
- The Lane 3 release-time defect was discovered by the required whole-owner PG
  process. The minimal repair changes only the audit release timestamp lower
  bound; it does not floor receipt, attempt, or Job business timestamps.
- Coverage repairs are behavioral assertions, not mock-only line filling. Lane
  2 exercises migration-local closed JSON roots in real PG, and Lane 3 exercises
  the accepted public pre-session top-level DTO boundary through Store and real
  Service.
- Lane 1 is intentionally plain and makes no coverage claim. Lanes 2-4 derive
  JSON, exact shape, and report from the same `.coverage` file created by their
  single owner process.
- The evidence-only status-parser failure in `0fpIFN` is not counted as a PG
  candidate run and did not consume the Lane 3 one-process authorization.

## Accepted residual risks and destinations

1. Item 6 main still owns the complete idempotency lookup/reconstruction public
   surface, protocol/Service boundary, Source execution/Job convergence, and its
   exact twenty-path / 51-test implementation. This prerequisite does not claim
   those behaviors.
2. Identity, schedule, Redis, Source execution, and other future owners were not
   run here. The global six-owner/nine-lane final acceptance, workflow wiring,
   aggregate ignores, and final docs belong to Item 8 after Item 6 main. The
   four prerequisite lanes cannot be cited as that final gate.
3. 0006 downgrade is intentionally empty-`job_runs` only. Future full-suite
   fixtures must remove Job descendants before downgrade; that fixture
   coordination remains with the future main/Item 8 owner and did not authorize
   schedule/Redis edits here.
4. PostgreSQL was tested only with the pinned local PostgreSQL 16 digest above.
   No provider, Redis, MinIO, network, CI, deployment, or production environment
   validation is claimed.
5. Formal independent code review and any corrective re-review remain pending.
   The bounded internal red-team `0/0/0` result cannot be used as a substitute.

## Completion and stop status

The exact-thirteen implementation is frozen, its complete static ledger and
four independent prerequisite PG lanes are green, and this artifact is ready
for independent code review. At artifact creation time the branch remains
`codex/investment-platform` at accepted base `addd8cb…`, with an empty index and
no staging, commit, push, PR, deployment, or network/provider action. The next
step is Controller-owned code review; this writer stops after final mechanical
inspection of the fourteen-path worktree.
