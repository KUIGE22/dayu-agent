# CLI Write Master Plan v5.8 Adversarial Plan Review — MiMo

- **日期**: 2026-08-08
- **审查者**: MiMo 独立 plan reviewer
- **分支**: `codex/dual-model-research-mvp`
- **基线**: `4d2535d`（v5.7 ACCEPTED）
- **候选计划**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v5.8 CANDIDATE
- **输入 artifacts**:
  - `docs/plans/2026-08-07-cli-write-architecture-refactor.md`（v5.8 CANDIDATE, AGG-RT-CTRL-01）
  - `docs/reviews/plan-v5.8-aggregate-rt-exit-erratum-20260808-codex.md`（erratum）
  - `docs/reviews/aggregate-code-review-adjudication-20260808-codex.md`（adjudication）
  - `docs/reviews/aggregate-cli-write-architecture-validation-20260808-codex.md`（validation）
  - `docs/reviews/code-review-20260808-aggregate-deepseek.md`（DeepSeek aggregate）
  - `docs/reviews/code-review-20260808-aggregate-mimo.md`（MiMo aggregate）
  - accepted v5.7 plan 与源码/测试
- **审查范围**: AGG-RT-CTRL-01 code-generation readiness
- **状态**: PASS / AWAITING DUAL PLAN RE-REVIEW

---

## 1. Verdict

**PASS — open High/Medium/Low = 0/0/0。**

AGG-RT-CTRL-01 达到 code-generation-ready 标准。修复范围精确、行为边界清晰、测试构造可行、验证门禁完整。以下 adversarial 挑战全部通过，无需 plan fix。

---

## 2. Adversarial 挑战清单与裁决

### 2.1 result shape 正确性

**挑战**: `validate_monitoring_source_map_payload` 的返回结构是否与其他 `_run_validate_*` 使用的 inspect 函数一致？`result.get("ok")` 路径是否正确？

**源码证据**:
- `validate_monitoring_source_map_payload`（`_research_template_core.py:359-428`）返回 `{"ok": not errors, "template": ..., "errors": errors, "warnings": ...}` — `ok` 在顶层。
- `inspect_research_template_bundle`（`_research_template_bundle.py:386`）、`inspect_monitoring_execution_plan`（`_research_template_monitoring.py:313`）、`inspect_research_workbook_report`（`research_workbook.py:499`）、`inspect_monitoring_scheduler_manifest`（`_research_template_monitoring.py:794`）返回 `{"validation": {..., "ok": ...}, ...}` — `ok` 嵌套在 `validation` 下。

**对比 6 个 `_run_validate_*` 的 return 模式**:
| Runner | Validator 返回结构 | Return 表达式 |
|---|---|---|
| `_run_validate_research_workbook` | 顶层 `ok` | `result.get("ok") is True` |
| `_run_validate_source_map` | 顶层 `ok` | **`return 0`**（缺陷）→ plan: `result.get("ok") is True` |
| `_run_validate_bundle` | 嵌套 `validation.ok` | `isinstance(validation, dict) and validation.get("ok") is True` |
| `_run_validate_monitoring_plan` | 嵌套 `validation.ok` | 同上 |
| `_run_validate_workbook_report` | 嵌套 `validation.ok` | 同上 |
| `_run_validate_scheduler_manifest` | 嵌套 `validation.ok` | 同上 |

**裁决**: **PASS**。plan 提议的 `result.get("ok") is True` 精确匹配 `validate_monitoring_source_map_payload` 的顶层 `ok` 字段路径。不套用嵌套 `validation` 路径，也不遗漏。唯一 `_run_validate_source_map` 使用顶层路径是因为其 validator 直接返回结果而非 inspect 包装。

### 2.2 `is True` identity check 边界

**挑战**: `result.get("ok") is True` 是否会在 `ok` 为 truthy 非布尔值时产生错误否定？

**源码证据**: `_research_template_core.py:422` — `"ok": not errors`，`errors` 是 `list[str]`，`not errors` 始终产出 `bool`。不存在 `ok` 为 truthy 非布尔值的路径。

**裁决**: **PASS**。`is True` 是 6 个 validate runner 的统一防御性模式（5 个已使用，1 个待修复）。validator 的 `not errors` 保证 `ok` 始终为 `bool`。identity check 无误否定风险。

### 2.3 异常边界不变性

**挑战**: 修复是否改变异常传播边界？

**源码证据**: 当前 `_run_validate_source_map`（行 610-614）：
```python
rules_payload = _load_json_object(Path(str(getattr(args, "rules"))).resolve())
source_map_payload = _load_json_object(Path(str(getattr(args, "source_map"))).resolve())
result = validate_monitoring_source_map_payload(rules_payload, source_map_payload)
print(json.dumps(result, ensure_ascii=False, indent=2))
return 0
```

修复只改变最后一行 `return 0` → `return 0 if result.get("ok") is True else 1`。`_load_json_object` 可能抛出 `FileNotFoundError`/`OSError`/`ValueError`（行 606-607 docstring 已声明），这些异常在修复前后均向上传播到 entry 层的 `(FileNotFoundError, FileExistsError, ValueError)` → stderr + exit 1 处理。

`validate_monitoring_source_map_payload` 自身不抛出业务异常（docstring: "本函数把结构和一致性问题收集到结果中，不显式抛出业务异常"）。

**裁决**: **PASS**。异常集合、传播路径与 entry 层映射完全不变。

### 2.4 stdout JSON 不变性

**挑战**: 修复是否改变 stdout 输出？

**源码证据**: `print(json.dumps(result, ...))` 在 `return` 之前执行。修复不改变 `result` 的内容或 `json.dumps` 参数。`result` dict 的 `ok` 字段在修复前后均由 validator 决定；打印的 JSON 不变。

**裁决**: **PASS**。stdout JSON 在修复前后字节相同。

### 2.5 dispatch key / owner / DAG 不变性

**挑战**: 修复是否影响 dispatch mapping、函数 owner 或模块 DAG？

**源码证据**: `_run_validate_source_map` 是 `research_template.py` 的 39 个 `_run_*` runner 之一，通过 `if action == "validate-source-map"` dispatch。修复不改变函数名、签名、action key 或 owner 模块。不引入新 import、不修改其他 runner。

**裁决**: **PASS**。dispatch/owner/DAG 完全不变。

### 2.6 Slice 9/10 exact-behavior 例外边界

**挑战**: 此例外是否精确有界？是否会让 implementation agent 借机扩大 scope？

**源码证据与 plan 约束**:
- AGG-RT-CTRL-01 明确限定只允许修改 `_run_validate_source_map` 的 return 与 docstring，以及新增 CLI invalid 回归测试。
- "禁止顺手改变其他 38 runner、提取通用 validate wrapper、增加 compatibility/glue、新增 Slice 14，或改变 manual recovery application / rollback 使用默认 `run_label="configuration-application"` 的 v4.9/v5.0 accepted design。"
- adjudication 已将 WRITE-01/MIMO-WRITE-01（run_label）裁决为 `rejected-with-reason / CLOSED (ACCEPTED-DESIGN)`，明确不能作为 RT-01 附带修复。
- "修后 AST delta 只允许该 Return 与对应 docstring。"

**裁决**: **PASS**。例外边界由 AGG-RT-CTRL-01 的逐项禁止清单、adjudication 的 WRITE-01 rejection、以及 "AST delta 只允许该 Return 与对应 docstring" 三重约束。implementation agent 无扩大 scope 的合法路径。

### 2.7 测试构造可行性

**挑战**: invalid payload 回归测试是否可构造？是否有现成的 fixtures？

**源码证据**:
- `write_monitoring_rules_payload("financial", workspace_root=tmp_path)` 与 `write_monitoring_source_map_payload("consumer", workspace_root=tmp_path)` 会创建 template 不一致的文件（"financial" vs "consumer"）。
- 现有单元测试 `test_validate_monitoring_source_map_payload_reports_template_mismatch`（行 1171）已验证 `validate_monitoring_source_map_payload(rules_financial, source_map_consumer)` 返回 `{"ok": False, "errors": ["template mismatch: ..."]}`。
- 新 CLI 回归测试只需将同样的 payload 写入 tmp 文件，通过 `run_research_template_command` dispatch，断言 exit=1、stdout `ok is False`、errors 非空。
- 测试文件已导入 `write_monitoring_rules_payload`、`write_monitoring_source_map_payload`、`DayuCliArguments`、`run_research_template_command`。

**裁决**: **PASS**。测试构造简单、fixtures 现成、模式与现有测试（行 3272 的 valid 路径）对称。

### 2.8 既有测试不受影响

**挑战**: 修复是否会破坏现有测试？

**源码证据**: 现有测试 `test_run_validate_source_map_command_outputs_validation_json`（行 3272）使用 "consumer" 模板的 rules 和 source_map（template 一致），validator 返回 `{"ok": True, ...}`。修复后 `result.get("ok") is True` → `return 0`，与当前行为相同。测试断言 `result == 0` 和 `payload["ok"] is True` 均继续通过。

**裁决**: **PASS**。既有 valid 路径测试不受影响。

### 2.9 docstring 更新精确性

**挑战**: docstring 更新是否准确反映真实行为？

**当前 docstring**（行 601-602）: "校验结果成功输出时返回 0。" — 只描述成功路径，遗漏失败路径。

**plan 要求**: "校验成功返回 0，校验失败返回 1。"

**裁决**: **PASS**。新 docstring 精确描述修复后的双向返回契约，与实际代码 `return 0 if result.get("ok") is True else 1` 一致。

### 2.10 其余 aggregate findings 拒绝是否会让本 fix 越界

**挑战**: adjudication 拒绝的 WRITE-01/02/04/05、RT-02~06、ENG-01~10、SEC-01/02/05、GATE-01~11 findings 是否有被 "搭车" 修复的风险？

**adjudication 证据**: Controller 对每个 rejected finding 均给出 `rejected-with-reason / CLOSED` 与直接理由。AGG-RT-CTRL-01 的 "禁止" 清单逐项覆盖：
- 其他 runner → "禁止顺手改变其他 38 runner"
- run_label → "不改变 manual recovery application 或 rollback 的默认 `run_label`"
- 通用 wrapper → "提取通用 validate wrapper" 被禁止
- Slice 14 → "不新增 Slice 14"
- Ruff residual → "不在本 fix 机械清理"（erratum）

**裁决**: **PASS**。adjudication 的 CLOSED 裁决 + AGG-RT-CTRL-01 的禁止清单形成双重门禁。implementation agent 无法合法搭车修复任何其他 finding。

### 2.11 验证门禁完整性

**挑战**: plan 的验证门禁是否覆盖所有必要维度？

**plan 门禁清单**:
1. `pytest -k "validate_source_map"` — focused 修复验证
2. aggregate behavior suite（379 tests）— 行为不回归
3. pyright ratchet — 类型不退化
4. Ruff architecture ratchet positive=0 — lint 不退化
5. Python 3.11 min-compat full suite — 真实重跑（不复用旧字节证据）
6. dual-model focused 699 + 3 JSON machine gates — gate 不退化
7. `git diff --check` / secret / temp / conflict hygiene
8. owner/DAG/identity 结构复证
9. DeepSeek + MiMo aggregate re-review — 双路关闭 RT-01

**裁决**: **PASS**。门禁覆盖行为、类型、lint、结构、全量、gate 与双路 re-review。production/tests 字节变化后强制重跑 Python 3.11 full suite（不复用旧字节证据）是正确的。

---

## 3. 风险评估

| 风险 | 级别 | 说明 |
|---|---|---|
| result shape 错误 | 无 | `ok` 在顶层已由源码确认 |
| `is True` 误否定 | 无 | `not errors` 始终产出 `bool` |
| 异常边界扩大 | 无 | 只改 return，不改加载/校验/print |
| 测试构造困难 | 无 | fixtures 现成，模式对称 |
| scope creep | 无 | 三重禁止约束（AGG-RT-CTRL-01 + adjudication CLOSED + AST delta 限制） |
| 既有测试破坏 | 无 | valid 路径 `ok=True` → `return 0` 不变 |

---

## 4. 残余观察（非 findings，不阻塞）

### O-1: `_run_validate_source_map` 使用 `getattr` 而非直接属性访问

`args.rules` 和 `args.source_map` 通过 `getattr(args, ...)` 访问，与同文件其他 runner 一致。这是 Slice 10 S10-CTRL-04 的设计决策：表外 argparse 字段保持动态 `getattr`，不扩充 Dayu 字段。当前模式正确，不是 defect。

### O-2: 其他 4 个嵌套 `validation` 路径的 validate runner 使用 `isinstance(validation, dict)` 额外防护

`_run_validate_bundle`、`_run_validate_monitoring_plan`、`_run_validate_workbook_report`、`_run_validate_scheduler_manifest` 均先 `result.get("validation")` 再 `isinstance(validation, dict) and validation.get("ok") is True`。`_run_validate_source_map` 的顶层 `ok` 路径不需要此额外防护（validator 保证返回 dict）。两条路径的设计一致性由各自 validator 的返回结构保证。

---

## 5. 结论

AGG-RT-CTRL-01 是一个精确有界的单行 return 修复 + docstring 同步 + CLI invalid 回归测试。result 路径、`is True` 语义、异常边界、stdout、dispatch、owner/DAG 均经源码逐行验证无误。测试构造简单且 fixtures 现成。验证门禁完整覆盖行为/类型/lint/结构/gate/re-review。adjudication 的 CLOSED findings 与 AGG-RT-CTRL-01 的禁止清单形成双重 scope 门禁。

**Verdict: PASS。open High/Medium/Low = 0/0/0。达到 code-generation-ready 标准。**

---

*MiMo 独立 plan reviewer | 2026-08-08*
