# Code Corrective Re-review — Slice 1.1 Platform Schema

## Scope

- Mode: corrective re-review（只读，独立复证 Terra 001-004 修复）
- Branch: `codex/investment-platform`
- Base: `7209eac`（doc-owner erratum accepted commit）
- Review clock: `2026-08-10`（本机系统时钟）
- Output file: `docs/reviews/code-review-20260810-slice-1.1-schema-rereview-mimo-native.md`
- Source reviews: Terra `code-review-20260810-slice-1.1-schema-terra.md`（FAIL 0/2/2）、MiM `code-review-20260810-slice-1.1-schema-mimo-native.md`（PASS 0/0/0）
- Adjudication: `slice-1.1-platform-schema-code-review-adjudication-20260810-codex.md`（Terra 001-004 ACCEPTED）
- Fix artifact: `slice-1.1-platform-schema-review-fix-20260810-deepseek.md`
- Excluded scope: Slice 1.2+、live data/model/broker、PG17 stack

## TERRA-001 — Audit-Bypass SET ROLE Path → CLOSED ✅

### 修复验证

**`create_temporary_login`**（`conftest.py:551`）：角色恒为 `LOGIN NOBYPASSRLS`，不再接受 `bypassrls` 参数。✅

**`test_audit_operator_requires_set_role_for_cross_tenant`**（`test_platform_migrations_postgres.py:1438-1498`）：
- 未 SET ROLE 时：RLS 生效，tenant 未设置 → default deny → `rows == []` ✅
- `SET ROLE dayu_platform_audit` 后：BYPASSRLS 生效 → 跨租户 SELECT 可见（`[(UUID(_TENANT_A),), (UUID(_TENANT_B),)]`）✅
- INSERT 被权限拒绝 ✅
- UPDATE 被权限拒绝 ✅
- DROP TABLE 被权限拒绝 ✅

**`test_audit_operator_membership_options_exact`**（`test_platform_migrations_postgres.py:1501-1555`）：
- 查询 `pg_auth_members` 联合 `pg_roles`，获取 `admin_option` 和 `rolinherit` ✅
- 断言 audit-operator 是 `dayu_platform_audit` member ✅
- 断言 app 是 `dayu_platform_app` member ✅
- 断言无交叉 membership（audit-operator 不是 app member，app 不是 audit member）✅
- 断言所有 membership 的 `admin_option=false, rolinherit=true` ✅

### 独立复证

- `pg_auth_members` 查询精确获取 `admin_option`（member 是否可 GRANT 该角色）和 `rolinherit`（成员是否继承角色权限），而非仅查 rolname ✅
- `NOBYPASSRLS` + `SET ROLE` 的真实边界已证明：operator 自身无 BYPASSRLS，必须通过 SET ROLE 获得 ✅
- `test_app_cannot_set_role_audit`（line 1646）保留 app → audit 负例 ✅

## TERRA-002 — 13-Table Independent Catalog → CLOSED ✅

### 修复验证

**独立 expected catalog**（不依赖 ORM metadata、不读取迁移脚本）：

| Catalog | 覆盖范围 | 验证 |
|---------|---------|------|
| `_EXPECTED_COLUMNS`（line 102-238） | 13 表全部列：column name、`pg_catalog.format_type` 精确类型（含 `character(64)`/`character varying(2)`）、nullable、default（`transaction_timestamp()`/`1`/`true`/`''::text`/`'{}'::jsonb`） | ✅ |
| `_EXPECTED_CONSTRAINTS`（line 241+） | 每表 named PK/FK/UQ/CK 的 `pg_get_constraintdef` 全串 | ✅ |
| `_EXPECTED_INDEXES`（line 365+） | 全部非默认索引的 `indexdef` 含 partial predicate（`WHERE (email IS NOT NULL)` 等） | ✅ |
| `_EXPECTED_POLICIES`（line 388+） | 10 张私有表 policy 的 command/roles/USING/WITH CHECK | ✅ |
| `test_public_and_default_acl_exact`（line 1281+） | PUBLIC 无表权限、PUBLIC 无 schema USAGE、`pg_default_acl` 为空 | ✅ |

**测试函数**：
- `test_schema_exact_columns`（line 1083）：全 13 表列精确断言 ✅
- `test_schema_exact_named_constraints`（line 1145）：全表 named constraint 断言 ✅
- `test_schema_exact_indexes_with_predicates`（line 1192）：全表 index + predicate 断言 ✅
- `test_schema_exact_policies`（line 1236）：10 表 RLS policy 断言 ✅

### 独立复证

- expected catalog 硬编码自 plan S11-CTRL-03/04 契约，与 ORM/migration 是独立第三真源 ✅
- 测试从 `information_schema`/`pg_constraint`/`pg_indexes`/`pg_policies` 获取实际值，不从 ORM metadata 自比 ✅
- 13 表全覆盖，无遗漏 ✅

## TERRA-003 — Redacted Logs Collected → CLOSED ✅

### 修复验证

**`_log_redacted_diagnostics`**（`conftest.py:272-293`）：
- 调用 `_collect_redacted_logs(cluster)` 获取 bounded/redacted 日志 ✅
- 通过 `dayu-slice11.integration` logger（WARNING 级）输出 ✅
- `_collect_redacted_logs` 同时替换 admin password 和其 URL-encoded 形式（line 265-266）✅
- bounded 4000 字符（line 267-268）✅

**`platform_cluster` fixture**（`conftest.py:597-605`）：
- `except BaseException:` → `_log_redacted_diagnostics(cluster)` 然后 re-raise ✅
- `finally:` → `_log_redacted_diagnostics(cluster)` 然后 cleanup ✅
- 成功和异常路径均收集日志 ✅

**`test_fixture_redacted_logs_do_not_leak_secrets`**（line 789）：断言收集日志不含 raw password、URL-encoded password、DSN 且 bounded ✅

### 独立复证

- 成功路径：`finally` 调用 `_log_redacted_diagnostics` ✅
- 异常路径：`except BaseException` 调用 `_log_redacted_diagnostics`，然后 `finally` 再调用一次（两次收集，确保异常信息被捕获）✅
- cleanup 仍只按已验证 owner label/name 删除 ✅

## TERRA-004 — PgRow/PgScalar Strict Types → CLOSED ✅

### 修复验证

**`PgScalar`**（`conftest.py:66`）：`TypeAlias = str | int | bool | UUID | None` ✅
**`PgRow`**（`conftest.py:67`）：`TypeAlias = tuple[PgScalar, ...]` ✅
**`query_all`**（`conftest.py:693`）：返回 `list[PgRow]` ✅

**Architecture guard 扩展**（`test_architecture_boundaries.py:446-485`）：
- `test_integration_tests_never_use_escape_patterns`：扫描 `tests/integration/investment/**` 的 `Any/object/cast/type: ignore/getattr/hasattr` ✅
- `test_integration_tests_carry_chinese_docstrings`：扫描 integration tests 的中文 docstring ✅

### 独立复证

- `tuple[object, ...]` 已完全替换为 `tuple[PgScalar, ...]` ✅
- Integration tests 纳入宽类型 guard，后续逃逸会被拦截 ✅
- 无 `Any`/`object`/`cast`/`type: ignore`/`getattr`/`hasattr` 残留 ✅

## Prior PASS Items — Regression Check

| 区域 | 验证 | 结果 |
|------|------|------|
| 13-table ORM ↔ DDL 一致 | `_EXPECTED_COLUMNS` 独立 catalog 与 ORM 模型/迁移 DDL 三方一致 | ✅ 无回归 |
| Rolsuper admission 零副作用 | `env.py:63-91` `_admission_preflight` 未变 | ✅ 无回归 |
| Bootstrap secret 隔离 | `db.py`/`env.py`/`alembic.ini` 未变 | ✅ 无回归 |
| RLS FORCE/USING/WITH CHECK | `_EXPECTED_POLICIES` 独立 catalog 断言 | ✅ 无回归 |
| GRANT 矩阵 | `test_app_privileges_exact` + `test_public_and_default_acl_exact` | ✅ 无回归 |
| Downgrade 三类 fail-closed | `test_downgrade_fails_closed_on_*` 三测试未变 | ✅ 无回归 |
| PG16 容器隔离 | `platform_cluster` fixture + cleanup 逻辑未变（仅增加 log 收集） | ✅ 无回归 |
| Architecture guard 分组 | `_PURE_RELATIVE_PATHS`/`_INFRA_RELATIVE_PREFIX` 未变 | ✅ 无回归 |
| 三 README 一致 | 未变 | ✅ 无回归 |

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| `pytest tests/investment -q` | **PASS** — 194 passed（+2 from guard） |
| `pytest tests/integration/investment -q` | **PASS** — 28 passed（+6 from fix） |
| `pyright dayu/investment tests/investment tests/integration/investment` | **PASS** — 0 errors |
| `ruff check dayu/investment tests/investment tests/integration/investment` | **PASS** — All checks passed |
| `git diff --check HEAD` | **PASS** — clean |
| TERRA-001 SET ROLE 真实路径 | **PASS** — NOBYPASSRLS operator + SET ROLE + pg_auth_members exact |
| TERRA-002 独立 13 表 catalog | **PASS** — columns/constraints/indexes/policies/ACL 全覆盖 |
| TERRA-003 redacted logs | **PASS** — 成功+异常路径均收集，raw secret 不泄漏 |
| TERRA-004 PgRow strict types | **PASS** — `tuple[PgScalar, ...]` + guard 扩展 |
| PG17 stack 未触碰 | **PASS** — 未连接/停止/修改 |
| Slice-owned cleanup | **PASS** — container/network 为零 |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `_downgrade_admission` 使用 `RuntimeError` 而非 `PlatformMigrationAdmissionError`：功能等价（Alembic 均 catch 并 rollback），deferred to Slice 1.2。
- `source_subscriptions.source_definition_id` FK 名 63 字符上限：当前有效，deferred to Slice 1.2。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。

Terra 001-004 全部闭合：audit operator 改为 NOBYPASSRLS + SET ROLE 真实路径 + pg_auth_members exact options；13 表独立 expected catalog 覆盖 columns/constraints/indexes/policies/ACL；redacted logs 在成功+异常路径均收集且完全脱敏；PgRow strict types + integration guard 扩展。先前全部 PASS 项无回归。194 unit + 28 integration tests 全部通过，pyright 0 errors，ruff All checks passed。允许进入 code review completion。
