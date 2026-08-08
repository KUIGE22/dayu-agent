# Slice 2A require_mapping 类型裁定

- **日期**: 2026-08-07
- **范围**: `write_model_configuration_rollback.py` 5 处 pyright 报错（行 840 / 1225 / 1316 / 1498 / 1831）
- **约束来源**: accepted plan v4.3、C5-CTRL-10、AGENTS 编码硬约束
- **性质**: 只读裁定，不修改代码 / 测试 / plan

---

## 1 问题根因

`require_mapping` 当前签名：

```python
# dayu/services/_write_artifact_utils.py:171
def require_mapping(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> JsonObject:
```

`ModelConfigJsonValue` 定义（`dayu/contracts/model_config.py:66`）：

```python
ModelConfigJsonValue: TypeAlias = (
    ModelConfigScalar
    | list["ModelConfigJsonValue"]
    | dict[str, "ModelConfigJsonValue"]
)
```

`JsonObject` 定义（`_write_artifact_utils.py:22`）：

```python
JsonObject: TypeAlias = Mapping[str, ModelConfigJsonValue]
```

5 个 public validator 签名均为 `payload: Mapping[str, Any]`，调用 `require_mapping(payload, name=...)`。

**pyright 判定链**：`Mapping[str, Any]` → 需要 assignable to `ModelConfigJsonValue`。
`ModelConfigJsonValue` 包含 `dict[str, ModelConfigJsonValue]`，不包含 `Mapping[str, ModelConfigJsonValue]`。
`Mapping` 不是 `dict` 的 subtype（`Mapping` 缺少 `__setitem__` 等 mutator 方法）。
因此 `Mapping[str, Any]` 不 assignable to `ModelConfigJsonValue`。→ 5 处报错。

同时注意：`require_mapping` 返回类型 `JsonObject = Mapping[str, ModelConfigJsonValue]` 本身也不 assignable to `ModelConfigJsonValue`（同样因为 `Mapping` ⊄ `dict`）。这是一个预先存在的类型不对齐，但不在本次 Slice 2A 范围内。

---

## 2 方案对比

### (A) shared require_mapping 输入扩宽为 `ModelConfigJsonValue | JsonObject`

```python
def require_mapping(
    value: ModelConfigJsonValue | JsonObject,
    *,
    name: str,
) -> JsonObject:
```

**pyright 可赋值性验证**：

- `Mapping[str, Any]` assignable to `JsonObject = Mapping[str, ModelConfigJsonValue]`？✅ 是。`Any` 兼容一切类型，`Mapping` covariant in value type → `Mapping[str, Any]` ≤ `Mapping[str, ModelConfigJsonValue]`。
- `Mapping[str, Any]` assignable to `ModelConfigJsonValue | JsonObject`？✅ 是（命中 `JsonObject` 分支）。

**运行时行为**：✅ 不变。函数体仅做 `isinstance(value, Mapping)` 检查 + `return value`（identity-return）。`ModelConfigJsonValue` 中的 `dict` 已是 `Mapping` 的 subtype，无需特殊处理。

**17 helper public surface 影响**：✅ 无。`require_mapping` 输入扩宽不改变任何其他 helper 的签名。

**2B 影响**：✅ 无。`gate_revalidation` / `incident_dossier_revalidation` 的 `_mapping` 返回 `dict[str, Any]`，`dict[str, Any]` assignable to `ModelConfigJsonValue | JsonObject`（`dict` ≤ `dict[str, ModelConfigJsonValue]` 因为 `Any` ≤ `ModelConfigJsonValue`，且 `dict` ≤ `Mapping`）。call-site adapter `dict(require_mapping(...))` 返回类型 `JsonObject`，`dict(JsonObject)` 行为不变。

**是否需 plan v4.4 correction**：❌ 不需。这是 Slice 2A 内部类型修正，不改变 C5-CTRL-10 的 identity-return 决定，不改变 17 helper 契约，不改变 2B 文件的 copy-family adapter 策略。属于 plan 执行时的 pyright 驱动微调。

### (B) overload

```python
@overload
def require_mapping(value: ModelConfigJsonValue, *, name: str) -> JsonObject: ...
@overload
def require_mapping(value: JsonObject, *, name: str) -> JsonObject: ...
def require_mapping(value: ModelConfigJsonValue | JsonObject, *, name: str) -> JsonObject:
```

**评估**：两个 overload 签名仅输入类型不同，返回类型和行为完全相同。overload 的目的是让不同类型输入产生不同类型输出（type narrowing），此处无此需求。引入 overload 增加维护成本，无任何类型安全收益。❌ 过度工程。

### (C) 改 5 个 public validator 签名

将 `payload: Mapping[str, Any]` 改为 `payload: ModelConfigJsonValue`。

**评估**：违反题目硬约束「不能改 public validator 契约」。且 `Mapping[str, Any]` 是更宽的类型，缩窄为 `ModelConfigJsonValue` 会拒绝合法的非-dict custom Mapping 调用方。❌ 违反约束 + 破坏兼容性。

### (D) inline guard / direct identity

在 5 个 validator 内联 `isinstance` 检查后直接 `return payload`，不调用 `require_mapping`。

**评估**：
- 违反 plan「迁移 _mapping → require_mapping」的核心目标。
- 产生 5 处重复 guard 代码，违反 AGENTS「重复逻辑必须抽取」。
- 无法享受 `require_mapping` 的统一错误消息和未来增强。
- ❌ 违反 plan 意图 + 违反编码硬约束。

### (E) 其他（cast / type: ignore / Any 逃逸）

**评估**：全部违反 AGENTS 编码硬约束——「禁止新增重复 helper / cast / type-ignore / Any / object 逃逸」。❌ 直接排除。

---

## 3 唯一推荐：方案 (A)

**精确修订**：

文件 `dayu/services/_write_artifact_utils.py`，行 171，变更签名：

```python
# BEFORE
def require_mapping(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> JsonObject:

# AFTER
def require_mapping(
    value: ModelConfigJsonValue | JsonObject,
    *,
    name: str,
) -> JsonObject:
```

函数体不变。返回类型不变。docstring 不变（已写「要求 JSON 值为映射并原样返回该映射」，语义覆盖扩宽后的输入）。

**可选但推荐**：同步修改 `optional_mapping`（如有相同签名模式），保持两个 mapping helper 一致。

**测试修订**：

Slice 1 差分 corpus 已有 dict 子类 identity / copy 测试（C5-CTRL-10 要求）。建议追加 1 个测试用例：传入自定义 `Mapping` 子类（非 `dict`）验证 `require_mapping` identity-return 且 pyright 无报错。例如：

```python
class CustomMapping(Mapping[str, Any]):
    def __getitem__(self, key: str) -> Any: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...

result = require_mapping(CustomMapping(...), name="test")
assert result is custom_mapping  # identity return
```

**Plan 修订**：不需要 v4.4 correction。方案 A 是 C5-CTRL-10 identity-return 决定的自然类型对齐，不改变任何契约或行为。

---

## 4 风险评估

| 风险 | 级别 | 说明 |
|------|------|------|
| `ModelConfigJsonValue \| JsonObject` 引入 union 让调用方误传非 Mapping 值 | 极低 | `isinstance(value, Mapping)` 运行时 guard 仍生效；pyright 对 union 的类型检查严格 |
| 2B 文件 `_mapping` 返回 `dict[str, Any]` 在扩宽后有新报错 | 无 | `dict[str, Any]` assignable to `ModelConfigJsonValue`（`dict` ≤ `dict[str, ModelConfigJsonValue]` via `Any` ≤ `ModelConfigJsonValue`），且 assignable to `JsonObject`（`dict` ≤ `Mapping`） |
| 其他 helper（`canonical_json_str` 等）输入类型也需要同步扩宽 | 无 | 这些 helper 接收 `require_mapping` 返回值 `JsonObject` 作为输入，已有隐式兼容（`Mapping` 值传入 `ModelConfigJsonValue` 参数时，pyright 当前可能已有报错，但那是独立问题，不在 Slice 2A 范围） |
| C5-CTRL-10 identity-return 决定被违反 | 无 | 方案 A 不改变 return 语义，仅扩宽输入接受范围 |

---

## 5 Verdict

**PASS — 推荐方案 (A)**

修改 1 个签名（`require_mapping` 输入 `ModelConfigJsonValue` → `ModelConfigJsonValue | JsonObject`），解决 5 处 pyright 报错，零运行时行为变更，零契约变更，无需 plan v4.4。

理由穷尽：
1. 是唯一同时满足「不改 public validator 契约」「不引入 cast/type-ignore/Any 逃逸」「不产生重复代码」「保持 identity-return」的方案。
2. `Mapping[str, Any]` 对 `JsonObject = Mapping[str, ModelConfigJsonValue]` 的 pyright 可赋值性已验证（`Any` 兼容一切）。
3. 17 helper public surface 不受影响，2B 不受影响。
4. 类型语义精确：`require_mapping` 的职责是「接受一个可能是映射的 JSON 值，验证它是映射，返回它」——接受 `JsonObject`（已经是映射的类型）是自然的。
