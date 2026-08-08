# Slice 8 Challenger 与配置回滚命令实现记录

- **日期**: 2026-08-08
- **基线**: `fcf4602 gateflow: accept cli write execution manual recovery slice 7`
- **分支**: `codex/dual-model-research-mvp`
- **计划**: v5.0 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **范围**: Slice 8 C1 / S5-CTRL-01..04 / S6-W12-CYCLE-01 / S7 owner 约束
- **状态**: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT

## 允许与实际修改范围

生产代码：

- `dayu/cli/commands/_write_challenger.py`（新建）
- `dayu/cli/commands/_write_config_rollback.py`（新建）
- `dayu/cli/commands/write.py`

直接测试：

- `tests/application/test_write_challenger.py`
- `tests/application/test_write_cli_dispatch.py`
- `tests/application/test_write_model_configuration_preapplication.py`
- `tests/engine/test_cli_running_config.py`

实现记录：

- `docs/reviews/slice-8-write-challenger-rollback-implementation-20260808-codex.md`
- DeepSeek 初审：`docs/reviews/code-review-20260808-073322-deepseek.md`
- MiMo 初审：`docs/reviews/code-review-20260808-073323-mimo.md`
- Controller 裁决：
  `docs/reviews/slice-8-code-review-adjudication-20260808-codex.md`
- DeepSeek re-review：`docs/reviews/code-review-20260808-074700-deepseek.md`
- MiMo re-review：`docs/reviews/code-review-20260808-074701-mimo.md`

测试入口与 application / engine 分层职责未改变，因此 `tests/README.md` 无需
更新。本 Slice 只迁移 CLI 私有实现，命令、参数、退出码与用户调用方式不变，
根 `README.md` 与 `dayu/README.md` 同样无需更新。

## 双路初审与 Controller 裁决

- DeepSeek 初审：`docs/reviews/code-review-20260808-073322-deepseek.md`，PASS，
  报告 M01/L02/L03 三项迁移前 private helper 测试粒度建议。
- MiMo 初审：`docs/reviews/code-review-20260808-073323-mimo.md`，PASS，报告
  L-1 函数计数 observation。
- Controller 裁决：
  `docs/reviews/slice-8-code-review-adjudication-20260808-codex.md`。
- DS M01/L02/L03 均为 exact AST owner migration 之外的既有测试粒度建议，
  `rejected-with-reason / CLOSED`；812 tests 与三个目标文件精确 coverage 门槛均
  通过，plan/AGENTS 不要求每个 private helper direct test。
- MiMo L-1 为 measurement error：Python AST 实测 `_write_challenger.py` exact
  13，rollback exact 1，总迁移 14；MiMo 自身 §1 的 `14/14 PASS` 也与 finding
  冲突。因此该项 `rejected-with-reason / CLOSED`。
- Controller accepted/deferred/needs-more-evidence 均为 0，open H/M/L=`0/0/0`；
  无需修改 code、tests、README 或 plan，进入双路 re-review。

## 双路 Re-review 闭环

- DeepSeek re-review：`docs/reviews/code-review-20260808-074700-deepseek.md`，
  PASS，open H/M/L=`0/0/0`。
- MiMo re-review：`docs/reviews/code-review-20260808-074701-mimo.md`，PASS，
  open H/M/L=`0/0/0`。
- 两路均独立确认 DS M01/L02/L03 是 HEAD 既有 private-helper 测试粒度建议，
  Controller 的 rejected-with-reason 裁决成立；三项全部 CLOSED。
- 两路均以 Python AST 确认 `_write_challenger.py` exact 13、rollback exact 1，
  MiMo 初审 L-1 为 measurement error，现已 CLOSED。
- 初审四项 observations 全部 CLOSED，无新 finding，无需继续修改 code、tests、
  README 或 plan；Slice 8 已可进入 accepted commit。

## 实现摘要

### `_write_challenger.py`

- 按 accepted v5.0 顺序 exact 迁移 13 个 Challenger 函数；
  `_challenger_requested` 继续由 Slice 5 的 `_write_params_validation.py` 持有，
  未复制或反向导入。
- 迁入 `_CHALLENGER_COMPARISON_FILE` 与真实功能依赖；日志通过
  `_write_config_helpers.MODULE` 单一真源，不本地复制常量，也不 import
  `write.py`。
- 模块概览及 13 个函数均补齐中文 Args / Returns / Raises docstring。
- HEAD 的 `_manifest_has_usable_company_facets` 含一处 function-local
  `research_template_routing` domain import。Controller 裁决按 exact AST 保留；
  owner / compatibility lazy import 新增为 0，compatibility wrapper/glue 为 0。

### `_write_config_rollback.py`

- exact 迁移 `_run_write_model_configuration_rollback`，退出码、异常分类、日志、
  报告输出与调用顺序不变。
- 连同 `build_snapshot_builder` 的默认-label 功能 import 与一次 factory call
  一并迁移；不显式传 `run_label`，不恢复 nested callback。
- 从 `_write_config_helpers` import `MODULE`，依赖方向保持
  `_write_config_rollback → _write_snapshot_builder → _write_config_application`。
- 模块概览与函数使用完整中文 Args / Returns / Raises docstring。

### `write.py`

- 删除 13 个 Challenger 与 1 个 rollback 旧定义，当前只保留
  `_materialize_research_after_write`、`run_write_command` 两个本地函数。
- surviving `run_write_command` 的 AST 真实 global caller 精确要求 10 个
  Challenger binding 加 1 个 rollback binding。最初口头盘点曾误称
  “11 Challenger + rollback”；二次 AST 审计纠正为下列 10+1，未为匹配旧计数
  添加 compatibility binding：
  `_assert_challenger_run_output_boundaries`、`_build_auto_bootstrap_args`、
  `_build_challenger_run_plan_from_args`、`_build_challenger_write_config`、
  `_needs_auto_research_bootstrap`、
  `_persist_challenger_run_authorization_after_preflight`、
  `_preflight_champion_and_challenger`、
  `_run_champion_challenger_experiment`、
  `_verify_and_consume_challenger_run_approval_before_host`、
  `_verify_challenger_preflight_approval_before_host`，以及
  `_run_write_model_configuration_rollback`。
- 三个 Challenger 内部 helper `_challenger_preflight_cli_args`、
  `_load_current_challenger_proposal`、`_manifest_has_usable_company_facets`
  没有 surviving `write.py` caller，因此不建立兼容绑定。
- 迁出独占依赖后，`write.py` 不再 import snapshot factory；`MODULE` 因本文件
  真实日志 caller 继续作为正常功能 import 可见。

### 类型与 AST 等价

- 14 个迁移函数逐一移除 docstring 后与 HEAD function AST 相同：14/14 PASS。
- `Any` semantic annotation/local uses 为 HEAD 7、当前 7，未新增签名、局部
  usage 或逃逸。新 owner 为承载既有签名增加一条必要 `typing.Any` import，
  import 数 1→2；Controller 明确该 ownership import 不属于类型扩散。
- `object`、`cast`、`type: ignore`、`noqa` 均无新增；没有 wrapper、同步 seam
  或 suppressions。

### 测试 ownership

- Challenger 与 rollback 函数的直接 import、直接 runner 依赖 patch 均迁到真实
  owner；自动研究引导 helper 的直接测试也从 Challenger owner import。
- `run_write_command`、dispatch priority 与 pre-host gate characterization 继续 patch
  `write.<symbol>` 真实功能 binding，没有 blanket 迁移。
- 新增 10 个 Challenger + 1 个 rollback functional-binding identity 回归；既有
  direct-owner 与 dispatch-owner 真实调用回归继续覆盖两个边界。

## 验证结果

### 功能测试

首轮 owner / dispatch 聚焦：

```text
pytest tests/application/test_write_challenger.py \
  tests/application/test_write_model_configuration_preapplication.py \
  tests/application/test_write_cli_dispatch.py \
  tests/engine/test_cli_running_config.py -q
```

结果：`659 passed in 12.92s`。

计划要求的全部 application `test_write*.py` 与 engine corpus，同时作为 coverage
真实 caller corpus：

```text
COVERAGE_FILE=.coverage.slice8 pytest \
  $(rg --files tests/application | rg '/test_write.*\.py$' | sort) \
  tests/engine/test_cli_running_config.py -q \
  --cov=dayu.cli.commands._write_challenger \
  --cov=dayu.cli.commands._write_config_rollback \
  --cov=dayu.cli.commands.write \
  --cov-report=json:.coverage-slice8.json --cov-report=
```

coverage 运行结果：`812 passed, 15 warnings in 23.62s`；最终非 coverage
复跑结果：`812 passed in 12.77s`。warnings 均为既有 sqlite
`ResourceWarning`，没有测试失败。

### Pyright

```text
pyright --pythonpath .venv/bin/python dayu/cli/ \
  tests/application/test_write_challenger.py \
  tests/application/test_write_cli_dispatch.py \
  tests/application/test_write_model_configuration_preapplication.py \
  tests/engine/test_cli_running_config.py
```

结果：`0 errors, 0 warnings, 0 informations`。显式 `--pythonpath` 用于让 pyright
解析当前 `.venv` 已安装的 `prompt_toolkit`；不带该参数时全 CLI 扫描会产生两条
环境解析型 `reportMissingImports`，目标文件与本 Slice 类型实现本身无错误。

### 精确 statement coverage

| 文件 | statements | covered | missing | 精确覆盖率 | 状态 |
|---|---:|---:|---:|---:|---|
| `_write_challenger.py` | 200 | 166 | 34 | 83.000000% | PASS |
| `_write_config_rollback.py` | 34 | 31 | 3 | 91.176471% | PASS |
| `write.py` | 189 | 157 | 32 | 83.068783% | PASS |

三份修改生产文件均满足精确 `>=80%` 门槛；未使用终端表格四舍五入值作判定。
覆盖率运行后仅增加 docstring 说明与恢复 engine HEAD import 顺序，不改变 executable
statement 或 caller corpus，因此上述 JSON 结果仍对应最终可执行行为。

### Ruff

```text
ruff check --select F,I \
  dayu/cli/commands/_write_challenger.py \
  dayu/cli/commands/_write_config_rollback.py \
  dayu/cli/commands/write.py \
  tests/application/test_write_challenger.py \
  tests/application/test_write_cli_dispatch.py \
  tests/application/test_write_model_configuration_preapplication.py \
  tests/engine/test_cli_running_config.py --exit-zero
```

结果：只保留 engine test 的 HEAD 既有 `I001`；无新增 F/I finding。

同一文件集合的 HEAD full-rule finding-code multiset 比较：

```text
HEAD:          B009=14, I001=1, PIE804=4, RUF059=1, TRY004=3, UP035=1
CURRENT:       B009=14, I001=1, PIE804=4, RUF059=1, TRY004=3, UP035=1
positive delta: {}
```

两个新 owner 自身无 Ruff finding；没有新增 full-rule code。

### 结构、factory、identity 与依赖门禁

- Challenger 顶层定义 exact 13，rollback 顶层定义 exact 1，`write.py` 本地定义
  exact 2；14 个旧定义在 `write.py` 中为 0。
- `write.py` 从 Challenger import exact 10、从 rollback import exact 1；同进程
  import smoke 与 10+1 identity 均 PASS。
- rollback 的 `build_snapshot_builder` import exact 1、call exact 1；不显式绑定
  label。Challenger 与 `write.py` 中该 factory import/call 均为 0。
- 两个新 owner 对 `write.py` 反向 import 为 0，nested function 定义为 0，
  compatibility/lazy owner import 为 0；既有 domain local import exact 1 preserved。
- `_write_config_helpers.MODULE` 在两个新 owner 中各正常 import exact 1；没有本地
  `MODULE =`。
- `git diff --check`：PASS。
- README diff：0。

## Residual risk

1. 全量测试仍报告既有 sqlite `ResourceWarning`，但 812 个测试全部通过；本 Slice
   不扩大到测试基础设施资源生命周期清理。
2. engine test 保留 HEAD 既有 `I001`；full-rule finding-code multiset 无正增量，
   两个新 owner 无 lint suppression。
3. HEAD 既有 domain local import 按 exact AST 保留；它不是 owner/compat lazy seam，
   且 import smoke 与单向依赖检查均通过。
4. 未执行 `git add`、`git commit`、`git push` 或 `git stash`。
