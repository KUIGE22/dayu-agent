# Code Review — Slice 1.2 Repository/Provider Final Re-review（Terra）

## Scope

- Mode: current changes / final independent re-review
- Branch: `codex/investment-platform`
- Base: `main`（`7c97c1f4e28af17d1a6d5c1b92706d793d9c7180`）及 accepted master plan `docs/plans/2026-08-10-investment-platform-restoration.md` 的 Slice 1.2 / S12-CTRL-01..08。
- Review clock: `2026-08-10 17:09:18 CST`（本机系统时钟）。
- Output file: `docs/reviews/code-review-20260810-slice-1.2-repository-provider-final-rereview-terra.md`
- Included scope: 根 `AGENTS.md`、accepted plan、implementation/adjudication/两轮 fix artifact、Terra/MiM 的初审与 rereview/final-rereview artifact；Slice 1.2 的 domain/repository/provider/service/guard、相关 unit tests、integration test 源码和 README。
- Excluded scope: Slice 1.3+、live/network/paid 操作、Docker/PG16 运行、既有 PG17 stack；未修改 production、tests、plan 或既有 artifacts。
- Parallel review coverage: 无（独立复核）。

## Findings

### TERRA-S12-FRR-001-未修复-中-guard 以装饰器末段名称和跨装饰器聚合判定 dataclass，允许非 frozen/slots 类绕过 `object` 禁令

- **入口/函数**: `_collect_escape_violations_from_source()` → `_collect_allowed_object_setattr_nodes()` → `_direct_post_init_owner()` → `_is_frozen_slots_dataclass()`。
- **文件(行号)**: `tests/investment/test_architecture_boundaries.py:287-296, 357-389, 434-498, 501-546`。
- **输入场景**: 在受扫描的 investment 源码中定义一个同名的本地 `dataclass` decorator（返回原类），并将其用于 `@dataclass(frozen=True, slots=True)` 的类；该类直接定义 `__post_init__(self)`，对本类字段调用精确三参数的 `object.__setattr__`。
- **实际分支**: `_is_frozen_slots_dataclass()` 仅以 `_call_name(decorator.func) == "dataclass"` 判断装饰器（451-455、460-464），不校验其来自标准库 `dataclasses.dataclass`；只要关键字值是 `ast.Constant(True)` 就分别将 `frozen`、`slots` 置真（465-478）。随后 `_direct_post_init_owner()` 和字段检查返回当前类，`_collect_allowed_object_setattr_nodes()` 将 `object` 节点加入 allowlist（535-545），外层 collector 因而跳过违规（291-296）。同一聚合还会把两个不同的 `@dataclass` 调用中的 `frozen=True` 与 `slots=True` 拼成允许条件。
- **预期行为**: S12-CTRL-08 要求豁免仅限于**直接的、标准 dataclass 的** `@dataclass(frozen=True, slots=True)` 内 `__post_init__(self)`；`frozen` 和 `slots` 是同一个精确 decorator call 的两个精确布尔参数。其余 `object` 形态必须命中 guard。
- **实际行为**: 本轮最小复现调用 `_collect_escape_violations_from_source()` 返回 `[]`；随后执行该同名 decorator 版本源码，普通可变 `Foo` 的 `__post_init__()` 成功把字段从 `before` 改为 `changed`。这证明 allowlist 可放行并非 frozen/slots dataclass 的真实可变写入，而非仅 AST 命名偏好。
- **直接证据**: 当前函数没有 import/provenance 校验，也没有要求单一 decorator 同时携带两个关键字；本轮本地复现输出为 `guard-violations []` 和 `fake-decorator-mutation changed`。现有负例矩阵覆盖 lambda/comprehension、改名 `self`、额外参数及 `frozen=1, slots=1`，但未覆盖 decorator shadowing、attribute callee 或 frozen/slots 分散在两个 decorator 的情形。
- **影响**: S12-CTRL-08 的唯一 `object.__setattr__` 逃逸豁免不再 fail-closed；后续 investment 源码可以通过一个无关的同名 decorator 把本应被禁止的宽 `object` 写入带入普通可变类，破坏 frozen DTO 防御性写回的结构边界。
- **建议改法和验证点**: 将 dataclass 识别收紧为模块级 `from dataclasses import dataclass` 的已解析直接绑定，并要求**同一个** `ast.Call(ast.Name("dataclass"), ...)` 同时拥有 `frozen=ast.Constant(True)` 与 `slots=ast.Constant(True)`；不接受 attribute callee、局部 shadowing 或跨 decorator 聚合。新增上述三类 negative，并保留现有合法 direct `@dataclass(frozen=True, slots=True)` positive，确保其不被误拒。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

## Open Questions

- 无。

## Residual Risk

- RR-003 属 reviewer environment/non-defect：本轮按授权未运行 Docker 或 PG16 integration；已读取 Controller/DeepSeek/MiM final artifact 的同树真实 PG16 14 passed、相关 322 passed 和 isolated coverage 证据，且未把本 sandbox 的 Docker 可用性计为开放代码 finding。
- 本轮运行的只读验证为：聚焦 unit `pytest -q tests/investment/test_identity_repositories.py tests/investment/test_architecture_boundaries.py tests/application/test_service_startup_preparation.py`（197 passed）、Slice 1.2 生产与相关测试的 pyright（0 errors/warnings/informations）、ruff（通过）及 `git diff --check`（通过）。
- RR-001 已闭合：`postgres_identity.py:101-126` 在 Session 创建前的统一 `_canonical_uuid()` 拒绝 nil UUID，所有 scope/ID normalization 均经此路径；对应五类 pre-session/zero-SQL tests 已通过。
- RR-002 已闭合的已列举面未回归：lambda、四类 comprehension、nested function/class、改名 `self`、positional-only/vararg/kw-only/kwargs、额外 call 参数及 `frozen=1, slots=1` 都由当前 AST guard 拒绝；直接合法 `@dataclass(frozen=True, slots=True)` 的 `__post_init__(self)` 仍不被误拒。但 finding 所述 decorator provenance/single-call 漏洞仍未闭合。
- TERRA-001、002（除已闭合的 guard 子项）、004、005 和 MiM 的 recursive deep-freeze/guard 观察均未见当前代码回归：startup probe 位于 Host/Fins 前，repository 的 private SQL 保留 tenant predicate 与 CAS，deep-freeze 仍递归复制 Mapping/tuple，未发现新的 future-owner import、`hasattr`、`getattr`、`Any`、`cast` 或 raw DSN 输出路径。

## Conclusion

**FAIL**。Open H/M/L = **0 / 1 / 0**。

RR-001 完整闭合，RR-002 的指定反例完整闭合且合法 direct `__post_init__(self)` 不被误拒；但同一 allowlist 对 decorator 的来源和单一精确 call 缺少约束，存在可复现的当前 guard bypass，故不能给出 PASS。
