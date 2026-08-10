# Code Review — Slice 1.2 Repository/Provider Final Closure Re-review（MiM Native）

## Scope

- Mode: current changes / final closure re-review
- Branch: `codex/investment-platform`
- Base: `main`（`7c97c1f4e28af17d1a6d5c1b92706d793d9c7180`）及 accepted master plan `docs/plans/2026-08-10-investment-platform-restoration.md` 的 Slice 1.2 / S12-CTRL-01..08。
- Review clock: `2026-08-10 17:34:43 CST`（本机系统时钟）。
- Output file: `docs/reviews/code-review-20260810-slice-1.2-repository-provider-final-closure-mimo-native.md`
- Included scope: 根 `AGENTS.md`、accepted plan、implementation/adjudication/三轮 fix artifact、Terra/MiM 的初审与 rereview/final-rereview artifact；Slice 1.2 的 domain/repository/provider/service/guard、相关 unit tests、integration test 源码和 README。
- Excluded scope: Slice 1.3+、live/network/paid 操作、Docker/PG16 运行、既有 PG17 stack；未修改 production、tests、plan 或既有 artifacts。
- Parallel review coverage: 无（独立复核）。

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| `pytest tests/investment/test_architecture_boundaries.py -q` | **PASS** — 148 passed |
| `pytest tests/investment tests/application/test_service_startup_preparation.py -q` | **PASS** — 287 passed |
| `pyright tests/investment/test_architecture_boundaries.py dayu/services/startup_preparation.py dayu/investment/domain/source.py dayu/investment/storage/postgres_identity.py dayu/investment/composition.py dayu/services/investment_identity.py dayu/services/protocols.py dayu/investment/storage/protocols.py` | **PASS** — 0 errors, 0 warnings, 0 informations |
| 合法 direct standard decorator positive | **PASS** — 不被误拒 |
| 8 项负例（TERRA-S12-FRR-001） | **PASS** — 全部 fail-closed |
| nested class 豁免拒绝 | **PASS** — `_collect_frozen_slots_fields_by_class` 检查 parent 为 Module |
| RR-001: Repository nil UUID rejection | **PASS** — `parsed.int == 0` at `_canonical_uuid` |
| RR-002: Guard lambda/self/decorator strictness | **PASS** — 8 negative matrix items + `_is_sole_self_param` + `ast.Constant value is True` |
| Lifecycle coordination | **PASS** — deferred register + exact-once + idempotent close |
| JSON deep-freeze | **PASS** — recursive Mapping/tuple + cycle/list/NaN rejection |
| No escape / no future owner | **PASS** — 0 escapes, 0 future imports |
| Protocol boundaries | **PASS** — Service 不反向依赖 storage/Web/Host |

## Findings

### 编号-未修复-[严重程度]-finding简述

未发现实质性问题。

**验证详情**：

#### 1. Guard Verification (TERRA-S12-FRR-001) — VERIFIED ✅

**Provenance 校验**：`_collect_standard_dataclass_names()` 只接受模块顶层 `from dataclasses import dataclass`（含 `as` 别名）的直接绑定；若该名字随后在模块作用域被重新赋值、被同名 def/class 覆盖、出现重复导入或其它模糊绑定形态，则整个模块对该名字 fail closed。

**Single direct call**：`_is_frozen_slots_dataclass()` 要求 decorator callee 为直接 `ast.Name` 且其 id 属于可信标准名字集合；attribute callee（`fake.dataclass`）、无标准导入、同名伪 decorator 全部不满足；整个类必须恰好命中一个这样的 decorator call。

**Same-call keyword**：该唯一 call 必须同时携带 `frozen=ast.Constant(True)` 与 `slots=ast.Constant(True)`，不得跨 decorator 聚合；重复关键字或模糊绑定一律 fail closed；call 携带位置参数视为非精确形态拒绝。

**Module-level-only exemption**：豁免类必须是直接挂在模块顶层的 ClassDef（parent 为 `ast.Module`）；函数/类体内嵌套的同形类由局部同名伪 decorator 遮蔽一律拒绝。

**对抗性验证结果**：

| 测试场景 | `_is_frozen_slots_dataclass` | violations |
|----------|------------------------------|------------|
| 合法 direct standard decorator | `True` | `[]` |
| 模块级同名伪 decorator | `False` | `['禁止使用 object']` |
| attribute callee | `False` | `['禁止使用 object']` |
| frozen/slots 分散在两个 decorator | `False` | `['禁止使用 object']` |
| 标准 import 后模块级重绑定 | `False` | `['禁止使用 object']` |
| import-as 重绑定 | `False` | `['禁止使用 object']` |
| from-import 重绑定 | `False` | `['禁止使用 object']` |
| nested class | `True`（但 parent 非 Module） | `['禁止使用 object']` |

#### 2. RR-001 — Repository Nil UUID Rejection — VERIFIED ✅

`_canonical_uuid()` 在 Session 创建前拒绝 nil UUID（`parsed.int == 0`）；所有 repository entry 经 `_validate_scope` / `_normalize_*_id` 均经由此 helper；一处修复全链生效。

#### 3. RR-002 — Guard Lambda/Self/Decorator Strictness — VERIFIED ✅

- `_direct_post_init_owner` 父链遇 `ast.Lambda`、`ast.ListComp`、`ast.SetComp`、`ast.DictComp`、`ast.GeneratorExp` 即返回 `None`。
- `__post_init__` 唯一参数名精确为 `self`（`_is_sole_self_param`）。
- `frozen` / `slots` 仅接受 `ast.Constant` 且 `value is True`；`frozen=1` / `slots=1` 真值常量被正确拒绝。

#### 4. Lifecycle Coordination — VERIFIED ✅

- `manual close` 后 `callback` no-op ✅
- `callback` 两次只 `close` 一次 ✅
- `register` 前 `callback` 无动作 ✅
- `register` exact-once ✅
- `close` 后 `register` no-op ✅

#### 5. JSON Deep-Freeze — VERIFIED ✅

- recursive Mapping → `MappingProxyType` ✅
- recursive tuple → tuple ✅
- list → `ValueError` ✅
- cycle detection ✅
- non-string key → `ValueError` ✅
- NaN/Infinity → `ValueError` ✅

## Open Questions

- 无。

## Residual Risk

- 输入校验分支类型系统不可达——合理防御性分支。
- 条件性/非顶层 `from dataclasses import dataclass` 不被识别为标准绑定——fail-closed 保守，production 无此类用法。
- 模块级重绑定按"全模块模糊"处理——保守 fail-closed，production 无此类用法。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。

RR-001（repository nil UUID rejection via `parsed.int == 0`）、RR-002（guard AST strictness: lambda/comprehension rejection, `_is_sole_self_param`, `ast.Constant value is True`）和 TERRA-S12-FRR-001（guard provenance/single-call/fail-closed/import-rebinding/module-level-only）均已独立验证闭合。Lifecycle/startup/RLS/JSON codec 全部通过。287 tests 全部通过，148 guard tests 全部通过，pyright 0 errors，无新回归。允许进入 code review completion。
