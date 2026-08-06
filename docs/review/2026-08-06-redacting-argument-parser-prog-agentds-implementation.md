# RedactingArgumentParser prog secret-shape 脱敏 — implementation artifact

## current gate

implementation

## work unit

redact argparse prog secret shapes

## assigned slice

S1 — 修复共享 RedactingArgumentParser：当 argparse 的 prog 本身含 secret-shaped 文本时，usage 行和错误前缀都必须脱敏，同时保持 argparse 标准语义。

## scope / non-goals

### In scope
- `RedactingArgumentParser.format_usage()` — 脱敏 usage 行中的 prog
- `RedactingArgumentParser.error()` — 脱敏 `prog: error:` 前缀中的 prog 与 message
- 保持 SystemExit(2)、stderr 输出、标准 usage 格式、正常参数解析

### Non-goals
- 不修改 `tests/test_validate_handoff_docs.py`
- 不修改其他源码、配置、文档
- 不改动 `SECRET_KEY_PATTERN` / `REDACTED_SECRET` / `redact_secret_shapes`

## changed files

- `utils/validate_handoff_docs.py` — 重写 `RedactingArgumentParser.format_usage()` 和 `error()`
- `docs/review/2026-08-06-redacting-argument-parser-prog-agentds-implementation.md` — 本 artifact

## 实现项

### 根因

`RedactingArgumentParser` 原先只重写 `error(message)`，对 `message` 做脱敏后调用 `super().error()`。但 argparse 父类 `error()` 内部还使用了 `self.prog` 生成两处输出：

1. `self.print_usage(sys.stderr)` → 生成 `usage: {self.prog} [-h] ...` 格式的 usage 行
2. `self.exit(2, f'{self.prog}: error: {message}\n')` → 生成 `prog: error: ...` 格式的错误前缀

当 `prog` 本身包含 secret-shaped 文本时，这两处都会泄漏原始 `prog` 值。

### 修复策略

采用覆盖 argparse 公开扩展点的方式，不修改 `__init__`，避免类型签名冲突：

1. **`format_usage()`** — 覆盖 argparse 的 usage 格式化入口。对整个 usage 字符串调用 `redact_secret_shapes()`，统一脱敏 usage 行中的 prog 及其他可能泄漏的敏感子串。

2. **`error()`** — 完全接管错误输出流程，与父类保持一致的 `print_usage` → `exit(2)` 流程，但在构建 `prog: error:` 格式字符串时对 `self.prog` 和 `message` 分别做脱敏处理。

### 为什么不用 `__init__` 中修改 prog

在 `__init__` 中通过 `*args: object` / `**kwargs: object` 透传会导致 pyright 类型检查失败（`object` 无法赋值给 argparse 父类的各类型化参数），产生 13 个新增类型错误。使用 `format_usage` + `error` 覆盖方式完全避免了签名问题，零新增类型错误。

## 逐条验证命令与结果

### pytest
```
UV_CACHE_DIR=... uv run --no-project --with pytest==9.0.3 python -m pytest \
  tests/test_validate_handoff_docs.py::test_redacting_argument_parser_redacts_secret_shape_in_prog \
  tests/test_validate_handoff_docs.py::test_main_parser_error_redacts_secret_shape -q
```
结果：2 passed in 0.10s ✓

### ruff
```
UV_CACHE_DIR=... uv run --no-project --with ruff==0.15.11 ruff check utils/validate_handoff_docs.py
```
结果：All checks passed! ✓

### pyright
```
UV_CACHE_DIR=... uv run --no-project --with pyright==1.1.408 --with pytest==9.0.3 \
  pyright utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py
```
结果：`utils/validate_handoff_docs.py` 零错误。`tests/test_validate_handoff_docs.py` 仅有 1 个预存的 pytest import 解析错误（非本次修改引入）。✓

## docs decision

根据 CLAUDE.md 的 README 触发规则，本次修改仅触及 `utils/validate_handoff_docs.py`，不属于 `dayu/engine/`、`dayu/host/`、`dayu/fins/`、`dayu/config/`、`tests/`、`dayu/cli/`、`dayu/render/` 或分层边界变更，不触发任何 README 更新。

## plan gaps

无。S1 的范围描述精确覆盖了根因和修复点。

## residual risks / uncovered areas

1. **`format_help()` 未覆盖** — 当通过 `--help` / `-h` 输出帮助文本时，`self.prog` 可能出现在帮助文本中且未被脱敏。当前测试未覆盖此路径，任务描述中也未要求覆盖 `--help`。若未来需要在 help 输出中脱敏 prog，可同样覆盖 `format_help()` 方法。

2. **`print_usage()` 直接调用** — 若有代码直接调用 `parser.print_usage()` 而不经过 `error()`，usage 输出中的 prog 会经过 `format_usage()` 被脱敏（已覆盖）。

3. **非 error 路径的 prog 使用** — argparse 内部还有一些边缘路径（如 `add_subparsers` 相关的错误消息）可能直接使用 `self.prog` 而不经过 `error()`。这些路径未在当前测试中触发，也未在任务范围中要求。

## completion/stop status

**completed** — S1 实现、验证、artifact 均已完成。未修改允许列表之外的文件，argparse 标准语义完整保留。
