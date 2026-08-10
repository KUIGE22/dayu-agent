# Plan Review — Slice 1.2 Frozen-Slots Guard Erratum

## Scope

- Reviewed target：`docs/plans/2026-08-10-investment-platform-restoration.md` S12-CTRL-08 + `docs/reviews/plan-fix-20260810-slice-1.2-frozen-slots-guard-codex.md`
- Reviewer：MiM Native
- Review clock：`2026-08-10`（本机系统时钟）
- Output file：`docs/reviews/plan-review-20260810-slice-1.2-frozen-slots-guard-mimo-native.md`
- Focus：AST 豁免精确性、frozen/slots defensive-copy 契约可实施性、allowlist 范围

## Assumptions Tested

1. S12-CTRL-08 的 AST 豁免只放行 `object.__setattr__` call target，其他 `object/Any/cast/ignore/getattr/hasattr` 仍拒绝。
2. `source.py` 的所有 `object` 使用都是 `object.__setattr__()` 调用，无裸 `object` 或其它逃逸。
3. Allowlist 扩展（`test_architecture_boundaries.py`）是最小且必要的。
4. Frozen/slots defensive-copy 契约在 Python 3.11 中可实施。

## Verification

### AST Exemption Precision

S12-CTRL-08 规定的豁免 AST 模式：

```text
ast.Name(id="object")
  → ast.Attribute(value=<same node>, attr="__setattr__")
    → ast.Call.func
```

独立验证结果（AST 解析）：

| 模式 | AST 结构 | 是否匹配豁免 | 预期 |
|------|---------|-------------|------|
| `object.__setattr__(self, "field", value)` | Name→Attribute(attr=\_\_setattr\_\_)→Call | ✅ MATCH | EXEMPT |
| `object` | Name(id="object") | ❌ 不匹配 | REJECT |
| `object()` | Name→Call | ❌ 不匹配 | REJECT |
| `object.__new__(cls)` | Name→Attribute(attr=\_\_new\_\_) | ❌ 不匹配 | REJECT |
| `x: object` | Name(Annotation) | ❌ 不匹配 | REJECT |
| `isinstance(x, object)` | Name(Arg) | ❌ 不匹配 | REJECT |
| `import object as o` → `o()` | Alias→Name | ❌ 不匹配 | REJECT |

✅ 豁免精确——只有 `object.__setattr__()` call target 被放行，所有其它 `object` 形态仍命中。

### source.py Object Usage Audit

AST 扫描 `dayu/investment/domain/source.py` 全部 `object` 使用：

| 行号 | 代码 | 是否 `__setattr__` call |
|------|------|------------------------|
| 442 | `object.__setattr__(self, "created_at", ...)` | ✅ |
| 443 | `object.__setattr__(self, "updated_at", ...)` | ✅ |
| 504 | `object.__setattr__(self, "created_at", ...)` | ✅ |
| 505 | `object.__setattr__(self, "updated_at", ...)` | ✅ |
| 631 | `object.__setattr__(self, "created_at", ...)` | ✅ |
| 632 | `object.__setattr__(self, "updated_at", ...)` | ✅ |
| 706 | `object.__setattr__(self, "config", MappingProxyType(...))` | ✅ |
| 740 | `object.__setattr__(self, "config", MappingProxyType(...))` | ✅ |
| 797 | `object.__setattr__(self, "config", MappingProxyType(...))` | ✅ |
| 798 | `object.__setattr__(self, "created_at", ...)` | ✅ |
| 799 | `object.__setattr__(self, "updated_at", ...)` | ✅ |

✅ 全部 11 处 `object` 使用都是 `object.__setattr__()` call target——无裸 `object`、`object()`、`object.__new__()` 或类型标注。

### Frozen/Slots Defensive-Copy Contract

`source.py` 中 `object.__setattr__` 的使用场景：

1. **datetime UTC normalization**：`object.__setattr__(self, "created_at", _validate_aware_utc(self.created_at, "created_at"))` — frozen dataclass 在 `__post_init__` 中将 aware UTC datetime 归一化后写回自身字段。✅

2. **Mapping defensive copy**：`object.__setattr__(self, "config", MappingProxyType(dict(self.config)))` — frozen dataclass 在 `__post_init__` 中将用户传入的 Mapping 防御性复制为只读 `MappingProxyType` 后写回自身字段。✅

两者都是 frozen+slots dataclass 在 `__post_init__` 中把已严格校验的值写回自身字段的唯一合法方式。Python 3.11 的 `dataclass(frozen=True, slots=True)` 在 `__init__` 中已通过 `object.__setattr__` 设置字段，`__post_init__` 中再次写回必须显式使用同一机制。✅

### Allowlist Scope

S12-CTRL-08 把 `tests/investment/test_architecture_boundaries.py` 加入 Slice 1.2 allowlist。

✅ 必要且最小——guard 需要新增 self-test 证明豁免生效且负例仍拒绝，不扩大到其它文件。

### Guard Self-Test Requirements

Plan 要求 "guard 自测必须包含 exact positive 与上述 negative matrix"：

- **Positive**：`object.__setattr__(self, "field", validated_value)` 通过 guard（不报违规）
- **Negative**：裸 `object`、`object()`、`object.__new__`、别名导入、`Any/cast/type: ignore/getattr/hasattr` 仍报违规

✅ 自测矩阵覆盖完整。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- S12-CTRL-08 的豁免仅适用于 `domain/source.py` 的 frozen+slots DTO。如果未来 slice 的 storage/service 层也需要 `object.__setattr__`，需要重新评估豁免范围。当前 erratum 明确 "不扩大到 storage/service"，风险可控。
- Guard 的 AST 遍历是 tree-level 而非 parent-aware——实现时需要在遍历中维护 parent 信息才能检查 `ast.Attribute` 的 parent 是否是 `ast.Call`。这是实现细节，不构成 plan 缺陷。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。

S12-CTRL-08 的 AST 豁免精确——只放行 `object.__setattr__` call target，所有其它 `object` 形态（裸 name、annotation、constructor、`__new__`、alias、`Any/cast/ignore/getattr/hasattr`）仍拒绝。`source.py` 全部 11 处 `object` 使用都是 `__setattr__` call target，无逃逸。Frozen/slots defensive-copy 契约在 Python 3.11 中可实施。Allowlist 扩展最小且必要。Guard 自测矩阵覆盖 positive + negative。允许进入 implementation。
