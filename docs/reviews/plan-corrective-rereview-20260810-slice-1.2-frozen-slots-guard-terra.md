# Slice 1.2 S12-CTRL-08 frozen-slots guard corrective re-review — Terra

- **审查范围**：更新后的 master plan S12-CTRL-05/08、Controller guard plan-fix、原 Terra/MiM guard reviews、当前 architecture guard 与冻结 WIP `source.py`。
- **方式**：只读 closure review。未修改 WIP、plan、tests 或 README；未运行 PG16/live/broker。
- **结论**：**PASS**，open **H0 / M0 / L0**。

## Assumptions tested

1. `object.__setattr__` 例外不会成为任意对象写入或宽类型逃逸。
2. recursive JSON config 在构造后不保留 caller-owned nested mutable state。
3. 负例、allowlist、pure/storage 边界和 frozen/slots DTO 契约保持可直接实施。

## Closure verification

| 前次 finding | 结论 | 直接证据 |
| --- | --- | --- |
| TERRA-S12-08-001：call-target 会放行 other receiver | 已闭合 | S12-CTRL-08 现锁定完整 AST：direct `object.__setattr__`、该 Attribute 是 Call.func、恰三位置参数/零 keyword、首参精确 `self`、第二参为当前 class `AnnAssign` 声明的字符串字段、位于 `def __post_init__(self)`，且 class 是 `@dataclass(..., frozen=True, slots=True)` exact boolean。negative matrix 覆盖 other receiver、未知字段、method 外、非 dataclass、非 frozen/slots、stored reference、keyword/额外参数和既有 escape。 |
| 合法 DTO writeback 的可实施性 | 已闭合 | 对当前 `source.py` 11 处 writeback 做只读 AST 适配检查：全部处于 frozen+slots `__post_init__`，均为 `object.__setattr__(self, <declared literal field>, value)`，恰三位置参数、无 keyword；收紧 guard 不会阻挡 UTC normalization 或 config writeback。 |
| TERRA-S12-08-002：recursive config shallow proxy | 已闭合 | S12-CTRL-05/08 明定 scalar 保留、tuple 逐元素复制为新 tuple、Mapping 递归复制为新 dict 再 `MappingProxyType`；任意深度不保留 caller Mapping，nested Mapping/tuple-of-Mapping runtime immutable。 |
| deep-freeze failure gates | 已闭合 | plan 要求 nested input mutation、nested write reject、tuple nested mapping、cycle、非字符串 key、list、NaN/Infinity 与 canonical equality/hash-serialization input 的 unit gates；source/test 都已在 Slice 1.2 allowlist。 |
| 其它 strict guards / scope | 已闭合 | 裸 `object`、annotation、`object()`、`object.__new__`、alias/property chain 及 `Any/cast/type: ignore/getattr/hasattr` 保持拒绝；禁止 pragma/skip/ignore，不扩至 storage/service/schema/repository/startup，也不引入 future owner。 |

## Findings

无。前次两项 Medium 都由更新后的 plan 文本与 required self-tests 形成可唯一实现的闭环：AST exemptions 只容纳当前 frozen DTO 的受控 self-field writeback；recursive JSON input 则须深复制并冻结，不能再以顶层 proxy 掩盖 nested mutation。

## Open questions

无。

## Residual risk

实现 review 必须实际检查 parent/class stack 的 AST 关联，而不能退化为 Name-only 扫描；还必须执行 deep-freeze 的 nested mutation/write/cycle gates。任意通过 `cast`、`getattr`、alias 或 guard pragma 回退的做法都应拒绝。

## Final conclusion

**PASS，open H0 / M0 / L0。** S12-CTRL-08 的 frozen-slots guard 与 S12-CTRL-05 recursive defensive-copy 契约已完整闭合；allowlist、DAG 和 WIP freeze 边界无新增缺口。
