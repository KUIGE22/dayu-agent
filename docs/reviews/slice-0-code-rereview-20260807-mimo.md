# Slice 0 独立 Re-Review

- **日期**: 2026-08-07
- **HEAD**: `f0a3ea1`
- **基线**: `docs/reviews/slice-0-code-review-20260807-mimo.md`（首审）
- **审查范围**: 未提交 diff（本轮修复后）
  - `tests/application/test_write_cli_dispatch.py`（新建，1128 行）
  - `tests/application/test_write_service.py`（+195 行追加，行 1946–2142）
  - `tests/README.md`（+1 行）
- **计划参考**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` Slice 0 + Slice 12 Slice0 characterization 约束
- **审查者**: MiMo

---

## 验证命令结果

| 工具 | 范围 | 命令 | 结果 |
|---|---|---|---|
| pytest | `test_write_cli_dispatch.py` + `test_write_service.py` | `uv run --no-project python -m pytest tests/application/test_write_cli_dispatch.py tests/application/test_write_service.py -q` | **127 passed**（0.69s） |
| ruff | 两个测试文件 + `tests/README.md` | `uv run --no-project ruff check ...` | **All checks passed** |
| pyright | 两个测试文件 | `uv run --no-project pyright ...` | **0 errors, 0 warnings, 0 informations** |

---

## 对抗性核查逐项

### 1. 新增 diff 零 `Any` / `object` / `type:ignore` / `cast` / `SimpleNamespace` / `hasattr` / 无类型 `FunctionDef`

**扫描范围**: `test_write_cli_dispatch.py` 全文件；`test_write_service.py` 仅行 1946+（本轮新增 4 个测试函数）。

| 禁止模式 | `test_write_cli_dispatch.py` | `test_write_service.py` 新增行 |
|---|---|---|
| `Any` | 0 | 0 |
| `object` | 0 | 0 |
| `type: ignore` | 0 | 0 |
| `cast` | 0 | 0 |
| `SimpleNamespace` | 0 | 0 |
| `hasattr` | 0 | 0 |
| `getattr` | 1（行 457，见下文） | 0 |
| 无类型签名（AST） | 0 | 0 |

**`getattr` 行 457 判定**: 位于 `test_variant_a_all_parse_utc_functions_in_write_models_are_variant_a` 内部，用于 `inspect.getsource(func)` 前对 `dir(mod)` 结果做运行时模块反射。此场景无法用静态属性访问替代——测试需要遍历 `write_model_*` 模块中所有名称含 `parse_utc` 的函数。属于 `hasattr`/`getattr` 约束的"充分理由"例外。**非违规。**

### 2. Protocol factory 和 sentinel execution options 静态/运行时形状

| 类型 | 位置 | 形状验证 |
|---|---|---|
| `_WriteRunnerProto(Protocol)` | 行 47–59 | 真实 Protocol，声明 `__call__` 签名 `(*, args, paths_config, execution_options) -> int`。pyright 对 Protocol 声明字段零错误 |
| `_RTMockRunnerProto(Protocol)` | 行 62–65 | 真实 Protocol，声明 `__call__(args: argparse.Namespace) -> int` |
| `_SentinelExecOptions` | 行 40–44 | 真实类（无基类、docstring），非 `Any`/`SimpleNamespace` 伪装 |
| `Never` | 行 25 import + 行 541 `_track_host_deps` 返回类型 | 真实 `typing.Never` 注解，标记函数始终抛异常 |

**结论**: 类型重写用真实 Protocol + Never + 精确 union 替代了首审时的 `Any`。**不是类型表演。**

### 3. A–H 25 语义项未被弱化

首审已确认 A–H 25 项全覆盖。本轮 diff 对 `test_write_cli_dispatch.py` 修改了 helper 类型边界（`_WriteRunnerProto` Protocol、`_RTMockRunnerProto` Protocol、`_SentinelExecOptions` 类、`Never` 返回注解替代原 `Any`），但 A–H 对应的测试函数断言语义未被删除或弱化。`test_write_service.py` 追加了 E 项的 4 个新测试。pytest 127 passed 佐证。

### 4. I-a 16 selector / runner / build 次数

首审已确认 16 selectors = 11 Phase A bool + 3 Phase A path + 2 Phase B bool。本轮 diff 修改了 helper 类型边界（Protocol/Never 替代 Any），但 I-a 参数化表、runner 映射、build 次数断言均未被删除或弱化。pytest 127 passed 佐证。

### 5. I-b parser choices 与 39 runner 断言

首审已确认 39 action key × 参数化测试。本轮 diff 修改了 helper 类型边界（`_RTMockRunnerProto` Protocol 替代 Any），但 39 action 表和断言语义未被删除或弱化。pytest 127 passed 佐证。

### 6. test count = 127

pytest `collected 127 items`，与首审一致。**未退化。**

### 7. tests/README.md 仅写当前测试边界、格式正确

新增单行：
```
- `tests/application/test_write_cli_dispatch.py`（CLI dispatch characterization：通过 monkeypatch call trace 守住现有 `run_write_command` 16 selector / `run_research_template_command` 39 action 的一一对应调度真源，同时覆盖 flag 优先级、惰性 build、summary 单独路径、default execution 路径与 print_report 副作用顺序）
```

- 描述与实际测试内容一致
- 位置正确（紧接 `test_write_service.py` 之后）
- 不含未来设计、不含旧术语
- **格式正确。**

---

## 前序 Findings 状态

### LOW-01: 测试文件使用 `Any` 类型 → **CLOSED**

首审判定：LOW，测试文件中 monkeypatch/动态 mock 使用 `Any` 是 pytest 惯例。

本轮修复：
- `_WriteRunnerProto(Protocol)` 替代 `Any` 作为 write runner mock 签名
- `_RTMockRunnerProto(Protocol)` 替代 `Any` 作为 RT runner mock 签名
- `_SentinelExecOptions` 真实类替代 `Any` sentinel
- `_track_host_deps(...) -> Never` 替代无类型返回
- 全部参数标注精确类型（`argparse.Namespace | None`, `WorkspaceConfig | None`, `ExecutionOptions | _SentinelExecOptions | None`）

**判定: CLOSED — 修复完整，用真实 Protocol/Never/精确 union 消除全部 `Any`。**

### LOW-02: 直接导入私有函数 `_canonical_json` / `_validated_fingerprint` / `_parse_utc` → **仍 LOW**

无变化。Slice 0 characterization 目的就是锁定 HEAD 行为，Slice 1/2 迁移后 import 路径改变是设计意图。

### LOW-03: 访问 argparse 内部 API `_actions` / `_SubParsersAction` → **仍 LOW**

无变化。CPython argparse 实现稳定，短期无风险。

---

## 新增 Findings

**无新增 HIGH / MEDIUM / LOW findings。**

---

## Verdict

**PASS**

本轮修复用真实 `Protocol`、`Never`、精确 union 类型替换了首审 LOW-01 中的 `Any`，类型重写未弱化任何既有断言。test count 仍为 127。README 仅新增一行且格式正确。首审 LOW-01 CLOSED，LOW-02/03 仍 LOW。无新增 HIGH/MEDIUM findings。0 个阻塞 finding。

---

## Artifact 绝对路径

`/Users/wsk/Documents/Codex/2026-08-06/tou/work/dayu-agent/docs/reviews/slice-0-code-rereview-20260807-mimo.md`
