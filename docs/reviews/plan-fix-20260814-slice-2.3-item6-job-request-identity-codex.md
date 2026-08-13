# Slice 2.3 Item 6 Job Request Identity Plan Fix

- 日期：2026-08-14（Asia/Shanghai）
- Gate：Gateflow plan fix metadata closure；fresh same-new-SHA Round 4 dual PASS后Controller accepted，local corrective-plan commit next
- 分支：`codex/investment-platform`
- 基线/HEAD：`4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723`
- Source review：`docs/reviews/plan-review-20260813-234659.md`
  - SHA-256：`4d27271b57f7cbb1bfcd2065ecdf1bd08da0459782e6ab7a76ac3358019edbe0`
  - 行数：227
  - 结论：`FAIL / open H/M/L=2/3/0`
- DeepSeek V4 Pro Round 3 re-review：`docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-deepseek-v4-pro-round3.md`
  - SHA-256：`e8739eecd9c505e607efe94f0d70f6464ec6c8d8c7dd5be37d5b5809dfece103`
  - 行数：104
  - 结论：`FAIL / open H/M/L=0/0/1`
- DeepSeek V4 Pro Round 4 re-review：`docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-deepseek-v4-pro-round4.md`
  - SHA-256：`9a41173eb6c88c17f3bb0e0e8a1e0f21d7b511c18a8bff44977f82d71fdac378`
  - 行数：93
  - 结论：`PASS / open H/M/L=0/0/0`
- MiMo Round 4 re-review：`docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo-round4.md`
  - SHA-256：`8bb545597568e836447249fbd7620cc15d1d2cb9fbd46661e29f8cfcc816c393`
  - 行数：563
  - 结论：`PASS / open H/M/L=0/0/0`
- Corrected target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
  - DeepSeek V4 Pro Round 3 Low fix写后语义 SHA-256：`dc210d4a3a6c0c4b7f5521e6e372f5ec0cc7e236c9c09a52460ad6847d432fa0`
  - 行数：3564
- Corrected master：`docs/plans/2026-08-10-investment-platform-restoration.md`
  - DeepSeek V4 Pro Round 3 Low fix写后语义 SHA-256：`83680025d05881ef535c124120e39aefd3c964615abab237aca0b54f30acef62`
  - 行数：4498
- Original fix-writer scope：上述target、master与本artifact共exact三path
- Controller acceptance：`docs/reviews/plan-acceptance-20260814-slice-2.3-item6-job-request-identity-codex.md`；metadata closure exact四path
- 外部边界：未改production/test/README/CI；未运行test、PostgreSQL、Docker、network、provider、model、Broker、交易或部署；未stage、commit、push或创建PR

## 1. Controller adjudication

正式review的五项finding全部为直接代码事实支持的plan blocker，Controller裁决均为`accepted`：

| Finding | Severity | Decision | Candidate status |
|---|---|---|---|
| `S23-I6-PLAN-01` | High | accepted | 已修复，待fresh re-review最终确认 |
| `S23-I6-PLAN-02` | High | accepted | 已修复，待fresh re-review最终确认 |
| `S23-I6-PLAN-03` | Medium | accepted | 已修复，待fresh re-review最终确认 |
| `S23-I6-PLAN-04` | Medium | accepted | 已修复，待fresh re-review最终确认 |
| `S23-I6-PLAN-05` | Medium | accepted | 已修复，待fresh re-review最终确认 |

没有`rejected-with-reason`、`deferred-with-owner`或`needs-more-evidence` finding。source review保持immutable；最终标题状态权威属于fresh independent re-review，不由本fix自报替代。

### 1.1 Round 2 internal redteam adjudication

Internal redteam锁定Round 1 frozen target
`85c7910c4a7da0a86c81a9ab929d7acd25d4c59d283bf2133b2216fc4be83f9c` / 3454行、master
`d7089e71ed26176c9194e46e1d5a9645848d949764ef4a7271e4d97281e10fdb` / 4446行与fix
`01dd54e95cd369866f791ae53243778081b893fd89f81b820502025e3827aa93` / 198行，给出
`FAIL / open H/M/L=1/1/0`。Controller接受两项：

| Finding | Severity | Decision | Round 2 fix |
|---|---|---|---|
| `S23-I6-REDTEAM-R2-01` prerequisite未授权CI/README owner | High | accepted | 总scope改为exact13 paths，并冻结workflow command/ignore与existing CI test owner |
| `S23-I6-REDTEAM-R2-02` fingerprint前未证明payload canonical bytes | Medium | accepted | bytes SHA后增加strict canonical parse/re-encode byte identity admission及negative PG cases |

Round 1三SHA现在只作historical/superseded证据。MiMo在STOP到达前完成old-SHA artifact
`docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo.md`，SHA-256
`ac1193fe28cd02a3a06df5ba1ae67f380dd22e5f9239a159dd2903025cc0ba22` / 218行，虽为
`PASS / open H/M/L=0/0/0`，但漏后续accepted 1H/1M，状态精确为
`SUPERSEDED / REJECTED / IMMUTABLE`且不能计入fresh new-SHA gate。DeepSeek V4 Pro old-SHA attempt已验证actual
route但HTTP 402，无artifact、无verdict、无PASS，也不能计gate。

### 1.2 Round 3 internal redteam adjudication

Round 3 internal redteam锁定Round 2 target
`c4a8de3476487bd4c27357e7d9124e95c7e996257811d171f4ff036e4c495dc3` / 3485行、master
`afaa3377a0c2f82ec814fdc16718f3c6819e99c93647320c6bb7e29b94aaa705` / 4463行与fix
`f5c225d63ab867f0435815d672779f513cc39d11791c002b6056fcea8944de1d` / 239行，给出
`FAIL / open H/M/L=2/2/0`。Controller接受全部四项：

| Finding | Severity | Decision | Round 3 fix |
|---|---|---|---|
| `S23-I6-REDTEAM-R3-01` future workflows错误纳入prerequisite | High | accepted | scope收敛exact12；workflow/static test延至Item 8，前两级zero diff/not run |
| `S23-I6-REDTEAM-R3-02` new enqueue缺pre-session canonical admission | High | accepted | PostgresJobStore唯一owner，fingerprint/session/SQL/publish前strict validate，closed input/zero side effect |
| `S23-I6-REDTEAM-R3-03` prerequisite retry test越界要求future lookup | Medium | accepted | rename为durable columns preservation；record/protocol/service lookup留Item 6 main |
| `S23-I6-REDTEAM-R3-04` investment README owner遗漏 | Medium | accepted | exact12 docs为tests README + investment README；root README zero diff |

Round 2三SHA现为historical/superseded。MiMo Round 2 artifact
`docs/reviews/plan-rereview-20260814-slice-2.3-item6-job-request-identity-mimo-round2.md`，SHA-256
`dc849d2d60184beb0dcaeeaf20711435706804b40995fdc4ce03a19062d2b139` / 312行，虽为PASS0但遗漏上述2H/2M，
状态为`SUPERSEDED / REJECTED / IMMUTABLE`。DeepSeek V4 Pro Round 2 actual-route attempt再次HTTP 402，无artifact、
无verdict、无PASS。Round 1 MiMo `ac1193fe…`同样保持immutable rejected；本fix不编辑任何external artifact。

### 1.3 DeepSeek V4 Pro Round 3 adjudication

DeepSeek V4 Pro official Round 3 artifact锁定上一target/master/fix三SHA并给出
`FAIL / open H/M/L=0/0/1`。Controller接受唯一finding：

| Finding | Severity | Decision | Current candidate status |
|---|---|---|---|
| `S23-I6-DSV4P-R3-01` backfill sensitive-key matrix与migration-local/domain canonical admission pure pin未闭合 | Low | accepted | 已修复，fresh new-SHA DeepSeek V4 Pro + MiMo re-review pending |

修复只扩展既有两个named tests的parameter corpus：不新增/重命名test，不让migration import domain helper，不编辑official
DeepSeek或任何MiMo artifact。official `FAIL / 0/0/1`保持immutable；本fix不得自报PASS。

## 2. Direct evidence and first-principles decision

问题不是Source writer的实现技巧不足，而是durable owner没有保存计划要求恢复的事实：

1. accepted `0003`只有一个`job_runs.available_at`，且app可更新；真实retry helper会把它改为下一次claim eligibility；
2. generic `job_enqueue_request_fingerprint`包含exact `available_at`、deadline、七字段descriptor、request payload schema name/version与payload SHA；明确不含idempotency key；
3. `job_runs`此前只保存payload bytes/SHA，没有request payload schema identity；generic domain又允许payload schema与descriptor schema不同；
4. Item 5 `postgres_sources.py`此前用current mutable `available_at`重验manual/scheduled provenance，跨UTC retry会产生假drift或移动首次scheduled window；
5. schedule croniter语义唯一owner是ScheduleService私有helper，Source facade没有合法validation-only入口；
6. persisted schedule strict reconstruction发生在immutable compare前，malformed enum/canonical/hash不能被诚实分类为caller conflict。

因此最小可信解不是删减fingerprint字段、相信stored hash、猜历史值或收窄generic public contract，而是在accepted migration链后新增足以逐字段重建原请求的immutable durable facts，并保持owner边界。

## 3. Accepted architecture decisions

### 3.1 Linear `0006_job_request_identity`

- `0003_durable_jobs.py`与`0005_source_connectors_health.py`保持byte-identical；new revision的`down_revision`精确为`0005_source_connectors_health`。
- `job_runs`新增最终NOT NULL三列：
  - `original_available_at TIMESTAMPTZ`；
  - `request_payload_schema_name TEXT`；
  - `request_payload_schema_version INTEGER`。
- mutable `available_at`只负责retry eligibility；lookup、manual/scheduled provenance、query window与takeover全部读取`original_available_at`。
- generic payload/descriptor schema mismatch继续合法；不新增equality admission，不删fingerprint输入字段。
- raw SQL Job owner继续拥有`job_runs`；`models_identity.py`保持zero diff。

### 3.2 Exact migration object manifest

0006只创建下列五个named object：

1. `ck_job_runs_original_deadline_after_available`；
2. `ck_job_runs_request_payload_schema_name_nonempty`；
3. `ck_job_runs_request_payload_schema_version_positive`；
4. `guard_job_runs_request_identity_immutable`；
5. `guard_job_runs_request_identity_immutable_trigger`。

app role不得获得三个新列的UPDATE权限；existing tenant RLS、table ACL与其它列级grant保持原样。

### 3.3 Upgrade/backfill admission

- 在同一migration transaction中以NOWAIT顺序锁`job_runs`再`job_definitions`；lock conflict整次fail closed，无partial DDL。
- 三列先nullable加入。每row先验证raw payload bytes SHA等于stored值，再执行与domain
  `parse_canonical_document`等值的strict admission：exact UTF-8、无BOM/duplicate key/trailing bytes，只允许closed
  null/bool/int/string/array/object tree，拒绝float/NaN/Infinity、non-string key与closed sensitive key，并以
  sort-keys/compact-separators/`ensure_ascii=False`重新编码；re-encoded bytes必须与raw bytes逐字节相等。invalid UTF-8、
  bytes/SHA drift、SHA自洽但noncanonical JSON或canonical re-encode drift均在identity写入前整次fail closed。
- canonical admission通过后，migration-local fingerprint reproducer才按domain真源的exact keys、canonical JSON encoding、UTF-8 SHA-256、aware UTC `datetime.isoformat()`重算fingerprint；明确不含idempotency key。
- 既有pure
  `test_0006_migration_fingerprint_reproducer_matches_domain_and_excludes_idempotency_key`同时冻结migration-local canonical
  admission与public domain `parse_canonical_document`的逐值等价；migration保留frozen local implementation，不import domain
  helper。valid-UTF-8 raw按exact `ACCEPT`/`CANONICAL_INVALID`归一：domain侧只捕获`JobInputError`，migration侧只捕获0006定义的
  exact private canonical-invalid exception，其它异常直接失败；禁止broad catch与错误文案比较。`ACCEPT`至少逐项含root
  `null`/`true`/`-1`/`"中"`、array `[null,false,0,"中",{}]`、sorted nested object，以及按canonical key顺序编码且分别含`apikey`、
  `password_hint`、`token_count`、`x-authorization`的near-miss object，并逐值exact比较schema name/version、canonical bytes与
  SHA-256及输入raw-byte identity。`CANONICAL_INVALID`将`password`、`secret`、`token`、`authorization`、`cookie`、`api_key`作为六个独立cases，
  另含recursive mixed-case `ToKeN`、float/`NaN`、nested duplicate、BOM、trailing junk/whitespace、noncanonical key order、
  noncompact separators与escaped Unicode；禁止合并六key导致短路掩盖，禁止不可构造non-string JSON key。
- invalid UTF-8只由PG byte-wrapper验证，不与public text parser伪造pure等价。bytes/SHA drift在pure test中由migration wrapper以
  valid canonical raw + mismatched supplied SHA归一为`CANONICAL_INVALID`并证明parser零调用，同时保留PG参数覆盖。
- 对每个existing row，只以`current available_at`和definition schema作为候选历史事实；只有候选重算fingerprint与stored值exact相等，才证明并backfill。
- 任一row不等即整次fail closed。`current_attempt_number == 0`不是证明；one-way fingerprint不能反演；retry-mutated timestamp或合法historical schema mismatch不能被猜值掩盖。
- backfill后再次逐row验证bytes SHA、strict canonical re-encode identity与fingerprint，再SET NOT NULL、安装CHECK/guard并做catalog/ACL/RLS self-check。

### 3.4 Downgrade admission

- 先取得相同NOWAIT locks，并以`pg_depend`拒绝三个列、CHECK、function/trigger的owner外dependency。
- `job_runs`必须精确为空；任何row存在即拒绝，以免drop immutable request facts造成数据损失。
- admission通过后按trigger -> function -> CHECK -> columns逆序删除，禁止CASCADE，最终验证exact 0005 catalog。

### 3.4.1 New-enqueue canonical admission

- `PostgresJobStore.enqueue`是唯一validation owner；JobService不复制。
- 在fingerprint helper、session factory、任何SQL/DML或可能publish的返回之前，strict UTF-8 decode request payload，
  执行domain-equivalent canonical parse/re-encode，并要求returned bytes/SHA等于request bytes/SHA。
- invalid UTF-8、sensitive/unsupported/float、duplicate/BOM/trailing、noncanonical/self-consistent bytes或bytes/SHA drift
  统一closed `JobInputError`；fingerprint/session/row/publisher均零调用。
- valid canonical case才持久化三个original identity列。renamed existing prerequisite test覆盖direct Store与JobService caller，
  但只证明Store唯一owner。

### 3.4.2 Prerequisite vs Item 6 main boundary

- Prerequisite只负责0006 schema/migration、enqueue canonical admission与三列insert、retry保持original columns、Source
  provenance改读original列。
- `JobIdempotencyRecord`、storage/service protocol lookup、JobService lookup与Source recovery reconstruction仍全部属于Item 6
  main exact20-path surface及其既有lookup tests。
- Prerequisite renamed retry test直接读取durable columns；不得构造或调用future lookup surface。

### 3.5 Job lookup observability boundary

- 先以tenant + exact descriptor解析definition，再查询`(tenant_id, resolved_definition_id, idempotency_key)`。
- exact definition/key missing或cross-tenant均返回`None`；其它合法definition下的same key不影响结果。
- 该surface没有original definition proof或job_id，cross-definition relocation不可观察，诚实行为是exact lookup missing。
- 禁止tenant-wide key scan、tenant-global unique或把合法B/K误报tamper。可证明drift只覆盖命中exact row内部descriptor、payload、hash、original time与request schema identity。

### 3.6 Schedule validation and error ownership

- `ScheduleService.validate_cron_expression(expression: str) -> None`是唯一public validation-only seam；只复用现有private croniter helper，零Store、零clock、零mutation。
- `InvestmentSourcesService.ensure_polling_schedule`先做structural/tz，再调用该seam；它发生在schedule lookup和任何source read之前。invalid cron在hit/miss均为`ScheduleInputError`且零Store/source调用。
- persisted row先strict reconstruct。unknown/single-valued misfire tamper、invalid cron/timezone、noncanonical payload/hash或其它malformed shape为`ScheduleRepositoryError -> SourceServiceUnavailableError(unavailable)`。
- 只有request与persisted row均为当前schema-valid完整DTO时，immutable field drift才为`ScheduleVersionConflictError`。

## 4. Exact implementation sequencing and ownership

当前线性gate固定为：

1. 本docs-only candidate冻结；
2. actual-route DeepSeek V4 Pro与MiMo对同一target/master/fix SHA独立plan review；
3. 两路均`PASS / open H/M/L=0/0/0`后Controller acceptance与local corrective-plan commit；
4. exact-twelve-path 0006 prerequisite implementation（production/test exact10 + docs 2）；
5. focused/coverage/static/PG/mechanical validation、independent deepreview/fix/re-review、单独local prerequisite accepted commit；
6. 以新clean baseline恢复Item 6 exact20-path main writer；
7. Item 6 main implementation/review/fix/re-review/local accepted commit；
8. 后续Slice aggregate gates。

0006 prerequisite exact twelve paths：

Production（4）：

- `dayu/investment/storage/migrations/versions/0006_job_request_identity.py`；
- `dayu/cli/workspace_migrations/platform_jobs.py`；
- `dayu/investment/storage/postgres_jobs.py`；
- `dayu/investment/storage/postgres_sources.py`。

Tests（6）：

- `tests/cli/workspace_migrations/test_platform_jobs.py`；
- `tests/investment/test_platform_migrations.py`；
- `tests/integration/investment/test_platform_migrations_postgres.py`；
- `tests/integration/investment/test_job_request_identity_migration_postgres.py`；
- `tests/integration/investment/test_postgres_jobs.py`；
- `tests/integration/investment/test_postgres_sources.py`。

Docs（2）：

- `tests/README.md`。
- `dayu/investment/README.md`。

`test_job_request_identity_migration_postgres.py`是0006唯一instrumented PG coverage owner；existing `test_platform_migrations_postgres.py`继续是0005 owner，只更新full-chain/head/cycle assertion。两个migration owner不得在同一process组合或共享coverage分母。
Prerequisite的tests README只文档当前local dedicated 0006 commands/owners与future CI deferral；investment README同步
0006 schema、new-enqueue/backfill canonical admission与dedicated local lane。Root README及两份workflow zero diff。
Existing planned workflow audit、final nine commands/ignores与两workflow mutation只在Item 6 main materialize final owner后由
Item 8 explicit CI/docs slice完成；prerequisite与Item 6 main incremental gate不materialize/collect/run该future test。

Item 4与Item 5的accepted commits保持历史真源，但证据有限重开：0005 full-chain owner因head/cycle更新需fresh运行；`postgres_sources.py`与其PG owner因provenance改读original seed需fresh review/coverage/PG。新字节及证据只进入prerequisite accepted commit。

## 5. Tests and normalized ledger

本candidate在历史159 exact names上新增15项、rename两项但不增量，当前总数174：

- prerequisite 12项：migration reproducer 1、dedicated 0006 PG owner 7、Job repository 2、Source repository hostile provenance 2；
- Item 6 main corrective 3项：Schedule validation seam、hit/miss ordering、schema-valid conflict vs malformed persisted row；
- renamed：schedule `any immutable drift`收窄为`each schema-valid immutable drift`；cross-midnight name显式写`original_available_at`。

两项Source hostile proof必须覆盖：

1. manual existing-operation在current `available_at`跨UTC retry后仍以original seed重验，零假drift；
2. scheduled在首次acquire前retry，以及existing operation takeover，都以original seed构造/验证同一window。

两个Job prerequisite exact names为：

- `test_new_enqueue_strictly_validates_canonical_payload_before_session_fingerprint_or_publish_and_persists_original_identity`；
- `test_retry_mutates_only_current_available_at_and_preserves_original_request_identity_columns`。

前者覆盖Store唯一pre-session owner与零side effect；后者只查current/original列，不调用future lookup。

既有dedicated 0006 named test
`test_0006_proven_backfill_persists_original_available_and_request_payload_schema_identity`以parameter cases同时覆盖
canonical success、invalid UTF-8/closed primitive、bytes/SHA drift、SHA自洽但noncanonical JSON、duplicate key/BOM/
trailing bytes、canonical re-encode drift，以及stored SHA与raw bytes自洽的exact lowercase `token`代表键与recursive
mixed-case `{"a":{"ToKeN":"x"}}`独立sensitive parameters；negative cases均证明无partial DDL/identity write且0005
catalog exact。invalid UTF-8只属该PG byte-wrapper层。
不新增test名，仍为12 prerequisite tests / 174 overall names。

同一既有pure reproducer named test另按§3.3冻结valid/hostile corpus、双方exact
`ACCEPT`/`CANONICAL_INVALID` classification与accept schema/bytes/SHA逐值等价；不比较错误文案、不broad-catch，也不把
invalid UTF-8伪装成public text parser输入。

其余机械账本：

- `COVERAGE_OWNER_TESTS`：44 exact keys，29 tracked-existing + 15 planned-new；
- concrete PG/migration owners：6；
- final isolated PG/source-job/MinIO/Redis lanes及aggregate ignores：9，明确只在Item 8 final CI/docs gate闭合；
- §13.3 operation/crash/health子集仍53，Item 5 PG27 + Item 6 APP4/JOB15/OP5/HEALTH2互斥穷尽；
- 0006 prerequisite：exact12 paths（production/test 10 + docs 2）/ 12新增tests；future CI audit不计incremental evidence；
- Item 6 main：exact20 paths / 51 tests。

Prerequisite与Item 6 main incremental gate两份workflow保持zero diff，不materialize/collect/runfuture workflow static test；
Item 8等``test_source_sync_job.py``与全部final owner materialize后，才写两workflow九commands/九ignores、运行existing
workflow audit并再次同步tests README。

## 6. Per-finding fix status

### S23-I6-PLAN-01-已修复-[高]-mutable retry time与immutable original seed已分离

- Target locations：§3.2.1、§3.2.2、§3.4、§3.5、§5.1、§6.2、§8.6、§12–§16。
- Fix：新增`original_available_at` durable owner；current `available_at`仅retry eligibility；manual/scheduled lookup、provenance与window改读original；补两个真实Source hostile PG tests。
- Verification required：跨UTC manual existing-operation、scheduled pre-first-acquire retry、takeover与lost-response exact fingerprint。

### S23-I6-PLAN-02-已修复-[高]-request payload schema identity已成为durable fact

- Target locations：§3.4、§8.6、§13.4。
- Fix：持久化schema name/version并用于exact request重建；保留generic mismatch；migration candidate仅在stored fingerprint证明时backfill。
- Verification required：equal/mismatch、name-only/version-only drift、invalid UTF-8/closed JSON、noncanonical self-consistent bytes、bytes/SHA、canonical re-encode drift，以及migration/domain fingerprint等值。

### S23-I6-PLAN-03-已修复-[中]-lookup合同收窄到可观察definition scope

- Target locations：§3.4、§13.1、§15。
- Fix：exact descriptor先解析definition；合法other-definition same key不构成tamper；relocation按missing，禁止tenant-global workaround。
- Verification required：A/K missing且B/K存在仍`None`；命中exact A/K内部drift才repository failure。

### S23-I6-PLAN-04-已修复-[中]-cron语义由Schedule owner经窄public seam提供

- Target locations：§3.3、§5.2、§13.1、§13.4。
- Fix：新增validation-only gateway/service method并冻结pre-lookup/pre-source-read ordering；禁止Source复制croniter/private helper。
- Verification required：hit/miss invalid cron同一input error、Store/source/clock/mutation调用均零。

### S23-I6-PLAN-05-已修复-[中]-schema-valid conflict与persisted corruption已分流

- Target locations：§5.2、§13.1、§13.4、§15。
- Fix：strict reconstruction先行；malformed enum/canonical/hash/cron/timezone为repository unavailable；两份valid DTO不同才version conflict。
- Verification required：每个当前可构造alternate immutable field conflict；single-valued misfire tamper与unknown enum走unavailable且零mutation。

### S23-I6-DSV4P-R3-01-已修复-[低]-backfill hostile admission与domain等价验证已闭合

- Target locations：§8.6 step 3、§13.4、§17.1；master current status/current decision/bookkeeping。
- Fix：在existing PG backfill named test加入self-consistent raw/stored-SHA sensitive-key parameters；在existing pure reproducer named test内用
  closed valid/hostile corpus逐值pin migration-local admission与public domain parser，六个sensitive literal各自独立reject，
  near-miss keys保持accept，classification只允许`ACCEPT`/`CANONICAL_INVALID`，accept exact比schema/bytes/SHA/raw identity。
- Verification required：invalid UTF-8仅byte-wrapper、valid UTF-8 pure parser corpus、双方exact typed exception adapter、零错误
  文案比较/零broad catch、每个PG negative case零partial DDL；fresh new-SHA双路复审确认。

## 7. Residual risks and stop state

- Nonempty legacy DB可能含无法由stored fingerprint证明的retry-mutated或payload-schema-mismatch row，0006会fail closed。若必须保留，owner为独立legacy identity migration/public unavailable work unit，不在Item 6隐含兼容。
- 原既有residual继续保留：provider非exactly-once、Source/Job双事务窗口、Redis hint不可靠、PONR同步thread无wall-clock上界、Job/Schedule repository public failure无typed diagnostic。
- 无unclassified residual、blocking open question或deferred finding；accepted Low已由fresh Round 4双路`PASS / open H/M/L=0/0/0`确认关闭。产品新增“保留不可证明legacy row”要求才触发重新设计。
- 本fix语义正文不自报review结论；Controller metadata closure后的当前状态为`CORRECTIVE PLAN ACCEPTED / FRESH SAME-NEW-SHA DEEPSEEK V4 PRO + MIMO ROUND 4 PASS 0/0/0 / LOCAL ACCEPTED PLAN COMMIT NEXT / IMPLEMENTATION FROZEN UNTIL COMMIT`。

## 8. Completion / stop

本docs-only fix与fresh Round 4双路plan review已由Controller接受；official DeepSeek Round 3仍是immutable `FAIL / 0/0/1`，旧MiMo R1/R2/R3继续superseded/rejected/immutable。下一动作只允许Controller逐path核验并创建exact十一path local accepted corrective-plan commit；commit成功后才可dispatch exact-twelve-path 0006 prerequisite。当前任何implementation、test、PG、stage/commit、push、PR或部署都超出本metadata writer授权。
