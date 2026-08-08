# Code Re-Review — Slice 3 W15: finish() 内联消除

- **审查者**: MiMo 第二路复审
- **日期**: 2026-08-08
- **基线**: `4e90a69` (`gateflow: accept write artifact callers slice 2b`)
- **分支**: `codex/dual-model-research-mvp`
- **审查范围**: 工作区未提交改动（`git diff HEAD`）
- **Approved plan**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v4.4 Slice 3
- **裁决输入**: `docs/reviews/slice-3-code-review-adjudication-20260808-codex.md`

---

## 1. 复审任务

Controller 裁决要求双路 re-review 确认：

1. DS L-01/L-02 与 MiMo L1/L2/L3 均按裁决关闭。
2. Open High/Medium/Low 保持 `0`。
3. 无需且没有 production/test/README/plan fix。
4. W15 的五处 direct inline 是 accepted design；不得通过新增 wrapper 或其它 glue seam 重新引入间接层。
5. Docstring 已按功能完整描述用户可见 `ValueError`，无需枚举内部 helper。
6. HEAD pre-existing Ruff `UP035 × 1`、`TRY004 × 4` 继续按 zero-delta baseline 处理。

---

## 2. 逐项裁决确认

### 2.1 DS L-01 — 五处参数重复 → CLOSED / non-defect

**初审 observation**: 五处 `_finalize_payload` 直接调用重复相同参数，未来签名变化时需同步修改。

**裁决理由**: accepted W15 明确要求删除 nested `finish()` 并原位替换为 direct `_finalize_payload(...)`；参数重复是该设计的预期结果。新增 wrapper 会逆转 W15 目标并引入禁止的 glue seam。Pyright + 五路径测试可防止签名漂移。

**复审确认**: ✅ 同意裁决。当前代码中 5 处 `_finalize_payload` 调用的 kwargs 完全一致（AST 审计确认），参数重复是 accepted W15 的 direct-inline 设计，不是意外耦合。pyright 0 errors 确认静态检查覆盖。CLOSED。

### 2.2 DS L-02 — Docstring Raises 未逐条枚举 → CLOSED / non-defect

**初审 observation**: Raises 节未逐条列出 `_required_non_negative_int` 的两个调用点和 `validated_fingerprint` 调用点分别的触发条件。

**裁决理由**: 当前 docstring "当指纹、运行数量或窗口数量关系不合法时抛出" 按功能覆盖了全部用户可见 `ValueError`。Docstring 应描述稳定调用者契约，不复制内部调用清单。

**复审确认**: ✅ 同意裁决。复核实际异常源：
- `validated_fingerprint()` → `ValueError`（指纹不合法）
- `_required_non_negative_int(selected_run_count, ...)` → `ValueError`（运行数量不合法）
- `_required_non_negative_int(baseline_run_count, ...)` → `ValueError`（运行数量不合法）
- `selected_run_count != recent_run_count + baseline_run_count` → `ValueError`（窗口数量关系不合法）

docstring 以功能分类描述，不泄漏内部 helper 名称，符合 AGENTS.md 编码硬约束。CLOSED。

### 2.3 MiMo L1 — ruff UP035 → CLOSED / non-defect

**初审 observation**: 文件存在 ruff `UP035`（`from typing import Mapping, Sequence` 应改为 `from collections.abc`）。

**裁决理由**: HEAD 与当前全规则 multiset 均为 `UP035 × 1`，本 slice zero delta。Pre-existing baseline 不构成本 slice finding。

**复审确认**: ✅ 同意裁决。独立验证：

```text
当前:  UP035 × 1, TRY004 × 4  (共 5 errors)
base:  UP035 × 1, TRY004 × 4  (共 5 errors)
delta: zero
```

CLOSED。

### 2.4 MiMo L2 — ruff TRY004 × 4 → CLOSED / non-defect

**初审 observation**: 文件存在 ruff `TRY004 × 4`（`validate_write_model_challenger_proposal` 中 4 处 `raise ValueError` 应为 `TypeError`）。

**裁决理由**: 四项均在 HEAD 已存在；HEAD 与当前计数完全一致，本 slice zero delta，且对应 validator 不在 W15 范围。

**复审确认**: ✅ 同意裁决。4 处 TRY004 均位于 `validate_write_model_challenger_proposal` 函数（line 505、549、561、600），该函数不在本 slice 修改范围。CLOSED。

### 2.5 MiMo L3 — 参数重复 → CLOSED / non-defect

**初审 observation**: 五处 finalize 参数重复会要求未来同步更新。

**裁决理由**: 与 DS L-01 相同。参数重复是 accepted W15 明示的 direct-inline 设计。

**复审确认**: ✅ 同意裁决。与 DS L-01 同一事实的重复观察，CLOSED。

---

## 3. 独立验证（复审重跑）

### 3.1 pytest

```text
$ pytest tests/application/test_write_model_challenger_proposal.py -q
8 passed in 0.60s
```

✅ 全部通过。

### 3.2 pyright

```text
$ pyright dayu/services/write_model_challenger_proposal.py
0 errors, 0 warnings, 0 informations
```

✅ 零错误。

### 3.3 ruff delta

```text
当前:  UP035 × 1, TRY004 × 4  (5 errors)
base:  UP035 × 1, TRY004 × 4  (5 errors)
delta: zero
```

✅ 零新增。

### 3.4 结构审计（AST）

```text
nested_finish_defs=0
return_finish_calls=0
direct_finalize_returns=5
```

✅ 与初审一致。

### 3.5 五分支核心等价性

| # | 分支 | 条件 | payload 写入时序 | finalize 调用 | 等价 |
|---|------|------|-----------------|--------------|------|
| 1 | global-block | `if global_reasons:` | evaluated_routes → reason_codes → finalize | 1 次 | ✅ |
| 2 | not-needed | `if not role_decisions:` | evaluated_routes → role_decisions → status/action/reason_codes → finalize | 1 次 | ✅ |
| 3 | ambiguous | `if ambiguous:` | 同 2 + status/reason_codes → finalize | 1 次 | ✅ |
| 4 | blocked | `if blocked:` | 同 2 + reason_codes → finalize | 1 次 | ✅ |
| 5 | ready | else | 同 2 + overrides/args/status/action/reason_codes → finalize | 1 次 | ✅ |

5 处 `_finalize_payload` 调用均为同一 `payload` 局部变量，keyword-only 参数名与值来源与原闭包完全一致。

✅ 核心等价性维持。

---

## 4. Fix 确认

| 类别 | 是否有 fix |
|------|-----------|
| 生产代码 fix | 否 — 无需要、无实际 |
| 测试 fix | 否 — 无需要、无实际 |
| README fix | 否 — 本 slice 不改变公共接口或用户工作流 |
| Plan fix | 否 — plan 与实现一致 |

✅ 无需且没有 production/test/README/plan fix。

---

## 5. Open Findings

| 级别 | 数量 |
|------|------|
| High | 0 |
| Medium | 0 |
| Low | 0 |

DS L-01/L-02 与 MiMo L1/L2/L3 均已 CLOSED，不计入 open findings。

---

## 6. Verdict

**RE-REVIEW PASS — 裁决全部确认，核心等价性维持。**

确认清单：

1. ✅ DS L-01 CLOSED / non-defect — 参数重复是 accepted W15 direct-inline 设计。
2. ✅ DS L-02 CLOSED / non-defect — docstring 按功能覆盖全部用户可见 ValueError。
3. ✅ MiMo L1 CLOSED / non-defect — UP035 × 1 为 HEAD pre-existing baseline。
4. ✅ MiMo L2 CLOSED / non-defect — TRY004 × 4 为 HEAD pre-existing baseline。
5. ✅ MiMo L3 CLOSED / non-defect — 同 DS L-01。
6. ✅ Open H/M/L = 0。
7. ✅ 无需且没有 production/test/README/plan fix。
8. ✅ 五处 direct inline 是 accepted design，未重新引入间接层。
9. ✅ 核心等价性（五分支、时序、调用次数、payload identity、参数）维持。

---

## 7. Artifact 信息

- **复审 artifact**: `docs/reviews/code-rereview-slice-3-20260808-mimo.md`
- **初审 artifact**: `docs/reviews/code-review-slice-3-20260808-mimo.md`
- **Controller 裁决**: `docs/reviews/slice-3-code-review-adjudication-20260808-codex.md`
- **实现 artifact**: `docs/reviews/slice-3-challenger-proposal-finish-implementation-20260808-codex.md`
- **Approved plan**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v4.4 Slice 3
