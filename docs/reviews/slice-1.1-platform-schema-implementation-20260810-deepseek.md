# Slice 1.1 platform schema implementation artifact

- **Work unit**：Investment Platform Restoration / Slice 1.1
- **Gate**：implementation
- **Approved plan**：`docs/plans/2026-08-10-investment-platform-restoration.md`
  （Slice 1.1，S11-CTRL-01..07，行 394-558）
- **Acceptance**：`docs/reviews/plan-acceptance-20260810-slice-1.1-schema-environment-codex.md`
- **Predecessor accepted commit**：`724b824`；doc-owner erratum `7209eac`
- **Branch**：`codex/investment-platform`
- **Status**：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**
- **Open H/M/L**：`0/0/0`（本 slice 无未分类 residual）

- **Final corrective reviews**：
  - `docs/reviews/code-review-20260810-slice-1.1-schema-final-terra.md`
    （PASS，open `0/0/0`）
  - `docs/reviews/code-review-20260810-slice-1.1-schema-final-mimo-native.md`
    （PASS，open `0/0/0`）

## Scope / Non-goals

只实现 approved plan 的 Slice 1.1 allowlist 与本文档；不启动
plan/review/commit/push/PR；不触碰其它 slice 文件。

- **Allowed files 实际改动**：
  - `pyproject.toml`（新增 3 个 PostgreSQL 依赖）
  - `constraints/min-py311.txt`、`constraints/lock-common-py311.txt`
    （新增 4 个 exact pins）
  - `alembic.ini`（新增，无 DSN）
  - `dayu/investment/storage/__init__.py`、`db.py`、
    `models_identity.py`、`models_auth.py`、`migrations/**`
  - `tests/investment/test_platform_migrations.py`（新增）
  - `tests/investment/test_architecture_boundaries.py`（pure/storage
    分组 guard）
  - `tests/integration/investment/conftest.py`、
    `test_platform_migrations_postgres.py`（新增）
  - `dayu/investment/README.md`（依赖真源与 schema 契约同步）
  - 本文档 `docs/reviews/slice-1.1-platform-schema-implementation-20260810-deepseek.md`
- **Non-goals**：不实现 repository/service/composition/startup 装配
  （Slice 1.2）；不创建任何 fake/SQLite 替代；不启动 scheduler/worker。

## Implemented plan items

### S11-CTRL-01 Dependencies

- `pyproject.toml` 新增 `SQLAlchemy>=2.0.51,<2.1.0`、
  `psycopg[binary]>=3.3.4,<3.4.0`、`alembic>=1.18.5,<1.19.0`。
- `constraints/min-py311.txt` 与 `constraints/lock-common-py311.txt`
  新增 direct exact pins：`SQLAlchemy==2.0.51`、`psycopg==3.3.4`、
  `psycopg-binary==3.3.4`、`alembic==1.18.5`；四个平台 lock 保持字节
  不变（pip resolver 证明无需平台特异 transitive pin）。
- 两条 clean Python 3.11 resolution lane 均成功：
  - `pip install -e ".[test,dev,browser,web]" -c constraints/min-py311.txt`
  - 当前 platform lock（macos-arm64）
- 临时 venv 已验证后删除，不留残留。

### S11-CTRL-02 Architecture boundary

- `tests/investment/test_architecture_boundaries.py` 改为相对路径分组：
  - pure 集合精确为根 `__init__.py`、`domain/**`、`config.py`、
    `composition.py`，使用完整 forbidden set（含 sqlalchemy/psycopg/
    alembic）；
  - infra 集合精确为 `storage/**`，只移除 ORM/驱动依赖，其余上层
    依赖与 escape/docstring guards 不变；
  - 未知新增路径默认按 pure 规则拒绝；
  - 根 `__init__.py` 不 re-export storage/ORM。
- `dayu/investment/README.md` 同步同一依赖真源。

### S11-CTRL-03 Exact schema（13 表）

全部对象位于 `dayu_platform` schema，UUID 调用方提供、无 server
random default，文本业务键非空且无首尾空白，`created_at/updated_at`
为 `TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp()`，
`observed_at/started_at` 调用方提供，`finished_at` 可空，`version`
为 `INTEGER NOT NULL DEFAULT 1 CHECK (version > 0)`；mutable 表带
`updated_at/version`，append-only 表不带。精确列/FK/unique/check/index
逐表在迁移 DDL 与 ORM 双写并保持一致（unit 校验约束名完整编译、integration
用 `information_schema`/`pg_constraint`/`pg_indexes` 精确断言）。

- 13 表：`organizations`（tenant root，RLS on id）、`companies` /
  `securities` / `source_definitions`（公共 reference，无 RLS）、
  `users` / `roles` / `permissions` / `user_roles` /
  `role_permissions` / `api_tokens` / `source_subscriptions` /
  `source_sync_runs` / `source_health_snapshots`（私有）。
- default organization 以固定 UUID `00000000-0000-0000-0000-000000000001`
  幂等创建（slug/display_name=`default`、status=`active`、version=1）。
- 修正两处实施中发现的问题：CheckConstraint 显式名与 naming convention
  叠加产生超 63 字符约束名（改语义短名，convention 自动补
  `ck_<table>_` 前缀）；`fk_source_health_snapshots_tenant_*` 超长
  FK 名缩短并与 ORM/迁移 DDL 同步。

### S11-CTRL-04 RLS/roles

- 私有表每张 `ENABLE + FORCE ROW LEVEL SECURITY`，唯一
  `tenant_isolation` policy `FOR ALL TO dayu_platform_app`，tenant
  表达式 `nullif(current_setting('app.tenant_id', true), '')::uuid`，
  `organizations` 比较 `id`，其余比较 `tenant_id`；未设置/空/错误
  tenant default deny。
- group role：`dayu_platform_app`（NOLOGIN NOSUPERUSER NOCREATEDB
  NOCREATEROLE NOREPLICATION NOBYPASSRLS）、`dayu_platform_audit`
  （同上但 BYPASSRLS）。
- 权限矩阵：先 `REVOKE ALL FROM PUBLIC`；bootstrap owns
  schema/tables/policies；app schema 仅 `USAGE`，公共 reference
  `SELECT,INSERT,UPDATE`，`organizations/users/roles/permissions/
  api_tokens/source_subscriptions` `SELECT,INSERT,UPDATE`，
  join 表 `user_roles/role_permissions` `SELECT,INSERT,DELETE`，
  append-only `source_sync_runs/source_health_snapshots`
  `SELECT,INSERT`；无 `TRUNCATE/REFERENCES/TRIGGER`、schema 无
  `CREATE`。audit schema `USAGE`、13 表 `SELECT` 只读。
  schema default privileges 只显式 revoke PUBLIC，不 blanket grant。
- 受控 `SET ROLE`：app 不是 audit member，`SET ROLE audit` 被拒；
  audit-operator（BYPASSRLS + audit membership）可跨租户只读。

### S11-CTRL-05 Migration/runtime

- `db.py`：`create_platform_engine`（`echo=False`）、
  `create_platform_session_factory`、确定性 `NAMING_CONVENTION`、
  平台 schema/role/tenant/default-org 常量、
  `PlatformMigrationAdmissionError`；**无任何 `create_all()`**。
- `alembic.ini` 不保存 DSN；`migrations/env.py` 只从
  `DAYU_PLATFORM_POSTGRES_DSN` 读取 bootstrap DSN，关闭 SQL 参数/secret
  回显，不注册 `sqlalchemy.engine` logger；在任何 DDL 前以 bootstrap
  connection 查询 `pg_roles` 要求 `rolsuper IS TRUE`，否则抛稳定
  `PlatformMigrationAdmissionError`，事务中零 side effect。
- 单次 transactional migration 创建 app/audit group role、
  schema/13 表/policy/grant/default organization；同名 role/schema
  预先存在 fail closed（DO block），不接管未知 owner；Alembic version
  table 留在 bootstrap-owned 默认 schema；任一步失败整次 rollback。
- downgrade 在任何破坏性 DDL 前执行**显式 admission**
  （`_downgrade_admission`）：查询 `pg_auth_members`（app/audit 外部
  member）、`pg_stat_activity`（使用 app/audit 或其 member 的非当前
  活跃 session）、`pg_shdepend`（`dayu_platform` schema 之外的
  外部对象依赖），任一命中稳定 fail closed；通过后按
  policy -> 13 表 -> schema `RESTRICT` -> app/audit group role 精确
  回滚，禁止 CASCADE，不删除 bootstrap role/database/Alembic version
  table。

### S11-CTRL-06 PostgreSQL 16 integration

- 拉取官方 `postgres:16.14-bookworm` 并记录本机（arm64/linux）
  resolved immutable digest：
  `sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8`
  （测试按 digest 启动，不依赖 tag）。
- `conftest.py`：session fixture 用已有 Docker CLI 启动随机
  container/network/database/users，绑定 `127.0.0.1` 随机端口，唯一
  owner label `dayu-slice11.owner`，`docker run --detach --rm`，bounded
  `pg_isready` 后产出 bootstrap DSN；`finally` 收集 bounded/redacted
  日志后只按已验证 label 删除 owned container/network；不使用 broad
  glob/prune/compose down；不连接/停止/修改既有 PG17 stack（已验证
  未被触碰）；提供 Alembic Config/bootstrap engine/application DSN、
  temporary-login 与显式 helper；只经 Alembic upgrade 建 schema。
- 修复实施中发现的问题：DSN 需显式 `+psycopg` 方言前缀；docker
  inspect 的 label 为 JSON 形式，cleanup 匹配改为
  `"dayu-slice11.owner": "<label>"` 片段；测试结束后零资源残留。

### S11-CTRL-07 Unit/integration split

- `tests/investment/test_platform_migrations.py`（unit，19 tests，无
  数据库）：13 表 metadata、naming convention、列类型/nullable、
  `version > 0`、append-only 契约、FK RESTRICT、禁止 `create_all`
  （AST 扫描 storage 与迁移版本目录）、engine/session factory。
- `tests/integration/investment/test_platform_migrations_postgres.py`
  （integration，22 tests，真实 PG16）：
  - `upgrade -> downgrade -> upgrade`、default organization 种子、
    非 superuser `CREATEROLE NOBYPASSRLS` admission 拒绝且零对象、
    同名 role fail-closed 零对象；
  - **downgrade 三类 fail-closed**（Controller correction 要求）：
    external member、active session、external dependency——均断言
    13 表/schema/group roles/default seed 原样保留，清理后正常
    downgrade 成功；
  - schema exact：13 表集合、私有表 non-null tenant、公共 reference
    无 tenant、group role 属性、RLS enable+force、tenant_isolation
    policy、FK RESTRICT、关键表列/类型/nullable（information_schema）；
  - RLS 行为：unset default deny、`SET LOCAL` same-tenant allow 且
    提交后不泄漏、cross-tenant reject、audit-operator 跨租户只读
    但 DML 被拒；
  - GRANT 矩阵：app schema USAGE/无 CREATE、各表 SELECT/INSERT/UPDATE/
    DELETE 精确、`SET ROLE audit` 拒绝、audit 全表 SELECT-only、
    app 在 schema 内 CREATE 被拒。
- 测试数据/credential 仅限临时 integration 环境；`pg_isready` 超时、
  失败诊断不打印 DSN/password。

## Validation results

```bash
# unit lane（含 minPy311 clean venv 复跑）
pytest tests/investment -q                                   # 192 passed
pytest tests/investment --cov=dayu.investment --cov-report=term-missing
#   db.py 100%；models_identity/models_auth/domain/config/composition 100%
pytest tests/integration/investment -q --cov=dayu/investment/storage \
  --cov-report=term-missing                                   # 22 passed
#   路径式 cov：env.py 92%、0001_platform_foundation.py 99%、总 98%
#   （unit lane 包名过滤下 migration 显示 0% 属 alembic 动态加载模块
#     不匹配包名；真实覆盖以路径式 integration cov 为准）
pytest tests/investment tests/integration/investment -q       # 214 passed

# 全仓 Python 3.11 unit lane（not integration and not slow and not e2e）
#  首次（有 SERPER_API_KEY 污染环境）7572 passed, 1 failed
#  唯一失败 test_search_with_serper_requires_api_key 为本机代理 127.0.0.1:7897
#  不可达的环境问题；改动前基线（stash）同样失败，判定与本 slice 无关。
#  Controller 指定的最终 clean lane（env -u SERPER_API_KEY）：
pytest -q --timeout=60 -m "not integration and not slow and not e2e"
#  7573 passed, 5 skipped, 31 deselected —— 零失败
#  （unset SERPER_API_KEY 后该 serper 测试走 mock 回退分支通过，
#   证实此前失败是污染环境产物，不是代码回归）

# 类型/风格/差异
pyright dayu/investment tests/investment tests/integration/investment  # 0 errors
ruff check dayu/investment tests/investment tests/integration/investment  # All checks passed
git diff --check                                                    # clean
```

## Docs decision

- 更新 `dayu/investment/README.md`（allowlist 内）：依赖方向按 pure/
  infra 分组、storage 模块 owner、schema/RLS/GRANT/migration 契约、
  开发命令含 integration lane。
- 更新 `dayu/README.md` §3.9（S11-CTRL-08 accepted 增量，allowlist
  已纳入）：investment owner 图为 pure `domain/config/composition` +
  infra `storage`，只对 pure 层禁 ORM，storage 只依赖 pure +
  SQLAlchemy/psycopg/Alembic 且不向上暴露 ORM row；登记 Alembic /
  13 表 / RLS 阅读顺序与 path-based guard 规则。
- 更新 `tests/README.md`（S11-CTRL-08 accepted 增量，allowlist 已
  纳入）：architecture guard 更新为 pure/storage 相对路径规则；
  登记 `tests/investment/test_platform_migrations.py` unit lane 与
  `tests/integration/investment/test_platform_migrations_postgres.py`
  真实 PG16 `integration` lane；明确禁止 SQLite/fake 替代、Docker
  fixture 必须按 owner label 清理、每 lifecycle 独立随机 database、
  `SET LOCAL app.tenant_id` 不泄漏断言。
- 根 `README.md` 无触发项（用户手册职责外）。
- 未改写其它 package/test 历史；未把 future slice、live data、模型或
  broker 能力标为已实现。

## Residual risks / owners

| 风险 | 分类 | Owner / destination |
| --- | --- | --- |
| `dayu/README.md` §3.9 文案过时（不导入 ORM 表述） | **CLOSED**（S11-CTRL-08 erratum accepted，commit `7209eac`） | 本 slice 已同步 |
| `tests/README.md` 未登记 unit/integration migration lane | **CLOSED**（S11-CTRL-08 erratum accepted） | 本 slice 已同步 |
| `test_search_with_serper_requires_api_key` 本机代理不可达失败 | environment（改动前基线同样失败） | 非本 slice；本机网络恢复后全绿 |
| migration 文件在 unit lane 包名过滤下 cov 显示 0% | covered（路径式 integration cov 98%） | 本 slice 已闭环，CI 用路径式或 integration cov |
| bootstrap credential 生命周期（迁移结束 unset） | covered by later slice（Slice 1.2 composition 负责运行时 DSN 隔离） | Slice 1.2 |
| 应用 LOGIN 创建/轮换流程 | covered by later slice（Slice 7.1 auth） | Slice 7.1 |

## Completion / stop status

- **Completed**：依赖 resolution 与锁定；官方 PG16.14 digest 记录；
  storage 包与 13 表 ORM；transactional migration（roles/RLS/GRANT/
  seed/admission/downgrade admission）；pure/storage architecture
  guard；unit lane 与真实 PG16 integration lane；pyright/Ruff/
  coverage/diff-check；三份 README 同步（`dayu/investment/README.md`、
  `dayu/README.md` §3.9、`tests/README.md`，含 S11-CTRL-08 增量）；
  最终 clean full Python 3.11 lane（`env -u SERPER_API_KEY`）执行并
  如实分类。
- **Code-review fix**：Terra 001–004 全部修复并经双路 re-review 通过
  （见 `slice-1.1-platform-schema-review-fix-20260810-deepseek.md`）；
  corrective round2（Terra R1-001..003）修复见
  `slice-1.1-platform-schema-corrective-review-fix-20260810-deepseek.md`；
  implementation artifact 状态更新为 CORRECTIVE FIX APPLIED。
- **Not run**：无真实 broker/live data/付费模型/外发通知；未触碰
  既有 PG17 stack；未 push/commit/PR。
- **Status**：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**。
