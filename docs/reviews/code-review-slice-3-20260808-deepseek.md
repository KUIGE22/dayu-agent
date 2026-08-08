# Slice 3 W15 finish() 内联消除 — DeepSeek 独立代码审查

- **日期**: 2026-08-08
- **审查者**: DeepSeek（独立审查路）
- **基线**: `4e90a69` (`gateflow: accept write artifact callers slice 2b`)
- **分支**: `codex/dual-model-research-mvp`
- **审查对象**: Slice 3 W15 未提交改动
- **Accepted plan**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v4.4 Slice 3
- **参考实现记录**: `docs/reviews/slice-3-challenger-proposal-finish-implementation-20260808-codex.md`
- **参考指令**: `AGENTS.md`

---

## 1. 审查范围与方法

### 1.1 范围

| 项 | 状态 |
|---|---|
| 修改文件 | `dayu/services/write_model_challenger_proposal.py`（仅此一文件） |
| 新增文件 | 无（本 artifact 除外） |
| 跨 slice 改动 | **零** — diff stat 仅一个文件 |
| 测试修改 | **零** — 现有测试直接覆盖五路径 |
| 生产代码修改 | **零** — 本次审查不修改任何生产/测试/实现 artifact |

### 1.2 方法

1. 逐行 diff 审计（`git diff 4e90a69`）
2. AST 级结构审计（nested function detection, call-site parameter verification）
3. 五分支逐路径 payload 写入时序追踪
4. 参数等价性验证（闭包捕获 vs 直接传参）
5. Docstring 准确性校验（Args/Returns/Raises 与实际行为对照）
6. 测试聚焦运行 + pyright + ruff + diff 门禁
7. 类型逃逸扫描（`Any`/`object`/`cast`/`type: ignore`/`hasattr`/`getattr`）
8. 过度耦合 / cross-slice 边界检查

---

## 2. 结构审计

### 2.1 nested finish 删除

```text
$ rg -n "^    def finish\(" dayu/services/write_model_challenger_proposal.py
(零匹配)
```

```text
$ rg -n "return finish\(\)" dayu/services/write_model_challenger_proposal.py
(零匹配)
```

**结论**: ✅ 嵌套 `def finish()` 已完全删除，零残留。

### 2.2 direct finalize 调用计数

```text
$ rg -n "return _finalize_payload\(" dayu/services/write_model_challenger_proposal.py
386:        return _finalize_payload(
400:        return _finalize_payload(
416:        return _finalize_payload(
435:        return _finalize_payload(
470:    return _finalize_payload(
```

**结论**: ✅ 恰为 5 处 `return _finalize_payload(...)`，与 accepted plan 一致。

### 2.3 AST 级验证

```text
Nested functions in builder: []
Zero nested functions in builder. PASS
```

```text
All calls have identical keyword argument names and AST structure. PASS
```

---

## 3. 五分支逐路径审计

### 3.1 全局阻塞路径（line 384–392）

**条件**: `if global_reasons:` — 近期运行窗口存在全局阻塞因素（运行量不足、收据不完整、gate 通过率过低）。

**Payload 写入时序**:
1. `payload["evaluated_routes"] = assessed_routes`（line 383）
2. `payload["reason_codes"] = global_reasons`（line 385）
3. → `_finalize_payload(payload, ...)`（line 386）

**旧代码等价性**: ✅ 写入顺序与旧 `return finish()` 完全一致。`finish()` 闭包捕获的 `payload` 即当前 `payload` 引用。

### 3.2 无需操作路径（line 396–406）

**条件**: `if not role_decisions:` — 无降级角色，无需 Challenger。

**Payload 写入时序**:
1. `payload["evaluated_routes"] = assessed_routes`（line 383）
2. `payload["role_decisions"] = role_decisions`（line 395）
3. `payload["status"] = "not_needed"`（line 397）
4. `payload["action"] = "none"`（line 398）
5. `payload["reason_codes"] = ["no_degraded_primary_route"]`（line 399）
6. → `_finalize_payload(payload, ...)`（line 400）

**旧代码等价性**: ✅

### 3.3 歧义路径（line 408–422）

**条件**: `if ambiguous:` — 同一角色存在多个降级候选。

**Payload 写入时序**:
1–2. 同 3.2 的步骤 1–2
3. `payload["status"] = "ambiguous"`（line 414）
4. `payload["reason_codes"] = ["ambiguous_degraded_role_routes"]`（line 415）
5. → `_finalize_payload(payload, ...)`（line 416）

**旧代码等价性**: ✅

### 3.4 角色阻塞路径（line 424–441）

**条件**: `if blocked:` — 降级角色的 fallback 候选不稳定。

**Payload 写入时序**:
1–2. 同 3.2 的步骤 1–2
3. `reason_codes = ["degraded_role_has_no_stable_fallback_candidate"]`（line 430）
4. 遍历 blocked decisions 追加 reason_codes（line 431–433）
5. `payload["reason_codes"] = reason_codes`（line 434）
6. → `_finalize_payload(payload, ...)`（line 435）

**旧代码等价性**: ✅

### 3.5 Ready 路径（line 443–476）

**条件**: 隐含 else — 所有降级角色均有唯一稳定的 fallback 候选。

**Payload 写入时序**:
1–2. 同 3.2 的步骤 1–2
3. 构建 `role_overrides` 和 `cli_args`（line 448–461）
4. `payload["status"] = "ready"`（line 463）
5. `payload["action"] = "run_isolated_challenger"`（line 464）
6. `payload["role_overrides"] = role_overrides`（line 465）
7. `payload["challenger_cli_args"] = cli_args`（line 466）
8. `payload["reason_codes"] = ["stable_fallback_candidate_requires_challenger_evaluation"]`（line 467）
9. → `_finalize_payload(payload, ...)`（line 470）

**旧代码等价性**: ✅

---

## 4. 参数等价性验证

### 4.1 闭包捕获变量映射

旧闭包 `finish()` 捕获的五个变量与直接调用参数的对应关系：

| 闭包变量 | 直接调用参数 | 变量定义位置 | 是否被重赋值 |
|---|---|---|---|
| `payload` | 位置参数 `payload` | line 372 (`_base_payload()`) | 否（原地修改） |
| `normalized_history_fingerprint` | `history_fingerprint=normalized_history_fingerprint` | line 354 | 否 |
| `selected_run_count` | `selected_run_count=selected_run_count` | line 358（重赋值） | **是**（shadow 参数） |
| `recent_run_count` | `recent_run_count=recent_run_count` | line 366 | 否 |
| `baseline_run_count` | `baseline_run_count=baseline_run_count` | line 362（重赋值） | **是**（shadow 参数） |

### 4.2 重赋值变量语义验证

`selected_run_count` 和 `baseline_run_count` 在函数体内被 `_required_non_negative_int()` 重赋值（shadow 了同名参数）。闭包定义位于重赋值之后（line 371），因此闭包捕获的是**重赋值后的值**。直接调用同样使用重赋值后的变量。语义完全等价。

### 4.3 五处调用一致性

所有 5 处 `_finalize_payload` 调用使用**完全相同**的关键字参数：

```python
_finalize_payload(
    payload,
    history_fingerprint=normalized_history_fingerprint,
    selected_run_count=selected_run_count,
    recent_run_count=recent_run_count,
    baseline_run_count=baseline_run_count,
)
```

AST 结构审计确认五处 kwargs 完全一致。

**结论**: ✅ 参数闭包等价性成立。

---

## 5. Docstring 审计

### 5.1 旧 docstring

```python
"""Return a safe argv proposal for an isolated Challenger evaluation."""
```

### 5.2 新 docstring

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

### 5.3 准确性验证

| Docstring 声称 | 实际行为 | 判定 |
|---|---|---|
| Args 六个参数 | 函数签名恰为六个 keyword-only 参数 | ✅ |
| Returns 描述 | `_finalize_payload` 返回 `dict[str, Any]`，含 `evidence_window` 与 `proposal_fingerprint` | ✅ |
| Raises `ValueError` — 指纹 | `validated_fingerprint()` 对非法指纹抛出 `ValueError` | ✅ |
| Raises `ValueError` — 运行数量 | `_required_non_negative_int()` 对非法整数抛出 `ValueError` | ✅ |
| Raises `ValueError` — 窗口数量关系 | `selected_run_count != recent_run_count + baseline_run_count` 时抛出 `ValueError` | ✅ |

**结论**: ✅ Docstring 准确描述了参数、返回值和异常情况。未发现误述。

### 5.4 Raises 覆盖完备性

函数体内可能产生异常的所有路径：
- `validated_fingerprint()` → `ValueError`
- `_required_non_negative_int()` × 2 → `ValueError`
- 数量不匹配检查 → `ValueError`
- `_finalize_payload()` → 内部 `fingerprint_str()` 调用 `json.dumps()`，理论上可抛 `TypeError`（非可序列化类型），但 payload 构造路径保证不会触发

Docstring 仅声明 `ValueError`，不声明 `TypeError`（属内部错误/编程错误，非用户可触发）。此做法与项目惯例一致。

**结论**: ✅ Raises 覆盖完备，无遗漏的用户可见异常类型。

---

## 6. 测试与覆盖率

### 6.1 聚焦测试

```text
$ pytest tests/application/test_write_model_challenger_proposal.py -q
8 passed in 0.58s
```

### 6.2 广泛测试

```text
$ pytest tests/application -k "challenger_proposal" -q
11 passed, 1 skipped, 1308 deselected in 0.72s
```

### 6.3 五路径测试映射

| 路径 | 预期 status | 测试用例 |
|---|---|---|
| global-block | `blocked` | `test_challenger_proposal_blocks_incomplete_recent_receipts` |
| not-needed | `not_needed` | `test_challenger_proposal_does_nothing_for_healthy_routes` |
| ambiguous | `ambiguous` | `test_challenger_proposal_rejects_ambiguous_role_candidates` |
| role-blocked | `blocked` | `test_challenger_proposal_blocks_unstable_fallback` |
| ready | `ready` | `test_challenger_proposal_is_ready_only_for_isolated_evaluation` |

其余 3 个测试覆盖 fingerprint 绑定、CLI 参数验证、持久化原子性。

**结论**: ✅ 五条业务路径全部有直接测试覆盖，8 个测试全部通过。

### 6.4 覆盖率

Codex 实现记录报告精确覆盖率 84.11%（254/302 statements），超过 80% 门槛。当前环境受 Python 3.13/NumPy 导入问题影响无法复现 coverage 精确值，但该问题是已知环境限制，非 Slice 3 引入。

---

## 7. 静态分析

### 7.1 Pyright

```text
$ pyright dayu/services/write_model_challenger_proposal.py
0 errors, 0 warnings, 0 informations
```

### 7.2 Ruff

```text
$ ruff check --select F,I001 dayu/services/write_model_challenger_proposal.py
All checks passed!
```

### 7.3 git diff --check

```text
(零输出 — 无空白错误)
```

---

## 8. 门禁检查

### 8.1 类型逃逸

```text
$ git diff -U0 | rg '^\+.*(\bAny\b|\bobject\b|cast\(|type:\s*ignore|hasattr|getattr)'
(零匹配)
```

**结论**: ✅ 零类型逃逸新增。

### 8.2 跨 Slice 改动

```text
$ git diff 4e90a69 --stat
 dayu/services/write_model_challenger_proposal.py | 66 ++++++++++++++++++------
 1 file changed, 51 insertions(+), 15 deletions(-)
```

**结论**: ✅ 仅修改 Slice 3 目标文件 `write_model_challenger_proposal.py`，零跨 slice 改动。

### 8.3 过度耦合

| 检查项 | 结果 |
|---|---|
| 新增 import | 零 |
| 新增模块依赖 | 零 |
| 修改公共 API | 零 — `build_write_model_challenger_proposal` 签名不变 |
| 修改 `__all__` | 零 |
| 新增类/全局状态 | 零 |
| 影响其他模块 | 零 — `_finalize_payload` 是模块级私有函数，仅被 `build_write_model_challenger_proposal` 调用 |

**结论**: ✅ 无过度耦合。改动完全自包含于 `build_write_model_challenger_proposal` 函数体内。

### 8.4 架构约束

| 约束 | 状态 |
|---|---|
| 分层架构 `UI -> Service -> Host -> Agent` | ✅ 文件位于 `dayu/services/`，依赖方向正确 |
| 禁止反向依赖 | ✅ 仅 import `_write_artifact_utils`（叶子模块） |
| 禁止 God function | ✅ 函数职责单一（构建提案） |
| 禁止嵌套函数（无充分理由） | ✅ 嵌套已消除 |
| 禁止魔法数字/字符串 | ✅ 无新增字面量 |

---

## 9. Adversarial Failure Pass

以下 adversarial 场景已逐一验证通过：

| 攻击面 | 尝试 | 结果 |
|---|---|---|
| `recent_run_count` 在分支间被修改 | 代码中 `recent_run_count` 仅在 line 366 赋值一次，后续只读 | 不可行 |
| `payload` 引用被替换 | `payload` 仅在 line 372 赋值，后续原地修改 | 不可行 |
| `selected_run_count` 重赋值与闭包时序 | 重赋值在闭包定义之前（line 358 < line 371），直接调用同理 | 语义等价 |
| 分支间 payload 状态泄漏 | 每个分支 `return` 终止执行，无 fall-through | 无泄漏 |
| `_finalize_payload` 签名变更后五处不同步 | 五处 kwargs 完全一致，pyright 检查参数数量/名称 | 受静态检查保护 |

---

## 10. Findings

### High

**零 HIGH findings。**

### Medium

**零 MEDIUM findings。**

### Low

#### L-01: 五处 _finalize_payload 调用的参数重复

- **严重度**: Low
- **位置**: `write_model_challenger_proposal.py:386,400,416,435,470`
- **描述**: 五处 `return _finalize_payload(payload, history_fingerprint=normalized_history_fingerprint, selected_run_count=selected_run_count, recent_run_count=recent_run_count, baseline_run_count=baseline_run_count)` 使用完全相同的四个关键字参数。如果 `_finalize_payload` 签名发生变化，需同步修改五处。
- **判定**: 这是 **accepted W15 的明确设计结果**。五条业务路径的测试矩阵（8 个测试，5 条路径全部直接覆盖）和 pyright 静态检查可在签名变更时捕获不一致。重复参数是直接内联的合理代价，不需要额外 glue seam。
- **缓解**: 现有 5 路径测试矩阵 + pyright 静态检查 + 本次 code review gate。
- **处置**: ✅ ACCEPTED — 不阻塞合并。

#### L-02: Docstring Raises 节未逐条枚举触发条件

- **严重度**: Low
- **位置**: `write_model_challenger_proposal.py:350–351`
- **描述**: Raises 节写 "ValueError: 当指纹、运行数量或窗口数量关系不合法时抛出"，未逐条列出 `_required_non_negative_int` 的两个调用点（`selected_run_count`、`baseline_run_count`）和 `validated_fingerprint` 调用点分别的触发条件。
- **判定**: 当前 docstring 以功能分类（指纹/运行数量/窗口关系）描述异常来源，与项目其他 docstring 的风格一致。无需逐条枚举内部校验函数名。
- **处置**: ✅ ACCEPTED — docstring 已足够准确，不阻塞合并。

---

## 11. Verdict

**PASS — 零 blocking findings**。

### 通过项一览

| 检查项 | 状态 |
|---|---|
| nested `def finish()` 完全删除 | ✅ |
| `return finish()` 零残留 | ✅ |
| `return _finalize_payload(...)` 恰为 5 处 | ✅ |
| 五分支条件语义等价 | ✅ |
| Payload 写入时序等价 | ✅ |
| 调用次数等价（每路径 1 次） | ✅ |
| Payload identity 保持 | ✅ |
| 参数与原闭包精确等价 | ✅ |
| Docstring 不误述异常 | ✅ |
| 测试全部通过（8 + 11） | ✅ |
| pyright 0/0/0 | ✅ |
| ruff 清洁 | ✅ |
| 零类型逃逸 | ✅ |
| 零跨 slice 改动 | ✅ |
| 零过度耦合 | ✅ |
| git diff --check 通过 | ✅ |
| Adversarial failure pass 全通过 | ✅ |

### 未覆盖项与残余风险

1. **L-01**（参数重复）— 已接受，属 W15 明确设计。
2. **L-02**（docstring 未逐条枚举）— 已接受，风格一致。
3. **Python 3.13/NumPy 环境限制** — 阻止 coverage 精确复现，但属已知环境问题（Codex 记录已有 workaround），非 Slice 3 引入。

**建议**: ✅ 可以合并。实现精确遵循 accepted plan v4.4 Slice 3，各项门禁全部通过。

---

## 12. 参考验证数据

```text
=== 结构审计 ===
nested_finish_defs  = 0
return_finish_calls = 0
direct_finalize_returns = 5
新增 Any/object/cast/type:ignore/hasattr/getattr = 0

=== 测试 ===
pytest focused (8):  8 passed
pytest broad (11):   11 passed, 1 skipped
pyright:             0 errors, 0 warnings, 0 informations
ruff:                All checks passed!
git diff --check:    通过

=== 范围 ===
修改文件数:          1（仅 write_model_challenger_proposal.py）
跨 slice 改动:       0
新增依赖:            0
公共 API 变更:       0
```
