# Slice 1.1 platform schema review-fix artifact

- **Work unit**：Investment Platform Restoration / Slice 1.1
- **Gate**：fix（code-review findings）
- **Source review**：`docs/reviews/code-review-20260810-slice-1.1-schema-terra.md`
  （FAIL，H/M/L=`0/2/2`）；MiM Native PASS `0/0/0`
- **Adjudication**：`docs/reviews/slice-1.1-platform-schema-code-review-adjudication-20260810-codex.md`
  （Terra 001–004 ACCEPTED）
- **Status**：**CLOSED / SUPERSEDED BY CORRECTIVE FIX / DUAL RE-REVIEW PASS**
- **External actions**：无（未拉取新镜像；仅用已 pinned PG16 digest）

## Per-finding fix status

### TERRA-001-已修复-中-audit-bypass 测试以直接 BYPASSRLS 绕过受控 membership/SET ROLE 路径

- **改法**：`create_temporary_login` 移除 `bypassrls` 参数，角色恒为
  `NOBYPASSRLS`（PostgreSQL 默认显式声明）；`_make_audit_operator_login`
  只授予 `dayu_platform_audit` membership。新增
  `test_audit_operator_requires_set_role_for_cross_tenant`：
  未 `SET ROLE` 时 RLS 生效、tenant 未设置 => default deny（跨租户不可见）；
  显式 `SET ROLE dayu_platform_audit` 后跨租户 `SELECT` 可见但
  INSERT/UPDATE/DROP TABLE 全部被权限拒绝。新增
  `test_audit_operator_membership_options_exact`：`pg_auth_members`
  断言 audit-operator 是 `dayu_platform_audit` member、app 是
  `dayu_platform_app` member、无交叉 membership、`admin_option=false`、
  `rolinherit=true`。`test_audit_select_only_all_tables` 改为
  `SET ROLE` 后断言；app 的 `SET ROLE audit` 拒绝负例保留。
- **验证**：真实 PG16 integration 通过。

### TERRA-002-已修复-中-13 表 ORM/migration exact 契约没有独立且完整的 catalog 验收

- **改法**：在 `test_platform_migrations_postgres.py` 内置**独立
  expected catalog**（硬编码自 accepted plan S11-CTRL-03/04 契约，
  不读取 ORM metadata、不读取迁移脚本，杜绝同源自比）：
  - `_EXPECTED_COLUMNS`：13 表全部列，用 `pg_catalog.format_type`
    精确类型（含 `character(64)`/`character varying(2)` 长度）、
    nullable、default（`transaction_timestamp()`/`1`/`true`/`''::text`
    /`'{}'::jsonb`）；
  - `_EXPECTED_CONSTRAINTS`：每表 named PK/FK/UQ/CK 的
    `pg_get_constraintdef` 全串；
  - `_EXPECTED_INDEXES`：全部非默认索引的 `indexdef` 含 partial
    predicate（`WHERE (email IS NOT NULL)` 等）；
  - `_EXPECTED_POLICIES`：10 张私有表 policy 的
    command/roles/USING/WITH CHECK。
  - 新增 4 个测试：`test_schema_exact_columns`（全 13 表）、
    `test_schema_exact_named_constraints`、
    `test_schema_exact_indexes_with_predicates`、
    `test_schema_exact_policies`；
  - `test_public_and_default_acl_exact`：PUBLIC 无表权限、
    PUBLIC 无 schema USAGE、`pg_default_acl` 为空（无 blanket grant）。
  - membership options 由 TERRA-001 的 options 测试覆盖。
- **验证**：真实 PG16 integration 通过；发现并修复 pg_attribute 需
  过滤 `relkind='r'`（否则混入索引 attribute 行）。

### TERRA-003-已修复-低-fixture 声称的成功/失败 redacted log 收集未执行

- **改法**：`_collect_redacted_logs` 同时替换 admin password 与其 URL
  encoded 形式，bounded 4000 字符；`platform_cluster` fixture 在
  异常路径（`except BaseException`）与正常清理路径（`finally`）都调用
  新增 `_log_redacted_diagnostics` 接入 `dayu-slice11.integration`
  logger（WARNING 级，受控 pytest diagnostics）。新增
  `test_fixture_redacted_logs_do_not_leak_secrets`：断言收集日志不含
  raw password、URL-encoded password、DSN 且 bounded。
- **验证**：真实 PG16 integration 通过。

### TERRA-004-已修复-低-新增 integration helper 使用禁止的 object 宽类型

- **改法**：`query_all` 返回类型从 `list[tuple[object, ...]]` 改为
  `list[PgRow]`（`PgRow = tuple[PgScalar, ...]`，
  `PgScalar = str | int | bool | UUID | None`）；`tests/investment/
  test_architecture_boundaries.py` 新增
  `_iter_integration_test_files()` 与两个测试，把
  `tests/integration/investment/**` 纳入 `Any/object/cast/type: ignore/
  getattr/hasattr` 与中文 docstring 守护（TERRA-004）。
- **验证**：unit lane 通过（guard 新增 2 tests 生效；并因此修复
  `TestRlsBehavior` 类 docstring 缺汉字问题）。

## Changed files

- `tests/integration/investment/conftest.py`（PgRow/PgScalar、
  redacted logs 接入、create_temporary_login 去 bypassrls）
- `tests/integration/investment/test_platform_migrations_postgres.py`
  （expected catalog + 4 exact 测试 + ACL 测试 + audit SET ROLE 测试
  + redacted logs 测试）
- `tests/investment/test_architecture_boundaries.py`（integration
  forbidden-type/docstring guard）
- `dayu/investment/README.md`、`tests/README.md`（audit SET ROLE /
  expected catalog 表述同步）
- `docs/reviews/slice-1.1-platform-schema-implementation-20260810-deepseek.md`
  （状态 REVIEW FIX APPLIED）
- 本文档

## Validation

```bash
pytest tests/investment -q                        # 194 passed
pytest tests/integration/investment -q            # 28 passed（真实 PG16，pinned digest）
pytest tests/investment --cov=dayu.investment ... # db 100%、models/domain 100%
pytest tests/integration/investment -q --cov=dayu/investment/storage ...
#   env.py 92%、0001_platform_foundation.py 99%、总 98%
pyright dayu/investment tests/investment tests/integration/investment  # 0 errors
ruff check dayu/investment tests/investment tests/integration/investment  # All checks passed
git diff --check                                   # clean
```

测试后 Slice-owned container/network 为零，既有 PG17 stack 未触碰
（5 容器健康）。

## New risks / open questions

- `_downgrade_admission` 使用 `RuntimeError` 而非
  `PlatformMigrationAdmissionError`：MiM 已列为 residual，功能等价
  （Alembic 均 catch 并 rollback），保留现状，后续 slice 可统一。
- `source_subscriptions.source_definition_id` FK 名恰为 63 字符上限：
  MiM 已列为 residual，当前有效。

## Residual risk classification

| 风险 | 分类 |
| --- | --- |
| audit operator 直接 BYPASSRLS | **fixed in current fix**（TERRA-001） |
| 13 表 catalog 双真源漂移 | **fixed in current fix**（TERRA-002，独立 expected catalog） |
| fixture 失败诊断无日志 | **fixed in current fix**（TERRA-003） |
| integration 宽类型 | **fixed in current fix**（TERRA-004） |
| downgrade admission 异常类型不统一 | deferred-with-owner（Slice 1.2） |
| FK 名 63 字符上限 | deferred-with-owner（Slice 1.2 发现时处理） |

## Status

本轮初次修复后来由 Terra corrective re-review 重新打开三项证据缺口；它们已在
`slice-1.1-platform-schema-corrective-review-fix-20260810-deepseek.md` 完整修复。
最终 Terra 与 MiM Native 均 PASS、open H/M/L=`0/0/0`，因此本 artifact 状态为
**CLOSED / SUPERSEDED BY CORRECTIVE FIX / DUAL RE-REVIEW PASS**。未 push/PR/live。
