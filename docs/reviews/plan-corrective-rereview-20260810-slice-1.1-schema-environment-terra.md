# Plan Corrective Re-Review — Slice 1.1 Schema / Environment（Terra）

## 审查范围

- 审查时间：2026-08-10 11:09 CST（本机系统时钟）。
- 只读审查：
  - `docs/plans/2026-08-10-investment-platform-restoration.md` 的 Slice 1.1 最新 S11-CTRL-04/05；
  - `docs/reviews/plan-fix-20260810-slice-1.1-schema-environment-codex.md`。
- 本轮只验证 Terra final 001 corrective closure 及既有已闭合项目是否回归；未修改 plan、代码、测试、依赖、镜像或运行环境。

## 已验证的前提与证据

| 验证项 | 结论 | 直接证据 |
| --- | --- | --- |
| 一次性 superuser bootstrap | 通过 | S11-CTRL-04 将 bootstrap principal 固定为 migration 外部提供、短生命周期的 PostgreSQL `SUPERUSER LOGIN`/owner，只用于初始 upgrade/downgrade 创建 audit `BYPASSRLS` group role 与 schema objects，且不由 migration 创建或删除。 |
| DDL 前 `rolsuper` admission | 通过 | S11-CTRL-05 要求 Alembic 在构造 metadata、创建 role/schema/table 或任何其它 DDL 前，从 `pg_roles` 检查 `current_user.rolsuper IS TRUE`；`CREATEROLE`、`BYPASSRLS` membership、对象 owner、预置同名 role 都不能替代。失败抛不含 DSN/credential 的稳定 `PlatformMigrationAdmissionError`。 |
| limited `CREATEROLE` 负例零对象 | 通过 | S11-CTRL-05 将 preflight 失败定义为事务内零 schema/table/role/seed/grant side effect；Slice validation 进一步要求非 superuser `LOGIN CREATEROLE NOBYPASSRLS` 在首个 DDL 前被拒绝，并精确断言 schema、table、group roles、seed 均不存在。 |
| runtime DSN 隔离 | 通过 | S11-CTRL-04 明定 bootstrap credential 不得注入或继承 API、Worker、Scheduler、UI 或 application composition，迁移进程结束立即 unset/销毁 secret 引用；migration 使用 bootstrap DSN，运行时仅对应 application LOGIN。S11-CTRL-05 同时规定 `alembic.ini` 不保存 DSN。 |

## 原已闭合项目的回归检查

| 原项目 | 回归结论 | 保持的契约 |
| --- | --- | --- |
| Terra 001：逐表 schema 可实施性 | 无回归 | S11-CTRL-03 仍固定 13 表逐列、键、约束、索引与独立 catalog 验收。 |
| Terra 002：最小权限与 membership | 无回归 | app/audit role 属性、禁止 app audit membership/`SET ROLE`、表级权限矩阵、FORCE RLS 与正反向集成矩阵保持不变。 |
| MiM 001：pure/storage path guard | 无回归 | S11-CTRL-02 仍以 `_INVESTMENT_SRC` 相对路径区分 pure 与 `storage/**`，未知路径默认拒绝。 |
| MiM 002：Docker fixture 生命周期 | 无回归 | S11-CTRL-06 仍要求固定官方 PG16、Slice-owned 随机资源、有限等待与按验证标签精确 cleanup。 |
| MiM 003：pip constraints 真源 | 无回归 | S11-CTRL-01 仍以 pip constraints 为安装/resolver 真源，明确 `uv.lock` 非真源。 |
| MiM 004：no-`CASCADE` downgrade | 无回归 | S11-CTRL-05 仍以 policy/grant → 表/seed → schema `RESTRICT` → roles 的顺序回滚，禁止 `CASCADE`，外部 dependency/member/session 导致整次 rollback。 |

## Findings

无。Terra final 001 的根因已由明确 bootstrap 能力、DDL 前 admission、负向零副作用测试和运行时 DSN 隔离共同闭合；未发现该纠正对既有最小权限、RLS、schema、rollback、fixture 或 resolver 契约造成回归。

## Open Questions

无。

## Residual Risks

- 当前结论限于计划可实施性；真正实现后仍须按计划在官方 PostgreSQL 16 integration lane 证明 admission、rollback、权限矩阵与 DSN 不回显。
- 该验证属于 Slice 1.1 implementation gate，不构成当前 plan blocker。

## 结论

**PASS**（open H/M/L：**0 / 0 / 0**）。

Slice 1.1 S11-CTRL-04/05 现已闭合 Terra final 001，且原有闭合项无回归，可解除该 corrective plan re-review 阻塞并进入后续既定 implementation gate。
