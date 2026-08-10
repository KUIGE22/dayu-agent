# Code Review — Slice 1.2 Repository/Provider Corrective Re-review（Terra）

## Scope

- Mode: 当前未提交 Slice 1.2 corrective re-review（只读）。
- Branch/base: `codex/investment-platform`，base 为 `main`（`7c97c1f`）。
- Review clock: 2026-08-10 16:26 CST。
- Required sources read: `AGENTS.md`、accepted plan 的 Slice 1.2 / S12-CTRL-01..08、原 Terra review、Controller adjudication、DeepSeek fix artifact，以及当前全部 tracked diff 与新增文件。
- Included: production default provider admission、UUID/version boundary、frozen-slots AST guard、auto-owned lifecycle、repository SQL/codec/RLS/CAS、unit/PG16 integration/typing/lint/coverage evidence。
- Excluded: Slice 1.3+、live/broker/外发与既有 PG17；未修改 production/tests/README/plan/既有 artifact，未 commit/push/PR。

## Findings

### TERRA-S12-RR-001-中-repository 的 canonical UUID 边界仍接受 nil UUID，TERRA-S12-002 未完整闭合

- **位置**: `dayu/investment/storage/postgres_identity.py:101-124`，所有 repository entry 的 `_validate_scope()` / `_normalize_*_id()` 都经由此 helper（`142, 161, 179, 197, 215`）。
- **复现**: 直接调用 `_canonical_uuid("00000000-0000-0000-0000-000000000000", "id")` 返回该 nil UUID，而非 `RepositoryInputError`。因此仍可用 generic `TenantId` / `CompanyId` / `SecurityId` 的 nil 值越过 repository pre-session UUID admission，进入后续 SQL 路径。
- **对照修复**: `source.py` 的 `_validate_canonical_uuid()` 已拒绝 `parsed.int == 0`，`_validate_positive_int()` 与 repository `_validate_positive_version()` 也已以 exact `int` 拒绝 bool；但 storage helper 遗漏同一 nil 判定。S12-CTRL-05 要求每一个 repository entry 在 Session 前拒绝所有 physical nil UUID，不能只依赖 source DTO。
- **影响**: DTO/SQL boundary 不一致，nil sentinel 可作为 tenant 或 identity key 进入数据库操作；这正是原 TERRA-S12-002 要求补齐的 repository pre-SQL negative。
- **最小修复**: 在 storage `_canonical_uuid()` 的 canonical comparison 后（或前）拒绝 `parsed.int == 0`，并为每一类 repository entry 至少补一个 spy session 断言（抛 `RepositoryInputError`、零 SQL）。

### TERRA-S12-RR-002-中-frozen-slots AST 豁免仍可经 lambda/非精确 self/decorator 真值绕过，TERRA-S12-003 仅部分闭合

- **位置**: `tests/investment/test_architecture_boundaries.py:357-389, 393-425, 467-493`。
- **复现**: 以下三段分别调用现有 `_collect_escape_violations_from_source()` 均返回 `[]`，即未报告禁止的 `object`：

  1. `def __post_init__(self): callback = lambda: object.__setattr__(self, "value", "x")`；父链跨过 `ast.Lambda`，而 `_direct_post_init_owner()` 只在遇到 `FunctionDef` / `ClassDef` / `Module` 时停止。
  2. `def __post_init__(owner): object.__setattr__(self, "value", "x")`；只检查 `len(parent.args.args) == 1`，未要求唯一参数名字精确为 `self`。
  3. `@dataclass(frozen=1, slots=1)`；`bool(keyword.value.value)` 将任意真值常量当作精确 `True`。

- **已闭合部分**: 普通 nested `def`、nested class 与跨 class field 的已加 negative 均通过；field 集也已按 class id 隔离。因此不是原 bypass 的重复报告，而是 current parent/decorator matching 的新反例。
- **影响**: guard 的契约声称仅豁免当前 frozen=True、slots=True dataclass 直接 `__post_init__(self)` 的精确调用，实际仍放宽了 nested function context 和方法/装饰器形态；后续生产代码可借此绕过 `object` 禁令。
- **最小修复**: parent walk 遇到 `ast.Lambda`、comprehension 等嵌套 execution scope 即拒绝；检查 sole positional parameter 的 `arg == "self"`（并拒绝其他参数种类）；仅接受 `ast.Constant(value is True)` 的 `frozen` 与 `slots`。补上述三个 negative。

### TERRA-S12-RR-003-中-required PG16/coverage closure 未能在本机独立完成

- **复现**: `pytest -q tests/integration/investment/test_identity_repositories_postgres.py` 在 fixture 创建任何容器前，14 项全部因本机缺少 locked digest `postgres@sha256:64154d0babcb` 报 setup error；未创建或触碰 PG16 资源，也未影响既有 PG17。
- **影响范围**: 因而无法独立实证 member app login 成功、wrong-role 真正于 Host/Fins 前失败、真实 nested JSONB/SQL/RLS/CAS、PG16 cleanup。带 `pytest-cov` 的覆盖率命令亦在 collection 被本地 pandas/numpy 的 `cannot load module more than once per process` 阻断，不能独立验证每个修改生产文件 >=80%。这不是 production 代码缺陷，但在本 gate 不能作为已验证 closure。
- **最小修复/验证**: 提供已锁定 PG16.14 digest 镜像后，复跑该 integration 文件并确认 owner-labeled container/network 为零；修复本地 coverage tracer/numpy 环境后，以隔离 `COVERAGE_FILE` 复跑针对五个修改生产模块的 coverage gate。

## Closure Evidence

| 原项 | 独立结论 | 证据 |
| --- | --- | --- |
| TERRA-S12-001 | **代码与 unit 闭合；PG16 black-box 未执行** | `_probe_production_engine()` 在构造 session/Host/Fins 前执行 connect、`SELECT 1`、`pg_has_role(..., 'MEMBER')` 与 `rolsuper`/`rolbypassrls` 拒绝；`test_unreachable_dsn_fails_safely` 证明安全错误、dispose 一次、Host/Fins sentinel 与 atexit 注册均为零。PG16 member/wrong-role test 存在但被缺镜像阻断。 |
| TERRA-S12-002 | **未闭合** | source UUID nil 与 bool projection/CAS 已拒绝；storage `_canonical_uuid()` 仍接受 nil，见 RR-001。 |
| TERRA-S12-003 | **部分闭合** | 原 nested `def`、nested class、cross-class field negatives 通过；lambda、改名 `self`、truthy decorator 仍误放行，见 RR-002。 |
| TERRA-S12-004 | **闭合** | `PreparedHostRuntimeDependencies` 持有 `_OwnedLifecycleRegistration`；完整 Prepared 构造后才 `register()`；unit 覆盖 public `prepared.close()` 后 callback no-op、callback-only、重复 register/close。 |
| TERRA-S12-005 | **闭合** | 对本次 production/测试范围的 `rg '\\bhasattr\\s*\\('` 无命中；protocol test 已改为显式属性引用，聚焦 guard 通过。 |

## Regression Check

- 静态走读确认 repository 各事务仍先以 `set_config('app.tenant_id', :tenant_id, true)` 建立 local tenant context；subscription 读写仍带显式 `tenant_id` predicate，CAS 仍以 `tenant_id + id + expected_version` 作为 update 条件。递归 JSON tuple/Mapping codec 和单事务 rollback 路径未发现本 corrective diff 引入的回归。
- production default provider 仍只装配 `investment_identity`，显式 provider 不交出 ownership；failure 路径不会先注册 atexit，public close 后既注册 callback 为真 no-op。
- 未发现 `hasattr`、新增 Any/object/cast/type-ignore escape、future owner（jobs/evidence/portfolio）import、raw DSN 日志或对既有 PG17 的操作路径。

## Validation

| 检查 | 结果 |
| --- | --- |
| `pytest -q tests/investment/test_identity_repositories.py tests/investment/test_architecture_boundaries.py tests/application/test_service_startup_preparation.py` | PASS，184 passed。 |
| AST/nil 最小反例 | FAIL as expected：storage nil UUID、lambda/renamed-self/truthy-decorator guard 均被当前实现接受。 |
| `pytest -q tests/integration/investment/test_identity_repositories_postgres.py` | BLOCKED：14 setup errors，缺 locked PG16 digest；零容器启动。 |
| `pyright ...`（所有变更 production 与相关 tests） | PASS，0 errors / warnings / informations。 |
| `ruff check ...`（同范围） | PASS，All checks passed。 |
| `git diff --check` | PASS。 |
| coverage | BLOCKED：pytest-cov collection 触发本地 pandas/numpy import error，未把历史 artifact 的覆盖率数字当作本轮结果。 |

## Open Questions

无。三项 open 均有当前代码或当前环境的直接复现。

## Residual Risk

- 在修复 RR-001 前，数据库 boundary 对 source DTO 与 generic identity/tenant ID 不一致。
- 在修复 RR-002 前，guard 不能作为“仅精确 direct `__post_init__(self)`”的完整防线。
- PG16 image/coverage 环境恢复前，真实 PostgreSQL role admission、RLS、cleanup 与每文件 coverage 仅有测试设计/历史 artifact，非本轮实证。

## Conclusion

**FAIL**。Open H/M/L = **0 / 3 / 0**。

TERRA-S12-001、004、005 已由当前代码和 unit 复证为闭合（001 的 PG16 black-box 仍待环境恢复）；TERRA-S12-002 与 003 未完整闭合，且 required PG16/coverage verification 被本机确定性环境前置条件阻断。
