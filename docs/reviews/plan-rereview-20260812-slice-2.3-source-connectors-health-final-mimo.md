# Independent Plan Review — Slice 2.3 Source Connectors Health (Final MiMo)

- **Reviewed target**: `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- **Reviewed SHA-256**: `96bceb321464223c9022af25905ca36c4bfe5cdca371111384567acb396ee4f0`
- **Branch**: `codex/investment-platform`
- **Baseline**: `0db6c7b63608a15cd157f842a5be772799fdacd9`
- **Reviewer**: MiMo (independent review lane, not Controller or implementation agent)
- **Date**: 2026-08-12T17:08:12Z
- **Artifact path**: `docs/reviews/plan-rereview-20260812-slice-2.3-source-connectors-health-final-mimo.md`

## 1. Review scope & assumptions tested

This is an independent adversarial re-review of the Slice 2.3 implementation plan. I did **not** read any prior review artifacts, Controller adjudications, or DeepSeek findings. I independently:

1. Read the full plan (2288 lines)
2. Verified baseline code facts against commit `0db6c7b`
3. Simulated code generation paths to identify where the plan under-specifies or mis-specifies behavior
4. Applied architecture boundary, overcoupling, overengineering, state machine, and concurrency lenses

**Assumptions tested**:

| # | Assumption | Evidence source | Status |
|---|---|---|---|
| A1 | `JobExecutionHandlerProtocol.execute` is currently 2-param | `job_service.py:151` — `execute(request, cancellation)` | ✅ Confirmed |
| A2 | `SafeJobErrorCode` currently has 12 values including `REPOSITORY_FAILURE` | `jobs.py:148-162` — 12 enum members | ✅ Confirmed |
| A3 | `domain/source.py` is ~900 lines, no `dayu.fins` imports | `source.py` — 897 lines, imports only `domain.identifiers` | ✅ Confirmed |
| A4 | `DefaultFinsRuntime` is ~3000 lines, no source_sync methods | `service_runtime.py` — 3144 lines, grep=0 matches | ✅ Confirmed |
| A5 | `connectors/`, `investment_sources.py`, `source_sync_execution.py`, `source_sync.py`, `source_health.py`, `source_operation.py` do not exist | glob/read confirms all absent | ✅ Confirmed |
| A6 | Current production mapping is 3 items (identity/jobs/schedules) | `startup_preparation.py:726-730` | ✅ Confirmed |
| A7 | Current composition has 3 service protocols | `composition.py` — identity, workspace_import, base | ✅ Confirmed |
| A8 | Baseline has exactly 24 PostgreSQL tables | Migration grep: 13+2+7+2 = 24 | ✅ Confirmed |
| A9 | PlatformBase metadata has 8 ORM tables | `models_identity.py` — 8 classes | ✅ Confirmed |
| A10 | `DownloadEvent.payload` is `dict[str, Any]` | `download_events.py:45` | ✅ Confirmed |
| A11 | `JobHandlerRegistry` / `JobExecutionRegistry` have no `seal()` / `is_sealed` | `job_service.py:264-350` — no such methods | ✅ Confirmed (plan adds them) |
| A12 | `JobExecutionRequest` has 8 fields | `jobs.py:1191` — tenant_id, definition_id, job_id, attempt_id, attempt_number, descriptor, payload, deadline_at | ✅ Confirmed |
| A13 | `JobHandlerDescriptor` exists with expected fields | `jobs.py:973` | ✅ Confirmed |

## 2. Findings

### No material findings

After thorough adversarial review, I find **zero** evidence-based material findings at H/M/L severity.

**Rationale**:

#### Architecture boundary review
- The 4-module domain DAG (`source.py → nothing; source_sync → source/jobs/schedules; source_health → source_sync/source/jobs; source_operation → source_sync/source_health/jobs`) is clean with no cycles. `source.py` (897 lines) is confirmed to have zero `dayu.fins` imports.
- The `connectors/source.py` adapter boundary correctly restricts `dayu.fins` exposure to exactly two packages (`fins.domain.source_sync`, `fins.domain.evidence_locator`) while forbidding `fins.*` for all investment pure owners.
- The `storage/source_sync_protocols.py` protocol-only owner correctly forbids concrete Postgres/Session/Row/Fins/Service imports.
- The handler protocol change (2→3 params) is correctly specified as a full replacement with `inspect.signature`/Pyright gate and AST proof — no compat path that could silently break.

#### Async-to-sync bridge (§6.1.1)
- `asyncio.create_task(asyncio.to_thread(...))` + `asyncio.shield()` is the correct pattern for offloading sync PG calls from the event loop. The pre-PONR reap/propagate semantics are precisely specified: first outer `CancelledError` recorded, shield continues, reap to completion, then first cancel re-raised.
- PONR semantics are exact: last `is_cancel_requested()` check is synchronous on event-loop thread, `create_task` success is the irreversible boundary, no `await` between check and task creation.

#### FOR UPDATE NOWAIT / 55P03
- Lock sequence is 8-row fixed order (job_run → job_definition → job_attempt → job_lease → source_operation → subscription → source_definition → security → health). Each row uses `NOWAIT`.
- `55P03` / `psycopg.errors.LockNotAvailable` is the sole typed mapping to `SourceSyncRepositoryFailure(unavailable)`. No message/driver-class guessing.
- Terminal PONR conflict: entire transaction rollback, operation stays ACTIVE, inner failure is authoritative, outer cancellation cannot override.

#### DDL / 0005 migration
- 3 new tables with exact column/type/nullability/default/CHECK/RLS/grant specs.
- 14 new nullable columns on `source_sync_runs` with named CHECK constraints (`ck_source_sync_runs_v1_core_presence`, `_counts`, `_outcome_shape`) that correctly handle legacy all-NULL rows.
- Named `ck_source_health_snapshots_v2_shape` correctly allows legacy `health_state_version IS NULL` rows.
- Named `ck_source_sync_operations_state_shape` enforces ACTIVE/TERMINAL nullability.
- `ck_source_health_states_shape` correctly requires `IS NOT NULL` (not `NOT IN`) for `safe_error_code`.
- 11 named trigger functions + 11 named triggers in a single manifest. Upgrade DAG creates parent UNIQUEs before child FKs; downgrade reverses.
- Insert guards (`source_sync_runs_require_v1_insert`, `source_health_snapshots_require_v2_insert`, `source_sync_operations_require_initial_insert`, `source_health_states_require_initial_insert`) prevent new legacy shapes.
- Immutable guards (`guard_source_sync_runs_append_only`, etc.) prevent UPDATE/DELETE on append-only tables.
- Transition guards (`guard_source_sync_operations_transition`, `guard_source_health_states_transition`) enforce exact state machine transitions.
- 0005 adds 3 tables → 27 total. Confirmed baseline is 24 (13+2+7+2 from migrations 0001–0004).

#### Domain model / DTOs
- All DTOs are `@dataclass(frozen=True, slots=True)` — correct for immutable value objects.
- `SourceConnectorKey` values are strings (not enums), with only `fins.market-disclosure.v1` in production registry — correctly deferred.
- Manual/scheduled fingerprint formulas are closed and deterministic.
- `SourceFinsTerminalCandidate` construction matrix is exhaustive with exact outcome/count/error/docs shapes.
- Alert dedupe/event UUID derivation is deterministic and order-independent.

#### Startup composition (§10)
- Explicit provider correctly skipped from source-specific assembly. Auto-provider adds `investment_sources` as 4th mapping item. Seal-before-publish with逆序 close on failure.
- Registry seal prevents dynamic registration after startup.

#### Testing
- 100+ named tests covering handler signature migration, sealed registries, async bridge pre-PONR/PONR, real PG NOWAIT conflicts, DDL catalog exactness, downgrade safety, crash residual replay, and architecture boundary enforcement.
- Architecture boundary test (`test_architecture_boundaries.py`, 1491+ lines) already enforces forbidden import lists and escape pattern guards — plan correctly extends it for `connectors/**` owner.

#### STOP conditions
- 18 explicit STOP conditions covering Worker modification, Fins submit leakage, architecture boundary violation, source date forgery, nested stream missing owner, operation claiming Job state, async bridge violations, migration hazards, and allowlist expansion.

## 3. Open questions

None. All architecture decisions, contract specifications, edge cases, and sequencing are fully resolved within the plan.

## 4. Residual risks (inherent to problem scope, not plan defects)

| Risk | Severity | Mitigation in plan |
|---|---|---|
| Nested stream aclose chain across8 files — implementation precision required | Low | Exact owner chain documented; each layer owns exactly one inner stream; finally: aclose() exactly once |
| Async-to-sync bridge PONR edge case — `asyncio.to_thread` thread creation failure | Low | Plan specifies `create_task` success as PONR; failure =尚未越界, zero repository call |
| Migration DDL scope — 3 new tables + 14 new columns + triggers + RLS + grants in single transaction | Low | Exact upgrade/downgrade DAG with preflight; parent-before-child ordering; named manifest |
| 0005 adds 3 tables to 24 — total 27 must match catalog test exactly | Low | Plan specifies exact catalog self-check with kind/name/columns/predicate/FK/trigger/policy/ACL |

## 5. Plan review conclusion

**PASS**

Open findings: **H=0, M=0, L=0**

The plan is code-generation-ready with precise contracts, exhaustive edge-case handling, correct architecture boundaries, comprehensive DDL specification, and explicit STOP conditions. No material adversarial findings. Implementation agents may proceed.

## 6. Reviewed artifact integrity

| Item | Value |
|---|---|
| Reviewed file | `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` |
| SHA-256 verified | `96bceb321464223c9022af25905ca36c4bfe5cdca371111384567acb396ee4f0` ✅ |
| Baseline commit | `0db6c7b63608a15cd157f842a5be772799fdacd9` |
| Branch | `codex/investment-platform` |
| Prior review artifacts read | 0 (independent lane) |
