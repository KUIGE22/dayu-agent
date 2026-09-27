# Code Review — S31-A final disk

## Findings

Fresh open H/M/L：**0/2/1，FAIL**。本报告审查的是下方冻结的未提交 S31-A 最终磁盘；此前三项 PG/ORM finding 在当前实现中已修复，以下为新发现。

### 1-未修复-中-持久 reviewer witness 无法重建领域投影

- **入口/函数**：未来 `get_claim` / `record_claim_review` / `resolve_conflict_with_review` 对历史 `ClaimVersion` 与 `ClaimConflict` 的读回；`ReviewWitness.__init__`。
- **文件(行号)**：`dayu/investment/domain/evidence.py:1648-1682`；`dayu/investment/storage/models_evidence.py:162-169,252-259`；`dayu/investment/storage/_evidence_review_auth.py:176-183,430-440`。
- **输入场景**：审查在有效 grant 下提交后，`user_roles` 或 `role_permissions` 行被撤销删除，再读取仍不可变的审查版本或已解决冲突。
- **实际分支**：认证 helper 返回 `user_role_id, role_id, role_permission_id, permission_id`；六表持久化 `user_role_id, role_permission_id, permission_id`，**没有** `role_id`；领域 `ReviewWitness` 却必填 `role_id`，且没有两个持久 grant ID 字段。
- **预期行为**：不依赖当前可撤销 grant 行，仍能从历史行精确重建不可变 reviewer witness；V9 §3.2/§4 明确 grant IDs 不做 FK，以容许撤销。
- **实际行为**：历史行本身无法提供 `ReviewWitness.role_id`。若读回时查询 `user_roles`/`role_permissions` 补齐，撤销后查询无行；若拿 `user_role_id` 冒充 `role_id`，投影身份错误。当前 S31-A 无 repository，因此现有测试未触发该路径。
- **直接证据**：上述三个字段集合与 0001 app 对 `user_roles`/`role_permissions` 的 `DELETE` 授权（`0001_platform_foundation.py:562`）。同一问题作用于 `ClaimVersion.reviewer` 与 `ClaimConflict.reviewer`。
- **影响**：S31-B 实现稳定历史 readback 时会失败或伪造 grant 身份；认证撤销后不能可靠展示此前审查记录。
- **建议改法和验证点**：最小方案是将领域 `ReviewWitness` 改为持久的 `user_role_id`、`role_permission_id`、`permission_id`，移除无持久来源的必填 `role_id`；认证 helper 仍可返回 `role_id` 用于当次内部核验，但投影只复制持久字段。同步改 `tests/investment/test_evidence_domain.py` 中 witness 构造/断言，并在 S31-B 加真实 PG 的审查提交→删除 grant→历史版本/冲突读回用例。若必须对外保留 `role_id`，需将它作为新不可变列同步加到 ORM/0007 与 PG 测试，不能从可撤销表补查。
- **修复风险（低/中/高）**：中。
- **严重程度（低/中/高/严重）**：中。

### 2-未修复-中-0007 downgrade NOWAIT 锁冲突缺真实 PG 验收

- **入口/函数**：`0007_strict_evidence._preflight_downgrade`。
- **文件(行号)**：`dayu/investment/storage/migrations/versions/0007_strict_evidence.py:550-572`；`tests/integration/investment/test_postgres_evidence.py:70-179,241-530`；`tests/integration/investment/test_platform_migrations_postgres.py:6834-6923`。
- **输入场景**：第二 PG 连接持有六表之一或 `securities` 的冲突锁/未提交写入，第一连接尝试 `downgrade -1`。
- **实际分支**：生产代码逐表执行 `LOCK TABLE ... ACCESS EXCLUSIVE MODE NOWAIT`，但 S31-A 的两个新 PG 用例只覆盖空库往返、外部 ACL/view 与业务行；新增 catalog 用例只查询静态元数据。现有双连接 NOWAIT 用例位于 0005 的测试类，不运行 0007 的上述锁序。
- **预期行为**：按 V9 §4 的严格 downgrade admission 和 §7 的真实 PG preflight/rollback 验收，冲突须立即拒绝，六表、证券约束及 Alembic revision 原样保留，释放锁后空库回退成功。
- **实际行为**：现有通过结果没有执行该 0007 竞争路径，故不能证明拒绝时点、原子性及恢复；这是一项缺失的必需 PG 证据，并不声称当前 SQL 已被证明错误。
- **直接证据**：0007 的 NOWAIT 行为在迁移第 568–569 行；新 PG 文件仅两个 `test_0007_*` 函数，均无第二连接持锁；通用 PG 文件新增的 0007 用例在第 6834–6923 行只做 catalog 断言。
- **影响**：迁移回退安全门在并发条件下未获 S31-A 验收；不能以 2+57 PG 通过替代该指定场景。
- **建议改法和验证点**：在 `test_postgres_evidence.py` 用两连接 barrier 分别覆盖六表与 `securities` 至少各一个代表锁冲突，断言 PG SQLSTATE `55P03`、downgrade 不等待、revision/对象无变化；释放锁后 `downgrade -1→upgrade head` 成功。测试必须运行 0007，而非复用 0005 断言。
- **修复风险（低/中/高）**：低。
- **严重程度（低/中/高/严重）**：中。

### 3-未修复-低-FactPitTimes 接受数据库拒绝的单侧期间

- **入口/函数**：`FactPitTimes.__post_init__` → `FactCreateRequest` → 未来 `create_fact` INSERT。
- **文件(行号)**：`dayu/investment/domain/evidence.py:900-936,995-1025`；`dayu/investment/storage/models_evidence.py:103`；`dayu/investment/storage/migrations/versions/0007_strict_evidence.py:105`。
- **输入场景**：`FactPitTimes(period_start=date(2026,1,1), period_end=None, ...)`，或反向单侧非空。
- **实际分支**：DTO 只在两值均非空时比较顺序，因此两种单侧输入均构造成功；本人以只读 Python 构造复现。ORM/0007 的 `ck_facts_period_shape` 要求两值均空或均非空，INSERT 会报 `23514`。
- **预期行为**：结构无效的 Fact period 在领域入口即拒绝，与物理 DB 合同一致。
- **实际行为**：合法形态的 DTO 可承载无法落库的请求，未来 repository 会把稳定输入错误推迟到数据库失败。
- **直接证据**：DTO 第 925–930 行缺“恰好同时为空”判定；0007 第 105 行明确双空/双非空 CHECK。`tests/investment/test_evidence_domain.py:336-347` 只覆盖完整区间与倒置区间。
- **影响**：单侧日期请求无法作为 Fact 持久化，错误边界和异常分类不稳定；DB 保持 fail closed，无数据污染证据。
- **建议改法和验证点**：DTO 增 `(period_start is None) == (period_end is None)` 校验；补两种单侧负例，保持完整区间/双空/倒置正负例。
- **修复风险（低/中/高）**：低。
- **严重程度（低/中/高/严重）**：低。

## Scope and frozen identity

- Mode：S31-A 指定未提交 diff 的非作者独立复审；base 是 `b6444ae16aa524a717e396160bacc855faa2049f`，branch `codex/investment-platform`，不是相对 `main` 的整分支 review。
- Plan：已接受 V9 `docs/plans/2026-09-27-slice-3.1-strict-evidence.md` SHA-256 `d3b658297a75c21a74b821f63166b3ccbf41762f56cf0d21123ff7ad686b59e2`；同时阅读 `AGENTS.md`、S31-A security ORM 增补、此前修复裁定与 author handoff。未修改冻结计划。
- 13 个 S31-A 交付路径（含 author handoff）及修复裁定在写此报告前复开，SHA-256 如下；另有本 review 文件。全部目标文件只读，未 stage/commit。

| 文件 | SHA-256 |
| --- | --- |
| `dayu/investment/domain/evidence.py` | `f80cf5b51411ac66cd130a16f897259a69717dc735da33e0e4439d917f5d058b` |
| `dayu/investment/storage/models_evidence.py` | `3462acfccb745b8f04f3112ae71f51a190327c8eb7f730c2adbfb467958b0791` |
| `dayu/investment/storage/migrations/versions/0007_strict_evidence.py` | `640e4101c61004ee115b7f7ed66303168fe11fb78c704fc37f14994277f8bd52` |
| `dayu/investment/storage/models_identity.py` | `5d266741efec51b7b83178de4228b86a0dc87785a16b3a9bb3a2fc283f090a78` |
| `dayu/investment/storage/__init__.py` | `44f0a2aab9736c2d93f04755d5da356a88baaad61c9b8e7c9d9e1746ca95591c` |
| `dayu/investment/README.md` | `1547146aedec38209bd2df037f39a90500d092ddc191b1085dcf611c4154206f` |
| `tests/README.md` | `0ce26a0011e2a317638b0e27b641a848906a4b189ff8b5bba26a9076604390f4` |
| `tests/investment/test_evidence_domain.py` | `1a910baea29f7c7aaad01c92ee1b1d91c19554337ca0ad9ac0332b7f5c32c120` |
| `tests/investment/test_evidence_storage_contract.py` | `eebcef575ad3c8d31e606c84803fd2d0428dc8a8f3be65567b161a64fd911eae` |
| `tests/investment/test_platform_migrations.py` | `8cfab568a6b57d9d3a49c5bf458bc563edf5d4365f9d11f977e7e1b62272a51c` |
| `tests/integration/investment/test_postgres_evidence.py` | `4046eb512d30029d10bff4ed383fd9d03b7ba04ab0ba8750b16229cfdb820cea` |
| `tests/integration/investment/test_platform_migrations_postgres.py` | `aca0cbb5b6a55572f1f5387549f405514785842aa3858f82e5b2e3f11344e70b` |
| `docs/reviews/implementation-20260927-s31-a-domain-handoff.md` | `baab9c21bfe2da3c2987106f8418a103c2236ded4e901251737fdf5925281436` |
| `docs/reviews/implementation-adjudication-20260927-s31-a-interrupted-review.md`（裁定，非 S31-A 源码） | `807a15ed9c43cb4f1b8202f92cb67e60e722eaf37017be2db058b618d318e5a6` |

## Verification and positive evidence

- 本人实际运行 `.venv/bin/python -m pytest tests/investment/test_evidence_domain.py tests/investment/test_evidence_storage_contract.py -q`：41 passed；`.venv/bin/python -m pytest tests/integration/investment/test_postgres_evidence.py -q -m integration --timeout=120`：PG16 2 passed；`.venv/bin/pyright --pythonpath .venv/bin/python` 加六个本片新 Python 路径：0 errors/0 warnings；`.venv/bin/ruff check` 加同六路径：pass；fallback Git 的 `git diff --check`：pass。默认 `/usr/bin/git` 受 Xcode license 阻断，Git 身份/diff 改由 `/Users/wsk/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/git` 只读取得。
- 独立编译 `CreateTable` 六张表与 0007 固定 DDL，6/6 字节一致；按 index 名配对编译 `CreateIndex`，5/5 字节一致。首次按两个列表顺序 `zip` 比较 index 得 0/5，因为 `_NEW_INDEXES` 是名称排序而 `_INDEX_DDL` 是创建顺序；按名称重比后 5/5，此前结果不是缺陷。
- ACL 修复：`_preflight_downgrade` 以 `aclexplode(coalesce(relacl,acldefault))`、列 `attacl`、四函数 `proacl` 联合查询，明确拦 `PUBLIC`/外部 grantee/grantor；PG16 用例真实 GRANT 表、列、函数给 PUBLIC 并检查拒绝/撤销后回退。first_version 修复：ORM/0007 共同要求 V1 `claim_create+replace_all+draft`、V2+ 禁 `claim_create`；PG raw 反例命名 CHECK 通过。locator 空白修复：U& 列表与 Python 3.11 `str.isspace()` 29 个 code point 精确相等，五个字段的 tab/NBSP/EM SPACE 负例由 Fins parser 与 PG 函数/INSERT 覆盖。
- 真 PG 新用例还以 app role 参数化 raw SQL 验证 Fact/direct link NULL arm、ticker 三元 FK、NUMERIC 未舍入 38/12 与拒绝、双 MIC 同 ticker/locator、五类 locator 与 8KB 难压缩 section locator 回读、digest 覆盖 caller 值及 append guard。上述通过只证明已执行的 S31-A schema 路径。

## Open Questions

- 无。三个 finding 均有当前代码/测试直接证据；S31-B 的 repository 行为尚未实现，不在此报告内推断通过。

## Residual Risk and boundary

- 本人没有重跑 root 报告的全体 256 unit+architecture、PG migration 57 或全仓 pyright；这些是 Controller 已报告的既有结果，本报告的独立执行结果见上。0007 NOWAIT 双连接、撤销 grant 后历史 witness、单侧 period 三项均未被当前通过的测试掩盖为已验收。
- V9 §7 的 repository 并发 CAS/copy snapshot/响应丢失/23505 碰撞分类属于 S31-B，现无该代码；Fins owner/readback/freshness 属 3.2；十种 shape 递归闭包独立 OPEN。`FAIL 0/2/1` 不构成 Gate acceptance、远端验证或交易授权。
