# Slice 5 C1 write config / params 实现记录

- **日期**: 2026-08-08
- **基线**: `9041d7d gateflow: accept cli write architecture plan v4.7`
- **计划**: v4.7 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **范围**: Slice 5 C1 / S5-CTRL-01..04
- **状态**: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT

## v4.7 计划闭环

- Controller erratum：
  `docs/reviews/plan-slice-5-v4.7-private-binding-erratum-20260808-codex.md`。
- DeepSeek final plan review：
  `docs/reviews/plan-review-20260808-024405.md`，PASS，open H/M/L=0。
- MiMo 初次 re-review：
  `docs/reviews/plan-review-20260808-024406.md`；三项 Low 已逐项裁决。
- MiMo corrective re-review：
  `docs/reviews/plan-review-20260808-025255.md`，PASS，open H/M/L=0。
- 初审三项 finding 与 MiMo re-review 三项 observation 全部 CLOSED；v4.7 明确
  `write.py` 只保留六个真实功能 private binding，两个无 caller validator 不做
  compatibility re-export。

## Code review 初审与 Controller 裁决

- DS 初审：`docs/reviews/code-review-20260808-033848.md`，PASS，报告
  M1/L1/L2。
- MiMo 初审：`docs/reviews/code-review-20260808-033849.md`，PASS，报告
  M1/L1/L2。
- Controller 裁决：
  `docs/reviews/slice-5-code-review-adjudication-20260808-codex.md`。
- 六项 observation 均已 `rejected-with-reason`：双 owner 与 exact/docstring 是
  accepted v4.7 contract；异常吞噬、六处 `getattr` 与大型 validator 是 exact 迁移
  保留的既有行为/规模；32/4 coverage 已超过精确门槛且计划没有逐行 missing 说明
  要求。
- 两路初审均 PASS；Controller open High/Medium/Low=0/0/0，无需 code、test、
  README 或 plan fix，等待双路 re-review 闭环。

## 双路 Re-review 闭环

- DS re-review：`docs/reviews/code-review-20260808-034952.md`，PASS，open
  High/Medium/Low=0/0/0。
- MiMo re-review：`docs/reviews/code-review-20260808-034953.md`，PASS，open
  High/Medium/Low=0/0/0。
- 两路均确认 Controller 六项裁决有 accepted v4.7 与源码证据支持；六项 finding
  全部 CLOSED，未发现新的 blocking defect，无需 code、test、README 或 plan fix。
- Slice 5 code review loop 已闭环，可进入 accepted slice commit。

## 修改范围

生产代码：

- `dayu/cli/commands/_write_config_helpers.py`
- `dayu/cli/commands/_write_params_validation.py`
- `dayu/cli/commands/write.py`

直接测试：

- `tests/application/test_write_cli_dispatch.py`
- `tests/application/test_write_model_configuration_preapplication.py`
- `tests/engine/test_cli_running_config.py`

文档：

- `docs/reviews/slice-5-write-config-params-implementation-20260808-codex.md`

测试入口与测试分层未改变，因此 `tests/README.md` 无需更新；CLI public API、参数与
用户用法未改变，因此根 `README.md` 无需更新。

## 实现摘要

### `_write_config_helpers.py`

- 单一定义 `MODULE = "APP.WRITE"`。
- 从 `dayu.cli.dependency_setup` 功能性 import `WriteCliConfig` 与
  `setup_model_name`。
- exact 迁移四个函数：
  `_resolve_write_model_override_name`、
  `_resolve_write_company_name`、
  `_build_write_run_config`、
  `_log_write_preflight_result`。

### `_write_params_validation.py`

- exact 迁移 `_challenger_requested` 与三个 validator：
  `_validate_challenger_run_plan_args`、
  `_validate_live_smoke_plan_args`、
  `_validate_research_materialization_args`。
- `_validate_research_materialization_args` 继续从定义模块 globals 直接调用
  `_challenger_requested`。
- 本模块不 import `write.py` 或未来 `_write_challenger.py`，无反向依赖。

### `write.py`

- 正常顶层 import `MODULE` 与六个真实功能 private symbol：config helper 四个、
  `_challenger_requested`、`_validate_research_materialization_args`。
- 不 import/re-export `_validate_challenger_run_plan_args` 与
  `_validate_live_smoke_plan_args`；后者的 engine direct import 已迁至真实 owner。
- 删除本地 `MODULE`、`setup_model_name` dependency import 与八个旧定义。
- `run_write_command` 的三个 `_challenger_requested` global call site 保持原位。
- 两个新模块合计 exact 八个定义；全部具有完整中文 Args / Returns / Raises
  docstring，未新增 `Any`、`object`、`cast`、`type: ignore` 或 glue seam。

### 测试边界

- engine test 中 13 处 `dayu.cli.commands.write.setup_model_name` patch 全部迁至
  `dayu.cli.commands._write_config_helpers.setup_model_name`；旧 owner 0、新 owner
  13。
- engine live-smoke validator direct import 迁至
  `dayu.cli.commands._write_params_validation`。
- 约 line 5919 的 research validator patch 与约 line 5934 的
  `write._challenger_requested` patch 均保持其真实 owner 语义。
- dispatch identity 回归精确锁定六个 `write.<private>` 功能 binding。
- 双 owner 回归分别证明：patch `write._challenger_requested` 控制真实
  `run_write_command`；patch params owner 控制真实 research validator 内部路径。
- 覆盖率回归采用参数化真实 configuration runner success/error/root/cancel 路径；
  最小化后未保留冗余 case，未增加生产 seam、pragma、noqa 或 dummy 引用。

## 验证结果

### 功能测试

```text
pytest $(rg --files tests/application | rg '/test_write.*\.py$') \
  tests/engine/test_cli_running_config.py -q
```

结果：`805 passed in 12.58s`。

最终最小 runner corpus 聚焦复跑：

```text
pytest \
  tests/application/test_write_model_configuration_preapplication.py::test_cli_configuration_runners_preserve_success_exit_contracts \
  tests/application/test_write_model_configuration_preapplication.py::test_cli_configuration_runners_map_errors_to_stable_exit_codes \
  tests/application/test_write_model_configuration_preapplication.py::test_cli_manual_recovery_runners_require_config_root \
  tests/application/test_write_model_configuration_preapplication.py::test_cli_write_stage_maps_cancellation_to_stable_exit_code \
  -q
```

结果：`13 passed in 1.05s`。

### Pyright 与 import/cycle

```text
pyright dayu/cli/ \
  tests/application/test_write_cli_dispatch.py \
  tests/application/test_write_model_configuration_preapplication.py \
  tests/engine/test_cli_running_config.py
```

结果：`0 errors, 0 warnings, 0 informations`。

从 config helper、params validator 与 `write.run_write_command` 同进程导入的 smoke
通过；两个新模块反向 import `write.py` 为 0，未形成 import cycle。

### 精确覆盖率

Python 3.13 环境按仓库既有 workaround 预载
`tests.application.conftest`，清除三个目标模块缓存后，以独立 data file、
`Coverage(..., timid=True, branch=True)` 运行真实 caller。完整 804-test corpus
结果为 `804 passed`；随后对新增 case 所属 10-row 参数化函数增量运行，结果为
`10 passed`（其中 9 条与完整 corpus 重合、1 条为新增 case）。Coverage data
并集因此精确对应当前 805 个 unique tests；按 `analysis2` statements/missing
计算精确 statement coverage：

| 文件 | statements | missing | covered | 精确覆盖率 | 状态 |
|---|---:|---:|---:|---:|---|
| `_write_config_helpers.py` | 32 | 4 | 28 | 87.5000000000% | PASS |
| `_write_params_validation.py` | 396 | 23 | 373 | 94.1919191919% | PASS |
| `write.py` | 962 | 192 | 770 | 80.0415800416% | PASS |

三份修改生产文件均满足精确 `>=80%` 门槛。

### Ruff

```text
ruff check --select F,I \
  dayu/cli/commands/_write_config_helpers.py \
  dayu/cli/commands/_write_params_validation.py \
  dayu/cli/commands/write.py \
  tests/application/test_write_cli_dispatch.py \
  tests/application/test_write_model_configuration_preapplication.py \
  tests/engine/test_cli_running_config.py
```

当前仅报告两处 HEAD 既有 `I001`（`write.py:3`、engine test `:3`），F/I
新增为 0。

HEAD full-rule finding-code multiset：
`B009=14, BLE001=2, I001=2, PIE804=4, RUF059=1, TRY004=3, UP035=2`。
当前 multiset：
`B009=14, BLE001=2, I001=2, PIE804=4, RUF059=1, TRY004=3, UP035=1`。
所有 code count 增量均为 0；唯一差异是迁移真实依赖后 `UP035` 从 2 降为 1。

### 结构与 diff 审计

- 旧 `write.setup_model_name` patch：0；新 config-helper owner patch：13。
- `MODULE = "APP.WRITE"`：1，且仅位于 `_write_config_helpers.py`。
- `write.py` 八个旧定义：0；两个新模块目标定义：8。
- `write.py` 两个禁止 compatibility validator binding：0。
- dispatch 功能 identity：6；两个新模块反向 import `write.py`：0。
- engine research / challenger owner patch 仍位于约 line 5919 / 5934。
- `git diff --check`：通过。
- README diff：0。

## Residual risk

1. 修改路径仍保留 HEAD 已有 Ruff findings，但 full-rule code multiset 无正增量，
   F/I 亦无新增；本 Slice 不扩大清理范围。
2. 覆盖率使用 Python 3.13 timid tracer workaround；这是测量环境处理，不改变生产
   行为，三个文件精确门槛均已通过。
3. Slice 6-8 的后续模块拆分不在本 Slice 范围。
4. 未执行 `git add`、`git commit` 或 `git push`。
