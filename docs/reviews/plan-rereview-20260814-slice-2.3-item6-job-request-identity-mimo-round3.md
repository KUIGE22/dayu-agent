# Slice 2.3 Item 6 Job Request Identity — Fresh Independent Round 3 Plan Re-Review (MiMo)

- 本机时间：`2026-08-14`（Asia/Shanghai）
- 角色：独立 plan reviewer；只审计划与已存在代码事实，不实施、不修计划
- 分支：`codex/investment-platform`
- 基线 HEAD：`4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723`
- Frozen reviewed target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
  - SHA-256：`f641eb210953a60756c8ff2ed36eea34e0a5c429457e846941b531a5a7b32c29`
  - 行数：`3536`
- Frozen master：`docs/plans/2026-08-10-investment-platform-restoration.md`
  - SHA-256：`18ae04a6e759737f5a37fa2c07cbd2f7e6f083a577e05d0e5b183b83b4d2b2a8`
  - 行数：`4475`
- Frozen fix：`docs/reviews/plan-fix-20260814-slice-2.3-item6-job-request-identity-codex.md`
  - SHA-256：`b07f89affe919bc7dccff98211eda9a322d0dc682f89691c0b920c466b346780`
  - 行数：`288`
- Immutable source formal review：`docs/reviews/plan-review-20260813-234659.md`
  - SHA-256：`4d27271b57f7cbb1bfcd2065ecdf1bd08da0459782e6ab7a76ac3358019edbe0`
  - 行数：`227`
  - 结论：`FAIL / open H/M/L=2/3/0`
- Superseded/rejected old MiMo artifacts（不inform本结论）：
  - Round 1：`docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo.md`，
    SHA-256 `ac1193fe28cd02a3a06df5ba1ae67f380dd22e5f9239a159dd2903025cc0ba22` / 218行，
    状态 `SUPERSEDED / REJECTED / IMMUTABLE`（漏后续 accepted 1H/1M）。
  - Round 2：`docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo-round2.md`，
    SHA-256 `dc849d2d60184beb0dcaeeaf20711435706804b40995fdc4ce03a19062d2b139` / 312行，
    状态 `SUPERSEDED / REJECTED / IMMUTABLE`（漏后续 Round 3 accepted 2H/2M）。
- 外部边界：未编辑 reviewed docs/code/tests，未运行 PG/network/provider/model，未 stage/commit/push/PR。

## 1. Review scope

本 re-review 对 Round 3 corrective candidate 执行 fresh independent 审查，覆盖：

- 原始正式 review 五项 finding（`S23-I6-PLAN-01`..`S23-I6-PLAN-05`）的修复充分性；
- Round 1 internal redteam 一项 accepted finding（`S23-I6-REDTEAM-R2-01`）的修复充分性；
- Round 1 internal redteam 一项 accepted finding（`S23-I6-REDTEAM-R2-02`）的修复充分性；
- Round 3 internal redteam 四项 accepted finding（`S23-I6-REDTEAM-R3-01`..`S23-I6-REDTEAM-R3-04`）的修复充分性；
- exact 12 path scope（production/test 10 + docs 2，workflow deferred Item 8）；
- strict UTF-8 closed canonical JSON parse/re-encode before fingerprint 与 new-enqueue；
- 0006 fields/objects/locks/admission/downgrade；
- payload schema mismatch 合法性与 fingerprint 完整性；
- definition observable boundary 与 cross-definition same-key；
- cron owner/order 与 schedule taxonomy；
- 44 keys、six owners、nine lanes、174 exact names、dedicated owner；
- source hostile tests 覆盖；
- Item 4/5 evidence reopening 与 linear sequence；
- prerequisite test boundary vs future lookup surface；
- README owner completeness。

直接代码事实取自 HEAD `4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723`。

## 2. Frozen byte verification

| Artifact | Expected SHA-256 | Expected lines | Actual SHA-256 | Actual lines | Status |
|---|---|---:|---|---:|---|
| target | `f641eb21…b32c29` | 3536 | `f641eb21…b32c29` | 3536 | ✅ MATCH |
| master | `18ae04a6…b2a8` | 4475 | `18ae04a6…b2a8` | 4475 | ✅ MATCH |
| fix | `b07f89af…46780` | 288 | `b07f89af…46780` | 288 | ✅ MATCH |
| formal source | `4d27271b…dbe0` | 227 | `4d27271b…dbe0` | 227 | ✅ MATCH |
| old MiMo R1 | `ac1193fe…ba22` | 218 | `ac1193fe…ba22` | 218 | ✅ MATCH |
| old MiMo R2 | `dc849d2d…b139` | 312 | `dc849d2d…b139` | 312 | ✅ MATCH |

**零字节漂移。无 STOP 条件。**

## 3. Old MiMo verdict identity verification

两份 old MiMo artifact 仅验证 identity 与 rejected 状态，不采信其内容：

1. Round 1 `ac1193fe…` / 218行：self-claimed `PASS / 0/0/0`，但 fix §1.1 证明遗漏后续 accepted `S23-I6-REDTEAM-R2-01`（1H）与 `S23-I6-REDTEAM-R2-02`（1M），状态精确为 `SUPERSEDED / REJECTED / IMMUTABLE`。**确认 rejected。**
2. Round 2 `dc849d2d…` / 312行：self-claimed `PASS / 0/0/0`，但 fix §1.2 证明遗漏后续 accepted `S23-I6-REDTEAM-R3-01`..`R3-04`（2H/2M），状态精确为 `SUPERSEDED / REJECTED / IMMUTABLE`。**确认 rejected。**

## 4. Source code fact verification

独立验证直接代码事实（与 formal review §1 交叉确认）：

| File | Formal review lines | Actual lines | Match |
|---|---:|---:|---|
| `0003_durable_jobs.py` | 1032 | 1032 | ✅ |
| `0005_source_connectors_health.py` | 2674 | — | (not re-verified, not in scope) |
| `jobs.py` | 2147 | 2147 | ✅ |
| `postgres_jobs.py` | 5354 | 5354 | ✅ |
| `postgres_sources.py` | 3004 | 3004 | ✅ |

`0003_durable_jobs.py:189` 确认 `available_at TIMESTAMPTZ NOT NULL`（单一列，无 `original_available_at`）。`jobs.py:2048` 确认 `job_enqueue_request_fingerprint` 函数存在。`postgres_jobs.py` 确认为 raw SQL Job owner。

## 5. Per-finding re-verification

### 5.1 S23-I6-PLAN-01 [高] — mutable retry `available_at` 与 immutable original seed 分离

**原始问题**：`job_runs.available_at` 同时承担首次 enqueue seed 与 retry eligibility，response-loss/takeover/cross-midnight 合同不可实现。

**Fix 验证**：

- target §8.6：0006 新增 `original_available_at TIMESTAMPTZ` 列，mutable `available_at` 只负责 retry eligibility；
- target §3.4：`JobIdempotencyRecord` 新增 `original_available_at: datetime` 字段；
- target §3.5：query window 改读 `job_runs.original_available_at`；
- target §5.1：manual recovery 以 `original_available_at` 重建 fingerprint；
- target §6.2：scheduled acquire 从 locked `job_runs.original_available_at` 构造 authoritative snapshot；
- target §13.4：新增 `test_cross_midnight_retry_never_moves_original_available_at_seeded_source_query_window`、`test_manual_retry_across_utc_midnight_keeps_original_available_at_for_existing_operation_provenance`、`test_scheduled_retry_before_first_acquire_and_existing_takeover_use_original_available_at_seed`；
- fix §3.1/§3.3：confirmed。
- 0006 immutable trigger `guard_job_runs_request_identity_immutable_trigger` 阻止 original 列被 UPDATE。
- app role 不获得三个新列的 UPDATE 权限。

**结论**：**已修复。** original durable fact 已独立于 mutable retry state，hostile tests 覆盖 cross-UTC/takeover/pre-first-acquire。

### 5.2 S23-I6-PLAN-02 [高] — request payload schema identity 成为 durable fact

**原始问题**：fingerprint 包含 request payload schema name/version，但 `job_runs` 未持久化，且当前允许与 descriptor 不同。

**Fix 验证**：

- target §8.6：0006 新增 `request_payload_schema_name TEXT` 与 `request_payload_schema_version INTEGER`；
- target §3.4：fingerprint 算法保留 payload schema 字段，不删减，不加入 idempotency key；
- target §8.6 upgrade step 3：migration-local fingerprint reproducer 与 domain `job_enqueue_request_fingerprint` 逐 key 等值，含 request payload schema name/version；
- fix §1.2/§3.2：generic mismatch 继续合法，不新增 equality admission；
- target §13.4：`test_0006_proven_backfill_persists_original_available_and_request_payload_schema_identity` 参数化覆盖 equal/mismatch/drift。

**结论**：**已修复。** payload schema identity 已持久化，generic mismatch 合法保留，migration reproducer 与 domain 逐值等同。

### 5.3 S23-I6-PLAN-03 [中] — lookup 合同收窄到可观察 definition scope

**原始问题**：exact descriptor+key lookup 无法区分合法 cross-definition same-key 与被重定向的 definition identity。

**Fix 验证**：

- target §3.4：lookup 先用 tenant + exact descriptor 解析 definition，再查 `(tenant_id, resolved_definition_id, idempotency_key)`；cross-tenant/missing 等价 None；
- target §3.4："其它合法 definition 下同 key 的 row 不影响结果"；"cross-definition relocation 在此 surface 不可观察，按 exact definition/key missing 处理"；
- target §3.4："禁止为检测它改成 tenant-global key unique 或把合法 B/K 误报 tamper"；
- target §13.1：`test_postgres_job_idempotency_lookup_exact_missing_cross_tenant_and_persisted_drift` 覆盖 missing/cross-tenant/persisted drift。

**结论**：**已修复。** 可观察边界已诚实划定，合法 cross-definition 不误判。

### 5.4 S23-I6-PLAN-04 [中] — cron 语义由 Schedule owner 经窄 public seam 提供

**原始问题**：Source facade 需做 cron preflight，但唯一 croniter owner 是 ScheduleService 私有 helper。

**Fix 验证**：

- target §3.3：`SourceScheduleGatewayProtocol` 新增 `validate_cron_expression(self, expression: str) -> None`；
- target §5.2："`ScheduleService.validate_cron_expression(expression: str) -> None` 是唯一 public validation-only seam，精确调用既有 `_validate_croniter_expression`，不调用 Store、不读取 clock、不改变状态"；
- target §5.2 ordering："先做不读 mutable source state 的 request shape/tz 验证...随后精确调用一次 `ScheduleService.validate_cron_expression`，它必须先于 `get_by_key` 与任何 source read"；
- target §13.1：`test_schedule_validation_only_cron_seam_reuses_owner_without_store_clock_or_mutation`、`test_polling_schedule_cron_validation_precedes_lookup_and_source_reads_for_hit_and_miss`。

**结论**：**已修复。** 唯一窄 public seam 已定义，ordering 已冻结，hit/miss 均为 `ScheduleInputError`。

### 5.5 S23-I6-PLAN-05 [中] — schema-valid conflict 与 malformed persisted row 已分流

**原始问题**：schedule "任一 immutable drift" 未区分 schema-valid caller drift 与 malformed persisted row。

**Fix 验证**：

- target §5.2："Store 必须先 strict 重建完整 `ScheduleDefinition`；unknown/single-valued misfire tamper、invalid cron/timezone、noncanonical payload/hash 或其它 malformed persisted shape 先成为 `ScheduleRepositoryError`。只有 request 与 persisted row 均为当前 schema-valid 完整 DTO 时，逐字段 immutable 不同才为 `ScheduleVersionConflictError`"；
- target §13.1：`test_schedule_schema_valid_immutable_conflict_is_distinct_from_malformed_persisted_row`。

**结论**：**已修复。** strict reconstruction 先行，malformed → unavailable，schema-valid drift → conflict。

### 5.6 S23-I6-REDTEAM-R2-01 [高] — prerequisite 未授权 CI/README owner

**原始问题**：0006 prerequisite 漏授权 CI workflow 与 README path。

**Fix 验证**：

- target §8.6："本 corrective prerequisite 精确十二个 writable path：exact 十个 production/test path 加两个 docs path"；
- target §8.6 列表包含 `tests/README.md`、`dayu/investment/README.md`；
- target §8.6：CI workflow 在 prerequisite 和 Item 6 main incremental gate 保持 zero diff；final nine commands/ignores 只在 Item 8 materialize；
- fix §1.1 confirmed。

**结论**：**已修复。** exact 12 paths 已明确（R3 收敛自 R2 的 13），CI workflow deferred Item 8，README owner 完整。

### 5.7 S23-I6-REDTEAM-R2-02 [中] — fingerprint 前未证明 payload canonical bytes

**原始问题**：migration admission 漏 strict canonical payload 证明。

**Fix 验证**：

- target §8.6 upgrade step 2："先验证 raw payload bytes SHA-256 等于 stored payload_sha256，随后执行 migration-local、与 domain `parse_canonical_document` 等值的 strict canonical JSON admission：bytes 必须是 exact UTF-8、无 BOM/duplicate key/trailing bytes；只允许 closed null/bool/int/string/array/object primitive tree，拒绝 float/NaN/Infinity、非 string object key 与 domain closed sensitive key；再按 `sort_keys=True`、compact separators、`ensure_ascii=False` 重编码，且 re-encoded bytes 必须与 raw bytes 逐字节相等"；
- target §8.6 upgrade step 4："任一 row 不等即整次 upgrade fail closed"；
- target §13.4：`test_0006_proven_backfill_persists_original_available_and_request_payload_schema_identity` 参数化覆盖 "canonical success、invalid UTF-8/closed primitive、bytes/SHA drift、SHA 自洽但 noncanonical JSON、duplicate key/BOM/trailing bytes 与 canonical re-encode drift"。

**结论**：**已修复。** strict UTF-8 closed canonical admission 已在 fingerprint 之前，negative cases 均证明无 partial DDL/identity write。

### 5.8 S23-I6-REDTEAM-R3-01 [高] — future workflows 错误纳入 prerequisite

**原始问题**：prerequisite 纳入 CI workflow 但 workflow mutation 属于 future Item 8。

**Fix 验证**：

- target §8.6：prerequisite exact 12 paths（production/test 10 + docs 2），CI workflow 不在其中；
- target §8.6：两份 workflow 在 prerequisite 和 Item 6 main incremental gate 必须 zero diff；
- target §12/§14：final nine commands/ignores、workflow static audit、tests/README final CI 只在 Item 8；
- fix §4 confirmed。

**结论**：**已修复。** scope 收敛 exact 12，workflow zero diff，final lanes deferred Item 8。

### 5.9 S23-I6-REDTEAM-R3-02 [高] — new enqueue 缺 pre-session canonical admission

**原始问题**：`PostgresJobStore.enqueue` 在 fingerprint/SQL/publish 前未验证 payload canonical。

**Fix 验证**：

- target §3.4："PostgresJobStore.enqueue 是唯一 validation owner；JobService 不复制"；
- target §3.4："在 fingerprint helper、session factory、任何 SQL/DML 或可能 publish 的返回之前，strict UTF-8 decode request payload，执行 domain-equivalent canonical parse/re-encode，并要求 returned bytes/SHA 等于 request bytes/SHA"；
- target §3.4："invalid UTF-8、sensitive/unsupported/float、duplicate/BOM/trailing、noncanonical/self-consistent bytes 或 bytes/SHA drift 统一 closed `JobInputError`；fingerprint/session/row/publisher 均零调用"；
- target §13.4：`test_new_enqueue_strictly_validates_canonical_payload_before_session_fingerprint_or_publish_and_persists_original_identity`；
- fix §3.4.1 confirmed。

**结论**：**已修复。** PostgresJobStore 是唯一 pre-session canonical admission owner，closed input/zero side effect。

### 5.10 S23-I6-REDTEAM-R3-03 [中] — prerequisite test 越界要求 future lookup

**原始问题**：prerequisite retry test 要求 future `JobIdempotencyRecord`/lookup surface。

**Fix 验证**：

- target §3.4.2："Prerequisite 只负责 0006 schema/migration、enqueue canonical admission 与三列 insert、retry 保持 original columns、Source provenance 改读 original 列"；
- target §3.4.2："`JobIdempotencyRecord`、storage/service protocol lookup、JobService lookup 与 Source facade recovery 仍全部属于 Item 6 main"；
- target §3.4.2："Prerequisite renamed retry test 直接读取 durable columns；不得构造或调用 future lookup surface"；
- target §13.4：`test_retry_mutates_only_current_available_at_and_preserves_original_request_identity_columns`；
- fix §3.4.2 confirmed。

**结论**：**已修复。** prerequisite test 只证明 durable columns 持久化，不涉及 future lookup。

### 5.11 S23-I6-REDTEAM-R3-04 [中] — investment README owner 遗漏

**原始问题**：prerequisite docs 只有 tests README，缺 investment README。

**Fix 验证**：

- target §8.6 exact 12 paths 包含 `tests/README.md` 与 `dayu/investment/README.md`；
- target §8.6："`dayu/investment/README.md` 只同步 0006 schema、new-enqueue/backfill canonical admission 和 dedicated local lane"；
- target §8.6："根 `README.md` 保持 zero diff"；
- fix §4 confirmed。

**结论**：**已修复。** 两个 README owner 完整，root README zero diff。

## 6. Cross-cutting verification

### 6.1 Exact 12 path scope

target §8.6 列出：

- Production（4）：`0006_job_request_identity.py`、`platform_jobs.py`、`postgres_jobs.py`、`postgres_sources.py`；
- Tests（6）：`test_platform_jobs.py`、`test_platform_migrations.py`、`test_platform_migrations_postgres.py`、`test_job_request_identity_migration_postgres.py`、`test_postgres_jobs.py`、`test_postgres_sources.py`；
- Docs（2）：`tests/README.md`、`dayu/investment/README.md`。

合计 12。两份 CI workflow 保持 zero diff。**PASS**。

### 6.2 Strict UTF-8 closed canonical JSON parse/re-encode before fingerprint

target §8.6 upgrade step 2–3 明确要求：

1. raw bytes SHA-256 == stored payload_sha256；
2. strict canonical JSON admission：UTF-8、无 BOM/duplicate key/trailing bytes、closed primitive tree、拒绝 float/NaN/Infinity/non-string key/sensitive key；
3. re-encode `sort_keys=True, separators=(',',':'), ensure_ascii=False`；
4. re-encoded bytes == raw bytes（逐字节）；
5. 只有 admission 通过后才重算 fingerprint。

target §3.4.1 new-enqueue 同样要求上述 canonical admission 在 fingerprint/session/SQL/publish 前执行。

**PASS**。

### 6.3 0006 fields/objects/locks/admission/downgrade

- 三列：`original_available_at TIMESTAMPTZ`、`request_payload_schema_name TEXT`、`request_payload_schema_version INTEGER`（均最终 NOT NULL）；
- 五对象：三 CHECK + function + trigger，manifest 唯一；
- Locks：NOWAIT `job_runs` → `job_definitions`，conflict 整次 fail closed；
- Admission：SHA → canonical admission → fingerprint reproducer → proof-or-fail；
- Downgrade：NOWAIT locks + `pg_depend` preflight + `job_runs` 精确为空 + 逆序 drop + 禁 CASCADE。

**PASS**。

### 6.4 Payload schema mismatch

- target §3.4："generic payload/descriptor schema mismatch 继续合法；不新增 equality admission，不删 fingerprint 输入字段"；
- fingerprint 包含 `request_payload_schema_name` 与 `request_payload_schema_version`；
- migration 用 definition schema 作为候选，只在 fingerprint 证明时 backfill。

**PASS**。

### 6.5 Definition observable boundary

- target §3.4："exact definition/key missing 或 cross-tenant 均返回 None"；"cross-definition relocation 在此 surface 不可观察"；"禁止 tenant-wide key scan、tenant-global unique 或把合法 B/K 误报 tamper"；
- 可证明 drift 只覆盖命中 exact row 内部。

**PASS**。

### 6.6 Cron owner/order

- `ScheduleService.validate_cron_expression(str) -> None`：唯一 public validation-only seam，复用 private croniter helper，零 Store/零 clock/零 mutation；
- Ordering：structural/tz → `validate_cron_expression` → `get_by_key` → source read；
- hit/miss 均为 `ScheduleInputError`；
- Source facade 不 import croniter/private helper，不复制语义。

**PASS**。

### 6.7 Schedule taxonomy

- schema-valid 两份完整 DTO immutable drift → `ScheduleVersionConflictError`；
- malformed（unknown misfire/invalid cron/timezone/noncanonical payload/hash）→ `ScheduleRepositoryError` → `SourceServiceUnavailableError(unavailable)`；
- test 覆盖 `test_schedule_schema_valid_immutable_conflict_is_distinct_from_malformed_persisted_row`。

**PASS**。

### 6.8 44 keys、six owners、nine lanes、174 exact names

- target §11.1：44 exact keys（29 tracked-existing + 15 planned-new）；
- target §14 Gate 2：六个 concrete PG/migration owners（0005/0006/identity/jobs/schedules/sources）；
- target §14：九个 isolated lanes（六个 PG + source-sync-job + MinIO + Redis）；
- target §13：174 exact names（原 159 + 15 新增，两个 rename 不增量）。

**PASS**。

### 6.9 Dedicated owner

- `test_job_request_identity_migration_postgres.py` 是 0006 唯一 instrumented PG owner；
- `test_platform_migrations_postgres.py` 继续是 0005 owner；
- 两个 migration 不共享 process 或 coverage 分母。

**PASS**。

### 6.10 Source hostile tests

- `test_cross_midnight_retry_never_moves_original_available_at_seeded_source_query_window`：跨 UTC 午夜 retry；
- `test_manual_retry_across_utc_midnight_keeps_original_available_at_for_existing_operation_provenance`：manual existing-operation 跨 UTC retry 零假 drift；
- `test_scheduled_retry_before_first_acquire_and_existing_takeover_use_original_available_at_seed`：scheduled 首次 acquire 前 retry 与 existing takeover 均用 original seed。

**PASS**。

### 6.11 Item 4/5 evidence reopening 与 linear sequence

- target §12："Item 4 的 0005 full-chain migration owner 因 head/cycle assertion 更新而需 fresh 运行"；
- target §12："Item 5 的 `postgres_sources.py` 与其 PG owner 因 provenance 改读 `original_available_at` 而需 fresh review/coverage/PG"；
- linear sequence：① docs-only freeze → ② fresh dual review PASS → ③ Controller acceptance + local commit → ④ 0006 prerequisite → ⑤ Item 6 main writer。

**PASS**。

### 6.12 Workflow zero-diff and final nine lanes deferred Item 8

- target §8.6："两份 `.github/workflows/ci-pr-extended.yml`/`ci-mainline.yml` 在 prerequisite 与 Item 6 main incremental gate 都必须 zero diff"；
- target §8.6："不得提前物化、要求或执行 planned `test_ci_extended_workflows_pull_three_pinned_images_isolate_nine_lanes_and_ignore_each_from_aggregate`"；
- target §12/§14：final nine commands/ignores、workflow static audit、tests/README final CI 只在 Item 8 运行。

**PASS**。

### 6.13 New-enqueue strict canonical admission

- target §3.4/§3.4.1：PostgresJobStore 是唯一 owner；
- 严格 UTF-8 decode → domain-equivalent canonical parse/re-encode → bytes/SHA identity；
- invalid UTF-8、sensitive/unsupported/float、duplicate/BOM/trailing、noncanonical/self-consistent bytes、bytes/SHA drift → closed `JobInputError`；
- fingerprint/session/SQL/publisher 均零调用；
- test `test_new_enqueue_strictly_validates_canonical_payload_before_session_fingerprint_or_publish_and_persists_original_identity` 覆盖 Store direct 与 JobService caller。

**PASS**。

### 6.14 Migration backfill admission

- target §8.6 upgrade step 2–4：每 row 先验证 bytes SHA → strict canonical admission → fingerprint reproducer → proof-or-fail；
- negative cases：invalid UTF-8、closed primitive violation、bytes/SHA drift、SHA 自洽但 noncanonical JSON、duplicate key/BOM/trailing bytes、canonical re-encode drift；
- 任一 row 不等即整次 fail closed；
- backfill 后再次验证 bytes SHA、strict canonical re-encode identity 与 fingerprint；
- test `test_0006_proven_backfill_persists_original_available_and_request_payload_schema_identity`。

**PASS**。

### 6.15 Prerequisite test boundary vs future lookup

- target §3.4.2：prerequisite test 只证明 durable columns 持久化，不构造 `JobIdempotencyRecord`，不调用 future `get_by_idempotency_key`；
- `test_retry_mutates_only_current_available_at_and_preserves_original_request_identity_columns` 直接读取数据库列；
- public lookup/reconstruction 由 Item 6 main exact 20-path 及其既有 lookup tests 负责。

**PASS**。

### 6.16 Two READMEs

- `tests/README.md`：文档化当前 local dedicated 0006 commands/owners 与 future CI deferral；
- `dayu/investment/README.md`：同步 0006 schema、new-enqueue/backfill canonical admission 与 dedicated local lane；
- 根 `README.md` zero diff。

**PASS**。

### 6.17 0006 locks/TOCTOU/backfill/downgrade/ACL/RLS/trigger

- Locks：NOWAIT `job_runs` → `job_definitions`，conflict 整次 fail closed；
- TOCTOU：lock conflict → no partial DDL/identity write；
- Backfill：逐 row SHA + canonical + fingerprint proof，任一不等整次 fail closed；
- Downgrade：NOWAIT locks + `pg_depend` preflight + `job_runs` 精确为空 + 逆序 drop + 禁 CASCADE；
- ACL：app role 不获得三个新列 UPDATE 权限；
- RLS：existing tenant RLS 保持原样；
- Trigger：`guard_job_runs_request_identity_immutable_trigger` BEFORE UPDATE，任一 original 列变化即拒绝。

**PASS**。

### 6.18 Payload schema mismatch roundtrip

- fingerprint 包含 request payload schema name/version；
- generic mismatch 合法，不新增 equality admission；
- migration 用 definition schema 候选，fingerprint 证明才 backfill；
- fingerprint reproducer 与 domain 逐值等同。

**PASS**。

### 6.19 Definition-scoped observable boundary

- 先 tenant + exact descriptor 解析 definition；
- 再 `(tenant_id, resolved_definition_id, idempotency_key)` 查询；
- cross-definition relocation 不可观察，按 missing 处理；
- 禁止 tenant-wide scan、tenant-global unique、合法 B/K 误报 tamper。

**PASS**。

### 6.20 Cron 唯一 seam/order

- `validate_cron_expression` 是唯一 public validation-only seam；
- 复用 `_validate_croniter_expression`，零 Store/零 clock/零 mutation；
- structural/tz → validate → get_by_key → source read；
- invalid cron hit/miss 均为 `ScheduleInputError`。

**PASS**。

### 6.21 Schedule malformed vs valid conflict

- strict reconstruction 先行；
- malformed（unknown misfire/invalid cron/timezone/noncanonical payload/hash）→ `ScheduleRepositoryError` → unavailable；
- 两份 schema-valid DTO immutable drift → `ScheduleVersionConflictError`；
- test 覆盖。

**PASS**。

### 6.22 44 owners、6 PG owners、9 final lanes、174 tests

- 44 exact coverage keys（29 + 15）；
- 六个 concrete PG/migration owners；
- 九个 isolated lanes（六 PG + source-sync-job + MinIO + Redis）；
- 174 exact named tests（159 + 15，two rename 不增量）。

**PASS**。

### 6.23 Item 4/5 limited reopen 与 linear sequence

- Item 4：0005 full-chain owner 因 head/cycle assertion 更新需 fresh 运行；
- Item 5：`postgres_sources.py` 与 PG owner 因 provenance 改读 `original_available_at` 需 fresh；
- linear sequence：docs-only freeze → fresh dual review PASS → Controller acceptance + local commit → prerequisite → Item 6 main。

**PASS**。

## 7. Hostile schema-valid case search

### 7.1 Retry-mutated `available_at`

Row 的 `available_at` 被 retry 改写 → migration fingerprint reproducer 用 `current available_at` 候选 → 不等 stored fingerprint → fail closed。**正确。**

### 7.2 Payload schema mismatch backfill

Row 的 historical request payload schema 与 definition schema 不同 → migration 候选用 definition schema → fingerprint reproducer 含 request schema → 不等 → fail closed。**正确。**

### 7.3 Cross-definition same-key after fix

`(tenant, definition A, key K)` 不存在，`(tenant, definition B, key K)` 存在。Fix 按 exact definition A lookup → missing → None。合法 B/K 不影响。**正确。**

### 7.4 Single-valued misfire tamper

当前 `misfire_policy` 仅有 `coalesce_one`。写入 unknown 值 → strict reconstruction 失败 → `ScheduleRepositoryError` → unavailable。不进入 DTO compare。**正确。**

### 7.5 Noncanonical self-consistent bytes

Stored bytes SHA 自洽但非 canonical（如 trailing whitespace）→ strict canonical admission re-encode drift → fail closed。**正确。**

### 7.6 Duplicate key / BOM / trailing bytes

Strict admission 明确拒绝。**正确。**

### 7.7 Definition disable after lease

target §6.1："already-LEASED Job 的 current active/disabled status 不参与 live predicate"。**正确。**

### 7.8 `get_source_receipt` legacy 13-core-all-null row

target §9："合法 0001 13-core-all-null legacy row → None"。不伪造成 receipt。**正确。**

### 7.9 Transaction outcome precedence

target §9：rollback 自身 failure（含 exact `55P03`）→ `transaction_aborted`，最高优先。rollback 成功时 original typed lock → `unavailable`。**正确。**

### 7.10 New-enqueue invalid payload rejection

target §3.4/§3.4.1：invalid UTF-8、sensitive/unsupported/float、duplicate/BOM/trailing、noncanonical/self-consistent bytes、bytes/SHA drift → closed `JobInputError`，fingerprint/session/SQL/publisher 均零调用。**正确。**

### 7.11 Prerequisite test does not require future lookup surface

target §3.4.2：renamed retry test 直接读取 durable columns，不构造 `JobIdempotencyRecord`，不调用 future `get_by_idempotency_key`。**正确。**

### 7.12 Workflow zero-diff enforcement

target §8.6/§12：两份 CI workflow 在 prerequisite 与 Item 6 main incremental gate 保持 zero diff，final nine lanes 只在 Item 8 materialize。**正确。**

## 8. New blocker search

逐项检查：

1. **0006 五对象是否完整**：三 CHECK（deadline/schema name/version）+ function + trigger。与 manifest 一致。无遗漏。
2. **App role 无 UPDATE 权限**：target §8.6 "app role 不获得三个新列的 UPDATE 权限"。明确。
3. **`models_identity.py` zero diff**：target §8.6 明确。正确。
4. **Fingerprint reproducer 排除 idempotency key**：target §8.6 "明确不包含 idempotency_key"。正确。
5. **`datetime.isoformat()` 无格式化/截断**：target §8.6 "不得格式化/截断/改微秒"。正确。
6. **Post-backfill 验证**：target §8.6 "backfill 后再次验证 bytes SHA、strict canonical re-encode identity 与 fingerprint"。完整。
7. **Downgrade 空表要求**：target §8.6 "`job_runs` 必须精确为空"。严格。
8. **CI workflow zero diff**：target §8.6 明确。正确。
9. **`test_ci_extended_workflows_pull_three_pinned_images_isolate_nine_lanes_and_ignore_each_from_aggregate` 不增加 174 计数**：target §8.6 明确。正确。
10. **SourceScheduleGatewayProtocol 有 `validate_cron_expression`**：target §3.3 明确列出。正确。
11. **New-enqueue pre-session canonical admission**：target §3.4/§3.4.1 明确 PostgresJobStore 唯一 owner。正确。
12. **Prerequisite test boundary**：target §3.4.2 明确 retry test 只读 durable columns。正确。
13. **Investment README owner**：target §8.6 明确 two docs paths。正确。

**未发现新 blocker。**

## 9. Residual risks

fix §7 已列出：

- Nonempty legacy DB 含无法证明 row → 0006 fail closed。这是 deliberate admission，不是 blocker。
- 既有 provider 非 exactly-once、Source/Job 双事务窗口、Redis hint 不可靠等 residual 继续保留。
- 无 unclassified residual、blocking open question 或 deferred finding。

**确认。**

## 10. Final conclusion

**PASS / open H/M/L = 0/0/0**

原始 2H/3M、Round 1 1H/1M（redteam R2）与 Round 3 2H/2M（redteam R3）共十一项 finding 均已在 target/master/fix 中充分修复。exact 12 path scope（production/test 10 + docs 2，workflow deferred Item 8）、strict UTF-8 closed canonical JSON admission（migration 与 new-enqueue）、0006 fields/objects/locks/admission/downgrade、payload schema mismatch、definition observable boundary、cron owner/order、schedule taxonomy、44 keys、six owners、nine lanes、174 exact names、dedicated owner、source hostile tests、Item 4/5 evidence reopening 与 linear sequence、prerequisite test boundary、two READMEs、workflow zero-diff enforcement、new-enqueue pre-session canonical admission 均已验证。未发现新 blocker 或 hostile schema-valid 反例。

本 artifact 不授权任何 implementation、test、PG、stage、commit、push、PR 或部署。

## 11. Post-write freeze protocol

- HEAD 仍为 `4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723`；
- reviewed target SHA/lines 仍为 `f641eb210953a60756c8ff2ed36eea34e0a5c429457e846941b531a5a7b32c29 / 3536`；
- master SHA/lines 仍为 `18ae04a6e759737f5a37fa2c07cbd2f7e6f083a577e05d0e5b183b83b4d2b2a8 / 4475`；
- fix SHA/lines 仍为 `b07f89affe919bc7dccff98211eda9a322d0dc682f89691c0b920c466b346780 / 288`；
- artifact final SHA-256 与行数由写后只读命令计算。
