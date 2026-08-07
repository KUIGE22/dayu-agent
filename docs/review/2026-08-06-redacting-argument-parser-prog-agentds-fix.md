# DeepSeek Fix Record

## Metadata

- **current gate**: fix
- **source review**: `docs/reviews/code-review-20260806-212542.md`
- **accepted finding**: DR-001-未修复-[高]-帮助输出仍会泄露 secret-shaped prog
- **work unit / slice**: redact argparse prog secret shapes / S1
- **controller decision**: 仅 DR-001 为 accepted finding；不处理其他猜测性事项，不扩大 scope

## Fix Status

### DR-001 — fixed

**根因**: argparse 的 `format_help()` 通过 `HelpFormatter._format_usage()` 直接访问 `self._prog` 构建 usage 行，不经过 `ArgumentParser.format_usage()`。当前实现的 `format_usage()` 和 `error()` 覆盖未保护 `--help` 路径，`print_help()` → `format_help()` → HelpFormatter 直接使用原始 prog。

**修复**: 覆盖 `_print_message` —— argparse 所有输出写入文件句柄前的唯一汇聚点。`print_help`、`print_usage`、`exit` 三条路径均经过此方法，在此处统一脱敏建立不变量，避免逐个路径打补丁。

| 项目 | 结果 |
|------|------|
| finding id | DR-001 |
| status | fixed |
| changed files | `utils/validate_handoff_docs.py` |

## Changed Files

- `utils/validate_handoff_docs.py`
  - 新增 `_SupportsStrWrite` Protocol：匹配 typeshed 中 `argparse._print_message` 的 `SupportsWrite[str]` 参数类型，保证 `_print_message` 覆盖签名满足严格类型检查。
  - `RedactingArgumentParser` 类新增 `_print_message` 方法覆盖：在调用父类写入前对所有 message 文本执行 `redact_secret_shapes`。
  - 保留已有的 `format_usage()` 和 `error()` 覆盖作为纵深防御。
  - 更新类 docstring 反映统一输出脱敏设计。

## Implementation Notes

- `_print_message` 是 argparse 内部方法，但它是 `print_help()`、`print_usage()` 和 `exit()` 写入输出的唯一汇聚点，覆盖它即可保护所有 argparse 对外输出。
- `_SupportsStrWrite` Protocol 仅含 `write(self, __s: str) -> object`，与 typeshed 中 `SupportsWrite[str]` 签名一致，既满足 LSP 覆盖兼容性，也满足 super 调用类型安全。
- help 路径保持 stdout 输出与 SystemExit(0)；error 路径保持 stderr、标准 usage/error 格式与 SystemExit(2)；正常解析不受影响。

## Verification

### 验收测试

```sh
UV_CACHE_DIR=/Users/wsk/Documents/Codex/2026-08-06/tou/work/uv-cache uv run --no-project --with pytest==9.0.3 python -m pytest tests/test_validate_handoff_docs.py::test_redacting_argument_parser_redacts_secret_shape_in_help tests/test_validate_handoff_docs.py::test_redacting_argument_parser_redacts_secret_shape_in_prog tests/test_validate_handoff_docs.py::test_main_parser_error_redacts_secret_shape -q
```

- **退出码**: 0
- **结果**: 3 passed in 0.03s

### Ruff

```sh
UV_CACHE_DIR=/Users/wsk/Documents/Codex/2026-08-06/tou/work/uv-cache uv run --no-project --with ruff==0.15.11 ruff check utils/validate_handoff_docs.py
```

- **退出码**: 0
- **结果**: All checks passed!

### Pyright

```sh
UV_CACHE_DIR=/Users/wsk/Documents/Codex/2026-08-06/tou/work/uv-cache uv run --no-project --with pyright==1.1.408 --with pytest==9.0.3 pyright utils/validate_handoff_docs.py tests/test_validate_handoff_docs.py
```

- **退出码**: 1（仅 test 文件中 pytest 的 `reportMissingImports`，属环境预存，非新增）
- **结果**: `utils/validate_handoff_docs.py` — 0 errors, 0 warnings, 0 informations

## New Risks / Open Questions

- **argparse 子命令路径**: 若未来使用 `add_subparsers()` 且子命令解析器的 prog 包含 secret 形状，当前 `_print_message` 覆盖一样保护子命令的输出（子命令的 help/error 输出同样经过 `_print_message`）。
- **显式 `print_*` 调用**: `_print_message` 覆盖保护所有通过 `print_help()`、`print_usage()` 的输出，无论调用方是 argparse 自身还是外部代码。
- **`format_help()` 返回值**: 若调用方获取 `format_help()` 返回值后自行 print（而非通过 `print_help()`），则该路径不受 `_print_message` 保护。但当前代码库无此用法。

## Residual Risk Classification

**低**。`_print_message` 覆盖保护了 argparse 所有标准输出路径（help/usage/error）。`format_help()` 返回值如在别处被外部代码格式化输出则不受保护，但当前项目无此模式，且已有的 `format_usage()` 覆盖提供额外安全网。

## Completion Status

**completed** — 仅 DR-001 accepted finding 已修复；未修改允许列表外文件；未 commit、push 或创建 PR。
