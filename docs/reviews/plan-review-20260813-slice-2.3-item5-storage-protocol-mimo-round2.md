# Item 5 Storage Protocol Corrective Plan — MiMo Round 2 Independent Review

- 日期：2026-08-13
- Reviewer：MiMo（fresh independent plan re-review，Round 2）
- 状态：`PASS / open H/M/L=0/0/0`
- Review scope：target + master + fix 三份 FINAL FROZEN semantic 字节
- Superseded prior review：`docs/reviews/plan-review-20260813-slice-2.3-item5-storage-protocol-mimo.md`，SHA-256 `71d74ea837c42a3d328f237e8c978c1c5f23ff548fe537f61ca5f31009be9200` / 147行；因本轮 metadata/manifest 变化已 `SUPERSEDED / STALE`，不继承结论

## 1. Document Identity & SHA Verification

| Document | SHA-256 | Lines | Status |
|---|---|---|---|
| target `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `470e7f18a5cf441df9dceb39163d989008b7e4ac7faf31b5e1ed8ae1ee239dbd` | 3094 | FINAL FROZEN ✅ |
| master `docs/plans/2026-08-10-investment-platform-restoration.md` | `ce8605bebb7233d9f32e45607383c48153e41356521b1acecf612b370eee8ca7` | 4361 | FINAL FROZEN ✅ |
| fix `docs/reviews/fix-20260813-slice-2.3-item5-storage-protocol.md` | `1f4fa387633e95e630490b7840573e5be0bfaedafa91d7e706d82f8c539ec981` | 180 | FINAL FROZEN ✅ |
| base HEAD | `45154597d3d01be13287393f4123003a1444f0eb` | — | Verified ✅ |

- 三份 SHA-256 与行数全部与 fix §0 声明一致，无字节漂移。
- base HEAD `4515459` 是 `gateflow: record slice-2.3 item4 acceptance`，与 fix §1 metadata 一致。
- target 和 master 在 working tree 中有 uncommitted diff（来自本轮 corrective fix 写回），SHA 验证针对当前 working tree 字节。

## 2. Motivation & Architecture Review

### 2.1 Protocol Import Set（fix §3.1 / target §3.3 + §9）

**Finding S23-I5-PROTOCOL-OWNER-01 — 已修复 — 高**

fix 声称：HEAD 版本 target §3.3 的 protocol-only import set 遗漏了 `uuid.UUID` 和 `source.SourceSubscriptionId`，并误列了无 annotation 的 `source_sync.py`。

**独立验证**：
- target §3.3（lines 773-778）已冻结 protocol-only exact direct-import manifest：
  - `typing.Protocol/runtime_checkable`
  - `uuid.UUID`
  - `identifiers.TenantScope`
  - `source.SourceSubscriptionId`
  - `source_payload.SourceExecutionBinding`
  - `source_evidence.SourceSyncAttemptReceipt`
  - 四个 health DTO（`SourceHealthProjection`, `SourceHealthReenableRequest`, `SourceHealthSnapshotCursor`, `SourceHealthSnapshotPage`）
  - 四个 operation DTO（`SourceOperationAcquireDecision`, `SourceOperationAcquireRequest`, `SourceTerminalRecordDecision`, `SourceTerminalRecordRequest`）

- 七方法实际 annotation 依赖核对：
  - `UUID`：`get_source_receipt` 的 `source_sync_run_id` 参数（target §9 line 2200）
  - `SourceSubscriptionId`：`get_executable_binding`（line 2183）、`get_health`（line 2207）、`list_health_snapshots`（line 2213）的 `subscription_id` 参数
  - `source_payload.SourceExecutionBinding`：`get_executable_binding` 返回值（line 2184）
  - `source_evidence.SourceSyncAttemptReceipt`：`get_source_receipt` 返回值（line 2202）
  - `source_health` 四个 DTO：`get_health`/`list_health_snapshots`/`reenable_health` 的参数与返回值
  - `source_operation` 四个 DTO：`acquire_operation`/`record_terminal` 的参数与返回值

- HEAD blob 确认 `SourceSubscriptionId` 定义于 `source.py:233`，SHA-256 `b87774f69bb90d8c9d4cd0971f572882e9103b6c8a33b8087bc7a1663f80096d`。
- `source_sync.py` 不拥有上述任何一个 annotation type，只包含 `SourceSyncErrorCode`、`SourceSyncRequestRejected`、`SourceSyncExecutionRejected`、`SourceSyncRepositoryFailure`、`SourceServiceInputError`、`SourceServiceUnavailableError` 等异常/枚举类。

**裁决**：accepted。fix 的 §9 exact import set 完整覆盖七方法 annotation 需求，无遗漏、无多余。`source_sync.py` 的 closed exceptions 属于 concrete 行为合同，由 `postgres_sources.py` 按需 import，不进入 protocol module。

### 2.2 Concrete Class & Constructor（fix §3.2 / target §9）

**Finding S23-I5-CONCRETE-CONSTRUCTOR-02 — 已修复 — 高**

fix 声称：HEAD 版本 target 从未冻结 `PostgresSourceSyncRepository` 类名或 `session_factory: sessionmaker[Session]` constructor。

**独立验证**：
- target §9（lines 2226-2233）已冻结：
  ```python
  class PostgresSourceSyncRepository(SourceSyncRepositoryProtocol):
      def __init__(self, session_factory: sessionmaker[Session]) -> None: ...
  ```
- `storage/source_sync_protocols.py` 和 `postgres_sources.py` 在 HEAD 均不存在（planned-new files）。
- 现有 platform store pattern 核对：
  - `PostgresJobStore(JobStoreProtocol)` at `postgres_jobs.py:573`，constructor `session_factory: sessionmaker[Session]` at line 580
  - `PostgresScheduleStore(ScheduleStoreProtocol)` at `postgres_schedules.py:1246`，constructor `session_factory: sessionmaker[Session]` at line 1253
- fix 提议的 constructor 零 I/O、零 optional dependency、零 setter，完全匹配既有 pattern。

**裁决**：accepted。constructor 精确为 `(self, session_factory: sessionmaker[Session]) -> None`，与 platform convention 一致。target 现在已冻结该 exact contract。

### 2.3 Item 4 Dependency Gate（fix §3.3 / target §12）

**Finding S23-I5-ITEM4-DEPENDENCY-03 — 已修复 — 高**

fix 声称：Item 5 不得绑定未 accepted 的 Item 4 moving schema bytes。

**独立验证**：
- git log 确认 Item 4 semantic commit `4101fb6da02eb08ddd245561a92e021046fdeccb`（`gateflow: accept slice-2.3 item4 source schema`）存在。
- metadata acceptance commit `45154597d3d01be13287393f4123003a1444f0eb`（`gateflow: record slice-2.3 item4 acceptance`）是 HEAD。
- target §12（lines 2578-2605）明确要求 Item 5 dispatch 前置 manifest 五项，缺一即 STOP。

- 五项 manifest SHA-256 验证：
  1. `item4_accepted_commit` = `4101fb6da02eb08ddd245561a92e021046fdeccb` ✅
  2. `item4_migration_sha256` = `90b66245012ea33eb97fa7f222b8744b48b4d9cf12a2ff5a51c9d2ff04e23b09` for `0005_source_connectors_health.py`（2674行）✅
  3. `item4_models_identity_sha256` = `d3e034f88aac1575637b1eb8bc36d44395279455a17a90de34408fb9b84f16fd` for `models_identity.py`（908行）✅
  4. `item4_acceptance_artifact` = `docs/reviews/slice-2.3-item4-source-schema-code-acceptance-20260813-codex.md` / `a61382414b548dd3237121c6bb94bf0935be480999a53c6bab3322746fd486ce` / 117行 / `PASS` ✅
  5. `item4_final_review_artifacts` = `(docs/reviews/code-review-20260813-item4-schema-candidate9-final.md, a6aed10b0ef1b0b894a62b3f9d56c689f01dda66b76217d21e09a02696325bf1, PASS / open H/M/L=0/0/0)`（37行）✅

- Supporting formal metadata：`docs/reviews/code-review-20260813-104658.md` / `5adf3516a08725fd202a7bc12d66850fb78507e9daca4a3b327bf47d6b949683` / 152行 / `CLOSED / PASS` ✅

- `source_sync_protocols.py`、`postgres_sources.py` 及相关 test 文件在 HEAD 均不存在，确认 Item 5 尚未 dispatch。

**裁决**：accepted。Item 4 accepted manifest 是硬 STOP predicate，不是可绕过的 placeholder。fix 正确保持该约束。五项 SHA-256 全部与 HEAD 字节一致。

## 3. Best Practice / Optimality / Coupling

- **Architecture boundary**：protocol 只暴露 pure DTO，concrete 独占 SQLAlchemy/psycopg；Service 只依赖 protocol。依赖方向不反转。✅
- **Best practice**：从 canonical owner direct import 使 Pyright/runtime type hints/AST ownership 三者同源。单一 session factory 与既有 Postgres stores 一致。✅
- **Optimality**：修改 exact manifest 与 constructor 比新增 adapter/re-export/dependency bag 更小。✅
- **Overengineering**：拒绝为未 accepted 的 schema 增加 revision detector、dual SQL、clock/UUID injection。✅
- **Overcoupling**：Item 4 通过 immutable accepted manifest 成为前置证据，Item 5 不回写 migration/models。✅

## 4. Codegen Readiness

- 七方法 exact signature + exact import set → implementation agent 可机械生成 `source_sync_protocols.py`。
- `PostgresSourceSyncRepository` class/constructor frozen → 可机械生成 `postgres_sources.py`。
- Item 4 dependency manifest 是确定性 STOP → 不存在歧义。
- §13 named test catalog 159 项 → 可机械验证。
- constructor zero-I/O trap → 可机械测试。

## 5. Slice Sequencing

- Item 1 accepted `4cfb932`、Item 2 accepted `e3167d7`、Item 3 `595564e`、Item 4 semantic `4101fb6` + metadata `4515459`（HEAD）。✅
- Item 5 保持 frozen 直到 fresh same-new-SHA 双审、Controller acceptance 与 local accepted corrective-plan commit 完成。✅
- fix 不宣称 review pass、Item 4 accepted 或 Item 5 implementation 获授权。✅

## 6. Test / Allowlist / Coverage

- named-test catalog：158→159，唯一新增 `test_postgres_source_sync_repository_class_and_session_factory_constructor_are_exact`（target line 2652）。✅
- §11 production/test allowlist 零增删。✅
- §11.1 `COVERAGE_OWNER_TESTS` 精确 43 keys 零变化。✅
- Item 5 exact writer 仍只有五个既有 path：
  1. `dayu/investment/storage/source_sync_protocols.py`
  2. `dayu/investment/storage/postgres_sources.py`
  3. `tests/investment/test_source_sync_storage_protocols.py`
  4. `tests/integration/investment/test_postgres_sources.py`
  5. `tests/investment/test_architecture_boundaries.py`
- `test_source_sync_storage_protocols.py` 和 `test_postgres_sources.py` 在 HEAD 不存在（planned-new），不构成 stale ref。✅

## 7. Target / Master / Fix Consistency

- target §3.3（lines 773-778）已包含 fix 提议的 exact import set。✅
- target §9（lines 2149-2168）已包含 fix 提议的 exact import block。✅
- target §9（lines 2226-2233）已包含 `PostgresSourceSyncRepository` + `sessionmaker[Session]` constructor。✅
- target §12（lines 2578-2605）已包含 Item 4 dependency manifest STOP。✅
- target §13（line 2652）已包含新增 test name。✅
- target §11（lines 2547-2554）确认零 allowlist 扩张。✅
- master §0（lines 284-300）与 §7（lines 4057-4068）确认 Item 5 corrective decision 与 target/fix 一致。✅
- master 确认旧 MiMo `71d74ea8` 已 `SUPERSEDED / STALE`。✅
- fix §2 evidence table 中的 HEAD blob SHA `b87774f69bb90d8c9d4cd0971f572882e9103b6c8a33b8087bc7a1663f80096d` 用于 `source.py:233` `SourceSubscriptionId`，与 HEAD 一致。✅
- 三份文档内部一致，无冲突。✅

## 8. Stale References

- `source_sync_protocols.py`、`postgres_sources.py`、`test_source_sync_storage_protocols.py`、`test_postgres_sources.py`：planned-new，HEAD 不存在，不构成 stale ref。✅
- `source_sync.py` HEAD 为 789 行（非 fix §2 引用的 WIP 1839 行），说明 WIP 已被拆分/缩减；fix 不依赖该行数。✅
- `source.py` HEAD 897 行，与 target §3.2 一致。✅
- `0005_source_connectors_health.py` HEAD 2674 行，与 manifest 一致。✅
- `models_identity.py` HEAD 908 行，与 manifest 一致。✅

## 9. Item 4 Source/Test as Foreign Moving WIP

- fix 不读取、不引用、不编辑任何 Item 4 production/test/migration 字节。✅
- Item 4 的 `0005_source_connectors_health` migration、`postgres_schedules.py` test 等均为 foreign scope。✅
- fix 不误报 Item 4 artifacts 为 plan scope。✅
- Item 4 dependency manifest 只从已提交的两个 commit 读取，不从 working tree 推导。✅

## 10. 0004 STOP Verification

- target §12（line 2601-2603）明确：Item 5 repository 只面向已通过 startup migration admission 的 0005 head，不查询 `alembic_version`、不尝试 0004 column/table fallback、不捕获 undefined-table/column 后切换 SQL，也不回改 0005 migration/models。✅
- fix §3.3 确认：repository 只支持已由 startup admission 升级到 0005 的 schema，不查 `alembic_version`、不 catch undefined table/column 切换 0004 SQL、不回改 migration/models。✅
- 0004 fallback 是明确禁止的，STOP predicate 正确。✅

## 11. Open Questions

| # | Severity | Question | Resolution |
|---|---|---|---|
| — | — | 无 blocking open question | — |

Item 4 exact SHA values 已由 target §12 frozen manifest 闭合，不再是 dispatch blocker。当前未满足的是 fresh same-new-SHA DeepSeek V4 Pro + MiMo review、Controller acceptance 与 local accepted corrective-plan commit。这些是 deterministic implementation prerequisites，不是 open questions。

## 12. Finding Summary

| ID | Title | Severity | Status |
|---|---|---|---|
| S23-I5-PROTOCOL-OWNER-01 | closed import set 遗漏真实 annotation owner 并误列 source_sync | 高 | 已修复 ✅ |
| S23-I5-CONCRETE-CONSTRUCTOR-02 | authoritative plan 未冻结 repository 类与 constructor | 高 | 已修复 ✅ |
| S23-I5-ITEM4-DEPENDENCY-03 | Item 5 不得绑定未 accepted 的 moving schema bytes | 高 | 已修复 ✅ |

**Open H/M/L: 0/0/0**

## 13. Conclusion

**PASS**

两个 Item 5 code-generation blocker 与一个 schema sequencing blocker 已在 docs candidate 中闭合。target/master/fix 三份 FINAL FROZEN semantic 字节 SHA-256/lines 验证通过，三者内部一致。protocol exact direct imports 完整覆盖七方法 annotation 需求，concrete class/constructor 冻结并与 platform convention 一致，Item 4 dependency gate 正确保持硬 STOP。test catalog 159 项、allowlist 43 keys 零扩张。

本 review 只证明上述三 SHA 的 semantic 合格性，不授权 Item 5 implementation、Item 4 accepted 或任何 commit/push/PR。下一入口是 Controller acceptance + local accepted corrective-plan commit + Item 4 local accepted dependency manifest 闭合。

---

**前置 SHA-256 验证**（写前 snapshot）：
- target: `470e7f18a5cf441df9dceb39163d989008b7e4ac7faf31b5e1ed8ae1ee239dbd` / 3094行
- master: `ce8605bebb7233d9f32e45607383c48153e41356521b1acecf612b370eee8ca7` / 4361行
- fix: `1f4fa387633e95e630490b7840573e5be0bfaedafa91d7e706d82f8c539ec981` / 180行
- base HEAD: `45154597d3d01be13287393f4123003a1444f0eb`
