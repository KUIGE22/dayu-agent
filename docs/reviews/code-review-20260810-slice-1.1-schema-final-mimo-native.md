# Final Corrective Re-review — Slice 1.1 Platform Schema

## Scope

- Mode: final corrective re-review（只读，最终 closure gate）
- Branch: `codex/investment-platform`
- Base: `7209eac`（doc-owner erratum accepted commit）
- Review clock: `2026-08-10`（本机系统时钟）
- Output file: `docs/reviews/code-review-20260810-slice-1.1-schema-final-mimo-native.md`
- Source chain: Terra initial FAIL → MiM initial PASS → Controller adjudication（Terra 001-004 ACCEPTED）→ DeepSeek fix → MiM rereview PASS → **本 final closure**
- Excluded scope: Slice 1.2+、live data/model/broker、PG17 stack

## PG16 Membership Three Fields — Independent Verification

### pg_auth_members 精确三字段

`test_audit_operator_membership_options_exact`（line 1614-1669）：

```sql
SELECT m.member::regrole::text, m.roleid::regrole::text,
       m.inherit_option, m.set_option, m.admin_option
FROM pg_auth_members m
JOIN pg_roles gr ON gr.oid = m.roleid
WHERE gr.rolname IN ('dayu_platform_app', 'dayu_platform_audit')
ORDER BY gr.rolname, m.member::regrole::text
```

查询 PostgreSQL 16 `pg_auth_members` 的三个独立 membership 字段：
- `inherit_option`：成员是否继承角色权限（membership 级）
- `set_option`：成员是否可 `SET ROLE` 到该角色（membership 级）
- `admin_option`：成员是否可 GRANT 该角色给他人（membership 级）

断言（line 1668）：`assert options == (True, True, False)`——三个 membership 字段精确匹配。

### rolinherit 作为独立 role 属性断言

```sql
SELECT rolname, rolinherit FROM pg_roles
WHERE rolname IN ('<audit_login>', '<app_login>')
```

断言（line 1669-1671）：`pg_roles.rolinherit` 是 LOGIN role 的属性，与 membership option 分离断言，不相互替代。

### 交叉 membership 验证

- audit-operator 是 `dayu_platform_audit` member ✅
- app 是 `dayu_platform_app` member ✅
- audit-operator 不是 `dayu_platform_app` member ✅
- app 不是 `dayu_platform_audit` member ✅

### SET ROLE 真实边界

`test_audit_operator_requires_set_role_for_cross_tenant`（line 1546-1606）：
- 未 SET ROLE：operator 自身 NOBYPASSRLS → RLS 生效 → tenant 未设置 → default deny → `rows == []` ✅
- `SET ROLE dayu_platform_audit`：获得 group BYPASSRLS → 跨租户 SELECT 可见 ✅
- INSERT/UPDATE/DROP TABLE 全部被权限拒绝 ✅

## All Physical Index Exact + pk_ Fake Negative

### _EXPECTED_INDEXES 覆盖

13 表全部 physical index（含 pk_ 前缀的 PRIMARY KEY index）：

| 表 | pk_ index | 其它 index |
|----|-----------|-----------|
| organizations | `pk_organizations` | — |
| companies | `pk_companies` | — |
| securities | `pk_securities` | `ix_securities_company_id` |
| source_definitions | `pk_source_definitions` | — |
| users | `pk_users` | `uq_users_tenant_email_lower`（partial） |
| roles | `pk_roles` | — |
| permissions | `pk_permissions` | — |
| user_roles | `pk_user_roles` | — |
| role_permissions | `pk_role_permissions` | — |
| api_tokens | `pk_api_tokens` | — |
| source_subscriptions | `pk_source_subscriptions` | `uq_source_subscriptions_tenant_wide`（partial）、`uq_source_subscriptions_company`（partial）、`uq_source_subscriptions_security`（partial） |
| source_sync_runs | `pk_source_sync_runs` | `ix_source_sync_runs_tenant_subscription_started` |
| source_health_snapshots | `pk_source_health_snapshots` | `ix_source_health_snapshots_tenant_subscription_observed` |

`test_schema_exact_indexes_with_predicates`（line 1245）：全 13 表双向比较 `pg_indexes`。✅

### pk_ 伪装负例

`test_schema_exact_rejects_extra_pk_prefixed_index`（line 1292-1341）：
- 手工创建 `pk_unchecked` 普通 index → `by_table["companies"] != _EXPECTED_INDEXES["companies"]` → 比较失败 ✅
- 移除后恢复 exact 一致 ✅
- 证明 `pg_indexes` 双向比较不因名称前缀被过滤而假绿 ✅

## Escape Guard Name/Attribute/Module/From Aliases/Type-Ignore Self-Test

### `_collect_escape_aliases` 别名解析

`test_architecture_boundaries.py:312-338`：
- `Import`：`import typing as t` → `aliases["t"] = "typing"` → 后续 `t.cast()` 被解析为 `cast()` ✅
- `ImportFrom`：`from builtins import getattr as g` → `aliases["g"] = "getattr"` → 后续 `g()` 被解析为 `getattr()` ✅
- `import hasattr as h` → `aliases["h"] = "hasattr"` → 后续 `h()` 被解析为 `hasattr()` ✅

### `_resolve_call_target` 属性链解析

`test_architecture_boundaries.py:341-350`：
- `t.cast(str, x)` → 属性链 `t` → alias `typing` → `cast` → 匹配 `_ESCAPE_CALL_NAMES` ✅
- `g(x, 'k')` → alias `getattr` → 匹配 ✅
- `h(x, 'k')` → alias `hasattr` → 匹配 ✅

### type: ignore 扫描

`test_architecture_boundaries.py:306-308`：逐行扫描 `# type: ignore` 字符串。✅

### 集成测试纳入 guard

`test_integration_tests_never_use_escape_patterns`（line 543）：扫描 `tests/integration/investment/**` 的 `Any/object/cast/type: ignore/getattr/hasattr`。✅

## TERRA 001-004 and Original Security/RLS/Downgrade/Log/Cleanup — No Regression

| 区域 | 状态 | 证据 |
|------|------|------|
| TERRA-001 audit SET ROLE | ✅ CLOSED | NOBYPASSRLS operator + SET ROLE + pg_auth_members 三字段 exact |
| TERRA-002 13-table catalog | ✅ CLOSED | 独立 expected catalog + pk_ 负例 + policies/ACL |
| TERRA-003 redacted logs | ✅ CLOSED | except BaseException + finally 双路径收集 |
| TERRA-004 PgRow strict types | ✅ CLOSED | `tuple[PgScalar, ...]` + integration guard |
| Rolsuper admission | ✅ 无回归 | `env.py:63-91` 未变 |
| Bootstrap secret 隔离 | ✅ 无回归 | db.py/env.py/alembic.ini 未变 |
| RLS FORCE/USING/WITH CHECK | ✅ 无回归 | `_EXPECTED_POLICIES` 独立 catalog |
| GRANT 矩阵 | ✅ 无回归 | `test_app_privileges_exact` + `test_public_and_default_acl_exact` |
| Downgrade 三类 fail-closed | ✅ 无回归 | 三测试未变 |
| PG16 容器隔离 | ✅ 无回归 | fixture + cleanup 未变 |
| Architecture guard 分组 | ✅ 无回归 | pure/infra 路径分组 + integration guard 扩展 |
| 三 README 一致 | ✅ 无回归 | 未变 |

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| `pytest tests/investment -q` | **PASS** — 196 passed |
| `pyright dayu/investment tests/investment tests/integration/investment` | **PASS** — 0 errors, 0 warnings |
| `ruff check dayu/investment tests/investment tests/integration/investment` | **PASS** — All checks passed |
| `git diff --check HEAD` | **PASS** — clean |
| PG16 membership 三字段 exact | **PASS** — inherit_option/set_option/admin_option + rolinherit 分离 |
| pk_ 伪装负例 | **PASS** — `pk_unchecked` 被双向比较拒绝 |
| Escape guard 别名解析 | **PASS** — `import as` / `from import as` / Attribute chain / type: ignore |
| TERRA 001-004 无回归 | **PASS** — 全部 CLOSED |
| 原始 security/RLS/downgrade/log/cleanup | **PASS** — 全部无回归 |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `_downgrade_admission` 使用 `RuntimeError` 而非 `PlatformMigrationAdmissionError`：功能等价，deferred to Slice 1.2。
- `source_subscriptions.source_definition_id` FK 名 63 字符上限：当前有效，deferred to Slice 1.2。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。

Slice 1.1 final closure gate 全部通过：PG16 `pg_auth_members` 三字段（`inherit_option`/`set_option`/`admin_option`）精确断言且与 `pg_roles.rolinherit` 分离；13 表全部 physical index exact 包含 pk_ 且 `pk_unchecked` 伪装负例被拒绝；escape guard 解析 `Import as`/`from Import as`/Attribute chain/`type: ignore` 并纳入 integration tests；TERRA 001-004 全部 CLOSED 无回归；原始 security/RLS/downgrade/log/cleanup 无回归。196 unit tests 全部通过，pyright 0 errors，ruff All checks passed。允许 accepted local commit。
