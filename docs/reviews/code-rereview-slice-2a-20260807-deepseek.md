# Slice 2A 修复后复审 — DeepSeek 审查路

- **日期**: 2026-08-07
- **分支**: `codex/dual-model-research-mvp`
- **基线**: `8350226`
- **审查者**: DeepSeek
- **状态**: CODE REREVIEW / DUAL MODEL

---

## 1. 审查输入

| # | 文件 | 角色 |
|---|---|---|
| 1 | `docs/reviews/code-review-20260807-220136.md` | 初审 artifact（本审查的判决来源） |
| 2 | `docs/reviews/slice-2a-write-artifact-callers-fix-20260807-codex.md` | 修复记录（Controller 裁决 + 四处生产修复 + 测试） |
| 3 | `docs/reviews/slice-2a-write-artifact-callers-implementation-20260807-codex.md` | 原始实现 artifact |

---

## 2. 初审 Finding 逐项复审

### 2.1 Finding 1-MEDIUM — `changed_roles` guard 接受 dict/str

**初审描述**: `format_write_model_challenger_promotion_report` 和 `format_write_model_configuration_change_request_report` 中 `isinstance(changed_roles, (dict, list, str))` 允许 dict/str 导致静默迭代语义错误。

**修复**（fix artifact #1, #2）:
- `write_model_challenger_promotion.py:1013`: `if not isinstance(changed_roles, list):`
- `write_model_configuration_change.py:1490`: `if not isinstance(changed_roles, list):`

**生产代码核对**:

```text
# promotion.py:1012-1016
changed_roles = review.get("changed_roles", [])
if not isinstance(changed_roles, list):
    raise TypeError(
        "promotion proposal model_plan_review changed_roles must be a list"
    )

# change.py:1489-1493
changed_roles = target.get("changed_roles", [])
if not isinstance(changed_roles, list):
    raise TypeError(
        "configuration change request target changed_roles must be a list"
    )
```

- `isinstance(changed_roles, (dict, list, str))` → `isinstance(changed_roles, list)` ✓
- 仅 `list` 通过，dict/str 被正确拒绝 ✓
- 错误消息精确，与 guard 条件一致 ✓
- `TypeError` 保留（fix artifact 明示"保留原 TypeError 精确消息"） ✓

**回归测试核对**:

两个参数化测试各覆盖 `dict[str, str]` 与 `str` 两类畸形输入，断言精确异常类型与消息：

```python
# promotion test
@pytest.mark.parametrize("malformed_changed_roles", [{"primary": "mimo"}, "primary"])
def test_promotion_report_rejects_non_list_changed_roles(
    malformed_changed_roles: dict[str, str] | str,
) -> None:
    with pytest.raises(TypeError) as exc_info:
        format_write_model_challenger_promotion_report(
            {"model_plan_review": {"changed_roles": malformed_changed_roles}}
        )
    assert str(exc_info.value) == (
        "promotion proposal model_plan_review changed_roles must be a list"
    )

# change test — 同模式，断言 "configuration change request target changed_roles must be a list"
```

- 参数化 dict + str 两类反例 ✓
- 断言精确 `TypeError` 异常类型 ✓
- 断言精确错误消息 ✓
- 类型签名 `dict[str, str] | str`，无 Any/object/cast/type-ignore ✓

**Verdict**: **CLOSED** — 两处 guard 已收紧为仅接受 `list`，dict/str 回归测试充分（4 用例：2 文件 × 2 反例），错误消息与 guard 一致。

---

### 2.2 Finding 2-LOW — rollback `receipt_source_path` TypeError→ValueError

**初审描述**: `build_write_model_configuration_operator_rollback_approval` 和 `verify_write_model_configuration_operator_rollback_approval` 中 `receipt_source_path` 的 isinstance guard 使用 `TypeError` 而非模块惯例 `ValueError`。

**修复**（fix artifact #3, #4）:
- `write_model_configuration_rollback.py:1409`: `raise ValueError(...)`（build 函数）
- `write_model_configuration_rollback.py:1745`: `raise ValueError(...)`（verify 函数）

**生产代码核对**:

```text
# rollback.py:1407-1409
receipt_source_path = receipt_source.get("path")
if not isinstance(receipt_source_path, str):
    raise ValueError("source_application_receipt path must be a string")

# rollback.py:1743-1745
receipt_source_path = receipt_source.get("path")
if not isinstance(receipt_source_path, str):
    raise ValueError("source_application_receipt path must be a string")
```

- 两处均为 `raise ValueError(...)` ✓
- 错误消息不变 ✓
- 与同模块其他校验（`require_mapping` → `ValueError`、`validated_fingerprint` → `ValueError`、`absolute_path` → `ValueError`、`require_text` → `ValueError`）一致 ✓

**Verdict**: **CLOSED** — 两处异常类型已统一为 `ValueError`，与模块惯例一致。

---

## 3. 新增问题审查

### 3.1 修复是否引入新问题？

| 检查项 | 结果 |
|---|---|
| `changed_roles` guard 是否过严（如拒绝合法的 tuple） | **否** — JSON 反序列化后 `changed_roles` 始终为 `list`（来自 `.get("changed_roles", [])` 默认值或已校验 payload），tuple 不会出现在正常路径 |
| `changed_roles` guard 的 `TypeError` 是否应改为 `ValueError` | **低优先级** — 初审仅指出 error type 不一致，但此处是格式函数（非核心校验），`TypeError` 语义上对应于"类型不匹配"场景。保留 `TypeError` 在 Controller 裁决范围内（fix artifact 明示"保留原 TypeError 精确消息"） |
| `receipt_source_path` 的 `ValueError` 是否与其他模块一致 | **是** — 同模块内 `require_mapping`、`validated_fingerprint`、`absolute_path`、`require_text` 均使用 `ValueError` |
| 修复是否触及了非 fix scope 的代码 | **否** — 仅四处生产行 + 两个测试文件的新测试函数 |
| 是否新增 Any/object/cast/type-ignore | **否** — 测试参数类型为精确的 `dict[str, str] \| str` |

### 3.2 Adversarial Failure Pass（增量）

| 攻击面 | 结论 |
|---|---|
| `changed_roles` guard 收紧是否破坏现有调用方 | **否** — validate 路径已在 format 之前校验 `changed_roles` 为合法 list；report 路径的内部调用方始终传入合法 payload |
| `receipt_source_path` ValueError 变更是否影响上层错误处理 | **否** — 正常路径中 receipt path 始终为合法 str（由上游 validate/load 保证）；异常路径中 `ValueError` 与模块惯例一致，调用方的 `except ValueError` 现在正确捕获 |
| 新增测试是否引入 fixture 污染 | **否** — 新测试为纯 unit test（`@pytest.mark.unit`），不依赖 tmp_path 或外部 fixture |

---

## 4. 全量验证

### 4.1 测试

```text
258 passed in 11.15s
```

shared helper 单文件（`test_write_artifact_utils.py`）`23 passed`，不变。

新增 4 个参数化 report 回归用例分布在 caller 测试文件中：
`test_write_model_challenger_promotion.py` 2 例（dict/str 反例）、
`test_write_model_configuration_change.py` 2 例（dict/str 反例），不属 shared helper 聚焦入口。

### 4.2 Pyright

```text
pyright dayu/services/ → 0 errors, 0 warnings, 0 informations
```

### 4.3 Ruff F/I

```text
ruff check --select F,I001 <fix-targeted 5 files> → All checks passed!
```

### 4.4 结构自审

| 检查项 | 结果 |
|---|---|
| Cohort B 9 文件 diff | **零 diff ✓** |
| Cohort A eligible 私有定义残留 | **零 ✓**（`^def _canonical_json`、`^def _fingerprint` 等 10 文件均无） |
| Defer 定义保留 | **全部保留 ✓**（18 个 defer 定义逐一定位确认） |
| Any/object/cast/type-ignore 新增逃逸 | **零 ✓** |
| `git diff --check` | **通过 ✓** |
| 5 rollback `Mapping[str, Any]` public 契约 | **零变更 ✓** |
| `require_mapping` 类型 | **仅扩宽 ✓** |

---

## 5. Verdict

| 初审 Finding | 状态 |
|---|---|
| 1-MEDIUM — `changed_roles` guard dict/str 逃逸 | **CLOSED** |
| 2-LOW — rollback `receipt_source_path` TypeError vs ValueError | **CLOSED** |

### 统计

| 严重度 | Open |
|---|---|
| 严重 | 0 |
| 高 | 0 |
| 中 | 0 |
| 低 | 0 |

**Open Findings: 0**

### 最终 Verdict

**PASS — 所有初审 finding 已正确关闭，无新增 findings**

四处生产修复（2 changed_roles guard 收紧 + 2 receipt_source_path ValueError 统一）精确解决初审 findings，4 个参数化用例（2 测试函数 × dict/str 双反例，分属 promotion 与 change 两个测试文件）验证 guard 行为。258 测试全通过，pyright `0 errors`，Ruff F/I 零新增，Cohort B 零 diff，defer 定义全部保留，无 Any/object/cast/type-ignore 新增逃逸。
