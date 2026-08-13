# Slice 2.3 Item 5 storage repository implementation evidence

Date: 2026-08-13

Repository: `/Users/wsk/workspace/dayu-agent`

Branch: `codex/investment-platform`

Gate / work unit / slice: Gateflow implementation and code-review closure / Item 5 storage repository / Slice 2.3 source connectors and health.

Implementation base and accepted-plan checkpoint: `0b0de626a9df475240c945f77cc68a836ede3d4c`.

Status: **IMPLEMENTATION COMPLETE / FORMAL SOURCE REVIEW PASS 0/0/0 / DURABLE BOOKKEEPING READY FOR FINAL MECHANICAL GATE**. This artifact records evidence; it does not claim that staging, a local accepted commit, push, Draft PR, deployment, or any external action occurred.

Artifact path: `docs/reviews/implementation-20260813-slice-2.3-item5-storage-repository.md`.

## Accepted plan identities

The accepted semantic review set froze these pre-acceptance bytes:

| Truth source | Reviewed SHA-256 | Lines |
|---|---:|---:|
| `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `c51e89ddce927300ba03dd293cb15e8927de2ecb341f5955f5fe9b097b440988` | 3248 |
| `docs/plans/2026-08-10-investment-platform-restoration.md` | `1db7eb076637dc3ec8eaed92bcd422b36b8c102076c32b957fc99ed650b5b87a` | 4405 |
| `docs/reviews/fix-20260813-slice-2.3-item5-storage-protocol.md` | `62b6d2dae6a91caf7ee189c4a408028b24b1998b8bc80f457d50976f80cf822f` | 349 |

Fresh independent DeepSeek V4 Pro and MiMo Round 9 reviews both returned `PASS / open H/M/L = 0/0/0`; the Round 9 mechanical audit also returned `PASS / 0/0/0`. The Controller accepted all nine plan findings. At the implementation base, bookkeeping additions made the current committed truth-source identities:

| Current truth source at HEAD | SHA-256 | Lines |
|---|---:|---:|
| `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `4d5acca2037a4cf28892bd3f5d1df8fd5ecdcf59ec53c4ea73184d5753e76df6` | 3261 |
| `docs/plans/2026-08-10-investment-platform-restoration.md` | `351d372b2da669e254bbc551fbecfbc7853d6614530d784c180dce0c3809d7c7` | 4423 |
| `docs/reviews/fix-20260813-slice-2.3-item5-storage-protocol.md` | `ff8afee1aab8d4552692222a9757a4c722a9f7604fc4797ed0631e06abff5fd4` | 369 |
| `docs/reviews/plan-acceptance-20260813-slice-2.3-item5-storage-protocol-codex.md` | `522dd61b0a2d1b1d2ff0a8afc49853086e8d41a404a31f7f57e8fb7626162346` | 160 |

The reviewed semantic snapshot identities and current committed bookkeeping identities are intentionally both recorded; neither is substituted for the other.

## Scope, non-goals, and write boundary

Item 5 implemented one pure synchronous storage protocol, one PostgreSQL repository, and their exact owner/architecture tests. The accepted implementation allowlist was exactly these five paths:

1. `dayu/investment/storage/source_sync_protocols.py`
2. `dayu/investment/storage/postgres_sources.py`
3. `tests/investment/test_source_sync_storage_protocols.py`
4. `tests/integration/investment/test_postgres_sources.py`
5. `tests/investment/test_architecture_boundaries.py`

This durability pass is evidence-only and is separately authorized to create this artifact and `docs/reviews/fix-20260813-slice-2.3-item5-storage-repository-code.md`. It does not retroactively widen the implementation allowlist.

Non-goals remained unchanged: no domain, migration, model, storage export, Service, execution handler, startup/composition, provider, Broker, model, network, trading, capital, deployment, Item 6, or other Slice implementation; no schema change; no public compatibility re-export; no stage, commit, push, or PR.

## Frozen implementation files

| Path | SHA-256 | Lines | Responsibility |
|---|---:|---:|---|
| `dayu/investment/storage/source_sync_protocols.py` | `0be190fb2ad8e67842f3bb83e908864d1362b3247e73a62c3d9143d59128ec2f` | 181 | Pure `SourceSyncRepositoryProtocol` owner |
| `dayu/investment/storage/postgres_sources.py` | `8505198ef28aaf32af1506f82b2ba8c5e32fba2ca5eccc888a3ab1097c727030` | 3004 | Concrete PostgreSQL repository |
| `tests/investment/test_source_sync_storage_protocols.py` | `231c94b7feeced32251f63fe310a04d6d1e98c2ee091da41dc85b001dbc24a93` | 213 | Exact protocol owner tests |
| `tests/integration/investment/test_postgres_sources.py` | `7090745b568bcfec7bd9413d2a6de6e608f0263713cb878f130fc44fe1e50128` | 4294 | Exact PG27 assignment, collected as 28 tests including the constructor owner |
| `tests/investment/test_architecture_boundaries.py` | `aed6d88237145d37e3422c7b759b1061ca6017ebe0cb965d1c78289898a53e48` | 3842 | Dependency, strict type, docstring, and adversarial AST gates |

Total frozen implementation/test size is 11,534 lines. Candidate and post-run SHA/line manifests were identical in both final owner evidence lanes.

## Implemented plan mapping

- The protocol owns exactly seven synchronous methods: `get_executable_binding`, `acquire_operation`, `record_terminal`, `get_source_receipt`, `get_health`, `list_health_snapshots`, and `reenable_health`. Its imports and annotations expose only accepted pure domain DTOs and identifiers; it does not import concrete storage, SQLAlchemy, psycopg, Fins, Session/Row, or Service owners.
- `PostgresSourceSyncRepository(SourceSyncRepositoryProtocol)` has the single accepted `sessionmaker[Session]` constructor and owns session lifecycle, tenant-local RLS setup, transaction settlement, and the closed request/execution/repository failure surface. Typed lock and rollback precedence follows the accepted `CONSTRUCT-06/09` full order rather than message or SQL-text guessing.
- Acquire and terminal flows use the accepted fixed NOWAIT lock order, one PostgreSQL clock observation after all locks, strict Job/definition/attempt/lease/source lineage, generation fences, and zero source DML on rejected preconditions. An already-leased Job validates immutable definition identity without treating a later definition disable as lease revocation.
- Existing ACTIVE operation takeover validates durable snapshot provenance. Manual snapshots are anchored to the locked payload; scheduled windows are anchored to locked `job_runs.available_at`. Busy, acquired, takeover, replay, lease-loss, and persisted-drift outcomes remain closed and typed.
- Terminal recording atomically owns source operation terminal state, source run/result/receipt, health head/snapshot, and semantic alert outbox mutation. Replay does not add a marker or rewrite canonical source truth. Conflict re-read verifies that the outbox body, status, error, dedupe key, UUID, lineage, and snapshot time remain byte/identity consistent.
- Receipt reads distinguish missing/cross-tenant/legal legacy all-null rows (`None`) from strict v1 all-full reconstruction. Partial, illegal-full, canonical/SHA, run, subscription, Job, or attempt lineage drift fails as `persisted_invariant`.
- Health reads, descending keyset pagination (`observed_at`, `id`, limit 1..200), and CAS re-enable enforce tenant scope, exact head/snapshot lineage, version/time monotonicity, state conflicts, and zero-mutation failures.
- Owner tests materialize the Item 5 PG27 ordinal assignment in one file, plus the concrete constructor test. They cover transaction phases and rollback precedence, typed NOWAIT conflicts, concurrent definition/security/health serialization, provenance, takeover/replay, exact negative receipt/operation/lease matrices, pagination, health transitions, alert conflicts, and adversarial cross-tenant/cross-lineage cases.
- Architecture gates enforce exact protocol imports and no concrete leaks, all 85 PG owner functions' strict annotations and complete semantic Chinese `Args`/`Returns` or `Yields`/`Raises` contracts, nested-owner assert attribution, known placeholder rejection, and precise bootstrap database-error documentation.

## Candidate C1-C14 history

Later green candidates do not rewrite failed or incomplete history. An em dash means the fact was not durably retained and is not inferred.

| Candidate | Frozen identity / retained evidence | Outcome |
|---|---|---|
| C1 | `/tmp/dayu-s23-item5-postgres-sources.HZK89u`; only `.coverage`; SHA, lines, pytest log/exit — | Controller session observed 3 passed / 25 failed; the actual `companies` table has no `tenant_id`. Incomplete, not gate evidence. |
| C2 | `/tmp/dayu-s23-item5-postgres-sources-c2.CNG0xt`; only `.coverage`; SHA, lines, log/exit — | Session observed 23 passed / 5 failed; setup guard and lock-timing problems. Incomplete. |
| C3 | `/tmp/dayu-s23-item5-postgres-sources-c3.LGmaCm`; only `.coverage`; SHA, lines, log/exit — | Session observed 26 passed / 2 failed; immutable guards rejected bootstrap updates. Incomplete. |
| C4 | `/tmp/dayu-s23-item5-postgres-sources-c4.84K9SC`; only `.coverage` and `coverage.json`; SHA, lines, pytest log/exit — | Session observed 28/28, but coverage gate failed. Retained exact-singleton branch JSON: raw 67.3076923076923%, 762/553 statements and 278/147 branches. Not gate evidence. |
| C5 | protocol `0be190fb…`; production `3f48b216…`; protocol test `231c94b7…`; PG test `4e69eb19…`; architecture `450f6093…`; lines — | Exit 1: 27 passed / 1 failed in 17.80s; cross-ID/cross-source binding test failed. No coverage closure. |
| C6 | same protocol/production/protocol-test/architecture; PG test `b574dddd…`; lines — | Exit 0: 28/28 in 17.61s; exact-singleton raw 81.0576923076923%, 762/641 statements and 278/202 branches. No post/final identity, so not final evidence. |
| C7 | protocol `0be190fb…/181`; production `78d2ac81…/2935`; protocol test `231c94b7…/213`; PG test `a63e9e7f…/1410`; architecture `450f6093…` with lines not retained | PG 28/28 in 17.76s; raw 81.17760617760618%. Formal review `180904`: FAIL 2/0/0. |
| C8 | No PG evidence directory; session observed production 3004 lines and PG owner 2317 lines; complete five-file SHA/lines were not retained | Replaced during pre-freeze/static/collect/focused work; PG lane never started. No PG result is claimed. |
| C9 | protocol `0be190fb…`; production `8505198e…`; protocol test `231c94b7…`; PG test `61b338de…/2339`; architecture `450f6093…` | PG 28/28 in 20.29s; raw 84.22509225092251%; candidate/post identity retained. Formal review `191154`: FAIL 1/0/0. |
| C10 | `0be190fb…/181`, `8505198e…/3004`, `231c94b7…/213`, PG `bef09e2e…/3063`, architecture `450f6093…/3595` | Exit 1: 2 failed / 20 passed / 7 errors in 17.72s. Fixture SQL used reserved alias `constraint`; downgrade conflict and cluster-global role pollution cascaded. No coverage derivation. |
| C11 | same stable three owners; PG `75a90288…/3077`; architecture `450f6093…/3595` | Exit 1: 27 passed / 1 failed in 21.68s. #47 attempted to update immutable `job_leases.token_sha256`; trigger rejected it. No coverage closure; diff/index checks were 0. |
| C12 | stable protocol/production/protocol-test; PG `7d282759…/3092`; architecture `450f6093…/3595` | 28/28 in 19.50s; raw 85.60885608856088%; all evidence exits 0; candidate==post. Formal review `201941`: FAIL 1/1/0. |
| C13 | stable protocol/production/protocol-test; PG `d4c4d789…/4260`; architecture `bdb81e9f…/3728` | 28/28 in 22.48s; raw 85.60885608856088%; all final exits 0; candidate==post. Formal review `212630`: FAIL 0/1/0. |
| C14 | exact five frozen identities in the preceding table | PG 28/28 in 19.84s; raw 85.60885608856088%; fresh protocol 3/3 in 0.23s and raw 100.0%; all final exits 0; final formal review `223139`: PASS 0/0/0. |

## Final validation evidence

### PostgreSQL owner lane

Durable directory: `/tmp/dayu-s23-item5-postgres-sources-c14.7090745b-aed6d882`.

- The retained bundle does not store a literal command line. Its logs and coverage metadata prove one instrumented pytest process over `tests/integration/investment/test_postgres_sources.py`, with branch coverage including exactly `dayu/investment/storage/postgres_sources.py`; there was no plain rerun.
- The resolved PostgreSQL 16 image was exactly `postgres@sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8` (`docker-image-inspect.exit=0`).
- Pytest exit 0; exactly 28 collected unique owner tests, 28 passed in 19.84s.
- Coverage JSON, exact-shape verifier, and `coverage report --fail-under=80` exits were 0/0/0. `branch_coverage=True`; file set was the exact singleton `[dayu/investment/storage/postgres_sources.py]`; raw combined coverage was 85.60885608856088%, with 792 statements / 700 covered and 292 branches / 228 covered.
- Preflight, pytest, coverage, diff, index, and final verifier exits were all 0. Candidate and post-run five-path SHA/line manifests were identical. The final owned-container list was empty.

### Protocol owner lane

Durable directory: `/tmp/dayu-s23-item5-protocol-c14.f2HnEZ`.

- The bundle records one instrumented pytest process over `tests/investment/test_source_sync_storage_protocols.py`, with branch coverage including exactly `dayu/investment/storage/source_sync_protocols.py`; no rerun occurred.
- Pytest exit 0; the exact three protocol tests passed in 0.23s.
- Coverage JSON, shape verification, and `coverage report --fail-under=80` exits were 0/0/0. `branch=True`; exact singleton file set; raw 100.0%; 19/19 statements and 0/0 branches.
- Candidate and post-run protocol/test SHA and line manifests were identical (`0be190fb…/181`, `231c94b7…/213`). Branch, HEAD, empty index, diff check, status identity, and final verifier all closed with exit 0.

### Static, focused, collection, and structural checks

The Controller's retained bounded ledger records `py_compile` exit 0; Pyright on the exact five paths with 0 errors / 0 warnings / 0 informations; Ruff default and `--select F,I` both passing; a focused non-PG selection with 174 passed; PG collect-only at exactly 28; and `git diff --check` passing. The final independent review separately retained protocol plus exact semantic-doc architecture selection `4 passed in 0.31s`.

AST inventories found 85 functions in the PG owner and exactly 28 top-level tests; 106 functions and 69 tests in the architecture owner. Missing sections, old argument/return placeholders, untyped parameters/returns, `Any`/`object`, incomplete direct-assert contracts, and forbidden private import gaps were all zero. The C13 and C14 PG owner executable ASTs were identical after docstring removal; normalized dump SHA-256 was `9cad14f42c263ad606c64c023bc8ee66d367a9f2c3f749f968a05418806947bb`.

## Formal review and documentation decision

The authoritative final review is `docs/reviews/code-review-20260813-223139.md`, SHA-256 `cdaf021442223ee125eff2cc0446bb223753ff6b218c267bac4a83ce9d765767`, 52 lines, with `PASS / open H/M/L = 0/0/0`. Its retained protocol-evidence bookkeeping gap was subsequently closed by the fresh protocol lane above.

The Controller inspected the `tests/README.md` responsibility trigger. No update is required: the exact five-path implementation allowlist excludes README; this work does not change CLI/configuration, test invocation, user workflow, or runbook responsibility. It strengthens implementation correctness, negative matrices, annotations, docstrings, and their gates without changing how users run the tests.

## Deviations, collisions, and plan gaps

- Durable implementation/fix bookkeeping was intentionally created after the formal source review because those artifacts were not in the exact five implementation paths. This is a gate-recording delay, not an implementation-scope expansion.
- An orchestration collision briefly produced two apparent Controller threads. Ownership was explicitly handed to the current Controller; the duplicate lane was interrupted and remained read-only thereafter. An unaccepted 18-line speculative production patch from that duplicate lineage was reversed before final freeze. `postgres_sources.py` is exactly the accepted `8505198e…/3004` bytes; the reverted patch is not represented as a fix or validation input.
- C1-C4 lack complete durable pytest/SHA evidence, and C8 never launched a PG lane. They remain explicitly incomplete historical candidates and are not used to support PASS.
- C10 and C11 are retained failures, not hidden retries. C12-C14 are distinct candidate runs; C14 is the final evidence identity.
- No unresolved semantic plan-to-code gap was found in the exact five paths. The remaining concerns are the accepted residuals below and final mechanical/staging bookkeeping, not an unclassified source defect.

## Accepted residual risks and destinations

These are accepted plan §16 residuals; PASS does not mean `none`.

1. Provider reads are not exactly once. Local Fins document identity and source operation identity prevent duplicate trusted side effects. Destination: later provider/execution reliability work.
2. Source terminal and Job terminal are separate transactions. Last-attempt crash or post-handler cancellation can diverge the Job envelope from canonical source truth; if source never commits, an ACTIVE operation remains physical audit only. Destination: Item 6 execution/Worker convergence and later audit projection work.
3. Redis wakeups can drop, duplicate, or reorder. PostgreSQL claim and source operation remain truth. Destination: existing durable Job/Schedule reliability model.
4. Automatic health disable does not stop schedules from creating no-op Jobs. Operators must disable the schedule explicitly. Destination: operator workflow / later health automation.
5. RSS, industry, and manual connectors remain non-executable. Destination: later connector slices.
6. Semantic alerts are persisted only; Telegram/Obsidian delivery is deferred. Destination: later alert-delivery slice.
7. Existing Fins date-only metadata supports calendar-day freshness only, not minute-level freshness. Destination: future provider metadata contract.
8. Owned-thread reap has no wall-clock bound if database, pool, network, OS, or statement work never returns. NOWAIT covers row-lock contention only. Destination: future platform reliability gate with executable pool/connect/statement/network timeout configuration and fault tests.
9. Existing Job/Schedule repository failures have no typed code, so the Source facade can expose only stable `unavailable` rather than distinguish infrastructure from persisted drift. Destination: separate typed repository-error contract work unit if operator observability requires it.

## Completion and stop status

Implementation and corrective source review are complete on the frozen C14 exact-five identity, with authoritative open H/M/L = 0/0/0 and both owner coverage lanes closed. This artifact itself still requires final mechanical inspection together with the fix artifact. The Controller alone owns the subsequent exact stage-set decision and local accepted commit. This writer performed no stage, commit, push, PR, PostgreSQL run, network access, or edit outside the two authorized new artifact paths.
