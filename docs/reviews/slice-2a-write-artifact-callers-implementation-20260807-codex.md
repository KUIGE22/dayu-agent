# Slice 2A write artifact caller 迁移实现记录

- **日期**: 2026-08-07
- **基线**: `8350226` (`gateflow: accept write artifact utilities slice 1`)
- **状态**: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT
- **范围**: Slice 2A Cohort A 10 个生产文件及其直接测试入口

## 允许与实际修改路径

生产代码：

- `dayu/services/write_model_configuration_change.py`
- `dayu/services/write_model_configuration_rollback.py`
- `dayu/services/write_model_configuration_preapplication.py`
- `dayu/services/write_model_challenger_run_approval.py`
- `dayu/services/write_model_challenger_preflight_approval.py`
- `dayu/services/write_model_challenger_promotion.py`
- `dayu/services/write_model_challenger_proposal.py`
- `dayu/services/write_model_health.py`
- `dayu/services/write_model_live_smoke_plan.py`
- `dayu/services/write_run_comparison.py`

共享 helper 及测试：

- `dayu/services/_write_artifact_utils.py`（按 accepted v4.4 erratum 仅扩宽 `require_mapping` 输入类型，函数体与 identity-return 不变）
- `tests/application/test_write_artifact_utils.py`
- `tests/application/test_write_model_configuration_change.py`
- `tests/application/test_write_model_challenger_run_approval.py`
- `tests/application/test_write_model_challenger_promotion.py`
- `tests/application/test_write_model_configuration_preapplication.py`
- `tests/application/test_write_run_comparison.py`

实现记录：

- `docs/reviews/slice-2a-write-artifact-callers-implementation-20260807-codex.md`

Cohort B 9 文件未修改，`tests/README.md` 已有当前 shared helper 测试入口，本 slice 无需改写。

v4.4 类型 erratum 的决策与验收证据：

- `docs/reviews/slice-2a-require-mapping-type-adjudication-20260807-212526-deepseek.md`
- `docs/reviews/slice-2a-require-mapping-type-adjudication-20260807-212527-mimo.md`
- `docs/reviews/plan-c5-v4.4-type-erratum-20260807-deepseek.md`
- `docs/reviews/plan-c5-v4.4-type-erratum-rereview-20260807-mimo.md`（`9/9 PASS`，零 findings）
- `docs/plans/2026-08-07-cli-write-architecture-refactor.md`（`v4.4 ACCEPTED / MIMO RE-REVIEW PASS`）

## 逐文件迁移

| 文件 | 删除的 eligible 定义 | shared 替换 | 保留/defer |
|---|---|---|---|
| `write_model_configuration_change.py` | `_canonical_json`, `_fingerprint`, `_file_fingerprint`, `_validated_fingerprint`, `_mapping`, `_absolute_path`, `_serialize` | `canonical_json_str`, `fingerprint_str`, `file_fingerprint`, `validated_fingerprint`, `require_mapping`, `absolute_path`, `serialize_pretty` | `_required_text`, `_format_utc`, `_persist_immutable` |
| `write_model_configuration_rollback.py` | `_canonical_json`, `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_validated_fingerprint`, `_mapping`, `_required_text`, `_absolute_path`, `_is_relative_to`, `_serialize`, `_decode_base64` | `canonical_json_str`, `fingerprint_str`, `file_fingerprint`, `bytes_fingerprint`, `validated_fingerprint`, `require_mapping`, `require_text`, `absolute_path`, `is_subpath`, `serialize_pretty`, `decode_base64` | `_format_utc`, `_snapshot_fingerprint`, `_persist_immutable` |
| `write_model_configuration_preapplication.py` | `_canonical_json`, `_fingerprint`, `_file_fingerprint`, `_bytes_fingerprint`, `_validated_fingerprint`, `_mapping`, `_absolute_path`, `_serialize`, inline `b64decode` | `canonical_json_str`, `fingerprint_str`, `file_fingerprint`, `bytes_fingerprint`, `validated_fingerprint`, `require_mapping`, `absolute_path`, `serialize_pretty`, `decode_base64` | `_required_text`, `_persist_immutable` |
| `write_model_challenger_run_approval.py` | `_canonical_json`, `_fingerprint`, `_file_fingerprint`, `_validated_fingerprint`, `_mapping`, `_serialize` | `canonical_json_str`, `fingerprint_str`, `file_fingerprint`, `validated_fingerprint`, `require_mapping`, `serialize_pretty` | `_required_text`, `_format_utc`, `_validated_absolute_path`, `_persist_immutable` |
| `write_model_challenger_preflight_approval.py` | `_canonical_json`, `_fingerprint`, `_validated_fingerprint` | `canonical_json_str`, `fingerprint_str`, `validated_fingerprint` | `_required_text`, `_format_utc` |
| `write_model_challenger_promotion.py` | `_canonical_json`, `_fingerprint`, `_file_fingerprint`, `_validated_fingerprint`, `_mapping` | `canonical_json_str`, `fingerprint_str`, `file_fingerprint`, `validated_fingerprint`, `require_mapping` | `_required_text`, non-sort-key `_serialize` |
| `write_model_challenger_proposal.py` | `_canonical_json`, `_fingerprint`, `_validated_fingerprint`, `_mapping` | `canonical_json_str`, `fingerprint_str`, `validated_fingerprint`, `optional_mapping` | 无 |
| `write_model_health.py` | `_fingerprint`, `_mapping` | `fingerprint_str`, `optional_mapping` | `_history_fingerprint` 是业务级 defer，不在 eligible 列表 |
| `write_model_live_smoke_plan.py` | `_canonical_json`, `_fingerprint`, `_serialize` | `canonical_json_str`, `fingerprint_str`, `serialize_pretty` | `_required_text`, `_file_fingerprint_if_present`, `_persist_immutable` |
| `write_run_comparison.py` | `_mapping` | `optional_mapping` | 无 |

语义边界保持：

- configuration change/preapplication 仍先经本地族 3 `_required_text`，再调用 `absolute_path`；preapplication codec 同样先预处理文本。
- rollback 的路径与 codec 先经 shared `require_text`；`is_subpath` 保持词法判断，不 resolve symlink。
- 五个严格 mapping 文件直接使用 identity-return `require_mapping`；proposal/health/comparison 使用静默 `optional_mapping`，未引入 copy adapter。
- auto 精度 `_format_utc`、promotion non-sort-key `_serialize`、validated absolute path、snapshot/history fingerprint 及各 persist family 均留在原位。
- 已删除 eligible 私有 seam 的差分 corpus 改为直接断言 shared helper；deferred 私有族 characterization 继续保留。

## 测试与验证

### 聚焦与相关 application 测试

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

结果：review 修复后为 `258 passed in 11.16s`。其中 shared helper 聚焦入口仍为 `23 passed`，包含 v4.4 `MappingProxyType` 非字典 Mapping identity 回归。新增四个参数化 case 覆盖 promotion/change 报告对 dict 与 str 两类畸形 `changed_roles` 的精确拒绝。

### 覆盖率

直接 pytest-cov 会在 Python 3.13/NumPy 导入期触发 tracer 问题。按 Slice 1 已记录的 workaround，先导入 `dayu.services`，从 `sys.modules` 与 package attribute 移除当前目标模块，再使用 `coverage.Coverage(source=[module_name], timid=True)` 运行同一组 pytest。

| 生产文件 | 覆盖率 |
|---|---:|
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
签名改动后的 shared helper 文件同样使用 timid workaround 复跑，结果为 `86 stmts / 0 miss / 100%`。

### Pyright

```text
source .venv/bin/activate
pyright dayu/services/
```

结果：`0 errors, 0 warnings, 0 informations`。v4.4 方案 A 将输入类型扩宽为 `ModelConfigJsonValue | JsonObject`，保持函数体、返回类型、identity 行为和 rollback 5 个 public validator 签名/direct call 不变，消除了全部 5 个契约错误。

### Ruff

```text
source .venv/bin/activate
ruff check --select F,I001 <10 production files> <6 changed test files>
```

结果：`All checks passed!`

全规则按每个生产文件的 rule-code multiset 与 `HEAD` stdin 基线对比，无新增违规；五文件违规数下降（change `8→7`、rollback `7→6`、preapplication `15→13`、run approval `10→9`、promotion `9→8`），其余文件 rule-code multiset 不变。尚存项均是 HEAD 的 TRY004/FURB162/RUF010/UP035/ISC004 基线。

### 结构自审

```text
rg <eligible private definitions> <10 Cohort A files>
rg <deferred private definitions> <10 Cohort A files>
git diff --name-only -- <9 Cohort B files>
git diff --check
```

结果：eligible 私有定义为零（promotion defer `_serialize` 除外）；所有 defer 定义仍在；Cohort B diff 为零；`git diff --check` 通过。

## 双路 code re-review 闭环

- DeepSeek：`docs/reviews/code-rereview-slice-2a-20260807-deepseek.md`
- MiMo：`docs/reviews/code-rereview-slice-2a-20260807-mimo.md`

两路复审均为 **PASS**，确认原 changed-roles Medium 与 receipt-path Low
findings 全部 **CLOSED**，且无新增 findings。当前 open High/Medium/Low 均为
`0`，Slice 2A 已达到 accepted commit 门槛。

## 残余风险

- v4.4 `require_mapping` 类型 erratum 已经 MiMo `9/9 PASS` 并实施；后续 2B 仍需保持 identity 文件 direct call，仅计划明示的两个 copy 族使用 `dict(require_mapping(...))` adapter。
- DeepSeek/MiMo code review 接受的 changed-roles Medium 与 receipt-path Low 已按 Controller 裁决修复；当前等待双路 re-review。
- 全量 Ruff 仍有 HEAD 基线违规，已通过逐文件差分确认本 slice 无新增。
- 两个大模块的覆盖率刚好为 80%；此次补充的是真实 report/persistence/validator caller corpus，未为覆盖率引入生产 glue seam。
