# Slice 7 写作执行与人工恢复命令实现记录

- **日期**: 2026-08-08
- **基线**: `5d1c3f9 gateflow: accept cli write architecture plan v5.0`
- **分支**: `codex/dual-model-research-mvp`
- **计划**: v5.0 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **范围**: Slice 7 C1 / S7-CTRL-01..04
- **状态**: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT

## 允许与实际修改范围

生产代码：

- `dayu/cli/commands/_write_execution.py`（新建）
- `dayu/cli/commands/_write_manual_recovery.py`（新建）
- `dayu/cli/commands/write.py`

直接测试：

- `tests/application/test_write_cli_dispatch.py`
- `tests/application/test_write_model_configuration_preapplication.py`
- `tests/engine/test_cli_running_config.py`

实现记录：

- `docs/reviews/slice-7-write-execution-manual-recovery-implementation-20260808-codex.md`
- `docs/reviews/slice-7-code-review-adjudication-20260808-codex.md`
- `docs/reviews/slice-7-write-execution-manual-recovery-fix-20260808-codex.md`

测试入口与 application / engine 分层未改变，因此 `tests/README.md` 无需更新。
本 Slice 只迁移 CLI 私有实现，命令、参数、退出码和用户调用方式均未改变，因此根
`README.md` 与 `dayu/README.md` 也无需更新。

## v5.0 计划闭环

- Controller plan erratum：
  `docs/reviews/plan-slice-7-v5.0-runner-ownership-erratum-20260808-codex.md`。
- DeepSeek final plan re-review：
  `docs/reviews/plan-review-20260808-061005-deepseek.md`，PASS，open H/M/L=0/0/0。
- MiMo final plan re-review：
  `docs/reviews/plan-review-20260808-061006-mimo.md`，PASS，open H/M/L=0/0/0。
- 实现遵循 S7-CTRL-01..04：manual exact 14 runner + 1 Phase C gate，execution
  exact 2；直接定义测试与 dispatch functional-binding 测试分别使用真实 owner。

## 双路初审与 Controller 裁决

- DeepSeek 初审：`docs/reviews/code-review-20260808-065515-deepseek.md`，PASS，
  报告 H-1/M-1/L-1/L-2。
- MiMo 初审：`docs/reviews/code-review-20260808-065516-mimo.md`，PASS，open
  H/M/L=0/1/0，报告 M-01。
- Controller 裁决：
  `docs/reviews/slice-7-code-review-adjudication-20260808-codex.md`。
- Fix artifact：
  `docs/reviews/slice-7-write-execution-manual-recovery-fix-20260808-codex.md`。
- DS H-1 与 MiMo M-01 是同一 docstring defect，ACCEPT/FIXED；DS M-1
  import-block 噪音 ACCEPT/FIXED。
- DS L-1 为 AST 等价前提下的纯换行 observation，REJECT/NON-DEFECT；DS L-2
  会给私有模块扩大 star-import surface，REJECT/NON-DEFECT/OUT-OF-SCOPE。
- 外部 observation 共 5 项，归并为 4 个唯一问题；接受并修复 2 项、
  rejected-with-reason 2 项。修后 Controller open H/M/L=0/0/0，随后进入双路
  re-review。

## 双路 Re-review 闭环

- DeepSeek re-review：`docs/reviews/code-review-20260808-070609-deepseek.md`，
  PASS，open H/M/L=0/0/0。
- MiMo re-review：`docs/reviews/code-review-20260808-070610-mimo.md`，PASS，
  open H/M/L=0/0/0。
- 两路均确认初审 5 项 observation 全部 CLOSED：DS H-1 / MiMo M-01 与
  DS M-1 已修复；DS L-1/L-2 的 rejected-with-reason 裁决成立。
- 无新 finding，无需继续修改 code、tests、README 或 plan；Slice 7 已可进入
  accepted commit。

## 实现摘要

### `_write_execution.py`

- 从基线 `write.py` exact 迁移 `_run_write_stage` 与 `_run_write_preflight`，签名、
  控制流、日志、异常到退出码映射和 I/O 顺序不变。
- 从 `_write_config_helpers` 导入 `MODULE` 与 `_log_write_preflight_result`，不复制
  常量，不反向 import `write.py`。
- 模块概览及两个函数均补齐完整中文 Args / Returns / Raises docstring。

### `_write_manual_recovery.py`

- 按基线源码顺序 exact 迁移 14 个
  `_run_write_model_configuration_manual_recovery_*` runner 与
  `_check_write_model_configuration_manual_recovery_gate`，合计 exact 15。
- application / verification / clearance 三个 runner 连同
  `build_snapshot_builder` import 与 factory call 一并迁移；label 精确保持默认、
  `configuration-manual-recovery-verification`、
  `configuration-manual-recovery-clearance`。
- 从 `_write_config_helpers` 导入单一真源 `MODULE`；依赖保持
  `_write_manual_recovery → _write_snapshot_builder → _write_config_application`
  单向。
- 模块概览及 15 个函数均补齐完整中文 Args / Returns / Raises docstring。

### `write.py`

- 删除上述 17 个旧定义，并从两个真实 owner 正常顶层 import exact 17 个功能
  binding；`run_write_command`、Phase A/C dispatch 和 Challenger helper 继续通过
  这些真实 global binding 调用。
- 删除迁出函数独占的 imports；没有 compatibility re-export、wrapper、lazy
  import 或 glue seam。
- manual 三处 factory 迁出后，只为 rollback runner 保留一处默认-label
  `build_snapshot_builder` 调用。

### 测试 ownership 与差分保护

- execution / manual runner 的直接调用及其内部依赖 patch 已迁至真实定义模块。
- `run_write_command`、Phase A/C dispatch 与 Challenger helper 的
  characterization 继续 patch `write.<symbol>` 功能 binding，没有 blanket 迁移。
- 新增 exact 17 identity 回归，逐项断言 `write` binding 与真实 owner 函数对象
  相同。
- 新增真实 preflight 依赖错误与快照门禁阻断回归，分别锁定退出码 2 与 4；该
  回归同时把 `_write_execution.py` 精确 statement coverage 提升到门槛以上。
- 迁移函数与 HEAD 的 AST 在移除 docstring 后逐项相同：17/17 PASS。
- 新模块及新增测试未引入 `Any`、`object`、`cast`、`type: ignore`、`noqa`。

## 验证结果

### 功能测试

聚焦 owner / dispatch corpus：

```text
pytest tests/application/test_write_cli_dispatch.py \
  tests/application/test_write_model_configuration_preapplication.py \
  tests/engine/test_cli_running_config.py -q
```

结果：`644 passed`。

计划要求的全部 application `test_write*.py` 与 engine write corpus：

```text
pytest $(rg --files tests/application | rg '/test_write.*\.py$' | sort) \
  tests/engine/test_cli_running_config.py -q
```

实现阶段结果：`811 passed in 12.91s`；coverage 运行同一 corpus再次得到
`811 passed in 22.91s`。review fix 后重跑结果：`811 passed in 12.90s`。

### Pyright

```text
pyright dayu/cli/ \
  tests/application/test_write_cli_dispatch.py \
  tests/application/test_write_model_configuration_preapplication.py \
  tests/engine/test_cli_running_config.py
```

结果：`0 errors, 0 warnings, 0 informations`。

### 精确 statement coverage

使用独立 `COVERAGE_FILE` 和 pytest-cov JSON report 对最终 811 个真实 caller tests
计算：

| 文件 | statements | covered | missing | 精确覆盖率 | 状态 |
|---|---:|---:|---:|---:|---|
| `_write_execution.py` | 142 | 116 | 26 | 81.690141% | PASS |
| `_write_manual_recovery.py` | 400 | 327 | 73 | 81.750000% | PASS |
| `write.py` | 406 | 337 | 69 | 83.004926% | PASS |

三份修改生产文件均满足精确 `>=80%` 门槛；未接受终端表格的四舍五入结果。
review fix 仅修改生产 docstring 与测试 import 顺序，没有改变 executable
statement 或 caller corpus，因此无需重跑 coverage，沿用上述最终精确结果。

### Ruff

```text
ruff check --exit-zero --select F,I \
  dayu/cli/commands/_write_execution.py \
  dayu/cli/commands/_write_manual_recovery.py \
  dayu/cli/commands/write.py \
  tests/application/test_write_cli_dispatch.py \
  tests/application/test_write_model_configuration_preapplication.py \
  tests/engine/test_cli_running_config.py
```

修后结果：只报告 engine test 一处 HEAD 既有 `I001`；无新增 F/I finding。

同一文件集合的 HEAD full-rule finding-code multiset 比较：

```text
CURRENT: B009=14, BLE001=1, I001=1, PIE804=4, RUF059=1, TRY004=3, UP035=1
HEAD:    B009=14, BLE001=1, I001=2, PIE804=4, RUF059=1, TRY004=3, UP035=1
positive delta: {}
```

当前没有新增 full-rule finding。按初审接受项恢复 HEAD import 顺序后，engine test
保留一处既有 `I001`；另一个 HEAD `I001` 随生产 import 迁移自然消除。

### 结构、identity、依赖与 diff 门禁

- `_write_execution.py` 目标顶层定义 exact 2；`_write_manual_recovery.py` 目标
  顶层定义 exact 15；`write.py` 旧定义 exact 0。
- `write.py` 从 execution owner import exact 2，从 manual owner import exact 15；
  同进程 import smoke 与 exact 17 identity 均 PASS。
- manual `build_snapshot_builder` import exact 1、call exact 3；label 为默认、
  verification、clearance。`write.py` factory call exact 1 且使用默认 label。
- manual → snapshot import exact 1，snapshot → config-application import exact 1；
  manual → write/application、snapshot → manual/write、application → manual 均为 0。
- manual、write、snapshot、config-application 的 nested `_snapshot_builder` AST
  定义合计为 0；同进程 import smoke PASS，无 cycle。
- `git diff --check`：PASS。
- README diff：0。

## Residual risk

1. 最终测试运行仍出现既有 sqlite `ResourceWarning`，但 811 个测试全部通过；本
   Slice 不扩大到测试基础设施资源生命周期清理。
2. 当前 full-rule Ruff 仍有 HEAD 既有 finding；finding-code multiset 无正增量，
   两个新 owner 无逃逸性 lint suppression。
3. 后续 Slice 8 会迁移 Challenger 与 rollback owner；本 Slice 仅保留当前真实
   functional imports 与 rollback 的一处 snapshot factory。
4. 未执行 `git add`、`git commit`、`git push` 或 `git stash`。
