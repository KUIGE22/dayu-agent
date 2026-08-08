# Plan C5 v4.4 TYPE ERRATUM MiMo Re-Review

- **日期**: 2026-08-07
- **分支**: `codex/dual-model-research-mvp`
- **HEAD**: `81df373`
- **审查目标**: master plan v4.4 CANDIDATE diff + 三份 adjudication artifact
- **审查者**: MiMo
- **范围**: 只读——不修改代码/测试/plan

---

## 1. 审查输入

| # | 文件 | 角色 |
|---|---|---|
| 1 | `docs/plans/2026-08-07-cli-write-architecture-refactor.md` (git diff v4.3→v4.4) | master plan |
| 2 | `docs/reviews/slice-2a-require-mapping-type-adjudication-20260807-212526-deepseek.md` | DeepSeek type adjudication |
| 3 | `docs/reviews/slice-2a-require-mapping-type-adjudication-20260807-212527-mimo.md` | MiMo type adjudication |
| 4 | `docs/reviews/plan-c5-v4.4-type-erratum-20260807-deepseek.md` | DeepSeek plan fix |

---

## 2. Re-Review Checklist 逐项验证

### 2.1 标题版本

| 位置 | 预期 | 实际 | 结果 |
|---|---|---|---|
| 行 0（标题） | `v4.4 CANDIDATE / TYPE ERRATUM AWAITING MIMO RE-REVIEW` | ✅ 一致 | PASS |
| 行 1560（尾注） | `v4.4 CANDIDATE / TYPE ERRATUM AWAITING MIMO RE-REVIEW` | ✅ 一致 | PASS |

### 2.2 三处签名一致性

| 位置 | 预期签名 | 实际 | 结果 |
|---|---|---|---|
| §1.6.3 行 214 | `require_mapping(value: ModelConfigJsonValue \| JsonObject, *, name: str) -> JsonObject` | ✅ 一致 | PASS |
| §1.6.7 表 #8 行 309 | `(value: ModelConfigJsonValue \| JsonObject, *, name: str) -> JsonObject` | ✅ 一致 | PASS |
| §5 Slice 1 行 571 | `require_mapping(value: ModelConfigJsonValue \| JsonObject, *, name: str) -> JsonObject` | ✅ 一致 | PASS |

三处签名完全一致，均为 `ModelConfigJsonValue | JsonObject`。

### 2.3 C5-CTRL-10-ERRATUM 说明完整性

行 10（v4.3→v4.4 变更条目）验证：

| 要素 | 是否覆盖 |
|---|---|
| 触发：5 个 public validator `Mapping[str, Any]` payload | ✅ |
| 机制：经 `JsonObject`（`Mapping[str, ModelConfigJsonValue]`）协变分支通过 | ✅ |
| 实现不变 | ✅ |
| 返回类型不变 | ✅ |
| identity-return 不变 | ✅ |
| 17 helper count 不变 | ✅ |
| 2B copy adapter 不变 | ✅ |
| Slice 1 commit 不重写 | ✅ |
| Slice 1 新增 MappingProxyType 测试 | ✅ |
| 类型验证方式：静态 pyright，非运行时测试 | ✅ |
| 5 个方案及拒绝理由 | ✅ |

### 2.4 5 个 rollback `Mapping[str, Any]` Pyright 静态证据

| 行号 | public 函数 | diff 中引用 |
|---|---|---|
| `:840` | `validate_...rollback_plan` | ✅ 行 10、行 598、行 642 |
| `:1225` | `validate_...rollback_plan_verification` | ✅ 同上 |
| `:1316` | `validate_...rollback_approval_request` | ✅ 同上 |
| `:1498` | `validate_...rollback_approval` | ✅ 同上 |
| `:1831` | `validate_...rollback_approval_verification` | ✅ 同上 |

5 个调用点在 diff 中精确引用，与两份 adjudication artifact 中的行号完全一致。

### 2.5 Identity 行为

- identity-return（`return value`）在 §1.6.7 表 #8 行 309 中保留 ✅
- 12 个 identity-return 文件直接迁移 ✅
- 行 683（Cohort B 迁移规则）完整描述 identity vs copy 区分 ✅

### 2.6 MappingProxyType 测试零逃逸

行 597 新增测试项：

```
test_require_mapping_non_dict_mapping_identity — 使用 MappingProxyType 构造精确
Mapping[str, ModelConfigJsonValue] 非 dict 映射（零 Any/object/cast/type: ignore）
验证：require_mapping(value) is value（identity-return 对任意 Mapping 成立）
```

- 零 `Any` ✅
- 零 `object` ✅
- 零 `cast` ✅
- 零 `type: ignore` ✅
- 使用 `MappingProxyType`（标准库，非自定义 Mapping 子类）✅

### 2.7 2B Adapter

| 文件 | adapter 描述 | diff 行 | 结果 |
|---|---|---|---|
| `incident_dossier_revalidation` | `dict(require_mapping(value, name=...))` | 行 669 | ✅ v4.4 C5-CTRL-10-ERRATUM |
| `gate_revalidation` | `dict(require_mapping(value, name=...))` | 行 670 | ✅ v4.4 C5-CTRL-10-ERRATUM |

两文件版本标签均已从 `v4.3 C5-CTRL-10` 更新为 `v4.4 C5-CTRL-10-ERRATUM`。

### 2.8 版本/路径/尾注

| 位置 | 变更 | 结果 |
|---|---|---|
| 行 0 标题 | `v4.3 ACCEPTED` → `v4.4 CANDIDATE / TYPE ERRATUM AWAITING MIMO RE-REVIEW` | ✅ |
| 行 5 审查来源 | 新增 3 份 artifact 引用 | ✅ |
| 行 10 v4.3→v4.4 变更 | 新增完整条目 | ✅ |
| 行 11 状态行 | 更新为 v4.4 CANDIDATE | ✅ |
| 行 1428 §8 合规 | `（v4.3）` → `（v4.4）` | ✅ |
| 行 1560 尾注 | 更新为 v4.4 CANDIDATE | ✅ |

### 2.9 无越界修改

diff 仅涉及以下变更区域：

1. 标题行（版本号）
2. 审查来源（新增 artifact 引用）
3. v4.3→v4.4 变更条目（新增）
4. 状态行（更新）
5. §1.6.3 签名（1 处）
6. §1.6.7 表 #8 签名 + 版本标签（1 处）
7. §5 Slice 1 签名（1 处）
8. §5 Slice 1 测试项（新增 MappingProxyType + v4.4 类型验证说明）
9. §5 Slice 2A 迁移规则（新增 v4.4 说明）
10. §5 Slice 2B 两文件行（版本标签 v4.3→v4.4）
11. §5 Slice 2B 迁移规则（签名完整写明 + v4.4 标签）
12. §8 硬约束合规（版本 v4.3→v4.4）
13. 尾注（版本更新）

**未被修改的内容**（与 plan fix §4.7 "未修改" 声明一致）：
- 迁移表 A/B cohort 文件集合 ✅
- 17 helper 清单（除 #8 签名更新外）✅
- defer 项 ✅
- Slice 编号和顺序 ✅
- 类型不变量 §4.3 ✅
- 依赖方向 §2.2 ✅
- 非目标 §3 ✅

零越界修改。

---

## 3. 与三份 Adjudication Artifact 的一致性

### 3.1 DeepSeek adjudication（`slice-2a-...-212526-deepseek.md`）

- 方案 A 推荐 ✅
- 可赋值性分析与 plan diff 一致 ✅
- 风险评估 LOW ✅

### 3.2 MiMo adjudication（`slice-2a-...-212527-mimo.md`）

- "无需 v4.4" 观点（行 149）→ Controller REJECTED WITH REASON ✅
- 方案 A 推荐与 DeepSeek 一致 ✅
- plan fix 明确引用此 REJECTED 观点 ✅

### 3.3 DeepSeek plan fix（`plan-c5-v4.4-type-erratum-...-deepseek.md`）

- 7 项 Controller 审计修正全部执行 ✅
- MiMo re-re-review checklist 与本审查逐项对应 ✅

---

## 4. Verdict

**全部 9 项 re-review checklist 通过。零 findings。**

| # | 检查项 | 结果 |
|---|---|---|
| 1 | 标题版本 `v4.4 CANDIDATE` | ✅ PASS |
| 2 | §1.6.3/§1.6.7/§5 三处签名一致 | ✅ PASS |
| 3 | C5-CTRL-10-ERRATUM 说明完整 | ✅ PASS |
| 4 | 5 个 rollback `Mapping[str, Any]` pyright 静态证据 | ✅ PASS |
| 5 | identity-return 行为不变 | ✅ PASS |
| 6 | MappingProxyType 测试零逃逸 | ✅ PASS |
| 7 | 2B adapter 版本标签 v4.4 | ✅ PASS |
| 8 | 版本/路径/尾注一致 | ✅ PASS |
| 9 | 无越界修改 | ✅ PASS |

---

## 5. Final Verdict

**v4.4 ACCEPTED / MIMO RE-REVIEW PASS**

Plan v4.4 TYPE ERRATUM 通过 MiMo re-review。签名 `require_mapping(value: ModelConfigJsonValue | JsonObject, *, name: str) -> JsonObject` 为唯一变更，精确解决 5 个 rollback public validator 的 `Mapping[str, Any]` 类型冲突，零实现/行为/契约变更。17 helper / 19 file 验证不变。Controller 7 项审计修正全部落地。Ready for implementation。
