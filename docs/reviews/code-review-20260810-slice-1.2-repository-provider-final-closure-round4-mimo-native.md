# Code Review — Slice 1.2 Repository/Provider Final Closure Re-review（Round 4，MiM Native）

## Scope

- Mode: current changes / final closure round 4 re-review（只读）
- Branch: `codex/investment-platform`
- Base: `main`（`7c97c1f4e28af17d1a6d5c1b92706d793d9c7180`）及 accepted master plan `docs/plans/2026-08-10-investment-platform-restoration.md` 的 Slice 1.2 / S12-CTRL-01..08
- Review clock: `2026-08-10 17:46:33 CST`（本机系统时钟）
- Output file: `docs/reviews/code-review-20260810-slice-1.2-repository-provider-final-closure-round4-mimo-native.md`
- Included scope: 根 `AGENTS.md`、accepted plan 的 Slice 1.2 / S12-CTRL-01..08、全部 Slice 1.2 implementation/adjudication/四轮 fix artifact（round1 到 round4）、Terra/MiM 的初审/corrective rereview/final rereview/final closure artifacts；当前 Slice 1.2 domain/repository/provider/service/guard 源码与测试
- Excluded scope: Slice 1.3+、Docker/PG16 执行、live/network/paid 操作、既有 PG17 stack、push/PR；未修改 code/tests/plan 或既有 artifacts
- Parallel review coverage: 无（独立复核）

## TERRA-S12-FC-001 Round 4 Fix Verification

### Finding Background

Terra final closure（`code-review-20260810-slice-1.2-repository-provider-final-closure-terra.md`）报告 TERRA-S12-FC-001：`_module_scope_bound_names()` 手工枚举绑定形态未覆盖 `ast.MatchAs` 的 capture pattern，模块级 `match fake: case dataclass: pass` 会把 `dataclass` 重绑定为 `fake`（伪 decorator），guard 仍视其可信并放行普通可变类 `__post_init__` 内的 `object.__setattr__`。

### Fix Description（`slice-1.2-repository-provider-code-review-fix-round4-20260810-deepseek.md`）

按 Controller 指示停止手工枚举 pattern AST，改用 Python 标准库 **symtable** 作为模块绑定真源：

1. **单次 parse + source 传递**：`_collect_escape_violations_from_source()` 将 `source` 传给 `_collect_allowed_object_setattr_nodes(tree, source)`，复用调用方同一 tree（保证豁免 node id 一致），内部不再 `ast.parse`，symtable 仅用 `source`——修复同 source 双 parse 导致的 11 个合法 `object` 误报。
2. **信任判定**（`_collect_standard_dataclass_names(source)`）：
   - AST 层面：候选仍须是**唯一**模块级 `from dataclasses import dataclass [as alias]` 导入绑定；
   - symtable 层面：`symtable.symtable(source, "<module>", "exec")` 的 `lookup(alias)` 必须 `is_imported()` 为 True 且 `is_assigned()` 为 False——assignment/for/with/except/walrus/match capture/del/function/class 等一切模块级写绑定统一 fail closed。
3. 删除手工枚举 helper `_module_scope_bound_names()` / `_iter_assigned_names()`。
4. 保留既有限制：top-level ClassDef、direct `ast.Name` callee、唯一同一 call 同时携带 `frozen=ast.Constant(True)` 与 `slots=ast.Constant(True)`。

### Independent Verification

#### 1. Symtable Binding Source of Truth — VERIFIED ✅

独立验证 Python 3.11 `symtable.symtable(source, "<module>", "exec")` 对所有关键绑定形态的判定：

| 绑定形态 | `is_imported` | `is_assigned` | Guard 行为 |
|----------|---------------|---------------|------------|
| `from dataclasses import dataclass`（正常导入） | True | **False** | 放行（正例） |
| `match fake: case dataclass: pass`（match/case capture） | True | **True** | 拒绝 |
| `del dataclass`（del 绑定） | True | **True** | 拒绝 |
| `dataclass = lambda cls: cls`（assignment 重绑定） | True | **True** | 拒绝 |
| `x = (dataclass := None)`（walrus operator） | True | **True** | 拒绝 |
| `for dataclass in [None]: pass`（for 循环） | True | **True** | 拒绝 |
| `with open('x') as dataclass: pass`（with 语句） | True | **True** | 拒绝 |
| `except Exception as dataclass: pass`（except 子句） | True | **True** | 拒绝 |
| `def dataclass(): pass`（函数定义） | True | **True** | 拒绝 |
| `class dataclass: pass`（类定义） | True | **True** | 拒绝 |

symtable 的 `is_assigned()` 覆盖所有 Python 语言级绑定形态，无需手工枚举 AST pattern。嵌套函数/类内部作用域由 symtable 天然隔离（`lookup` 只在模块作用域解析）。

#### 2. Single AST Tree Node Identity — VERIFIED ✅

`_collect_escape_violations_from_source()` 在 line 285 执行 `tree = ast.parse(source)` 一次，然后在 line 290 将同一 `tree` 传给 `_collect_allowed_object_setattr_nodes(tree, source)`。该函数内部 `_collect_standard_dataclass_names(source)` 虽再次 `ast.parse` 用于 AST import 扫描，但 **allowed node 收集使用调用方传入的同一 tree**，因此 `id(base)` 与 escape walker 中 `id(node)` 一致。

独立测试验证：使用同一 tree 时 node ID 一致（`allowed_nodes == allowed_nodes2` 当 tree 相同时为 True）；使用不同 tree 时 node ID 不同（这是预期行为，因为 fix 已确保调用方传入同一 tree）。

#### 3. TERRA-S12-FC-001 Negative Tests — VERIFIED ✅

新增 2 项负例（`test_architecture_boundaries.py:1345-1366`）：

- **match/case capture**：`from dataclasses import dataclass` → `match fake: case dataclass: pass` → `@dataclass(frozen=True, slots=True)` 装饰含 `object.__setattr__` 的类 → 断言 `"禁止使用 object"` in violations
- **del binding**：`from dataclasses import dataclass` → `del dataclass` → 同上装饰 → 断言 `"禁止使用 object"` in violations

150 guard tests 全部通过（148 既有 + 2 新增）。

#### 4. Repository Nil UUID Rejection — VERIFIED ✅

`postgres_identity.py:121` — `if parsed.int == 0: raise RepositoryInputError(...)`。所有 repository entry 的 `_validate_scope` / `_normalize_*_id` 均经由 `_canonical_uuid()`，一处修复全链生效。nil UUID `00000000-0000-0000-0000-000000000000` 被正确拒绝，valid UUID 通过。

#### 5. Startup/Lifecycle Coordination — VERIFIED ✅

22 startup preparation tests 全部通过。关键契约验证：
- `manual close` 后 `callback` no-op
- `callback` 两次只 `close` 一次
- `register` 前 `callback` 无动作
- `register` exact-once
- `close` 后 `register` no-op

#### 6. RLS/CAS — VERIFIED ✅

- **RLS**：`postgres_identity.py:275` — `set_config('app.tenant_id', :tenant_id, true)` transaction-local tenant setting；migration `0001_platform_foundation.py:588-594` — `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` + `tenant_isolation` policy
- **CAS**：`postgres_identity.py:1151` — `WHERE tenant_id = :tenant_id AND id = :id AND version = :expected_version` optimistic concurrency control
- **Explicit tenant predicate**：所有 private query 同时带显式 tenant predicate

#### 7. JSON Deep-Freeze — VERIFIED ✅

- recursive Mapping → `MappingProxyType`
- recursive tuple → tuple
- list → `ValueError`
- cycle detection
- non-string key → `ValueError`
- NaN/Infinity → `ValueError`

#### 8. Guard Strictness (RR-002) — VERIFIED ✅

- `_direct_post_init_owner` 父链遇 `ast.Lambda`、`ast.ListComp`、`ast.SetComp`、`ast.DictComp`、`ast.GeneratorExp` 即返回 `None`
- `__post_init__` 唯一参数名精确为 `self`（`_is_sole_self_param`）
- `frozen` / `slots` 仅接受 `ast.Constant` 且 `value is True`；`frozen=1` / `slots=1` 真值常量被正确拒绝

#### 9. Validation Summary

| 检查项 | 结果 |
|--------|------|
| `pytest tests/investment/test_architecture_boundaries.py -q` | **PASS** — 150 passed |
| `pytest tests/investment tests/application/test_service_startup_preparation.py -q` | **PASS** — 289 passed |
| `pyright` (8 key files) | **PASS** — 0 errors, 0 warnings, 0 informations |
| 合法 direct standard decorator positive | **PASS** — 不被误拒 |
| 10 项负例（含 TERRA-S12-FC-001 2 项） | **PASS** — 全部 fail-closed |
| nested class 豁免拒绝 | **PASS** |
| RR-001: Repository nil UUID rejection | **PASS** |
| RR-002: Guard lambda/self/decorator strictness | **PASS** |
| Lifecycle coordination | **PASS** |
| JSON deep-freeze | **PASS** |
| RLS/CAS | **PASS** |
| No escape / no future owner | **PASS** |
| Protocol boundaries | **PASS** |

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- 输入校验分支类型系统不可达——合理防御性分支。
- 条件性/非顶层 `from dataclasses import dataclass` 不被识别为标准绑定——fail-closed 保守，production 无此类用法。
- 模块级重绑定按"全模块模糊"处理——保守 fail-closed，production 无此类用法。
- 本轮按授权未运行 Docker/PG16 integration——已读取 Controller/DeepSeek/MiM prior artifacts 的同树真实 PG16 证据，且未把本环境 Docker 可用性计为开放代码 finding。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。

TERRA-S12-FC-001（symtable 绑定真源替换手工枚举）已独立验证闭合：match/case capture、del、assignment/for/with/except/walrus/function/class 等一切模块级写绑定由 `symtable.is_assigned()` 统一覆盖，合法 direct standard `@dataclass(frozen=True, slots=True)` 正例放行，单次 AST tree node identity 保证无误报。RR-001（nil UUID）、RR-002（guard strictness）、lifecycle/startup/RLS/CAS/JSON codec 全部通过。289 tests 全部通过，150 guard tests 全部通过，pyright 0 errors，无新回归。允许进入 code review completion。
