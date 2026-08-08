# v5.8 AGG-RT-CTRL-01 Adversarial Plan Review

- **审查者**: DeepSeek 独立 plan reviewer
- **日期**: 2026-08-08
- **分支**: `codex/dual-model-research-mvp`
- **HEAD**: `4d2535d` (`gateflow: accept cli write architecture plan v5.7`)
- **审查对象**:
  - `docs/plans/2026-08-07-cli-write-architecture-refactor.md` (v5.8 CANDIDATE)
  - `docs/reviews/plan-v5.8-aggregate-rt-exit-erratum-20260808-codex.md` (勘误记录)
  - `docs/reviews/aggregate-code-review-adjudication-20260808-codex.md` (Controller 裁决)
- **Gate**: plan review → code-generation-ready 判定

---

## 1. Verdict

**PASS — code-generation-ready.**

Open High/Medium/Low = **0/0/1**。

AGG-RT-CTRL-01 的最小修复范围、精确实现契约、result shape 访问路径、测试构造策略、
scope 冻结、sequencing、Gateflow closeout 与 Slice 9/10 旧 exact 契约例外消歧均经
源码级 adversarial 验证通过。唯一 LOW finding 是测试构造策略未显式锁定既有
template-mismatch 模式，但不影响实施正确性。

---

## 2. 审查方法

本轮对以下维度逐项 adversarial 挑战，每项以源码/测试/Git 直接证据判定：

| 维度 | 判定 | 证据 |
|---|---|---|
| 行为边界 | PASS | 源码级确认 `result.get("ok") is True` 正确处理 ok=True/False/缺失/非布尔 |
| result shape | PASS | `validate_monitoring_source_map_payload` L421-428 始终返回 `dict[str, object]`，`ok` 始终为 `bool`，零 None/非 dict 路径 |
| 测试构造 | PASS with 1 Low | 既有 valid 测试 L3272 + validator 单元测试 L1171 提供充分构造模式 |
| scope 冻结 | PASS | AGG-RT-CTRL-01 逐项枚举禁止修改项；Controller 裁决逐项拒绝其余 findings |
| sequencing | PASS | plan review → accepted commit → implementation → full suite → aggregate re-review，无 gap |
| Gateflow closeout | PASS | v5.8 为 plan erratum 非新 slice；closeout 条件明确：双路 re-review PASS + RT-01 CLOSED + open 0/0/0 |
| Slice 9/10 例外消歧 | PASS | 明确声明"唯一有界例外"，逐项锁定只允许 Return + docstring 变化 |
| 其余 findings 拒绝 → 越界风险 | PASS | Controller 裁决 WRITE-01/RT-02 等全部 rejected-with-reason；plan 显式禁止顺手修复 |

---

## 3. 逐维度详细分析

### 3.1 行为边界

**命题**: `return 0 if result.get("ok") is True else 1` 对所有合法 result shape 正确。

**验证**:

`validate_monitoring_source_map_payload` (L359-428) 的返回构造：

```python
return {
    "ok": not errors,       # bool, always present, initialized L376: errors = []
    "template": ...,
    "errors": errors,        # list[str], always present
    "warnings": warnings,    # list[str], always present
    ...
}
```

行为矩阵：

| result["ok"] 值 | `.get("ok")` | `is True` | 返回 | 语义 |
|---|---|---|---|---|
| `True` | `True` | `True` | `0` | 校验通过 ✅ |
| `False` | `False` | `False` | `1` | 校验失败 ✅ |
| 缺失 (key absent) | `None` | `False` | `1` | fail-closed ✅ |
| 非布尔 (validator bug) | 任意 | `False` | `1` | fail-closed ✅ |

**结论**: 所有合法路径 + 异常路径均正确处理。fail-closed 策略正确。与
`_run_validate_research_workbook` (L497) 的 `result.get("ok") is True` 严格一致。

### 3.2 result shape

**命题**: `result.get("ok")` 访问路径与 validator 返回结构一致。

**验证**:

- `_run_validate_source_map` 直接打印 `result`（不包装），`ok` 在顶层
- 对比 `_run_validate_research_workbook`：同样直接访问 `result.get("ok")`，不经过
  `result.get("validation")` 嵌套
- 对比 `_run_validate_bundle` 等 4 个：validator 返回的 `validation` 嵌套在
  `result["validation"]` 中，因此使用 `result.get("validation").get("ok")`

`_run_validate_source_map` 的 result shape 属于 Pattern A（直接 ok），与
`_run_validate_research_workbook` 一致。计划正确选择了 `result.get("ok")` 而非
`result.get("validation", {}).get("ok")`。

**结论**: result shape 访问路径正确。与既有 Pattern A runner 一致。

### 3.3 测试构造

**命题**: 新增 invalid CLI 回归的构造策略充分且可实施。

**既有证据**:

1. 既有 valid CLI 测试 (L3272-3288)：
   ```python
   rules_path = write_monitoring_rules_payload("consumer", workspace_root=tmp_path)
   source_map_path = write_monitoring_source_map_payload("consumer", workspace_root=tmp_path)
   args = DayuCliArguments(
       research_template_action="validate-source-map",
       rules=str(rules_path),
       source_map=str(source_map_path),
   )
   result = run_research_template_command(args)
   assert result == 0
   assert payload["ok"] is True
   ```

2. 既有 validator 单元测试 `test_validate_monitoring_source_map_payload_reports_template_mismatch`
   (L1171-1175)：使用 `build_monitoring_rules_payload("financial")` +
   `build_monitoring_source_map_payload("consumer")` 构造 template 不一致。

**invalid 测试构造策略**: 使用 `write_monitoring_rules_payload("financial", ...)` +
`write_monitoring_source_map_payload("consumer", ...)` 写入两个 template 不同的文件，
通过 `run_research_template_command(args)` 全 dispatch 路径调用，断言：
- `result == 1`
- `json.loads(capsys.readouterr().out)["ok"] is False`
- `len(payload["errors"]) > 0`

**L-PLAN-01 [Low] — 测试构造未显式指向既有 template-mismatch 模式**

计划写"构造语法有效但业务不一致的 rules/source-map JSON"但未显式指向
`test_validate_monitoring_source_map_payload_reports_template_mismatch` (L1171)
作为推荐构造策略。

- **影响**: 实施 agent 可能选择手动构造 JSON dicts 再写入文件的路径，增加不必要的
  复杂度。但任何合理的 inconsistency 构造（template mismatch / missing source /
  binding status）均能正确触发 `ok=False` 并验证退出码。
- **不升级为 Medium 的理由**: (a) 既有 test 在同一文件中可直接发现；
  (b) 计划描述已足够——"语法有效但业务不一致"明确排除了无效 JSON 路径；
  (c) 实施 agent 有 validator 单元测试 L1144-1175 的完整构造参考。
- **建议**: 实施时直接采用 template-mismatch 策略（`"financial"` vs `"consumer"`），
  这是最简洁、最不易出错的构造方式。

**结论**: 测试构造策略可实施，1 个 Low observation。

### 3.4 scope 冻结

**命题**: 计划的 scope 约束防止修复越界。

**验证**:

计划 AGG-RT-CTRL-01 显式禁止：

| 禁止项 | 计划证据 |
|---|---|
| 修改其他 38 runner | "stdout、异常、dispatch、其他 runner、owner/DAG 不变" |
| 新增 Slice 14 | "不新增 Slice 14" |
| 改变 manual/rollback default label | "不改变 manual recovery application 或 rollback 的默认 `run_label=\"configuration-application\"`" |
| 通用 validate wrapper | "禁止顺手改变其他 38 runner、提取通用 validate wrapper" |
| 修改 JSON stdout | "stdout...不变" |
| 修改异常传播 | "异常...不变" |
| 修改 dispatch mapping | "dispatch...不变" |

Controller 裁决 (aggregate-code-review-adjudication) 逐项拒绝：
- WRITE-01 (run_label): rejected-with-reason / ACCEPTED-DESIGN
- WRITE-02/04/05: rejected-with-reason
- RT-02..RT-06: rejected-with-reason
- ENG-01..ENG-10: rejected-with-reason
- SEC-01/02/05: rejected-with-reason
- GATE-01..GATE-11: rejected-with-reason

**结论**: scope 冻结完备，零越界风险。

### 3.5 sequencing

**命题**: plan review → implementation → verification 序列无 gap。

**当前 gate 状态** (勘误记录 L102-107):
- v5.8 candidate plan 等待双路 plan review ← **本 review**
- plan 未 accepted 前不得改 production/tests
- plan accepted → 实施 Aggregate Fix → 双路 aggregate re-review
- re-review PASS + RT-01 CLOSED + Controller open 0/0/0 → accepted deepreview commit

**实现后验证序列** (plan L2685-2730):
1. `pytest -k "validate_source_map"` — focused
2. Aggregate behavior suite (379)
3. `ci_pr_pyright` — type ratchet
4. Architecture Ruff ratchet (positive=0)
5. **Python 3.11 full suite (真实重跑，不复用 Slice 13 字节同一性证据)**
6. Dual-model focused 699 + 3 JSON machine gates
7. `git diff --check`
8. 双路 aggregate deepreview/re-review

**关键判断**: 计划正确识别 production 字节变化后 Slice 13 的 Git-object identity
证据失效，明确要求真实重跑 Python 3.11 full suite。这是正确且必要的。

**结论**: sequencing 完备，无 gap。

### 3.6 Gateflow closeout

**命题**: v5.8 plan erratum 不破坏 Gateflow 状态机。

**验证**:

- v5.8 是 plan erratum，不是新 Slice。勘误记录 L90-97 明确"production、tests、
  README、CI workflow 与外部 review artifacts 均冻结"
- plan accepted 后实施为 direct modification（`research_template.py` 1 行 +
  `test_research_template_command.py` 新增测试），不创建新 Slice commit
- Gateflow closeout 条件与 v5.7 一致：双路 aggregate re-review PASS +
  Controller open 0/0/0 → accepted deepreview commit → ready-to-open-draft-PR

**结论**: Gateflow closeout 路径清晰，不引入新状态或 ambiguity。

### 3.7 Slice 9/10 旧 exact 契约例外消歧

**命题**: "唯一有界例外"声明是否足够消歧。

**验证**:

计划 L54 声明：
> 该变更是对 Slice 9 stripped-docstring AST exact migration 与 Slice 10
> behavior-preservation 的唯一有界例外

勘误记录 L22-25 补充 Git 证据：
> Git 审计证明该行为由 `7579e0d` 引入，不在 `origin/main=2115c86`，但已存在于
> architecture baseline `5821014`。因此 Slice 9 stripped-docstring AST exact migration
> 与 Slice 10 behavior-preservation 没有制造回归，却把一个真实 PR defect 纳入了
> accepted behavior。

消歧要点：
1. 例外的**性质**: PR correctness defect，非设计选择
2. 例外的**范围**: 仅 `_run_validate_source_map` 的 Return 语句与 docstring
3. 例外的**边界**: 不授权对 Slice 9/10 其他 exact contract 的重新审理
4. 例外的**Git 证据**: `7579e0d` 引入，早于 baseline `5821014`，Slice 9/10 忠实
   保留而非制造

**结论**: 例外消歧充分。Git 时间线 + 精确范围声明 + 边界冻结共同防止未来误读。

### 3.8 其余 findings 拒绝 → 越界风险

**命题**: Controller 拒绝其余 findings 是否会因遗漏 legitimate fix 而导致后续被迫越界。

**验证**:

Controller 对每个被拒绝 finding 给出了明确拒绝理由：

| Finding | 拒绝理由类别 | 越界风险评估 |
|---|---|---|
| WRITE-01 (run_label) | ACCEPTED-DESIGN — v4.9/v5.0 精确锁定 | 无风险 — 默认 label 描述底层 domain，非外层 action |
| WRITE-02 (assert) | PRE-EXISTING / NON-DEFECT — 已验证不变量 | 无风险 — 来自迁移前实现，无 public CLI 绕过复现 |
| WRITE-04 (shallow copy) | PRE-EXISTING / HYPOTHETICAL — 当前全标量字段 | 无风险 — 无真实可变共享 caller 证据 |
| RT-02 (load_json_object 重复) | NON-DEFECT — 错误契约不同，统一会改变行为 | 无风险 — 维护建议非 correctness defect |
| RT-03..RT-06 | 各种 rejection — 私有常量按 owner/DAG 持有是 accepted design | 无风险 — 均为维护建议 |
| ENG-01..ENG-10 | PRE-EXISTING / INTENTIONAL / 无复现 | 无风险 — 均在 architecture baseline 后无本 work unit delta |
| SEC-01/02/05 | PRE-EXISTING / ACCEPTED-DESIGN / OUT-OF-SCOPE | 无风险 — `is_subpath` lexical 语义为 v4.1 SA-02 明确要求 |
| GATE-01..GATE-11 | PRE-EXISTING-TO-WORK-UNIT / 无复现 | 无风险 — 699 + 3 JSON machine gates 全部通过 |

**结论**: 所有被拒绝 finding 均有明确的非越界理由。不存在"拒绝后被迫在后续越界修复"的
风险。

---

## 4. 正面确认汇总

| 维度 | 结果 | 证据 |
|---|---|---|
| `result.get("ok")` 访问路径正确 | ✅ | validator L422 直接返回 `{"ok": not errors, ...}`，ok 在顶层 |
| `is True` 身份比较正确 | ✅ | `ok` 始终为 Python `bool`；fail-closed 对 None/非布尔 |
| 与既有 Pattern A runner 一致 | ✅ | `_run_validate_research_workbook` L497 使用完全相同的表达式 |
| 不改变 dispatch mapping | ✅ | L1287 `"validate-source-map": _run_validate_source_map` 不变 |
| 不改变 JSON stdout | ✅ | `print(json.dumps(result, ...))` 在 return 之前，不受影响 |
| 不改变异常传播 | ✅ | return 语句在 validator 成功返回后，异常路径不受影响 |
| 不改变 owner/DAG | ✅ | `_run_validate_source_map` 仍在 `research_template.py`，仍由 dispatch mapping 引用 |
| docstring 同步正确 | ✅ | 新增"校验失败返回 1"准确描述新行为，Args/Raises 不变 |
| valid 路径保留 | ✅ | 既有 L3272 测试继续断言 `result == 0` 且 `ok is True` |
| 字节变化后重跑 full suite | ✅ | 计划明确要求真实重跑，不复用 Slice 13 Git-object identity 证据 |

---

## 5. 未发现的风险

以下潜在风险经源码验证后排除：

| 假设风险 | 排除证据 |
|---|---|
| `result` 可能为 `None` | `validate_monitoring_source_map_payload` 始终返回 `dict[str, object]`，零 None 路径 |
| `ok` key 可能缺失 | validator L376 始终初始化 `errors = []`，L422 `"ok": not errors` 始终存在 |
| `ok` 可能为非布尔 | `not errors` 始终为 `bool` |
| `json.dumps(result)` 可能因非 dict result 失败 | result 始终为 dict，不受 exit code 变化影响 |
| dispatch 路径可能因修复而变化 | dispatch mapping 是静态 `dict[str, Callable]`，函数引用不变 |
| 其他 runner 可能受影响 | 39 runner 各自独立，零共享状态 |

---

## 6. Open Findings

| ID | Severity | Summary | Evidence |
|----|----------|---------|----------|
| L-PLAN-01 | **Low** | 新增 invalid 测试构造未显式锁定 template-mismatch 策略 | plan 写"业务不一致"但未引用既有 L1171 `test_validate_monitoring_source_map_payload_reports_template_mismatch` 作为构造参考。不影响实施正确性——既有 test 在同一文件可发现，任何合理 inconsistency 均能触发 `ok=False`。建议实施时直接采用 `"financial"` vs `"consumer"` template mismatch |

---

## 7. 总体评估

AGG-RT-CTRL-01 是 CLI Write 架构重构 aggregate 阶段最小、最精确的 plan fix：

- **1 行 production 变更**：`return 0` → `return 0 if result.get("ok") is True else 1`
- **1 句 docstring 更新**：失败返回 1
- **1 个新测试**：真实 CLI invalid 路径退出码 1
- **0 个越界修改**：stdout、异常、dispatch、owner/DAG、其余 38 runner、manual/rollback
  label 全部冻结

修复动机成立（CLI automation 依赖退出码），方案选择正确（方案 C vs 方案 A/B/D），
scope 冻结完备，sequencing 与 Gateflow closeout 清晰。唯一 LOW finding 是测试构造
策略的 minor specification incompleteness，不阻塞 code-generation-ready 判定。

---

*DeepSeek Independent Plan Reviewer | 2026-08-08*
