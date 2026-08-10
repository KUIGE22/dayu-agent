# Plan Final Re-Review — Slice 1.1 Schema / Environment（Terra）

## 范围与方法

- 审查时间：2026-08-10 11:05 CST。
- 只读核对修订后的 Slice 1.1 计划与 Controller corrective disposition：
  - `docs/plans/2026-08-10-investment-platform-restoration.md`
  - `docs/reviews/plan-fix-20260810-slice-1.1-schema-environment-codex.md`
- 逐项回验先前 Terra 001/002、MiM 001–004 的闭合证据；重点挑战逐表 schema、最小权限与 membership、无 `CASCADE` downgrade、Docker fixture、路径 guard 与 pip constraints 真源。
- 本轮未修改 plan、代码、测试、依赖或既有 review；未执行镜像拉取、容器、安装或 live 操作。

## 已闭合的既有观察项

| 原观察项 | 结论 | 修订计划中的直接证据 |
| --- | --- | --- |
| Terra 001：schema 仅列对象，无法实现或验收 | 已闭合 | S11-CTRL-03 逐表规定 13 张表的列、主/外键、唯一/检查约束、索引、版本与审计字段；并要求使用 `information_schema`、`pg_constraint`、`pg_indexes` 做独立集成验收。 |
| Terra 002：app/audit 权限与 membership 不可判定 | 已闭合 | S11-CTRL-04 明定 app/audit 角色属性、bootstrap 角色边界、禁止 app 获得 audit membership/`SET ROLE`、schema/table 权限矩阵、RLS policy 与正反向集成测试。 |
| MiM 001：pure-vs-storage guard 范围含混 | 已闭合 | S11-CTRL-02 以 `_INVESTMENT_SRC` 相对路径列出 pure 与 `storage/**` 两套精确 forbidden set；未知新路径默认 pure/reject，且明确根 `__init__.py` 不得 re-export storage/ORM。 |
| MiM 002：Docker fixture 生命周期不完整 | 已闭合 | S11-CTRL-06 规定官方固定 tag/digest、Docker CLI、随机 label/name/network/loopback 端口、`pg_isready` 上限、redacted logs 与仅按已验证 label/name 清理；禁止 broad glob、prune、compose down。 |
| MiM 003：lock/resolver 真源不明确 | 已闭合 | S11-CTRL-01 指定 `pip` constraints 为唯一安装真源，给出最低精确 pins、common/platform lock 关系和干净 venv 安装命令；`uv.lock` 明确不是真源。 |
| MiM 004：seed 与对象 downgrade 处理不完整 | 已闭合 | S11-CTRL-05 规定 policy/default privilege/grant → 13 表（含默认组织）→ schema `RESTRICT` → group roles 的确定顺序，严禁 `CASCADE`；任何外部 membership/session/dependency 均整体失败并回滚。 |

## Findings

### 001 — 高：迁移 bootstrap 身份缺少创建 `BYPASSRLS` 角色的可执行前提

- **位置**：Slice 1.1，S11-CTRL-04「role 和 membership」与 S11-CTRL-05「upgrade」约定。
- **现状**：计划要求在 migration 中创建 `dayu_platform_audit NOLOGIN ... BYPASSRLS`，并将 bootstrap principal 描述为外部提供的 `LOGIN/owner`；但没有规定该 principal 必须拥有 `SUPERUSER` 或 `BYPASSRLS` 属性，也没有给出等价的、可验证的预置流程。与此同时，S11-CTRL-05 又要求同名预存 role/schema fail-closed，排除了由外部预先无条件创建该 audit role 的退路。
- **直接证据**：PostgreSQL 规定只有 superuser 或自身具有 `BYPASSRLS` 的角色才能指定 `BYPASSRLS` 创建角色；见 PostgreSQL 官方 [`CREATE ROLE`](https://www.postgresql.org/docs/current/sql-createrole.html) 文档。单有常见的 `CREATEROLE`/对象 owner 能力不足以执行该 DDL。
- **可复现反例**：以 `LOGIN CREATEROLE NOBYPASSRLS` 的迁移账户执行 upgrade，`CREATE ROLE dayu_platform_audit ... BYPASSRLS` 会被 PostgreSQL 拒绝；迁移在 schema 与表就绪前失败。试图预置同名 audit role 又会触发计划要求的 fail-closed。
- **影响**：S11-CTRL-04/05 的最小权限目标无法在通常的 migration bootstrap 环境中落地，导致 Schema 初始化无法执行，或促使实现绕开计划的 fail-closed/最小权限边界。
- **建议纠正**：在 S11-CTRL-05 明确且测试下列单一路径：migration 专用、短生命周期的 bootstrap principal 必须是 `SUPERUSER` 或具备 `BYPASSRLS`；upgrade 在任何 DDL 前检查 `rolsuper OR rolbypassrls`，不满足时给出稳定的 fail-closed 错误。运行时 application DSN 必须仅继承 app group，绝不复用该 bootstrap DSN。集成测试还应覆盖：无 `BYPASSRLS` 的 `CREATEROLE` bootstrap 预检失败且未创建对象；容器初始管理账户的正向迁移成功。
- **验收标准**：计划同时指定 bootstrap 能力、其仅限 migration 的生命周期、DDL 前负向预检与正负向集成测试；同名 role fail-closed 语义保持不变。

## Open H/M/L

| 级别 | 数量 | 项目 |
| --- | ---: | --- |
| H | 1 | 001 — bootstrap 无法保证创建 `BYPASSRLS` audit group |
| M | 0 | 无 |
| L | 0 | 无 |

## 结论

**FAIL**（open H/M/L：**1 / 0 / 0**）。

先前 Terra 001/002 与 MiM 001–004 已全部闭合，且逐表 schema、最小权限/membership、`RESTRICT` downgrade、Docker fixture、路径 guard 和 pip constraints 真源均达到可执行、可验收的计划粒度。但上述 bootstrap 权限前提会使要求的 audit role DDL 在常规部署身份下确定失败；修订并复审该 H 项后，Slice 1.1 才可进入实现 gate。
