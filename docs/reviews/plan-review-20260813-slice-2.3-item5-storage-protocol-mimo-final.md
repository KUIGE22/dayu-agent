# Item 5 Storage Protocol Corrective Plan — MiMo Final Independent Review

- 日期：2026-08-13
- Reviewer：MiMo（fresh independent final plan review）
- 状态：`PASS / open H/M/L=0/0/0`
- Review scope：target + master + fix 三份 FINAL FROZEN semantic 字节
- Superseded/rejected prior reviews：
  - `docs/reviews/plan-review-20260813-slice-2.3-item5-storage-protocol-mimo.md`，SHA-256 `71d74ea837c42a3d328f237e8c978c1c5f23ff548fe537f61ca5f31009be9200` / 147行 — 使用 pre-correction SHA，遗漏 coverage-owner blocker → `SUPERSEDED / REJECTED`，不继承
  - `docs/reviews/plan-review-20260813-slice-2.3-item5-storage-protocol-mimo-round2.md`，SHA-256 `b5c0b1c97ce9094e51daa77a2178cfa66bcb305c950cd19a775289b7abc7c3e5` / 199行 — 使用 intermediate SHA，仍未发现不存在的 tuple member → `SUPERSEDED / REJECTED`，不继承

## 1. Document Identity & SHA Verification

| Document | SHA-256 | Lines | Status |
|---|---|---|---|
| target `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `66845a72f528b5955209de935dd798d01ad8fbdb35ab3c10db42fb5fd07986f1` | 3111 | FINAL FROZEN ✅ |
| master `docs/plans/2026-08-10-investment-platform-restoration.md` | `2a4e5e60510f12b5dd51b3279cc1f8118e609ff557a3a086ec10521ee3aecdf8` | 4371 | FINAL FROZEN ✅ |
| fix `docs/reviews/fix-20260813-slice-2.3-item5-storage-protocol.md` | `615d99975ab3e104539464f14e17bfa7761b12d49538674e211fb43ceeca2ca3` | 221 | FINAL FROZEN ✅ |
| base HEAD | `45154597d3d01be13287393f4123003a1444f0eb` | — | Verified ✅ |

- 三份 SHA-256/lines 与用户指定的 final frozen 值逐字节一致，无漂移。
- base HEAD `45154597` = `gateflow: record slice-2.3 item4 acceptance`，与 fix §1 和 target metadata 一致。
- target 和 master 在 working tree 中有 uncommitted diff（来自本轮 corrective fix 写回），SHA 验证针对当前 working tree 字节。
- 旧两份 MiMo review 分别使用 pre-correction 和 intermediate SHA，均不匹配本轮 final frozen 三SHA，结论不继承。

## 2. Motivation & Architecture Review

### 2.1 Protocol Import Set（fix §2 S23-I5-PROTOCOL-OWNER-01 / target §3.3 lines 773–778 + §9 lines 2141–2168）

**Finding S23-I5-PROTOCOL-OWNER-01 — 已修复 — 高**

fix 声称：target 旧版 §3.3 的 protocol-only import set 遗漏 `uuid.UUID` 和 `source.SourceSubscriptionId`，并误列无 annotation 的 `source_sync.py`。

**独立验证（从三 SHA 直接读取，不继承旧 review）**：

1. target §3.3 lines 773–778 冻结 protocol-only exact direct-import manifest：
   - `typing.Protocol/runtime_checkable`
   - `uuid.UUID`
   - `identifiers.TenantScope`
   - `source.SourceSubscriptionId`
   - `source_payload.SourceExecutionBinding`
   - `source_evidence.SourceSyncAttemptReceipt`
   - 四个 health DTO（`SourceHealthProjection`, `SourceHealthReenableRequest`, `SourceHealthSnapshotCursor`, `SourceHealthSnapshotPage`）
   - 四个 operation DTO（`SourceOperationAcquireDecision`, `SourceOperationAcquireRequest`, `SourceTerminalRecordDecision`, `SourceTerminalRecordRequest`）

2. target §9 lines 2149–2168 提供完整 Python import block，与 §3.3 exact-equal。

3. 七方法 annotation 逐项核对：
   - `UUID`：`get_source_receipt` 的 `source_sync_run_id: UUID`（line 2201）✅
   - `SourceSubscriptionId`：`get_executable_binding`（line 2183）、`get_health`（line 2207）、`list_health_snapshots`（line 2213）✅
   - `SourceExecutionBinding`：`get_executable_binding` 返回值（line 2184）✅
   - `SourceSyncAttemptReceipt`：`get_source_receipt` 返回值（line 2202）✅
   - 四个 health DTO：`get_health`/`list_health_snapshots`/`reenable_health` 参数与返回值 ✅
   - 四个 operation DTO：`acquire_operation`/`record_terminal` 参数与返回值 ✅

4. `source_sync.py` 不拥有上述任何一个 annotation type。它只含 closed exceptions（`SourceSyncErrorCode`, `SourceSyncRequestRejected`, `SourceSyncExecutionRejected`, `SourceSyncRepositoryFailure`, `SourceServiceInputError`, `SourceServiceUnavailableError`），属于 concrete 行为合同。

5. 禁止 escape routes 明确列出：无 `TYPE_CHECKING`、无字符串 literal annotation、无 lazy/dynamic import、无 package root re-export、无别名复制。`from __future__ import annotations` 可选但不豁免 runtime direct import。`typing.get_type_hints` 必须解析到 canonical owner。

**裁决**：accepted。exact import set 完整覆盖七方法 annotation，无遗漏、无多余。

### 2.2 Concrete Class & Constructor（fix §2 S23-I5-CONCRETE-CONSTRUCTOR-02 / target §9 lines 2226–2243）

**Finding S23-I5-CONCRETE-CONSTRUCTOR-02 — 已修复 — 高**

fix 声称：target 从未冻结 `PostgresSourceSyncRepository` 类名或 constructor。

**独立验证**：

1. target §9 lines 2226–2233 冻结：
   ```python
   class PostgresSourceSyncRepository(SourceSyncRepositoryProtocol):
       def __init__(self, session_factory: sessionmaker[Session]) -> None: ...
   ```

2. constructor 约束（lines 2236–2237）：只接受 `sessionmaker[Session]`，禁止 `Engine`、open `Session`、clock/UUID callback、settings、repository/provider bag、optional setter。

3. platform convention 核对：
   - `PostgresJobStore` constructor = `session_factory: sessionmaker[Session]`（`postgres_jobs.py:580`）
   - `PostgresScheduleStore` constructor = `session_factory: sessionmaker[Session]`（`postgres_schedules.py:1253`）
   - 完全一致 ✅

4. concrete 七方法 annotation 与 protocol 逐项相同，从 canonical domain owner 直接 import。从 `source_sync_protocols.py` 只 import `SourceSyncRepositoryProtocol`。SQLAlchemy/psycopg 只停留在 concrete。`source_sync.py` closed exceptions 只由 concrete 按行为分支 import。

5. `storage/protocols.py` 与 `storage/__init__.py` 均不得 import/re-export 该协议或 concrete。

**裁决**：accepted。constructor 零 I/O、零 optional dependency、零 setter，与 platform convention 一致。

### 2.3 Item 4 Dependency Gate（fix §2 S23-I5-ITEM4-DEPENDENCY-03 / target §12 lines 2586–2613）

**Finding S23-I5-ITEM4-DEPENDENCY-03 — 已修复 — 高**

fix 声称：Item 5 不得绑定未 accepted 的 moving schema bytes。

**独立验证**：

1. git log 确认两个 commit 存在：
   - `4101fb6` = `gateflow: accept slice-2.3 item4 source schema`（semantic code）
   - `4515459` = `gateflow: record slice-2.3 item4 acceptance`（metadata, HEAD）

2. target §12 lines 2586–2607 冻结 exact 五项 manifest：
   1. `item4_accepted_commit` = `4101fb6da02eb08ddd245561a92e021046fdeccb` ✅
   2. `item4_migration_sha256` = `90b66245012ea33eb97fa7f222b8744b48b4d9cf12a2ff5a51c9d2ff04e23b09`（`0005_source_connectors_health.py`, 2674行）✅
   3. `item4_models_identity_sha256` = `d3e034f88aac1575637b1eb8bc36d44395279455a17a90de34408fb9b84f16fd`（`models_identity.py`, 908行）✅
   4. `item4_acceptance_artifact` = `docs/reviews/slice-2.3-item4-source-schema-code-acceptance-20260813-codex.md` / SHA-256 `a61382414b548dd3237121c6bb94bf0935be480999a53c6bab3322746fd486ce` / 117行 / `PASS` ✅
   5. `item4_final_review_artifacts` = (`docs/reviews/code-review-20260813-item4-schema-candidate9-final.md`, `a6aed10b0ef1b0b894a62b3f9d56c689f01dda66b76217d21e09a02696325bf1`, `PASS / open H/M/L=0/0/0`, 37行) ✅

3. disk 验证：acceptance artifact SHA-256 = `a613824…` / 117行；final review artifact SHA-256 = `a6aed10…` / 37行 — 逐字节一致。

4. 0004 STOP：target line 2610–2611 明确 repository 只面向 0005 head，不查 `alembic_version`、不尝试 0004 fallback、不 catch undefined-table/column 后切换 SQL、不回改 0005 migration/models。

5. fix 不读取或伪造任何 Item 4 字节，不从 working tree 推导 SHA。

**裁决**：accepted。五项 manifest 逐 SHA 验证通过，0004 STOP 正确。

### 2.4 Coverage Owner Tuple（fix §3 S23-I5-COVERAGE-OWNER-04 / target §11.1 line 2506 + §11 lines 2547–2558）

**Finding S23-I5-COVERAGE-OWNER-04 — 已修复 — 高**

fix 声称：旧 tuple (`tests/investment/test_source_sync_storage_protocols.py`, `tests/application/test_source_sync_execution.py`) 第二项在 HEAD 不存在且不属于 Item 5 exact 五 path。

**独立验证**：

1. `tests/application/test_source_sync_execution.py` 在 HEAD `45154597` **NOT FOUND** — 确认不存在。

2. Item 5 exact 五 path（target lines 2551–2555）：
   1. `dayu/investment/storage/source_sync_protocols.py` — **NOT FOUND**（planned-new）✅
   2. `dayu/investment/storage/postgres_sources.py` — **NOT FOUND**（planned-new）✅
   3. `tests/investment/test_source_sync_storage_protocols.py` — **NOT FOUND**（planned-new）✅
   4. `tests/integration/investment/test_postgres_sources.py` — **NOT FOUND**（planned-new）✅
   5. `tests/investment/test_architecture_boundaries.py` — **EXISTS**（既有）✅

3. `test_source_sync_execution.py` 不在上述五 path 内。若保留旧二元组，Gate 1 全 member collect 会确定性 fail closed。

4. target line 2506 修正后：`source_sync_protocols.py` → (`tests/investment/test_source_sync_storage_protocols.py`,) — singleton。

5. §11.1 `COVERAGE_OWNER_TESTS` 精确 43 keys — disk 计数确认 43 行 key（不含 header）。其余 42 个 tuple 不变。

6. 新增 named test：`test_postgres_source_sync_repository_class_and_session_factory_constructor_are_exact`（target line 2660）— 位于 §13 已规划 `tests/integration/investment/test_postgres_sources.py`，不新增 lane。

7. named-test catalog：158→159（target line 3096 确认）。

**裁决**：accepted。singleton direct owner 是满足同一 branch gate 的最小修正，不提前创建 future test、不扩大 exact 五 path。

## 3. Best Practice / Optimality / Coupling

- **Architecture boundary**：protocol 只暴露 pure DTO，concrete 独占 SQLAlchemy/psycopg；Service 只依赖 protocol。依赖方向不反转。✅
- **Best practice**：从 canonical owner direct import 使 Pyright/runtime type hints/AST ownership 三者同源。单一 session factory 与既有 Postgres stores 一致。✅
- **Optimality**：修改 exact manifest/constructor/一个 tuple 比新增 adapter/re-export/dependency bag 更小。✅
- **Overengineering**：拒绝为未 accepted 的 schema 增加 revision detector、dual SQL、clock/UUID injection 或第二 concrete。✅
- **Overcoupling**：Item 4 通过 immutable accepted manifest 成为前置证据，Item 5 不回写 migration/models。Item 6 execution test 不反向耦合 protocol owner gate。✅

## 4. Codegen Readiness

- 七方法 exact signature + exact import block → implementation agent 可机械生成 `source_sync_protocols.py`。
- `PostgresSourceSyncRepository` class/constructor frozen → 可机械生成 `postgres_sources.py`。
- Item 4 dependency manifest 五项 SHA 是确定性 STOP → 不存在歧义。
- §13 named test catalog 159 项 → 可机械验证。
- constructor zero-I/O trap → 可机械测试。
- 五个 path 中四个 planned-new、一个既有 → 可机械确认 write scope。

## 5. Slice Sequencing

- Item 1 accepted `4cfb932`、Item 2 accepted `e3167d7`、Item 3 `595564e`、Item 4 semantic `4101fb6` + metadata `4515459`（HEAD）。✅
- Item 5 保持 frozen 直到 fresh same-new-SHA 双审 PASS、Controller acceptance 与 local accepted corrective-plan commit 完成。✅
- fix 不宣称 review pass、Item 4 accepted 或 Item 5 implementation 获授权。✅

## 6. Test / Allowlist / Coverage

- named-test catalog：158→159，唯一新增 `test_postgres_source_sync_repository_class_and_session_factory_constructor_are_exact`。✅
- §11 production/test allowlist 零增删。✅
- §11.1 `COVERAGE_OWNER_TESTS` 精确 43 keys 零增减，唯一 tuple 修正 `source_sync_protocols.py` → singleton。✅
- 其余 42 个 tuple byte-equivalent 不变。✅
- Item 5 exact writer 仍只有五个既有 path。✅
- 四个 planned-new 文件在 HEAD 均不存在，不构成 stale ref。✅

## 7. Target / Master / Fix Consistency

- target §3.3（lines 773–778）已包含 exact import set。✅
- target §9（lines 2149–2168）已包含完整 Python import block。✅
- target §9（lines 2226–2233）已包含 `PostgresSourceSyncRepository` + `sessionmaker[Session]` constructor。✅
- target §12（lines 2586–2613）已包含 Item 4 dependency manifest 五项 STOP。✅
- target §13（line 2660）已包含新增 test name。✅
- target §11（lines 2547–2558）确认零 allowlist 扩张与 tuple 修正。✅
- master §0（lines 284–301）确认 Item 5 corrective decision 与 target/fix 一致。✅
- master revision changelog（lines 4063–4076）确认 Item 5 corrective decision 与 fix 一致。✅
- fix §2 evidence table 与 target 实际字节一致。✅
- 三份文档内部一致，无冲突。✅

## 8. Stale References

- `source_sync_protocols.py`、`postgres_sources.py`、`test_source_sync_storage_protocols.py`、`test_postgres_sources.py`：planned-new，HEAD 不存在，不构成 stale ref。✅
- `test_source_sync_execution.py`：HEAD 不存在，已从 protocol coverage tuple 移除。✅
- `test_architecture_boundaries.py`：HEAD EXISTS，是既有 path。✅

## 9. Item 4 Source/Test as Foreign Scope

- fix 不读取、不引用、不编辑任何 Item 4 production/test/migration 字节。✅
- Item 4 dependency manifest 只从已提交的两个 commit 读取，不从 working tree 推导。✅
- 0004 runtime fallback 明确禁止（target line 2610–2611）。✅

## 10. Open Questions

| # | Severity | Question | Resolution |
|---|---|---|---|
| — | — | 无 blocking open question | — |

Item 4 exact 五项 SHA manifest 已闭合，coverage-owner 修正已冻结。当前未满足的是 fresh same-new-SHA 双审 PASS（本文即其一）、Controller acceptance 与 local accepted corrective-plan commit。这些是 deterministic implementation prerequisites，不是 open questions。

## 11. Finding Summary

| ID | Title | Severity | Status |
|---|---|---|---|
| S23-I5-PROTOCOL-OWNER-01 | closed import set 遗漏真实 annotation owner 并误列 source_sync | 高 | 已修复 ✅ |
| S23-I5-CONCRETE-CONSTRUCTOR-02 | authoritative plan 未冻结 repository 类与 constructor | 高 | 已修复 ✅ |
| S23-I5-ITEM4-DEPENDENCY-03 | Item 5 不得绑定未 accepted 的 moving schema bytes | 高 | 已修复 ✅ |
| S23-I5-COVERAGE-OWNER-04 | protocol owner tuple 依赖不存在且不可由 Item 5 写入的 future test | 高 | 已修复 ✅ |

**Open H/M/L: 0/0/0**

## 12. Conclusion

**PASS**

四个 Item 5 constructibility blocker（protocol import set、concrete constructor、Item 4 dependency gate、coverage-owner tuple）已在 docs candidate 中闭合。target/master/fix 三份 FINAL FROZEN semantic 字节 SHA-256/lines 逐字节验证通过，三者内部一致。protocol exact direct imports 完整覆盖七方法 annotation 需求，concrete class/constructor 冻结并与 platform convention 一致，Item 4 五项 dependency manifest 已闭合且 0004 STOP 正确。43 keys 零增减、唯一 tuple 修正为 singleton direct owner、其余 42 tuple 不变、allowlist 零扩张、Item 5 exact 五 path 不变、159 项 named catalog 不变。

本 review 只证明上述三 SHA 的 semantic 合格性，不授权 Item 5 implementation、Item 4 accepted 或任何 commit/push/PR。下一入口是 Controller acceptance + local accepted corrective-plan commit。

---

**SHA-256 verification snapshot**：
- target: `66845a72f528b5955209de935dd798d01ad8fbdb35ab3c10db42fb5fd07986f1` / 3111行
- master: `2a4e5e60510f12b5dd51b3279cc1f8118e609ff557a3a086ec10521ee3aecdf8` / 4371行
- fix: `615d99975ab3e104539464f14e17bfa7761b12d49538674e211fb43ceeca2ca3` / 221行
- base HEAD: `45154597d3d01be13287393f4123003a1444f0eb`
