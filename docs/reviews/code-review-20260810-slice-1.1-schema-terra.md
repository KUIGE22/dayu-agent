# Code Review — Slice 1.1 Platform Schema Implementation（Terra）

## Scope

- Mode: current changes（Slice 1.1 未提交改动）
- Branch: `codex/investment-platform`
- Base: `main` 的 merge-base `7c97c1f4e28af17d1a6d5c1b92706d793d9c7180`；当前 `HEAD` 为 doc-owner accepted commit `7209eac`。
- Review clock: 2026-08-10 12:16 CST（本机系统时钟）。
- Output file: `docs/reviews/code-review-20260810-slice-1.1-schema-terra.md`
- Included scope: 当前所有 Slice 1.1 tracked diff 与新文件：依赖/constraints、Alembic、`dayu.investment.storage`、architecture guard、unit/PG16 integration 测试、三份 README、DeepSeek implementation artifact，以及审查期间出现的 MiM review artifact。
- Excluded scope: Slice 1.2+、live data/model/broker、外发与既有 PG17/pgvector stack；未编辑、未 stage、未 commit/push/PR。
- Parallel review coverage: 无；主 reviewer 完整走读 `env.py → 0001 migration → ORM → fixture → integration tests` 执行链路。

## Findings

### 001-未修复-中-audit-bypass 测试以直接 BYPASSRLS 绕过受控 membership/SET ROLE 路径

- **入口/函数**: `_make_audit_operator_login()` 与 `test_audit_operator_can_read_across_tenants_but_no_dml()`。
- **文件(行号)**: `tests/integration/investment/test_platform_migrations_postgres.py:221-235, 927-967`；`tests/integration/investment/conftest.py:483-522`。
- **输入场景**: 已 upgrade 的数据库，audit operator 以计划规定的 audit group membership 访问跨 tenant 数据。
- **实际分支**: `_make_audit_operator_login()` 调用 `create_temporary_login(..., member_of=dayu_platform_audit, bypassrls=True)`；helper 因此执行 `CREATE ROLE ... LOGIN BYPASSRLS ... IN ROLE dayu_platform_audit`。测试连接后直接 `SELECT`，从未 `SET ROLE dayu_platform_audit`。
- **预期行为**: S11-CTRL-04 的最小权限契约是 audit group 持有 `BYPASSRLS`，受审计 operator 通过 audit membership + `SET ROLE` 使用该边界，且不具 ADMIN option；integration 应证明该真实路径及 membership matrix。
- **实际行为**: 跨租户读取由 temporary LOGIN 自身的 `BYPASSRLS` 属性证明，而非 group-role/`SET ROLE` 契约。当前只有 app 的 `SET ROLE audit` 拒绝测试（同文件:1058-1089），没有 audit operator 的正向 `SET ROLE`，也没有 `pg_auth_members` 的 `INHERIT/SET/ADMIN` 断言。
- **直接证据**: integration 文件虽在顶部宣称使用 `pg_auth_members`（:12-16），实际不存在该 catalog 查询；`rg` 只命中说明文字。S11-CTRL-04 要求的 `pg_auth_members` exact matrix 因此未由该 lane 验证。
- **影响**: audit group membership、`SET ROLE` option 或无 ADMIN 约束回归时，测试仍会因 login 的直接 `BYPASSRLS` 而通过；这会将应收敛在 group role 的高权限扩散到每个 operator LOGIN，破坏最小权限审计边界。
- **建议改法和验证点**: 建立 `LOGIN NOBYPASSRLS` 的 audit operator，只授予 audit group membership（显式 `INHERIT/SET/ADMIN` 选项）；先证明未 `SET ROLE` 时不能跨 tenant 读，再 `SET ROLE dayu_platform_audit` 验证跨 tenant `SELECT` 和全部 DML/DDL 拒绝，并通过 `pg_auth_members` 精确断言 app/audit 两条 membership 的 option matrix 与无 ADMIN。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。

### 002-未修复-中-13 表 ORM/migration exact 契约没有独立且完整的 catalog 验收

- **入口/函数**: `TestSchemaExact.test_schema_exact_columns()` 与 schema/RBAC integration assertions。
- **文件(行号)**: `tests/integration/investment/test_platform_migrations_postgres.py:706-812, 974-1055`；对照 `dayu/investment/storage/models_identity.py`、`models_auth.py` 与 `migrations/versions/0001_platform_foundation.py`。
- **输入场景**: 任何后续改动使手写 Alembic DDL 与 ORM metadata 在未覆盖表的列、FK、unique/check/index/default/version 或权限/默认权限上发生漂移。
- **实际分支**: integration 只对 `organizations`、`source_sync_runs`、`api_tokens` 三张表列清单做 `information_schema` exact 比较；`pg_constraint` 只检查所有 FK 的 `confdeltype='r'`；app grant 仅检查部分 privilege 位。
- **预期行为**: S11-CTRL-03/04 要求 integration 通过 `information_schema`、`pg_constraint`、`pg_indexes` 独立精确断言全部 13 表的列/类型/nullable、FK/unique/check/index，并验证 role membership、PUBLIC/default privileges；不能从 ORM metadata 自比。implementation artifact 同样声称已用这些 catalogs 做 exact 验收。
- **实际行为**: integration 文件没有 `pg_indexes` 查询，也没有 `pg_auth_members`、default ACL/PUBLIC 查询；其余 10 表没有完整列清单断言，unique/check/index 的名字和定义亦未与 migration 的独立期望逐项比较。unit lane 只编译 ORM 自身，不能发现 ORM 与手写 migration 双真源之间的差异。
- **直接证据**: `test_schema_exact_columns` 的断言止于三张表（:777-811）；`test_foreign_keys_use_restrict` 只读取 `confdeltype`（:728-737）；文件中 `pg_indexes`/`pg_auth_members` 仅出现于模块 docstring（:12-14），无执行查询。MiM review artifact 和 DeepSeek artifact 的“`pg_indexes`/`pg_auth_members` exact”结论与此不符。
- **影响**: 关键约束（例如 partial unique index、composite FK、check/default、role membership 或 future-object PUBLIC 默认权限）被误改、漏建或与 ORM 不一致时，真实 PG16 lane 仍会通过；这直接削弱 Slice 1.1 的 fresh-schema 数据完整性与最小权限验收。
- **建议改法和验证点**: 用不依赖 ORM 的 data-driven expected catalog，覆盖 13 张表全部列（含 default）、每个命名 FK/unique/check/PK、全部索引及 partial predicate、RLS policy 的 command/role/`USING`/`WITH CHECK`、schema/table PUBLIC privilege、default ACL、`pg_auth_members` options；让断言从已 migration 的 PG16 catalogs 获取实际值。保留现有行为测试作为补充而非替代。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。

### 003-未修复-低-fixture 声称的成功/失败 redacted log 收集未执行

- **入口/函数**: `platform_cluster` session fixture 与 `_collect_redacted_logs()`。
- **文件(行号)**: `tests/integration/investment/conftest.py:232-252, 542-560`。
- **输入场景**: PG16 启动、测试或 teardown 失败，需要 bounded/redacted 容器诊断信息。
- **实际分支**: fixture `finally` 仅调用 `_cleanup_cluster(...)`；`_collect_redacted_logs()` 只被定义，仓库内没有调用点。
- **预期行为**: S11-CTRL-06 要求成功/失败均在 `finally` 收集 bounded/redacted logs，然后只按已验证 label/name 清理 owned 资源。
- **实际行为**: label-based cleanup 已执行，但日志既不收集也不以脱敏形式附带到 failure diagnostics；失败时只能得到 Docker/Alembic 的有限错误。
- **直接证据**: `_collect_redacted_logs` 的唯一搜索命中是其定义本身；`platform_cluster` 的 `finally`（:556-560）没有调用它。
- **影响**: 不会触碰 PG17 或泄漏当前 fixture password，但容器启动/迁移失败时缺少计划要求的、可安全诊断的 PostgreSQL logs，增加复现和修复成本。
- **建议改法和验证点**: 在 cluster 句柄可用后，成功和异常的 `finally` 均调用 helper；仅把截断、密码脱敏后的文本接入 pytest failure diagnostics/受控日志，并新增失败路径测试确认 raw password/DSN 不出现。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

### 004-未修复-低-新增 integration helper 使用禁止的 object 宽类型

- **入口/函数**: `query_all()`。
- **文件(行号)**: `tests/integration/investment/conftest.py:648-663`。
- **输入场景**: 所有 integration catalog/privilege assertions 调用该 helper。
- **实际分支**: 返回标注为 `list[tuple[object, ...]]`，将不同 SQL result 值无差别擦除为 `object`。
- **预期行为**: 项目 `AGENTS.md` 编码硬约束禁止 `object`/`Any` 及无法严格类型检查的签名；测试文件同样受该约束。
- **实际行为**: helper 新引入的公开类型签名违反该硬约束；现有 architecture guard 只扫描 production package，因此 pyright 不会把它作为错误拦下。
- **直接证据**: `rg` 在变更范围内唯一命中 `tests/integration/investment/conftest.py:648` 的 `tuple[object, ...]`（JSON SQL 字面量中的 `object` 不属于类型问题）。
- **影响**: catalog assertion 的值类型被静默宽化，违反项目的严格类型 gate，后续误用不易被静态检查发现。
- **建议改法和验证点**: 定义精确的 PostgreSQL test scalar/result TypeAlias（覆盖 `str/int/bool/UUID/None` 等当前实际结果）或按查询结果在各 helper 返回精确行类型；将 integration tests 纳入同一类禁止宽类型静态 guard。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## Validation

| 检查 | 结果 |
| --- | --- |
| `pytest tests/investment -q` | PASS，192 passed |
| `pyright dayu/investment tests/investment tests/integration/investment` | PASS，0 errors / warnings / information |
| `ruff check dayu/investment tests/investment tests/integration/investment` | PASS |
| `git diff --check HEAD` | PASS |
| `pytest tests/integration/investment -q` | PASS，22 passed；按固定 PG16 digest 启动随机、label-owned fixture |
| PG16 fixture cleanup | PASS；测试后按 `dayu-slice11.owner` filter 未发现 container 或 network，既有 PG17 未被操作 |
| Python/直接依赖 | Python 3.11.15；SQLAlchemy 2.0.51、psycopg/psycopg-binary 3.3.4、Alembic 1.18.5 与 min/common constraints 一致 |

## Open Questions

无。

## Residual Risk

- 当前 workspace `.venv` 的 `pip check` 报告既有 Streamlit 与 `packaging`/`pandas`/`pillow` 版本冲突；该冲突不涉及本 Slice 新增的三项 PostgreSQL direct dependencies，且未据此归因于本改动。implementation artifact 声称 clean venv resolution，本轮未创建或改写额外虚拟环境复验。
- 本轮因用户允许的 PG16 integration 拉取并使用了指定 digest；本轮结束时 Slice-owned container/network 为零。该镜像是本机缓存状态变化，不是仓库文件改动。

## Conclusion

**FAIL**。Open H/M/L = **0 / 2 / 2**。

ORM/migration 的人工走读、pre-DDL `rolsuper` admission、RLS DDL、最小 GRANT、无 `CASCADE` downgrade、路径 guard、constraints 与三份 README 未发现新的实现偏差，且聚焦 unit/static/真实隔离 PG16 lane 均通过。但 audit 权限路径和 13 表 exact catalog 验收这两项核心安全/完整性证据尚未被真实测试证明；在修复 001/002 并复审前，不应进入 merge gate。
