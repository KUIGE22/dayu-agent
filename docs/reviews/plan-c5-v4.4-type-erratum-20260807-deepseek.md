# Plan C5 v4.4 TYPE ERRATUM（C5-CTRL-10-ERRATUM）

- **日期**: 2026-08-07
- **分支**: `codex/dual-model-research-mvp`
- **触发**: Slice 2A type adjudication — DeepSeek: `docs/reviews/slice-2a-require-mapping-type-adjudication-20260807-212526-deepseek.md`；MiMo: `docs/reviews/slice-2a-require-mapping-type-adjudication-20260807-212527-mimo.md`；DeepSeek plan fix: `docs/reviews/plan-c5-v4.4-type-erratum-20260807-deepseek.md`（本件）
- **Controller Ruling**: 采纳方案 A；MiMo "无需 v4.4" **REJECTED WITH REASON** — master plan 行 1/213/308/570 等明确把签名当 exact contract，签名变更必须更新计划为新版本
- **Controller 审计修正（7 项）**: 1) "Slash 1"→"Slice 1"；2) "签名变更仅 1 字符"→"单一输入类型扩宽"；3) 审查来源同时列 DeepSeek 与 MiMo 两份 artifact；4) 删除运行时 `public_validator_pyright_evidence` 测试，改为静态 pyright 验证；非-dict identity 测试使用 `MappingProxyType`，零 Any；5) 行 670/671 v4.3→v4.4 C5-CTRL-10-ERRATUM；6) 行 1429 合规版本 v4.3→v4.4；7) 尾注 v4.3→v4.4 CANDIDATE
- **MiMo Re-Review**: `docs/reviews/plan-c5-v4.4-type-erratum-rereview-20260807-mimo.md` — 9/9 PASS, 零 findings, Controller accepted
- **目标版本**: v4.4 ACCEPTED / MIMO RE-REVIEW PASS

---

## 1. 问题

plan v4.3 在以下位置将 `require_mapping` 签名列为 exact contract：

| 行 | 上下文 | 旧签名 |
|---|---|---|
| 1 | 标题 | v4.3 ACCEPTED |
| 213 | §1.6.3 mapping 族 | `require_mapping(value: ModelConfigJsonValue, *, name: str) -> JsonObject` |
| 308 | §1.6.7 17 helper 表 #8 | 同上 |
| 570 | §5 Slice 1 签名清单 #8 | 同上 |

Slice 2A 需将 `write_model_configuration_rollback.py` 5 个 public validator 的 `_mapping(payload)`（`payload: Mapping[str, Any]`）迁为 `require_mapping(payload)`。pyright 在以下 5 个调用点报 `Mapping[str, Any]` 不可传 `ModelConfigJsonValue`：

| 行 | public 函数 |
|---|---|
| `:840` | `validate_write_model_configuration_operator_rollback_plan(payload: Mapping[str, Any])` → `require_mapping(payload, name=...)` |
| `:1225` | `validate_write_model_configuration_operator_rollback_plan_verification(payload: Mapping[str, Any])` → 同上 |
| `:1316` | `validate_write_model_configuration_operator_rollback_approval_request(payload: Mapping[str, Any])` → 同上 |
| `:1498` | `validate_write_model_configuration_operator_rollback_approval(payload: Mapping[str, Any])` → 同上 |
| `:1831` | `validate_write_model_configuration_operator_rollback_approval_verification(payload: Mapping[str, Any])` → 同上 |

## 2. 解决方案（唯一推荐 A，已采纳）

`require_mapping` 输入类型从 `ModelConfigJsonValue` 最小扩宽为 `ModelConfigJsonValue | JsonObject`。

```python
def require_mapping(
    value: ModelConfigJsonValue | JsonObject,
    *,
    name: str,
) -> JsonObject:
```

- **实现不变**：`isinstance(value, Mapping)` + identity-return
- **返回类型不变**：`JsonObject`
- **运行时行为不变**：继续接受任意 Mapping（含非 dict 自定义 Mapping）并 identity-return
- **17 helper count 不变**
- **2B copy adapter 不变**：`dict(require_mapping(value, name=...))` 行为不变

### 可赋值性

- `Mapping[str, Any]` → `JsonObject`（`Mapping` 对值协变，`Any` 兼容 `ModelConfigJsonValue`）→ pyright 通过
- `ModelConfigJsonValue` → `ModelConfigJsonValue | JsonObject` → 全部现有 caller 兼容
- 返回值 `JsonObject` → caller 期望 `Mapping[str, Any]`（协变）→ 通过

### 类型验证方式

不新增运行时测试。直接 `pyright dayu/services/` — 以 `write_model_configuration_rollback.py` 5 个 public validator 的现有 `Mapping[str, Any]` 签名及 `require_mapping` 调用作为静态证据，验证零 errors。

## 3. 拒绝的方案

| 方案 | 拒绝原因 |
|---|---|
| **B** (overload) | 功能等价，认知负担更高。两个 overload 返回类型相同，无差异化收益 |
| **C** (改 5 个 public 签名) | 直接违反行为约束——不可改 public validator 契约 |
| **D** (inline guard) | 5 处重复 isinstance guard，破坏 shared helper 单一校验入口 |
| **E** (其他) | Protocol/TypeVar 引入不必要复杂度 |

## 4. 计划修改摘要

| 位置 | 修改 |
|---|---|
| 标题 | `v4.3 ACCEPTED` → `v4.4 ACCEPTED / MIMO RE-REVIEW PASS` |
| 审查来源 | 新增 DeepSeek adjudication + MiMo adjudication + DeepSeek plan fix + MiMo re-review 四份 artifact |
| v4.3→v4.4 变更 | 新增条目：C5-CTRL-10-ERRATUM 完整说明；"Slice 1"（非 "Slash 1"）；零运行时 pyright evidence 测试；静态 pyright 验证 |
| 状态行 | "单一输入类型扩宽"（非 "签名变更仅 1 字符"）；Controller REJECTED WITH REASON |
| §1.6.3 行 214 | 签名 `ModelConfigJsonValue` → `ModelConfigJsonValue \| JsonObject` |
| §1.6.7 表 #8 行 309 | 签名更新 + 版本标签 v4.3→v4.4 |
| §5 Slice 1 行 571 | 签名更新 |
| §5 Slice 1 测试 | 新增 `test_require_mapping_non_dict_mapping_identity`（`MappingProxyType`，零 `Any`）；删除运行时 `public_validator_pyright_evidence`；改为静态 pyright 5 调用点验证 |
| §5 Slice 2A 迁移规则 | 新增 v4.4 说明：5 public validator `Mapping[str, Any]` 经协变分支通过 |
| §5 Slice 2B | 行 670/671 版本标签 `v4.3 C5-CTRL-10` → `v4.4 C5-CTRL-10-ERRATUM`；行 684 签名完整写明 |
| §8 硬约束合规 行 1429 | `（v4.3）` → `（v4.4）` |
| 尾注 行 1561 | `v4.3 ACCEPTED` → `v4.4 ACCEPTED / MIMO RE-REVIEW PASS`，保留 v4.3 历史说明，引用 MiMo re-review 9/9 PASS |

**未修改**：迁移表（A/B cohort 文件集合、17 helper 清单、defer 项）；Slice 编号和顺序；类型不变量 §4.3；依赖方向 §2.2；非目标 §3

## 5. 为什么必须更新 plan（而非仅 errata 附注）

Controller 裁决原文：

> master plan 在行 1/213/308/570 等明确把签名当 exact contract，故 MiMo "无需 v4.4" 被 REJECTED WITH REASON。

具体理由：
1. 行 1 标题含版本号，下游流程引用版本号做 gate
2. 行 213/308/570 三处将签名列为 literal exact contract，任何差异都会在 MiMo 逐行 review 时触发 FAIL
3. C5-CTRL-10 条目下已有 "identity-return" 精确行为描述，签名也属于该条目的 exact spec
4. 不改计划会导致 MiMo re-review 时发现 plan 签名与 Slice 1 实际签名不一致，产生新 finding

## 6. MiMo 需确认项（re-review checklist）—— 全部通过

- [x] 标题版本 `v4.4 ACCEPTED / MIMO RE-REVIEW PASS`（MiMo re-review PASS）
- [x] §1.6.3/§1.6.7/§5 三处签名均为 `ModelConfigJsonValue | JsonObject`，一致
- [x] C5-CTRL-10-ERRATUM 说明完整：5 个 rollback public `Mapping[str, Any]` validator 触发、实现/返回/identity/17 count/2B copy 不变
- [x] Slice 1 commit 不重写——签名中 `| JsonObject` 随 2A commit 修改
- [x] Slice 1 新增 `test_require_mapping_non_dict_mapping_identity`（`MappingProxyType`，零 `Any`）
- [x] 类型验证：`pyright dayu/services/` — 5 个 public validator（`:840` `:1225` `:1316` `:1498` `:1831`）零 errors
- [x] 方案 B/C/D/E 拒绝理由充分
- [x] 行 670/671 版本标签 `v4.4 C5-CTRL-10-ERRATUM`，行 1429 合规版本 `（v4.4）`，尾注 v4.4 ACCEPTED
- [x] 无其他 plan 内容被顺手修改
- [x] 审查来源同时列 DeepSeek (`slice-2a-require-mapping-type-adjudication-20260807-212526-deepseek.md`) 、MiMo (`slice-2a-require-mapping-type-adjudication-20260807-212527-mimo.md`) 与 DeepSeek plan fix (`plan-c5-v4.4-type-erratum-...`) 三份 artifact

> **MiMo re-review**: `docs/reviews/plan-c5-v4.4-type-erratum-rereview-20260807-mimo.md` — 9/9 PASS, 零 findings。

## 7. Verdict

**方案 A ACCEPTED。plan v4.4 ACCEPTED / MIMO RE-REVIEW PASS。**

MiMo re-review: `docs/reviews/plan-c5-v4.4-type-erratum-rereview-20260807-mimo.md` — 9/9 PASS, 零 findings, Controller accepted。

Controller 7 项审计修正已全部执行：1) "Slash 1"→"Slice 1" ✓；2) "签名变更仅 1 字符"→"单一输入类型扩宽" ✓；3) 审查来源列 DeepSeek adjudication + MiMo adjudication + DeepSeek plan fix ✓；4) 删除运行时 Any 测试，改静态 pyright，非-dict 用 MappingProxyType ✓；5) 行 670/671 v4.4 C5-CTRL-10-ERRATUM ✓；6) 行 1429 v4.4 ✓；7) 尾注 v4.4 ACCEPTED ✓。
