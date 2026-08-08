# Code Review — Slice 3 W15: finish() 内联消除

- **审查者**: MiMo 第二路独立审查
- **日期**: 2026-08-08
- **基线**: `4e90a69` (`gateflow: accept write artifact callers slice 2b`)
- **分支**: `codex/dual-model-research-mvp`
- **审查范围**: 工作区未提交改动（`git diff HEAD`）
- **Approved plan**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v4.4 Slice 3

---

## 1. 变更摘要

仅修改 `dayu/services/write_model_challenger_proposal.py`：

1. 删除 `build_write_model_challenger_proposal` 内部的嵌套 `def finish()` 闭包（原第 359-367 行）。
2. 将 5 处 `return finish()` 原位替换为直接 `return _finalize_payload(payload, history_fingerprint=normalized_history_fingerprint, selected_run_count=selected_run_count, recent_run_count=recent_run_count, baseline_run_count=baseline_run_count)`。
3. 为 `build_write_model_challenger_proposal` 补齐中文 Args/Returns/Raises docstring。

无新增文件、无删除文件、无 import 变更、无跨模块改动。

---

## 2. 逐项核对

### 2.1 nested finish 删除 & direct finalize 恰 5 处

**结构审计**（AST 解析）：

```text
nested_finish_defs=0
return_finish_calls=0
direct_finalize_returns=5
```

✅ 嵌套 `finish()` 定义为零，`return finish()` 调用为零，直接 `return _finalize_payload(...)` 恰为 5。

### 2.2 五分支条件等价性

| # | 分支条件 | base 行为 | 当前行为 | 等价 |
|---|---------|----------|---------|------|
| 1 | `if global_reasons:` | `payload["reason_codes"] = global_reasons` → `return finish()` | `payload["reason_codes"] = global_reasons` → `return _finalize_payload(...)` | ✅ |
| 2 | `if not role_decisions:` | 设 status/action/reason_codes → `return finish()` | 同左 → `return _finalize_payload(...)` | ✅ |
| 3 | `if ambiguous:` | 设 status/reason_codes → `return finish()` | 同左 → `return _finalize_payload(...)` | ✅ |
| 4 | `if blocked:` | 构建 reason_codes → `return finish()` | 同左 → `return _finalize_payload(...)` | ✅ |
| 5 | ready 路径（末尾） | 设 status/action/overrides/args/reason_codes → `return finish()` | 同左 → `return _finalize_payload(...)` | ✅ |

五分支条件表达式、payload 字段写入顺序、写入内容完全未变。

### 2.3 payload 写入时序

各分支中 payload 字段的写入发生在 `_finalize_payload` 调用之前，与 base 完全一致：

- 分支 1：`evaluated_routes` → `reason_codes` → finalize
- 分支 2：`evaluated_routes` → `role_decisions` → `status`/`action`/`reason_codes` → finalize
- 分支 3：同分支 2 + `ambiguous` 过滤 → `status`/`reason_codes` → finalize
- 分支 4：同分支 3 + `blocked` 过滤 → `reason_codes` → finalize
- 分支 5：同分支 4 + ready 过滤 → `status`/`action`/`role_overrides`/`challenger_cli_args`/`reason_codes` → finalize

✅ 时序无变化。

### 2.4 调用次数

每个分支恰好调用 `_finalize_payload` 1 次，与 base 中每个分支恰好调用 `finish()` 1 次等价。无重复调用、无遗漏调用。

✅ 调用次数等价。

### 2.5 payload identity

5 处 `_finalize_payload` 调用的第一个参数均为同一局部变量 `payload`（由 `_base_payload()` 创建于函数入口）。这与 base 中 `finish()` 闭包捕获的 `payload` 是同一对象。

✅ payload identity 等价。

### 2.6 全部参数与原闭包精确等价

base 闭包签名与调用：

```python
def finish() -> dict[str, Any]:
    return _finalize_payload(
        payload,                                    # 闭包捕获
        history_fingerprint=normalized_history_fingerprint,  # 闭包捕获
        selected_run_count=selected_run_count,              # 闭包捕获
        recent_run_count=recent_run_count,                  # 闭包捕获
        baseline_run_count=baseline_run_count,              # 闭包捕获
    )
```

当前 5 处直接调用：

```python
return _finalize_payload(
    payload,
    history_fingerprint=normalized_history_fingerprint,
    selected_run_count=selected_run_count,
    recent_run_count=recent_run_count,
    baseline_run_count=baseline_run_count,
)
```

5 个参数名、参数值来源、keyword-only 传递方式完全一致。

✅ 参数精确等价。

---

## 3. Docstring 审查

新增 docstring：

```python
"""构建仅用于隔离 Challenger 评估的安全参数提案。

Args:
    recent: 最近运行窗口的聚合证据。
    route_pairs: 各模型角色的主备路由证据。
    models: 当前模型健康状态清单。
    history_fingerprint: 当前历史窗口的 SHA-256 指纹。
    selected_run_count: 当前选择窗口的运行总数。
    baseline_run_count: 基线窗口的运行数量。

Returns:
    包含决策、证据窗口与内容指纹的 Challenger 提案。

Raises:
    ValueError: 当指纹、运行数量或窗口数量关系不合法时抛出。
"""
```

**Raises 核对**：

| 异常源 | 行号 | 异常类型 | docstring 声明 |
|-------|------|---------|---------------|
| `validated_fingerprint(history_fingerprint, ...)` | 354-357 | `ValueError` | ✅ |
| `_required_non_negative_int(selected_run_count, ...)` | 358-361 | `ValueError` | ✅ |
| `_required_non_negative_int(baseline_run_count, ...)` | 362-365 | `ValueError` | ✅ |
| `selected_run_count != recent_run_count + baseline_run_count` | 367-370 | `ValueError` | ✅ |

docstring 声明 `ValueError` 与实际抛出类型一致，无误述。

✅ docstring 准确。

---

## 4. 独立验证结果

### 4.1 pytest

```text
$ pytest tests/application/test_write_model_challenger_proposal.py -q
8 passed in 0.55s

$ pytest tests/application -k challenger_proposal -q \
    --ignore=tests/application/test_streamlit_chat_stream_runtime.py \
    --ignore=tests/application/test_streamlit_chat_tab.py \
    --ignore=tests/application/test_streamlit_filing_runtime.py \
    --ignore=tests/application/test_streamlit_filing_tab.py
11 passed, 1 skipped, 1308 deselected in 0.84s
```

✅ 全部通过。

### 4.2 pyright

```text
$ pyright dayu/services/write_model_challenger_proposal.py
0 errors, 0 warnings, 0 informations
```

✅ 零错误。

### 4.3 ruff

```text
$ ruff check dayu/services/write_model_challenger_proposal.py
Found 5 errors (1 UP035 + 4 TRY004)

$ git show 4e90a69:dayu/services/write_model_challenger_proposal.py | ruff check --stdin-filename ... -
Found 5 errors (1 UP035 + 4 TRY004)
```

base 与当前版本 ruff 报错完全一致（同 rule-code multiset），零新增、零扩散。

```
$ ruff check --select F,I001 dayu/services/write_model_challenger_proposal.py
All checks passed!
```

✅ 无新增 lint 问题。

### 4.4 结构审计

```text
$ rg '^    def finish\(' dayu/services/write_model_challenger_proposal.py
(no matches)

$ rg 'return finish\(\)' dayu/services/write_model_challenger_proposal.py
(no matches)

$ rg 'return _finalize_payload\(' dayu/services/write_model_challenger_proposal.py
5 matches
```

✅ 结构指标全部达标。

### 4.5 类型逃逸检查

```text
$ git diff -U0 | rg '^\+.*(\bAny\b|\bobject\b|cast\(|type:\s*ignore)'
(no matches)
```

✅ 零新增 `Any`、`object`、`cast`、`type: ignore`。

---

## 5. 编码硬约束合规

| 约束 | 状态 | 说明 |
|------|------|------|
| 函数必须提供完整中文 docstring | ✅ | 新增 Args/Returns/Raises |
| 禁止使用 `object`、`Any`、无类型参数 | ✅ | diff 无新增类型逃逸 |
| 禁止胶水 seam | ✅ | 无新增 lazy import 或 wrapper |
| 优先使用模块级私有辅助函数 | ✅ | `_finalize_payload` 已是模块级私有函数 |
| 禁止无必要的嵌套函数 | ✅ | 删除了不必要的嵌套 `finish()` |
| 禁止魔法数字、魔法字符串 | ✅ | 无新增 |
| 禁止兼容性代码 | ✅ | 非兼容性重构 |

---

## 6. 架构合规

| 约束 | 状态 | 说明 |
|------|------|------|
| 分层架构 UI → Service → Host → Agent | ✅ | 改动仅在 Service 层内部 |
| 禁止反向依赖 | ✅ | 无新增依赖 |
| 设计下层接口不向上泄漏实现细节 | ✅ | 公共 API 签名未变 |

---

## 7. 跨 slice 检查

- 改动仅涉及 Slice 3 定义的 `dayu/services/write_model_challenger_proposal.py`。
- 未触及 Slice 4（`research_workbook.py`）、Slice 5（`_write_config_helpers.py`、`_write_params_validation.py`）或任何其它 slice 的文件。
- 未修改测试文件、配置文件或文档文件（除本审查 artifact）。

✅ 无跨 slice 改动。

---

## 8. 测试缺口分析

- 五条返回路径（global-block / no-role-decisions / ambiguous / blocked-role / ready）均有对应测试用例。
- `_finalize_payload` 的参数传递通过现有 8 个测试用例间接验证（fingerprint 一致性断言覆盖）。
- 本次改动是纯机械内联，不引入新的分支或边界条件，无需新增测试。

✅ 无测试缺口。

---

## 9. 过度耦合检查

- 5 处 `_finalize_payload` 调用参数完全一致，这是 accepted W15 的明确设计结果（消除闭包，接受参数重复）。
- 若未来 `_finalize_payload` 签名变更，5 处调用需同步更新——但这是内联消除闭包的固有 trade-off，已在 plan 中明确接受。
- 当前 pyright + 测试覆盖可有效防止参数漂移。

✅ 无过度耦合。参数重复是 plan 明确接受的 trade-off。

---

## 10. Findings

### 10.1 无 High 级 findings

### 10.2 无 Medium 级 findings

### 10.3 Low 级 findings

| # | 类别 | 描述 | 严重性 | 建议 |
|---|------|------|--------|------|
| L1 | Pre-existing | ruff UP035: `from typing import Mapping, Sequence` 应改为 `from collections.abc import Mapping, Sequence` | Low | 非本次引入，base 即存在，不在本 slice 修复范围 |
| L2 | Pre-existing | ruff TRY004 × 4: `validate_write_model_challenger_proposal` 中 4 处 `raise ValueError` 应为 `TypeError` | Low | 非本次引入，base 即存在，不在本 slice 修复范围 |
| L3 | Style | 5 处 `_finalize_payload` 调用参数完全相同，未来签名变更需同步 5 处 | Low | 已在 plan 中明确接受；pyright + 测试覆盖可防止漂移 |

---

## 11. Verdict

**PASS — 无需修改即可合入。**

审查结论：

1. **nested finish 删除**：✅ 嵌套 `def finish()` 已完全删除，AST 审计确认 `nested_finish_defs=0`。
2. **direct finalize 恰 5 处**：✅ `direct_finalize_returns=5`，对应五条返回路径。
3. **五分支条件等价**：✅ 条件表达式、payload 字段写入顺序与内容完全未变。
4. **payload 写入时序**：✅ 各分支中 payload 字段写入发生在 finalize 调用之前，与 base 一致。
5. **调用次数**：✅ 每分支恰好 1 次 finalize 调用。
6. **payload identity**：✅ 5 处调用均为同一 `payload` 局部变量。
7. **全部参数精确等价**：✅ 5 个 keyword-only 参数名与值来源与原闭包完全一致。
8. **docstring 不误述异常**：✅ Raises 声明 `ValueError` 与实际抛出一致。
9. **无测试缺口**：✅ 五条路径均有测试覆盖，8 passed。
10. **无类型逃逸**：✅ diff 零新增 `Any`/`object`/`cast`/`type: ignore`。
11. **无跨 slice 改动**：✅ 仅修改 Slice 3 定义的单一文件。
12. **无过度耦合**：✅ 参数重复是 plan 明确接受的 trade-off。
13. **pyright**：✅ 0 errors。
14. **ruff**：✅ 零新增问题（5 个 pre-existing）。
15. **编码硬约束合规**：✅ 全部通过。

---

## 12. Artifact 信息

- **审查 artifact**: `docs/reviews/code-review-slice-3-20260808-mimo.md`
- **实现 artifact**: `docs/reviews/slice-3-challenger-proposal-finish-implementation-20260808-codex.md`
- **Approved plan**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v4.4 Slice 3
