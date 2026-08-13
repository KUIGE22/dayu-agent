# Slice 2.3 Item 6 Job Request Identity Round 4 独立 Plan Re-Review（DeepSeek V4 Pro）

- 日期：2026-08-14（Asia/Shanghai）
- 角色：Gateflow review worker（非 controller，不启动 /gateflow，不进入 implementation/commit）
- Actual route：DeepSeek 官方 Anthropic endpoint（Controller 已核验路由）
- Model：`deepseek-v4-pro[1m]`
- 分支：`codex/investment-platform`；HEAD：`4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723`；index：empty
- 评审对象：Controller 接受 Round 3 唯一 Low `S23-I6-DSV4P-R3-01` 后由 docs-only fix 产出的 fresh new-SHA candidate
- 外部边界：未读/未采信任何 MiMo 或 internal verdict 内容；仅核旧 reviewer artifact identity/rejected bookkeeping。未运行 test/PG/Docker/provider/network/model；未 stage/commit/push/PR；唯一写入为本 artifact。

## 1. 冻结核验（pre-freeze）

| Artifact | 本轮直接计算 SHA-256 | fix doc 声明写后 SHA-256 | 行数 | 相对 R3 冻结 |
|---|---|---|---|---|
| target `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md` | `dc210d4a3a6c0c4b7f5521e6e372f5ec0cc7e236c9c09a52460ad6847d432fa0` | 一致 | 3564 | 预期漂移（accepted fix 写入，+28 行） |
| master `docs/plans/2026-08-10-investment-platform-restoration.md` | `83680025d05881ef535c124120e39aefd3c964615abab237aca0b54f30acef62` | 一致 | 4498 | 预期漂移（accepted fix 写入，+23 行） |
| fix `docs/reviews/plan-fix-20260814-slice-2.3-item6-job-request-identity-codex.md` | `9066d39e98525e4d4a068ae03fe54679fc5690e1da72490fcec0ad92e8a697e1` | —（writer 不自报） | 331 | 预期漂移 |
| formal source `docs/reviews/plan-review-20260813-234659.md` | `4d27271b57f7cbb1bfcd2065ecdf1bd08da0459782e6ab7a76ac3358019edbe0` | 一致 | 227 | 不变 |

branch/HEAD/index 均与 fix doc 声明基线（`4ed503f` / `codex/investment-platform` / 无 stage）一致，未发生漂移，允许继续。

## 2. 直接代码证据核验（HEAD `4ed503f`，与 R3 同 HEAD 但本轮独立重核）

| 事实 | 证据 |
|---|---|
| `_SENSITIVE_KEY_SET` 六 literal；validator 用 `key.lower() in _SENSITIVE_KEY_SET` **case-insensitive** 递归拒绝 | `jobs.py:41, 513-519` |
| `parse_canonical_document`：`object_pairs_hook=_reject_duplicate_keys`、`parse_constant=_reject_nonfinite`、closed primitive validator（拒 float/非 string key/敏感键）、`_encode_canonical` 重编码与输入 bytes 逐字节相等、全部归一 `JobInputError` | `jobs.py:560-606` |
| fingerprint 含七字段 descriptor + request payload schema name/version + payload SHA + available/deadline，不含 idempotency_key | `jobs.py:2066-2088` |
| `CanonicalJobDocument.__post_init__` 只验 SHA 格式不验 bytes↔SHA 相等（“SHA 自洽但 noncanonical bytes”真实可达） | `jobs.py:430-438` |
| `JobEnqueueRequest.__post_init__` 不比较 payload schema 与 descriptor schema → 合法 mismatch 持续存在 | `jobs.py:1043-1060` |
| `PostgresJobStore.enqueue` 先 `_session(scope)`（829）后算 fingerprint（894）；job_runs 单 INSERT 站点 | `postgres_jobs.py:829, 894, 923` |
| retry 只改 `job_runs.available_at = next_available_at` | `postgres_jobs.py:4060-4085` |
| 0003 单 `available_at` 列、CHECK `deadline_at > available_at`、app 列级 UPDATE grant 含 `available_at` | `0003_durable_jobs.py:189, 220, 681` |
| 0005 `revision=0005_source_connectors_health`、`down_revision=0004_durable_schedules` → 0006 linear 后继合法 | `0005_source_connectors_health.py:36-37` |
| Source provenance 现读 mutable `job_runs.available_at` | `postgres_sources.py:1591, 1660, 1663, 1668, 2062` |
| croniter 语义仅私有 `_validate_croniter_expression`（164），`register` 调用之（890）；无 public validation seam（planned new） | `dayu/services/schedule_service.py:164, 890` |
| misfire enum 仅 `COALESCE_ONE` | `schedules.py:74-77` |
| `get_by_idempotency_key` / `JobIdempotencyRecord` 全仓零命中 → prerequisite 边界可构造 | grep exit=1 |
| `tests/integration/investment/test_job_request_identity_migration_postgres.py` 不存在（dedicated owner 确为新文件） | ABSENT |
| CLI head test `test_platform_jobs_workspace_migration_documents_0005_as_current_head` 真实存在（rename 目标真实） | `tests/cli/workspace_migrations/test_platform_jobs.py:161` |
| `models_identity.py` 零 job_runs 引用 | grep 计数 0 |
| `ci-pr-extended.yml` 仅四条 PG lane（39-44）→ 前两级 workflow zero-diff 为真实差异 | `.github/workflows/ci-pr-extended.yml:39-44` |
| §11.1 矩阵 = 44 exact data rows（29 tracked + 15 planned） | 逐行计数 44 |

## 3. 重点检查结论（Round 4 修订面）

1. **R3-01 支点 A（backfill PG 参数矩阵）**：§13.4（3137-3145）既有 named test 保持单一 exact name，参数化新增 stored SHA 与 raw bytes 自洽的 exact lowercase `token` 代表键与 recursive mixed-case `{"a":{"ToKeN":"x"}}` 两个独立 sensitive parameters，各自提供 self-consistent raw/stored SHA，证明 case-insensitive recursive closed-set admission 在任一 identity DDL/write 前 fail closed；每个 negative case 断言无 partial DDL/identity write 且 0005 catalog 保持 exact；禁止动态生成/alias/新增 catalog test 名，prerequisite 仍 12 项、overall 仍 174 项。**闭合。**
2. **R3-01 支点 B（migration-local/domain 等值 pin）**：§8.6 step 3（2243-2260）同一既有 pure named test 现冻结 migration-local admission 与 public `parse_canonical_document` 的 closed valid/hostile corpus 逐值等价：`ACCEPT` 至少逐项含 `null`、`true`、`-1`、`"中"`、canonical array `[null,false,0,"中",{}]`、sorted nested object 及按 canonical key 顺序编码且分别含 `apikey`、`password_hint`、`token_count`、`x-authorization` 的 near-miss object，逐值 exact 比较 schema name/version、canonical bytes、SHA-256 与输入 raw-byte identity；`CANONICAL_INVALID` 把六个 lowercase sensitive literal 各自作为独立 case，另含 recursive mixed-case `ToKeN`、float/`NaN`、nested duplicate、BOM、trailing junk/whitespace、noncanonical key order、noncompact separators、escaped Unicode；禁止合并六 key 短路掩盖、禁止 JSON 文本不可构造的 non-string key；typed exception adapter（domain 侧只捕获 `JobInputError`，migration 侧只捕获 0006 exact private canonical-invalid exception），禁止 broad catch 与错误文案比较。**闭合。**
3. **R3-01 支点 C（复制漂移面消除）**：§8.6（2246）明示 migration 保留 frozen local implementation、不得 import domain helper；fix doc §5/§6 同步。**闭合。**
4. **corpus 与 domain 真源一致性（本轮新增代码核验）**：`jobs.py:517` 的 `key.lower()` case-insensitive 匹配证明 mixed-case `ToKeN` 归 `CANONICAL_INVALID` 与 domain 行为逐点等值，四个 near-miss 键（lowercase 后均不在六 literal 集合）归 `ACCEPT` 亦等值；`parse_canonical_document`（560-606）的 duplicate/nonfinite/closed primitive/sensitive/重编码逐字节相等路径与 corpus 全部 hostile 类别一一对应。**通过。**
5. **修订范围与回归扫描**：净增 +28 行集中于 §8.6 step 3、§13.4 参数矩阵与新增 §17.1 账本；§11.1 仍 44 keys；§13 四节命名项仍 52/42/53/27 = 174（§13.2 末两 `- ` 行为续行、§13.4 含 5 个非命名检查项，逐行核对无漂移）；exact12 路径不变；prerequisite 12 / Item 6 main 51（原48+3）不变；六 PG owner、九 lane/ignore、§12 linear sequencing、§15 STOP（3360-3361 含 new-enqueue admission 双向闭合、3356-3358 含 backfill/downgrade fail closed）均与 R3 冻结语义一致。**通过。**
6. **master 同步**：master 4141-4161（current identity decision 含 R3-01 修复摘要）、4202-4207（R3 finding bookkeeping）、4094（Slice status 行含 `DEEPSEEK V4 PRO ROUND 3 FAIL OPEN H/M/L=0/0/1 ACCEPTED+FIXED / … FRESH NEW-SHA … RE-REVIEW PENDING`）与 fix doc、target §17.1 一致。**通过。**
7. **机械账本与 README/CI 边界**：fix doc §5 账本（44/6/9/174/12/51/exact12/exact20）与 target §17.1、§13.4、§14 逐项一致；两份 README 职责不变、根 README 与两份 workflow zero diff 不变；0006 dedicated owner 不得与 0005 owner 共享 coverage 进程的约束仍在（§8.6:2290-2292）。**通过。**

## 4. Hostile cases 尝试与结果

- **mixed-case `ToKeN` 分类与 domain 漂移**：domain 为 `key.lower()` case-insensitive 拒绝（`jobs.py:517`），计划 corpus 归 `CANONICAL_INVALID`，等值成立。已核验。
- **near-miss 键误拒**：`apikey`/`password_hint`/`token_count`/`x-authorization` lowercase 后均不在 `_SENSITIVE_KEY_SET`，归 `ACCEPT` 与 domain 一致。已核验。
- **migration-local 副本漏 sensitive 检查（复制漂移）**：六个 sensitive literal 为独立 parameter case，任一被漏接即 classification 不等 → pure named test 失败。已覆盖。
- **六 key 合并进同一 object 导致短路**：§8.6 明令禁止。已覆盖。
- **invalid UTF-8 伪装 pure 等价**：§8.6 明示只属 PG byte-wrapper，禁止传给 public text parser。已覆盖。
- **bytes/SHA drift 在 pure 层不可构造**：由 migration wrapper 用 valid canonical raw + mismatched supplied SHA 归一 `CANONICAL_INVALID` 并证明 parser 零调用，同时保留 PG 覆盖。已覆盖。
- **参数扩充偷增 catalog 名**：§13.4 明令禁止动态生成/alias/新增名，named audit 仍 174。已覆盖。
- **修订面之外的既有 closure 被意外触碰**：formal 01-05 与 R2/R3 internal redteam closure 的字节依据（§3.4/§3.5/§5.2/§6.2/§9/§13.1/§13.3/§14/§15）本轮逐段核对未被修订触及；§8.6/§13.4 的修订只增强 PLAN-02 的验证要求。无缺口。

## 5. Findings

无。`S23-I6-DSV4P-R3-01` 三支点（PG sensitive-key 参数、pure 等值 pin、frozen local 无 import）均在本 candidate 文本闭合，且本轮以直接代码证据确认 corpus 分类与 domain 真源逐点等值；修订面未引入新缺口。

## 6. 逐 finding closure 核对（prior rounds）

- formal review 2H/3M（`S23-I6-PLAN-01..05`）：修订面未触及其 closure 依据字节，closure 在新 SHA 上继续成立。
- Round 2 internal redteam 1H/1M、Round 3 internal redteam 2H/2M：同上，closure 继续成立。
- DeepSeek V4 Pro Round 3 1L（`S23-I6-DSV4P-R3-01`）：本轮闭合（见 §3.1-3.4）。
- 上述 closure 均为对当前冻结字节的核验；任何历史 PASS 不授权当前 candidate，本轮 PASS 亦不授权 MiMo 链路或 implementation。

## 7. Residuals / 观察（非 finding）

- §16 全部 10 项既有 residual 继续成立（provider 非 exactly-once、双事务窗口、Redis hint、PONR thread 无 wall-clock 上界、无 typed code 的 Job/Schedule repository failure、0006 对不可证明 legacy row fail closed 等），本轮未发现新增 unclassified residual。
- §14 中 postgres_jobs 79.874706%→80 的归因句仍指向 Item 6 main lookup test 而 prerequisite gate 已对 changed owner 要求 instrumented >=80；经分析非确定性矛盾（prerequisite 自身新增 covered branch 可能独立越线，且 fail closed 有 STOP 治理出口），维持 R3 观察。
- MiMo 链路的 finding 闭合与 verdict 由 MiMo fresh review 自行负责；本 artifact 不采信也不否决其内容，Controller 门禁仍要求双路 `PASS / 0/0/0`。

## 8. Final conclusion

**PASS / open H/M/L = 0/0/0**

Round 3 唯一 Low finding 已按三支点完整闭合，且新 hostile corpus 与 domain 真源的一致性经直接代码证据逐点核验成立；账本、sequencing、STOP、README/CI 边界与既有 closure 均无回归。本 candidate 计划文本达到 code-generation-ready。按门禁规则，仍需 MiMo 独立 fresh review 同得 `PASS / 0/0/0` 且 Controller acceptance / local plan commit 后，才可 dispatch exact-twelve-path 0006 prerequisite writer。

## 9. Post-write freeze protocol

- 写入后重新核验 HEAD 仍为 `4ed503fea35dbcfe1ecb7bd0c44b7dfccf7df723`、branch 仍为 `codex/investment-platform`、index 仍 empty、worktree 相对本 artifact 无新变化；
- reviewed 四份 doc 的 SHA-256/行数与 §1 冻结值逐项一致；
- artifact 最终 SHA-256 与行数由写后只读命令计算，见本轮 Controller handoff。
