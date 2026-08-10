# Slice 1.1 platform schema corrective review-fix artifact

- **Work unit**：Investment Platform Restoration / Slice 1.1
- **Gate**：fix（corrective re-review round2）
- **Source reviews**：
  - Terra round1 re-review `code-review-20260810-slice-1.1-schema-rereview-terra.md`
    （FAIL，H/M/L=`0/2/1`）
  - MiM Native round1 re-review `code-review-20260810-slice-1.1-schema-rereview-mimo-native.md`
    （PASS，H/M/L=`0/0/0`）
- **Adjudication**：`slice-1.1-platform-schema-code-review-adjudication-20260810-codex.md`
  （round2：TERRA-R1-001..003 ACCEPTED）
- **Status**：**CLOSED / DUAL RE-REVIEW PASS**
- **External actions**：无（复用已 pinned PG16 digest，未拉取新镜像）

## Per-finding fix status

### TERRA-R1-001-已修复-中-PG16 membership option matrix 把 role 属性误当作 membership option

- **改法**：
  - `create_temporary_login` 不再用 `CREATE ROLE ... IN ROLE <group>`，
    改为先 `CREATE ROLE ... LOGIN NOBYPASSRLS`，再显式
    `GRANT <group> TO <login> WITH INHERIT TRUE, SET TRUE, ADMIN FALSE`
    （PostgreSQL 16 真实 membership option 语法）；
  - `test_audit_operator_membership_options_exact` 改为直接查询
    `pg_auth_members` 的 `m.inherit_option`、`m.set_option`、
    `m.admin_option` 三个独立字段，按 `(member, roleid)` 精确断言
    `(True, True, False)`；`pg_roles.rolinherit` 单独作为 LOGIN role
    属性断言，绝不替代 membership 字段；
  - 保留 NOBYPASSRLS、未 SET ROLE 的 RLS deny、SET ROLE 后只读与
    DML/DDL 拒绝、app `SET ROLE audit` 拒绝负例。
- **验证**：真实 PG16 integration 通过（探测确认三字段
  `True/True/False`、`rolinherit=True`）。

### TERRA-R1-002-已修复-中-independent expected catalog 未覆盖全部 physical indexes

- **改法**：
  - `test_schema_exact_indexes_with_predicates` 删除
    `indexname NOT LIKE 'pk_%'`、`NOT LIKE 'uq_%tenant_id_id%'` 与
    `NOT IN (SELECT conname FROM pg_constraint)` 全部过滤，改为对
    `dayu_platform` schema 全部 `pg_indexes` 行做双向 exact 比较；
  - `_EXPECTED_INDEXES` 扩展为 13 表全部 physical indexes（PK/unique
    backing、普通、partial），`indexdef` 精确含 unique/primary 标记与
    WHERE predicate；
  - 新增 `test_schema_exact_rejects_extra_pk_prefixed_index`：手工创建
    `pk_unchecked` 伪装 index，证明完整双向比较会拒绝（`set(by_table)`
    仍等于 expected 表集合，但 `companies` 索引列表不相等），随后清理
    并恢复 exact 一致。
- **验证**：真实 PG16 integration 通过。

### TERRA-R1-003-已修复-低-integration escape guard 可由限定名或别名绕过

- **改法**：`_collect_escape_violations`（及新 `_collect_escape_violations_from_source`）
  现在解析：
  - `Name` 裸名（`Any`/`object`）与别名（`import typing as t`、
    `from typing import Any as T`）；
  - `Attribute` 访问（`typing.Any`、`t.cast`）及属性链调用；
  - `from ... import name as alias` 的 callable alias（
    `from builtins import getattr as read_attr`）；
  - `type: ignore[...]`（含带 code 的形态）。
  - 新增两个自测：`test_escape_guard_catches_qualified_names_and_aliases`
    覆盖 9 个反例 + 3 个合法反例；`test_escape_guard_resolves_attribute_chain_and_module_alias`
    覆盖 `t.cast`/`g(...)`/`h(...)` 组合。production 与 integration 两处
    扫描共用增强版。
- **验证**：unit lane 通过（114 guard tests），现有生产代码无新违规。

## Changed files

- `tests/integration/investment/conftest.py`（GRANT WITH options 建立
  membership）
- `tests/integration/investment/test_platform_migrations_postgres.py`
  （membership 三字段断言、index 全量 catalog + pk_ 伪装自测）
- `tests/investment/test_architecture_boundaries.py`（escape guard
  Name/Attribute/alias + 自测反例）
- `tests/README.md`（index 全量、membership 三字段表述同步）
- `docs/reviews/slice-1.1-platform-schema-implementation-20260810-deepseek.md`
  （状态 CORRECTIVE FIX APPLIED）
- `docs/reviews/slice-1.1-platform-schema-code-review-adjudication-20260810-codex.md`
  （round2 fix status）
- 本文档

## Validation

```bash
pytest tests/investment -q                        # 196 passed
pytest tests/integration/investment -q            # 29 passed（真实 PG16，pinned digest）
pytest tests/investment --cov=dayu.investment ... # db 100%、models/domain 100%
pytest tests/integration/investment -q --cov=dayu/investment/storage ...
#   env.py 92%、0001_platform_foundation.py 99%、总 98%
pyright dayu/investment tests/investment tests/integration/investment  # 0 errors
ruff check dayu/investment tests/investment tests/integration/investment  # All checks passed
git diff --check                                   # clean
```

测试后 Slice-owned container/network 为零，既有 PG17 stack 未触碰。

## New risks / open questions

- `_downgrade_admission` 使用 `RuntimeError` 而非
  `PlatformMigrationAdmissionError`：既有 deferred，Slice 1.2 可统一。
- `source_subscriptions.source_definition_id` FK 名恰为 63 字符上限：
  既有 deferred，当前有效。

## Residual risk classification

| 风险 | 分类 |
| --- | --- |
| membership option 语义错误（rolinherit 冒充） | **fixed in current fix**（TERRA-R1-001） |
| index catalog 名称过滤可绕过 | **fixed in current fix**（TERRA-R1-002） |
| escape guard 可被限定名/别名绕过 | **fixed in current fix**（TERRA-R1-003） |
| downgrade admission 异常类型不统一 | deferred-with-owner（Slice 1.2） |
| FK 名 63 字符上限 | deferred-with-owner（Slice 1.2） |

## Status

最终复审：Terra
`code-review-20260810-slice-1.1-schema-final-terra.md` 与 MiM Native
`code-review-20260810-slice-1.1-schema-final-mimo-native.md` 均 PASS，open
H/M/L=`0/0/0`。TERRA-R1-001..003 与此前 TERRA-001..004 全部 CLOSED；本
artifact 状态为 **CLOSED / DUAL RE-REVIEW PASS**。未 push/PR/live。
