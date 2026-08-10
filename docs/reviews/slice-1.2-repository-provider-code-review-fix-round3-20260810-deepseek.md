# Slice 1.2 code review fix artifact — Round 3（TERRA-S12-FRR-001）

- **Work unit**：Investment Platform Restoration / Slice 1.2
- **Gate**：code review fix（round 3，final re-review）
- **Adjudication**：`docs/reviews/code-review-adjudication-20260810-slice-1.2-repository-provider-codex.md`
  （round 3 段落）
- **Review input**：`docs/reviews/code-review-20260810-slice-1.2-repository-provider-final-rereview-terra.md`
  （**FAIL**，TERRA-S12-FRR-001）；MiM final re-review（
  `code-review-20260810-slice-1.2-repository-provider-final-rereview-mimo-native.md`）
  **PASS**（保留）。
- **Branch**：`codex/investment-platform`
- **Status**：**CLOSED / DUAL RE-REVIEW PASS**
- **Date**：2026-08-10

## TERRA-S12-FRR-001（中）— guard 以装饰器末段名称和跨装饰器聚合判定 dataclass

**Finding**：`_is_frozen_slots_dataclass()` 仅以
`_call_name(decorator.func) == "dataclass"` 判断装饰器，不校验其来自
标准库 `dataclasses.dataclass`；只要关键字值为 `ast.Constant(True)`
就分别将 `frozen`、`slots` 置真，且同一聚合会把两个不同
`@dataclass(...)` 调用中的 `frozen=True` 与 `slots=True` 拼成允许条件。
模块级同名伪 decorator（返回原类）可让普通可变类的 `__post_init__`
对自身字段执行 `object.__setattr__` 真实改写而绕过豁免（Terra 实测
`guard-violations []` + `fake-decorator-mutation changed`）。

**Fix**（`tests/investment/test_architecture_boundaries.py`，production
零改动）：

1. **Provenance（来源绑定）**：新增 `_collect_standard_dataclass_names()`
   ——只接受模块顶层 `from dataclasses import dataclass`（含 `as`
   别名）的直接绑定；该名字在模块作用域被重新赋值、被同名 def/class
   覆盖、重复导入或其它模糊绑定形态（`_module_scope_bound_names()` 沿
   模块作用域子树收集，不深入函数/类/lambda 内部作用域）一律对该名字
   fail closed。
2. **Import 绑定计入重绑定（hardening）**：`_module_scope_bound_names()`
   对 `import fake as dataclass` / `from fake import dataclass` 的本地
   别名同样计为模块作用域绑定；标准 dataclasses 目标导入由 collector
   单独处理，其余 import 一律视作潜在重绑定并 fail closed。
3. **仅 module-level ClassDef 可豁免（hardening）**：豁免类必须是
   **直接**挂在模块顶层的 ClassDef（parent 为 `ast.Module`）；
   `_collect_frozen_slots_fields_by_class()` 与
   `_direct_post_init_owner()` 双侧校验，函数/类体内嵌套的同形类（可
   由局部同名伪 decorator 遮蔽）一律拒绝——已确认 `dayu/investment`
   生产代码无 nested dataclass 用法。
4. **Single direct call（单一直接调用）**：`_is_frozen_slots_dataclass()`
   只接受 decorator callee 为**直接** `ast.Name` 且其 id 属于可信标准
   名字集合；attribute callee（`fake.dataclass`）、无标准导入、同名伪
   decorator 全部不满足；整个类必须恰好命中**一个**这样的 decorator
   call。
5. **Same-call keyword（同一 call 双关键字）**：该唯一 call 必须同时
   携带 `frozen=ast.Constant(True)` 与 `slots=ast.Constant(True)`，
   不得跨 decorator 聚合；`frozen`/`slots` 关键字重复出现或值非精确
   `True` 一律 fail closed；call 携带位置参数视为非精确形态拒绝。
6. 移除已无使用点的 `_call_name()`（原末段名称判定入口）。

**Tests**：负例矩阵新增 8 项（全部 fail-closed）：

- 模块级同名伪 decorator（`def dataclass(cls): return cls`，无标准
  导入）；
- attribute callee（`import fake; @fake.dataclass(frozen=True,
  slots=True)`）；
- 两个标准 dataclass call 分散 frozen/slots（`@dataclass(frozen=True)`
  + `@dataclass(slots=True)` 叠放）；
- 标准 import 后模块级重绑定（`from dataclasses import dataclass` 后
  `dataclass = fake_dataclass`）；
- 重复 `frozen` 关键字；
- 标准 import 后 `import fake as dataclass` 重绑定；
- 标准 import 后 `from fake import dataclass` 重绑定；
- 函数内局部同名伪 decorator + nested class。

合法 direct standard `@dataclass(frozen=True, slots=True)` positive
保留且不被误拒。

## Validation（本 fix 轮重跑）

```bash
pytest tests/investment tests/application/test_service_startup_preparation.py \
  tests/integration/investment -q        # 330 passed（guard 文件 148，含新增 8 负例）
pyright tests/investment/test_architecture_boundaries.py \
  dayu/services/startup_preparation.py dayu/investment/domain/source.py \
  dayu/investment/storage/postgres_identity.py dayu/investment/composition.py \
  dayu/services/investment_identity.py dayu/services/protocols.py \
  dayu/investment/storage/protocols.py   # 0 errors/warnings/informations
ruff check tests/investment/test_architecture_boundaries.py  # All checks passed
git diff --check                         # clean
```

- guard：`test_architecture_boundaries.py` **148 passed**（140 既有 +
  8 TERRA-S12-FRR-001 负例，其中 3 项为本轮 Controller hardening 追加：
  import-as/from-import 重绑定、nested-local-fake decorator）；
- investment + startup unit 287 passed；真实 PG16 integration 43 passed
  （含 identity repository / migrations / startup black-box），测试后
  Slice-owned 容器/网络为零、既有 PG17 未动；
- Terra 复现场景复验：同名伪 decorator 源码扫描结果为
  `guard-violations ['禁止使用 object']`（原 `[]`）；合法 direct
  standard decorator 仍为 `guard-violations []`；import-rebinding 与
  nested-local-fake 三个 hardening 场景同样全部命中。

## Residual risks

| 风险 | 分类 |
| --- | --- |
| 条件性/非顶层 `from dataclasses import dataclass` 不被识别为标准绑定（fail-closed 保守） | 合理（本 guard 仅承诺模块级直接导入形态） |
| 模块级重绑定按“全模块模糊”处理：import 在 class 定义之后出现的重绑定也会拒绝该类的豁免 | 保守 fail-closed，production 无此类用法（已扫描确认） |
| 嵌套作用域内的局部标准 dataclass import + 类定义不被豁免 | 保守 fail-closed（豁免仅限直接 module-level ClassDef，已确认 production 无 nested dataclass） |
| 输入校验分支类型系统不可达（原有防御分支） | 合理防御（见 implementation artifact） |

## Completion / stop status

- **Completed**：TERRA-S12-FRR-001 修复并验证（含 Controller hardening：
  Import/ImportFrom 绑定计入重绑定、豁免仅限直接 module-level ClassDef）；
  guard 140→148 passed、相关 330 passed、pyright 0、ruff clean、diff
  clean；adjudication 与 implementation artifact 状态更新为 **REVIEW
  FIX APPLIED / AWAITING DUAL RE-REVIEW**（记录 MiM prior PASS 保留、
  Terra prior FAIL 已修复）。
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
