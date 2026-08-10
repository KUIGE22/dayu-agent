# Slice 1.2 code review fix artifact — Round 4（TERRA-S12-FC-001）

- **Work unit**：Investment Platform Restoration / Slice 1.2
- **Gate**：code review fix（round 4，final closure）
- **Adjudication**：`docs/reviews/code-review-adjudication-20260810-slice-1.2-repository-provider-codex.md`
  （round 4 段落）
- **Review input**：`docs/reviews/code-review-20260810-slice-1.2-repository-provider-final-closure-terra.md`
  （**FAIL**，TERRA-S12-FC-001）；MiM final closure（
  `code-review-20260810-slice-1.2-repository-provider-final-closure-mimo-native.md`）
  **PASS**（保留）。
- **Branch**：`codex/investment-platform`
- **Status**：**CLOSED / DUAL RE-REVIEW PASS**
- **Date**：2026-08-10

## TERRA-S12-FC-001（中）— 模块级 match/case capture 重绑定未被 guard 识别

**Finding**：`_module_scope_bound_names()` 手工枚举绑定形态，未覆盖
`ast.MatchAs` 的 capture pattern；模块级
`match fake: case dataclass: pass` 会把 `dataclass` 重绑定为 `fake`
（伪 decorator），guard 仍视其可信并放行普通可变类
`__post_init__` 内的 `object.__setattr__`（Terra 实测 `match_rebind
ALLOW`、`violations=[]`、`runtime_value=mutated`）。

**Fix**（`tests/investment/test_architecture_boundaries.py`，production
零改动）：按 Controller 指示停止手工枚举 pattern AST，改用 Python
标准库 **symtable** 作为模块绑定真源：

1. **单次 parse + source 传递**：`_collect_escape_violations_from_source()`
   将 `source` 传给 dataclass trust collector；
   `_collect_allowed_object_setattr_nodes(tree, source)` 复用调用方同一
   tree（保证豁免 node id 一致），内部不再 `ast.parse`，symtable 仅用
   `source`——修复同 source 双 parse 导致的 11 个合法 `object` 误报。
2. **信任判定**（`_collect_standard_dataclass_names(source)`）：
   - AST 层面：候选仍须是**唯一**模块级
     `from dataclasses import dataclass [as alias]` 导入绑定，模块作用域
     内无其它同名 import 模糊绑定（`_module_scope_import_bindings()`
     只扫描 import 绑定，不深入函数/类/lambda 作用域）；
   - symtable 层面：`symtable.symtable(source, "<module>", "exec")`
     的 `lookup(alias)` 必须 `is_imported()` 为 True 且
     `is_assigned()` 为 False——assignment/for/with/except/walrus/
     match capture/del/function/class 等一切模块级写绑定统一 fail
     closed，嵌套函数/类内部作用域由 symtable 天然隔离。
3. 删除手工枚举 helper `_module_scope_bound_names()` /
   `_iter_assigned_names()`。
4. 保留既有限制：top-level ClassDef（module-level-only 豁免）、direct
   `ast.Name` callee、唯一同一 call 同时携带
   `frozen=ast.Constant(True)` 与 `slots=ast.Constant(True)`。

**Tests**：负例矩阵新增 2 项（全部 fail-closed）：

- Terra 精确 match/case capture runtime-shape：模块级
  `from dataclasses import dataclass` 后
  `match fake: case dataclass: pass`，再 `@dataclass(frozen=True,
  slots=True)` 装饰含 `object.__setattr__` 的类；
- del 绑定边界：`from dataclasses import dataclass` 后
  `del dataclass`（符号表边界）。

合法 direct standard `@dataclass(frozen=True, slots=True)` positive
保留且不被误拒。

## Validation（本 fix 轮重跑）

```bash
pytest tests/investment tests/application/test_service_startup_preparation.py \
  tests/integration/investment -q        # 332 passed（guard 文件 150，含新增 2 负例）
pyright tests/investment/test_architecture_boundaries.py \
  dayu/services/startup_preparation.py dayu/investment/domain/source.py \
  dayu/investment/storage/postgres_identity.py dayu/investment/composition.py \
  dayu/services/investment_identity.py dayu/services/protocols.py \
  dayu/investment/storage/protocols.py   # 0 errors/warnings/informations
ruff check tests/investment/test_architecture_boundaries.py  # All checks passed
git diff --check                         # clean
```

- guard：`test_architecture_boundaries.py` **150 passed**（148 既有 +
  2 TERRA-S12-FC-001 负例：match/case capture、del binding）；
- investment + startup unit 289 passed；真实 PG16 integration 43 passed
  （含 identity repository / migrations / startup black-box），测试后
  Slice-owned 容器/网络为零、既有 PG17 未动；
- Terra 复现场景复验：match/case capture 源码扫描结果为
  `guard-violations ['禁止使用 object']`（原 `[]`）；del binding 同样
  命中；合法 direct standard decorator 仍为 `guard-violations []`；
  import-as / from-import / nested-local-fake 等既有负例无回归。

## Residual risks

| 风险 | 分类 |
| --- | --- |
| 条件性/非顶层 `from dataclasses import dataclass` 的信任语义保守（count==1 才可信） | 合理（仅承诺模块级唯一直接导入形态） |
| symtable 对模块级条件 import（`if cond: import fake as dataclass`）不置 is_assigned，靠 AST import 扫描兜底 | 已由 `_module_scope_import_bindings` 模块作用域扫描覆盖 |
| 输入校验分支类型系统不可达（原有防御分支） | 合理防御（见 implementation artifact） |

## Completion / stop status

- **Completed**：TERRA-S12-FC-001 修复并验证（symtable 绑定真源 + 单次
  parse 修正 11 个误报）；guard 148→150 passed、相关 332 passed、
  pyright 0、ruff clean、diff clean、零临时文件；adjudication 与
  implementation artifact 状态更新为 **REVIEW FIX APPLIED / AWAITING
  DUAL RE-REVIEW**（记录 MiM prior PASS 保留、Terra prior FAIL 已修复）。
- **Not run**：未启动 review/commit/push/PR/live/Slice 1.3；未改
  production、plan、README 及其它 tests。
- **Status**：**REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW**。

## Artifact-only closure（round4 dual re-review PASS）

- **Round 4 dual re-review**：
  - Terra final closure round4（
    `code-review-20260810-slice-1.2-repository-provider-final-closure-round4-terra.md`）
    **PASS**，open H/M/L = **0/0/0**；
  - MiM final closure round4（
    `code-review-20260810-slice-1.2-repository-provider-final-closure-round4-mimo-native.md`）
    **PASS**，open H/M/L = **0/0/0**。
- **Findings closure**：TERRA-S12-001..005、TERRA-S12-RR-001/002、
  TERRA-S12-FRR-001、TERRA-S12-FC-001 全部 **CLOSED**；RR-003
  （reviewer-environment / non-defect）与 MiM 001/002（stale-source）
  的 REJECT 保持事实记录。
- **Status**：**CLOSED / DUAL RE-REVIEW PASS**（历史 FAIL/PASS 与各轮
  裁决保持事实记录）。
