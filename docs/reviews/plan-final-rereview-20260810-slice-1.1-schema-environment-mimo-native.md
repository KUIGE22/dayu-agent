# Plan Final Re-review — Slice 1.1 ORM / Tenant / Auth / Alembic Erratum

## Scope

- Reviewed target：`docs/plans/2026-08-10-investment-platform-restoration.md` Slice 1.1 erratum（已修订版，§8 Phase 1 Slice 1.1 + S11-CTRL-01..07）与 `docs/reviews/plan-fix-20260810-slice-1.1-schema-environment-codex.md`
- Reviewer：MiM Native
- Review clock：`2026-08-10`（本机系统时钟）
- Output file：`docs/reviews/plan-final-rereview-20260810-slice-1.1-schema-environment-mimo-native.md`
- Focus：验证 Terra 001/002、MiM 001-004 与所有 S11-CTRL 闭合；反例挑战 schema/GRANT/RLS/downgrade/container cleanup/constraints

## Prior Findings Closure Verification

### Terra 001 (HIGH) — S11-CTRL-03 缺少列级 exact schema 契约 → CLOSED ✅

- **先前问题**：plan 只固定表清单，未定义列、键、约束、nullable、version 字段。
- **修订内容**：plan 第 421-445 行新增完整列级表，覆盖全部 12 张表的每个列、类型、约束、FK、unique、check、index。例如 `securities` 表定义了 `UNIQUE(exchange_mic,ticker)`、`index company_id`、`security_type CHECK equity/adr/etf/fund/bond/other` 等。
- **验证**：integration 必须通过 `information_schema`、`pg_constraint`、`pg_indexes` 精确断言列、类型、nullable、FK/unique/check/index，不能从 ORM metadata 自比生成期望。✅ 契约可验证。

### Terra 002 (MEDIUM) — S11-CTRL-04 缺少 application/audit 对象权限矩阵 → CLOSED ✅

- **先前问题**：只定义 role 属性，未定义 GRANT/REVOKE 矩阵。
- **修订内容**：plan 第 461-474 行新增完整对象权限矩阵：
  - `REVOKE ALL from PUBLIC`
  - bootstrap owns schema/tables/policies
  - app：schema `USAGE`；public references `SELECT,INSERT,UPDATE`；organizations/users/roles/permissions/api_tokens/source_subscriptions `SELECT,INSERT,UPDATE`；user_roles/role_permissions `SELECT,INSERT,DELETE`；source_sync_runs/source_health_snapshots `SELECT,INSERT`；全部表无 `TRUNCATE,REFERENCES,TRIGGER`；schema 无 `CREATE`；无 role/DDL
  - audit：schema `USAGE`；13 张表 `SELECT` only；无 DML/DDL
  - membership：app 不得成为 audit member，不得 `SET ROLE audit`；受审计 operator 才可获得 audit membership + `SET ROLE`，不得授予 ADMIN option
- **验证**：integration 以 `has_schema_privilege`、`has_table_privilege`、`pg_auth_members` exact matrix 断言。✅ 矩阵可验证。

### MiM 001 (MEDIUM) — Architecture AST guard 重构方案未指定 → CLOSED ✅

- **先前问题**：plan 说 "按 owner 分组" 但未给出具体分组策略。
- **修订内容**：plan 第 406-413 行明确指定：
  - "以 `_INVESTMENT_SRC` 的相对路径而非文件名匹配"
  - "pure 集合精确为根 `__init__.py`、`domain/**`、`config.py`、`composition.py`"
  - "infra 集合精确为 `storage/**`，只从 forbidden set 移除 `sqlalchemy`、`psycopg`、`alembic`"
  - "根 `__init__.py` 不得 re-export storage/ORM"
  - "tests/constraints/alembic.ini 不是 production package，不进入该 AST import guard"
- **验证**：implementation agent 可按此规格直接实现分组逻辑。✅ 可实施。

### MiM 002 (MEDIUM) — Integration test fixture 基础设施未指定 → CLOSED ✅

- **先前问题**：plan 未指定 conftest.py 的 container lifecycle/migration execution/session fixture。
- **修订内容**：plan 第 501-508 行明确指定：
  - "conftest.py 使用已有 Docker CLI（不新增 testcontainers 依赖、不在 pytest 内隐式 pull）"
  - "session fixture 要求本地已存在 pinned digest"
  - "`docker run --detach --rm` + unique label/name/network + loopback random published port"
  - "bounded `pg_isready` 后才产出 bootstrap DSN"
  - "fixture 提供 Alembic Config/bootstrap engine/application engine 与显式 temporary-login helper"
  - "只经 Alembic upgrade 建 schema，禁止 `create_all()`"
  - "成功/失败均在 `finally` 收集 bounded/redacted logs 后只按已验证 label/name 删除 owned container/network"
  - "不用 broad glob/prune/compose down"
  - "失败诊断不打印 DSN/password"
- **验证**：implementation agent 可按此规格直接实现 fixture。✅ 可实施。

### MiM 003 (LOW) — Lock file resolver 未指定 → CLOSED ✅

- **先前问题**：plan 未指定使用哪个 resolver。
- **修订内容**：plan 第 392-400 行明确指定：
  - "本仓库的安装真值是 pip constraints，不是已被 `.gitignore` 排除的 `uv.lock`"
  - "只在 `constraints/min-py311.txt` 与 `constraints/lock-common-py311.txt` 增加上述 direct exact pins"
  - "用 clean Python 3.11 venv 分别执行 CI 同形 `pip install`"
  - "不得用 `pip freeze`、手工猜 transitive version 或引入新的 lock 工具/`uv.lock` 真源"
- **验证**：implementation agent 可按此规格直接实现。✅ 可实施。

### MiM 004 (LOW) — Downgrade 策略对 default organization 的处理未明确 → CLOSED ✅

- **先前问题**：plan 未明确 downgrade 是否删除 organizations 表和 default org 数据。
- **修订内容**：plan 第 489-494 行明确指定：
  - "downgrade 精确删除本 slice owner"
  - "顺序为 policy/default privileges/grants -> 13 tables（含 default organization row）-> `dayu_platform` schema `RESTRICT` -> app/audit group roles"
  - "禁止 CASCADE"
  - "有外部 member/session/dependency 时整次 downgrade fail/rollback"
  - "bootstrap role、database、Alembic version table 与非本 slice object 保持"
- **验证**：downgrade 策略完整且明确。✅ 可实施。

## S11-CTRL Items — 逐项闭合验证

| 控制项 | 状态 | 闭合依据 |
|--------|------|----------|
| S11-CTRL-01 依赖/locks | ✅ CLOSED | 第 388-400 行：pip constraints 真源、exact pins、clean venv testing、禁止 uv.lock/pip freeze |
| S11-CTRL-02 Architecture guard | ✅ CLOSED | 第 401-413 行：路径分组、pure/infra 集合、re-export 禁令、非生产代码排除 |
| S11-CTRL-03 Exact schema | ✅ CLOSED | 第 414-445 行：12 张表完整列级定义、information_schema 断言 |
| S11-CTRL-04 RLS/roles | ✅ CLOSED | 第 446-480 行：role 属性、GRANT/REVOKE 矩阵、membership 约束、has_*_privilege 断言 |
| S11-CTRL-05 Migration/runtime | ✅ CLOSED | 第 481-494 行：transactional migration、downgrade 顺序、禁止 create_all、无 DSN 回显 |
| S11-CTRL-06 PG16 integration | ✅ CLOSED | 第 495-508 行：Docker CLI、random port/network、digest pinning、finally cleanup |
| S11-CTRL-07 Unit/integration split | ✅ CLOSED | 第 509-519 行：文件/marker 分离、integration 场景、禁止 SQLite/fake |

## Adversarial Challenge — Schema / GRANT / RLS / Downgrade / Container Cleanup / Constraints

### Schema 反例挑战

| 反例 | 预期 | plan 覆盖 | 结论 |
|------|------|-----------|------|
| `securities.ticker` 无 unique per exchange | 同一交易所重复 ticker | `UNIQUE(exchange_mic,ticker)` ✅ | 已覆盖 |
| `users.email` 无 tenant-scoped unique | 同一租户重复 email | partial unique lower-email per tenant when email non-null ✅ | 已覆盖 |
| `source_subscriptions` company/security 可同时非空 | 多目标冲突 | `num_nonnulls(company_id,security_id)<=1` + 3 条 partial unique index ✅ | 已覆盖 |
| `source_sync_runs` 无幂等键 | 重复同步 | `UNIQUE(tenant_id,idempotency_key)` ✅ | 已覆盖 |
| `api_tokens.token_hash` 无 CHECK | 非 hex hash | `CHECK lowercase hex` + `CHAR(64)` ✅ | 已覆盖 |
| `version` 列无下界 | 非正 version | `CHECK (version > 0)` ✅ | 已覆盖 |
| append-only 表有 `updated_at` | 语义矛盾 | `source_sync_runs`/`source_health_snapshots` 无 `updated_at/version` ✅ | 已覆盖 |
| `source_health_snapshots` 无 `finished_at` | 语义矛盾 | append-only row 无 `finished_at` ✅ | 已覆盖 |

### GRANT 反例挑战

| 反例 | 预期 | plan 覆盖 | 结论 |
|------|------|-----------|------|
| app 对 public references 无 INSERT | 无法创建 company | `SELECT,INSERT,UPDATE` on public references ✅ | 已覆盖 |
| app 对 user_roles 有 UPDATE | 可篡改角色 | 只有 `SELECT,INSERT,DELETE`，无 UPDATE ✅ | 已覆盖 |
| app 对 append-only 有 DELETE | 可删除同步记录 | 只有 `SELECT,INSERT`，无 DELETE ✅ | 已覆盖 |
| audit 有 INSERT on private tables | 可写入租户数据 | audit 只有 `SELECT`，无 DML ✅ | 已覆盖 |
| app 有 TRUNCATE | 可清空表 | `REVOKE TRUNCATE` ✅ | 已覆盖 |
| future migration 扩大 audit 权限 | 审计边界泄漏 | "每个 future migration 必须按 owner 显式授予最小权限，不得扩大 audit" ✅ | 已覆盖 |

### RLS 反例挑战

| 反例 | 预期 | plan 覆盖 | 结论 |
|------|------|-----------|------|
| 未设置 tenant 时 allow | 越权访问 | `nullif(..., '')::uuid` → NULL → default deny ✅ | 已覆盖 |
| 跨租户读取 | 数据泄露 | `USING` + `WITH CHECK` 均使用 tenant expression ✅ | 已覆盖 |
| table owner 绕过 RLS | 权限提升 | `FORCE ROW LEVEL SECURITY` ✅ | 已覆盖 |
| audit 无 BYPASSRLS | 无法审计跨租户 | audit 有 `BYPASSRLS` + `SELECT` ✅ | 已覆盖 |
| app 成为 audit member | 间接 bypass | "app 不得直接/间接成为 audit member" ✅ | 已覆盖 |
| SET LOCAL app.tenant_id 泄漏 | 跨事务污染 | "每个 application transaction 必须由测试显式 SET LOCAL，并在提交/rollback 后证明设置不泄漏" ✅ | 已覆盖 |

### Downgrade 反例挑战

| 反例 | 预期 | plan 覆盖 | 结论 |
|------|------|-----------|------|
| CASCADE 删除外部依赖 | 意外数据丢失 | "禁止 CASCADE" ✅ | 已覆盖 |
| 先删 schema 再删 table | 依赖错误 | "顺序为 policy -> grants -> tables -> schema -> roles" ✅ | 已覆盖 |
| 删除 Alembic version table | 无法追踪 migration | "Alembic version table 留在 bootstrap-owned 默认 schema" ✅ | 已覆盖 |
| 保留 bootstrap role | 可重建 | "bootstrap role、database、Alembic version table 保持" ✅ | 已覆盖 |
| default organization row 未删除 | 数据残留 | "13 tables（含 default organization row）" ✅ | 已覆盖 |

### Container Cleanup 反例挑战

| 反例 | 预期 | plan 覆盖 | 结论 |
|------|------|-----------|------|
| 固定端口并发冲突 | 测试失败 | "loopback random published port" ✅ | 已覆盖 |
| broad glob cleanup | 误删其他容器 | "只按已验证 label/name 删除 owned container/network" ✅ | 已覆盖 |
| compose down | 影响其他 stack | "不用 broad glob/prune/compose down" ✅ | 已覆盖 |
| 失败时泄漏 DSN | 安全风险 | "失败诊断不打印 DSN/password" ✅ | 已覆盖 |
| 测试进程崩溃 container 泄漏 | 资源泄漏 | "`docker run --detach --rm`" + finally cleanup ✅ | 已覆盖 |
| pg_isready 超时 | 连接失败 | "bounded pg_isready" ✅ | 已覆盖 |

### Constraints 反例挑战

| 反例 | 预期 | plan 覆盖 | 结论 |
|------|------|-----------|------|
| SQLAlchemy 2.1 beta 不兼容 | 安装失败 | `>=2.0.51,<2.1.0` ✅ | 已覆盖 |
| Python 3.10 不支持 | 运行失败 | "Python 3.11 minimum lane 固定" ✅ | 已覆盖 |
| pip freeze 生成不完整 lock | 缺失依赖 | "不得用 pip freeze" ✅ | 已覆盖 |
| 手工猜 transitive version | 版本冲突 | "不得手工猜 transitive version" ✅ | 已覆盖 |
| 引入 uv.lock 真源 | 与 pip constraints 冲突 | "不得引入新的 lock 工具/uv.lock 真源" ✅ | 已覆盖 |

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| Terra 001 (HIGH) 列级 schema | ✅ CLOSED — 12 张表完整列级定义 |
| Terra 002 (MEDIUM) GRANT 矩阵 | ✅ CLOSED — 完整对象权限矩阵 + has_*_privilege 断言 |
| MiM 001 (MEDIUM) guard 分组 | ✅ CLOSED — 路径分组 + pure/infra 集合 |
| MiM 002 (MEDIUM) fixture 基础设施 | ✅ CLOSED — Docker CLI + random port + finally cleanup |
| MiM 003 (LOW) lock resolver | ✅ CLOSED — pip constraints + 禁止 uv.lock |
| MiM 004 (LOW) downgrade default org | ✅ CLOSED — 13 tables 含 default org row |
| S11-CTRL-01 依赖/locks | ✅ CLOSED |
| S11-CTRL-02 Architecture guard | ✅ CLOSED |
| S11-CTRL-03 Exact schema | ✅ CLOSED |
| S11-CTRL-04 RLS/roles | ✅ CLOSED |
| S11-CTRL-05 Migration/runtime | ✅ CLOSED |
| S11-CTRL-06 PG16 integration | ✅ CLOSED |
| S11-CTRL-07 Unit/integration split | ✅ CLOSED |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- S11-CTRL-01 的实际 transitive resolution、S11-CTRL-06 的真实 digest 与 PG16 行为尚未实际执行；计划已正确要求在 erratum accepted 后用 resolver、min-compat/full-suite 与独立 integration lane 复证。这些应保留为 Slice 1.1 implementation gate，不以当前只读审查替代。
- S11-CTRL-04 的 GRANT 矩阵未覆盖 `information_schema`/`pg_catalog` 系统目录访问；但这些是 PostgreSQL 系统 catalog，不需要显式 GRANT，application role 默认有只读访问。✅ 可接受。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。

Terra 001/002 与 MiM 001-004 全部闭合。S11-CTRL-01..07 全部闭合。Schema 列级定义完整、GRANT 矩阵精确、RLS 双层隔离可验证、downgrade 顺序与依赖处理明确、container cleanup 策略安全、constraints 窗口闭合。全部 13 项闭合验证通过，6 轮反例挑战无新增问题。允许进入 accepted plan commit。
