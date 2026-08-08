# Slice 2A write artifact caller code-review 修复记录

- **日期**: 2026-08-07
- **基线**: `8350226` (`gateflow: accept write artifact utilities slice 1`)
- **状态**: REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW
- **审查来源**:
  - `docs/reviews/code-review-20260807-220136.md`（DeepSeek）
  - `docs/reviews/code-review-20260807-220137.md`（MiMo，事实已由 Controller 纠正）

## Controller 裁决

Controller 接受两项 finding：

1. `changed_roles` guard 按较高严重度 **Medium** 处理。报告 schema 与错误消息均要求列表，不能把字典键或字符串字符静默格式化为角色。
2. rollback `receipt_source_path` 异常类型按 **Low** 处理。核心数据校验统一使用 `ValueError`；正常路径以及先行 validator 行为不变，不新增跨 scope monkeypatch 测试。

除上述裁决外不扩展修复范围。

## 四处生产修复

| # | 文件与入口 | 修复 |
|---|---|---|
| 1 | `write_model_challenger_promotion.py::format_write_model_challenger_promotion_report` | `changed_roles` guard 从接受 `(dict, list, str)` 收紧为仅接受 `list`；保留原 `TypeError` 精确消息。 |
| 2 | `write_model_configuration_change.py::format_write_model_configuration_change_request_report` | `changed_roles` guard 从接受 `(dict, list, str)` 收紧为仅接受 `list`；保留原 `TypeError` 精确消息。 |
| 3 | `write_model_configuration_rollback.py::build_write_model_configuration_operator_rollback_approval` | 非文本 `receipt_source_path` 的异常从 `TypeError` 改为 `ValueError`，消息不变。 |
| 4 | `write_model_configuration_rollback.py::verify_write_model_configuration_operator_rollback_approval` | 非文本 `receipt_source_path` 的异常从 `TypeError` 改为 `ValueError`，消息不变。 |

## 回归测试

- `tests/application/test_write_model_challenger_promotion.py`
  - 参数化覆盖 dict 与 str 两类畸形 `changed_roles`。
  - 断言 `TypeError` 及精确消息
    `promotion proposal model_plan_review changed_roles must be a list`。
- `tests/application/test_write_model_configuration_change.py`
  - 参数化覆盖 dict 与 str 两类畸形 `changed_roles`。
  - 断言 `TypeError` 及精确消息
    `configuration change request target changed_roles must be a list`。

两个新测试均使用精确联合类型 `dict[str, str] | str`，未新增
`Any`、`object`、`cast` 或 type-ignore。

## 验证

### 聚焦测试

```text
source .venv/bin/activate
pytest -q \
  tests/application/test_write_model_challenger_promotion.py \
  tests/application/test_write_model_configuration_change.py
```

结果：`23 passed in 1.17s`。

### Cohort A 相关套件

```text
source .venv/bin/activate
pytest -q tests/application/test_write_artifact_utils.py \
  tests/application/test_write_model_configuration_change.py \
  tests/application/test_write_model_configuration_preapplication.py \
  tests/application/test_write_model_challenger_run_approval.py \
  tests/application/test_write_model_challenger_preflight_approval.py \
  tests/application/test_write_model_challenger_promotion.py \
  tests/application/test_write_model_challenger_proposal.py \
  tests/application/test_write_model_health.py \
  tests/application/test_write_run_comparison.py \
  tests/application/test_write_model_challenger_verification.py \
  tests/application/test_write_challenger.py
```

结果：`258 passed in 11.16s`。shared helper 聚焦入口仍为 `23 passed`。

### Pyright

```text
source .venv/bin/activate
pyright dayu/services/
```

结果：`0 errors, 0 warnings, 0 informations`。

### Ruff

```text
source .venv/bin/activate
ruff check --select F,I001 <11 production files> <6 changed test files>
```

结果：`All checks passed!`。

全规则逐文件 rule-code multiset 与 `HEAD` 对比，无新增违规。当前差异：

- change：`8 → 7`
- rollback：`7 → 6`
- preapplication：`15 → 13`
- run approval：`10 → 9`
- promotion：`9 → 8`
- 其余生产文件与 HEAD rule-code multiset 相同

### 覆盖率

直接 pytest-cov 会触发 Python 3.13/NumPy tracer 问题，因此沿用已记录的
preload + `coverage.Coverage(..., timid=True)` workaround。

| 文件 | 覆盖率 |
|---|---:|
| `_write_artifact_utils.py` | 100% |
| `write_model_configuration_change.py` | 80% |
| `write_model_configuration_rollback.py` | 81% |
| `write_model_configuration_preapplication.py` | 80% |
| `write_model_challenger_run_approval.py` | 80% |
| `write_model_challenger_preflight_approval.py` | 81% |
| `write_model_challenger_promotion.py` | 82% |
| `write_model_challenger_proposal.py` | 84% |
| `write_model_health.py` | 88% |
| `write_model_live_smoke_plan.py` | 81% |
| `write_run_comparison.py` | 86% |

全部达到 `AGENTS.md` 的单文件 `>= 80%` 门槛。

### 结构与 diff

```text
rg <eligible private definitions> <10 Cohort A files>
rg <deferred private definitions> <10 Cohort A files>
git diff --name-only -- <9 Cohort B files>
git diff --check
```

结果：

- eligible 私有定义为零（promotion defer `_serialize` 除外）
- deferred 定义全部保留
- Cohort B 9 文件 diff 为零
- `git diff --check` 通过

## 残余风险

- rollback 两处新 guard 位于已由先行 validator 保护的 defense-in-depth 路径；
  按 Controller 裁决不引入跨 scope monkeypatch 测试。
- change 与 preapplication 覆盖率仍恰为 80%，但本轮新增测试直接覆盖已接受的
  operator-facing report finding，没有引入生产 glue seam。
