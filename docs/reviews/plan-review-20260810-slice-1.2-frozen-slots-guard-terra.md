# Slice 1.2 S12-CTRL-08 frozen-slots guard erratum — Terra plan review

- **审查目标**：master plan 的 S12-CTRL-08 与 `plan-fix-20260810-slice-1.2-frozen-slots-guard-codex.md`。
- **只读证据**：当前 `tests/investment/test_architecture_boundaries.py`、冻结 WIP `dayu/investment/domain/source.py`、worktree diff；未修改 code/tests/plan/README，未启动 PG16/live/broker。
- **结论**：**FAIL**，open **H0 / M2 / L0**。实现 WIP 应保持冻结。

## Assumptions tested

1. AST 豁免仅能放行 frozen+slots `__post_init__` 对自身的已校验写回，而非任何 `object.__setattr__`。
2. `Any/object/cast/type: ignore/getattr/hasattr`、裸 object、annotation、constructor、`__new__`、别名与属性链仍 fail closed。
3. 当前 WIP 的 frozen/slots 与 recursive JSON Mapping defensive-copy 契约可由该最小 guard 勘误保持，不需要扩大 schema/repository/startup scope。

## Confirmed closure direction

- 勘误动机成立：当前 source 有 11 个直接 `object.__setattr__(self, ...)`，均用于 UTC 归一化或将 config 写为 `MappingProxyType`；标准 frozen dataclass 无法以普通赋值完成这些操作。
- Slice 1.2 allowlist 已精确加入 `tests/investment/test_architecture_boundaries.py`，并未扩张到 schema、repository、startup 或 future owner。
- S12-CTRL-08 正确要求保留 alias、qualified `Any/cast`、`type: ignore`、`getattr/hasattr` 的既有 collector 规则，并要求 negative matrix；这比 pragma/skip 或全局删除 `object` 检查安全。

## Findings

### TERRA-S12-08-001-未修复-中-仅限制 call target 仍允许任意对象的底层改写

- **位置**：S12-CTRL-08 第 814–822 行；Controller fix 第 18–22 行；当前 `_collect_escape_violations_from_source()` 第 245–286 行。
- **问题类型**：契约缺失 / frozen invariant bypass / 测试缺口。
- **当前写法**：计划只要求忽略如下 AST 中的 `ast.Name(id="object")`：其直接 parent 为 `Attribute(value=<same node>, attr="__setattr__")`，且该 Attribute 为 `Call.func`；文字说明用途仅限 frozen+slots dataclass 的 `__post_init__` 向自身写回。
- **反例/失败场景**：`object.__setattr__(other, "x", value)` 与合法的 `object.__setattr__(self, "x", value)` 完全满足该 parent/call-target predicate。只读 AST 复现已确认两者均为 `matches-S12-target`。前者可改写任意 frozen/slots 对象或跨对象状态，仍被现有 guard 放行；在普通函数、非 dataclass 方法或写入未验证字段中使用也同样通过。
- **为什么有问题**：计划的形式化 AST 条件与“仅限 `__post_init__`、self、已校验字段”的语义不等价。实现 agent 只能选择自行扩展规则或照文字最小实现；后者会把 `object` 的最危险 mutation primitive 留成生产 escape。
- **直接证据**：当前 source 的 11 个实际调用全为 `object.__setattr__(self, <literal field>, <validation/copy result>)`，故更严格约束不会阻塞正当路径；但 S12-CTRL-08 与 fix 的 negative matrix 均未要求 `other` receiver、非 `__post_init__`、错误 arity/keyword 或未冻结 class 的反例。
- **影响**：architecture guard 可显示 green，同时出现绕过 frozen DTO 不变式的 production 写入；code review 失去一条防线。
- **建议改法和验证点**：把 accepted predicate 提升到完整 `ast.Call` shape：direct `object.__setattr__`、恰好三个 positional arguments、无 keywords、第一参数为 `ast.Name("self")`，且调用所在 direct enclosing function 为 `__post_init__`、direct enclosing class 带 `@dataclass(frozen=True, slots=True)`。第二参数至少要求常量字符串，允许当前 11 个字段写回。guard 自测增加 `object.__setattr__(other, ...)`、模块/普通方法中 self 写入、attribute reference、错误 arity/keyword 与非-frozen class negative；当前 11 个 source call 为 exact positive。
- **修复风险（低/中/高）**：低。
- **严重程度（低/中/高/严重）**：中。

### TERRA-S12-08-002-未修复-中-递归 JSON 的 frozen defensive-copy 仍为浅复制

- **位置**：S12-CTRL-05 frozen/slots Mapping defensive-copy 契约、S12-CTRL-08 第 817–824 行；当前 `source.py` 第 706、740、797 行及 `_validate_json_value()` 第 820–861 行。
- **问题类型**：不可变契约 / 测试缺口。
- **当前写法**：S12-CTRL-08 以“不得改变 DTO frozen/slots/defensive-copy 语义”为前提，允许 `object.__setattr__` 写入 `MappingProxyType(dict(self.config))`；JSON contract 同时允许 recursive `Mapping[str, JsonValue]`。
- **反例/失败场景**：以 `raw = {"nested": {"value": 1}}` 构造 `SourceSubscriptionUpdateRequest` 后执行 `raw["nested"]["value"] = 2`，DTO 的 `config["nested"]["value"]` 随即读为 `2`。已在 Python 3.11 venv 只读复现。顶层 `MappingProxyType(dict(...))` 只复制第一层，递归允许的内层 Mapping 与 caller 共享。
- **为什么有问题**：frozen slots DTO 的 recursive config 在构造后仍可从外部改变，既不是完整 defensive copy 也不是真正只读值。S12-CTRL-08 若只让 guard green 而冻结这一语义，会把实际 value-object state mutation 固化；其用途说明又将 config 防御性复制列为 `object.__setattr__` 的正当理由，二者直接相冲突。
- **直接证据**：`_validate_json_value()` 递归接受 `Mapping`，而三个 DTO 仅调用 `MappingProxyType(dict(self.config))`；没有 deep-freeze helper 或 nested-alias negative test。
- **影响**：调用者可在 request/projection 已交给 Service/repository 后静默改变 config，破坏 frozen DTO、CAS/retry 的输入稳定性与审计可复现性。
- **建议改法和验证点**：在本 erratum 中明确“defensive-copy”为递归冻结：Mapping 递归复制为 `MappingProxyType`，sequence 递归转换为 tuple，scalar 保持原值，并只在校验成功后用允许的 self writeback 写入；或若产品只需要 shallow snapshot，则删去 recursive Mapping immutability 的 claim并明确其风险（不推荐）。加入 nested mapping/tuple-mapping alias mutation negative，断言构造后 DTO 可观察值不变且外层、内层均不可写；对应 source/test 路径已在 Slice 1.2 allowlist，不涉及 schema 或 future owner。
- **修复风险（低/中/高）**：中。
- **严重程度（低/中/高/严重）**：中。

## Open questions

无。两项均由当前 plan 文本、AST 形态和 Python 3.11 运行时的直接复现得出。

## Residual risk

修复后仍应保留 S12-CTRL-08 的所有原始 escape negative；不得通过 pragma、skip、alias、storage/service 扩张或忽略 marker 来绕过。recursive JSON freeze 属于当前 Slice 1.2 DTO owner，不能后移到 repository 或 future source/job slice。

## Final conclusion

**FAIL，open H0 / M2 / L0。** 最小 allowlist 与“仅接受 `object.__setattr__` call target”的方向正确，但其 AST 形态没有约束接收者/上下文，且当前 recursive config 的 shallow proxy 不满足 frozen defensive-copy 语义。两项修订并补齐自测后，再进行 closure re-review。
