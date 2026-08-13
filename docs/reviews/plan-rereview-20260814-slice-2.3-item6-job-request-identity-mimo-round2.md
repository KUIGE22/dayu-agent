# Slice 2.3 Item 6 Job Request Identity — Fresh Independent Round 2 Plan Re-Review (MiMo)

- 本机时间：`2026-08-14`（Asia/Shanghai）
- 角色：独立 plan reviewer；只审计划与已存在代码事实，不实施、不修计划
- 分支：`codex/investment-platform`
- 基线 HEAD：`4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723`
- Frozen reviewed target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
  - SHA-256：`c4a8de3476487bd4c27357e7d9124e95c7e996257811d171f4ff036e4c495dc3`
  - 行数：`3485`
- Frozen master：`docs/plans/2026-08-10-investment-platform-restoration.md`
  - SHA-256：`afaa3377a0c2f82ec814fdc16718f3c6819e99c93647320c6bb7e29b94aaa705`
  - 行数：`4463`
- Frozen fix：`docs/reviews/plan-fix-20260814-slice-2.3-item6-job-request-identity-codex.md`
  - SHA-256：`f5c225d63ab867f0435815d672779f513cc39d11791c002b6056fcea8944de1d`
  - 行数：`239`
- Immutable source formal review：`docs/reviews/plan-review-20260813-234659.md`
  - SHA-256：`4d27271b57f7cbb1bfcd2065ecdf1bd08da0459782e6ab7a76ac3358019edbe0`
  - 行数：`227`
  - 结论：`FAIL / open H/M/L=2/3/0`
- Superseded/rejected old MiMo artifact（不inform本结论）：
  `docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo.md`，
  SHA-256 `ac1193fe28cd02a3a06df5ba1ae67f380dd22e5f9239a159dd2903025cc0ba22` / 218行，
  状态 `SUPERSEDED / REJECTED / IMMUTABLE`。
- 外部边界：未编辑 reviewed docs/code/tests，未运行 PG/network/provider/model，未 stage/commit/push/PR。

## 1. Review scope

本 re-review 对 Round 2 corrective candidate 执行 fresh independent 审查，覆盖：

- 原始正式 review 五项 finding（`S23-I6-PLAN-01`..`S23-I6-PLAN-05`）的修复充分性；
- Round 2 internal redteam 两项 accepted finding（`S23-I6-REDTEAM-R2-01`、`S23-I6-REDTEAM-R2-02`）的修复充分性；
- exact 13 path scope（含两个 CI workflow + tests README）；
- strict UTF-8 closed canonical JSON parse/re-encode before fingerprint；
- 0006 fields/objects/locks/admission/downgrade；
- payload schema mismatch 合法性与 fingerprint 完整性；
- definition observable boundary 与 cross-definition same-key；
- cron owner/order 与 schedule taxonomy；
- 44 keys、six owners、nine lanes、174 exact names、dedicated owner；
- source hostile tests 覆盖；
- Item 4/5 evidence reopening 与 linear sequence。

直接代码事实取自 HEAD `4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723`。

## 2. Per-finding re-verification

### 2.1 S23-I6-PLAN-01 [高] — mutable retry `available_at` 与 immutable original seed 分离

**原始问题**：`job_runs.available_at` 同时承担首次 enqueue seed 与 retry eligibility，response-loss/takeover/cross-midnight 合同不可实现。

**Fix 验证**：

- target §8.6：0006 新增 `original_available_at TIMESTAMPTZ` 列，mutable `available_at` 只负责 retry eligibility；
- target §3.4：`JobIdempotencyRecord` 新增 `original_available_at: datetime` 字段；
- target §3.5：query window 改读 `job_runs.original_available_at`；
- target §5.1：manual recovery 以 `original_available_at` 重建 fingerprint；
- target §6.2：scheduled acquire 从 locked `job_runs.original_available_at` 构造 authoritative snapshot；
- target §13.4：新增 `test_cross_midnight_retry_never_moves_original_available_at_seeded_source_query_window`、`test_manual_retry_across_utc_midnight_keeps_original_available_at_for_existing_operation_provenance`、`test_scheduled_retry_before_first_acquire_and_existing_takeover_use_original_available_at_seed`；
- fix §3.1/§3.3：confirmed。

**结论**：已修复。original durable fact 已独立于 mutable retry state，hostile tests 覆盖 cross-UTC/takeover/pre-first-acquire。

### 2.2 S23-I6-PLAN-02 [高] — request payload schema identity 成为 durable fact

**原始问题**：fingerprint 包含 request payload schema name/version，但 `job_runs` 未持久化，且当前允许与 descriptor 不同。

**Fix 验证**：

- target §8.6：0006 新增 `request_payload_schema_name TEXT` 与 `request_payload_schema_version INTEGER`；
- target §3.4：fingerprint 算法保留 payload schema 字段，不删减，不加入 idempotency key；
- target §8.6 upgrade step 3：migration-local fingerprint reproducer 与 domain `job_enqueue_request_fingerprint` 逐 key 等值，含 request payload schema name/version；
- fix §1.2/§3.2：generic mismatch 继续合法，不新增 equality admission；
- target §13.4：`test_0006_proven_backfill_persists_original_available_and_request_payload_schema_identity` 参数化覆盖 equal/mismatch/drift。

**结论**：已修复。payload schema identity 已持久化，generic mismatch 合法保留，migration reproducer 与 domain 逐值等同。

### 2.3 S23-I6-PLAN-03 [中] — lookup 合同收窄到可观察 definition scope

**原始问题**：exact descriptor+key lookup 无法区分合法 cross-definition same-key 与被重定向的 definition identity。

**Fix 验证**：

- target §3.4：lookup 先用 tenant + exact descriptor 解析 definition，再查 `(tenant_id, resolved_definition_id, idempotency_key)`；cross-tenant/missing 等价 None；
- target §3.4："其它合法 definition 下同 key 的 row 不影响结果"；"cross-definition relocation 在此 surface 不可观察，按 exact definition/key missing 处理"；
- target §3.4："禁止为检测它改成 tenant-global key unique 或把合法 B/K 误报 tamper"；
- target §13.1：`test_postgres_job_idempotency_lookup_exact_missing_cross_tenant_and_persisted_drift` 覆盖 missing/cross-tenant/persisted drift。

**结论**：已修复。可观察边界已诚实划定，合法 cross-definition 不误判。

### 2.4 S23-I6-PLAN-04 [中] — cron 语义由 Schedule owner 经窄 public seam 提供

**原始问题**：Source facade 需做 cron preflight，但唯一 croniter owner 是 ScheduleService 私有 helper。

**Fix 验证**：

- target §3.3：`SourceScheduleGatewayProtocol` 新增 `validate_cron_expression(self, expression: str) -> None`；
- target §5.2："`ScheduleService.validate_cron_expression(expression: str) -> None` 是唯一 public validation-only seam，精确调用既有 `_validate_croniter_expression`，不调用 Store、不读取 clock、不改变状态"；
- target §5.2 ordering："先做不读 mutable source state 的 request shape/tz 验证...随后精确调用一次 `ScheduleService.validate_cron_expression`，它必须先于 `get_by_key` 与任何 source read"；
- target §13.1：`test_schedule_validation_only_cron_seam_reuses_owner_without_store_clock_or_mutation`、`test_polling_schedule_cron_validation_precedes_lookup_and_source_reads_for_hit_and_miss`。

**结论**：已修复。唯一窄 public seam 已定义，ordering 已冻结，hit/miss 均为 `ScheduleInputError`。

### 2.5 S23-I6-PLAN-05 [中] — schema-valid conflict 与 malformed persisted row 已分流

**原始问题**：schedule "任一 immutable drift" 未区分 schema-valid caller drift 与 malformed persisted row。

**Fix 验证**：

- target §5.2："Store 必须先 strict 重建完整 `ScheduleDefinition`；unknown/single-valued misfire tamper、invalid cron/timezone、noncanonical payload/hash 或其它 malformed persisted shape 先成为 `ScheduleRepositoryError`。只有 request 与 persisted row 均为当前 schema-valid 完整 DTO 时，逐字段 immutable 不同才为 `ScheduleVersionConflictError`"；
- target §13.1：`test_schedule_schema_valid_immutable_conflict_is_distinct_from_malformed_persisted_row`。

**结论**：已修复。strict reconstruction 先行，malformed → unavailable，schema-valid drift → conflict。

### 2.6 S23-I6-REDTEAM-R2-01 [高] — prerequisite 未授权 CI/README owner

**原始问题**：0006 prerequisite 漏授权 CI workflow 与 README path。

**Fix 验证**：

- target §8.6："本 corrective prerequisite 精确十三个 writable path：exact 十个 production/test path 加三个 workflow/docs path"；
- target §8.6 列表包含 `.github/workflows/ci-pr-extended.yml`、`.github/workflows/ci-mainline.yml`、`tests/README.md`；
- target §8.6："既有 planned exact test `test_ci_extended_workflows_pull_three_pinned_images_isolate_nine_lanes_and_ignore_each_from_aggregate` 唯一位于已授权 `tests/investment/test_platform_migrations.py`"；
- fix §1.1 confirmed。

**结论**：已修复。exact 13 paths 已明确，CI workflow command/ignore 与 existing CI test owner 已冻结。

### 2.7 S23-I6-REDTEAM-R2-02 [中] — fingerprint 前未证明 payload canonical bytes

**原始问题**：migration admission 漏 strict canonical payload 证明。

**Fix 验证**：

- target §8.6 upgrade step 2："先验证 raw payload bytes SHA-256 等于 stored payload_sha256，随后执行 migration-local、与 domain `parse_canonical_document` 等值的 strict canonical JSON admission：bytes 必须是 exact UTF-8、无 BOM/duplicate key/trailing bytes；只允许 closed null/bool/int/string/array/object primitive tree，拒绝 float/NaN/Infinity、非 string object key 与 domain closed sensitive key；再按 `sort_keys=True`、compact separators、`ensure_ascii=False` 重编码，且 re-encoded bytes 必须与 raw bytes 逐字节相等"；
- target §8.6 upgrade step 4："任一 row 不等即整次 upgrade fail closed"；
- target §13.4：`test_0006_proven_backfill_persists_original_available_and_request_payload_schema_identity` 参数化覆盖 "canonical success、invalid UTF-8/closed primitive、bytes/SHA drift、SHA 自洽但 noncanonical JSON、duplicate key/BOM/trailing bytes 与 canonical re-encode drift"。

**结论**：已修复。strict UTF-8 closed canonical admission 已在 fingerprint 之前，negative cases 均证明无 partial DDL/identity write。

## 3. Cross-cutting verification

### 3.1 Exact 13 path scope

target §8.6 列出：

- Production（4）：`0006_job_request_identity.py`、`platform_jobs.py`、`postgres_jobs.py`、`postgres_sources.py`；
- Tests（6）：`test_platform_jobs.py`、`test_platform_migrations.py`、`test_platform_migrations_postgres.py`、`test_job_request_identity_migration_postgres.py`、`test_postgres_jobs.py`、`test_postgres_sources.py`；
- Workflow/docs（3）：`ci-pr-extended.yml`、`ci-mainline.yml`、`tests/README.md`。

合计 13。**PASS**。

### 3.2 Strict UTF-8 closed canonical JSON parse/re-encode before fingerprint

target §8.6 upgrade step 2–3 明确要求：

1. raw bytes SHA-256 == stored payload_sha256；
2. strict canonical JSON admission：UTF-8、无 BOM/duplicate key/trailing bytes、closed primitive tree、拒绝 float/NaN/Infinity/non-string key/sensitive key；
3. re-encode `sort_keys=True, separators=(',',':'), ensure_ascii=False`；
4. re-encoded bytes == raw bytes（逐字节）；
5. 只有 admission 通过后才重算 fingerprint。

**PASS**。

### 3.3 0006 fields/objects/locks/admission/downgrade

- 三列：`original_available_at TIMESTAMPTZ`、`request_payload_schema_name TEXT`、`request_payload_schema_version INTEGER`（均最终 NOT NULL）；
- 五对象：三 CHECK + function + trigger，manifest 唯一；
- Locks：NOWAIT `job_runs` → `job_definitions`，conflict 整次 fail closed；
- Admission：SHA → canonical admission → fingerprint reproducer → proof-or-fail；
- Downgrade：NOWAIT locks + `pg_depend` preflight + `job_runs` 精确为空 + 逆序 drop + 禁 CASCADE。

**PASS**。

### 3.4 Payload schema mismatch

- target §3.4："generic payload/descriptor schema mismatch 继续合法；不新增 equality admission，不删 fingerprint 输入字段"；
- fingerprint 包含 `request_payload_schema_name` 与 `request_payload_schema_version`；
- migration 用 definition schema 作为候选，只在 fingerprint 证明时 backfill。

**PASS**。

### 3.5 Definition observable boundary

- target §3.4："exact definition/key missing 或 cross-tenant 均返回 None"；"cross-definition relocation 在此 surface 不可观察"；"禁止 tenant-wide key scan、tenant-global unique 或把合法 B/K 误报 tamper"；
- 可证明 drift 只覆盖命中 exact row 内部。

**PASS**。

### 3.6 Cron owner/order

- `ScheduleService.validate_cron_expression(str) -> None`：唯一 public validation-only seam，复用 private croniter helper，零 Store/零 clock/零 mutation；
- Ordering：structural/tz → `validate_cron_expression` → `get_by_key` → source read；
- hit/miss 均为 `ScheduleInputError`；
- Source facade 不 import croniter/private helper，不复制语义。

**PASS**。

### 3.7 Schedule taxonomy

- schema-valid 两份完整 DTO immutable drift → `ScheduleVersionConflictError`；
- malformed（unknown misfire/invalid cron/timezone/noncanonical payload/hash）→ `ScheduleRepositoryError` → `SourceServiceUnavailableError(unavailable)`；
- test 覆盖 `test_schedule_schema_valid_immutable_conflict_is_distinct_from_malformed_persisted_row`。

**PASS**。

### 3.8 44 keys、six owners、nine lanes、174 exact names

- target §11.1：44 exact keys（29 tracked-existing + 15 planned-new）；
- target §14 Gate 2：六个 concrete PG/migration owners（0005/0006/identity/jobs/schedules/sources）；
- target §14：九个 isolated lanes（六个 PG + source-sync-job + MinIO + Redis）；
- target §13：174 exact names（原 159 + 15 新增，两个 rename 不增量）。

**PASS**。

### 3.9 Dedicated owner

- `test_job_request_identity_migration_postgres.py` 是 0006 唯一 instrumented PG owner；
- `test_platform_migrations_postgres.py` 继续是 0005 owner；
- 两个 migration 不共享 process 或 coverage 分母。

**PASS**。

### 3.10 Source hostile tests

- `test_cross_midnight_retry_never_moves_original_available_at_seeded_source_query_window`：跨 UTC 午夜 retry；
- `test_manual_retry_across_utc_midnight_keeps_original_available_at_for_existing_operation_provenance`：manual existing-operation 跨 UTC retry 零假 drift；
- `test_scheduled_retry_before_first_acquire_and_existing_takeover_use_original_available_at_seed`：scheduled 首次 acquire 前 retry 与 existing takeover 均用 original seed。

**PASS**。

### 3.11 Item 4/5 evidence reopening 与 linear sequence

- target §12："Item 4 的 0005 full-chain migration owner 因 head/cycle assertion 更新而需 fresh 运行"；
- target §12："Item 5 的 `postgres_sources.py` 与其 PG owner 因 provenance 改读 `original_available_at` 而需 fresh review/coverage/PG"；
- linear sequence：① docs-only freeze → ② fresh dual review PASS → ③ Controller acceptance + local commit → ④ 0006 prerequisite → ⑤ Item 6 main writer。

**PASS**。

## 4. Hostile schema-valid case search

### 4.1 Cross-definition same-key after fix

`(tenant, definition A, key K)` 不存在，`(tenant, definition B, key K)` 存在。Fix 按 exact definition A lookup → missing → None。合法 B/K 不影响。**正确**。

### 4.2 Single-valued misfire tamper

当前 `misfire_policy` 仅有 `coalesce_one`。写入 unknown 值 → strict reconstruction 失败 → `ScheduleRepositoryError` → unavailable。不进入 DTO compare。**正确**。

### 4.3 Retry-mutated `available_at`

Row 的 `available_at` 被 retry 改写 → migration fingerprint reproducer 用 `current available_at` 候选 → 不等 stored fingerprint → fail closed。**正确**。

### 4.4 Noncanonical self-consistent bytes

Stored bytes SHA 自洽但非 canonical（如 trailing whitespace）→ strict canonical admission re-encode drift → fail closed。**正确**。

### 4.5 Duplicate key / BOM / trailing bytes

Strict admission 明确拒绝。**正确**。

### 4.6 Definition disable after lease

target §6.1："already-LEASED Job 的 current active/disabled status 不参与 live predicate"。**正确**。

### 4.7 `get_source_receipt` legacy 13-core-all-null row

target §9："合法 0001 13-core-all-null legacy row → None"。不伪造成 receipt。**正确**。

### 4.8 Transaction outcome precedence

target §9：rollback 自身 failure（含 exact `55P03`）→ `transaction_aborted`，最高优先。rollback 成功时 original typed lock → `unavailable`。**正确**。

## 5. New blocker search

逐项检查：

1. **0006 五对象是否完整**：三 CHECK（deadline/schema name/version）+ function + trigger。与 manifest 一致。无遗漏。
2. **App role 无 UPDATE 权限**：target §8.6 "app role 不获得三个新列的 UPDATE 权限"。明确。
3. **`models_identity.py` zero diff**：target §8.6 明确。正确。
4. **Fingerprint reproducer 排除 idempotency key**：target §8.6 "明确不包含 idempotency_key"。正确。
5. **`datetime.isoformat()` 无格式化/截断**：target §8.6 "不得格式化/截断/改微秒"。正确。
6. **Post-backfill 验证**：target §8.6 "backfill 后再次验证 bytes SHA、strict canonical re-encode identity 与 fingerprint"。完整。
7. **Downgrade 空表要求**：target §8.6 "`job_runs` 必须精确为空"。严格。
8. **CI workflow dedicated 0006 command/ignore**：target §8.6 要求两 workflow 都有 dedicated 0006 command 与 ignore。明确。
9. **`test_ci_extended_workflows_pull_three_pinned_images_isolate_nine_lanes_and_ignore_each_from_aggregate` 不增加 174 计数**：target §8.6 明确。正确。
10. **SourceScheduleGatewayProtocol 有 `validate_cron_expression`**：target §3.3 明确列出。正确。

**未发现新 blocker。**

## 6. Residual risks

fix §7 已列出：

- Nonempty legacy DB 含无法证明 row → 0006 fail closed。这是 deliberate admission，不是 blocker。
- 既有 provider 非 exactly-once、Source/Job 双事务窗口、Redis hint 不可靠等 residual 继续保留。
- 无 unclassified residual、blocking open question 或 deferred finding。

**确认。**

## 7. Final conclusion

**PASS / open H/M/L = 0/0/0**

原始 2H/3M 与 Round 2 accepted 1H/1M 共七项 finding 均已在 target/master/fix 中充分修复。exact 13 path scope、strict UTF-8 closed canonical JSON admission、0006 fields/objects/locks/admission/downgrade、payload schema mismatch、definition observable boundary、cron owner/order、schedule taxonomy、44 keys、six owners、nine lanes、174 exact names、dedicated owner、source hostile tests、Item 4/5 evidence reopening 与 linear sequence 均已验证。未发现新 blocker 或 hostile schema-valid case。

本 artifact 不授权任何 implementation、test、PG、stage、commit、push、PR 或部署。

## 8. Post-write freeze protocol

- HEAD 仍为 `4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723`；
- reviewed target SHA/lines 仍为 `c4a8de3476487bd4c27357e7d9124e95c7e996257811d171f4ff036e4c495dc3 / 3485`；
- master SHA/lines 仍为 `afaa3377a0c2f82ec814fdc16718f3c6819e99c93647320c6bb7e29b94aaa705 / 4463`；
- fix SHA/lines 仍为 `f5c225d63ab867f0435815d672779f513cc39d11791c002b6056fcea8944de1d / 239`；
- artifact final SHA-256 与行数由写后只读命令计算。
