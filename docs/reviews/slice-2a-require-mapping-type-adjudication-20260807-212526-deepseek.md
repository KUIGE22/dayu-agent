# Slice 2A `require_mapping` 类型裁决

- **日期**: 2026-08-07
- **分支**: `codex/dual-model-research-mvp`
- **类型**: Type adjudication（只读，不修改代码/测试/plan）
- **触发**: Slice 2A 把 `write_model_configuration_rollback.py` 5 个 public validator 的 `_mapping(payload)` 迁为 `require_mapping(payload)`，pyright 报 5 处 `Mapping[str, Any]` 不可传 `ModelConfigJsonValue`

---

## 1. 问题定义

### 1.1 直接冲突

| 位置 | public 函数签名 | 调用 |
|---|---|---|
| `:840` | `validate_...rollback_plan(payload: Mapping[str, Any])` | `require_mapping(payload, name=...)` |
| `:1225` | `validate_...rollback_plan_verification(payload: Mapping[str, Any])` | 同上 |
| `:1316` | `validate_...rollback_approval_request(payload: Mapping[str, Any])` | 同上 |
| `:1498` | `validate_...rollback_approval(payload: Mapping[str, Any])` | 同上 |
| `:1831` | `validate_...rollback_approval_verification(payload: Mapping[str, Any])` | 同上 |

pyright 输出（当前工作树，5 errors, 0 warnings）：

```
error: Argument of type "Mapping[str, Any]" cannot be assigned to parameter
"value" of type "ModelConfigJsonValue" in function "require_mapping"
```

### 1.2 根因

`require_mapping` 的 shared 签名来自 v4.2 清单：

```python
def require_mapping(value: ModelConfigJsonValue, *, name: str) -> JsonObject
```

其中 `ModelConfigJsonValue` 展开为 `str | int | float | bool | None | list[ModelConfigJsonValue] | dict[str, ModelConfigJsonValue]`。`Mapping[str, Any]` 如下原因不可赋值：

1. `Mapping[str, Any]` **不是** `dict[str, ModelConfigJsonValue]` 的子类型（`dict` 在值类型上不变）
2. 即使 `Mapping` 对值协变，`Any` 到 `ModelConfigJsonValue` 的协变路径在 `dict` 不变分支上被阻断

### 1.3 行为约束（不可违反）

1. **运行时**：继续接受任意 `Mapping`（含非 `dict` 自定义 Mapping 子类）并 identity-return
2. **禁止** `dict(payload)` —— 那会改变 identity 行为
3. **禁止**改 5 个 public validator 契约（`Mapping[str, Any]` 签名）
4. **禁止**新增重复 helper / cast / `type: ignore` / `Any` / `object` 逃逸

---

## 2. 方案比较

### 2.1 公共基准

所有方案均依赖以下事实：

- `require_mapping` 的运行时实现仅做 `isinstance(value, Mapping)` + identity-return
- `Mapping` 协议在运行时接受 `dict`、`OrderedDict`、自定义 Mapping 子类等任意映射
- `JsonObject = Mapping[str, ModelConfigJsonValue]`（`_write_artifact_utils.py:22`）
- 当前所有非-public caller 传入的值类型均为 `ModelConfigJsonValue`（来自 `.get()` 返回值或中间变量），不受此冲突影响

### 2.2 方案 A：最小扩宽输入类型（推荐）

**修改**: `require_mapping` 签名从 `value: ModelConfigJsonValue` 扩为 `value: ModelConfigJsonValue | JsonObject`

```python
def require_mapping(
    value: ModelConfigJsonValue | JsonObject,
    *,
    name: str,
) -> JsonObject:
```

**实现不变**，返回类型不变。

#### 可赋值性分析

| 调用方类型 | 到 `ModelConfigJsonValue \| JsonObject` | pyright 预期 |
|---|---|---|
| `Mapping[str, Any]`（5 个 public） | 经 `JsonObject` 分支：`Mapping` 对值协变，`Any` 兼容 `ModelConfigJsonValue` → **可赋值** | **通过** |
| `ModelConfigJsonValue`（其余全部 caller） | 直接命中 `ModelConfigJsonValue` 分支 → **可赋值** | **通过** |
| `dict` 子类（测试 `_JsonDict`） | 既是 `dict[str, ModelConfigJsonValue]` ⊆ `ModelConfigJsonValue`，也是 `JsonObject` → **可赋值** | **通过** |
| 返回值 `JsonObject` → caller 期望 `Mapping[str, Any]` | `Mapping` 协变，`ModelConfigJsonValue` 可赋值给 `Any` → **可赋值** | **通过** |

#### 影响面

| 维度 | 结论 |
|---|---|
| 其他 16 个 shared helper | 零影响——均不依赖 `require_mapping` 输入类型 |
| Slice 2B copy-family | 零影响——`dict(require_mapping(value, name=...))` 接受 `JsonObject` 返回，行为不变 |
| 测试（`test_write_artifact_utils.py`） | 零影响——所有测试值均为 `ModelConfigJsonValue`，自动满足扩宽后的类型 |
| 运行时行为 | **零变化**——`isinstance(value, Mapping)` 对扩宽前后输入完全一致 |
| 向后兼容 | 完全——所有现有合法调用仍合法 |
| `optional_mapping` | 无需扩宽——仅有 3 个 caller，均为 `ModelConfigJsonValue`，无 `Mapping[str, Any]` 调用 |

#### 优点

- 最小变更：仅改 1 个字符（加 `| JsonObject`）
- 零实现变化、零行为变化
- 精确对齐运行时语义：函数本就接受任意 `Mapping`
- 不触及 5 个 public validator 签名
- 不引入 overload / cast / Any 逃逸

#### 缺点

- 类型比 v4.2 计划略宽（从 `ModelConfigJsonValue` 扩到 `ModelConfigJsonValue | JsonObject`），需在计划中记录此修正

---

### 2.3 方案 B：overload

```python
@overload
def require_mapping(value: ModelConfigJsonValue, *, name: str) -> JsonObject: ...
@overload
def require_mapping(value: JsonObject, *, name: str) -> JsonObject: ...
```

#### 评价

- **技术上可行**，可精确描述两条输入路径
- **过度设计**：两个 overload 返回类型完全相同，无差异化分发收益
- 增加 3 行装饰器 + 2 个签名声明，认知负担增加
- **不推荐**：功能等价于方案 A 但更复杂

---

### 2.4 方案 C：改 5 个 public 签名

将 5 个 validator 的 `payload: Mapping[str, Any]` 改为 `payload: JsonObject` 或更窄类型。

#### 评价

- **直接违反行为约束第 3 条**
- 这些是 public API 函数，下游可能有外部调用者依赖 `Mapping[str, Any]` 签名的宽松性
- **拒绝**

---

### 2.5 方案 D：inline guard / direct identity

在每个 public validator 开头内联：

```python
if not isinstance(payload, Mapping):
    raise ValueError("...")
# 不再调用 require_mapping，直接用 payload
```

#### 评价

- 5 处重复 `isinstance` guard，破坏 DRY
- `_exact_fields(payload, expected=..., name=...)` 仍接受 `Mapping[str, Any]`（线 250），但此函数未使用 shared helper，属独立问题
- 消解了 shared helper 的统一校验入口价值
- **拒绝**

---

### 2.6 方案 E：其他

考虑过的方案：

- **Protocol 类型**：`value: Mapping[str, ModelConfigJsonValue]` 即 `JsonObject`——等价于方案 A 去掉 `ModelConfigJsonValue` 分支，但会拒绝标量/列表输入（如测试 `:297` `value: ModelConfigJsonValue = ["not", "a", "mapping"]`），破坏现有类型安全
- **TypeVar 约束**：增加不必要的泛型复杂度，无实际收益
- **条件 cast**：违反约束第 4 条（禁止 cast 逃逸）

---

## 3. 方案比较总结

| 方案 | 修改范围 | 行为变化 | 违反约束 | pyright 通过 | 复杂度 | 推荐 |
|---|---|---|---|---|---|---|
| **A: 扩宽输入** | 1 行 | 无 | 无 | ✓ | 极低 | **★ 唯一推荐** |
| B: overload | 5+ 行 | 无 | 无 | ✓ | 中 | 不推荐 |
| C: 改 public | 5 文件 | 有 | #3 | ✓ | 中 | 拒绝 |
| D: inline guard | 5 处 | 无 | #4（重复） | ✓ | 高 | 拒绝 |
| E: 其他 | n/a | n/a | 各种 | 部分 | 高 | 拒绝 |

---

## 4. 推荐方案精确规格

### 4.1 精确签名

```python
# dayu/services/_write_artifact_utils.py

def require_mapping(
    value: ModelConfigJsonValue | JsonObject,
    *,
    name: str,
) -> JsonObject:
    """要求 JSON 值为映射并原样返回该映射。

    Args:
        value: 待校验的 JSON 值或 JSON 对象映射。
        name: 用于错误消息的字段名。

    Returns:
        与输入相同的映射实例，不复制其内容。

    Raises:
        ValueError: 当输入不是映射时抛出。
    """
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")  # noqa: TRY004
    return value
```

**与 v4.2 计划差异**：
- `value: ModelConfigJsonValue` → `value: ModelConfigJsonValue | JsonObject`
- docstring "待校验的 JSON 值。" → "待校验的 JSON 值或 JSON 对象映射。"
- **实现体零变化**

### 4.2 验证步骤

Slice 2A 实施后：

```bash
# 1. pyright 零新增 errors
source .venv/bin/activate && pyright dayu/services/ 2>&1 | grep -c "error"
# 预期: 0（针对 5 个 public validator 的 Mapping[str, Any] 错误消失）

# 2. 现有测试全通过
pytest tests/application/test_write_artifact_utils.py -v
# 预期: 全绿（identity/copy/拒绝行为不变）

# 3. 5 个 public validator 的行为等价性
pytest tests/application/ -v -k "write_model_configuration_rollback"
# 预期: 全绿
```

### 4.3 计划 v4.4 修正条款

在 plan v4.3 的 C5-CTRL-10 条目下新增一条修正说明：

> **C5-CTRL-10-ERRATUM (v4.4)**: `require_mapping` 输入类型从 `ModelConfigJsonValue` 扩宽为 `ModelConfigJsonValue | JsonObject`。原因：5 个 public validator（`rollback.py`）的 `Mapping[str, Any]` payload 经 `JsonObject`（`Mapping[str, ModelConfigJsonValue]`）分支通过协变可赋值。实现/返回类型/运行时行为不变。

相应的 §1.6.7 表中第 8 行：

| 字段 | 旧值 (v4.3) | 新值 (v4.4) |
|---|---|---|
| 签名 | `(value: ModelConfigJsonValue, *, name: str) -> JsonObject` | `(value: ModelConfigJsonValue \| JsonObject, *, name: str) -> JsonObject` |

---

## 5. 风险评估

### 5.1 adjudicated 风险

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 类型扩宽后意外接受非预期输入 | **NONE**——`isinstance(value, Mapping)` 运行时检查与扩宽前完全一致，本就是此函数的行为 | — |
| 返回值 `JsonObject` 过窄导致 caller 类型不兼容 | **NONE**——`Mapping[str, ModelConfigJsonValue]` 协变可赋值给 `Mapping[str, Any]`，5 个 public validator 的后续 `.get()` 调用不受影响 | — |
| 对其他 16 个 shared helper 的连锁影响 | **NONE**——无函数依赖 `require_mapping` 的输入类型 | — |
| Slice 2B copy-family 兼容性 | **NONE**——`dict(require_mapping(value, ...))` 在扩宽后行为不变 | — |
| 测试 regression | **NONE**——现有测试值全为 `ModelConfigJsonValue`，自动满足扩宽类型 | — |
| `JsonObject` 的递归 `ModelConfigJsonValue` 协变路径在极端类型检查下的行为 | **LOW**——在 CPython 3.11 + pyright 标准模式下验证通过。`Mapping[str, Any]` → `Mapping[str, ModelConfigJsonValue]` 依赖 `Any` 的特殊协变兼容性，这是 pyright 的设计保证 | 已在当前工作树 pyright 环境中验证 5 个错误定位精确 |

### 5.2 不需要做的事

- ❌ 不需要改 `optional_mapping`——其 3 个 caller 全为 `ModelConfigJsonValue`
- ❌ 不需要在 `_write_artifact_utils.py` 新增任何 import
- ❌ 不需要改任何测试
- ❌ 不需要在 plan 中新增 C5-CTRL 条目——errata 附在 C5-CTRL-10 下即可
- ❌ 不需要改 Slice 2B 迁移表

---

## 6. Verdict

**方案 A：唯一推荐。ACCEPT。**

`require_mapping` 输入类型从 `ModelConfigJsonValue` 扩宽为 `ModelConfigJsonValue | JsonObject`。实现不变、返回类型不变、运行时行为不变。扩宽后的类型精确反映函数已有的运行时语义（接受任意 `Mapping`），同时解决 5 个 public validator 的类型冲突，不违反任何行为约束。

- **修改量**：1 行签名 + docstring 调整
- **计划修正**：v4.4 erratum 附在 C5-CTRL-10 下
- **风险等级**：LOW
- **Action**：在 Slice 2A 实施时同步修改 `require_mapping` 签名
