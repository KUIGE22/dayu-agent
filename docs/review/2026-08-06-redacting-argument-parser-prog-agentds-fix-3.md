# DeepSeek Fix 3 Artifact

## Current Gate

fix

## Source Re-review

`docs/reviews/code-review-20260806-213256.md`

## DR-002 Fix Status

**已修复。**

## 第二次方案为何被拒绝

第二次 fix（`docs/review/2026-08-06-redacting-argument-parser-prog-agentds-fix-2.md`）采用了 `prog` property getter/setter 设计。该方案在运行时正确（三项行为验收 exit 0，3 passed），但 Pyright 报 `reportIncompatibleVariableOverride`：typeshed 将 `ArgumentParser.prog` 声明为 `str` 实例属性，子类以 property 覆盖该属性触发类型检查错误。

Controller 判定："typeshed false positive" 不是放行理由——AGENTS.md 明确要求"任何新增或修改代码必须通过 pyright；禁止新增、扩散、掩盖或绕过类型错误"。因此第二次 fix artifact 的 completed 结论被拒绝。

## Changed Files

- `utils/validate_handoff_docs.py`

## 实现说明

### 方案：三个公开扩展点

按 controller 精确修复要求，删除 prog property 与 `_prog` 设计，改用三个公开且严格类型的扩展点：

| 方法 | 签名 | 实现 |
|---|---|---|
| `format_usage` | `() -> str` | `redact_secret_shapes(super().format_usage())` |
| `format_help` | `() -> str` | `redact_secret_shapes(super().format_help())` |
| `error` | `(message: str) -> NoReturn` | 先 `print_usage(stderr)` 输出脱敏 usage，再以脱敏 prog 与 message 构造错误行，调用 `self.exit(2, ...)` |

### 脱敏覆盖

- **usage 输出**: `format_usage()` 返回前对 `super().format_usage()` 全文脱敏。覆盖 `--help` 输出、error 输出中的 usage 行。
- **help 输出**: `format_help()` 返回前对 `super().format_help()` 全文脱敏。覆盖 `parser.format_help()` 直接调用。
- **error 输出**: `error(message)` 中 prog 与 message 均通过 `redact_secret_shapes` 脱敏后拼接 `"prog: error: message\n"` 格式行。

### 移除的代码

| 移除项 | 原因 |
|---|---|
| `@property prog` getter | `reportIncompatibleVariableOverride` |
| `@prog.setter` setter | 同上 |
| `_prog` 实例属性 | 随 property 设计一并移除 |

### 类型安全性

- `format_usage`: `() -> str`，全链 `str`
- `format_help`: `() -> str`，全链 `str`
- `error`: `(message: str) -> NoReturn`，`redact_secret_shapes` 接受 `str` 返回 `str`
- 无 `object`、`Any`、`type: ignore`、`Protocol`、`_print_message` override

## 验证命令与真实退出码

### 1. pytest（四项验收测试）

```
UV_CACHE_DIR=/Users/wsk/Documents/Codex/2026-08-06/tou/work/uv-cache uv run --no-project --with pytest==9.0.3 python -m pytest tests/test_validate_handoff_docs.py::test_redacting_argument_parser_redacts_secret_shape_in_help tests/test_validate_handoff_docs.py::test_redacting_argument_parser_redacts_secret_shape_in_formatted_help tests/test_validate_handoff_docs.py::test_redacting_argument_parser_redacts_secret_shape_in_prog tests/test_validate_handoff_docs.py::test_main_parser_error_redacts_secret_shape -q
```

退出码: **0** — 4 passed

### 2. Ruff

```
UV_CACHE_DIR=/Users/wsk/Documents/Codex/2026-08-06/tou/work/uv-cache uv run --no-project --with ruff==0.15.11 ruff check utils/validate_handoff_docs.py
```

退出码: **0** — All checks passed

### 3. Pyright

```
UV_CACHE_DIR=/Users/wsk/Documents/Codex/2026-08-06/tou/work/uv-cache uv run --no-project --with pyright==1.1.408 pyright utils/validate_handoff_docs.py
```

退出码: **0** — 0 errors, 0 warnings, 0 informations

## New Risks / Open Questions

1. **`self.prog` 在 error 中仍为原始值**: 移除 prog property 后 `self.prog` 保留原始未脱敏值；`format_usage()` 与 `format_help()` 在返回值中脱敏，`error()` 在构造错误行时显式对 `self.prog` 调用 `redact_secret_shapes`。若 argparse 未来在其他路径直接消费 `self.prog` 而未经过这三个扩展点，需新增覆盖。当前 argparse (3.13) 的三个主要输出路径（usage、help、error）均已覆盖。

2. **`format_help()` 全文脱敏的性能**: `format_help()` 返回前对超长帮助文本执行正则替换；当前帮助文本规模极小（仅 `--root`、`--json` 两个参数），无性能风险。

3. **无**: 无其他已知风险或开放问题。

## Residual Risk Classification

- **低**: 三个公开扩展点均为 argparse 文档化 API，稳定且可测试；所有类型严格为 `str`/`NoReturn`；Pyright 0 errors。
- **低**: 不影响 argparse 正常解析、SystemExit 行为、stdout/stderr 分发。

## Completion / Stop Status

**completed** — DR-002 已修复，四项 pytest 通过（exit 0），Ruff 通过（exit 0），Pyright 0 errors（exit 0），未修改允许列表外文件，无 scope creep。
