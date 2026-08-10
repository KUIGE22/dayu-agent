# Plan Corrective Re-review — Slice 1.2 Frozen-Slots Guard

## Scope

- Reviewed target：`docs/plans/2026-08-10-investment-platform-restoration.md` S12-CTRL-08（lines 818-841）+ S12-CTRL-05 config defensive copy（lines 833-838）+ `docs/reviews/plan-fix-20260810-slice-1.2-frozen-slots-guard-codex.md`
- Reviewer：MiM Native
- Review clock：`2026-08-10`（本机系统时钟）
- Output file：`docs/reviews/plan-corrective-rereview-20260810-slice-1.2-frozen-slots-guard-mimo-native.md`
- Source chain：Terra FAIL（H0/M2/L0）→ MiM PASS（L0）→ Controller fix → Terra corrective FAIL（M2）→ Controller tightened S12-CTRL-08 → **本 corrective closure**
- Focus：两项 accepted Medium 是否由 tightened S12-CTRL-08 完整闭合

## Terra Medium 1 — AST Exemption Context Constraints → CLOSED ✅

### 先前问题

原 S12-CTRL-08 的 AST 豁免只检查 `object.__setattr__` call target，会放行 `object.__setattr__(other, field, value)` ——接收者不是 `self` 时也通过。

### Tightened S12-CTRL-08 闭合验证

Plan lines 819-831 现在要求 **七层 AST 上下文匹配**：

| 约束 | Plan 文本 | 验证 |
|------|----------|------|
| `ast.Name(id="object")` | line 820 | ✅ |
| 直接 parent 是 `ast.Attribute(value=<same node>, attr="__setattr__")` | line 821 | ✅ |
| Attribute 是 `ast.Call.func` | line 822 | ✅ |
| Call 恰有 **3 positional args / 0 keyword** | line 822 | ✅ |
| 第一项为 `ast.Name(id="self")` | line 822 | ✅ |
| 第二项为字符串常量且匹配当前 class 的 `AnnAssign` 字段名 | line 823 | ✅ |
| Call 必须位于 `def __post_init__(self)` 内 | line 824 | ✅ |
| Class decorator 必须是 `@dataclass(..., frozen=True, slots=True)` 两项 exact boolean | line 824-825 | ✅ |

### Negative Matrix

Plan line 829-831 要求 guard 自测覆盖：

| Negative 场景 | 是否覆盖 |
|---------------|---------|
| other receiver（非 self） | ✅ |
| unknown field（非 AnnAssign 字段） | ✅ |
| `__post_init__` 外 | ✅ |
| 非 dataclass | ✅ |
| 非 frozen/slots | ✅ |
| stored method reference | ✅ |
| keyword / 额外参数 | ✅ |
| 既有 escapes（裸 object / annotation / constructor / __new__ / alias / Any / cast / ignore / getattr / hasattr） | ✅ |

✅ 七层上下文 + 完整负例矩阵——不会误放行。

## Terra Medium 2 — Recursive Deep-Freeze/Copy → CLOSED ✅

### 先前问题

原 S12-CTRL-05 的 config defensive copy 只说 "Mapping 字段防御性复制为只读"，当前实现 `MappingProxyType(dict(self.config))` 是**浅拷贝**——嵌套 Mapping 仍引用 caller-owned 对象。

### Tightened S12-CTRL-05/08 闭合验证

Plan lines 833-838 现在要求 **递归 deep-freeze/copy**：

| 层级 | Plan 文本 | 验证 |
|------|----------|------|
| Scalar | "原值保留" | ✅ |
| Tuple | "逐元素递归生成新 tuple" | ✅ |
| Mapping | "逐 key/value 递归生成新 dict 后包 `MappingProxyType`" | ✅ |
| 任意深度 | "不得保留 caller-owned Mapping 引用" | ✅ |
| Cycle | "cycle → fail closed" | ✅ |
| 非字符串 key | "非字符串 key → fail closed" | ✅ |
| list | "list → fail closed"（`JsonValue` 类型别名不允许 list） | ✅ |
| NaN/Infinity | "NaN/Infinity → fail closed" | ✅ |

### Unit Test Requirements

Plan line 837-838 要求 unit tests 覆盖：

| 测试场景 | 是否要求 |
|---------|---------|
| nested input mutation（修改原始 nested Mapping 不影响 DTO） | ✅ |
| nested write reject（DTO nested Mapping 不可写） | ✅ |
| tuple nested mapping（tuple 内含 Mapping 的 deep-freeze） | ✅ |
| canonical equality / hash-serialization（deep-freeze 后 equality/hash 正确） | ✅ |

### 当前实现 vs Plan 要求

当前 `source.py` 的 `MappingProxyType(dict(self.config))` 是浅拷贝。Plan 要求递归 deep-freeze/copy。这是 plan-level requirement——implementation agent 需要将 `MappingProxyType(dict(...))` 替换为递归 deep-freeze 函数（例如 `_deep_freeze_mapping`）。

⚠️ 注意：这是 plan erratum 的 closing 范围——plan 已正确指定递归语义，implementation agent 在实现时必须满足。当前 WIP 冻结，不修改代码。

## Allowlist / DAG / Scope

| 检查项 | 结果 |
|--------|------|
| S12-CTRL-08 只修改 `test_architecture_boundaries.py` | ✅ |
| 不修改 production DTO / schema / repository / startup | ✅ |
| 不扩大到 storage/service 层 | ✅ |
| 不改变 37-slice DAG | ✅ |
| 不引入 future owner | ✅ |
| 不添加 pragma/skip/ignore | ✅ |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- 当前 `source.py` 的 `MappingProxyType(dict(self.config))` 是浅拷贝，不满足 plan 要求的递归 deep-freeze/copy。Implementation agent 需要在实现时替换为递归函数。这是 plan 与 current WIP 之间的已知 gap，plan 已正确指定语义，不构成 plan 缺陷。
- Guard 的 AST 遍历需要维护 parent 信息才能检查 `ast.Attribute` 的 parent 是否是 `ast.Call`、Call 的 args 数量和类型、以及 `__post_init__` 上下文和 class decorator。这是实现复杂度，不构成 plan 缺陷。

## Conclusion

**PASS**。Open H/M/L = **0/0/0**。

Terra Medium 1（AST exemption context constraints）已闭合：S12-CTRL-08 现要求七层 AST 上下文匹配（frozen+slots decorator / `__post_init__(self)` / exact 3-arg call / self receiver / declared field name / no keyword）+ 完整 negative matrix（8 类场景）。Terra Medium 2（recursive deep-freeze/copy）已闭合：S12-CTRL-05 现要求 scalar/tuple/Mapping 递归 deep-freeze、任意深度无 caller-owned reference、cycle/non-string key/list/NaN/Infinity fail closed、4 类 unit test。S12-CTRL-08 allowlist 范围最小且精确。允许进入 implementation。
