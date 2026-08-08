# PR #1 P0 独立 Re-Review — MiMo 第二路

**日期**: 2026-08-07
**基线**: 6e22cb57ac180ab69483baf0af1b45efefad3233
**审查范围**: 4 文件未提交 P0 diff

---

## Verdict: BLOCKED

**阻塞 finding**: F1 兼容性 re-export 违反编码硬约束。

---

## F1: DayuCliArgumentParser 脱敏与共享 redaction 叶模块

### F1.1 脱敏覆盖完整性 — CLOSED

| 路径 | 证据 |
|------|------|
| `format_usage()` | `dayu/redaction.py:79-81` — `redact_secret_shapes(super().format_usage())` |
| `format_help()` | `dayu/redaction.py:83-85` — `redact_secret_shapes(super().format_help())` |
| `error()` | `dayu/redaction.py:87-95` — `prog` 和 `message` 均脱敏，保持 exit(2) |
| `DayuCliArgumentParser.error()` | `dayu/cli/arg_parsing.py:30-47` — 继承 `RedactingArgumentParser`，覆写 `error()` 中缺失子命令时输出 help（help 已被父类脱敏） |

四条输出路径（usage/help/error/prog）全部覆盖。

### F1.2 叶模块隔离 — CLOSED

`dayu/redaction.py` 仅依赖 `argparse`、`re`、`sys`、`typing.NoReturn`，不依赖任何 `dayu.*` 子包。docstring 明确声明叶模块定位。`utils/` 工具脚本通过 `from utils.validate_handoff_docs import ...` 间接引用，不会触发 CLI/Engine 初始化。

### F1.3 反向依赖 — NOT CLOSED（BLOCKED）

**问题**: `validate_handoff_docs.py` 第 12-18 行将 `SECRET_KEY_PATTERN` 和 `REDACTED_SECRET` 以 `# noqa: F401` 标记重新导出。注释明确写"由 codex_review_gate 等外部模块通过本模块引用"。

**影响**: `codex_review_gate.py`、`prepare_deepseek_task.py`、`dual_model_pipeline_check.py` 及其测试均通过 `validate_handoff_docs.SECRET_KEY_PATTERN` / `validate_handoff_docs.redact_secret_shapes` 等路径访问这些符号。

**违反**: 编码硬约束——"禁止兼容性 re-export：仅为保持旧导入路径而转发符号"。正确做法是更新外部消费者直接 `from dayu.redaction import ...`，而非在 `validate_handoff_docs` 中保留转发。

**注意**: `redact_secret_shapes` 和 `RedactingArgumentParser` 在 `validate_handoff_docs.py` 自身代码中也有使用（如第 1147、1155、3209 行），所以它们的 import 本身不是纯兼容性转发，但 `SECRET_KEY_PATTERN` 和 `REDACTED_SECRET` 是。

### F1.4 Handoff gate 兼容性 — CLOSED

- `from utils.validate_handoff_docs import SECRET_KEY_PATTERN` ✓（通过 re-export 仍可用）
- `validate_handoff_docs.RedactingArgumentParser` ✓（import + 自身使用）
- `validate_handoff_docs.redact_secret_shapes` ✓（import + 自身使用）
- `contains_secret_shape()` 现在委托给 `has_secret_shapes()` ✓
- 370 个 handoff docs 测试全部通过 ✓

---

## C10: WriteService.print_report 中 7 处 assert 替换

### C10.1 全部 7 处 assert 已替换为 if/raise ValueError — CLOSED

| # | 基线行号 | 新守卫行号 | 变量 |
|---|----------|-----------|------|
| 1 | 667 | 665-670 | `challenger_promotion_proposal_input` |
| 2 | 747-749 | 750-755 | `challenger_config_change_approval_request` |
| 3 | 751-753 | 756-761 | `challenger_config_change_approval_output` |
| 4 | 878 | 886-891 | `proposal` |
| 5 | 897 | 910-915 | `proposal` |
| 6 | 928 | 946-951 | `routing_preflight_approval_request` |
| 7 | 929 | 952-957 | `routing_preflight_approval_output` |

**验证**: `grep -n "assert" dayu/services/write_service.py` 返回空。`test_print_report_source_contains_no_assert_statements` 使用 AST 解析验证零 `ast.Assert` 节点，通过。

### C10.2 python -O 有效性 — CLOSED

所有守卫使用 `if ... is None: raise ValueError(...)` 模式。`ValueError` 在 `python -O` 下不会被优化掉（`assert` 会被）。守卫在所有优化级别下有效。

### C10.3 正常路径保持 — CLOSED

34 个 write_service 测试全部通过，包括已有测试覆盖正常路径（exit code 0/2/4）和 3 个新增非法组合测试（均返回 exit code 2）。

---

## 测试质量

### 测试能否在旧代码上失败 — YES

`test_print_report_source_contains_no_assert_statements` 使用 `ast.parse(inspect.getsource(WriteService.print_report))` 检查是否存在 `ast.Assert` 节点。基线代码包含 7 处 assert，此测试在基线上必然失败。

### 测试 secret 虚构性 — PASS

所有测试中的 `sk-` 字符串均使用 `"sk-" + ("A" * 20)` 模式，明显虚构。本次 diff 未引入任何新 secret。

### 新增测试

| 测试 | 作用 |
|------|------|
| `test_print_report_source_contains_no_assert_statements` | C10 回归守卫（AST 级） |
| `test_print_report_config_change_request_without_promotion_input_returns_2` | 非法组合边界 |
| `test_print_report_config_change_approval_mismatched_inputs_returns_2` | 非法组合边界 |
| `test_print_report_preflight_approval_mismatched_returns_2` | 非法组合边界 |

---

## 代码质量

### Any/object/untyped 签名 — PASS

diff 中无新增 `Any` 或 `object` 返回类型。测试中 `dict[str, object]` 收窄为 `dict[str, str]`（改进）。`Callable` 从 `typing` 移至 `collections.abc`（改进）。

### 耦合 — SEE F1.3

`validate_handoff_docs.py` 的 re-export 构成兼容性耦合。

### 重复逻辑 — PASS

`dayu/redaction.py` 是单一真相源。`contains_secret_shape()` 是薄 wrapper 用于保留函数签名兼容，非重复实现。

### 无关变化 — PASS

diff 中的 `startswith` tuple 合并、import 排序调整属于代码风格改进，与 P0 目标一致，无实质无关变化。

### 安全泄漏 — PASS

无新增安全泄漏。

---

## 验证结果

| 检查 | 结果 |
|------|------|
| `git diff --check` | 0 errors |
| Pyright（5 个变更文件） | 0 errors, 0 warnings, 0 informations |
| Ruff（5 个变更文件） | All checks passed |
| `tests/application/test_write_service.py` | 34/34 passed |
| `tests/test_validate_handoff_docs.py` | 370/370 passed |
| 运行时 import 验证 | `dayu.redaction` ✓, `validate_handoff_docs` re-exports ✓ |

---

## 剩余风险

1. **F1.3 BLOCKED**: `validate_handoff_docs.py` 中 `SECRET_KEY_PATTERN` 和 `REDACTED_SECRET` 的 re-export 违反"禁止兼容性 re-export"约束。需更新外部消费者（`codex_review_gate.py`、`prepare_deepseek_task.py`、`dual_model_pipeline_check.py` 及其测试）直接从 `dayu.redaction` 导入，然后移除 re-export。
2. `print_report` 方法约 570 行，仍属超长函数，但不在本次 P0 diff 修复范围内。
