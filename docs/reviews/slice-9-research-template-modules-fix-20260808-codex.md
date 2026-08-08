# Slice 9 Research Template 私有模块 Review Fix 记录

- **日期**: 2026-08-08
- **基线**: `89fa4bc gateflow: accept cli write architecture plan v5.1`
- **Gate**: Slice 9 code review fix
- **状态**: DUAL RE-REVIEW PASS / CLOSED
- **裁决**: `docs/reviews/slice-9-code-review-adjudication-20260808-codex.md`

## 来源与 fix scope

- DeepSeek：`docs/reviews/code-review-20260808-091000-deepseek.md`。
- MiMo：`docs/reviews/code-review-20260808-091001-mimo.md`。
- 接受 DS 2 / 3 / 5 的异常 docstring 精度问题。
- 接受 MiMo L-01，对五个 owner 的 exact 83 个迁移函数做全量 docstring
  精化。
- DS 1 / 4 按 Controller 裁决 rejected-with-reason，不进入可执行修复范围。

## 修改路径

- `dayu/cli/commands/_research_template_helpers.py`
- `dayu/cli/commands/_research_template_core.py`
- `dayu/cli/commands/_research_template_bundle.py`
- `dayu/cli/commands/_research_template_monitoring.py`
- `dayu/cli/commands/_research_template_materialize.py`
- `dayu/cli/commands/write.py`
- `docs/reviews/slice-9-research-template-modules-implementation-20260808-codex.md`
- `docs/reviews/slice-9-code-review-adjudication-20260808-codex.md`
- `docs/reviews/slice-9-research-template-modules-fix-20260808-codex.md`

未修改可执行语句、签名、owner/import、控制流、tests、README、master plan 或
外部 review artifact。

## 修复内容

1. 逐项重写 83 个迁移函数的中文 docstring，明确真实功能、参数业务
   含义、返回载荷、落盘或校验副作用，以及可传播异常的精确触发条件。
2. `list_research_templates` 明确声明缺失模板目录的
   `FileNotFoundError` 和目录/标题读取失败的 `OSError`。
3. `build_research_template_usage_guide` 明确声明模板名校验、模板
   缺失及标题读取可传播的 `ValueError` / `FileNotFoundError` / `OSError`。
4. `write._materialize_research_after_write` 明确声明底层物化流程原样传播
   的 I/O、验证、文件存在性与回滚 double-fault 异常。

## 修后验证

```text
pytest tests/cli/test_research_template_command.py \
  tests/cli/test_research_template_definitions.py \
  tests/application/test_write_cli_dispatch.py -q
```

结果：`323 passed in 1.99s`。

```text
pytest $(rg --files tests/application | rg '/test_write.*\.py$' | sort) \
  tests/engine/test_cli_running_config.py -q
```

结果：`812 passed in 11.97s`。

```text
pyright dayu/cli/ tests/cli/test_research_template_command.py
```

结果：`0 errors, 0 warnings, 0 informations`。

Ruff F/I：`All checks passed!`。Full-rule finding-code multiset：

```text
BASELINE: B009=39, I001=1, RUF022=1, TRY004=11
CURRENT:  B009=39, RUF022=1, TRY004=11
positive delta: {}
negative delta: {I001: 1}
```

83 个迁移函数、2 个 dataclass、retained entry + 39 runners 去 docstring AST
差异均为 0。83/83 函数均含中文概览与 Args / Returns / Raises，参数
说明遗漏 0，已知泛化模板短语残留 0。

精确 coverage 不重跑：相对已验证的实现，本 fix 只改五个 owner 与
`write.py` 的 docstring，`research_template.py` 也没有新的可执行变化。七文件的
statement、caller corpus 与 stripped-docstring AST 不变，继承实现阶段精确证据：

- helpers `87.179487%`
- core `89.330025%`
- bundle `83.044983%`
- monitoring `81.411765%`
- materialize `89.962825%`
- main `82.812500%`
- write `83.068783%`

七文件均 `>=80%`。`ruff format --check` 报告 8 个涉及文件全部已格式化；
`git diff --check` PASS。

## 双路 Targeted Re-review 闭环

- DeepSeek：`docs/reviews/code-review-20260808-093800-deepseek.md`，PASS，
  open High/Medium/Low=`0/0/0`。
- MiMo：`docs/reviews/code-review-20260808-093801-mimo.md`，PASS，
  open High/Medium/Low=`0/0/0`。
- 两路均确认 DS 1–5 与 MiMo L-01 共 6 项初审 observations 全部 CLOSED，
  无新 finding，无需进一步 code、tests、README 或 plan fix。
- 本 fix gate 已关闭，实现进入 `READY FOR ACCEPTED COMMIT`。

## Residual risk

1. RuntimeError double-fault runner 捕获范围是 HEAD 存量语义，本 exact owner
   migration 不改变；如要改变，需独立语义 work unit 与 runner-level 回归。
2. 83 函数大规模 docstring 改写的漂移风险由 stripped-docstring AST、参数名
   完整性、323 + 812 tests 与静态门禁共同约束。
3. 双路 targeted re-review 均 PASS，全部 finding CLOSED；未执行 `git add`、
   `git commit`、`git push` 或 `git stash`。

## Artifact

`docs/reviews/slice-9-research-template-modules-fix-20260808-codex.md`
