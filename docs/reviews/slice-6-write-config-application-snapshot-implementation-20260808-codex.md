# Slice 6 C1+W12 配置应用与快照回调实现记录

- **日期**: 2026-08-08
- **基线**: `3363b6d gateflow: accept cli write architecture plan v4.9`
- **计划**: v4.9 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **范围**: Slice 6 C1+W12 / S6-CTRL-01 / S6-W12-CYCLE-01
- **状态**: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT

## 允许与实际修改范围

生产代码：

- `dayu/cli/commands/_write_config_application.py`（新建）
- `dayu/cli/commands/_write_snapshot_builder.py`（新建）
- `dayu/cli/commands/write.py`

直接测试：

- `tests/application/test_write_model_configuration_preapplication.py`
- `tests/engine/test_cli_running_config.py`

实现记录：

- `docs/reviews/slice-6-write-config-application-snapshot-implementation-20260808-codex.md`

测试入口和 application / engine 分层均未改变，因此 `tests/README.md` 无需更新；
本次只迁移 private CLI 实现，命令参数、退出码和用户调用方式未改变，因此根
`README.md` 与 `dayu/README.md` 也无需更新。

## v4.9 计划闭环

- v4.8 type-ownership Controller artifact：
  `docs/reviews/plan-slice-6-v4.8-argument-type-ownership-erratum-20260808-codex.md`。
- v4.9 W12 cycle Controller artifact：
  `docs/reviews/plan-slice-6-v4.9-w12-cycle-erratum-20260808-codex.md`。
- DeepSeek final plan review：
  `docs/reviews/plan-review-20260808-044555.md`，PASS，open H/M/L=0/0/0。
- MiMo final plan review：
  `docs/reviews/plan-review-20260808-044556.md`，PASS，open H/M/L=0/0/0。
- 实现遵循 v4.9 接受的单向依赖：builder 顶层 import application；application
  不 import builder，并在本模块 direct partial 闭环第一处 callback。

## Code review 初审与 Controller 裁决

- DeepSeek 初审：
  `docs/reviews/code-review-20260808-060001-deepseek.md`，PASS，报告两项 Low
  observation，open H/M/L=0/0/0。
- MiMo 初审：
  `docs/reviews/code-review-20260808-060002-mimo.md`，PASS，
  High/Medium/Low=0/0/0，open H/M/L=0/0/0。
- Controller 裁决：
  `docs/reviews/slice-6-code-review-adjudication-20260808-codex.md`。
- DS Low-01 `rejected-with-reason` / NON-DEFECT：三个
  `run_label: str = "configuration-application"` 是 accepted v4.9 item 1/2
  精确签名；计划外跨模块常量会扩大 scope，测试独立字面量则能避免生产与测试同错
  同过。
- DS Low-02 `rejected-with-reason` / NON-DEFECT：
  `_build_snapshot_for_args` 是 accepted v4.9 exact W12 factory 设计，不是
  compatibility glue。
- 两路初审均 PASS；Controller accepted findings=0，open H/M/L=0/0/0，无需
  code、test、README 或 plan fix，等待双路 re-review。

## 双路 Re-review 闭环

- DeepSeek re-review：
  `docs/reviews/code-review-20260808-060003-deepseek.md`，PASS，open
  High/Medium/Low=0/0/0。
- MiMo re-review：
  `docs/reviews/code-review-20260808-060004-mimo.md`，PASS，open
  High/Medium/Low=0/0/0。
- 两路均独立确认 DS Low-01/Low-02 的 `rejected-with-reason` 裁决成立；两条
  初审 Low 全部 CLOSED，无新增 finding，无需 code、test、README 或 plan fix。
- Slice 6 code review loop 已闭环，可进入 accepted slice commit。

## 实现摘要

### `_write_config_application.py`

- exact 迁移 `_build_fresh_application_routing_snapshot` 与
  `_run_write_model_configuration_application`。
- 两个函数的 `args` 均为 `argparse.Namespace`，执行选项均为
  `ExecutionOptions`；快照返回类型为
  `Mapping[str, ModelConfigJsonValue]`。
- `MODULE` 从 `_write_config_helpers` 单一真源导入，不复制本地常量。
- application runner 以同模块唯一一次
  `functools.partial(_build_fresh_application_routing_snapshot, ...)` 绑定
  `args`、`paths_config`、`execution_options`，不显式绑定 `run_label`，继续使用
  `configuration-application` 默认值。
- 原有参数读取、事务调用、异常到退出码映射、回执打印和状态映射保持不变。

### `_write_snapshot_builder.py`

- 新增模块级 `_build_snapshot_for_args` 与 `build_snapshot_builder`，签名精确使用
  `argparse.Namespace`、`WorkspaceConfig`、`ExecutionOptions` 和
  `Mapping[str, ModelConfigJsonValue]`。
- factory 使用 `functools.partial` 返回零参数 callback，并从
  `_write_config_application` 顶层导入即时快照 helper；不 import `write.py`。
- 两个函数和模块概览均使用完整中文 Args / Returns / Raises docstring。

### `write.py`

- 删除本地 `_build_fresh_application_routing_snapshot` 与
  `_run_write_model_configuration_application` 定义；正常顶层 import application
  runner，保留 `run_write_command` 的真实 global lookup。
- 其余四处 nested `_snapshot_builder` 全部替换为 `build_snapshot_builder`：
  rollback 与 manual-recovery application 使用默认 label；verification 与
  clearance 分别显式使用
  `configuration-manual-recovery-verification`、
  `configuration-manual-recovery-clearance`。
- 四个相关 runner 的 `execution_options` 从既有 `Any` 收窄为
  `ExecutionOptions`，并补齐完整中文 Args / Returns / Raises docstring。
- 未新增 `Any`、`object`、`cast`、`type: ignore`、`noqa`、compatibility
  re-export、lazy import 或 glue seam。

### 测试所有权与真实 callback

- application runner 的 direct unit tests、依赖 patch 和异常参数化目标迁至
  `_write_config_application` 真实 owner；dispatch / `run_write_command` 路径仍在
  `write` 的真实功能 binding 上 patch。
- factory 参数化回归覆盖默认与 verification label，真实调用零参数 callback，
  并断言返回同一 snapshot mapping。
- application transaction dependency stub 真实调用 runner 提供的 partial
  callback，断言参数、时区、mapping 和默认 label 行为。
- 即时快照 helper 通过真实控制流配合底层依赖 stub，覆盖依赖解析、preflight、
  logging 与 snapshot mapping 返回。
- engine direct runner test 改用真实 `ExecutionOptions()`，与收窄后的契约一致。

## 验证结果

### 功能测试

最终当前树完整 write caller corpus：

```text
pytest $(rg --files tests/application | rg '/test_write.*\.py$') \
  tests/engine/test_cli_running_config.py -q
```

结果：`809 passed in 13.20s`。

新增真实 callback / snapshot 聚焦测试：

```text
pytest tests/application/test_write_model_configuration_preapplication.py -q \
  -k 'fresh_application_routing_snapshot or snapshot_builder_forwards or application_runner_invokes'
```

结果：`4 passed, 148 deselected`。

收窄类型后的 engine direct runner 聚焦测试：

```text
pytest \
  tests/engine/test_cli_running_config.py::test_manual_recovery_verification_cli_exit_semantics \
  -q
```

结果：`5 passed`。

### Pyright 与 import smoke

```text
pyright dayu/cli/ \
  tests/application/test_write_model_configuration_preapplication.py \
  tests/application/test_write_cli_dispatch.py \
  tests/engine/test_cli_running_config.py
```

结果：`0 errors, 0 warnings, 0 informations`。

同进程 import / identity smoke 通过：

- `write._run_write_model_configuration_application` 与 application owner 为同一
  函数对象。
- builder 持有的 `_build_fresh_application_routing_snapshot` 与 application owner
  为同一函数对象。

### 精确覆盖率

使用独立 `COVERAGE_FILE`、`coverage run --timid --branch` 对最终当前树运行上述
809 个真实 caller tests；结果 `809 passed in 91.75s`。按 JSON report 的
statements / missing 精确计算：

| 文件 | statements | missing | covered | 精确覆盖率 | 状态 |
|---|---:|---:|---:|---:|---|
| `_write_config_application.py` | 49 | 2 | 47 | 95.918367346939% | PASS |
| `_write_snapshot_builder.py` | 12 | 0 | 12 | 100.000000000000% | PASS |
| `write.py` | 924 | 175 | 749 | 81.060606060606% | PASS |

三份修改生产文件均满足精确 `>=80%` 门槛。

### Ruff

检查范围：两个新模块、`write.py` 与两份修改测试。当前与 HEAD full-rule
finding-code multiset 完全相同：

```text
B009=14, BLE001=1, I001=2, PIE804=4,
RUF059=1, TRY004=3, UP035=1
```

所有 code count 增量均为 0；两个新模块没有 finding。F/I 当前仅报告 HEAD
既有两处 `I001`（`write.py:3` 与 engine test `:3`），F/I 新增为 0。

### 结构、类型禁令与 diff 审计

- `write.py` 两个旧定义：0；两个新模块目标定义：4。
- application + write 的 nested `_snapshot_builder` AST 定义：0。
- application → builder import：0；builder → application import：精确 1；
  builder → write import：0。
- application 的 `functools.partial`：精确 1 且无 `run_label` keyword。
- `write.py` 的 `build_snapshot_builder`：精确 4，label 顺序为默认、默认、
  verification、clearance。
- 新增 production / test diff 中 `Any`、`object`、`cast`、`type: ignore`、
  `noqa`：0。
- `git diff --check`：通过。
- README diff：0。

## Residual risk

1. `write.py` 和 engine test 仍有 HEAD 既有 Ruff findings；full-rule multiset
   与 HEAD 完全相同，本 Slice 不扩大清理范围。
2. 即时快照测试对外部 host / service 装配使用精确 dependency stub，但真实执行
   helper、runner、partial callback 与 mapping 返回路径；完整 write caller corpus
   提供其余回归保护。
3. 后续 Slice 7/8 会随 runner 迁移 factory import / call；本 Slice 只建立已接受
   的单向依赖与四处当前 owner 调用。
4. 未执行 `git add`、`git commit` 或 `git push`。
