# Plan Corrective Re-review — Slice 1.1 Terra Final 001 Closure

## Scope

- Reviewed target：`docs/plans/2026-08-10-investment-platform-restoration.md` Slice 1.1 最新版 S11-CTRL-04/05 与 `docs/reviews/plan-fix-20260810-slice-1.1-schema-environment-codex.md`
- Reviewer：MiM Native
- Review clock：`2026-08-10`（本机系统时钟）
- Output file：`docs/reviews/plan-corrective-rereview-20260810-slice-1.1-schema-environment-mimo-native.md`
- Focus：Terra final 001 的 superuser/bootstrap admission/runtime 隔离独立验证；先前 PASS 项回归检查

## Terra Final 001 — Bootstrap SUPERUSER / BYPASSRLS Admission

### 先前问题

Terra final 001（HIGH）指出：计划要求 migration 创建 `dayu_platform_audit NOLOGIN ... BYPASSRLS`，但未规定 bootstrap principal 必须拥有 `SUPERUSER` 或 `BYPASSRLS` 属性。PostgreSQL 规定只有 superuser 或自身具有 `BYPASSRLS` 的角色才能指定 `BYPASSRLS` 创建角色（见 [`CREATE ROLE`](https://www.postgresql.org/docs/current/sql-createrole.html)）。单有 `CREATEROLE` 不足以执行该 DDL。

### 修订内容验证

**S11-CTRL-04（第 461-465 行）**：
> "bootstrap principal 是 migration 外部提供的短生命周期 PostgreSQL `SUPERUSER LOGIN`/owner，不由 migration 创建或删除，只用于初始 upgrade/downgrade 创建 BYPASSRLS group role 与 schema objects。该 credential 不得注入或继承到 API、Worker、Scheduler、UI 或 application composition，迁移进程结束立即 unset/销毁 secret 引用。"

✅ 明确指定 bootstrap principal 为 `SUPERUSER LOGIN`，解决 PostgreSQL 权限前提。

**S11-CTRL-05（第 494-498 行）**：
> "Alembic env 在构造 metadata、创建 role/schema/table 或执行任何其它 DDL 前，先以 bootstrap connection 查询 `pg_roles` 并要求 `current_user` 的 `rolsuper IS TRUE`；只有 `CREATEROLE`、`BYPASSRLS` membership、object ownership 或同名预置 role 均不能替代。预检不通过抛稳定、无 DSN/credential 的 `PlatformMigrationAdmissionError`，事务中零 schema/table/role/seed/grant side effect。"

✅ 新增 DDL 前负向预检：`rolsuper IS TRUE`，不满足时 fail-closed，零副作用。

### 闭合结论

Terra final 001 **CLOSED** ✅。计划同时指定：
1. Bootstrap 能力（`SUPERUSER LOGIN`）
2. 仅限 migration 的短生命周期
3. DDL 前 `rolsuper IS TRUE` 负向预检
4. 预检失败的 stable error（`PlatformMigrationAdmissionError`）
5. 零 side effect 保证
6. 运行时 DSN 不得复用 bootstrap DSN

### Runtime 隔离验证

- Bootstrap DSN 仅用于 migration（S11-CTRL-05 第 492-493 行）
- 运行时 DSN 对应 application LOGIN（S11-CTRL-05 第 485 行）
- "该 credential 不得注入或继承到 API、Worker、Scheduler、UI 或 application composition"（S11-CTRL-04 第 464 行）
- "迁移进程结束立即 unset/销毁 secret 引用"（S11-CTRL-04 第 465 行）

✅ Runtime 隔离完整。

## Prior PASS Items — Regression Check

| 控制项 | 先前状态 | 当前状态 | 回归 | 闭合依据 |
|--------|----------|----------|------|----------|
| S11-CTRL-01 依赖/locks | ✅ PASS | ✅ PASS | 无回归 | 第 388-406 行未变：pip constraints、exact pins、clean venv testing、禁止 uv.lock |
| S11-CTRL-02 Architecture guard | ✅ PASS | ✅ PASS | 无回归 | 第 407-419 行未变：路径分组、pure/infra 集合、re-export ban |
| S11-CTRL-03 Exact schema | ✅ PASS | ✅ PASS | 无回归 | 第 420-451 行未变：12 张表完整列级定义、information_schema 断言 |
| S11-CTRL-04 RLS/roles | ✅ PASS | ✅ PASS | 无回归 | 第 452-489 行新增 bootstrap SUPERUSER 规格（lines 461-465），原有 role 属性/GRANT 矩阵/membership 约束未变 |
| S11-CTRL-05 Migration/runtime | ✅ PASS | ✅ PASS | 无回归 | 第 490-508 行新增 `rolsuper IS TRUE` 预检（lines 494-498），原有 transactional migration/downgrade 顺序/禁止 create_all 未变 |
| S11-CTRL-06 PG16 integration | ✅ PASS | ✅ PASS | 无回归 | 第 509-522 行未变：Docker CLI、random port/network、digest pinning、finally cleanup |
| S11-CTRL-07 Unit/integration split | ✅ PASS | ✅ PASS | 无回归 | 第 523+ 行未变：文件/marker 分离、integration 场景、禁止 SQLite/fake |

## Adversarial Check — Bootstrap Admission Edge Cases

| 反例 | 预期 | plan 覆盖 | 结论 |
|------|------|-----------|------|
| bootstrap 无 SUPERUSER，只有 CREATEROLE | DDL 失败 | `rolsuper IS TRUE` 预检 + `PlatformMigrationAdmissionError` ✅ | 已覆盖 |
| bootstrap 无 SUPERUSER，只有 BYPASSRLS membership | DDL 失败 | "只有 `CREATEROLE`、`BYPASSRLS` membership、object ownership 或同名预置 role 均不能替代" ✅ | 已覆盖 |
| bootstrap 无 SUPERUSER，audit role 已预置 | fail closed | "若同名 role/schema 预先存在则 fail closed，不接管未知 owner" ✅ | 已覆盖 |
| 预检失败后事务有 side effect | 数据污染 | "事务中零 schema/table/role/seed/grant side effect" ✅ | 已覆盖 |
| bootstrap DSN 泄漏到运行时 | 权限提升 | "该 credential 不得注入或继承到 API/Worker/Scheduler/UI/composition" + "迁移进程结束立即 unset/销毁" ✅ | 已覆盖 |
| 预检错误消息泄漏 DSN | 安全风险 | "稳定、无 DSN/credential 的 `PlatformMigrationAdmissionError`" ✅ | 已覆盖 |

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| Terra final 001 bootstrap SUPERUSER | ✅ CLOSED — 第 462 行指定 `SUPERUSER LOGIN` |
| Terra final 001 DDL 前预检 | ✅ CLOSED — 第 494-498 行 `rolsuper IS TRUE` + fail-closed |
| Terra final 001 runtime 隔离 | ✅ CLOSED — 第 464-465 行禁止 bootstrap DSN 继承 + 即时销毁 |
| S11-CTRL-01 无回归 | ✅ PASS |
| S11-CTRL-02 无回归 | ✅ PASS |
| S11-CTRL-03 无回归 | ✅ PASS |
| S11-CTRL-04 无回归 | ✅ PASS |
| S11-CTRL-05 无回归 | ✅ PASS |
| S11-CTRL-06 无回归 | ✅ PASS |
| S11-CTRL-07 无回归 | ✅ PASS |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `rolsuper IS TRUE` 预检的实际执行依赖 PostgreSQL 16 的 `pg_roles` 系统目录行为；计划已正确要求在 erratum accepted 后用真实 PG16 integration lane 复证。
- Bootstrap SUPERUSER 生命周期的"即时 unset/销毁 secret 引用"实现细节由 implementation agent 在 integration fixture 中负责；计划已指定约束（短生命周期、不得继承到运行时）。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。

Terra final 001（bootstrap SUPERUSER / BYPASSRLS admission）已闭合：计划明确指定 bootstrap principal 为 `SUPERUSER LOGIN`，DDL 前 `rolsuper IS TRUE` 负向预检，预检失败零副作用，运行时 DSN 不得复用 bootstrap credential。先前 S11-CTRL-01..07 全部 PASS 项无回归。全部 10 项验证通过，6 轮反例挑战无新增问题。Slice 1.1 erratum 可进入 accepted plan commit。
