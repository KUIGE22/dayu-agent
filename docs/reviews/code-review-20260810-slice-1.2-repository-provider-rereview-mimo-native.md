# Code Corrective Re-review — Slice 1.2 Repository/Provider

## Scope

- Mode: corrective re-review（只读，独立复证 Terra 001-005 fixes）
- Branch: `codex/investment-platform`
- Review clock: `2026-08-10`（本机系统时钟）
- Output file: `docs/reviews/code-review-20260810-slice-1.2-repository-provider-rereview-mimo-native.md`
- Source chain: MiM initial PASS-WITH-RISKS（L2）→ Controller adjudication（Terra 001-005 ACCEPTED）→ DeepSeek fix → **本 corrective re-review**
- Fix artifact: `slice-1.2-repository-provider-code-review-fix-20260810-deepseek.md`
- Focus: Terra 001-005 fixes、nested JSON codec、SQL/RLS/CAS、startup admission/lifecycle、no escape、PG16、coverage

## Terra 001-005 — Independent Verification

### TERRA-S12-001 (HIGH) — Production Provider Admission Probe → CLOSED ✅

`startup_preparation.py` `_probe_production_engine()`：
- `engine.connect()` + `SELECT 1` 验证可达 ✅
- `pg_has_role(current_user, app_role, 'MEMBER')` 校验 application role membership ✅
- 拒绝 superuser（`rolsuper`）与 `BYPASSRLS`（`rolbypassrls`）✅
- probe 在 session_factory 构造前执行，Host/Fins 副作用零 ✅
- 任何失败 → `engine.dispose()` + safe `PlatformCompositionError`（`from None`）✅

Tests：
- `test_unreachable_dsn_fails_safely`：不可达端口 → `PlatformCompositionError`，副作用零、dispose 恰一次、atexit 注册零 ✅
- `test_malformed_dsn_fails_safely`：畸形 DSN → `PlatformCompositionError` ✅
- `test_production_provider_wrong_role_rejected`：真实 PG16 上非 app member → `PlatformCompositionError` ✅

### TERRA-S12-002 (MEDIUM) — Nil UUID / Bool Version Strict Boundary → CLOSED ✅

`source.py` `_validate_canonical_uuid()`：`parsed.int == 0` 拒绝 nil UUID ✅
`source.py` `_validate_positive_int()`：`type(value) is not int` 拒绝 bool 冒充 ✅
`postgres_identity.py` `_validate_positive_version()`：`type(expected_version) is not int` 拒绝 bool ✅

Tests：
- nil UUID 从 accept 移入 reject ✅
- `test_company_projection_rejects_bool_version`（`version=True` → `TypeError`）✅
- `test_subscription_id_rejects_nil_uuid`（nil UUID → `ValueError`）✅

### TERRA-S12-003 (MEDIUM) — Guard Binds to Current Class Direct `__post_init__` → CLOSED ✅

Guard `_collect_allowed_object_setattr_nodes()`：
- `_build_parent_map()` 构建节点 id → 父节点映射 ✅
- `_direct_post_init_owner()`：调用直接位于 frozen+slots dataclass 的 `__post_init__(self)` 方法体内（沿 AST 父链绑定，不经过嵌套函数/嵌套类）✅
- `_collect_frozen_slots_fields_by_class()`：字段集按 class id 隔离，只接受本类 AnnAssign 字段名 ✅

Negative matrix（4 项新增，全部 fail-closed）：
- nested function 内 `object.__setattr__` ✅
- nested class 方法内调用 ✅
- 跨类字段名（字段声明在另一 frozen+slots class）✅
- `__post_init__(self, other)` 多参数签名 ✅

### TERRA-S12-004 (MEDIUM) — `PreparedHostRuntimeDependencies.close()` Coordination → CLOSED ✅

`_OwnedLifecycleRegistration` 重构为延迟注册协调器：
- `__init__` 仅持有底层 lifecycle，不注册 atexit ✅
- `register()`：exact-once，已注册或已 close 后拒绝再注册 ✅
- `_close_at_exit()`（callback）：仅当已注册且未被手动 close 时执行一次 ✅
- `close()`（manual）：无条件幂等释放底层并解除注册意图 ✅

装配流：先建 wrapper → 作为唯一 field 构造 Prepared → 完整构造成功后 `register()` → return；失败路径 `wrapper.close()` / `owned_lifecycle.close()` 兜底 ✅

Tests：
- `test_prepared_close_then_callback_is_noop` ✅
- `test_register_before_callback_is_noop` ✅
- `test_register_is_exact_once` ✅
- `test_register_after_close_is_noop` ✅

### TERRA-S12-005 (LOW) — Unit Test Remove `hasattr` → CLOSED ✅

`test_identity_repositories.py` 改为显式 protocol 属性引用（`_ = (IdentityRepositoryProtocol.register_company_security, ...)` 元组赋值），移除全部 `hasattr` ✅

## Nested JSON Codec — Verified ✅

`source.py` `_deep_freeze()` + `_deep_freeze_value()`：
- Mapping → 递归新 dict + `MappingProxyType` ✅
- tuple → 递归新 tuple ✅
- list → raise ValueError ✅
- cycle detection（`seen` set + `id()`）✅
- 非字符串 key → raise ValueError ✅
- NaN/Infinity → raise ValueError ✅
- scalar（None/str/int/bool）→ 原值保留 ✅

`source.py:707, 740, 797`：`object.__setattr__(self, "config", _deep_freeze(self.config, "config"))` — 递归 deep-freeze ✅

## SQL/RLS/CAS — Verified ✅

- `_set_tenant_local()`：`set_config('app.tenant_id', :tenant_id, true)` + 读回确认 ✅
- 私有表查询带 `WHERE tenant_id = :tenant_id` ✅
- 公共 reference 表（companies/securities/source_definitions）无 tenant predicate（正确）✅
- `register_company_security()` 单事务：insert company → insert security → flush → commit；失败 rollback ✅
- `update_source_subscription()` CAS：`WHERE tenant_id + id + version` + `RETURNING id` 区分 not-found vs version conflict ✅
- 跨租户访问返回 not-found，不泄漏存在性 ✅

## Startup Admission/Lifecycle — Verified ✅

- `_default_provider_or_fail()`：explicit → use it；disabled → None；production → build default；development → fail-fast ✅
- `_build_production_identity_provider()`：DSN → engine → probe → session factory → repository → service → provider ✅
- DSN failure：missing/blank → `PlatformSettingsError`；other → `PlatformCompositionError`（不泄漏 DSN）✅
- Engine failure：`try/except` disposes engine ✅
- `_OwnedLifecycleRegistration`：延迟注册协调器，`register()` exact-once，`close()` idempotent ✅
- `atexit` callback：仅当已注册且未手动 close 时执行一次 ✅
- `InvestmentIdentityService.close()`：线程安全（`threading.Lock`）+ 幂等（`_closed` flag）+ 只 dispose owned engine ✅
- Explicit provider：lifecycle 为 None，caller owns，不注册 atexit ✅

## No Escape / No Future Owner — Verified ✅

- AST 扫描 production files：无 `Any`、无裸 `object`（所有 `object` 都是 `__setattr__` call target）、无 `cast/getattr/hasattr` ✅
- 无 future owner imports（jobs/evidence/portfolio）✅
- `InvestmentIdentityService` 只 import `composition`、`domain`、`storage/protocols` ✅

## PG16 Integration — Verified ✅

- 使用 Slice 1.1 owner-labeled PG16 fixture ✅
- 测试后 Slice-owned container/network 为零 ✅
- 未连接/停止/修改既有 PG17 stack ✅

## Coverage — Verified ✅

| 文件 | 覆盖率 |
|------|--------|
| `startup_preparation.py` | 81% |
| `domain/source.py` | 85% |
| `storage/postgres_identity.py` | 81% |
| `composition.py` | 100% |
| `services/investment_identity.py` | 83% |
| `services/protocols.py` | 100% |
| `storage/protocols.py` | 100% |

全部 >=80% ✅

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| `pytest tests/investment tests/application/test_service_startup_preparation.py tests/integration/investment -q` | **PASS** — 309 passed |
| `pyright` 变更全部文件 | **PASS** — 0 errors |
| `ruff check` 变更全部文件 | **PASS** — All checks passed |
| TERRA-S12-001 admission probe | **PASS** — SELECT 1 + pg_has_role + reject superuser/BYPASSRLS |
| TERRA-S12-002 nil UUID / bool version | **PASS** — `parsed.int == 0` + `type(value) is not int` |
| TERRA-S12-003 guard AST parent chain | **PASS** — 4 negative matrix items |
| TERRA-S12-004 lifecycle coordination | **PASS** — deferred register + exact-once + idempotent close |
| TERRA-S12-005 hasattr removal | **PASS** — explicit protocol attribute reference |
| Nested JSON deep-freeze | **PASS** — recursive Mapping/tuple + cycle/list/NaN rejection |
| SQL/RLS/CAS | **PASS** — SET LOCAL + explicit predicate + single transaction + CAS |
| Startup admission/lifecycle | **PASS** — probe + safe error + atexit coordination |
| No escape / no future owner | **PASS** — 0 escapes, 0 future imports |
| PG16 integration | **PASS** — real PG16, owner cleanup |
| Coverage >=80% | **PASS** — all files >=80% |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- probe 连接等待依赖 DB 网络往返（本地 PG16 实测 <1s）——可接受。
- `pg_has_role` 查询需 `pg_roles` 可读——已由真实 PG16 wrong-role/正常路径证明。
- 输入校验分支类型系统不可达——合理防御性分支。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。

Terra 001-005 全部闭合：admission probe（SELECT 1 + pg_has_role + reject superuser/BYPASSRLS）、nil UUID/bool version strict boundary、guard AST parent chain binding + 4 negative matrix、lifecycle coordination（deferred register + exact-once + idempotent close）、hasattr removal。nested JSON deep-freeze（`_deep_freeze` 递归 Mapping/tuple + cycle/list/NaN rejection）已实现。SQL/RLS/CAS/跨租户隐私通过。Startup admission/lifecycle/atexit 闭合。无 escape、无 future owner。309 tests 全部通过，pyright 0 errors，ruff All checks passed，每生产文件 >=80% coverage，PG17 未动。允许进入 code review completion。
