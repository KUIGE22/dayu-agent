# Item 5 Storage Protocol Corrective Plan — MiMo Independent Review

- 日期：2026-08-13
- Reviewer：MiMo（独立 plan re-review）
- 状态：`PASS / open H/M/L=0/0/0`
- Review scope：target + master + fix 三份 FINAL FROZEN semantic 字节

## 1. Document Identity & SHA Verification

| Document | SHA-256 | Lines | Status |
|---|---|---|---|
| target `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `d25505f3778e04d9f7dfcf669bb495d07265ce63ad243875a008c86a110b16d6` | 3078 | FINAL FROZEN ✅ |
| master `docs/plans/2026-08-10-investment-platform-restoration.md` | `b66b2bba0539d66fd0777222a8da5bd775d808ae72f0e9b33ab02759e6334aad` | 4345 | FINAL FROZEN ✅ |
| fix `docs/reviews/fix-20260813-slice-2.3-item5-storage-protocol.md` | `28f7bb3c337998d367c935fc702ae148b0136385eb5ea412020437132f961838` | 149 | FINAL FROZEN ✅ |
| base HEAD | `595564ebcbd398fb84a4eab21e0cd9e045f56dd5` | — | Verified ✅ |

- 三份 SHA-256 与行数全部与 fix §0 声明一致，无字节漂移。
- base HEAD `595564e` 是 `gateflow: accept slice-2.3 item3 fins source sync`，与 target §metadata 一致。
- target 在 HEAD 上有 uncommitted diff（2955→3078行），该 diff 正是本 fix candidate 的内容写回；fix 的 pre-edit line refs 指向 HEAD 版本。

## 2. Motivation & Architecture Review

### 2.1 Protocol Import Set（fix §3.1 / target §3.3 + §9）

**Finding S23-I5-PROTOCOL-OWNER-01 — 已修复 — 高**

fix 声称：HEAD 版本 target §3.3 的 protocol-only import set 遗漏了 `uuid.UUID` 和 `source.SourceSubscriptionId`，并误列了无 annotation 的 `source_sync.py`。

**独立验证**：
- HEAD 版本 target（2955行）的 storage protocol 描述为"storage protocol可按DTO实际需要import五个owner"，未指定 exact symbols。
- 七方法实际 annotation 依赖：
  - `UUID`：`get_source_receipt` 的 `source_sync_run_id` 参数（target §9 line 2199）
  - `SourceSubscriptionId`：`get_executable_binding`（line 2182）、`get_health`（line 2207）、`list_health_snapshots`（line 2210）的 `subscription_id` 参数
  - `source_payload.SourceExecutionBinding`：`get_executable_binding` 返回值
  - `source_evidence.SourceSyncAttemptReceipt`：`get_source_receipt` 返回值
  - `source_health` 四个 DTO：`get_health`/`list_health_snapshots`/`reenable_health` 的参数与返回值
  - `source_operation` 四个 DTO：`acquire_operation`/`record_terminal` 的参数与返回值
- `source_sync.py` 不拥有上述任何一个 annotation type。HEAD blob 确认 `SourceSubscriptionId` 定义于 `source.py:233`，`UUID` 是标准库。
- 现有 `PostgresJobStore` 和 `PostgresScheduleStore` 均使用 `sessionmaker[Session]` constructor（`postgres_jobs.py:580`、`postgres_schedules.py:1253`），与 fix 提议一致。

**裁决**：accepted。fix 的 §9 exact import set 完整覆盖七方法 annotation 需求，无遗漏、无多余。`source_sync.py` 的 closed exceptions 属于 concrete 行为合同，由 `postgres_sources.py` 按需 import，不进入 protocol module。

### 2.2 Concrete Class & Constructor（fix §3.2 / target §9）

**Finding S23-I5-CONCRETE-CONSTRUCTOR-02 — 已修复 — 高**

fix 声称：HEAD 版本 target 从未冻结 `PostgresSourceSyncRepository` 类名或 `session_factory: sessionmaker[Session]` constructor。

**独立验证**：
- HEAD 版本 target 只有"Postgres source repository"与 `postgres_sources.py` path，确实无 exact class name 或 constructor signature。
- `storage/source_sync_protocols.py` 和 `postgres_sources.py` 在 HEAD 均不存在（planned-new files）。
- 现有 platform store pattern：`PostgresJobStore(session_factory: sessionmaker[Session])`、`PostgresScheduleStore(session_factory: sessionmaker[Session])`。
- fix 提议 `PostgresSourceSyncRepository(SourceSyncRepositoryProtocol)` + `__init__(self, session_factory: sessionmaker[Session]) -> None` 完全匹配既有 pattern。

**裁决**：accepted。constructor 零 I/O、零 optional dependency、零 setter，与 platform convention 一致。target 现在已冻结该 exact contract。

### 2.3 Item 4 Dependency Gate（fix §3.3 / target §12）

**Finding S23-I5-ITEM4-DEPENDENCY-03 — 已修复 — 高**

fix 声称：Item 5 不得绑定未 accepted 的 Item 4 moving schema bytes。

**独立验证**：
- git log 确认 Item 4（durable schedules）无 local accepted commit。最近 commit 是 Item 3 `595564e`。
- target §12 明确要求 Item 5 dispatch 前置 manifest 五项（`item4_accepted_commit`、`item4_migration_sha256`、`item4_models_identity_sha256`、`item4_acceptance_artifact`、`item4_final_review_artifacts`），缺一即 STOP。
- fix 不读取或伪造任何 Item 4 字节，不从 working tree 推导 SHA。
- `source_sync_protocols.py`、`postgres_sources.py` 及相关 test 文件在 HEAD 均不存在，确认 Item 5 尚未 dispatch。

**裁决**：accepted。Item 4 accepted manifest 是硬 STOP predicate，不是可绕过的 placeholder。fix 正确保持该约束。

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

## 5. Slice Sequencing

- Item 1 accepted `4cfb932`、Item 2 accepted `e3167d7`、Item 3/HEAD `595564e`。✅
- Item 4 无 accepted commit → Item 5 保持 frozen。✅
- fix 不宣称 review pass、Item 4 accepted 或 Item 5 implementation 获授权。✅

## 6. Test / Allowlist / Coverage

- named-test catalog：158→159，唯一新增 `test_postgres_source_sync_repository_class_and_session_factory_constructor_are_exact`。✅
- §11 production/test allowlist 零增删。✅
- §11.1 `COVERAGE_OWNER_TESTS` 43 keys 零变化。✅
- Item 5 exact writer 仍只有五个既有 path。✅
- `test_source_sync_storage_protocols.py` 和 `test_postgres_sources.py` 在 HEAD 不存在（planned-new），不构成 stale ref。

## 7. Target / Master / Fix Consistency

- target §3.3（lines 772-774）已包含 fix 提议的 exact import set。✅
- target §9（lines 2148-2167）已包含 fix 提议的 exact import block。✅
- target §9（lines 2225-2233）已包含 `PostgresSourceSyncRepository` + `sessionmaker[Session]` constructor。✅
- target §12（lines 2577-2592）已包含 Item 4 dependency manifest STOP。✅
- target §13（line 2639）已包含新增 test name。✅
- target §11（lines 2546-2554）确认零 allowlist 扩张。✅
- master 不直接涉及 Item 5 storage protocol，无冲突。✅
- fix §2 evidence table 中的 HEAD blob SHA `b87774f69bb90d8c9d4cd0971f572882e9103b6c8a33b8087bc7a1663f80096d` 用于 `source.py:233` `SourceSubscriptionId`，与 HEAD 一致。✅

## 8. Stale References

- `source_sync_protocols.py`、`postgres_sources.py`、`test_source_sync_storage_protocols.py`、`test_postgres_sources.py`：planned-new，HEAD 不存在，不构成 stale ref。✅
- `source_sync.py` HEAD 为 789 行（非 fix §2 引用的 WIP 1839 行），说明 WIP 已被拆分/缩减；fix 不依赖该行数。✅
- `source.py` HEAD 897 行，与 target §3.2 一致。✅

## 9. Item 4 Source/Test as Foreign Moving WIP

- fix 不读取、不引用、不编辑任何 Item 4 production/test/migration 字节。✅
- Item 4 的 `0004_durable_schedules` migration、`postgres_schedules.py` test 等均为 foreign scope。✅
- fix 不误报 Item 4 artifacts 为 plan scope。✅

## 10. Open Questions

| # | Severity | Question | Resolution |
|---|---|---|---|
| — | — | 无 blocking open question | — |

Item 4 exact SHA values 尚不存在，由 §3 accepted prerequisite 在未来 dispatch 前机械填充，不是设计选择。这是确定性 implementation prerequisite，不是 open question。

## 11. Finding Summary

| ID | Title | Severity | Status |
|---|---|---|---|
| S23-I5-PROTOCOL-OWNER-01 | closed import set 遗漏真实 annotation owner 并误列 source_sync | 高 | 已修复 ✅ |
| S23-I5-CONCRETE-CONSTRUCTOR-02 | authoritative plan 未冻结 repository 类与 constructor | 高 | 已修复 ✅ |
| S23-I5-ITEM4-DEPENDENCY-03 | Item 5 不得绑定未 accepted 的 moving schema bytes | 高 | 已修复 ✅ |

**Open H/M/L: 0/0/0**

## 12. Conclusion

**PASS**

两个 Item 5 code-generation blocker 与一个 schema sequencing blocker 已在 docs candidate 中闭合。target/master/fix 三份 FINAL FROZEN semantic 字节 SHA-256/lines 验证通过，三者内部一致。protocol exact direct imports 完整覆盖七方法 annotation 需求，concrete class/constructor 冻结并与 platform convention 一致，Item 4 dependency gate 正确保持硬 STOP。test catalog 159 项、allowlist 43 keys 零扩张。

本 review 只证明上述三 SHA 的 semantic 合格性，不授权 Item 5 implementation、Item 4 accepted 或任何 commit/push/PR。下一入口是 Controller acceptance + local accepted corrective-plan commit + Item 4 local accepted dependency manifest 闭合。
