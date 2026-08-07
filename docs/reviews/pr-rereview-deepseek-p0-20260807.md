# PR Re-review — P0 Findings (DeepSeek, Adversarial)

- **日期**: 2026-08-07
- **角色**: DeepSeek Re-review Agent（adversarial，只读）
- **基线 HEAD**: 6e22cb57ac180ab69483baf0af1b45efefad3233
- **审查目标**: 未提交 P0 diff（DeepSeek F1 + MiMo C10 修复）
- **参考 artifact**:
  - `docs/reviews/pr-review-deepseek-20260807.md`（原始 DS review）
  - `docs/reviews/pr-review-mimo-20260807.md`（原始 MiMo review）
  - `docs/reviews/pr-fix-p0-deepseek-20260807.md`（上一轮实现说明）
- **输出文件**: `docs/reviews/pr-rereview-deepseek-p0-20260807.md`
- **修正记录**: 2026-08-07 总控核对指出三处事实错误，已全量修正（详见末尾修正清单）

---

## Verdict: ACCEPTED

两项 P0 finding 均已完整关闭，无阻塞问题。

---

## Finding 1: DeepSeek F1 — CLI 输出脱敏

**状态**: CLOSED

### 逐项验证

| 检查项 | 结果 | 证据 |
|--------|------|------|
| **error 脱敏** | ✓ | `DayuCliArgumentParser.error()` 保留 `"required: command"` 特殊分支，其余委托 `super().error(message)` → `RedactingArgumentParser.error()`，后者对 message + prog 双脱敏 |
| **usage 脱敏** | ✓ | `DayuCliArgumentParser` 不覆盖 `format_usage()`，继承自 `RedactingArgumentParser.format_usage()` |
| **help 脱敏** | ✓ | `DayuCliArgumentParser` 不覆盖 `format_help()`，继承自 `RedactingArgumentParser.format_help()` |
| **prog 脱敏** | ✓ | `RedactingArgumentParser.error()` 显式对 `self.prog` 调用 `redact_secret_shapes()` |
| **共享实现位置** | ✓ | `dayu/redaction.py` 顶层叶模块，不依赖任何 dayu 子包 |
| **无 dayu → utils 反向依赖** | ✓ | `utils/validate_handoff_docs.py` → `dayu.redaction`（单向，`dayu.redaction` 不导入 utils） |
| **无重复正则** | ✓ | 全仓库仅 1 处 `SECRET_KEY_PATTERN` 定义（`dayu/redaction.py:27`） |
| **无 UI adapter 副作用** | ✓ | `dayu/redaction.py` 仅导入 `argparse`、`re`、`sys`、`NoReturn`（均为 stdlib/typing） |
| **导入隔离** | ✓ | `from dayu.redaction import ...` 仅加载 6 个模块，无 `dayu.cli.*`、`dayu.engine.*` 等重型模块 |
| **handoff CLI API 兼容** | ✓ | `utils/validate_handoff_docs.py` re-export 5 个符号，`is` 身份一致；`contains_secret_shape()` 委托 `has_secret_shapes()` 行为不变 |
| **`dayu/cli/redaction.py` 中间文件** | ✓ | 本修复轮次中创建后删除的 working-tree-only 中间文件，未进入任何 commit；当前工作树无残留；最终共享实现位于 `dayu/redaction.py`（untracked new file） |

### 测试覆盖

| 测试套件 | 结果 |
|-----------|------|
| `tests/cli/test_arg_parsing_redaction.py`（16 tests） | 16 passed |
| `tests/test_validate_handoff_docs.py -k redact`（7 tests） | 7 passed |
| 测试使用虚构 secret shape（`sk-test-secret-key-...`） | ✓ 无真实 key |
| SystemExit 捕获 | ✓ 全部使用 `pytest.raises(SystemExit)`，无 bare try/except |
| 断言质量 | ✓ 35 个断言，13 个 `not in`（脱敏确认），含 exit code 2 断言 |

---

## Finding 2: MiMo C10 — assert 改为显式守卫

**状态**: CLOSED

### 三层防御结构（print_report 参数校验架构）

`WriteService.print_report` 对公开参数的校验采用三层防御：

| 层级 | 位置 | 职责 | 失败行为 |
|------|------|------|---------|
| **Tier 1（前置校验）** | `write_service.py:472-565` | 公开参数组合合法性校验。检查所有 CLI 可构造的非法参数组合。 | 打印 `[warning]` → `return 2` |
| **Tier 2（防御性不变量）** | `write_service.py:665-670, 749-760, 886-891, 910-915, 946-957` | 内部不变量守卫。重复 Tier 1 的约束，但位于深层调用链中。正常 API 路径不可达。 | `raise ValueError(msg)` → **向外传播（不被任何 try/except 捕获）** |
| **Tier 3（操作异常）** | `write_service.py:671+, 762+, 892+, 916+, 958+` | I/O 与数据操作的预期异常（FileNotFoundError, OSError, TypeError, ValueError）。 | 打印 `[warning]` → `return 2` |

### Tier 2 守卫不被捕获的逐行证据

7 个 `raise ValueError` 与相邻 `try/except` 的位置关系（精确行号）：

| 行号 | 条件 | 与 try/except 关系 |
|------|------|-------------------|
| 666 | `challenger_config_change_request_output` 已提供但 `challenger_promotion_proposal_input` 为 None | **try 从 671 行开始**，666 在其外部 |
| 751 | `config_change_approval_issuance` 为 True 但 `challenger_config_change_approval_request` 为 None | **try 从 762 行开始**，751 在其外部 |
| 757 | `config_change_approval_issuance` 为 True 但 `challenger_config_change_approval_output` 为 None | **try 从 762 行开始**，757 在其外部 |
| 887 | `routing_proposal_output` 已提供但 `proposal` 为 None | 位于外层 `try … except … else` 的 **else 子句**（line 866）中；else 子句的异常不被对应的 except 捕获 |
| 911 | `routing_proposal_input` 已提供但 `proposal` 为 None | 同上，else 子句中 |
| 947 | `approval_requested` 为 True 但 `routing_preflight_approval_request` 为 None | 同上，else 子句中 |
| 953 | `approval_requested` 为 True 但 `routing_preflight_approval_output` 为 None | 同上，else 子句中 |

**关键结论**：若 Tier 2 任一守卫被触发，`ValueError` 将作为**未处理异常向外传播**——不会被任何现有 `try/except` 捕获并转为 exit code 2。

### 为什么不可达守卫向外抛 ValueError 是可接受的

1. **Tier 1 是公开契约**：所有 CLI 可构造的非法参数组合在 Tier 1（lines 472-565）被拦截并返回 exit code 2。新增的 3 个行为测试覆盖的正是 Tier 1 路径——例如 `challenger_config_change_request_output` 与 `challenger_promotion_proposal_input` 的互斥在 line 517-525 处被拦截，远在 Tier 2 守卫（line 665）之前。

2. **Tier 2 仅防御 Tier 1 自身缺陷**：Tier 2 的每个条件都与 Tier 1 的某个条件等价。Tier 2 触发意味着 Tier 1 存在未被测试覆盖的逻辑漏洞——这是**内部逻辑错误**，不是用户输入错误。

3. **内部逻辑错误应 crash 而非静默**：若 Tier 2 触发后静默返回 exit code 2，将**掩盖** Tier 1 的缺陷——程序表面行为"正确"（返回 2），但校验管道实际已破损。向外抛 `ValueError` + traceback 能立即暴露缺陷位置，缩短 debug 周期。

4. **`-O` 模式下的旧 assert 更差**：旧代码在 `-O` 下跳过 assert → `None` 传入下游 → 难以诊断的 `AttributeError` 或静默数据损坏。新代码在 `-O` 下仍执行 `if/raise`，行为确定。

### AST 测试的定位

`test_print_report_source_contains_no_assert_statements` 是一个**静态代码质量检查**（lint-like），不是行为测试：

- 它用 `inspect.getsource` + `ast.parse` + `ast.walk` 验证 `print_report` 源码 AST 中零 `ast.Assert` 节点
- 它不测试异常路径、不测试运行时行为、不测试退出码
- 它会在旧代码（7 个 assert）上**正确失败**，在新代码（0 个 assert）上**正确通过**
- 它的职责是锁定"源代码不含 assert"这一可验证不变式，防止未来有人重新引入 assert

### 逐项验证

| 检查项 | 结果 | 证据 |
|--------|------|------|
| **7 处 assert 全部替换** | ✓ | AST 验证：`print_report` 源码中 0 个 `ast.Assert` 节点，7 个 `if/raise ValueError` |
| **优化模式仍有效** | ✓ | `if/raise` 不受 `-O` 影响；旧 `assert` 在 `-O` 下被跳过 |
| **正常路径无回归** | ✓ | Tier 1 前置校验覆盖所有公开非法组合；正常用户输入不触发 Tier 2 |
| **非法组合退出码** | ✓ | 3 个新增行为测试验证 Tier 1 前置校验返回 exit code 2 |
| **中文诊断消息** | ✓ | 7 个 ValueError 均含中文消息指明缺失参数名称 |
| **无逻辑变更** | ✓ | diff 仅含 import 重排（ruff I001）+ assert→if/raise 替换，无业务逻辑改动 |
| **Tier 2 不可达性** | ✓ | Tier 1 的 10 个 `return 2` 前置检查（lines 476, 482, 491, 504, 516, 525, 534, 547, 559, 565）先于任何 Tier 2 守卫执行 |

### 测试覆盖

| 测试 | 覆盖层级 | 结果 |
|------|---------|------|
| `tests/application/test_write_service.py`（34 tests，含 4 新增） | — | 34 passed |
| `test_print_report_source_contains_no_assert_statements` | **静态**：AST 零 assert 断言 | ✓ 在旧代码上会失败 |
| `test_print_report_config_change_request_without_promotion_input_returns_2` | **Tier 1**：line 517-525 前置校验 | ✓ exit code 2 |
| `test_print_report_config_change_approval_mismatched_inputs_returns_2` | **Tier 1**：line 505-516 前置校验 | ✓ exit code 2 |
| `test_print_report_preflight_approval_mismatched_returns_2` | **Tier 1**：line 548-559 前置校验 | ✓ exit code 2 |

注：3 个行为测试均命中 Tier 1 前置校验（`print_report` 入口处 lines 472-565），不触及 Tier 2 守卫。这是正确的——Tier 2 不可通过公开 API 到达，强行构造测试需 mock 内部状态，反而不可信。

---

## 独立验证结果（真实命令与输出）

### Pyright

```
$ source .venv/bin/activate && pyright dayu/redaction.py dayu/cli/arg_parsing.py \
  dayu/services/write_service.py utils/validate_handoff_docs.py \
  tests/cli/test_arg_parsing_redaction.py tests/application/test_write_service.py
0 errors, 0 warnings, 0 informations
```

### Ruff

```
$ source .venv/bin/activate && ruff check dayu/redaction.py dayu/cli/arg_parsing.py \
  dayu/services/write_service.py utils/validate_handoff_docs.py \
  tests/cli/test_arg_parsing_redaction.py tests/application/test_write_service.py
All checks passed!
```

### git diff --check

```
$ git diff --check HEAD
（无输出 — clean）
```

### pytest

```
$ pytest tests/cli/test_arg_parsing_redaction.py -v
16 passed

$ pytest tests/application/test_write_service.py -v
34 passed (含 4 新增)

$ pytest tests/test_validate_handoff_docs.py -v -k "redact"
7 passed

合计: 57 passed, 0 failed
```

---

## 新增代码类型安全检查

| 文件 | Any/object | 无类型参数 | 无类型返回 |
|------|-----------|-----------|-----------|
| `dayu/redaction.py` | 0 | 0 | 0 |
| `dayu/cli/arg_parsing.py` | 0 | 0 | 0 |
| `tests/cli/test_arg_parsing_redaction.py` | 0 | 0 | 0 |

---

## 剩余风险

1. **CLI 脱敏仅覆盖 `sk-` 前缀**：其他 provider 的 key 格式不在 `SECRET_KEY_PATTERN` 范围内。这是已知设计限制，非本次修复引入。
2. **Tier 2 防御性不变量不可达但不可测试**：7 个 `if/raise ValueError` 守卫是 defense-in-depth，正常 API 路径不可达，无法通过公开 API 构造触发它们的测试。若未来维护者误删 Tier 1 前置校验中对应的条件，对应的 Tier 2 守卫会以未处理 ValueError 形式向外抛出——这是 correct fail-loud 行为，使缺陷立即可见。
3. **`utils/validate_handoff_docs.py` re-export 带 `# noqa: F401`**：`codex_review_gate` 等外部模块通过 `validate_handoff_docs.` 引用 `SECRET_KEY_PATTERN`/`REDACTED_SECRET`。长期方案可让所有调用方直接从 `dayu.redaction` 导入，消除 `# noqa`。

---

## 未覆盖项

- `dayu/cli/commands/write.py` 的 `print_report` 静态方法（5226 行文件，不在本次 P0 diff 范围）
- `dayu/services/write_model_*.py` 20 个文件的代码重复（MiMo C5，P1 级别，不在本批次）
- CI pyright 步骤（MiMo W26，总控裁决 `.github/workflows/ci-pr-required.yml` 已执行）
- 其他 DS F2-F7、MiMo C1-C9/C11-C14、W1-W25/W27-W30 finding（总控裁决不在本批次）

---

## 修正清单（2026-08-07）

上一版 artifact 存在三处事实错误，已全部修正：

| # | 错误陈述 | 修正 |
|---|---------|------|
| 1 | "`dayu/cli/redaction.py` 已删除（在 commit `6e22cb5` 中处理）" | 该文件是本轮 working-tree-only 中间文件（创建后删除），从未进入任何 commit。基线 HEAD `6e22cb5` 及其祖先均无此文件。当前最终形态为 `dayu/redaction.py`（untracked new file），无残留。 |
| 2 | "3 个行为测试触发 ValueError→exit code 2" | 3 个测试实际命中 **Tier 1 前置校验**（lines 517-525, 505-516, 548-559），在进入任何 ValueError 守卫之前已 `return 2`。Tier 2 ValueError 守卫从未被触发。 |
| 3 | "ValueError 被现有 `except ValueError` 捕获→exit code 2" | 7 个 `raise ValueError` 均位于对应 `try/except` 之外（3 个结构上在 try 之前，4 个在 else 子句中）。若触发，将以**未处理异常**向外传播，不会被任何现有 except 转为 exit code 2。这是可接受的 fail-loud 行为——详见 Finding 2 分析。 |
