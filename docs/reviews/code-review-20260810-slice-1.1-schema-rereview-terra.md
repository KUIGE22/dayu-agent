# Code Corrective Re-review — Slice 1.1 Platform Schema（Terra）

## Scope

- Mode: current uncommitted Slice 1.1 corrective re-review（只读）。
- Base: `7209eac`；未 stage、未修改 production/tests/README/plan/既有 artifact，未 commit/push/PR。
- Required source read: Terra/MiM 原审查与 MiM corrective re-review、Controller adjudication、DeepSeek implementation/review-fix artifact，以及当前全部 tracked diff 与新增文件。
- Focus: 逐项复证 Controller 已采纳的 TERRA-001..004；不运行 live/model/broker，不触碰既有 PG17。

## TERRA closure matrix

| 项 | 结论 | 证据 |
| --- | --- | --- |
| TERRA-001 audit operator / membership | **未闭合** | operator 已为 `NOBYPASSRLS`，并真实覆盖未 `SET ROLE` 的 RLS deny、`SET ROLE` 后跨 tenant `SELECT` 与 DML/DDL deny；但 PG16 membership 三 option catalog 未被正确查询/断言。 |
| TERRA-002 independent 13-table catalog | **未闭合** | 13 表 columns/default、named constraints、policy（含 `USING`/`WITH CHECK`）和 PUBLIC/default ACL 均改为 catalog 读取；但 index query 过滤掉所有 constraint-backed 以及特定前缀索引，不能称为完整 expected index catalog。 |
| TERRA-003 bounded/redacted diagnostics | **闭合** | 成功 `finally` 与异常 `except` 均调用受控 logger；collector 4000 字符截断，raw/URL-encoded password 脱敏，运行期测试通过，cleanup 仍先核验 owner label。 |
| TERRA-004 integration strict guard | **未闭合** | 当前没有 `Any/object/cast/ignore/getattr/hasattr` 实例，且 `PgRow/PgScalar` 已替换宽类型；但 AST guard 只能拦截裸名称/裸调用，限定名和 import alias 可绕过。 |

## Findings

### 001-未闭合-中-PG16 membership option matrix 把 role 属性误当作 membership option

- **入口/函数**: `create_temporary_login()` 与 `test_audit_operator_membership_options_exact()`。
- **文件(行号)**: `tests/integration/investment/conftest.py:550-558`；`tests/integration/investment/test_platform_migrations_postgres.py:1501-1551`。
- **输入场景**: audit operator 加入 `dayu_platform_audit`，app login 加入 `dayu_platform_app`；需要证明 PG16 的 membership `INHERIT/SET/ADMIN` matrix，而不是仅证明一次当前默认路径可用。
- **实际分支**: helper 用 `CREATE ROLE ... IN ROLE <group>` 依赖默认 membership options。catalog 查询只取 `m.admin_option, r.rolinherit`，并把 `rolinherit` 断言为第二个“option”；docstring 明称 `pg_auth_members` 只记录 `admin_option`。
- **直接证据**: PostgreSQL 16 的 `pg_auth_members` 明确有彼此独立的 `admin_option`、`inherit_option`、`set_option`；而本测试完全未查询 `m.inherit_option` 或 `m.set_option`。`pg_roles.rolinherit` 是 role 属性，不能替代任一具体 membership row 的两个 option。当前 `SET ROLE` 行为测试只能间接覆盖该临时 audit membership 当下的 SET 能力，不能形成 Controller 要求的精确 catalog matrix。
- **复现**: 在当前 SQL 的 membership row 上将 `m.inherit_option` 或 `m.set_option` 作为待观察字段，现有 `SELECT`/assertion 无任何失败分支；反之，`rolinherit=true` 仍可与某条 membership `INHERIT FALSE` 或 `SET FALSE` 并存。官方 PG16 catalog 定义见 [pg_auth_members](https://www.postgresql.org/docs/16/catalog-pg-auth-members.html)。
- **影响**: TERRA-001 对最小权限和受控 `SET ROLE` 的 exact evidence 尚不成立；artifact 的“INHERIT 是 role 属性”说明也会误导后续维护。
- **最小修复**: 显式以 PG16 `GRANT <group> TO <login> WITH INHERIT TRUE, SET TRUE, ADMIN FALSE` 建立 fixture membership（或在创建后显式调整）；查询并按 `(member, roleid)` 精确断言 `m.inherit_option=true`、`m.set_option=true`、`m.admin_option=false`。`rolinherit` 如要保留，单独作为 LOGIN role 的属性断言，绝不替代 membership 字段；保留现有未 SET ROLE / SET ROLE / app 负例行为测试。
- **严重程度**: 中。

### 002-未闭合-中-independent expected catalog 未覆盖全部 physical indexes

- **入口/函数**: `TestSchemaExact.test_schema_exact_indexes_with_predicates()`。
- **文件(行号)**: `tests/integration/investment/test_platform_migrations_postgres.py:1192-1233`。
- **输入场景**: 13 表任一 primary/unique backing index、普通 index 或 partial index 被漏建、额外建入，或 index 定义漂移。
- **实际分支**: query 通过 `indexname NOT LIKE 'pk_%'`、`NOT LIKE 'uq_%tenant_id_id%'` 以及 `indexname NOT IN (SELECT conname FROM pg_constraint)` 排除了 constraint-backed indexes；`_EXPECTED_INDEXES` 只含六个显式创建的非 constraint indexes。
- **直接证据**: 该测试的断言对象不是完整 PG16 `pg_indexes` 集合。任何名称带 `pk_` / `uq_%tenant_id_id%` 的额外 non-constraint index 均会被静默过滤；所有 primary/unique backing index 的实际 `indexdef`/predicate 则根本未比较。`pg_constraint` 的 expected definition 不能替代“全部 indexes”的独立 catalog 证据。
- **复现**: 对已 upgrade 的库执行 `CREATE INDEX pk_unchecked ON dayu_platform.companies (legal_name)`；现有 index query 因 `NOT LIKE 'pk_%'` 不返回该对象，`by_table == _EXPECTED_INDEXES` 仍可通过。该场景表明不是完整 catalog comparison。
- **影响**: TERRA-002 和 Controller 所要求的“全部 indexes/predicate、不能因漏 query 假绿”未闭合；schema 验收仍可遗漏 physical index 漂移。
- **最小修复**: 删除名称/constraint 排除条件，建立独立 expected catalog 覆盖每张表的所有 `pg_indexes` 行（包括 PK/unique backing indexes），或用 `pg_index` + `pg_get_indexdef`/`pg_get_expr(indpred, indrelid)` 显式区分 constraint backing index、unique/primary 标记与 predicate；实际表集合与 expected 表集合须双向 exact 比较。
- **严重程度**: 中。

### 003-未闭合-低-integration escape guard 可由限定名或别名绕过

- **入口/函数**: `_collect_escape_violations()` 与 `test_integration_tests_never_use_escape_patterns()`。
- **文件(行号)**: `tests/investment/test_architecture_boundaries.py:245-271, 446-468`。
- **输入场景**: 新增 integration test 用 `typing.Any`、`typing.cast(...)`、`builtins.getattr as read_attr` 或对应 alias 绕过严格类型/边界约束。
- **实际分支**: visitor 只检查 `ast.Name` 的 `Any/object` 及 `ast.Call` 且 `func` 是裸 `ast.Name` 的 `cast/getattr/hasattr`；没有解析 `ast.Attribute` 或 import alias。
- **直接证据/复现**: 在任一被扫描 integration 文件加入 `import typing as t; value = t.cast(str, source)` 或 `from builtins import getattr as read_attr; read_attr(source, "x")`，AST 节点分别为 attribute/alias，不会命中 :263-266；guard 仍会通过。当前 tree 没有这些逃逸实例，但守护并未覆盖其声称禁止的写法。
- **影响**: TERRA-004 的当前宽类型已移除，但未来可重新引入同类 escape 而不被 guard 拦截，未满足“真实覆盖、无 Any/object/cast/ignore/getattr/hasattr 逃逸”的 closure 条件。
- **最小修复**: 以 AST 同时检查 `Name` 和 `Attribute.attr`，并跟踪 `from ... import ... as ...` / module aliases；或在规则允许范围内明确禁止这些来源模块的导入。为每种限定名、alias 与 `type: ignore[...]` 保留一个 guard 自测反例。
- **严重程度**: 低。

## Validation

| 检查 | 结果 |
| --- | --- |
| `pytest tests/investment -q` | PASS，194 passed |
| `pytest tests/integration/investment -q` | PASS，28 passed；真实 pinned PostgreSQL 16 fixture |
| `pyright dayu/investment tests/investment tests/integration/investment` | PASS，0 errors / 0 warnings / 0 informations |
| `ruff check dayu/investment tests/investment tests/integration/investment` | PASS，All checks passed |
| `git diff --check HEAD` | PASS |
| PG16 fixture cleanup | PASS；测试后 `dayu-slice11.owner` label 下 container/network 为零 |
| PG17 protection | PASS；只读列举仍有原 5 个 `investment-agent-platform-*` 容器，其中 PostgreSQL 为 `pgvector/pgvector:pg17`；本轮没有连接、停止或修改它们 |

## Open Questions

无。

## Residual Risk

- `RuntimeError` 与 `PlatformMigrationAdmissionError` 的 downgrade 异常类型不统一，以及 63 字符 FK 名上限，沿用既有 deferred ownership；不属于本 corrective diff 的新增回归。
- 当前 `.venv` 的既有 `pip check` 冲突未在本轮重跑，且先前已确认不涉及本 Slice 新增的 PostgreSQL direct dependencies；因此不归类为本轮 finding。

## Conclusion

**FAIL**。Open H/M/L = **0 / 2 / 1**。

真实 PG16 行为、日志脱敏调用、cleanup、unit、pyright、Ruff 与 diff-check 均通过，且当前 implementation 没有发现 raw DSN/password 持久化或 PG17 操作。但 TERRA-001 对 PostgreSQL 16 membership options 的验收使用了错误 catalog 语义，TERRA-002 的 expected index catalog 仍有可被名称过滤绕开的漏项，TERRA-004 的 integration guard 也不是不可绕过的守护。上述三项修复并再次复审前，不应关闭 Slice 1.1 code-review gate。
