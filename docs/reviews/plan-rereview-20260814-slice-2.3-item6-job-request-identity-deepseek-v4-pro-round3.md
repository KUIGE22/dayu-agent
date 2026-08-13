# Slice 2.3 Item 6 Job Request Identity Round 3 独立 Plan Re-Review（DeepSeek V4 Pro）

- 日期：2026-08-14（Asia/Shanghai）
- 角色：Gateflow review worker（非 controller，不启动 /gateflow，不进入 implementation/commit）
- Actual route：DeepSeek 官方 Anthropic endpoint（Controller 已核验路由）
- Model：`deepseek-v4-pro[1m]`
- 分支：`codex/investment-platform`；HEAD：`4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723`；index：empty
- 外部边界：未读/未采信任何 MiMo 或 internal verdict 内容；仅核旧 reviewer artifact identity/rejected bookkeeping。未运行 test/PG/Docker/provider/network/model；未 stage/commit/push/PR；唯一写入为本 artifact。

## 1. 冻结核验（pre-freeze）

| Artifact | 冻结 SHA-256 | 实际 SHA-256 | 冻结行数 | 实际行数 |
|---|---|---|---|---|
| target `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `f641eb210953a60756c8ff2ed36eea34e0a5c429457e846941b531a5a7b32c29` | 匹配 | 3536 | 匹配 |
| master `docs/plans/2026-08-10-investment-platform-restoration.md` | `18ae04a6e759737f5a37fa2c07cbd2f7e6f083a577e05d0e5b183b83b4d2b2a8` | 匹配 | 4475 | 匹配 |
| fix `docs/reviews/plan-fix-20260814-slice-2.3-item6-job-request-identity-codex.md` | `b07f89affe919bc7dccff98211eda9a322d0dc682f89691c0b920c466b346780` | 匹配 | 288 | 匹配 |
| formal source `docs/reviews/plan-review-20260813-234659.md` | `4d27271b57f7cbb1bfcd2065ecdf1bd08da0459782e6ab7a76ac3358019edbe0` | 匹配 | 227 | 匹配 |

branch/HEAD/index 均与冻结值一致，未发生漂移，允许继续。

## 2. 直接代码证据核验（HEAD `4ed503f`）

formal review 引用的代码事实在本轮全部以当前 HEAD 复核为真：

| 事实 | 证据 |
|---|---|
| fingerprint 含七字段 descriptor + request payload schema name/version + payload SHA + available/deadline，不含 idempotency_key | `dayu/investment/domain/jobs.py:2048-2088`（SHA `12d2497d…` 不变） |
| `CanonicalJobDocument` schema name/version 是 bytes 外独立字段；`__post_init__` 只验 SHA 格式不验 bytes↔SHA 相等（“SHA 自洽但 noncanonical bytes”是真实可达 hostile 形态） | `jobs.py:402-438` |
| `parse_canonical_document` 用 `object_pairs_hook=_reject_duplicate_keys`、`parse_constant=_reject_nonfinite`、closed primitive validator、sensitive-key 拒绝、重编码逐字节相等 | `jobs.py:560-606`；`_SENSITIVE_KEY_SET` 非空（`jobs.py:41`），validator 拒绝命中键（`jobs.py:517`） |
| `JobEnqueueRequest.__post_init__` 不比较 payload schema 与 descriptor schema → 合法 mismatch 持续存在 | `jobs.py:1043-1060` |
| 当前 `PostgresJobStore.enqueue` 先 `_session(scope)`（829）后算 fingerprint（894）；job_runs 仅此一个 INSERT 站点（923）且不写 original 三列 | `postgres_jobs.py:809-952`（SHA `69f7a063…` 不变） |
| retry 改写 `job_runs.available_at = next_available_at` | `postgres_jobs.py:4017-4085` |
| 0003 只有一个 `available_at`、app 列级 UPDATE grant 含 `available_at`（681）、immutable guard 刻意不含它；`deadline_at` 不在 UPDATE grant（候选事实 deadline 即原始值） | `0003_durable_jobs.py:180-235, 660-721` |
| Source provenance 现读 mutable `job_runs.available_at` | `postgres_sources.py:1591, 1660, 1663, 1668, 2062`（SHA `8505198e…` 不变） |
| croniter 语义唯一私有 helper `_validate_croniter_expression`（164），public `register`（866）调用之；misfire enum 仅 `COALESCE_ONE` | `schedule_service.py:164-190, 866`；`schedules.py:74-77` |
| `JobService.enqueue` 只 registry gate → 单次 store.enqueue → best-effort publish，服务层无 payload 校验复制 | `job_service.py:668-693` |
| `get_by_idempotency_key` / `JobIdempotencyRecord` 全仓不存在 → prerequisite 不得提前物化 lookup surface 的边界可构造 | grep 全仓零命中 |
| 0005 revision=`0005_source_connectors_health`、down_revision=`0004_durable_schedules` → 0006 linear 后继合法；0005 SHA 与 §12 item4 manifest（`90b66245…`）一致 | `0005_source_connectors_health.py:36-37` |
| `models_identity.py` 零 job_runs 引用 → 0006 zero-diff 可构造 | grep 零命中 |
| CLI head test `test_platform_jobs_workspace_migration_documents_0005_as_current_head` 真实存在于 `tests/cli/workspace_migrations/test_platform_jobs.py:161`（rename 目标真实） | 存在 |
| `test_job_request_identity_migration_postgres.py` 尚未存在（dedicated owner 确为新文件） | `tests/integration/investment/` 无此文件 |
| 两份 workflow 当前无 final 九 lane/MinIO pinned pull → 前两级 zero-diff 与 Item 8 延后为真实差异 | `ci-pr-extended.yml:39-44` 仅四条 PG lane |

## 3. 十一项重点检查结论

1. **exact12 路径**：production4（0006 migration、platform_jobs.py、postgres_jobs.py、postgres_sources.py）+ tests6（test_platform_jobs.py、test_platform_migrations.py、test_platform_migrations_postgres.py、test_job_request_identity_migration_postgres.py、test_postgres_jobs.py、test_postgres_sources.py）+ docs2（tests/README.md、dayu/investment/README.md）与 fix doc §4 逐项一致；12 path 全部落在 §11 production/test/docs allowlist 内，4 个 production path 全部命中 §11.1 44-key 矩阵。workflows 在 prerequisite 与 Item 6 main 两级 zero diff，final 九 lane/九 ignore/static audit 明确延后 Item 8（target §8.6、§14、§15 STOP；master 289-296、4143-4144 同口径）。**通过。**
2. **new-enqueue strict canonical admission**：§3.4 冻结 `PostgresJobStore.enqueue` 为唯一 owner，在 session factory / fingerprint / 任何 SQL / 返回给可能 publish 的 JobService 之前 strict UTF-8 decode + domain-equivalent parse（schema 取 request payload）+ 重编码 bytes/SHA 双比对；§13.4 renamed test 逐案覆盖 invalid UTF-8、sensitive、unsupported、float、duplicate、BOM、trailing、noncanonical self-consistent、bytes/SHA drift 九类 hostile，且 spy 证明 fingerprint/session/SQL/row/publisher 零调用；§15 STOP 条件双向闭合。当前代码 enqueue 首个动作即 `_session(scope)`、fingerprint 在 894 行，且 `CanonicalJobDocument` 构造不验 bytes↔SHA（“SHA 自洽”案例真实可达），证明该 admission 是不可省的实质新增而非冗余。**通过。**
3. **backfill 同等 admission**：§8.6 规范文本（2231-2235）要求与 domain `parse_canonical_document` 等值的逐项 admission（exact UTF-8、无 BOM/duplicate/trailing、closed primitive、拒 float/NaN/Infinity、非 string key、sensitive key、重编码逐字节相等），候选事实仅在 stored fingerprint 重算 exact 相等时写入。规范文本闭合；**唯一验证缺口见 finding L-01**。
4. **prerequisite 边界**：renamed retry test 只读 durable 列证明 `available_at` 变化而 original 三列不变；显式禁止构造 `JobIdempotencyRecord` 或调用 future `get_by_idempotency_key`；public lookup/reconstruction 归 Item 6 main。当前代码中该 surface 全仓不存在，边界可构造。**通过。**
5. **README 职责闭合**：tests/README.md 只文档化 0006 dedicated local lane、六 PG/migration owner 职责与 final CI deferral（对应 CLAUDE.md tests/ 触发规则与测试手册职责）；dayu/investment/README.md 同步 0006 三列 schema、admission 与 dedicated lane（对应 migration 变更触发规则与投资包手册职责）；根 README zero diff（migration head 变更不属于用户手册职责，符合触发规则“先检查是否属于职责范围”）。**通过。**
6. **0006 结构与安全**：三列 final NOT NULL + 五对象 manifest + `job_runs`→`job_definitions` ACCESS EXCLUSIVE NOWAIT 同序锁（upgrade/downgrade 一致；先锁 child 表配合 NOWAIT 不构成 40P01 死锁环，冲突即 55P03 fail closed，无 partial DDL）+ 单事务内两阶段 backfill（TOCTOU 被表级锁与事务封闭）+ 二次逐 row 验证后才 SET NOT NULL + app 无新列 UPDATE、既有 RLS/ACL 原样 + BEFORE UPDATE immutable trigger + single-manifest catalog self-check。`job_runs` 全仓唯一 INSERT 站点即 enqueue（923 行），“同一 INSERT 写三列”无旁路 producer。**通过。**
7. **payload-schema mismatch round-trip 与 lookup 边界**：三列持久化 request payload schema identity（允许与 descriptor 不同），new-enqueue admission 取 request payload schema，backfill 候选取 definition schema 且必须 fingerprint 证明（mismatch 行 fail closed，residual #10 明示）；lookup 以 tenant+exact descriptor 解析 definition 后按 (tenant, definition, key) 查询，other-definition same key 不影响 missing，relocation 不可观察等价 missing，合法 B/K 不误报 tamper（fix doc §6 要求 A/K missing+B/K 存在仍 None 的 hostile 验证）。**通过。**
8. **cron seam 与 schedule 分流**：`ScheduleService.validate_cron_expression` 唯一 validation-only seam，只复用私有 croniter helper、零 Store/clock/mutation；`ensure_polling_schedule` 在 get_by_key 与任何 source read 之前精确调用一次，hit/miss 同分类；persisted row 先 strict reconstruct，malformed enum/canonical/hash/cron/timezone → `ScheduleRepositoryError`→unavailable，仅两份 schema-valid 完整 DTO 的 immutable drift 才 `ScheduleVersionConflictError`。三个 corrective 测试（seam、ordering、分流）文件归属与 §11.1 owner tuple 一致。**通过。**
9. **机械账本**：§11.1 逐行计数 = 44 keys（29+15）；§14 Gate 2 = 6 个 PG/migration owners；final 九 lane = 六 PG + source-sync-job + MinIO + Redis，workflow 命令清单与九 ignore 一一对应；§13 四个子节 bullet 级逐名计数 = 52+42+53+27 = 174，全部唯一、零重复；§13.4 prerequisite 12 = 1（reproducer）+7（dedicated 0006 PG）+2（job）+2（source）；Item 6 main 51 = 原48+3。**通过。**
10. **Item4/5 有限重开与线性 sequencing**：重开仅限 0005 full-chain owner（head/cycle 断言）与 postgres_sources.py+其 PG owner（provenance 改读 original 列），二者路径都在 exact12 内；序列严格为 dual plan review → Controller acceptance/plan commit → prerequisite 实施/review/accepted commit → 以新 clean baseline 解冻 Item 6 main → Item 8；任一阶段不得把 Item 6 service/execution 塞入 prerequisite commit（§12、§15 STOP 闭合）。**通过。**
11. **Round 3 修订**：exact12 不含 workflows（zero-diff + Item 8 延后）；new-enqueue admission owner 可构造（enqueue 单入口单 INSERT 站点、request 在入口可见）；prerequisite test 名（`test_retry_mutates_only_current_available_at_and_preserves_original_request_identity_columns`）与边界不声称 public lookup；两份 README 均在 scope。**通过。**

## 4. Hostile cases 尝试与结果

- **SHA 自洽但 noncanonical bytes**：`CanonicalJobDocument.__post_init__` 不验 bytes↔SHA（`jobs.py:430-438`），该形态真实可达；new-enqueue 用重编码 bytes/SHA 双比对闭合，backfill 用重编码逐字节相等闭合。已覆盖。
- **自证但 schema 漂移的 backfill**：`available_at` retry 可改（`postgres_jobs.py:4067`）且 `deadline_at` 不可改，候选 `original=current available_at` + definition schema 必须 fingerprint 重算相等，`current_attempt_number==0` 捷径被 §8.6 明拒。已覆盖。
- **deadlock 环**：0006 先锁 job_runs 再 job_definitions 均 NOWAIT，先取得 child 表锁后再对 parent 的 NOWAIT 失败立即 abort，不形成 40P01 等待环；并发 enqueue 仅普通阻塞。无缺口。
- **job_runs 第二 producer 旁路**：全仓唯一 INSERT 站点。无缺口。
- **backfill 二次验证不比对写入列**：候选值即写入值，CHECK/trigger/NOT NULL 后置安装，事务内闭环；未发现可构造绕过。
- **改名账本**：`机械collector必须证明…两个rename`（target 3140、fix 210）经核对为 catalog 范围（schedule any→each、cross-midnight deadline/available_at→retry/original 两条均在 174 名单内）；CLI head 0005→0006 rename 为 extra-catalog（`不新增catalog名`，target 3134），不计入两 rename。**账本自洽，非 finding。**
- **prerequisite gate 时 postgres_jobs >=80% 可达性**：§14 将 79.874706%→80 的补齐归因于 Item 6 main 的 lookup test，而 prerequisite gate 已要求 changed owner instrumented >=80；prerequisite 自身的 2 项测试（约十参数 hostile admission + 列保留）亦新增大量 covered branch，未发现确定性矛盾，且任一 owner <80 时按 §14 fail closed → STOP 回 Controller 有既存治理出口。记入 residual 观察，不构成 finding。

## 5. Findings

### S23-I6-DSV4P-R3-01 [L] — backfill admission 的 hostile 验证矩阵未与 new-enqueue admission 同等闭合

- **状态**：open
- **位置**：target §13.4 3122-3125（`test_0006_proven_backfill_persists_original_available_and_request_payload_schema_identity` 参数矩阵）；对照 target §8.6 2231-2235 与 §13.4 3127-3128（new-enqueue 矩阵）；fix doc §5 229-232
- **问题类型**：验证缺口
- **证据（计划）**：§8.6 规范 admission 明确要求拒绝“domain closed sensitive key”；§13.4 new-enqueue 测试矩阵显式列“invalid UTF-8、sensitive/unsupported/float、duplicate/BOM/trailing、noncanonical/self-consistent bytes、bytes/SHA drift”九类，而 backfill 同一 named test 的强制参数矩阵只列“invalid UTF-8/closed primitive、raw bytes/SHA drift、SHA自洽但noncanonical JSON、duplicate key/BOM/trailing bytes、canonical re-encode drift”——sensitive-key case 缺失，形成两类 admission 的验证不对称。§8.6 step 3 只要求 fingerprint reproducer 与 domain 真源的 pure 等值测试（schema equal/mismatch、微秒/UTC 变体），migration-local canonical admission “与 domain `parse_canonical_document` 等值”没有任何 pure 测试 pin；若 migration-local 副本在搬移时漏掉 sensitive-key 检查（复制漂移），没有任何 lane 会失败。
- **证据（代码）**：`jobs.py:41` `_SENSITIVE_KEY_SET` 非空（password/secret/token/authorization/cookie/api_key），`jobs.py:517` validator 拒绝命中键——sensitive key 在 JSON 文本形态真实可达，是 runtime 真源的实质拒绝类，不是 unreachable 分支；0005 migration 已证明 migration 可 import 项目模块（`0005_source_connectors_health.py:30`），因此“migration-local 等值”是计划选择的复制语义而非恒真式，需要验证闭合。
- **影响**：backfill admission 的唯一 instrumented 验证（dedicated 0006 PG owner）无法证明 §8.6 要求的 sensitive-key 拒绝与 domain 等值；写入者若不自行补充参数 case，该拒绝类处于“有规范、无验证”状态。
- **建议修法与验证点**：在该 named test 的参数矩阵中显式加入 sensitive-key case（不新增 catalog test 名，符合“不得增加catalog test名”的既有约束；fix doc §5 同步），并在 `test_0006_migration_fingerprint_reproducer_matches_domain_and_excludes_idempotency_key` 所在 pure test 内追加 migration-local canonical admission 与 domain `parse_canonical_document` 的逐值等值断言（或改由 migration 直接 import domain 真源并明示理由，消除复制漂移面）。
- **严重程度**：低

## 6. 逐 finding closure 核对（prior rounds）

- formal review 2H/3M（`S23-I6-PLAN-01..05`）：01→0006 三列 immutable identity + proof-only backfill + empty-only downgrade + Source provenance 改读 original + prerequisite 12 tests；02→持久化 request payload schema name/version，保留 generic mismatch，fingerprint 算法不删字段不加 key；03→definition-scoped exact lookup 边界，relocation 不可观察等价 missing；04→`validate_cron_expression` validation-only seam + hit/miss pre-read ordering；05→strict reconstruction 先于 compare 的分流。五项均在本 candidate 文本闭合。
- Round 2 internal redteam 1H/1M：prerequisite 未授权 CI/README owner→exact12 + workflow zero-diff/Item 8 延后；fingerprint 前未证 canonical bytes→§3.4 admission + negative PG cases。闭合。
- Round 3 internal redteam 2H/2M：workflow stage ownership→Item 8；new-enqueue pre-session canonical admission→§3.4/§13.4/§15；prerequisite retry test 越界→renamed durable-columns test；README owner→两份 README 入 scope、根 README zero diff。闭合。
- 上述 closure 均为对当前冻结字节的核验；任何历史 PASS 不授权当前 candidate。

## 7. Residuals / 观察（非 finding）

- §16 全部 10 项既有 residual 继续成立（provider 非 exactly-once、双事务窗口、Redis hint、PONR thread 无 wall-clock 上界、无 typed code 的 Job/Schedule repository failure、0006 对不可证明 legacy row fail closed 等），本轮未发现新增 unclassified residual。
- §14 中 postgres_jobs 79.874706%→80 的归因句指向 Item 6 main lookup test，而 prerequisite gate 已对 changed owner 要求 instrumented >=80；经分析非确定性矛盾（prerequisite 自身新增 covered branch 可能独立越线，且 fail closed 有 STOP 治理出口），列为观察。
- §13.4 三个 Item 6 service/schedule 新测试的归属文件（test_schedule_service.py / test_investment_sources.py / test_postgres_schedules.py）均在各 owner 的 §11.1 tuple 内，且属于 Item 6 main 20-path 既有文件集合（§11 writable allowlist 含全部三者），无越界。

## 8. Final conclusion

**FAIL / open H/M/L = 0/0/1**

十一项重点检查中十项闭合、一项以 Low finding 打开。核心架构、schema、锁序、admission、账本与 sequencing 均 code-generation-ready；唯一缺口是 backfill admission 的 hostile 验证矩阵未与 new-enqueue admission 同等闭合（缺 sensitive-key case 与 migration-local/domain 等值 pin），不阻塞 writer 构造（规范文本明确、参数 case 可合法补充），但按“任何 finding 必须逐项闭合”的门禁标准，本 candidate 尚不能 PASS。

## 9. Post-write freeze protocol

- 写入后重新核验 HEAD 仍为 `4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723`、branch 仍为 `codex/investment-platform`、index 仍 empty、worktree 相对本 artifact 无新变化；
- reviewed 四份 doc 的 SHA-256/行数与 §1 冻结值逐项一致；
- artifact 最终 SHA-256 与行数由写后只读命令计算，见本轮 Controller handoff。
