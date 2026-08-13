# Slice 2.3 Item 6 Job Request Identity Independent Plan Re-Review

- 本机时间：`2026-08-14 +0800`
- 角色：独立 plan re-reviewer；只审计划与已存在代码事实，不实施、不修计划
- 技能：`$planreview`
- 分支：`codex/investment-platform`
- 审查前 HEAD：`4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723`
- 审查前 index：empty
- 审查前 worktree：clean（除本artifact与已存在的target/master/fix/review文件）
- Reviewed target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
  - SHA-256：`85c7910c4a7da0a86c81a9ab929d7acd25d4c59d283bf2133b2216fc4be83f9c`
  - 行数：`3454`
- Master control：`docs/plans/2026-08-10-investment-platform-restoration.md`
  - SHA-256：`d7089e71ed26176c9194e46e1d5a9645848d949764ef4a7271e4d97281e10fdb`
  - 行数：`4446`
- Corrective fix：`docs/reviews/plan-fix-20260814-slice-2.3-item6-job-request-identity-codex.md`
  - SHA-256：`01dd54e95cd369866f791ae53243778081b893fd89f81b820502025e3827aa93`
  - 行数：`198`
- Source review：`docs/reviews/plan-review-20260813-234659.md`
  - SHA-256：`4d27271b57f7cbb1bfcd2065ecdf1bd08da0459782e6ab7a76ac3358019edbe0`
  - 行数：`227`
  - 结论：`FAIL / open H/M/L=2/3/0`
- 外部边界：未运行 PostgreSQL、网络、provider、model、Broker、交易或部署；未 stage、commit、push 或创建 PR。
- 未检查任何 DeepSeek 或内部 reviewer artifact/conclusion。

## 1. Re-review scope

本轮对 Item 6 corrective candidate 执行独立对抗性 re-review，验证 source review 五项 finding（2H/3M）是否已由 target + fix 闭合，且未引入新 blocker。直接代码事实取自 HEAD `4ed503f`：

| Artifact | SHA-256 | Lines | Review use |
|---|---|---:|---|
| `dayu/investment/storage/migrations/versions/0003_durable_jobs.py` | (HEAD) | 1032 | `job_runs` schema、immutable guard、app role UPDATE grant |
| `dayu/investment/domain/jobs.py` | (HEAD) | 2147 | `job_enqueue_request_fingerprint` 算法与 `JobEnqueueRequest` |
| `dayu/investment/storage/postgres_jobs.py` | (HEAD) | 5354 | `_mark_attempt_failed_retry` 与 `available_at` mutation |
| `dayu/investment/storage/postgres_sources.py` | (HEAD) | 3004 | manual/scheduled provenance 读取 `available_at` |
| `dayu/investment/domain/source_payload.py` | (HEAD) | 723 | `build_source_query_window` / `build_source_execution_snapshot` |
| `dayu/services/schedule_service.py` | (HEAD) | — | `_validate_croniter_expression` 私有 helper |
| `dayu/investment/domain/schedules.py` | (HEAD) | — | `ScheduleMisfirePolicy` enum（仅 `COALESCE_ONE`） |

## 2. Code facts established

1. `0003_durable_jobs.py:189` — `job_runs` 只有一个 `available_at TIMESTAMPTZ NOT NULL`，无 `original_available_at`。
2. `0003_durable_jobs.py:678-690` — app role 对 `available_at` 有 UPDATE 权限。
3. `0003_durable_jobs.py:745-747` — immutable guard 保护 `(id, tenant_id, definition_id, idempotency_key, request_fingerprint, payload_bytes, payload_sha256, deadline_at, created_at)`；**不含** `available_at`。
4. `postgres_jobs.py:4067-4073` — `_mark_attempt_failed_retry` 执行 `SET ... available_at = :available_at`，值为 `next_available_at`（retry backoff 计算后的未来时间）。三条 retry 路径复用此 helper。
5. `jobs.py:2068-2080` — `job_enqueue_request_fingerprint` 输入包含七个 descriptor 字段、`request_payload_schema_name`、`request_payload_schema_version`、`request_payload_sha256`、`available_at.isoformat()`、`deadline_at.isoformat()`；**不含** `idempotency_key`。
6. `postgres_sources.py:1591,1660,2062` — manual/scheduled provenance 与首次 acquire 均直接读取当前 `job_runs.available_at` 构建 snapshot/window。
7. `source_payload.py:206-225` — `build_source_query_window(available_at, lookback_days)` 以 `available_at.date()` 作为 `end_date`。
8. `schedule_service.py:164` — `_validate_croniter_expression` 是模块级私有函数；`:890` 由 `register()` 直接调用。
9. `schedules.py:74-77` — `ScheduleMisfirePolicy` enum 仅含 `COALESCE_ONE = "coalesce_one"`。
10. `0003_durable_jobs.py:209-210` — idempotency unique 约束为 `(tenant_id, definition_id, idempotency_key)`，definition-scoped。

## 3. Per-finding adversarial re-review

### S23-I6-PLAN-01 — mutable retry `available_at` 当作 immutable 原入队种子

**Source review 问题**：`available_at` 有两个互斥语义（首次 enqueue seed 与 retry eligibility），response-loss/takeover 合同不可实现。

**Fix 声称**：§8.6 新增 `original_available_at` immutable 列；§3.4/§3.5/§5.1/§6.2 全部改读 original；migration 以 fingerprint 证明型 backfill。

**对抗性验证**：

1. **immutable 列与 guard**：§8.6 新增 `original_available_at TIMESTAMPTZ`，`BEFORE UPDATE` trigger 拒绝任何 original 列变化。app role 不获得 UPDATE 权限。✓
2. **retry 隔离**：mutable `available_at` 继续由 retry 路径拥有；所有 lookup/provenance/window/takeover 改读 `original_available_at`。§3.5 `end_date = job_runs.original_available_at.astimezone(UTC).date()`。✓
3. **fingerprint 证明型 backfill**：migration 对每个 existing row 以 `current available_at` 作为 `original_available_at` 候选、以 definition schema 作为 request payload schema 候选重算 fingerprint。只有与 stored `request_fingerprint` exact 相等时才写入。retry-mutated row 的 `current available_at ≠ original`，重算 fingerprint 不等，整次 fail closed。✓
4. **`current_attempt_number == 0` 不是证明**：attempt=0 不排除 payload schema 合法不同。fingerprint 验证是唯一证明机制。✓
5. **lock ordering**：`NOWAIT` 先锁 `job_runs` 再锁 `job_definitions`，与正常 enqueue 路径的 FK 依赖顺序一致，避免死锁。✓
6. **hostile tests**：跨 UTC manual existing-operation、scheduled pre-first-acquire retry、existing takeover、lost-response exact fingerprint 均在 §13.4 覆盖。✓

**反例构造尝试**：假设 row 在 T0 enqueue，T1 retry（available_at 变为 T1+backoff）。migration 用 T1+backoff 候选，fingerprint 与 stored（用 T0 算）不等 → fail closed。正确。假设 row 在 T0 enqueue，未 retry，available_at 仍为 T0。migration 用 T0 候选，fingerprint 相等 → backfill。正确。假设 T0 enqueue 后 zero-backoff retry，available_at 仍为 T0（巧合相同）。fingerprint 相等 → backfill。正确，因为值确实是原值。

**结论**：**已修复**。immutable durable owner 分离了两个语义；fingerprint 证明型 backfill 安全；fail closed 正确处理不可证明 row。

### S23-I6-PLAN-02 — generic fingerprint 包含未持久化的 request payload schema identity

**Source review 问题**：fingerprint 包含 `request_payload_schema_name/version`，但 `job_runs` 未持久化这些字段，admission 也允许其与 descriptor 不同。lookup 重建时用 definition schema 会得到不同 fingerprint。

**Fix 声称**：§8.6 新增 `request_payload_schema_name TEXT` 与 `request_payload_schema_version INTEGER`；§3.4 lookup 用持久化的值重建；保留 generic mismatch；backfill 仅在 fingerprint 证明时写入。

**对抗性验证**：

1. **新列持久化**：§8.6 明确三个新列为最终 NOT NULL，CHECK 约束 name 非空/trim、version > 0。✓
2. **fingerprint 重建**：§8.6 step 2-3 要求 migration reproducer 与 `job_enqueue_request_fingerprint` 逐 key 等值，包含 request payload schema name/version。✓
3. **generic mismatch 保留**：§3.4 "generic payload/descriptor schema mismatch 继续合法；不新增 equality admission，不删 fingerprint 输入字段"。✓
4. **backfill 安全**：candidate 用 definition schema 作为 request payload schema。对 schema equal 的 row，候选与原值相同，fingerprint 相等。对历史合法 mismatch 的 row，候选（definition schema）≠ 原值（request schema），fingerprint 不等 → fail closed。✓
5. **新 enqueue**：§8.6 "enqueue 同一 INSERT 必须同时写三个 original 字段"。✓
6. **hostile tests**：equal/mismatch、name-only/version-only drift、payload bytes/SHA 与 migration/domain fingerprint 等值均在 §13.4 覆盖。✓

**反例构造尝试**：假设 row 在 schema A/1 definition 下以 payload schema B/1 enqueue。stored fingerprint 用 B/1。backfill 候选用 definition A/1。fingerprint 不等 → fail closed。正确拒绝猜测。假设 row 以 payload schema A/1（等于 definition）enqueue。候选 A/1 = 原值。fingerprint 相等 → backfill。正确。

**结论**：**已修复**。request payload schema identity 已成为 durable fact；fingerprint 证明型 backfill 对 mismatch fail closed。

### S23-I6-PLAN-03 — exact descriptor+key lookup 无法区分 cross-definition same-key 与 tamper

**Source review 问题**：lookup 按 `(tenant, definition, key)` 查找，无法区分合法 B/K 与被篡改的 A/K→B/K。

**Fix 声称**：§3.4 收窄为 definition-scoped lookup；cross-definition relocation 按 missing 处理；禁止 tenant-wide scan。

**对抗性验证**：

1. **lookup 合同**：§3.4 "先用 tenant + exact descriptor 解析唯一 definition，再只用 `(tenant_id, resolved definition_id, idempotency_key)` 查询"。✓
2. **missing 行为**：exact definition/key missing 或 cross-tenant 均返回 `None`。✓
3. **禁止 workaround**：§3.4 "禁止 tenant-wide key scan、tenant-global unique 或把合法 B/K 误报 tamper"。§15 STOP 条件确认。✓
4. **可证明 drift 限定**：§3.4 "可证明 drift 只覆盖命中 exact row 内部 descriptor、payload、hash、original time 与 request schema identity"。✓
5. **hostile test**：§13.1 `test_postgres_job_idempotency_lookup_exact_missing_cross_tenant_and_persisted_drift` 覆盖 A/K missing 且 B/K 存在仍 `None`。✓

**反例构造尝试**：tenant T 有 definition A/B，均允许 key K。A/K 不存在，B/K 存在。lookup(T, A, K) → 查 `(T, A_id, K)` → 无行 → `None`。不扫描 B。正确。A/K 存在且被篡改为 B/K（definition_id 变化）：lookup(T, A, K) → 查 `(T, A_id, K)` → 无行 → `None`。按 missing 处理。诚实记录边界。

**结论**：**已修复**。lookup 合同收窄到可观察 definition scope；不可观察的 relocation 诚实记录为 missing。

### S23-I6-PLAN-04 — cron 语义唯一 owner 是 ScheduleService 私有 helper

**Source review 问题**：Source facade 需做 cron validation，但 `_validate_croniter_expression` 是私有的。没有合法 validation-only 入口。

**Fix 声称**：§3.3 新增 `ScheduleService.validate_cron_expression(str) -> None` public seam；§5.2 冻结 pre-lookup/pre-source-read ordering。

**对抗性验证**：

1. **public seam**：§5.2 "`ScheduleService.validate_cron_expression(expression: str) -> None` 是唯一 public validation-only seam；精确调用既有 `_validate_croniter_expression(expression)`"。✓
2. **零副作用**：不调用 Store、不读取 clock、不改变状态。✓
3. **ordering**：§5.2 "先做 structural/tz，再调用该 seam；它发生在 schedule lookup 和任何 source read 之前"。✓
4. **error 一致性**：invalid cron 在 hit/miss 两路均为 `ScheduleInputError`，Store/source 调用均为零。✓
5. **不复制逻辑**：§15 STOP "Source facade 直接 import croniter/private Schedule helper、复制 cron semantics" 为 STOP 条件。✓
6. **hostile tests**：§13.1 `test_schedule_validation_only_cron_seam_reuses_owner_without_store_clock_or_mutation` 与 `test_polling_schedule_cron_validation_precedes_lookup_and_source_reads_for_hit_and_miss`。✓

**反例构造尝试**：caller 提交 croniter-invalid cron 到 `ensure_polling_schedule`。先 structural/tz → pass。调用 `validate_cron_expression` → `ScheduleInputError`。零 Store/source 调用。hit/miss 均相同。正确。如果 caller 提交 valid cron 但 hit existing schedule with different cron → strict reconstruct 成功 → schema-valid immutable compare → `ScheduleVersionConflictError`。正确。

**结论**：**已修复**。cron validation 由 Schedule owner 经窄 public seam 提供；ordering 冻结。

### S23-I6-PLAN-05 — schedule "任一 immutable drift" 未区分 schema-valid caller drift 与 malformed persisted row

**Source review 问题**：`misfire_policy` 只有 `COALESCE_ONE` 一个 schema-valid 值。要制造 stored misfire policy drift 只能写入 malformed 值，但 `ScheduleDefinition` reconstruction 会先失败。测试期待 version conflict 会迫使 Store 放宽 reconstruction。

**Fix 声称**：§5.2 strict reconstruction 先行；malformed 为 `ScheduleRepositoryError`；schema-valid drift 为 `ScheduleVersionConflictError`。

**对抗性验证**：

1. **strict reconstruction 先行**：§5.2 "Store 必须先 strict 重建完整 `ScheduleDefinition`；unknown/single-valued misfire tamper、invalid cron/timezone、noncanonical payload/hash 或其它 malformed persisted shape 先成为 `ScheduleRepositoryError`"。✓
2. **分类**：§5.2 "只有 request 与 persisted row 均为当前 schema-valid 完整 DTO 时，逐字段 immutable 不同才为 `ScheduleVersionConflictError`"。✓
3. **error mapping**：`ScheduleRepositoryError` → `SourceServiceUnavailableError(unavailable)`。`ScheduleVersionConflictError` → 原样传播。✓
4. **测试拆分**：§13.1 `test_schedule_ensure_registered_rejects_same_key_with_each_schema_valid_immutable_drift`（每个当前可构造的 alternate immutable field）；`test_schedule_schema_valid_immutable_conflict_is_distinct_from_malformed_persisted_row`（single-valued misfire tamper、unknown enum → unavailable，零 mutation）。✓
5. **不预造兼容逻辑**：对未来 enum 新增值只测试当时真实 schema 允许的合法值。✓

**反例构造尝试**：caller 请求 `misfire_policy=COALESCE_ONE`，stored row 有 `misfire_policy=invalid_value`。strict reconstruction 失败 → `ScheduleRepositoryError` → `SourceServiceUnavailableError(unavailable)`。不是 version conflict。正确。caller 请求 `cron="0 * * * *"`，stored 有 `cron="0 0 * * *"`。两份 DTO 均 schema-valid。immutable compare → `ScheduleVersionConflictError`。正确。

**结论**：**已修复**。strict reconstruction 先行；malformed 与 schema-valid 已分流。

## 4. New-blocker scan

### 4.1 0006 migration lock ordering 与 concurrent enqueue

`NOWAIT` 先锁 `job_runs` 再锁 `job_definitions`。migration 持有 `ACCESS EXCLUSIVE` 期间无 concurrent INSERT 可发生（表级锁阻塞所有写操作）。正常 enqueue 路径先 INSERT `job_definitions`（或读取已有）再 INSERT `job_runs`，lock 顺序与 migration 相反但不冲突（migration 是表级锁，enqueue 是行级锁）。无死锁风险。

### 4.2 fingerprint algorithm 一致性

§8.6 step 3 要求 migration reproducer 与 `job_enqueue_request_fingerprint` 逐 key 等值，编码为 `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` 后 UTF-8 SHA-256。两个 TIMESTAMPTZ 使用 Python `datetime.isoformat()`。`SET LOCAL TIME ZONE 'UTC'` 确保 PG 侧一致。§13.4 `test_0006_migration_fingerprint_reproducer_matches_domain_and_excludes_idempotency_key` 在 schema equal、合法 schema mismatch、微秒/UTC time variation 上逐值对照。充分。

### 4.3 downgrade empty-only 与 external dependency

§8.6 downgrade 先以 `pg_depend` 拒绝 owner 外 dependency，再要求 `job_runs` 精确为空。存在任一外部依赖或 Job row 即 fail closed。禁止 CASCADE。正确保护 immutable request facts。

### 4.4 coverage owner ledger

- 44 keys：29 tracked-existing + 15 planned-new。§11.1 逐 production path 唯一映射。✓
- 6 PG owners：每个 production file 唯一对应一个 test file。0006 有 dedicated owner `test_job_request_identity_migration_postgres.py`，不与 0005 共享 process。✓
- 9 isolated lanes：6 PG/migration + source-sync-job + MinIO + Redis。§14 逐项 `--ignore`。✓
- 174 named tests：159 base + 15 new = 174。§13 逐项唯一。✓

### 4.5 0005 head/cycle 更新

0006 成为新 head 后，0005 的 full-chain/cycle assertion 需更新。§12 "Item 4 的 0005 full-chain migration owner 因 head/cycle assertion 更新而需 fresh 运行"。既有 `test_platform_migrations_postgres.py` 仍是 0005 owner，只更新 assertion。不冲突。

### 4.6 Item 4/5 证据有限重开

§12 "Item 5 的 `postgres_sources.py` 与其 PG owner 因 provenance 改读 `original_available_at` 而需 fresh review/coverage/PG"。历史 semantic commit 保持可追溯，但旧 review SHA 不证明新字节。新证据进入 0006 prerequisite accepted commit。正确。

### 4.7 payload schema equal case 测试覆盖

§13.4 列出 "equal/mismatch、name-only/version-only drift、payload bytes/SHA 与 migration/domain fingerprint 等值"。equal case 是默认正常路径（definition schema = request schema），由 `test_new_enqueue_persists_exact_original_available_and_request_payload_schema_identity` 覆盖。mismatch case 由 `test_0006_upgrade_rejects_legacy_payload_schema_mismatch_without_partial_ddl` 覆盖。充分。

## 5. Special review lenses

- **Architecture boundary review**：Job identity owner 拥有 `original_available_at` + request payload schema；Schedule owner 拥有 cron validation；Source facade 拥有 caller-intent compare。三个 owner 单向协作，无循环依赖。✓
- **Best-practice review**：immutable request identity 与 mutable scheduling state 已分离。hash 只校验已持久化输入。migration 有可证明 backfill/admission。✓
- **Overengineering review**：未新增 Source-specific Job shadow table、第二 Job repository、兼容 facade 或 ORM 只读镜像。`job_runs` 上三个 immutable 列是最小可信设计。✓
- **Overcoupling review**：未把 generic idempotency key 改成 tenant-global unique。未让 Source 层依赖 croniter/private helper。✓
- **Optimal-solution review**：`0006` 是当前要求下最小可信方向。删除 fingerprint 字段、复用 mutable time、把 stored hash 当真源都更不安全。✓

## 6. Residual risks（与 target §16 一致，未新增）

1. Nonempty legacy DB 可含无法证明的 row → 0006 fail closed。
2. Provider 非 exactly-once。
3. Source/Job 双事务窗口。
4. Redis wakeup 不可靠。
5. RSS/industry/manual connector 不可执行。
6. Semantic alert 只持久化。
7. Date-only freshness。
8. Owned-thread 无 wall-clock 上界。
9. Job/Schedule repository failure 无 typed code。
10. 0006 安全升级 fail closed 对不可证明 row。

无新增 residual、blocking open question 或 deferred finding。

## 7. Final conclusion

**PASS / open H/M/L = 0/0/0**

Source review 的五项 finding 全部已由 target + fix 闭合：

- **01（H）**：`original_available_at` immutable durable owner 分离 retry eligibility 与 original seed；fingerprint 证明型 backfill；hostile tests 覆盖跨日/retry/takeover。
- **02（H）**：`request_payload_schema_name/version` 持久化；fingerprint 重建包含新字段；generic mismatch 保留；backfill 对 mismatch fail closed。
- **03（M）**：lookup 收窄到 definition-scoped；cross-definition relocation 按 missing；禁止 tenant-wide scan。
- **04（M）**：`validate_cron_expression` public seam；pre-lookup ordering；零 Store/clock/mutation。
- **05（M）**：strict reconstruction 先行；malformed → repository unavailable；schema-valid drift → version conflict。

未引入新 blocker。44 coverage keys、6 PG owners、9 isolated lanes、174 named tests、10-path/20-path prerequisite 均机械闭合。

本 artifact 不授权任何 fix、implementation、PG、stage、commit、push、PR 或部署。
