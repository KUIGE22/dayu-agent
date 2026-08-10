# Slice 1.1 platform schema code-review adjudication

- **Work unit**：Investment Platform Restoration / Slice 1.1
- **Controller**：Codex
- **状态**：**CLOSED / DUAL RE-REVIEW PASS**
- **Source reviews**：
  - `docs/reviews/code-review-20260810-slice-1.1-schema-terra.md`
  - `docs/reviews/code-review-20260810-slice-1.1-schema-mimo-native.md`
- **Accepted findings**：H/M/L=`0/2/2`
- **External actions**：无

## Review result

MiM Native 为 PASS、open `0/0/0`；Terra 为 FAIL、open `0/2/2`。Controller
逐项复核后接受 Terra 的四项 finding。它们均能在已接受的 Slice 1.1 测试/fixture/
artifact allowlist 内修复，不构成新 plan gap，也不授权修改 13 表生产 schema 或进入
Slice 1.2。

## Disposition

### TERRA-001 — ACCEPTED / Medium

现有 audit-operator LOGIN 自身带 `BYPASSRLS`，测试未证明 audit group membership +
`SET ROLE dayu_platform_audit` 的真实最小权限路径。修复必须让 operator 本身
`NOBYPASSRLS`，精确断言 PostgreSQL 16 `pg_auth_members` 的 INHERIT/SET/ADMIN
options；未 `SET ROLE` 时不能跨租户读取，显式 `SET ROLE` 后可跨租户只读且所有
DML/DDL 仍拒绝。app 到 audit 的负例保持。

### TERRA-002 — ACCEPTED / Medium

真实 PG16 lane 只对三表列清单和部分权限做 exact assertion，不足以证明 accepted
13-table catalog contract。新增与 ORM/migration 不共享数据源的 expected catalog，
对全部表的 columns/type/nullability/default、named PK/FK/unique/check、indexes/predicate、
RLS policy command/roles/USING/WITH CHECK、PUBLIC/default ACL 与 membership options 做
catalog exact comparison。已有行为测试保留。

### TERRA-003 — ACCEPTED / Low

`_collect_redacted_logs()` 是未调用的死 helper，与 S11-CTRL-06 的成功/失败 bounded
redacted diagnostics 契约不符。fixture 必须在 owned cluster 可用后的成功和异常清理
路径收集一次有界脱敏日志，并将其接入受控 pytest diagnostics；raw password/DSN 不得
出现，cleanup 仍只按已验证 owner label/name。

### TERRA-004 — ACCEPTED / Low

新增 `query_all()` 的 `tuple[object, ...]` 违反项目禁止宽类型签名的约束。改为覆盖
当前 catalog query 实际值的严格 test scalar/row 类型或每查询精确类型，并把
integration tests 纳入宽类型 guard；不得使用 `Any/object/cast/ignore/getattr/hasattr`
逃逸。

## Required gates

1. 所有四项新增 adversarial tests 先失败后通过；不得以修改 assertion 规避真实路径。
2. `pytest tests/investment -q` 与真实隔离 PG16 integration 全绿；结束后 Slice-owned
   container/network 为零，既有 PG17 stack 不动。
3. exact pyright、Ruff、forbidden-type/docstring、coverage、diff-check 与三 README
   truth gates 重新通过。
4. 更新 implementation artifact；新增 bounded fix artifact；然后 Terra + MiM Native
   双路 corrective code re-review，open H/M/L 必须归零。
5. 不 commit/push/PR，不运行 live data/model/broker，不进入 Slice 1.2。

## Corrective re-review adjudication

- Terra：`docs/reviews/code-review-20260810-slice-1.1-schema-rereview-terra.md`，
  FAIL，open H/M/L=`0/2/1`。
- MiM Native：
  `docs/reviews/code-review-20260810-slice-1.1-schema-rereview-mimo-native.md`，
  PASS，open H/M/L=`0/0/0`。

Controller 接受 Terra 的三项未闭合 finding；MiM 的 PASS 不能覆盖下列直接反例：

1. **TERRA-R1-001 / Medium — ACCEPTED**：PostgreSQL 16
   `pg_auth_members.inherit_option`、`set_option`、`admin_option` 是 membership
   row 的三个独立字段，`pg_roles.rolinherit` 不能替代。fixture 必须显式建立
   `INHERIT TRUE, SET TRUE, ADMIN FALSE`，catalog 精确断言三字段；`rolinherit`
   若保留只能单独断言 LOGIN role 属性。
2. **TERRA-R1-002 / Medium — ACCEPTED**：index query 过滤 constraint-backed、
   `pk_%` 与特定 `uq_%` 名称，允许额外物理 index 假绿。删除名称/constraint
   过滤，并以独立 expected catalog 双向 exact 覆盖 13 表全部 `pg_indexes` 行，
   包含 PK/unique backing、普通/partial index、definition/predicate。
3. **TERRA-R1-003 / Low — ACCEPTED**：escape guard 只识别裸 `Name`，可被
   `typing.Any`、`typing.cast`、module alias 与 imported callable alias 绕过。
   guard 必须解析 `Name`、`Attribute` 和 import aliases，并为限定名、模块 alias、
   callable alias、`type: ignore[...]` 加自测反例。

三项仍在 Slice 1.1 tests/fixture/artifact allowlist 内，不是新 plan gap。TERRA-003
日志脱敏项保持 CLOSED；原修复的真实 NOBYPASSRLS/SET ROLE 行为与 strict PgRow
保持，不得回退。修复后须再次双路 corrective re-review，open H/M/L 归零。

## Final closure

- Terra final：`docs/reviews/code-review-20260810-slice-1.1-schema-final-terra.md`，
  **PASS**，open H/M/L=`0/0/0`。
- MiM Native final：
  `docs/reviews/code-review-20260810-slice-1.1-schema-final-mimo-native.md`，
  **PASS**，open H/M/L=`0/0/0`。

TERRA-001..004 与 TERRA-R1-001..003 全部 CLOSED；accepted findings 当前
open H/M/L=`0/0/0`。没有 deferred code finding；两项低风险 residual 继续按已有
owner 进入 Slice 1.2，不阻断本 slice accepted commit。

## Corrective round2 fix status

- **TERRA-R1-001 / ACCEPTED / Medium — 已修复**：fixture 显式
  `GRANT <group> TO <login> WITH INHERIT TRUE, SET TRUE, ADMIN FALSE`；
  `pg_auth_members` 直接查询并精确断言 `m.inherit_option=true` /
  `m.set_option=true` / `m.admin_option=false`；`rolinherit` 单独作为
  LOGIN role 属性断言，不再替代 membership 字段。保留 NOBYPASSRLS、
  未 SET deny、SET ROLE 只读与 app 负例。
- **TERRA-R1-002 / ACCEPTED / Medium — 已修复**：index query 删除全部
  名称/constraint 过滤，独立 expected catalog 双向 exact 覆盖 13 表
  全部 `pg_indexes` 行（PK/unique backing、普通、partial，
  definition/predicate 精确）；新增 `pk_unchecked` 伪装 index 自测
  证明额外 index 会被完整比较拒绝。
- **TERRA-R1-003 / ACCEPTED / Low — 已修复**：escape guard 解析
  `Name`、`Attribute`、`import module as alias` 与
  `from ... import name as alias`，覆盖 `typing.Any` / `typing.cast` /
  `t.cast` / aliased `cast`/`getattr`/`hasattr` / `type: ignore[...]`
  自测反例；production 与 integration 两处扫描均使用增强版。
- TERRA-003（日志脱敏）保持 CLOSED，未回退。
- 修复详情与验证见
  `docs/reviews/slice-1.1-platform-schema-corrective-review-fix-20260810-deepseek.md`。
- **待办**：Terra + MiM Native 双路 corrective re-review，open H/M/L
  归零后关闭本 gate。
