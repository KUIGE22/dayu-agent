# Slice 2.3 Item 6 Job Request Identity — Round 4 Plan Re-Review (MiMo)

- 本机时间：2026-08-14（Asia/Shanghai）
- 角色：独立 plan reviewer；只审计划与已存在代码事实，不实施、不修计划
- 分支：codex/investment-platform
- 基线 HEAD：4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723
- Frozen reviewed target：docs/plans/2026-08-12-slice-2.3-source-connectors-health.md
  - SHA-256：dc210d4a3a6c0c4b7f5521e6e372f5ec0cc7e236c9c09a52460ad6847d432fa0
  - 行数：3564
- Frozen master：docs/plans/2026-08-10-investment-platform-restoration.md
  - SHA-256：83680025d05881ef535c124120e39aefd3c964615abab237aca0b54f30acef62
  - 行数：4498
- Frozen fix：docs/reviews/plan-fix-20260814-slice-2.3-item6-job-request-identity-codex.md
  - SHA-256：9066d39e98525e4d4a068ae03fe54679fc5690e1da72490fcec0ad92e8a697e1
  - 行数：331
- Immutable source formal review：docs/reviews/plan-review-20260813-234659.md
  - SHA-256：4d27271b57f7cbb1bfcd2065ecdf1bd08da0459782e6ab7a76ac3358019edbe0
  - 行数：227
  - 结论：FAIL / open H/M/L=2/3/0
- Immutable DeepSeek V4 Pro Round 3 artifact：docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-deepseek-v4-pro-round3.md
  - SHA-256：e8739eecd9c505e607efe94f0d70f6464ec6c8d8c7dd5be37d5b5809dfece103
  - 行数：104
  - 结论：FAIL / open H/M/L=0/0/1
- Superseded/rejected old MiMo artifacts（不inform本结论）：
  - Round 1：plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo.md，
    SHA-256 ac1193fe28cd02a3a06df5ba1ae67f380dd22e5f9239a159dd2903025cc0ba22 / 218行，
    状态 SUPERSEDED / REJECTED / IMMUTABLE（漏后续 accepted 1H/1M）。
  - Round 2：plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo-round2.md，
    SHA-256 dc849d2d60184beb0dcaeeaf20711435706804b40995fdc4ce03a19062d2b139 / 312行，
    状态 SUPERSEDED / REJECTED / IMMUTABLE（漏后续 Round 3 accepted 2H/2M）。
  - Round 3：plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo-round3.md，
    SHA-256 见后文 / 行数见后文，
    状态 SUPERSEDED / IMMUTABLE（基于旧三SHA，未含 DeepSeek V4 Pro Round 3 Low fix）。
- 外部边界：未编辑 reviewed docs/code/tests，未运行 PG/network/provider/model，未 stage/commit/push/PR。

## 1. Review scope

本 Round 4 re-review 对 DeepSeek V4 Pro Round 3 Low finding 修复后的 fresh new-SHA candidate 执行独立审查，覆盖：

- 原始正式 review 五项 finding（S23-I6-PLAN-01..05）的修复充分性；
- Round 2 internal redteam 两项 accepted finding（S23-I6-REDTEAM-R2-01..02）的修复充分性；
- Round 3 internal redteam 四项 accepted finding（S23-I6-REDTEAM-R3-01..04）的修复充分性；
- DeepSeek V4 Pro Round 3 一项 accepted finding（S23-I6-DSV4P-R3-01）的修复充分性；
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
- README owner completeness；
- **backfill sensitive-key parameter matrix 与 migration-local/domain canonical admission equivalence pin**。

直接代码事实取自 HEAD 4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723。

## 2. Frozen byte verification

| Artifact | Expected SHA-256 | Expected lines | Actual SHA-256 | Actual lines | Status |
|---|---|---:|---|---:|---|
| target | dc210d4a…432fa0 | 3564 | dc210d4a…432fa0 | 3564 | ✅ MATCH |
| master | 83680025…acef62 | 4498 | 83680025…acef62 | 4498 | ✅ MATCH |
| fix | 9066d39e…a697e1 | 331 | 9066d39e…a697e1 | 331 | ✅ MATCH |
| formal source | 4d27271b…dbe0 | 227 | 4d27271b…dbe0 | 227 | ✅ MATCH |
| DSV4P R3 | e8739eec…ce103 | 104 | e8739eec…ce103 | 104 | ✅ MATCH |

**零字节漂移。无 STOP 条件。**

## 3. Old MiMo verdict identity verification

三份 old MiMo artifact 仅验证 identity 与 rejected/superseded 状态，不采信其内容：

1. Round 1 ac1193fe… / 218行：self-claimed PASS / 0/0/0，但 fix §1.1 证明遗漏后续 accepted S23-I6-REDTEAM-R2-01（1H）与 S23-I6-REDTEAM-R2-02（1M），状态精确为 SUPERSEDED / REJECTED / IMMUTABLE。**确认 rejected。**
2. Round 2 dc849d2d… / 312行：self-claimed PASS / 0/0/0，但 fix §1.2 证明遗漏后续 accepted S23-I6-REDTEAM-R3-01..R3-04（2H/2M），状态精确为 SUPERSEDED / REJECTED / IMMUTABLE。**确认 rejected。**
3. Round 3（old SHA）：基于旧 target f641eb21…/3536行、旧 master 18ae04a6…/4475行、旧 fix b07f89af…/288行。PASS / 0/0/0，但未含 DeepSeek V4 Pro Round 3 Low S23-I6-DSV4P-R3-01 fix。状态为 SUPERSEDED / IMMUTABLE。**确认 superseded。**

## 4. Source code fact verification

独立验证直接代码事实（与 formal review §1 及 DeepSeek V4 Pro Round 3 §2 交叉确认）：

| File | Formal review lines | Actual lines | Match |
|---|---:|---:|---|
| 0003_durable_jobs.py | 1032 | 1032 | ✅ |
| jobs.py | 2147 | 2147 | ✅ |
| postgres_jobs.py | 5354 | 5354 | ✅ |
| postgres_sources.py | 3004 | 3004 | ✅ |

关键代码事实确认：
- jobs.py:41 `_SENSITIVE_KEY_SET = frozenset({"password", "secret", "token", "authorization", "cookie", "api_key"})` — 非空。
- jobs.py:517 validator 拒绝命中 sensitive key — 真实拒绝类。
- jobs.py:560 `parse_canonical_document` 存在。
- jobs.py:2048 `job_enqueue_request_fingerprint` 存在。
- 0003_durable_jobs.py:189 `available_at TIMESTAMPTZ NOT NULL` — 单一列，无 original_available_at。
- postgres_jobs.py 确认为 raw SQL Job owner，job_runs 唯一 INSERT 站点。

## 5. Per-finding re-verification

### 5.1 S23-I6-PLAN-01 [高] — mutable retry available_at 与 immutable original seed 分离

**Fix 验证**：

- target §8.6：0006 新增 original_available_at TIMESTAMPTZ 列，mutable available_at 只负责 retry eligibility；
- target §3.4：JobIdempotencyRecord 新增 original_available_at: datetime 字段；
- target §3.5：query window 改读 job_runs.original_available_at；
- target §5.1：manual recovery 以 original_available_at 重建 fingerprint；
- target §6.2：scheduled acquire 从 locked job_runs.original_available_at 构造 authoritative snapshot；
- target §13.4：三个 hostile tests 覆盖 cross-UTC/takeover/pre-first-acquire；
- 0006 immutable trigger guard_job_runs_request_identity_immutable_trigger 阻止 original 列被 UPDATE；
- app role 不获得三个新列的 UPDATE 权限。

**结论**：**已修复。**

### 5.2 S23-I6-PLAN-02 [高] — request payload schema identity 成为 durable fact

**Fix 验证**：

- target §8.6：0006 新增 request_payload_schema_name TEXT 与 request_payload_schema_version INTEGER；
- target §3.4：fingerprint 算法保留 payload schema 字段，不删减，不加入 idempotency key；
- target §8.6 upgrade step 3：migration-local fingerprint reproducer 与 domain job_enqueue_request_fingerprint 逐 key 等值，含 request payload schema name/version；
- generic mismatch 继续合法，不新增 equality admission；
- target §13.4：test_0006_proven_backfill_persists_original_available_and_request_payload_schema_identity 参数化覆盖 equal/mismatch/drift。

**结论**：**已修复。**

### 5.3 S23-I6-PLAN-03 [中] — lookup 合同收窄到可观察 definition scope

**Fix 验证**：

- target §3.4：lookup 先用 tenant + exact descriptor 解析 definition，再查 (tenant_id, resolved_definition_id, idempotency_key)；
- cross-tenant/missing 等价 None；cross-definition relocation 不可观察；
- 禁止 tenant-wide key scan、tenant-global unique 或把合法 B/K 误报 tamper。

**结论**：**已修复。**

### 5.4 S23-I6-PLAN-04 [中] — cron 语义由 Schedule owner 经窄 public seam 提供

**Fix 验证**：

- target §3.3：SourceScheduleGatewayProtocol 新增 validate_cron_expression(self, expression: str) -> None；
- target §5.2：ScheduleService.validate_cron_expression 是唯一 public validation-only seam，复用 _validate_croniter_expression，零 Store/零 clock/零 mutation；
- ordering：structural/tz → validate_cron_expression → get_by_key → source read；
- hit/miss 均为 ScheduleInputError。

**结论**：**已修复。**

### 5.5 S23-I6-PLAN-05 [中] — schema-valid conflict 与 malformed persisted row 已分流

**Fix 验证**：

- target §5.2：strict reconstruction 先行；malformed → ScheduleRepositoryError → unavailable；
- 两份 schema-valid DTO immutable drift → ScheduleVersionConflictError；
- test 覆盖 test_schedule_schema_valid_immutable_conflict_is_distinct_from_malformed_persisted_row。

**结论**：**已修复。**

### 5.6 S23-I6-REDTEAM-R2-01 [高] — prerequisite 未授权 CI/README owner

**Fix 验证**：

- target §8.6：exact 12 paths（production/test 10 + docs 2），包含 tests/README.md 与 dayu/investment/README.md；
- CI workflow 在 prerequisite 和 Item 6 main incremental gate 保持 zero diff；
- final nine commands/ignores 只在 Item 8 materialize。

**结论**：**已修复。**

### 5.7 S23-I6-REDTEAM-R2-02 [中] — fingerprint 前未证明 payload canonical bytes

**Fix 验证**：

- target §8.6 upgrade step 2：strict canonical JSON admission 在 fingerprint 之前；
- bytes SHA → strict UTF-8 decode → closed primitive → reject sensitive key → re-encode → byte identity；
- negative cases 均证明无 partial DDL/identity write。

**结论**：**已修复。**

### 5.8 S23-I6-REDTEAM-R3-01 [高] — future workflows 错误纳入 prerequisite

**Fix 验证**：

- target §8.6：prerequisite exact 12 paths，CI workflow 不在其中；
- 两份 workflow 在 prerequisite 和 Item 6 main incremental gate 必须 zero diff；
- final nine commands/ignores 只在 Item 8。

**结论**：**已修复。**

### 5.9 S23-I6-REDTEAM-R3-02 [高] — new enqueue 缺 pre-session canonical admission

**Fix 验证**：

- target §3.4：PostgresJobStore.enqueue 是唯一 validation owner；
- fingerprint helper、session factory、任何 SQL/DML 或可能 publish 的返回之前 strict validate；
- invalid UTF-8、sensitive/unsupported/float、duplicate/BOM/trailing、noncanonical/self-consistent bytes、bytes/SHA drift → closed JobInputError；
- fingerprint/session/SQL/publisher 均零调用。

**结论**：**已修复。**

### 5.10 S23-I6-REDTEAM-R3-03 [中] — prerequisite test 越界要求 future lookup

**Fix 验证**：

- target §3.4.2：prerequisite renamed retry test 只读取 durable columns；
- 不构造 JobIdempotencyRecord，不调用 future get_by_idempotency_key；
- public lookup/reconstruction 由 Item 6 main 负责。

**结论**：**已修复。**

### 5.11 S23-I6-REDTEAM-R3-04 [中] — investment README owner 遗漏

**Fix 验证**：

- target §8.6 exact 12 paths 包含 tests/README.md 与 dayu/investment/README.md；
- dayu/investment/README.md 只同步 0006 schema、new-enqueue/backfill canonical admission 与 dedicated local lane；
- 根 README.md 保持 zero diff。

**结论**：**已修复。**

### 5.12 S23-I6-DSV4P-R3-01 [低] — backfill sensitive-key matrix 与 migration-local/domain canonical admission pure pin 未闭合

**原始问题**：backfill PG named test 的参数矩阵缺少 sensitive-key case；migration-local canonical admission 与 domain parse_canonical_document 的逐值等价无 pure 测试 pin。

**Fix 验证（target §13.4 3137-3145）**：

- target §13.4："既有 dedicated owner named test test_0006_proven_backfill_persists_original_available_and_request_payload_schema_identity 保持单一 exact name 并参数化覆盖：canonical proven success、invalid UTF-8/closed primitive、raw bytes/SHA drift、SHA 自洽但 noncanonical JSON、duplicate key/BOM/trailing bytes、canonical re-encode drift，**以及 stored SHA 与 raw bytes自洽的 domain sensitive-key cases**"；
- target §13.4："后者至少把 exact lowercase token 代表键与 recursive mixed-case `{"a":{"ToKeN":"x"}}` 作为 independent parameters，二者各自提供 self-consistent raw/stored SHA，证明 case-insensitive recursive closed-set admission 在任一 identity DDL/write 前 fail closed"；
- 每个 negative case 均断言无 partial DDL/identity write 且 0005 catalog 保持 exact。

**Fix 验证（target §8.6 step 3 / 2244-2260）**：

- target §8.6 step 3：pure test test_0006_migration_fingerprint_reproducer_matches_domain_and_excludes_idempotency_key 必须把 migration reproducer 与 domain 真源在 schema equal、合法 schema mismatch、微秒/UTC time variation 上逐值对照；
- 同一 exact named test 还必须冻结 migration-local canonical admission 实现（migration 不得 import domain helper）与 public parse_canonical_document 的逐值等价；
- valid-UTF-8 parser corpus 按 exact ACCEPT/CANONICAL_INVALID 归一：domain adapter 只捕获 JobInputError，migration adapter 只捕获 0006 定义的 exact private canonical-invalid exception；
- ACCEPT corpus 至少逐项包含 null、true、-1、"中"、canonical array [null,false,0,"中",{}]、sorted nested object，以及按 canonical key 顺序编码并分别含 apikey、password_hint、token_count、x-authorization 的 near-miss object；
- CANONICAL_INVALID corpus 必须把 password、secret、token、authorization、cookie、api_key 六个 lowercase literal 各自作为 independent parameter case；
- 另含 recursive mixed-case ToKeN、float、NaN、nested duplicate key、BOM、trailing junk、trailing whitespace、noncanonical key order、noncompact separators 与 escaped Unicode；
- 不得把六个 sensitive key 合并进同一 object，不得加入 JSON 文本不可构造的 non-string object key；
- bytes/SHA drift 则在同一 pure named test 内由 migration wrapper 用 valid canonical raw + mismatched supplied SHA 独立归一为 CANONICAL_INVALID 并证明 parser 零调用。

**Fix 验证（fix §6 S23-I6-DSV4P-R3-01）**：

- fix §6："在 existing PG backfill named test 加入 self-consistent raw/stored-SHA sensitive-key parameters"；
- fix §6："在 existing pure reproducer named test 内用 closed valid/hostile corpus 逐值 pin migration-local admission 与 public domain parser"；
- fix §6："六个 sensitive literal 各自独立 reject，near-miss keys 保持 accept，classification 只允许 ACCEPT/CANONICAL_INVALID，accept exact 比 schema/bytes/SHA/raw identity"。

**代码事实确认**：
- jobs.py:41 _SENSITIVE_KEY_SET 非空（password/secret/token/authorization/cookie/api_key）；
- jobs.py:517 validator 拒绝命中键 — sensitive key 在 JSON 文本形态真实可达；
- 0005 migration 已证明 migration 可 import 项目模块 — "migration-local 等值"是计划选择的复制语义而非恒真式。

**结论**：**已修复。** backfill PG named test 现在包含 self-consistent sensitive-key parameters（exact lowercase token 与 recursive mixed-case ToKeN）；pure reproducer named test 冻结 migration-local canonical admission 与 domain parse_canonical_document 的逐值 ACCEPT/CANONICAL_INVALID 等价，六个 sensitive literal 各自独立 reject，near-miss keys 保持 accept。migration 不 import domain helper，等值由同一 test 内 corpus pin。

## 6. Cross-cutting verification

### 6.1 Exact 12 path scope

target §8.6 列出：

- Production（4）：0006_job_request_identity.py、platform_jobs.py、postgres_jobs.py、postgres_sources.py；
- Tests（6）：test_platform_jobs.py、test_platform_migrations.py、test_platform_migrations_postgres.py、test_job_request_identity_migration_postgres.py、test_postgres_jobs.py、test_postgres_sources.py；
- Docs（2）：tests/README.md、dayu/investment/README.md。

合计 12。两份 CI workflow 保持 zero diff。**PASS**。

### 6.2 Strict UTF-8 closed canonical JSON parse/re-encode before fingerprint

target §8.6 upgrade step 2–3 明确要求：

1. raw bytes SHA-256 == stored payload_sha256；
2. strict canonical JSON admission：UTF-8、无 BOM/duplicate key/trailing bytes、closed primitive tree、拒绝 float/NaN/Infinity/non-string key/sensitive key；
3. re-encode sort_keys=True, separators=(',',':'), ensure_ascii=False；
4. re-encoded bytes == raw bytes（逐字节）；
5. 只有 admission 通过后才重算 fingerprint。

target §3.4.1 new-enqueue 同样要求。**PASS**。

### 6.3 0006 fields/objects/locks/admission/downgrade

- 三列：original_available_at TIMESTAMPTZ、request_payload_schema_name TEXT、request_payload_schema_version INTEGER（均最终 NOT NULL）；
- 五对象：三 CHECK + function + trigger，manifest 唯一；
- Locks：NOWAIT job_runs → job_definitions，conflict 整次 fail closed；
- Admission：SHA → canonical admission → fingerprint reproducer → proof-or-fail；
- Downgrade：NOWAIT locks + pg_depend preflight + job_runs 精确为空 + 逆序 drop + 禁 CASCADE。

**PASS**。

### 6.4 Payload schema mismatch

- target §3.4："generic payload/descriptor schema mismatch 继续合法；不新增 equality admission，不删 fingerprint 输入字段"；
- fingerprint 包含 request_payload_schema_name 与 request_payload_schema_version；
- migration 用 definition schema 作为候选，只在 fingerprint 证明时 backfill。

**PASS**。

### 6.5 Definition observable boundary

- target §3.4：exact definition/key missing 或 cross-tenant 均返回 None；cross-definition relocation 不可观察；
- 禁止 tenant-wide key scan、tenant-global unique 或把合法 B/K 误报 tamper。

**PASS**。

### 6.6 Cron owner/order

- ScheduleService.validate_cron_expression(str) -> None：唯一 public validation-only seam；
- 复用 _validate_croniter_expression，零 Store/零 clock/零 mutation；
- Ordering：structural/tz → validate → get_by_key → source read；
- hit/miss 均为 ScheduleInputError。

**PASS**。

### 6.7 Schedule taxonomy

- schema-valid 两份完整 DTO immutable drift → ScheduleVersionConflictError；
- malformed（unknown misfire/invalid cron/timezone/noncanonical payload/hash）→ ScheduleRepositoryError → unavailable；
- test 覆盖。

**PASS**。

### 6.8 44 keys、six owners、nine lanes、174 exact names

- target §11.1：44 exact keys（29 tracked-existing + 15 planned-new）；
- target §14 Gate 2：六个 concrete PG/migration owners；
- target §14：九个 isolated lanes（六 PG + source-sync-job + MinIO + Redis）；
- target §13：174 exact names（原 159 + 15 新增，两个 rename 不增量）。

**PASS**。

### 6.9 Dedicated owner

- test_job_request_identity_migration_postgres.py 是 0006 唯一 instrumented PG owner；
- test_platform_migrations_postgres.py 继续是 0005 owner；
- 两个 migration 不共享 process 或 coverage 分母。

**PASS**。

### 6.10 Source hostile tests

- test_cross_midnight_retry_never_moves_original_available_at_seeded_source_query_window；
- test_manual_retry_across_utc_midnight_keeps_original_available_at_for_existing_operation_provenance；
- test_scheduled_retry_before_first_acquire_and_existing_takeover_use_original_available_at_seed。

**PASS**。

### 6.11 Item 4/5 evidence reopening 与 linear sequence

- Item 4：0005 full-chain owner 因 head/cycle assertion 更新需 fresh 运行；
- Item 5：postgres_sources.py 与 PG owner 因 provenance 改读 original_available_at 需 fresh；
- linear sequence：docs-only freeze → fresh dual review PASS → Controller acceptance + local commit → prerequisite → Item 6 main。

**PASS**。

### 6.12 Workflow zero-diff and final nine lanes deferred Item 8

- target §8.6：两份 CI workflow 在 prerequisite 与 Item 6 main incremental gate 保持 zero diff；
- target §12/§14：final nine commands/ignores、workflow static audit、tests/README final CI 只在 Item 8。

**PASS**。

### 6.13 New-enqueue strict canonical admission

- target §3.4/§3.4.1：PostgresJobStore 是唯一 owner；
- 严格 UTF-8 decode → domain-equivalent canonical parse/re-encode → bytes/SHA identity；
- invalid UTF-8、sensitive/unsupported/float、duplicate/BOM/trailing、noncanonical/self-consistent bytes、bytes/SHA drift → closed JobInputError；
- fingerprint/session/SQL/publisher 均零调用。

**PASS**。

### 6.14 Migration backfill admission

- target §8.6 upgrade step 2–4：每 row 先验证 bytes SHA → strict canonical admission → fingerprint reproducer → proof-or-fail；
- negative cases：invalid UTF-8、closed primitive violation、bytes/SHA drift、SHA 自洽但 noncanonical JSON、duplicate key/BOM/trailing bytes、canonical re-encode drift、**sensitive-key cases（token + recursive ToKeN）**；
- 任一 row 不等即整次 fail closed；
- backfill 后再次验证 bytes SHA、strict canonical re-encode identity 与 fingerprint。

**PASS**。

### 6.15 Prerequisite test boundary vs future lookup

- target §3.4.2：prerequisite test 只证明 durable columns 持久化，不构造 JobIdempotencyRecord，不调用 future get_by_idempotency_key；
- public lookup/reconstruction 由 Item 6 main 负责。

**PASS**。

### 6.16 Two READMEs

- tests/README.md：文档化当前 local dedicated 0006 commands/owners 与 future CI deferral；
- dayu/investment/README.md：同步 0006 schema、new-enqueue/backfill canonical admission 与 dedicated local lane；
- 根 README.md zero diff。

**PASS**。

### 6.17 0006 locks/TOCTOU/backfill/downgrade/ACL/RLS/trigger

- Locks：NOWAIT job_runs → job_definitions，conflict 整次 fail closed；
- TOCTOU：lock conflict → no partial DDL/identity write；
- Backfill：逐 row SHA + canonical + fingerprint proof，任一不等整次 fail closed；
- Downgrade：NOWAIT locks + pg_depend preflight + job_runs 精确为空 + 逆序 drop + 禁 CASCADE；
- ACL：app role 不获得三个新列 UPDATE 权限；
- RLS：existing tenant RLS 保持原样；
- Trigger：guard_job_runs_request_identity_immutable_trigger BEFORE UPDATE，任一 original 列变化即拒绝。

**PASS**。

### 6.18 Backfill sensitive-key matrix 与 migration-local/domain equivalence（DSV4P-R3-01 fix）

这是 DeepSeek V4 Pro Round 3 唯一 Low finding 的核心验证维度：

- target §13.4：backfill PG named test 现包含 self-consistent raw/stored-SHA sensitive-key parameters（exact lowercase token 与 recursive mixed-case `{"a":{"ToKeN":"x"}}`）作为 independent parameters；
- target §8.6 step 3：pure reproducer named test 冻结 migration-local canonical admission 与 domain parse_canonical_document 的逐值等价，六个 sensitive literal（password/secret/token/authorization/cookie/api_key）各自独立 reject；
- near-miss keys（apikey/password_hint/token_count/x-authorization）保持 accept；
- classification 只允许 ACCEPT/CANONICAL_INVALID，accept exact 比 schema/bytes/SHA/raw identity；
- migration 不 import domain helper，等值由同一 test 内 corpus pin；
- invalid UTF-8 只在 PG byte-wrapper 层验证，不伪造 pure 等价。

**PASS**。

### 6.19 Definition-scoped observable boundary

- 先 tenant + exact descriptor 解析 definition；
- 再 (tenant_id, resolved_definition_id, idempotency_key) 查询；
- cross-definition relocation 不可观察，按 missing 处理。

**PASS**。

### 6.20 Cron 唯一 seam/order

- validate_cron_expression 是唯一 public validation-only seam；
- 复用 _validate_croniter_expression，零 Store/零 clock/零 mutation；
- structural/tz → validate → get_by_key → source read；
- invalid cron hit/miss 均为 ScheduleInputError。

**PASS**。

### 6.21 Schedule malformed vs valid conflict

- strict reconstruction 先行；
- malformed → ScheduleRepositoryError → unavailable；
- 两份 schema-valid DTO immutable drift → ScheduleVersionConflictError。

**PASS**。

### 6.22 44 keys、6 PG owners、9 final lanes、174 tests

- 44 exact coverage keys（29 + 15）；
- 六个 concrete PG/migration owners；
- 九个 isolated lanes（六 PG + source-sync-job + MinIO + Redis）；
- 174 exact named tests（159 + 15，两个 rename 不增量）。

**PASS**。

### 6.23 Item 4/5 limited reopen 与 linear sequence

- Item 4：0005 full-chain owner 因 head/cycle assertion 更新需 fresh 运行；
- Item 5：postgres_sources.py 与 PG owner 因 provenance 改读 original_available_at 需 fresh；
- linear sequence：docs-only freeze → fresh dual review PASS → Controller acceptance + local commit → prerequisite → Item 6 main。

**PASS**。

## 7. Hostile schema-valid case search

### 7.1 Retry-mutated available_at

Row 的 available_at 被 retry 改写 → migration fingerprint reproducer 用 current available_at 候选 → 不等 stored fingerprint → fail closed。**正确。**

### 7.2 Payload schema mismatch backfill

Row 的 historical request payload schema 与 definition schema 不同 → migration 候选用 definition schema → fingerprint reproducer 含 request schema → 不等 → fail closed。**正确。**

### 7.3 Cross-definition same-key after fix

(tenant, definition A, key K) 不存在，(tenant, definition B, key K) 存在。Fix 按 exact definition A lookup → missing → None。合法 B/K 不影响。**正确。**

### 7.4 Single-valued misfire tamper

当前 misfire_policy 仅有 coalesce_one。写入 unknown 值 → strict reconstruction 失败 → ScheduleRepositoryError → unavailable。不进入 DTO compare。**正确。**

### 7.5 Noncanonical self-consistent bytes

Stored bytes SHA 自洽但非 canonical（如 trailing whitespace）→ strict canonical admission re-encode drift → fail closed。**正确。**

### 7.6 Duplicate key / BOM / trailing bytes

Strict admission 明确拒绝。**正确。**

### 7.7 Definition disable after lease

target §6.1："already-LEASED Job 的 current active/disabled status 不参与 live predicate"。**正确。**

### 7.8 get_source_receipt legacy 13-core-all-null row

target §9："合法 0001 13-core-all-null legacy row → None"。不伪造成 receipt。**正确。**

### 7.9 Transaction outcome precedence

target §9：rollback 自身 failure（含 exact 55P03）→ transaction_aborted，最高优先。rollback 成功时 original typed lock → unavailable。**正确。**

### 7.10 New-enqueue invalid payload rejection

target §3.4/§3.4.1：invalid UTF-8、sensitive/unsupported/float、duplicate/BOM/trailing、noncanonical/self-consistent bytes、bytes/SHA drift → closed JobInputError，fingerprint/session/SQL/publisher 均零调用。**正确。**

### 7.11 Prerequisite test does not require future lookup surface

target §3.4.2：renamed retry test 直接读取 durable columns，不构造 JobIdempotencyRecord，不调用 future get_by_idempotency_key。**正确。**

### 7.12 Workflow zero-diff enforcement

target §8.6/§12：两份 CI workflow 在 prerequisite 与 Item 6 main incremental gate 保持 zero diff，final nine lanes 只在 Item 8 materialize。**正确。**

### 7.13 Sensitive-key backfill admission（DSV4P-R3-01）

target §13.4：backfill PG named test 包含 self-consistent raw/stored-SHA sensitive-key parameters。exact lowercase token 与 recursive mixed-case ToKeN 各自独立作为 parameter case，各自提供 self-consistent SHA，证明 case-insensitive recursive closed-set admission 在 identity DDL/write 前 fail closed。**正确。**

### 7.14 Migration-local/domain canonical admission equivalence（DSV4P-R3-01）

target §8.6 step 3：pure reproducer named test 冻结 migration-local admission 与 domain parse_canonical_document 的逐值 ACCEPT/CANONICAL_INVALID 等价。六个 sensitive literal 各自独立 reject，near-miss keys（apikey/password_hint/token_count/x-authorization）保持 accept。migration 不 import domain helper，等值由 corpus pin。**正确。**

## 8. New blocker search

逐项检查：

1. **0006 五对象是否完整**：三 CHECK（deadline/schema name/version）+ function + trigger。与 manifest 一致。无遗漏。
2. **App role 无 UPDATE 权限**：target §8.6 明确。正确。
3. **models_identity.py zero diff**：target §8.6 明确。正确。
4. **Fingerprint reproducer 排除 idempotency key**：target §8.6 明确。正确。
5. **datetime.isoformat() 无格式化/截断**：target §8.6 明确。正确。
6. **Post-backfill 验证**：target §8.6 明确。完整。
7. **Downgrade 空表要求**：target §8.6 明确。严格。
8. **CI workflow zero diff**：target §8.6 明确。正确。
9. **SourceScheduleGatewayProtocol 有 validate_cron_expression**：target §3.3 明确列出。正确。
10. **New-enqueue pre-session canonical admission**：target §3.4/§3.4.1 明确 PostgresJobStore 唯一 owner。正确。
11. **Prerequisite test boundary**：target §3.4.2 明确 retry test 只读 durable columns。正确。
12. **Investment README owner**：target §8.6 明确 two docs paths。正确。
13. **Backfill sensitive-key parameters**：target §13.4 明确 token + recursive ToKeN 作为 independent parameters。正确。
14. **Migration-local/domain equivalence pin**：target §8.6 step 3 明确 pure reproducer test 冻结逐值等价。正确。
15. **Six sensitive literals independent reject**：target §8.6 step 3 明确 password/secret/token/authorization/cookie/api_key 各自独立 parameter case。正确。

**未发现新 blocker。**

## 9. Residual risks

fix §7 已列出：

- Nonempty legacy DB 含无法证明 row → 0006 fail closed。这是 deliberate admission，不是 blocker。
- 既有 provider 非 exactly-once、Source/Job 双事务窗口、Redis hint 不可靠等 residual 继续保留。
- 无 unclassified residual、blocking open question 或 deferred finding。

**确认。**

## 10. Final conclusion

**PASS / open H/M/L = 0/0/0**

原始 2H/3M、Round 2 1H/1M、Round 3 2H/2M 与 DeepSeek V4 Pro Round 3 1L 共十二项 finding 均已在 target/master/fix 中充分修复。exact 12 path scope（production/test 10 + docs 2，workflow deferred Item 8）、strict UTF-8 closed canonical JSON admission（migration 与 new-enqueue）、0006 fields/objects/locks/admission/downgrade、payload schema mismatch、definition observable boundary、cron owner/order、schedule taxonomy、44 keys、six owners、nine lanes、174 exact names、dedicated owner、source hostile tests、Item 4/5 evidence reopening 与 linear sequence、prerequisite test boundary、two READMEs、workflow zero-diff enforcement、new-enqueue pre-session canonical admission、**backfill sensitive-key parameter matrix 与 migration-local/domain canonical admission equivalence pin** 均已验证。未发现新 blocker 或 hostile schema-valid 反例。

本 artifact 不授权任何 implementation、test、PG、stage、commit、push、PR 或部署。

## 11. Post-write freeze protocol

- HEAD 仍为 4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723；
- reviewed target SHA/lines 仍为 dc210d4a3a6c0c4b7f5521e6e372f5ec0cc7e236c9c09a52460ad6847d432fa0 / 3564；
- master SHA/lines 仍为 83680025d05881ef535c124120e39aefd3c964615abab237aca0b54f30acef62 / 4498；
- fix SHA/lines 仍为 9066d39e98525e4d4a068ae03fe54679fc5690e1da72490fcec0ad92e8a697e1 / 331；
- artifact final SHA-256 与行数由写后只读命令计算。
