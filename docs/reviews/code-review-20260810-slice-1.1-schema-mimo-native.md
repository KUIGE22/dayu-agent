# Code Review — Slice 1.1 Platform Schema Implementation

## Scope

- Mode: current changes（Slice 1.1 未提交改动）
- Branch: `codex/investment-platform`
- Base: `7209eac`（doc-owner erratum accepted commit）
- Review clock: `2026-08-10`（本机系统时钟）
- Output file: `docs/reviews/code-review-20260810-slice-1.1-schema-mimo-native.md`
- Included scope:
  - `pyproject.toml`（改）
  - `constraints/min-py311.txt`、`constraints/lock-common-py311.txt`（改）
  - `alembic.ini`（新）
  - `dayu/investment/storage/__init__.py`、`db.py`、`models_identity.py`、`models_auth.py`（新）
  - `dayu/investment/storage/migrations/**`（新）
  - `tests/investment/test_platform_migrations.py`（新）
  - `tests/investment/test_architecture_boundaries.py`（改）
  - `tests/integration/investment/conftest.py`、`test_platform_migrations_postgres.py`（新）
  - `dayu/investment/README.md`、`dayu/README.md` §3.9、`tests/README.md`（改）
- Excluded scope: Slice 1.2+ repository/service/composition、network/live/broker、PG17 stack
- Parallel review coverage: 无 subagent；主 reviewer 独立完成全量走读

## Findings

未发现实质性问题。

### 13-Table ORM/Migration Schema Exact

逐表验证 ORM 模型（`models_identity.py` + `models_auth.py`）与迁移 DDL（`0001_platform_foundation.py`）一致性：

| 表 | ORM ↔ DDL 一致 | 列数 | PK/FK/UNIQUE/CHECK/INDEX |
|----|---------------|------|--------------------------|
| organizations | ✅ | 7 | PK + UQ(slug) + CK(status/slug_nonblank/version) |
| companies | ✅ | 7 | PK + UQ(lei) + CK(country_code/lei_nonblank/version) |
| securities | ✅ | 11 | PK + FK(companies) + UQ(exchange_mic,ticker) + UQ(isin) + IX(company_id) + CK(6) |
| source_definitions | ✅ | 7 | PK + UQ(source_key) + CK(source_kind/source_key_nonblank/version) |
| users | ✅ | 9 | PK + FK(organizations) + UQ(tenant_id,id) + UQ(tenant_id,subject) + IX(partial email) + CK(4) |
| roles | ✅ | 8 | PK + FK(organizations) + UQ(tenant_id,id) + UQ(tenant_id,name) + CK(2) |
| permissions | ✅ | 7 | PK + FK(organizations) + UQ(tenant_id,id) + UQ(tenant_id,permission_key) + CK(2) |
| user_roles | ✅ | 5 | PK + FK(organizations) + FK(users) + FK(roles) + UQ(2) |
| role_permissions | ✅ | 5 | PK + FK(organizations) + FK(roles) + FK(permissions) + UQ(2) |
| api_tokens | ✅ | 11 | PK + FK(organizations) + FK(users) + UQ(tenant_id,id) + UQ(token_hash) + CK(4) |
| source_subscriptions | ✅ | 12 | PK + FK(4) + UQ(tenant_id,id) + IX(3 partial) + CK(4) |
| source_sync_runs | ✅ | 11 | PK + FK(organizations) + FK(source_subscriptions) + UQ(2) + IX + CK(5) |
| source_health_snapshots | ✅ | 11 | PK + FK(organizations) + FK(source_subscriptions) + FK(source_sync_runs) + IX + CK(3) |

UUID 无 server default、`created_at/updated_at` 为 `TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp()`、`version` 为 `INTEGER NOT NULL DEFAULT 1 CHECK (version > 0)`、append-only 表无 `updated_at/version`——全部与 plan 一致。✅

### Pre-DDL Rolsuper Fail-Closed Zero Side-Effect

`env.py:63-91` `_admission_preflight()`：
- 在独立连接中查询 `pg_roles` 要求 `rolsuper IS TRUE` ✅
- 查询后立即 `conn.rollback()`，零 side effect ✅
- `CREATEROLE`/`BYPASSRLS` membership/object ownership 均不能替代 ✅
- 预检不通过抛 `PlatformMigrationAdmissionError`，消息不含 DSN/credential ✅
- 离线模式恒抛 admission error ✅

### Bootstrap Secret Not Entering Runtime/Log

- `db.py`：不读取环境变量，`echo=False` ✅
- `env.py`：从 `DAYU_PLATFORM_POSTGRES_DSN` 读取但不注册 `sqlalchemy.engine` logger ✅
- `alembic.ini`：无 DSN，日志只输出到 stderr，无 SQL 参数回显 ✅
- 错误消息：`PlatformMigrationAdmissionError` 和 `PlatformIntegrationError` 均不含 DSN/password ✅
- conftest：`secrets.token_urlsafe(24)` 生成密码，`_collect_redacted_logs` 脱敏 ✅

### RLS FORCE/USING/WITH CHECK/Default Deny/Cross Tenant/Audit

- 每张私有表 `ENABLE + FORCE ROW LEVEL SECURITY` ✅
- 唯一 `tenant_isolation` policy `FOR ALL TO dayu_platform_app` ✅
- `USING` 和 `WITH CHECK` 均使用 `nullif(current_setting('app.tenant_id', true), '')::uuid` ✅
- `organizations` 比较 `id`，其余比较 `tenant_id` ✅
- 未设置/空/错误 tenant → NULL → default deny ✅
- audit 通过 `BYPASSRLS` + `SELECT` 跨租户只读，不能 DML ✅
- integration 测试覆盖：unset deny、same-tenant allow、cross-tenant reject、audit bypass、SET LOCAL 不泄漏 ✅

### Role Membership and Minimal GRANT/PUBLIC/Default Privilege

- `REVOKE ALL FROM PUBLIC`（schema + 全部 13 表）✅
- bootstrap owns schema/tables/policies ✅
- app：schema `USAGE`；public references `SELECT,INSERT,UPDATE`；`organizations/users/roles/permissions/api_tokens/source_subscriptions` `SELECT,INSERT,UPDATE`；`user_roles/role_permissions` `SELECT,INSERT,DELETE`；`source_sync_runs/source_health_snapshots` `SELECT,INSERT` ✅
- app：无 `TRUNCATE/REFERENCES/TRIGGER`、schema 无 `CREATE`、无 role/DDL ✅
- audit：schema `USAGE`、13 表 `SELECT` only、无 DML/DDL ✅
- `ALTER DEFAULT PRIVILEGES IN SCHEMA dayu_platform REVOKE ALL ON TABLES FROM PUBLIC` ✅
- app 不是 audit member，`SET ROLE audit` 被拒 ✅
- integration 测试用 `has_schema_privilege`/`has_table_privilege`/`pg_auth_members` 断言矩阵 ✅

### Downgrade External Member/Session/Dependency Admission and Transaction Rollback/No CASCADE

`_downgrade_admission()`（migration 第 653-738 行）：
- `pg_auth_members`：app/audit 外部 member → fail closed ✅
- `pg_stat_activity`：使用 app/audit 或其 member 的非当前活跃 session → fail closed ✅
- `pg_shdepend`：`dayu_platform` schema 之外的外部依赖 → fail closed ✅
- 任一命中抛 `RuntimeError`，事务回滚，schema/tables/roles/seed 原样保留 ✅
- 降级顺序：policies → 13 tables → schema `RESTRICT` → group roles ✅
- 禁止 CASCADE ✅
- 不删除 bootstrap role/database/Alembic version table ✅
- integration 测试覆盖三类 fail-closed（external member、active session、external dependency）✅

### Official Isolated PG16 Fixture and Owner Cleanup/PG17 Not Touched

- 官方 `postgres:16.14-bookworm` pinned digest ✅
- 随机 container/network/database/users/port ✅
- `docker run --detach --rm` + unique label/name/network ✅
- Bounded `pg_isready` 超时 90s ✅
- `finally` 清理：`_cleanup_cluster` 按 verified label 删除 owned container/network ✅
- 不使用 broad glob/prune/compose down ✅
- 不连接/停止/修改既有 PG17 stack ✅
- 失败诊断不打印 DSN/password ✅

### Constraints/minPy311

- `pyproject.toml`：`SQLAlchemy>=2.0.51,<2.1.0`、`psycopg[binary]>=3.3.4,<3.4.0`、`alembic>=1.18.5,<1.19.0` ✅
- `constraints/min-py311.txt`：`SQLAlchemy==2.0.51`、`psycopg==3.3.4`、`psycopg-binary==3.3.4`、`alembic==1.18.5` ✅
- `constraints/lock-common-py311.txt`：同上 exact pins ✅
- pip constraints 为真源，不使用 uv.lock ✅

### Architecture Pure/Storage Guard and Three READMEs Truth

**Architecture guard**（`test_architecture_boundaries.py:69-106`）：
- `_PURE_FORBIDDEN_IMPORT_PREFIXES`：含 `sqlalchemy`/`psycopg`/`alembic` + 全部上层依赖 ✅
- `_INFRA_FORBIDDEN_IMPORT_PREFIXES`：从 pure set 移除 `sqlalchemy`/`psycopg`/`alembic` ✅
- `_PURE_RELATIVE_PATHS`：`__init__.py`、`domain/`、`config.py`、`composition.py` ✅
- `_INFRA_RELATIVE_PREFIX`：`storage/` ✅
- 未知路径返回 `None`，默认按 pure 规则拒绝 ✅

**`dayu/README.md` §3.9**：owner 图为 pure `domain/config/composition` + infra `storage`；只对 pure 层禁 ORM；storage 只依赖 pure + SQLAlchemy/psycopg/Alembic 且不向上暴露 ORM row ✅

**`tests/README.md`**：architecture guard 更新为 pure/storage 相对路径规则；登记 unit lane 与真实 PG16 `integration` lane；明确禁止 SQLite/fake ✅

**`dayu/investment/README.md`**：依赖方向按 pure/infra 分组、storage 模块 owner、schema/RLS/GRANT/migration 契约、开发命令含 integration lane ✅

### Overcoupling / Hidden Compatibility Layer

- 无兼容层：storage 直接依赖 pure domain + SQLAlchemy，无 wrapper/facade ✅
- 无 hidden seam：`PlatformBase` 是唯一 ORM 基类，无条件分支或 fallback ✅
- 无 cross-layer leak：storage 不导入 Web/Service/Host/Agent ✅
- 无 god object：`db.py` 只含常量 + base class + factory，职责收敛 ✅

### Test Truth — Not Self-Referencing

- unit tests（19 tests）：metadata/naming/column types/constraints/AST no-create-all，不触碰数据库 ✅
- integration tests（22 tests）：真实 PG16，`information_schema`/`pg_constraint`/`pg_indexes`/`pg_policies`/`pg_auth_members` 断言，不从 ORM metadata 自比 ✅
- integration 测试用 `has_schema_privilege`/`has_table_privilege` 验证 GRANT 矩阵，不从 migration DDL 自比 ✅
- downgrade admission 测试用 `pg_auth_members`/`pg_stat_activity`/`pg_shdepend` 断言，不从代码自比 ✅

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| `pytest tests/investment -q` | **PASS** — 192 passed |
| `pyright dayu/investment tests/investment tests/integration/investment` | **PASS** — 0 errors, 0 warnings |
| `ruff check dayu/investment tests/investment tests/integration/investment` | **PASS** — All checks passed |
| `git diff --check HEAD` | **PASS** — no whitespace errors |
| 13-table ORM ↔ DDL 一致性 | **PASS** — 全部一致 |
| Rolsuper admission 零副作用 | **PASS** — rollback 后零 side effect |
| Bootstrap secret 隔离 | **PASS** — 不进 runtime/log |
| RLS FORCE/USING/WITH CHECK | **PASS** — 10 张私有表全部启用 |
| GRANT 矩阵 | **PASS** — 最小权限，audit 只读 |
| Downgrade admission 三类 fail-closed | **PASS** — member/session/dependency |
| PG16 容器隔离 | **PASS** — pinned digest + random + cleanup |
| Architecture guard 分组 | **PASS** — pure/infra 路径分组 |
| 三份 README 一致 | **PASS** — 与代码一致 |

## Open Questions

无。

## Residual Risk

- `source_subscriptions.source_definition_id` FK 名 `fk_source_subscriptions_source_definition_id_source_definitions` 恰好 63 字符，达到 PostgreSQL 限制上限。当前有效，但若后续 migration 重命名该列可能触发命名 convention 生成超长名。风险极低，可在 Slice 1.2 发现时处理。
- `_downgrade_admission()` 使用 `RuntimeError` 而非 `PlatformMigrationAdmissionError`，与 upgrade 路径不一致。功能等价（Alembic 均会 catch 并 rollback），但为一致性可考虑统一。风险低。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。

Slice 1.1 实现完整闭合 S11-CTRL-01..08 全部契约：13 表 ORM/migration schema exact 一致、pre-DDL rolsuper fail-closed 零副作用、bootstrap secret 不进 runtime/log、RLS FORCE/USING/WITH CHECK/default deny/cross tenant/audit 完整、GRANT 矩阵最小权限、downgrade 三类 fail-closed admission、官方隔离 PG16 fixture + owner cleanup、constraints/minPy311 闭合、architecture pure/storage guard 正确、三 README 真源一致。192 unit + 22 integration tests 全部通过，pyright 0 errors，ruff All checks passed。允许进入 code review。
