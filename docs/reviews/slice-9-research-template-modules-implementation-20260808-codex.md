# Slice 9 Research Template 私有模块拆分实现记录

- **日期**: 2026-08-08
- **基线**: `89fa4bc gateflow: accept cli write architecture plan v5.1`
- **分支**: `codex/dual-model-research-mvp`
- **计划**: v5.1 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **范围**: Slice 9 C2 / S9-CTRL-01..04
- **状态**: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT

## 允许与实际修改范围

生产代码：

- `dayu/cli/commands/_research_template_helpers.py`（新建）
- `dayu/cli/commands/_research_template_core.py`（新建）
- `dayu/cli/commands/_research_template_bundle.py`（新建）
- `dayu/cli/commands/_research_template_monitoring.py`（新建）
- `dayu/cli/commands/_research_template_materialize.py`（新建）
- `dayu/cli/commands/research_template.py`
- `dayu/cli/commands/write.py`

直接测试：

- `tests/cli/test_research_template_command.py`

实现记录：

- `docs/reviews/slice-9-research-template-modules-implementation-20260808-codex.md`
- `docs/reviews/slice-9-code-review-adjudication-20260808-codex.md`
- `docs/reviews/slice-9-research-template-modules-fix-20260808-codex.md`

测试入口、测试分层、CLI 命令、参数、退出码与用户调用方式均未改变。
`tests/README.md`、根 `README.md` 与 `dayu/README.md` 的职责范围内没有需要同步的
稳定接口或使用方式变化，因此本 Slice 不修改 README。

## 实现摘要

### 五个真实 owner

- `_research_template_helpers.py` 按计划逐名迁移 exact 22 个函数、
  `ResearchTemplate` / `ResearchTemplateRecommendation` 两个 dataclass 与 exact 7
  个域常量。
- `_research_template_core.py`、`_research_template_bundle.py`、
  `_research_template_monitoring.py`、`_research_template_materialize.py` 分别逐名
  迁移 exact 26 / 12 / 11 / 12 个函数。
- 五组互斥并集为 exact 83；每个迁移函数去除 docstring 后均与基线 AST 相同，
  两个 dataclass 去除 docstring 后同样与基线 AST 相同。
- 五个新模块均提供中文概览；83 个函数全部提供中文 Args / Returns /
  Raises docstring。初审指出其中存在系统性泛化表述后，已逐函数改为
  真实、具体的功能、参数、返回值与异常说明。没有引入 compatibility
  re-export、wrapper、glue seam、反向 import、
  owner lazy import、`cast`、`type: ignore` 或 suppression。
- 基线 `research_template.py` 与当前主模块加五 owner 的 `object` 文本 token
  均为 109，AST `Name(id="object")` 均为 84；`Any` token 均为 0。两种
  口径分别对应文本匹配与 AST 语义节点，基线/当前各自稳定。既有
  `_DATA_SOURCE_BINDING_CANDIDATES` 类型和值语义原样 1→1 迁移，没有新增
  或扩散类型逃逸。

### 主模块 functional facade

- `research_template.py` 只保留 `run_research_template_command` 与 39 个 `_run_*`
  runner：顶层 FunctionDef exact 40、ClassDef exact 0、迁移旧定义 exact 0。
- 从五个 owner 正常 import retained entry / runner 真实调用的 exact 45 个功能绑定，
  分布 exact `6 / 18 / 6 / 9 / 6`；其他 38 个迁移函数 compatibility binding 为 0。
- `research_template.py.__all__` 从 68 删除 accepted exact 13，终态 exact 55；
  五个私有 owner 均不定义 `__all__`。
- retained entry + 39 runners 去除 docstring 后与基线 AST 差异为 0。

### 依赖与 write lazy owner

- AST import 审计得到唯一 DAG：main→all5；core→helpers；bundle→core+helpers；
  monitoring→bundle+core+helpers；materialize→monitoring+bundle+core+helpers。
  helpers 不依赖其他新 owner，五个 owner 均不 import main。
- `write._materialize_research_after_write` 保留 function-local import 时序，只把
  materialize 真源从 `research_template` 改为 `_research_template_materialize`；
  旧路径 exact 0、新路径 exact 1。
- 同进程 import smoke 覆盖 main、五个 owner 与 `write.py`，全部通过。

### 测试 ownership

- 迁移函数的直接 import 与 owner 内依赖 patch 全部改指向真实 owner；只验证 entry
  或 39 runner global lookup 的 patch 继续指向 `research_template` 主模块。
- 新增 exact45 functional-binding identity 回归，逐项验证主模块绑定与真实 owner
  函数对象相同。
- 新增真实 write lazy-materialize caller 回归，验证 function-local import 使用新
  materialize owner，并保持 manifest、workspace 与 overwrite 参数语义。

## 初审与 Controller 修复

- DeepSeek 初审：`docs/reviews/code-review-20260808-091000-deepseek.md`。
  Verdict 为 PASS；Findings 正文实际为 1 High + 2 Medium + 2 Low 共 5 项。
  Verdict 段所写“3 Low”与正文编号不一致，Controller 按 5 项正文逐项裁决。
- MiMo 初审：`docs/reviews/code-review-20260808-091001-mimo.md`。
  Verdict 为 PASS，open High/Medium/Low=`0/0/1`。
- Controller 裁决：
  `docs/reviews/slice-9-code-review-adjudication-20260808-codex.md`。
  接受 DS 2/3/5 与 MiMo L-01，拒绝 DS 1/4；Controller open H/M/L=`0/0/0`。
- 修复记录：
  `docs/reviews/slice-9-research-template-modules-fix-20260808-codex.md`。
  修改仅限 docstring，可执行语句、签名、owner/import、tests、README 与 plan 均未变。
- DeepSeek targeted re-review：
  `docs/reviews/code-review-20260808-093800-deepseek.md`，PASS，open
  High/Medium/Low=`0/0/0`。
- MiMo targeted re-review：
  `docs/reviews/code-review-20260808-093801-mimo.md`，PASS，open
  High/Medium/Low=`0/0/0`。
- 两路均确认初审 6 项 observations 全部 CLOSED，无新 finding，无需进一步
  code、tests、README 或 plan fix。

## 验证结果

### 功能测试

相关 research-template / write dispatch corpus：

```text
pytest tests/cli/test_research_template_command.py \
  tests/cli/test_research_template_definitions.py \
  tests/application/test_write_cli_dispatch.py -q
```

实现阶段结果：`323 passed in 1.92s`；coverage 运行同一 corpus 再次得到
`323 passed in 3.33s`。docstring fix 后复跑结果：`323 passed in 1.99s`。

全部 application `test_write*.py` 与 engine write caller corpus：

```text
pytest $(rg --files tests/application | rg '/test_write.*\.py$' | sort) \
  tests/engine/test_cli_running_config.py -q \
  --cov=dayu.cli.commands.write \
  --cov-report=json:.coverage-slice9-write-final.json --cov-report=
```

实现阶段 coverage 结果：`812 passed, 15 warnings in 22.52s`。warnings 均为
既有 sqlite `ResourceWarning`，没有测试失败。docstring fix 后无 coverage
复跑结果：`812 passed in 11.97s`。

### Pyright

```text
pyright dayu/cli/ tests/cli/test_research_template_command.py
```

结果：`0 errors, 0 warnings, 0 informations`。
该命令在 docstring fix 后再次运行，结果仍为
`0 errors, 0 warnings, 0 informations`。

### Ruff

```text
ruff check --select F,I \
  dayu/cli/commands/_research_template_helpers.py \
  dayu/cli/commands/_research_template_core.py \
  dayu/cli/commands/_research_template_bundle.py \
  dayu/cli/commands/_research_template_monitoring.py \
  dayu/cli/commands/_research_template_materialize.py \
  dayu/cli/commands/research_template.py \
  dayu/cli/commands/write.py \
  tests/cli/test_research_template_command.py
```

结果：`All checks passed!`。
该 F/I 命令在 docstring fix 后再次运行，仍为 `All checks passed!`。

以 `git show 89fa4bc:<path>` 经 Ruff stdin 检查基线三文件，并与当前七个生产文件
加修改测试的 full-rule finding-code multiset 比较：

```text
BASELINE: B009=39, I001=1, RUF022=1, TRY004=11
CURRENT:  B009=39, RUF022=1, TRY004=11
positive delta: {}
negative delta: {I001: 1}
```

docstring fix 后复跑 full-rule multiset，结果与上表一致，positive delta 仍为
`{}`。

### 精确 statement coverage

research-template 六文件使用 323 个真实 caller tests；`write.py` 使用上述 812 个
application / engine 真实 caller tests。JSON 精确结果如下：

| 文件 | statements | covered | missing | 精确覆盖率 | 状态 |
|---|---:|---:|---:|---:|---|
| `_research_template_helpers.py` | 195 | 170 | 25 | 87.179487% | PASS |
| `_research_template_core.py` | 403 | 360 | 43 | 89.330025% | PASS |
| `_research_template_bundle.py` | 289 | 240 | 49 | 83.044983% | PASS |
| `_research_template_monitoring.py` | 425 | 346 | 79 | 81.411765% | PASS |
| `_research_template_materialize.py` | 269 | 242 | 27 | 89.962825% | PASS |
| `research_template.py` | 448 | 371 | 77 | 82.812500% | PASS |
| `write.py` | 189 | 157 | 32 | 83.068783% | PASS |

七个修改生产文件均按精确百分比满足 `>=80%`；没有使用 seam、pragma、noqa、
dummy branch 或四舍五入值提升/判断覆盖率。覆盖率临时 data / JSON 文件均已删除。
docstring fix 只改变文档常量与行号，不改变可执行 statement、caller corpus
或 stripped-docstring AST，因此继承上述实现阶段精确 coverage 证据。

### 结构与行为门禁

- owner FunctionDef exact `22/26/12/11/12`，无 missing、extra、overlap；main
  FunctionDef exact40 / ClassDef0 / moved definitions0。
- helpers ClassDef exact2、计划常量 exact7；owner private `__all__` exact0。
- main functional imports 与 identity exact45=`6/18/6/9/6`，其他38 compat0；
  main `__all__` exact55。
- 83 个迁移函数、2 个 dataclass、retained entry + 39 runners 的去 docstring AST
  差异均为 0；JSON、ID、duplicate、BOM、validation、rollback 与 materialization
  相关 323 个测试全部通过。
- docstring fix 后，83/83 函数均含真实中文概览、Args、Returns、Raises；
  参数说明遗漏 0，已知泛化模板短语残留 0，去 docstring AST 差异仍为 0。
- DAG、旧/新 lazy owner 路径、真实 direct/dispatch test owner 与同进程 import
  smoke 全部通过。
- `git diff --check`：PASS。
- README diff：0。

## Residual risk

1. 完整 write coverage corpus 仍报告 15 个既有 sqlite `ResourceWarning`；812 个测试
   全部通过，本 Slice 不扩大到测试基础设施资源生命周期清理。
2. 一次迁移 83 个函数的机械漂移风险已由逐名 inventory、去 docstring AST、
   exact45 identity、DAG、import smoke、323+812 tests 与七文件精确 coverage 共同
   约束；当前没有未分类或无 owner 的实现风险。
3. `RuntimeError` double-fault runner 捕获范围与透明 owner helper 均是 HEAD 存量、
   accepted plan 锁定的语义，本 fix 不扩大到可执行行为修改。
4. 双路 targeted re-review 均 PASS，初审 6 项 observations 全部 CLOSED，
   open High/Medium/Low=`0/0/0`；当前状态为
   `DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT`。未执行
   `git add`、`git commit`、`git push` 或 `git stash`。
