# Code Review — Slice 1.2 Repository/Provider Final Closure Round 4（Terra）

## Scope

- Mode: 当前工作树最终 closure round4 re-review（只读）。
- Branch: `codex/investment-platform`。
- Base: accepted master plan `docs/plans/2026-08-10-investment-platform-restoration.md` 的 Slice 1.2 / S12-CTRL-01..08，以及当前工作树。
- Review clock: `2026-08-10`（本机系统时钟）。
- Output file: `docs/reviews/code-review-20260810-slice-1.2-repository-provider-final-closure-round4-terra.md`。
- Included scope: 根 `AGENTS.md`；accepted plan 的 S12-CTRL-01..08；全部 Slice 1.2 plan/review/adjudication/implementation/fix artifacts，重点复核 `TERRA-S12-FC-001` 与 round4 fix；当前 domain/repository/provider/service/lifecycle/AST guard、相关 unit/integration 测试和 README。
- Excluded scope: Slice 1.3+、live/network/push/PR、Docker/PG16 实际执行；未修改 code、tests、plan 或既有 artifact。
- Parallel review coverage: 无（独立复核）。

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- `RR-003` 属 reviewer environment / non-defect：本轮按授权未运行 Docker/PG16 integration，不能作为 code finding；其既有真实 PG16 证据不因本轮未执行而失效。
- 本轮复核了 repository nil-UUID pre-session admission、production startup admission/secret-safe failure、owned lifecycle/atexit exact-once、RLS/显式 tenant predicate/CAS，以及递归 JSON codec；静态路径和现有单元测试均未见回归。未执行 PG16 仅表示本报告不重新提供该环境实证。

## Verification Evidence

- **symtable 绑定真源**：`_collect_standard_dataclass_names()` 同时要求唯一的模块作用域标准 `from dataclasses import dataclass` 导入、无同名 import 歧义、且 `symtable.Symbol.is_imported() is True`、`is_assigned() is False`。独立最小矩阵确认 assignment、`for`、`with`、`except`、walrus、function、class、`match/case` capture 与 `del` 都把候选拒绝。
- **provenance / structural matrix**：`import fake as dataclass`、`from fake import dataclass`、`fake.dataclass` attribute callee、nested/local fake decorator、split decorators、duplicate keyword 均拒绝；唯一可信的 module-level direct `@dataclass(frozen=True, slots=True)`、top-level class、direct `__post_init__(self)` 正例放行。
- **单次 AST identity**：escape collector 仅解析一次待检源码，并把该 tree 传入 allowlist collector；独立检查该同一 tree 中唯一 `ast.Name(id="object")` 的 `id` 位于 allowlist，确认不存在 round4 前双 parse 导致的正例误报。
- **精确豁免边界**：仍要求 direct `object.__setattr__` call、三个位置参数/零 keyword、receiver 精确为 `self`、字段为本 class 的直接 `AnnAssign` 字段字符串字面量，并拒绝 nested function/class/lambda/comprehension、错误 receiver/字段/参数和非精确 boolean。
- **本轮执行**：`pytest -q tests/investment/test_architecture_boundaries.py tests/investment/test_identity_repositories.py tests/application/test_service_startup_preparation.py` → `207 passed`；受影响 Slice 文件 pyright → `0 errors, 0 warnings, 0 informations`；ruff → 通过；`git diff --check` → 通过。

## Conclusion

**PASS**。Open H/M/L = **0 / 0 / 0**。

TERRA-S12-FC-001 已闭合：模块级 pattern capture 与其它模块写绑定均由 `symtable` 真源 fail closed，且可信唯一正例不被误拒；round4 的同-tree node identity 修正也经独立检查成立。repository nil、startup/lifecycle、RLS/CAS 与 JSON codec 的既有 finding 未见回归。
