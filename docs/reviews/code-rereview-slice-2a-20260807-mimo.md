# Slice 2A 修复后复审 — MiMo 审查路

- **日期**: 2026-08-07
- **基线**: `8350226` (`gateflow: accept write artifact utilities slice 1`)
- **审查范围**: base `8350226` 后全部 tracked/untracked workspace changes（含修复补丁）
- **真源**: `AGENTS.md`、master plan v4.4 ACCEPTED、type erratum adjudication/re-review、Slice 2A implementation artifact、Slice 2A fix artifact、初审 code-review artifact
- **审查者**: MiMo（修复后复审路）
- **前序审查**: `docs/reviews/code-review-20260807-220137.md`（MiMo 初审，2 findings）

---

## 1. 原 Finding 状态

| ID | 原严重性 | 原描述 | 修复措施 | 复审验证 | 状态 |
|---|---|---|---|---|---|
| F-01 | Low | rollback.py `receipt_source_path` guard 使用 `TypeError` 而非 `ValueError` | 两处 `TypeError` → `ValueError`，消息不变 | `rg -A2 "receipt_source_path"` 确认两处均为 `raise ValueError("source_application_receipt path must be a string")` | **CLOSED** |
| F-02 | Medium | promotion.py / configuration_change.py `changed_roles` guard 接受 `(dict, list, str)` 但错误消息声称 "must be a list" | `isinstance(changed_roles, (dict, list, str))` → `isinstance(changed_roles, list)`，保留 `TypeError` 精确消息 | `rg -A3 "changed_roles"` 确认两处均为 `isinstance(changed_roles, list)` + `raise TypeError("... must be a list")` | **CLOSED** |

---

## 2. 修复回归验证

### 2.1 F-02 回归测试

| 测试文件 | 新增测试 | 覆盖 | 验证 |
|---|---|---|---|
| `test_write_model_challenger_promotion.py` | `test_promotion_report_rejects_non_list_changed_roles` | `dict[str, str]` 和 `str` 两类畸形输入 → `TypeError` + 精确消息 | ✓ |
| `test_write_model_configuration_change.py` | `test_configuration_change_report_rejects_non_list_changed_roles` | `dict[str, str]` 和 `str` 两类畸形输入 → `TypeError` + 精确消息 | ✓ |

两个测试均使用参数化联合类型 `dict[str, str] | str`，零新增 `Any`/`object`/`cast`/`type:ignore`。**PASS**。

### 2.2 F-01 回归覆盖

Controller 裁决：rollback `receipt_source_path` guard 位于已由先行 validator 保护的 defense-in-depth 路径，不引入跨 scope monkeypatch 测试。两处 `ValueError` 修复为纯异常类型替换，消息不变，行为不变。**PASS**（按 Controller 裁决接受）。

---

## 3. 修复是否引入新 Finding

### 3.1 `changed_roles` 收紧影响

旧 guard `isinstance(changed_roles, (dict, list, str))` 接受 dict 和 str，新 guard `isinstance(changed_roles, list)` 拒绝它们。潜在影响：
- 调用方传入 `dict`：旧行为静默迭代 dict 键，新行为抛 `TypeError`。dict 不是合法的角色列表，拒绝是正确语义。
- 调用方传入 `str`：旧行为迭代字符串字符，新行为抛 `TypeError`。str 不是合法的角色列表，拒绝是正确语义。

收紧不会破坏合法调用路径，仅拒绝原本就不应被接受的畸形值。**无新 Finding**。

### 3.2 `receipt_source_path` 异常类型替换

`TypeError` → `ValueError` 为纯语义对齐，不影响运行时行为（先行 validator 已确保路径为文本，此 guard 为 defense-in-depth）。**无新 Finding**。

### 3.3 全局扫描

- 零新增 `Any`/`object`/`cast`/`type:ignore`（diff grep 确认）
- 零新增 eligible 私有定义（rg 确认）
- 零 Cohort B 变更（git diff 确认）
- 零额外/未计划 public/helper 签名变更（`require_mapping` 输入类型 `ModelConfigJsonValue` → `ModelConfigJsonValue | JsonObject` 为 v4.4 已批准的静态扩宽，已计入计划）

**无新 Finding**。

---

## 4. 独立验证结果

### 4.1 pytest（258 tests）

```
258 passed in 11.28s
```

较初审 254 tests 新增 4 个回归测试（promotion 参数化 2 case + configuration_change 参数化 2 case）。**PASS**。

### 4.2 pyright dayu/services/

```
0 errors, 0 warnings, 0 informations
```

**PASS**。

### 4.3 Ruff F/I

```
All checks passed!
```

对变更文件运行 `ruff check --select F,I001`，零新增违规。**PASS**。

### 4.4 结构审计

| 检查项 | 结果 |
|---|---|
| Cohort B 9 文件零 diff | ✓ |
| Eligible 私有定义零残留（deferred `_serialize` / `_file_fingerprint_if_present` 除外） | ✓ |
| Deferred 定义全部保留 | ✓ |
| `git diff --check` 通过 | ✓ |

**PASS**。

---

## 5. Open Findings

无。

---

## 6. Residual Risk

1. **Cohort B 未迁移**: 9 个文件仍在 2B 范围内，本 slice 不涉及。
2. **Coverage 数据依赖实现/fix artifact**: 本次未独立复跑 coverage（timid workaround 环境依赖），以 fix artifact 数据为准（各文件 ≥ 80%）。
3. **F-02 `TypeError` 保留**: Controller 裁决保留 `TypeError`（格式化 guard 非核心校验路径）。与 F-01 统一为 `ValueError` 的路径不一致，但按裁决接受。

---

## 7. Verdict

**PASS**（零 Open Findings）

| 严重性 | 计数 |
|---|---|
| High | 0 |
| Medium | 0 |
| Low | 0 |

**原 Finding 状态汇总**:

| ID | 原严重性 | 状态 |
|---|---|---|
| F-01 | Low | CLOSED |
| F-02 | Medium | CLOSED |

**证据摘要**:
- 258 tests passed（11.28s），较初审 +4 回归测试
- pyright 0 errors / 0 warnings / 0 informations
- Ruff F/I All checks passed
- Cohort B 零 diff
- Eligible 私有定义零残留（deferred 除外）
- 零新增 `Any`/`object`/`cast`/`type:ignore`
- F-01 两处 `TypeError` → `ValueError` 已确认
- F-02 两处 `isinstance(changed_roles, (dict, list, str))` → `isinstance(changed_roles, list)` 已确认
- 零新 Finding
