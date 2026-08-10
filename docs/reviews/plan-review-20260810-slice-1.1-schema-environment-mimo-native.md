# Plan Review — Slice 1.1 ORM / Tenant / Auth / Alembic Erratum

## Scope

- Reviewed target：`docs/plans/2026-08-10-investment-platform-restoration.md` Slice 1.1 erratum（§8 Phase 1 Slice 1.1 + S11-CTRL-01..07）
- Fix artifact：`docs/reviews/plan-fix-20260810-slice-1.1-schema-environment-codex.md`
- Reviewer：MiM Native
- Review clock：`2026-08-10`（本机系统时钟）
- Output file：`docs/reviews/plan-review-20260810-slice-1.1-schema-environment-mimo-native.md`
- Focus areas：S11-CTRL-01..07 可实施性、role/RLS 安全、schema/downgrade、lock/min-Py311、PG16 容器隔离、测试真值

## Assumptions Tested

1. Architecture AST guard 可以被正确重构为按 owner 分组，使 `storage/` SQL implementation 允许 SQLAlchemy 而 `domain/` 继续禁止。
2. S11-CTRL-04 的 bootstrap/application/audit 三类 role 设计在 PostgreSQL 16 中可实现且安全。
3. S11-CTRL-05 的 transactional migration + downgrade 策略足够精确，不会触碰非本 slice owner。
4. S11-CTRL-01 的 lock 文件可由 resolver 在 Python 3.11 环境下生成并验证。
5. S11-CTRL-06 的 PG16 容器隔离策略在并发测试和既有 PG17 stack 共存时安全。
6. S11-CTRL-07 的 unit/integration split 足够清晰，implementation agent 不会混淆测试边界。

## Findings

### 001-未修复-中-Architecture AST guard 重构方案未指定，implementation agent 需自行设计分组策略

- **位置**: S11-CTRL-02 + `tests/investment/test_architecture_boundaries.py` 现有实现
- **问题类型**: 不可直接实施 / 切片过粗
- **当前写法**: plan 声称 "architecture AST guard 必须按 owner 分组执行该规则，不能继续递归地把所有 storage infra import 判为违规"，但未指定分组策略的具体实现方式。
- **反例/失败场景**: 当前 `_iter_investment_files()` 使用 `rglob("*.py")` 递归扫描 `dayu/investment/` 下全部 Python 文件；`_FORBIDDEN_IMPORT_PREFIXES` 包含 `"sqlalchemy"`。Slice 1.1 新增 `dayu/investment/storage/models_identity.py` 和 `models_auth.py` 后，这两个文件会导入 `sqlalchemy`，AST guard 会将其判为违规，测试失败。Implementation agent 必须同时修改 guard 逻辑和允许列表，但 plan 未指定：(a) 是修改 `_FORBIDDEN_IMPORT_PREFIXES` 为路径条件判断，还是拆分为两个独立 guard 函数；(b) `storage/` 子包内哪些模块允许 ORM 导入、哪些仍然禁止；(c) `conftest.py`、`alembic.ini`、`constraints/**` 等非 Python 文件是否需要纳入 guard。
- **为什么有问题**: Architecture guard 是 Slice 0.1 的 hard gate，已在 `test_architecture_boundaries.py:284` 运行。如果 implementation agent 重构不当（例如过度放宽 guard 允许 `domain/` 也导入 SQLAlchemy），会破坏纯层隔离；如果重构不足（例如只加 `storage/` 到 allowlist 但未处理 `__init__.py` re-export），测试仍然失败。Plan 声称这是 "按 owner 分组" 但未给出 owner 到 guard 的映射规则。
- **直接证据**: `test_architecture_boundaries.py:69-83` `_FORBIDDEN_IMPORT_PREFIXES` 包含 `"sqlalchemy"`；`test_architecture_boundaries.py:104` `_iter_investment_files()` 使用 `_INVESTMENT_SRC.rglob("*.py")`；`test_architecture_boundaries.py:284-301` `test_investment_never_imports_forbidden_modules` 对所有 investment 文件执行统一检查。
- **影响**: Implementation agent 可能生成错误的 guard 重构代码，导致：(a) 测试仍然失败（guard 过严）；(b) 纯层隔离被破坏（guard 过松）；(c) 需要额外 fix round 增加 review 成本。
- **建议改法和验证点**: Plan 应明确指定：(a) guard 按文件路径分组——`dayu/investment/domain/**`、`config.py`、`composition.py` 继续禁止 SQLAlchemy；`dayu/investment/storage/**` 允许 SQLAlchemy/psycopg/Alembic；`dayu/investment/__init__.py` 作为 re-export 层只转发 domain 符号；(b) 分组逻辑通过 `_INVESTMENT_SRC` 子路径判断而非文件名匹配；(c) 新增 `alembic.ini`、`constraints/**`、`conftest.py` 不纳入 Python AST guard（它们不是 `dayu.investment` 包的生产代码）。
- **修复风险（低/中/高）**: 低。Implementation agent 可以在 plan 接受后自行设计，但明确指定可减少返工。
- **严重程度（低/中/高/严重）**: 中。

### 002-未修复-中-Integration test fixture 基础设施未指定，container lifecycle/migration execution/session fixture 需 implementation agent 自行设计

- **位置**: S11-CTRL-07 + `tests/integration/investment/conftest.py`（allowlist 中但 plan 未描述内容）
- **问题类型**: 不可直接实施
- **当前写法**: plan 声称 integration tests 在 `tests/integration/investment/test_platform_migrations_postgres.py`，统一标记 `integration`；`conftest.py` 在 allowlist 中但未指定内容。Plan 列出了测试应该覆盖的场景（upgrade/downgrade/upgrade、default organization、transaction rollback、role grants、RLS unset/default-deny/cross-tenant/audit bypass/schema exact），但未指定 fixture 基础设施。
- **反例/失败场景**: Implementation agent 需要自行设计：(a) 如何在测试开始前启动 PG16 container（`docker run` / `testcontainers` / `pytest-docker`？）；(b) 如何分配随机端口避免并发冲突；(c) 如何创建/销毁测试数据库；(d) 如何在每个测试前执行 migration 并在测试后清理；(e) 如何提供 `engine`/`session` fixture 并确保 `SET LOCAL app.tenant_id` 在每个事务中正确设置。这些是 integration test 的核心基础设施，plan 完全未覆盖。
- **为什么有问题**: Integration test fixture 是 Slice 1.1 的关键交付物之一。如果 implementation agent 设计不当（例如使用固定端口导致并发冲突、使用 `metadata.create_all()` 违反 S11-CTRL-05、或 cleanup 不完整导致 container 泄漏），会导致测试不可靠或违反 plan 约束。Plan 应至少指定 fixture 的职责边界和约束。
- **直接证据**: plan §8 Slice 1.1 allowlist 包含 `tests/integration/investment/conftest.py`；S11-CTRL-07 指定测试场景但未指定 fixture；S11-CTRL-06 指定容器隔离策略但未指定 container lifecycle 管理方式。
- **影响**: Implementation agent 可能生成：(a) 使用固定端口的 fixture，导致并发测试失败；(b) 使用 `create_all()` 的 fixture，违反 transactional migration 约束；(c) cleanup 不完整的 fixture，导致 container/database 泄漏；(d) 缺少 `SET LOCAL app.tenant_id` 的 session fixture，导致 RLS 测试无法验证。
- **建议改法和验证点**: Plan 应指定 conftest.py 的最小职责：(a) 使用 `docker` CLI 或 `testcontainers-python` 启动 PG16 container，绑定 `127.0.0.1:0`（随机端口）；(b) 使用 bootstrap DSN 创建临时 test database；(c) 提供 `alembic_config` fixture 指向临时 database；(d) 每个测试函数/类前执行 `alembic upgrade head`，测试后执行 `alembic downgrade base`；(e) 提供 `bootstrap_engine` 和 `application_engine` 两个 fixture，分别使用 bootstrap DSN 和 application DSN；(f) 测试结束后销毁 container 和 database。
- **修复风险（低/中/高）**: 低。Implementation agent 可以在 plan 接受后自行设计，但明确指定可减少返工。
- **严重程度（低/中/高/严重）**: 中。

### 003-未修复-低-Lock file resolver 未指定，implementation agent 需推断工具链

- **位置**: S11-CTRL-01
- **问题类型**: 不可直接实施
- **当前写法**: plan 声称 "lock-common-py311.txt 与各平台 include lock 由 resolver 重新生成/验证，不手工猜测 transitive versions"，但未指定使用哪个 resolver。
- **反例/失败场景**: 仓库使用 `pyproject.toml` 和 `constraints/**`，但未安装 `uv`、`pip-compile` 或 `poetry`。Implementation agent 需要推断使用哪个工具生成 lock 文件。如果推断错误（例如使用 `pip freeze` 而非 `uv lock`），生成的 lock 文件格式可能不符合项目约定。
- **为什么有问题**: Lock 文件是 Slice 1.1 的 hard gate（"安装与 lock resolution 只在本勘误 accepted 后执行"）。如果 resolver 不明确，implementation agent 可能浪费时间在工具选择上，或生成不符合项目约定的 lock 文件。
- **直接证据**: plan S11-CTRL-01 指定 "lock-common-py311.txt 与各平台 include lock 由 resolver 重新生成/验证"；仓库 `pyproject.toml` 存在但未安装任何 lock 工具。
- **影响**: Implementation agent 可能：(a) 花费额外时间选择工具；(b) 生成格式不一致的 lock 文件；(c) 需要额外 fix round 修正 lock 格式。
- **建议改法和验证点**: Plan 应明确指定 resolver 工具（例如 `uv lock` 或 `pip-compile`）和输出格式约定。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

### 004-未修复-低-Downgrade 策略对 default organization 的处理未明确

- **位置**: S11-CTRL-05
- **问题类型**: 契约缺失
- **当前写法**: plan 声称 "downgrade 精确删除本 slice owner，不触碰其它数据库/schema/role"。Default organization 在同一次 migration 中以幂等固定值创建。
- **反例/失败场景**: Downgrade 时如果删除 `organizations` 表，default organization 数据丢失；如果不删除，schema 不一致（表存在但 RLS policy 已删除）。当前 Slice 1.1 是第一个 schema slice，没有依赖方，所以影响有限。但 plan 应明确说明 downgrade 的预期行为。
- **为什么有问题**: Implementation agent 需要知道 downgrade 是否应该删除 `organizations` 表（连带 default org 数据），还是只删除 RLS policy 和 role 而保留表结构。不同的选择会影响后续 slice 的 migration 设计。
- **直接证据**: plan S11-CTRL-05 指定 "downgrade 精确删除本 slice owner"；S11-CTRL-03 指定 default organization 在 migration 中创建。
- **影响**: Implementation agent 可能做出与后续 slice 不一致的 downgrade 决策。
- **建议改法和验证点**: Plan 应明确：downgrade 删除 Slice 1.1 创建的所有对象（包括 `organizations` 表和 default org 数据），因为 Slice 1.1 是首次 migration，没有其他 slice 依赖它。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## Security Review — Role/RLS Design

逐项审查 S11-CTRL-04 的 role/RLS 设计：

### bootstrap role

- **职责**: 独占 schema/DDL/role/policy ownership。
- **DSN**: migration 使用 bootstrap DSN。
- **评估**: 设计正确。Bootstrap role 需要 DDL 权限（`CREATE TABLE`、`CREATE POLICY`、`ALTER TABLE`、`CREATE ROLE`、`GRANT`），独立于 application role 是安全最佳实践。

### application role

- **约束**: `NOSUPERUSER NOCREATEROLE NOBYPASSRLS`，无 schema DDL。
- **DSN**: 运行时使用 application DSN。
- **评估**: 设计正确。Application role 无法创建角色、无法绕过 RLS、无法执行 DDL。RLS policy 通过 `SET LOCAL app.tenant_id` 在每个事务中设置，repository 保留显式 tenant predicate，形成双层隔离。

### audit role

- **约束**: `NOLOGIN BYPASSRLS` group role，只允许受审计的 bootstrap/operator principal `SET ROLE`，application role 不得成为其 member。
- **评估**: 设计正确。`NOLOGIN` 防止直接登录，`BYPASSRLS` 允许审计查询绕过租户隔离，`SET ROLE` 需要显式授权，application role 不得成为 member 防止权限泄漏。

### RLS policy

- **policy 语法**: `nullif(current_setting('app.tenant_id', true), '')::uuid`
- **未设置/空/错误 tenant**: `current_setting` 返回空字符串，`nullif` 返回 NULL，比较失败，default deny。✅ 正确。
- **organizations 表**: 比较 `id`（而非 `tenant_id`），因为 organizations 是 tenant root。✅ 正确。
- **其它私有表**: 比较 `tenant_id`。✅ 正确。
- **FORCE ROW LEVEL SECURITY**: 每张私有表启用并 FORCE。✅ 正确（防止 table owner 绕过 RLS）。

### 潜在安全风险

- **bootstrap role 权限过大**: Bootstrap role 独占 DDL，如果 bootstrap DSN 泄露，攻击者可以修改 schema。但这是 migration 的固有风险，plan 已通过 "alembic.ini 不保存 DSN" 和 "关闭 SQL 参数/secret 回显" 缓解。✅ 可接受。
- **audit role BYPASSRLS**: Audit role 可以绕过 RLS 查询所有租户数据。但 plan 限制只有受审计的 principal 可以 `SET ROLE`，且 application role 不得成为 member。✅ 设计合理。

## Schema/Downgrade Review

### Upgrade 策略

- Transactional migration：`CREATE ROLE`、`CREATE TABLE`、`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`、`CREATE POLICY`、`ALTER TABLE ... FORCE ROW LEVEL SECURITY`、`GRANT` 均支持事务内执行。✅ PostgreSQL 16 支持 transactional DDL。
- Default organization 以幂等固定值创建：UUID `00000000-0000-0000-0000-000000000001`、slug `default`。✅ 不会在 migration 中生成随机 identity。
- 任一步失败必须 rollback：✅ Transactional DDL 保证原子性。

### Downgrade 策略

- "精确删除本 slice owner"：Slice 1.1 创建的对象包括 `organizations`、`companies`、`securities`、`source_definitions`、`users`、`roles`、`user_roles`、`permissions`、`role_permissions`、`api_tokens`、`source_subscriptions`、`source_sync_runs`、`source_health_snapshots` 表，以及 `bootstrap`、`application`、`audit` 三个 role 和对应的 RLS policy。Downgrade 应按逆序删除这些对象。
- "不触碰其它数据库/schema/role"：Slice 1.1 是第一个 schema slice，没有其他 slice 依赖它，所以 downgrade 安全。✅
- **注意**: Downgrade 后 default organization 数据丢失，这是预期行为。

## PG16 Container Isolation Review

### 隔离策略

- 官方 `postgres:16.14-bookworm` image：✅ 与既有 PG17 stack 完全隔离。
- 随机 container/network/database/users：✅ 避免命名冲突。
- `127.0.0.1` 随机端口：✅ 避免端口冲突。
- 不复用/不连接/不修改既有 PostgreSQL 容器：✅ 安全。

### 潜在风险

- **并发测试冲突**: 如果多个测试进程同时运行，随机端口可能冲突。但 `127.0.0.1:0` 让 OS 分配端口，冲突概率极低。✅ 可接受。
- **Container cleanup**: 如果测试进程崩溃，container 可能泄漏。Plan 要求 "失败时保留结构化诊断后清理"，但未指定 cleanup 机制（例如 `atexit` handler 或 `docker compose down`）。Implementation agent 需要自行设计。⚠️ 低风险，但应在 conftest.py 中实现。

## Test Truth Review

### Unit/Integration Split

- `tests/investment/test_platform_migrations.py`：只做 metadata/schema/naming/generated SQL/禁止 create_all 等不需要数据库的 unit contract。✅ 清晰。
- `tests/integration/investment/test_platform_migrations_postgres.py`：真实 PostgreSQL integration，统一标记 `integration`。✅ 清晰。
- "不得用 SQLite/fake 替代"：✅ 明确。

### 测试覆盖

Plan 列出的 integration test 场景：

| 场景 | 评估 |
|------|------|
| upgrade -> downgrade -> upgrade | ✅ 核心 migration 往返测试 |
| default organization | ✅ 验证幂等固定值 |
| transaction rollback | ✅ 验证 transactional DDL |
| role grants | ✅ 验证 role 权限 |
| RLS unset/default-deny | ✅ 验证未设置 tenant 时 deny |
| RLS same-tenant allow | ✅ 验证同租户允许 |
| RLS cross-tenant reject | ✅ 验证跨租户拒绝 |
| audit bounded bypass | ✅ 验证 audit role 绕过 RLS |
| schema exact | ✅ 验证表结构与 plan 一致 |

所有关键场景均有覆盖。✅

## Conclusion

**PASS-WITH-RISKS**。Open H/M/L = **0/2/2**。

S11-CTRL-01..07 的核心设计（role/RLS 安全、schema transactional DDL、PG16 容器隔离、unit/integration split）均可实施且设计合理。两项 M-level finding（architecture guard 重构方案未指定、integration test fixture 基础设施未指定）不构成 blocker，implementation agent 可以在 plan 接受后自行设计，但明确指定可减少返工。Role/RLS 安全设计经逐项审查无问题。Schema/downgrade 策略在 Slice 1.1 范围内安全。Lock 文件和 downgrade 细节为 L-level，不阻塞实施。

允许进入 implementation，但建议 controller 在 adjudication 中补充 architecture guard 分组策略和 conftest.py 最小职责的显式指引。
