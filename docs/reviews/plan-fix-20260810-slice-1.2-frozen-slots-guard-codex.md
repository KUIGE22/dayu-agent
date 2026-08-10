# Slice 1.2 frozen-slots guard plan fix

- **Work unit**：Investment Platform Restoration / Slice 1.2
- **Controller**：Codex
- **状态**：**CLOSED / DUAL PLAN RE-REVIEW PASS**
- **Implementation state**：frozen at test gate；不继续编辑

## Stop evidence

Slice 1.2 当前真实 PG16 integration `5/5` 通过，相关测试除 architecture guard 外
`253/253` 通过。唯一失败来自 `_collect_escape_violations_from_source()` 对所有
`ast.Name(id="object")` 无条件报错，而 accepted S12-CTRL-05 同时要求 DTO
frozen/slots 与 config 防御性复制为只读映射；标准 dataclass 在 `__post_init__` 完成该
写回只能使用 `object.__setattr__`。

## Controller decision

接受为 plan/allowlist gap。S12-CTRL-08 只对 exact
`object.__setattr__(self, field, validated_value)` call-target AST 豁免 Name 命中，并把
现有 `tests/investment/test_architecture_boundaries.py` 加入 Slice 1.2 allowlist。guard
必须新增自测，证明裸 `object`、annotation、constructor、`object.__new__`、alias 与
Any/cast/ignore/getattr/hasattr 仍 fail closed。

不允许改 production DTO 契约、添加 pragma/skip/ignore，或放宽 pure/storage import
边界。Terra 与 MiM Native 任一路非 PASS/open0 时 implementation 继续冻结。

## Plan-review adjudication

- Terra：FAIL，open H/M/L=`0/2/0`。两项均 **ACCEPTED / FIXED IN PLAN**：
  1. 原 call-target predicate 也会放行 `object.__setattr__(other, ...)`；
  2. 当前 config 仅顶层 proxy，嵌套 Mapping 保留 caller mutable reference。
- MiM Native：PASS/open0，但其“豁免精确”“defensive-copy 已闭合”结论被 Terra 的直接
  反例推翻；不以该 PASS 跳过修复。

S12-CTRL-08 现要求 class/method/decorator/self/field/arity 全上下文 AST 匹配与完整负例
矩阵；S12-CTRL-05 现要求 Mapping/tuple 递归 deep-freeze/copy、nested mutation 与 write
negative。implementation 在 corrective dual review 前继续冻结。

## Final closure

- Terra：`plan-corrective-rereview-20260810-slice-1.2-frozen-slots-guard-terra.md`，
  PASS，open H/M/L=`0/0/0`。
- MiM Native：
  `plan-corrective-rereview-20260810-slice-1.2-frozen-slots-guard-mimo-native.md`，
  PASS，open H/M/L=`0/0/0`。

两项 accepted Medium 全部 CLOSED，Slice 1.2 implementation 解冻。
