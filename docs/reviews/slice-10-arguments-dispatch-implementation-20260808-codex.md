# Slice 10 参数类型与 Research Template 分派实现记录

- **日期**: 2026-08-08
- **基线**: `3084841 gateflow: accept cli write architecture plan v5.4`
- **分支**: `codex/dual-model-research-mvp`
- **计划**: v5.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **范围**: Slice 10 / S10-CTRL-01..06 / C4-01
- **状态**: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT

## 允许与实际修改范围

生产代码：

- `dayu/cli/arguments.py`（新建）
- `dayu/cli/arg_parsing.py`
- `dayu/cli/commands/research_template.py`
- `dayu/cli/commands/write.py`
- `dayu/cli/commands/_write_config_application.py`

`dayu/cli/commands/_write_snapshot_builder.py` 在实施中曾用于验证传播边界，最终已
精确恢复 HEAD，当前对基线 diff 为 0，因此不属于实际修改生产文件。

直接测试与测试索引：

- `tests/cli/test_research_template_command.py`
- `tests/cli/test_research_template_definitions.py`
- `tests/application/test_write_cli_dispatch.py`
- `tests/application/test_write_challenger.py`
- `tests/application/test_write_model_configuration_preapplication.py`
- `tests/engine/test_cli_running_config.py`
- `tests/README.md`

根 `README.md` 与 `dayu/README.md` 无需修改：本 Slice 没有改变命令、参数、退出码
或用户调用方式。`tests/README.md` 已同步 research-template 从线性 if-chain 到
exact39 mapping 的当前测试入口与新增行为矩阵。

## v5.4 计划闭环

- accepted plan commit：`3084841 gateflow: accept cli write architecture plan v5.4`。
- v5.4 DeepSeek final plan re-review：
  `docs/reviews/plan-review-20260808-113000-deepseek.md`，PASS，open H/M/L=`0/0/0`。
- v5.4 MiMo final plan re-review：
  `docs/reviews/plan-review-20260808-113001-mimo.md`，PASS，open H/M/L=`0/0/0`。
- 实现遵循 S10-CTRL-06 的真实 consumer 边界：exact42 个 CLI 入口/runner args
  传播为 `DayuCliArguments`，三个 snapshot-chain helper 保持
  `argparse.Namespace`，`parse_arguments` 返回类型另计 exact1。

## 实现摘要

### 参数 owner 与真实运行时类型

- 新建仅依赖标准库的 `dayu/cli/arguments.py`，先定义 consumer 最小契约
  `ResearchTemplateDispatchArguments(Protocol)`，再定义 producer
  `DayuCliArguments(argparse.Namespace)`。
- 两个类型各有 exact1 个无默认值字段
  `research_template_action: str`；Dayu 不继承 Protocol、无自定义 `__init__`，两者
  通过 structural subtyping 对接。
- `parse_arguments() -> DayuCliArguments` 通过
  `parser.parse_args(namespace=DayuCliArguments())` 构造真实子类实例；没有使用
  alias、wrapper、adapter、`cast`、`type: ignore` 或 glue seam。

### exact42 + 1 传播边界

- `research_template.py` 的 entry 1 + runners 39、`write.py` entry 1、
  `_write_config_application.py` application runner 1，合计 exact42 个 `args`
  签名使用 `DayuCliArguments`。
- `_build_fresh_application_routing_snapshot`、`_build_snapshot_for_args`、
  `build_snapshot_builder` 精确保持 `argparse.Namespace`。snapshot-builder 最终对
  HEAD 零 diff，且 `DayuCliArguments` import/reference 为 0。
- rollback runner 与 manual recovery 14 个 runner 均保持
  `argparse.Namespace`；Phase C gate 无 `args` 参数。没有把具体 CLI 类型扩散到
  下层基础设施或其他 runner。

### Research Template selector 与 mapping

- 新增 `_resolve_research_template_action`，精确使用
  `str(getattr(args, "research_template_action", "") or "").strip().lower()`，只保留
  HEAD 对缺字段、`None`、非字符串和首尾空白的 defensive 语义。
- 新增
  `Final[Mapping[str, Callable[[DayuCliArguments], int]]]` 分派表，按 accepted 清单
  exact39 个 key、exact39 个不同 runner binding。
- `run_research_template_command` 保持 `setup_loglevel` 先行；mapping lookup、未知
  action 分支与 runner 调用均位于同一个 `try`。未知 action 无 stdout/stderr 且
  返回 1；`FileNotFoundError`、`FileExistsError`、`ValueError` 精确写入
  `research-template error: {exc}` 并返回 1；其他异常继续传播。
- 39 个 runner 的可执行 AST 与 HEAD 对比差异为 0；仅按计划更新参数注解并补齐
  真实中文 Args / Returns / Raises docstring。

### 测试 ownership

- 六个 direct-owner 测试文件中，只有直接调用 exact42 窄目标的变量/fixture 改用
  真实 `DayuCliArguments`；直接调用三个宽 snapshot helper 及表外 runner 的 fixture
  继续使用 `argparse.Namespace`，没有 blanket 迁移。
- `tests/application/test_write_cli_dispatch.py` 新增 exact39 mapping key/function
  identity 矩阵、真实 parser runtime identity、未知 action 静默返回、三类 caught
  exception 精确 stderr 与 selector 缺字段/`None`/非字符串 corpus。
- `tests/cli/test_research_template_command.py` 补充真实 list 文本输出 caller 回归，
  以行为断言覆盖 mapping entry 与 runner 正常路径；未增加生产 seam 或 pragma。

## 双路初审与 Controller 裁决

- DeepSeek 初审：`docs/reviews/code-review-20260808-120340.md`，PASS，open
  High/Medium/Low=`0/0/0`，没有 finding。
- MiMo 初审：`docs/reviews/code-review-20260808-120341.md`，PASS，结论段误将三项
  non-defect design observations 计为 open Low=`3`，正文另列一项 Info。
- Controller 裁决：
  `docs/reviews/slice-10-code-review-adjudication-20260808-codex.md`。
- MiMo F-01/F-02/F-03 均为 accepted v5.4 精确字段 ownership、bounded defensive
  selector 与 AGENTS 完整中文 docstring 的设计结果，全部
  `REJECTED-WITH-REASON / NON-DEFECT / CLOSED`；F-04 Info 为 consumer 最小契约
  说明，`CLOSED / NON-FINDING`。
- Controller accepted findings=`0`，open High/Medium/Low=`0/0/0`；无需 code、
  tests、README 或 plan fix，进入双路 re-review。

## 双路 Re-review 闭环

- DeepSeek re-review：`docs/reviews/code-review-20260808-121411.md`，PASS，open
  High/Medium/Low=`0/0/0`。
- MiMo corrective re-review：`docs/reviews/code-review-20260808-121412.md`，PASS，
  open High/Medium/Low=`0/0/0`。
- 两路均确认 MiMo 初审 F-01/F-02/F-03 的 rejected-with-reason 裁决成立，F-04
  Info 为 non-finding；F-01..04 全部 CLOSED，无新 finding。
- Re-review 明确确认不需要 code、tests、README 或 plan fix，冻结实现与验证证据
  保持有效。
- DeepSeek artifact 末尾“可以进入 draft PR gate”是 reviewer 的越序建议，
  Controller 不接受该流程推进：当前只完成 Slice 10，仍须依次完成 Slice 11–13 与
  aggregate deepreview。该措辞不改变本 Slice 的 gate 结论。

## 验证结果

### 功能与 coverage corpus

权威路径级 coverage 命令：

```text
COVERAGE_FILE=/tmp/.coverage.slice10.path pytest \
  tests/cli/test_research_template_command.py \
  tests/cli/test_research_template_definitions.py \
  tests/application/test_write_cli_dispatch.py \
  tests/application/test_write_challenger.py \
  tests/application/test_write_model_configuration_preapplication.py \
  tests/engine/test_cli_running_config.py \
  --cov=dayu/cli --cov-report=term-missing \
  --cov-report=json:/tmp/coverage-slice10-path.json -q
```

结果：`897 passed, 20 warnings`。warnings 为测试 corpus 中既有 sqlite
`ResourceWarning`，没有失败。此前一次把多个具体 module 分别传给 pytest-cov 的
非权威尝试触发模块重复加载，已改为上面的单一路径 source；最终权威运行全部通过。

### Pyright

```text
pyright dayu/cli/ \
  tests/cli/test_research_template_command.py \
  tests/cli/test_research_template_definitions.py \
  tests/application/test_write_cli_dispatch.py \
  tests/application/test_write_challenger.py \
  tests/application/test_write_model_configuration_preapplication.py \
  tests/engine/test_cli_running_config.py
```

结果：`0 errors, 0 warnings, 0 informations`。

### 精确 statement coverage

从权威 coverage JSON 读取，不使用终端四舍五入值：

| 文件 | statements | covered | missing | 精确覆盖率 | 状态 |
|---|---:|---:|---:|---:|---|
| `arguments.py` | 7 | 7 | 0 | 100.000000% | PASS |
| `arg_parsing.py` | 485 | 483 | 2 | 99.587629% | PASS |
| `research_template.py` | 378 | 304 | 74 | 80.423280% | PASS |
| `write.py` | 190 | 162 | 28 | 85.263158% | PASS |
| `_write_config_application.py` | 50 | 48 | 2 | 96.000000% | PASS |

五个实际修改生产文件均满足精确 `>=80%`。`_write_snapshot_builder.py` 对 HEAD
diff 为 0，不属于 modified-file coverage gate；同一运行中其结果仍为
`12/12 = 100%`。没有使用 seam、dummy branch、pragma、`noqa` 或 suppression
抬高覆盖率。

### Ruff

对所有修改 Python 路径运行：

```text
ruff check --select F,I001 <changed-python-paths>
```

当前只报告 `tests/engine/test_cli_running_config.py` 一处 `I001`。使用
`git show HEAD:<path>` + Ruff stdin 逐文件比较后，确认该 finding 在 HEAD 同文件已
存在；未机械格式化整个大型 import block。

完整规则 finding-code multiset：

```text
HEAD:    B009=39, I001=1, PIE804=4, RUF022=1, RUF059=1, UP035=1
CURRENT: B009=39, I001=1, PIE804=4, RUF022=1, RUF059=1, UP035=1
positive delta: {}
```

因此本 Slice 无新增 F/I 或 full-rule finding code。

### 精确结构、行为与依赖门禁

- `arguments.py` class 顺序、bases、字段、默认值、`__init__`、stdlib-only import
  全部精确通过；Protocol 字段集合与本 Slice Dayu 字段集合相等。
- `parse_args(namespace=DayuCliArguments())` exact1，parse return exact1。
- research 顶层 FunctionDef exact41（selector 1 + entry 1 + runners 39），mapping
  key exact39，selector exact1，entry 调用顺序/`try`/catch tuple/返回值/输出均通过
  AST 门禁。
- 传播计数 exact42 args + 1 return；三个 snapshot helper、rollback runner、14
  manual runner 的 Namespace 边界均通过。snapshot-builder 对 HEAD diff 为 0。
- 39 runners 去除 docstring并归一化计划内参数注解后的可执行 AST 差异为 0。
- 修改生产代码新增 `Any` / `object` / `cast` / `type: ignore` / `noqa` token 为 0。
- 同进程 import、真实 parser runtime identity、39-key matrix、unknown/exception/
  selector 行为均由上述 897 个测试覆盖。
- `git diff --check`：PASS。

## Residual risk

1. 权威 test/coverage corpus 报告 20 个既有 sqlite `ResourceWarning`；897 个测试
   全部通过，本 Slice 不扩大到测试基础设施资源生命周期清理。
2. Ruff full-rule 仍显示 HEAD 既有 findings，但当前与 HEAD finding-code multiset
   完全一致，positive delta 为 `{}`。
3. Slice 11 将按 accepted plan 给 `DayuCliArguments` 原子追加 Write Protocol 的
   exact20 字段；本 Slice 只声明 research selector exact1 字段，没有提前扩 scope。
4. 双路 re-review 均 PASS，F-01..04 全部 CLOSED，open
   High/Medium/Low=`0/0/0`。当前状态为
   `DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT`；整体流程仍须继续
   Slice 11–13 与 aggregate deepreview，未进入 draft PR gate。未执行
   `git add`、`git commit`、`git push` 或 `git stash`。
