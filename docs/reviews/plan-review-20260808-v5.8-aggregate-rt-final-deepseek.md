# v5.8 AGG-RT-CTRL-01 Final Corrective Plan Re-Review

- **审查者**: DeepSeek 独立 plan reviewer（final corrective pass）
- **日期**: 2026-08-08
- **分支**: `codex/dual-model-research-mvp`
- **HEAD**: `4d2535d`
- **初审 artifact**: `docs/reviews/plan-review-20260808-v5.8-aggregate-rt-deepseek.md`（PASS，open 0/0/1，L-PLAN-01）
- **审查对象（已修正）**:
  - `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v5.8
  - `docs/reviews/plan-v5.8-aggregate-rt-exit-erratum-20260808-codex.md`
  - `docs/reviews/aggregate-code-review-adjudication-20260808-codex.md`
- **Gate**: final corrective plan re-review — 只核对 L-PLAN-01 CLOSED、零 scope 扩张、AGG-RT-CTRL-01 仍 code-generation-ready

---

## 1. Final Verdict

**PASS — code-generation-ready.**

Open High/Medium/Low = **0/0/0**。

初审 L-PLAN-01 已 CLOSED。plan 现在精确锁定 invalid 测试的 template-mismatch 构造策略
（financial rules + consumer source-map），valid 回归锁定 consumer/consumer 对称路径，
明文禁止手写 payload 或另选不一致模式。scope 零扩张，AGG-RT-CTRL-01 核心契约不变。

---

## 2. L-PLAN-01 闭合验证

### 2.1 初审 finding 回顾

> L-PLAN-01 [Low]: 新增 invalid 测试构造未显式锁定 template-mismatch 策略。plan 写
> "构造语法有效但业务不一致的 rules/source-map JSON"但未显式指向既有
> `test_validate_monitoring_source_map_payload_reports_template_mismatch` (L1171) 作为
> 推荐构造策略。

### 2.2 修正证据

**Master plan §Aggregate Fix RT-01 (L2674-2681)**:

> 在 `tests/cli/test_research_template_command.py` 通过真实
> `run_research_template_command`/`validate-source-map` dispatch 路径新增 invalid payload
> 回归：必须调用 `write_monitoring_rules_payload("financial", workspace_root=tmp_path)` 与
> `write_monitoring_source_map_payload("consumer", workspace_root=tmp_path)` 写入 template
> mismatch 文件，经真实 entry 断言返回 `1`，解析 stdout 后断言
> `payload["ok"] is False` 且 `payload["errors"]` 非空。不得手写 payload 或另选不一致
> 模式。valid 回归必须用 consumer rules + consumer source-map 的对称构造，继续断言返回
> `0` 与 stdout `ok is True`。

**勘误记录 §Plan review observation 裁决 (L104-115)**:

> - **L-PLAN-01**：`accepted / FIXED`。原"语法有效但业务不一致"虽然可实施，但仍允许
>   implementation agent 手写 JSON 或自行选择 failure mode。计划现已锁定既有最小模式：
>   financial rules + consumer source-map 产生 template mismatch，consumer/consumer 作为
>   valid 对称路径；两者均经真实 CLI entry。没有扩大文件、行为或验证 scope。

**Controller 裁决 §Gate 状态与下一步 (L167-171)**:

> - DeepSeek L-PLAN-01：`accepted / FIXED`。invalid CLI regression 已精确锁定
>   `write_monitoring_rules_payload("financial", workspace_root=tmp_path)` +
>   `write_monitoring_source_map_payload("consumer", workspace_root=tmp_path)` 的 template
>   mismatch；valid 回归锁定 consumer/consumer。两者都必须经真实
>   `run_research_template_command`，禁止手写 payload 或另选不一致模式。

### 2.3 闭合判定

| 初审关注点 | 修正后状态 | 证据 |
|---|---|---|
| 构造策略未显式锁定 | 精确锁定 financial+consumer template mismatch | plan L2676-2677，勘误 L64-66 |
| 可能手写 JSON | 明文禁止"不得手写 payload 或另选不一致模式" | plan L2679-2680 |
| 未引用既有测试模式 | 既有 fixture `write_monitoring_rules_payload`/`write_monitoring_source_map_payload` 即为 L3272 使用的同一 helper | plan L2676-2677 |
| valid 路径是否对称 | consumer/consumer 对称构造，经同一真实 entry | plan L2680-2681 |

**L-PLAN-01: CLOSED** ✅

---

## 3. Scope 扩张检查

逐项对比初审 scope 约束与修正后 plan：

| 约束项 | 初审状态 | 修正后状态 | 扩张？ |
|---|---|---|---|
| production 修改范围 | `research_template.py` only | 不变 | 否 |
| test 修改范围 | `test_research_template_command.py` only | 不变 | 否 |
| 核心 fix | `return 0 if result.get("ok") is True else 1` | 不变 | 否 |
| docstring 更新 | 校验成功 0 / 失败 1 | 不变 | 否 |
| invalid 测试 | "业务不一致"（generic） | financial+consumer template mismatch（exact） | 否 — 精确化，非扩张 |
| valid 测试 | 保留既有 | 保留 + 明确 consumer/consumer 对称 | 否 — 明确化，非扩张 |
| 其他 38 runner | 冻结 | 不变 | 否 |
| stdout/异常/dispatch/owner/DAG | 冻结 | 不变 | 否 |
| manual/rollback label | 冻结 | 不变 | 否 |
| 新增 Slice 14 | 禁止 | 不变 | 否 |
| 通用 validate wrapper | 禁止 | 不变 | 否 |
| README 修改 | 禁止 | 不变 | 否 |

**结论**: 零 scope 扩张。修正仅在测试构造策略上增加精确度（generic → exact fixture names），
不改变修改范围、核心契约或冻结约束。

---

## 4. AGG-RT-CTRL-01 code-generation-ready 再确认

核心实现契约（初审已确认正确，修正未改变）：

```python
def _run_validate_source_map(args: DayuCliArguments) -> int:
    # 既有 rules/source-map 加载、validator 调用与 JSON stdout 保持原顺序、原参数和原格式。
    result = validate_monitoring_source_map_payload(rules_payload, source_map_payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") is True else 1
```

| 维度 | 初审结果 | 修正后 |
|---|---|---|
| `result.get("ok")` 访问路径正确 | ✅ | ✅ 不变 |
| `is True` 身份比较正确 | ✅ | ✅ 不变 |
| 与 Pattern A runner 一致 | ✅ | ✅ 不变 |
| 不改变 dispatch/owner/DAG | ✅ | ✅ 不变 |
| 不改变 stdout/异常 | ✅ | ✅ 不变 |
| scope 冻结完备 | ✅ | ✅ 不变 |
| sequencing 无 gap | ✅ | ✅ 不变 |
| Gateflow closeout 清晰 | ✅ | ✅ 不变 |
| Slice 9/10 例外消歧充分 | ✅ | ✅ 不变 |
| 其余 findings 拒绝不导致越界 | ✅ | ✅ 不变 |
| 测试构造策略 | ⚠️ L-PLAN-01 | ✅ CLOSED |

---

## 5. 最终完成定义确认

AGG-RT-CTRL-01 实施后必须通过的门禁（plan L2690-2730，未改变）：

- focused `pytest -k "validate_source_map"` — 至少 2 tests（valid + invalid）
- aggregate behavior suite 379
- pyright ratchet 219/219/new=0
- architecture Ruff positive=`{}`
- **Python 3.11 full suite 真实重跑**（不复用 Slice 13 字节同一性证据）
- dual-model focused 699 + 3 JSON machine gates
- `git diff --check`
- 双路 aggregate deepreview/re-review → RT-01 CLOSED + Controller open 0/0/0

---

## 6. Open Findings

**无。**

| ID | 初审严重度 | 状态 | 闭合证据 |
|----|-----------|------|----------|
| L-PLAN-01 | Low | **CLOSED** | plan L2674-2681 精确锁定 financial+consumer template mismatch；勘误 L104-115 记录 `accepted / FIXED`；裁决 L167-171 确认 |

---

*DeepSeek Independent Plan Reviewer — Final Corrective Pass | 2026-08-08*
