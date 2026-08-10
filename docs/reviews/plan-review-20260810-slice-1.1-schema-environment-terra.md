# Slice 1.1 Schema / Environment Erratum Plan Review

## Scope

- **Review clock**：2026-08-10 10:57:42 CST（本机系统时钟）
- **Reviewed target**：`docs/plans/2026-08-10-investment-platform-restoration.md` 的 Slice 1.1 erratum（第 368–444 行）与 `docs/reviews/plan-fix-20260810-slice-1.1-schema-environment-codex.md`。
- **Mode**：只读 adversarial plan review；未修改 plan、代码、测试、依赖、容器或远端状态。
- **Focus**：S11-CTRL-01..07：依赖/locks、pure-vs-storage guard、schema/tenant、RLS/roles、Alembic rollback、官方 PG16.14 隔离容器、unit/integration split。
- **Excluded**：Slice 1.2 及后续实现细节、实际依赖安装、镜像拉取和 PostgreSQL 运行验证；这些均被目标计划正确地置于 erratum accepted 之后。

## Assumptions Tested

| 控制项 | 审查结论 | 直接依据 |
| --- | --- | --- |
| S11-CTRL-01 依赖/locks | 通过 | 计划把 `constraints/**` 纳入 allowlist，并同时要求 minimum pins、common lock 与平台 include lock 重解；当前 CI 的 locked install 统一消费这些 constraints。PyPI 可确认 SQLAlchemy 2.0.51、psycopg 3.3.4、Alembic 1.18.5 均存在并覆盖 Python 3.11：[SQLAlchemy](https://pypi.org/project/SQLAlchemy/)、[psycopg](https://pypi.org/project/psycopg/)、[Alembic](https://pypi.org/project/alembic/)。 |
| S11-CTRL-02 pure-vs-storage guard | 通过 | 当前 `tests/investment/test_architecture_boundaries.py:64-75,91-110,284-301` 的确递归扫描整个 package 并禁 SQLAlchemy；计划明确改为按 owner 分组，pure layer 仍禁 infra，storage 可依赖 ORM 但禁上层。 |
| S11-CTRL-03 exact schema/tenant | 未通过 | 见 finding 001。 |
| S11-CTRL-04 RLS/roles | 未通过 | 见 finding 002。 |
| S11-CTRL-05 Alembic rollback | 通过 | `alembic.ini` 无 DSN、bootstrap DSN、单 migration transaction、失败 rollback、precise downgrade、禁止 `create_all()` 与 integration rollback 验证均已有明确 owner。 |
| S11-CTRL-06 PG16.14 隔离 | 通过 | 固定 `postgres:16.14-bookworm`、host-architecture digest、随机 Slice-owned resource、loopback random port、既有 PG17 禁触碰、失败脱敏 cleanup 均可执行；官方镜像 tag 当前存在：[PostgreSQL Official Image](https://hub.docker.com/_/postgres/tags?name=bookworm&page=1)。 |
| S11-CTRL-07 unit/integration split | 通过 | unit 与真实 PG16 integration 的文件、marker、必测场景明确；现有 CI 已有 `integration and not e2e` 独立 lane，计划未错误要求 SQLite/fake 证明 RLS。 |

## Findings

### 001-未修复-高-S11-CTRL-03 的“exact schema”只固定表清单，无法生成或验收 migration

- **位置**: Slice 1.1 的 S11-CTRL-03（计划第 395–403 行）、S11-CTRL-07（第 429–435 行）及 Slice 1.2 allowlist（第 446–451 行）。
- **问题类型**: 不可直接实施 / 契约缺失。
- **当前写法**: S11-CTRL-03 精确列出 3 张 public reference、`organizations` 与 9 张 private table，且规定 tenant FK、default organization 固定 UUID/slug；S11-CTRL-07 又要求真实 PostgreSQL lane 验收“schema exact”。
- **反例/失败场景**: 实现 Agent 必须在 1.1 为 `companies`、`securities`、`users`、`roles`、`permissions`、source 表等自行发明主键、业务键、FK、唯一约束、nullable、时间/version 列和检查约束。随后 Slice 1.2 需要验证 unique ticker/security、source subscription、optimistic conflict 与 public-reference/private-projection，但其 allowlist 不包含 `models_identity.py`、`models_auth.py` 或 migration，无法在发现缺列/错误约束后在所属 slice 修正。
- **为什么有问题**: 表名、tenant_id 与一个 seed 不是可验证的 exact schema。计划其他位置也未为上述表定义列级 contract；全文检索每个表名只命中表清单/后续 endpoint，未给出列、键或约束。这样 S11-CTRL-07 的 `schema exact` 测试只能复述实现本身，不能证明 plan 真源，且会把 schema 设计重新下放给 1.1 实现者。
- **直接证据**: 计划第 395–403 行仅出现 table inventory、tenant_id 与 default organization；第 429–435 行要求 schema exact；第 448–451 行要求 Slice 1.2 验证 unique ticker/security 和 projection，但其 allowlist 排除了 1.1 的 models/migration 文件。
- **影响**: 实施 Agent 可能生成任意且无法回滚到计划真源的 first schema；1.2 才暴露的约束缺口会迫使越过 allowlist 修改已接受 migration，或把不可逆 schema debt 推给后续 slice。
- **建议改法和验证点**: 在 S11-CTRL-03 增加逐表 column contract：主键类型、每个 tenant/public FK、自然键/unique/index、nullable/default、审计或 optimistic-version 字段、`source_health` 状态与必要 check；同时列出每个 RLS policy 的表/命令适用范围。明确哪些列由 1.1 初始化，后续 slice 只能新增自己 owner 的表/列并拥有对应 migration allowlist。integration 以 `information_schema` / `pg_constraint` / `pg_indexes` 精确断言该清单，且加入 Slice 1.2 所需 ticker/security/projection 负例。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

### 002-未修复-中-S11-CTRL-04 缺少 application/audit 对象权限与成员资格的精确矩阵

- **位置**: Slice 1.1 的 S11-CTRL-04（计划第 404–413 行）与 validation（第 440–443 行）。
- **问题类型**: 契约缺失 / 最佳实践偏离。
- **当前写法**: 计划定义 bootstrap、application、`dayu_platform_audit` 三类角色属性，要求 application 不得 BYPASSRLS/DDL、audit 为 `NOLOGIN BYPASSRLS`，并声称要验证 application same-tenant allow 与 audit bounded read bypass。
- **反例/失败场景**: 若只实现角色属性与 RLS，application 和 audit 均没有对 schema/table 的 `USAGE` / `SELECT` 等对象权限，两个“allow/read bypass”验证无法通过；若实现者为通过测试笼统 `GRANT ALL` 或让 audit 继承宽权限，则 `BYPASSRLS` 会把所有 private rows 暴露给非只读审计路径。计划也未定义“受审计 bootstrap/operator principal”具体角色、其 `SET ROLE` membership option，或禁止 application 的间接 membership。
- **为什么有问题**: RLS 是标准对象授权之上的行过滤，`BYPASSRLS` 只跳过 policy、不自动授予对象访问；因此 role attribute 不能表达“bounded read”。官方 PostgreSQL 文档明确说明 row security 叠加在标准 `GRANT` 权限之上，且 `BYPASSRLS` 角色始终跳过 RLS：[Row Security Policies](https://www.postgresql.org/docs/15/ddl-rowsecurity.html)、[CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html)。没有矩阵，最小权限、测试期望与后续 repository 的写入权限均由实现者临时决定。
- **直接证据**: 计划第 404–413 行只描述 role attribute、RLS expression 与“有界只读 bypass”，没有 `GRANT` / `REVOKE`、schema usage、table command、default privilege 或明确 operator principal；第 432–443 行要求 role grants / same-tenant allow / audit bypass 验证，但未提供其预期授权集合。
- **影响**: integration 可能在无权限处失败，或为通过 happy path 误授 application/audit 过宽权限；审计读取边界和 application 不可越权无法被精确验收。
- **建议改法和验证点**: 固定 role/principal 与 membership matrix（含 `INHERIT` / `SET ROLE` 约束）；逐类表写明 bootstrap owner、application 的 schema/table command grants、audit 的 schema `USAGE` + 只读 table grants、显式 `REVOKE`/default-privilege 策略，以及 audit 不得 DML/DDL、application 不得成为 audit member。真实 PG16 测试用 `has_*_privilege` 与 `pg_auth_members` 断言矩阵，并分别以 application/audit 登录验证同 tenant、cross tenant、DML/DDL 和非授权 `SET ROLE` 都拒绝。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。

## Open Questions

无。两项 finding 均由当前计划文本、后续 slice ownership 与 PostgreSQL 授权语义直接支持，不需要等待外部状态。

## Residual Risk

- S11-CTRL-01 的具体 transitive resolution、S11-CTRL-06 的 digest 与真实 PG16 行为尚未实际执行；计划已正确要求在 erratum accepted 后用 resolver、min-compat/full-suite 与独立 integration lane 复证。修复 001/002 后，这些应保留为 Slice 1.1 implementation gate，而非以当前只读审查替代。
- 不应通过放宽 architecture guard、改用 SQLite/fake、复用现有 PG17 stack 或把 audit/application 权限留给未来 slice 来关闭 findings；这些路径均直接违反现有 stop 条款。

## Conclusion

**FAIL**。Open H/M/L = **1/1/0**。

S11-CTRL-01、02、05、06、07 已达到可实施的计划级闭环；但在补齐 S11-CTRL-03 的列级 exact schema 契约和 S11-CTRL-04 的最小对象权限/成员资格矩阵前，Slice 1.1 仍不满足 code-generation-ready，不能恢复依赖安装、镜像拉取或代码编辑。
