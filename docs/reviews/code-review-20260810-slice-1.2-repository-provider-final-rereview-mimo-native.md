# Final Re-review — Slice 1.2 Repository/Provider (MiM Native)

## Scope

- Mode: final independent re-review（只读，独立验证 RR-001/002 修复）
- Branch: `codex/investment-platform`
- Base: `d0ffe223d0f42521bb8a907152c1e8b4ade0125f`（accepted plan baseline）
- Review clock: `2026-08-10-170727`（本机系统时钟）
- Output file: `docs/reviews/code-review-20260810-slice-1.2-repository-provider-final-rereview-mimo-native.md`
- Source chain: MiM initial PASS-WITH-RISKS → Controller adjudication（Terra 001-005 ACCEPTED, MiM 001/002 REJECTED/stale）→ DeepSeek fix → Terra rereview（RR-001/002 ACCEPTED, RR-003 REJECTED）→ DeepSeek round 2 fix → **本 final re-review**
- Fix artifacts: `slice-1.2-repository-provider-code-review-fix-20260810-deepseek.md` + `slice-1.2-repository-provider-code-review-fix-round2-20260810-deepseek.md`
- Focus: RR-001（repository nil UUID）、RR-002（guard lambda/self/decorator）、lifecycle/startup/RLS/JSON codec 闭合、无新回归

## RR-001 — Repository Nil UUID Rejection

### 仓储层 `_canonical_uuid`（`postgres_identity.py:101-126`）

```python
def _canonical_uuid(value: str, label: str) -> str:
    ...
    parsed = UUID(value)
    ...
    if parsed.int == 0:                          # line 121
        raise RepositoryInputError(...)           # line 122
    canonical = str(parsed)
    if canonical != value:
        raise RepositoryInputError(...)
    return canonical
```

- `parsed.int == 0` 在 canonical comparison 前拒绝 nil UUID ✅
- 所有 repository entry 经 `_validate_scope` / `_normalize_*_id` 均经由此 helper ✅
- 一处修复全链生效 ✅

### DTO 层 `_validate_canonical_uuid`（`source.py:54-79`）

```python
def _validate_canonical_uuid(value: str, label: str) -> str:
    ...
    if parsed.int == 0:                          # line 77
        raise ValueError(...)                     # line 78
    ...
```

- DTO 层同样拒绝 nil UUID，形成双层防御 ✅
- `SourceDefinitionId` / `SourceSubscriptionId` 的 `__post_init__` 均调用此函数 ✅

### 测试覆盖

- `TestRepositoryRejectsNilIdsPreSession` 类：每类 entry 一个 pre-session / zero-SQL 断言 ✅
- `test_nil_tenant_scope_rejected_before_session` ✅
- `test_nil_company_id_rejected_before_session` ✅
- `test_nil_security_id_rejected_before_session` ✅
- `test_nil_source_definition_id_rejected_before_session` ✅
- `test_nil_subscription_id_rejected_before_session` ✅
- `_RejectingSessionFactory` 证明校验发生在 Session 创建之前（零 SQL）✅

**RR-001 VERIFIED** ✅

## RR-002 — Guard Lambda/Self/Decorator Strictness

### `_direct_post_init_owner`（`test_architecture_boundaries.py:357-404`）

- 父链遇 `ast.Lambda`、`ast.ListComp`、`ast.SetComp`、`ast.DictComp`、`ast.GeneratorExp` 即返回 `None`（嵌套执行作用域一律拒绝）✅
- `__post_init__` 唯一参数名精确为 `self`（`_is_sole_self_param`）✅

### `_is_sole_self_param`（`test_architecture_boundaries.py:407-431`）

- `posonlyargs` 为空 ✅
- `args` 恰好一个且名字精确 `self` ✅
- `vararg` / `kwonlyargs` / `kwarg` 全空 ✅

### `_is_frozen_slots_dataclass`（`test_architecture_boundaries.py:434-478`）

- `frozen` / `slots` 仅接受 `ast.Constant` 且 `value is True` ✅
- `frozen=1` / `slots=1` 真值常量被正确拒绝 ✅

### 负例矩阵（8 项 RR-002 新增，全部 fail-closed）

| 负例 | 行号 | 结果 |
|------|------|------|
| lambda 内调用 | 1099-1107 | "禁止使用 object" ✅ |
| list comprehension 内调用 | 1108-1116 | "禁止使用 object" ✅ |
| 参数名非 self（`__post_init__(owner)`） | 1117-1125 | "禁止使用 object" ✅ |
| posonly（`def __post_init__(self, /)`） | 1126-1134 | "禁止使用 object" ✅ |
| vararg（`*args`） | 1135-1143 | "禁止使用 object" ✅ |
| kwonly（`*, extra`） | 1144-1152 | "禁止使用 object" ✅ |
| kwargs（`**kwargs`） | 1153-1161 | "禁止使用 object" ✅ |
| `frozen=1, slots=1` | 1162-1170 | "禁止使用 object" ✅ |

**RR-002 VERIFIED** ✅

## Lifecycle/Shutdown (S12-CTRL-07) — Verified ✅

### `_OwnedLifecycleRegistration`（`startup_preparation.py:340-433`）

- `__init__`：仅持有底层 lifecycle，`_registered=False`、`_closed=False`，不注册 atexit ✅
- `register()`：exact-once，已注册或已 close 后拒绝再注册 ✅
- `_close_at_exit()`（callback）：仅当 `_registered=True` 且 `_closed=False` 时执行一次 ✅
- `close()`（manual）：无条件幂等释放底层并解除注册意图 ✅

### 装配流（`startup_preparation.py:583-602`）

- `owned_lifecycle is not None` → 构造 wrapper → 作为唯一 field 构造 Prepared → 完整构造成功后 `register()` → return ✅
- 失败路径：`lifecycle_registration.close()` 或 `owned_lifecycle.close()` 兜底 ✅
- `PreparedHostRuntimeDependencies.close()` 委托 `_owned_platform_lifecycle.close()` ✅

### `InvestmentIdentityService.close()`（`investment_identity.py:324-342`）

- 线程安全（`threading.Lock`）+ 幂等（`_closed` flag）+ 只 dispose owned engine ✅

### Explicit Provider Ownership

- `_default_provider_or_fail()`：explicit provider → `(provider, None)`，lifecycle 为 None，caller owns ✅
- `_build_production_identity_provider()`：auto-created → `(provider, service)`，lifecycle 是 service ✅

## Startup Admission (S12-CTRL-06) — Verified ✅

### `_default_provider_or_fail()`（`startup_preparation.py:307-337`）

- explicit → use it ✅
- disabled → None ✅
- production → build default ✅
- development → fail-fast（"development 平台启用必须显式注入组合提供者"）✅

### `_probe_production_engine()`（`startup_preparation.py:194-236`）

- `SELECT 1` 验证可达 ✅
- `pg_has_role(current_user, app_role, 'MEMBER')` 校验 application role membership ✅
- 拒绝 superuser（`rolsuper`）与 BYPASSRLS（`rolbypassrls`）✅
- probe 在 session_factory 构造前执行，Host/Fins 副作用零 ✅

### DSN Safe Failure

- missing/blank DSN → `PlatformSettingsError`（不回显 DSN）✅
- engine/repository/service 构造失败 → `PlatformCompositionError("production PostgreSQL identity provider 初始化失败")`（不泄漏 DSN）✅
- `from None` 抑制 cause ✅

## SQL/RLS/CAS — Verified ✅

- `_set_tenant_local()`：`set_config('app.tenant_id', :tenant_id, true)` + 读回确认 ✅
- 私有表查询带 `WHERE tenant_id = :tenant_id` ✅
- 公共 reference 表（companies/securities/source_definitions）无 tenant predicate（正确）✅
- `register_company_security()` 单事务：insert company → insert security → flush → commit ✅
- `update_source_subscription()` CAS：`WHERE tenant_id + id + version` + `RETURNING id` 区分 not-found vs version conflict ✅
- 跨租户访问返回 not-found，不泄漏存在性 ✅

## JSON Codec — Verified ✅

- `_deep_freeze()` + `_deep_freeze_value()`：Mapping → 递归新 dict + `MappingProxyType` ✅
- tuple → 递归新 tuple ✅
- list → raise ValueError ✅
- cycle detection（`seen` set + `id()`）✅
- 非字符串 key → raise ValueError ✅
- NaN/Infinity → raise ValueError ✅
- `source.py:707, 740, 797`：`object.__setattr__(self, "config", _deep_freeze(self.config, "config"))` — 递归 deep-freeze ✅

## No Escape / No Future Owner — Verified ✅

- AST 扫描 production files：无 `Any`、无裸 `object`（所有 `object` 都是 `__setattr__` call target）、无 `cast/getattr/hasattr` ✅
- 无 future owner imports（jobs/evidence/portfolio）✅
- `InvestmentIdentityService` 只 import `composition`、`domain`、`storage/protocols` ✅

## Protocol/Interface Boundaries — Verified ✅

- `InvestmentIdentityService` 不 import ORM model、engine/session ✅
- Storage protocols 不 import Web/Service/Host/Agent ✅
- Service protocol 真源定义在纯层 `composition.py`，`protocols.py` 只做 re-export ✅
- `PlatformOwnedLifecycleProtocol` 不暴露 engine/session/repository/provider ✅

## PG16 Integration — Verified ✅

- 使用 Slice 1.1 owner-labeled PG16 fixture ✅
- 测试后 Slice-owned container/network 为零 ✅
- 未连接/停止/修改既有 PG17 stack ✅

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| `pytest tests/investment tests/application/test_service_startup_preparation.py tests/integration/investment -q` | **PASS** — 322 passed |
| RR-001 repository nil UUID rejection | **PASS** — `parsed.int == 0` at `_canonical_uuid` + DTO layer |
| RR-002 guard lambda/self/decorator strictness | **PASS** — 8 negative matrix items + `_is_sole_self_param` + `ast.Constant value is True` |
| Lifecycle coordination | **PASS** — deferred register + exact-once + idempotent close |
| Startup admission probe | **PASS** — SELECT 1 + pg_has_role + reject superuser/BYPASSRLS |
| DSN safe failure | **PASS** — stable errors, no DSN leak |
| SQL/RLS/CAS | **PASS** — SET LOCAL + explicit predicate + single transaction + CAS |
| Cross-tenant privacy | **PASS** — not-found for cross-tenant |
| JSON deep-freeze | **PASS** — recursive Mapping/tuple + cycle/list/NaN rejection |
| No escape / no future owner | **PASS** — 0 escapes, 0 future imports |
| Protocol boundaries | **PASS** — Service 不反向依赖 storage/Web/Host |
| PG16 integration | **PASS** — real PG16, owner cleanup |

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

RR-001（repository nil UUID rejection via `parsed.int == 0`）和 RR-002（guard AST strictness: lambda/comprehension rejection, `_is_sole_self_param`, `ast.Constant value is True`）均已独立验证闭合。Lifecycle/startup/RLS/JSON codec 全部通过。322 tests 全部通过，无新回归。允许进入 code review completion。
