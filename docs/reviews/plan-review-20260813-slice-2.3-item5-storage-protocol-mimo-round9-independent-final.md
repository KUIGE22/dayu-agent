# Plan Review — Slice 2.3 Item 5 Storage Protocol (Round 9, MiMo-V2.5 Independent)

- **Reviewer**: MiMo-V2.5 (`xiaomi/mimo-v2.5`)
- **Timestamp**: 20260813-161218（本机系统时钟）
- **Review posture**: Fresh independent adversarial review; no prior review artifact conclusions used as evidence

## Identities

| Role | Path | SHA-256 | Lines |
|---|---|---|---|
| Target | `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `c51e89ddce927300ba03dd293cb15e8927de2ecb341f5955f5fe9b097b440988` | 3248 |
| Master | `docs/plans/2026-08-10-investment-platform-restoration.md` | `1db7eb076637dc3ec8eaed92bcd422b36b8c102076c32b957fc99ed650b5b87a` | 4405 |
| Fix | `docs/reviews/fix-20260813-slice-2.3-item5-storage-protocol.md` | `62b6d2dae6a91caf7ee189c4a408028b24b1998b8bc80f457d50976f80cf822f` | 349 |
| HEAD | `45154597d3d01be13287393f4123003a1444f0eb` | (git rev-parse) | — |

## Scope

Fresh independent review of Item 5 storage protocol candidate, focusing on:
1. Protocol direct imports / concrete constructor
2. Item 4 / 0005 dependency manifest closure
3. Leased-definition contract (already-LEASED job status)
4. Full request/execution/repository seven-method failure taxonomy (§9)
5. Legacy receipt (0001 13-core-all-null)
6. §13.3 exact 53 ordinal / file assignment (Item 5 PG27, Item 6 APP4/JOB15/OP5/HEALTH2)
7. 159 named tests / 43 coverage keys / Item 5 exact five paths
8. Rollback SQLAlchemy/DBAPI failure including rollback self-55P03 → `transaction_aborted` override
9. Only rollback-success original-55P03 or no-rollback-55P03 → `unavailable`
10. #6/#23 must freeze all four combinations

## Assumptions Tested

| # | Assumption | Status |
|---|---|---|
| A1 | §9 protocol-only direct imports cover all seven method annotations without `source_sync.py` | Verified — no gap |
| A2 | `PostgresSourceSyncRepository` concrete constructor is uniquely frozen | Verified |
| A3 | Item 4 accepted manifest (five items) is closed at HEAD `4515459` | Verified |
| A4 | already-LEASED definition status is not a live predicate (§6.1) | Verified |
| A5 | §9 transaction outcome priority table is internally consistent | Verified — no contradiction |
| A6 | Rollback self-55P03 is highest priority (`transaction_aborted`), overriding original | Verified |
| A7 | #6/#23 cover all four rollback/typed-lock combinations | Verified |
| A8 | §13.3 ordinal/file assignment is exhaustive, pairwise-disjoint, union `{1..53}` | Verified |
| A9 | 43 coverage keys match production allowlist; `source_sync_protocols.py` tuple is singleton | Verified |
| A10 | Item 5 exact five paths are correct and exist | Verified |
| A11 | Legacy 0001 receipt read contract is complete | Verified |
| A12 | `get_source_receipt` cannot leak cross-tenant existence | Verified |

## Findings

No material findings identified. The candidate is code-generation-ready.

### Detailed Evidence for Each Focus Area

#### 1. Protocol Direct Imports (§9, target lines 2166–2194)

The closed import set is:
- `typing.Protocol`, `typing.runtime_checkable`
- `uuid.UUID`
- `dayu.investment.domain.identifiers.TenantScope`
- `dayu.investment.domain.source.SourceSubscriptionId`
- `dayu.investment.domain.source_evidence.SourceSyncAttemptReceipt`
- `dayu.investment.domain.source_health.{SourceHealthProjection, SourceHealthReenableRequest, SourceHealthSnapshotCursor, SourceHealthSnapshotPage}`
- `dayu.investment.domain.source_operation.{SourceOperationAcquireDecision, SourceOperationAcquireRequest, SourceTerminalRecordDecision, SourceTerminalRecordRequest}`
- `dayu.investment.domain.source_payload.SourceExecutionBinding`

Verification: The seven method signatures (lines 2204–2249) use exactly these types:
- `get_executable_binding`: `TenantScope`, `SourceSubscriptionId` → `SourceExecutionBinding`
- `acquire_operation`: `TenantScope`, `SourceOperationAcquireRequest` → `SourceOperationAcquireDecision`
- `record_terminal`: `TenantScope`, `SourceTerminalRecordRequest` → `SourceTerminalRecordDecision`
- `get_source_receipt`: `TenantScope`, `UUID` → `SourceSyncAttemptReceipt | None`
- `get_health`: `TenantScope`, `SourceSubscriptionId` → `SourceHealthProjection`
- `list_health_snapshots`: `TenantScope`, `SourceSubscriptionId`, `SourceHealthSnapshotCursor | None`, `limit: int` → `SourceHealthSnapshotPage`
- `reenable_health`: `TenantScope`, `SourceHealthReenableRequest` → `SourceHealthProjection`

Every annotation type has a direct import. `source_sync.py` is excluded (it has no annotation types). `uuid.UUID` is a stdlib import. No leak to concrete/session/Fins/Service. The fix's `S23-I5-PROTOCOL-OWNER-01` is correctly encoded.

#### 2. Concrete Constructor (§9, target lines 2251–2275)

`PostgresSourceSyncRepository(SourceSyncRepositoryProtocol)` is frozen with exact constructor `(self, session_factory: sessionmaker[Session]) -> None`. This matches the project-local convention (`PostgresJobStore`, `PostgresScheduleStore`). No additional dependencies, no optional setter, no second concrete. The fix's `S23-I5-CONCRETE-CONSTRUCTOR-02` is correctly encoded.

#### 3. Item 4 Dependency Manifest (§12, target lines 2658–2685)

Five items verified:
1. `item4_accepted_commit` = `4101fb6da02eb08ddd245561a92e021046fdeccb` ✓
2. `item4_migration_sha256` = `90b66245012ea33eb97fa7f222b8744b48b4d9cf12a2ff5a51c9d2ff04e23b09` (0005, 2674 lines) ✓
3. `item4_models_identity_sha256` = `d3e034f88aac1575637b1eb8bc36d44395279455a17a90de34408fb9b84f16fd` (908 lines) ✓
4. `item4_acceptance_artifact` = path/SHA/conclusion `PASS` stored at metadata commit ✓
5. `item4_final_review_artifacts` = single independent review tuple with `PASS / open H/M/L=0/0/0` ✓

Both commits (`4101fb6` semantic + `4515459` metadata acceptance) form an inseparable identity. The fix's `S23-I5-ITEM4-DEPENDENCY-03` is correctly encoded.

#### 4. Leased-Definition Contract (§6.1, target lines 1506–1556)

The plan explicitly states:
- "对已经处于LEASED的Job，当前 `job_definitions.status` 既不是acquire也不是terminal的live predicate"
- "active admission只属于generic Job owner在形成lease之前的claim/admission"
- "Source repository不得在lease形成后重新执行第二份definition-status admission"

两条Source路径仍按锁序执行 `FOR UPDATE NOWAIT`，以串行化 identity/descriptor 与并发 status update。Status update 占锁产生的 original typed `55P03` 在 rollback 成功时返回 `unavailable`，rollback 失败按 `CONSTRUCT-09` 覆盖为 `transaction_aborted`。disable 已提交后的重试在其它 live 条件成立时仍可成功。

The existing test `test_concurrent_source_definition_or_security_update_serializes_with_acquire_and_terminal_revalidation` is extended with definition status concurrency matrix (disable commit → retry success). The fix's `S23-I5-CONSTRUCT-05` is correctly encoded.

#### 5. Transaction Outcome Priority Table (§9, target lines 2286–2302)

Six priorities verified for internal consistency:

| Priority | Condition | Result | Consistent? |
|---|---|---|---|
| 1 | Rollback called + rollback self-failure (including55P03) | `transaction_aborted` | ✓ — covers all rollback failure scenarios |
| 2 | Rollback success + original 55P03/LockNotAvailable; or no rollback needed + original 55P03 | `unavailable` | ✓ — mutually exclusive with P1 |
| 3 | First SQL success + post-admission statement/flush/commit DB failure + rollback success | `transaction_aborted` | ✓ — P1 supersedes if rollback fails |
| 4 | Admission phase (before first SQL success) + non-55P03 DB failure + cleanup success | `unavailable` | ✓ — P1 supersedes if cleanup fails |
| 5 | SQL success + row reconstruction failure + rollback success | `persisted_invariant` | ✓ — P1 supersedes if rollback fails |
| 6 | Request/execution rejection + rollback success or no rollback | Preserved rejection code | ✓ — P1 supersedes if rollback fails |

Key invariants verified:
- P1 is truly highest: any rollback failure (including rollback-self-55P03) → `transaction_aborted`, regardless of original error type.
- P2 requires rollback success (or no rollback) — if rollback fails, P1 wins.
- P3–P5 all require rollback success — P1 supersedes on rollback failure.
- P4 is the only one that implicitly defers to P1 on cleanup failure (admission phase, first-SQL fails, cleanup fails → P1 returns `transaction_aborted`). This is correct behavior but implicit.
- Admission vs post-admission boundary: "第一条SQL成功返回前" = admission; "第一条SQL成功返回后" = post-admission. This is unambiguous.
- `persisted_invariant` only appears in P5 (reconstruction after successful SQL) — cannot be overridden by typed lock precedence.
- `request/execution rejection` (P6) is preserved regardless of phase — typed lock never downgrades it.

The fix's `S23-I5-CONSTRUCT-06` and `S23-I5-CONSTRUCT-09` are correctly encoded. The STOP conditions (target line 3118–3121) also match the priority table.

#### 6. #6/#23 Four Combinations (§9 + §13.3, target lines 2326–2335)

Test #6 `test_acquire_and_terminal_nowait_map_only_sqlstate_55p03_lock_not_available_to_retryable_repository_failure` and #23 `test_repository_failure_before_source_commit_writes_zero_source_health_or_alert_rows` are frozen with four combinations in parameter matrix:

1. Original typed `55P03` + rollback success → `unavailable` (P2)
2. Original typed `55P03` + rollback failure → `transaction_aborted` (P1)
3. Rollback self typed `55P03` → `transaction_aborted` (P1)
4. No-rollback original typed `55P03` → `unavailable` (P2)

All four combinations are explicitly stated in the target plan (lines 2327–2333) and the fix document (lines 250–252). They are in `parameterized cases` within the same test name, not new named catalog items.

#### 7. §13.3 Exact 53 Ordinal Assignment (target lines 2896–2919)

Five groups verified:

| Slice | Ordinals | Count | File | Disjoint? |
|---|---|---|---|---|
| Item 5 PG | 1,2,6,9,10,11,17,20,23,28,29,32,36–47,49,51,52 | 27 | `test_postgres_sources.py` | ✓ |
| Item 6 APP | 3,4,8,18 | 4 | `test_source_sync_execution.py` | ✓ |
| Item 6 JOB | 5,7,12,19,21,22,24–27,30,31,33,34,50 | 15 | `test_source_sync_job.py` | ✓ |
| Item 6 OP | 13–16,48 | 5 | `test_source_operation_domain.py` | ✓ |
| Item 6 HEALTH | 35,53 | 2 | `test_source_health_domain.py` | ✓ |

Union: `{1..53}` = 53 items. Counts: `27+4+15+5+2 = 53`. Pairwise disjoint verified by set inspection. Item 5 PG27 ordinal sets do not overlap with any Item 6 sets.

Item 6 additionally receives two domain-ratchet test-only write paths: `tests/investment/test_source_operation_domain.py` and `tests/investment/test_source_health_domain.py`. These are test-only scope, not production paths. The fix's `S23-I5-CONSTRUCT-08` is correctly encoded.

#### 8. Legacy Receipt (§9, target lines 2319 + §8.2, lines 1973–1980)

`get_source_receipt` contract:
- Invalid scope/run ID type/shape → `invalid_input`, zero SQL
- Missing / cross-tenant → `None`
- Legal 0001 13-core-all-null legacy row → `None`
- v1 13-core-all-nonnull → strict rebuild from `receipt_json` + outer `tenant_id`
- 13-core partial / illegal-full / canonical drift / SHA mismatch / lineage drift → `persisted_invariant`

The fix's `S23-I5-CONSTRUCT-07` is correctly encoded. Cross-tenant existence is not leaked (returns `None` without distinguishing missing vs cross-tenant).

#### 9. Coverage Owner Tuple (§11.1, target line 2571)

``dayu/investment/storage/source_sync_protocols.py`` → `(``tests/investment/test_source_sync_storage_protocols.py``,)`

Singleton tuple. The fix's `S23-I5-COVERAGE-OWNER-04` correctly narrows from a two-member tuple (with nonexistent `tests/application/test_source_sync_execution.py`) to this singleton. `test_source_sync_execution.py` is owned by Item 6, not Item 5.

Total: 43 keys, 42 unchanged tuples, 1 singleton correction. The fix's claim is verified.

#### 10. Item 5 Exact Five Paths (§11, target lines 2616–2623)

1. `dayu/investment/storage/source_sync_protocols.py` — protocol owner ✓
2. `dayu/investment/storage/postgres_sources.py` — concrete owner ✓
3. `tests/investment/test_source_sync_storage_protocols.py` — protocol test owner ✓
4. `tests/integration/investment/test_postgres_sources.py` — PG integration owner ✓
5. `tests/investment/test_architecture_boundaries.py` — architecture guard ✓

All five paths exist at HEAD `4515459`. No sixth path required. No expansion of global allowlist.

#### 11. Named Test Catalog (159 items)

159 named tests total:
- §13.1: 30 tests (Job/scope/registry/schedule)
- §13.2: 42 tests (Fins contracts)
- §13.3: 53 tests (operation/crash/health)
- §13.4: 20+ tests (migration/security) + 1 new concrete test
- Plus `test_postgres_source_sync_repository_class_and_session_factory_constructor_are_exact` (new)

Total from fix document: 158 → 159 with the new concrete/constructor test. The fix's `S23-I5-CONCRETE-CONSTRUCTOR-02` is correctly encoded.

## Open Questions

None. All focus areas have been verified with direct evidence from the target plan, fix document, and HEAD commit.

## Residual Risks

1. **P4 rollback-failure implicit**: Priority 4 in the transaction outcome table (target line 2295) only explicitly covers the "cleanup success" case. When admission-phase first-SQL fails and rollback also fails, Priority 1 takes precedence (returning `transaction_aborted`). This is logically correct but implicitly depends on P1 — the STOP condition (line 3118) mentions `transaction_aborted` for rollback failure but does not explicitly enumerate the admission-phase scenario. An implementation agent following P4 literally might not consider the rollback-failure branch. **Risk: Low** — P1 is clearly highest priority and the STOP condition does state "rollback failure" generically; the risk is that an implementation agent might only read P4 in isolation.

2. **DeepSeek V4 Pro still HTTP 402**: The second review path remains unavailable. This does not affect the MiMo review conclusion but means the dual-review gate is not yet satisfied.

## Conclusion

**PASS / open H/M/L = 0/0/0**

The Item 5 storage protocol candidate is code-generation-ready. All ten focus areas verified:

- Protocol imports are complete and correct; concrete constructor is uniquely frozen
- Item 4 dependency manifest is closed at HEAD `4515459`
- Leased-definition contract correctly excludes `job_definitions.status` from live predicate
- Transaction outcome priority table is internally consistent; rollback-self-55P03 correctly maps to `transaction_aborted` (highest priority)
- Legacy receipt contract handles 0001 13-core-all-null as `None` without cross-tenant leakage
- §13.3 53 ordinals are exhaustively assigned across five disjoint groups
- 43 coverage keys match production allowlist; singleton tuple correction is minimal
- Item 5 exact five paths are correct and sufficient
- Named catalog is 159 items with the new concrete/constructor test
- All four rollback/typed-lock combinations are frozen in #6/#23 parameter matrix

No material findings. One low-risk observation on implicit P1 dependency in P4 (residual, not blocking).

**Files touched**: (none — read-only review)

**Model**: `xiaomi/mimo-v2.5` (MiMo-V2.5)
**HEAD**: `45154597d3d01be13287393f4123003a1444f0eb`
**Target SHA-256**: `c51e89ddce927300ba03dd293cb15e8927de2ecb341f5955f5fe9b097b440988` / 3248 lines
**Master SHA-256**: `1db7eb076637dc3ec8eaed92bcd422b36b8c102076c32b957fc99ed650b5b87a` / 4405 lines
**Fix SHA-256**: `62b6d2dae6a91caf7ee189c4a408028b24b1998b8bc80f457d50976f80cf822f` / 349 lines
