# Code Review — Slice 1.1 Platform Schema Final Corrective Re-review（Terra）

## Scope

- Mode: 当前未提交 Slice 1.1 的 final corrective re-review（只读）。
- Branch/base: `codex/investment-platform`，base 为 `7209eac`（doc-owner accepted commit）。
- Output: 本文件（用户指定固定路径）。未 stage、未修改 code/tests/README/plan/既有 artifacts，未 commit/push/PR。
- Complete sources read: Terra/MiM 初审、Terra/MiM round1 re-review、Controller 初审与 round2 adjudication、`review-fix` 与 `corrective-review-fix` artifacts，以及当前全部 tracked diff 与新增文件。
- Included execution path: `env.py → 0001 migration → ORM → PG16 fixture → integration catalog/RLS/RBAC/downgrade tests → architecture guard`。
- Excluded: Slice 1.2+、live/model/broker/外发、既有 PG17 stack；无 subagent。

## Findings

未发现实质性问题。

## Closure evidence

| 项目 | 独立复证 |
| --- | --- |
| TERRA-R1-001 membership / audit | `create_temporary_login()` 先创建 `LOGIN NOBYPASSRLS`，再以 PG16 语法显式 `GRANT <group> TO <login> WITH INHERIT TRUE, SET TRUE, ADMIN FALSE`。真实 PG16 test 直接读取 `pg_auth_members.inherit_option/set_option/admin_option` 并按 `(member, roleid)` 断言 `(True, True, False)`；`pg_roles.rolinherit` 另行作为 LOGIN 属性断言。未 `SET ROLE` default-deny、`SET ROLE dayu_platform_audit` 跨 tenant 只读且 DML/DDL 被拒、app `SET ROLE audit` 负例均保留并通过。 |
| TERRA-R1-002 13 表 physical indexes | `_EXPECTED_INDEXES` 独立列出 13 表全部 `pg_indexes` 行（PK/unique backing、普通、partial）；查询没有名称或 constraint 过滤，先双向校验表集合，再逐表精确比较 `(indexname, indexdef)`。真实 PG16 `pk_unchecked` 额外 index 自测显示 `companies` 实际列表与期望不等，清理后恢复 exact 一致。columns/default、named constraints、policy command/roles/`USING`/`WITH CHECK`、PUBLIC/default ACL assertions 同时通过。 |
| TERRA-R1-003 strict guard | guard 同时解析 `Name`、`Attribute`、module alias 与 `from-import` callable alias，并覆盖 `typing.Any`、`typing.cast`、`t.cast`、alias `cast/getattr/hasattr`、`type: ignore[...]` 的源码级失败自测；production 与 integration 均复用该 guard。当前扫描只命中 SQL 字面量或说明文字中的 `object`，无宽类型或逃逸调用。 |
| TERRA-003 diagnostics / cleanup | `_collect_redacted_logs()` 对 raw 与 URL-encoded password 脱敏并限制 4000 字符；fixture 的异常与 `finally` 路径都接入受控 diagnostics logger，cleanup 仍必须先核验 `dayu-slice11.owner` label。真实 lane 后不存在该 label 的 container/network。 |
| 既有 security gates | 本轮未发现 pre-DDL `rolsuper` admission、RLS `ENABLE + FORCE`/default deny、最小 GRANT/PUBLIC ACL、无 `CASCADE` downgrade admission、bootstrap DSN 隔离或 pure/storage boundary 的回归；真实 PG16 lane 覆盖 upgrade/downgrade、RLS、RBAC 与三类 downgrade fail-closed。 |

## Validation

| 检查 | 结果 |
| --- | --- |
| `pytest tests/investment -q` | PASS，196 passed |
| `pytest tests/integration/investment -q` | PASS，29 passed；真实 pinned PostgreSQL 16 fixture |
| `pyright dayu/investment tests/investment tests/integration/investment` | PASS，0 errors / warnings / informations |
| `ruff check dayu/investment tests/investment tests/integration/investment` | PASS，All checks passed |
| `git diff --check HEAD` | PASS |
| Owned cleanup / PG17 protection | PASS；`dayu-slice11.owner` container/network 为零；只读列举确认既有 `investment-agent-platform-postgres-1`（`pgvector/pgvector:pg17`）仍在，未连接、停止或修改 |

## Open Questions

无。

## Residual Risk

- 既有 deferred 项：downgrade 使用 `RuntimeError` 而非 `PlatformMigrationAdmissionError`，以及一个 FK 名恰达 PostgreSQL 63 字符上限；均未由本 corrective diff 新增，已归属后续 Slice，不计入本 gate open。

## Conclusion

**PASS**。Open H/M/L = **0 / 0 / 0**。

TERRA-001..004 与 round2 的 TERRA-R1-001..003 均已按真实 PG16 语义闭合；当前未发现可阻断 Slice 1.1 code-review gate 的实现或测试证据缺口。
