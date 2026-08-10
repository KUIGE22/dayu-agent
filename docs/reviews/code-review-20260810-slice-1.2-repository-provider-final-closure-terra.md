# Code Review — Slice 1.2 Repository/Provider Final Closure（Terra）

## Scope

- Mode: 当前工作树最终 closure re-review（只读）。
- Branch: `codex/investment-platform`。
- Base: accepted master plan `docs/plans/2026-08-10-investment-platform-restoration.md` 的 Slice 1.2 / S12-CTRL-01..08，以及当前工作树。
- Review clock: `2026-08-10`（本机系统时钟）。
- Output file: `docs/reviews/code-review-20260810-slice-1.2-repository-provider-final-closure-terra.md`。
- Included scope: 根 `AGENTS.md`；accepted master plan 的 Slice 1.2 / S12-CTRL-01..08；全部 Slice 1.2 implementation、adjudication、三轮 fix、plan review/acceptance/closure，以及 Terra/MiM 的初审、corrective rereview 与 final rereview artifacts；当前 Slice 1.2 domain/repository/provider/service/lifecycle/AST guard、相关 unit/integration 测试源码和 README。
- Excluded scope: Slice 1.3+、Docker/PG16 执行、live/network/paid 操作、既有 PG17、push/PR；未修改 code、tests、plan 或既有 artifacts。
- Parallel review coverage: 无（独立复核）。

## Findings

### TERRA-S12-FC-001-未修复-中-模块级 `match/case` capture 重绑定未被 guard 识别，仍可伪造可信 `dataclass` 并放行 `object.__setattr__`

- **入口/函数**: `_collect_escape_violations_from_source()` → `_collect_allowed_object_setattr_nodes()` → `_collect_standard_dataclass_names()` / `_module_scope_bound_names()` → `_is_frozen_slots_dataclass()`。
- **文件(行号)**: `tests/investment/test_architecture_boundaries.py:454-488, 491-544, 572-614, 617-667`。
- **输入场景**: 受扫描模块先使用模块级 `from dataclasses import dataclass`，随后以模块级 structural pattern capture 执行 `match fake: case dataclass: pass`；再以 `@dataclass(frozen=True, slots=True)` 装饰含直接 `__post_init__(self)` / `object.__setattr__(self, "value", value)` 的类。`fake` 是接受 dataclass keyword 并返回原类的伪 decorator。
- **实际分支**: `_collect_standard_dataclass_names()` 将 `dataclass` 加入 `bound`；随后调用 `_module_scope_bound_names()`。该 helper 处理 import、赋值、循环、with、except 等绑定，但没有处理 `ast.MatchAs` 的 capture pattern，因此未把 `case dataclass` 识别为模块级绑定，`dataclass` 未进入 `ambiguous`。`_is_frozen_slots_dataclass()` 随后把 direct `ast.Name("dataclass")` 的单个 call 视为可信，allowlist 放行其中的 `object` Name。
- **预期行为**: 本轮 closure 的明确边界是：仅未重绑定的、可信模块级 `from dataclasses import dataclass` 的直接 Name decorator 可获得豁免；任何模块级重绑定都必须 fail closed。S12-CTRL-08 的 `object.__setattr__` 例外只能服务于真实 frozen+slots DTO 的受控 writeback。
- **实际行为**: 本轮最小复现调用 collector 返回 `[]`（ALLOW）。执行同一源码后，`dataclass is fake` 为 `True`，该普通可变 `Foo` 实例先写入 `"original"` 再调用 `__post_init__()`，字段实际变为 `"mutated"`。这证明不是抽象 AST 偏差，而是可执行的 guard bypass。
- **直接证据**: `_module_scope_bound_names()` 的分支集合见 514-543 行，其中无 `ast.Match` / `ast.MatchAs` / 其它 pattern capture 处理；`_collect_standard_dataclass_names()` 只以该 helper 的结果裁决模糊绑定（485-488 行）。本轮独立命令输出：`match_rebind ALLOW`；同一运行时复现输出：`violations=[]`、`decorator_is_fake=True`、`runtime_value=mutated`。
- **影响**: architecture guard 可在受扫描的 investment 源码中错误放行 `object.__setattr__`，使普通可变类伪装为 frozen+slots dataclass，破坏本 slice 对宽 `object` 逃逸 fail-closed 的硬边界。该漏洞正处于 TERRA-S12-FRR-001 已收紧的 decorator provenance / rebinding 防线内，故 final closure 不可 PASS。
- **建议改法和验证点**: 让模块级绑定收集器覆盖 structural-pattern capture（至少 `ast.MatchAs` 的 `name`，并按其它会绑定名字的 pattern 节点完整处理），或采用能证明“模块级无任何写绑定”的更完整 AST binding collector。新增上述 `match fake: case dataclass` negative，断言包含 `禁止使用 object`；同时保留当前唯一合法 direct standard positive，并复跑现有 fake/local/attribute/split/duplicate/import-as/from-import/nested-local-shadow matrix。
- **修复风险（低/中/高）**: 低（只收紧测试 guard；应避免把模式中非绑定的 `MatchValue` 误当重绑定）。
- **严重程度（低/中/高/严重）**: 中。

## Open Questions

- 无。该 finding 有当前 guard 的完整 AST 数据路径和同源运行时复现。

## Residual Risk

- RR-003 是 reviewer environment/non-defect，不作为代码 finding：本轮按授权未运行 Docker/PG16 integration，也未把本环境的镜像或 coverage 状态计入 open issue。
- 除本 finding 外，RR-001/002 已复核无回归：repository `_canonical_uuid()` 在 session 创建前拒绝 nil UUID；lambda/comprehension、非精确 `self`、非精确 boolean、嵌套 function/class、跨类字段、错误 receiver、错误参数和非字面字段均 fail closed。
- 本轮独立 guard matrix：合法 direct standard positive 为 ALLOW；`fake.dataclass`、split decorators、duplicate keyword、`import fake as dataclass`、`from fake import dataclass` 与 nested local shadow 均为 REJECT；仅模块级 `match/case` capture rebind 仍为 ALLOW。
- 只读验证已通过：`pytest -q tests/investment/test_architecture_boundaries.py tests/investment/test_identity_repositories.py tests/application/test_service_startup_preparation.py`（205 passed）；对 Slice 1.2 production/相关 tests 的 pyright（0 errors/warnings/informations）、ruff（通过）与 `git diff --check`（通过）。
- 对 repository/provider/lifecycle/RLS/JSON codec 的真实路径静态复核未见本轮回归：transaction-local `set_config` 和显式 private-tenant predicate/CAS 仍在；recursive deep-freeze/JSON codec、default-provider admission、secret-safe failure、auto-owned lifecycle exact-once 与 explicit-provider caller ownership 仍保持。该结论不替代本轮未执行的 PG16 实证。

## Conclusion

**FAIL**。Open H/M/L = **0 / 1 / 0**。

TERRA-S12-FRR-001 的已列 fake/local/attribute/split/duplicate/import-as/from-import/nested shadow 反例已闭合，且合法 positive 未误拒；但新的模块级 pattern-capture 重绑定在当前实现中仍能真实放行普通可变类的 `object.__setattr__`。在该收紧点修复并复审前，不应宣告 Slice 1.2 final closure PASS。
