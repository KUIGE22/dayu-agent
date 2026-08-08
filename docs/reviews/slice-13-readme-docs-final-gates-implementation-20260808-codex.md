# Slice 13 README / Docs 与最终门禁 Implementation 记录

- **日期**: 2026-08-08
- **基线**: `dda9cb4 gateflow: accept cli write architecture slice 12`
- **分支**: `codex/dual-model-research-mvp`
- **Gate**: Slice 13 implementation
- **Accepted plan**: v5.5 ACCEPTED / DUAL PLAN RE-REVIEW PASS，Slice 13
- **状态**: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT

## Code review 与 Controller 裁决

- DeepSeek 初审：`docs/reviews/code-review-20260808-144139.md`，PASS，material
  findings=`0`，open High/Medium/Low=`0/0/0`。
- MiMo 初审：`docs/reviews/code-review-20260808-144140.md`，PASS，material
  findings=`0`，open High/Medium/Low=`0/0/0`。
- Controller 裁决：
  `docs/reviews/slice-13-code-review-adjudication-20260808-codex.md`。
- Controller accepted findings=`0`，open High/Medium/Low=`0/0/0`；两路初审均无
  material finding，无需修改 code、tests、README 或 accepted plan。
- DeepSeek re-review：`docs/reviews/code-review-20260808-145534.md`，PASS，open
  High/Medium/Low=`0/0/0`。
- MiMo re-review：`docs/reviews/code-review-20260808-145535.md`，PASS，open
  High/Medium/Low=`0/0/0`。
- 双路复审确认 accepted findings=`0`、四类 informational/environment non-finding
  全部 CLOSED，无需 fix，也无需修改 code、tests、README 或 plan。Slice 13 已达到
  accepted commit gate 前置条件。

## Scope 与变更路径

本 Slice 的实际修改仅为：

- `dayu/README.md`
- `docs/reviews/slice-13-readme-docs-final-gates-implementation-20260808-codex.md`

只读核对但无需修改：

- `README.md`
- `tests/README.md`

没有修改 production Python、tests、public CLI、参数、返回码、输出文本或运行时行为；
没有实施 accepted plan 之外的重构，也没有新增 compatibility、glue、cast、ignore、
`Any` 或 `object`。

## Pre-edit 文档与 CLI 真相审计

- clean HEAD 为 `dda9cb4`，分支正确。
- 通过当前 `dayu-cli write --help` 核对根 README 的 write 示例所用关键参数：
  `--research-template`、`--materialize-research`、
  `--write-live-smoke-plan-output`、
  `--routing-challenger-run-plan-output` 均存在。
- 根 README 共包含 50 条 `dayu-cli write` 示例；research-template 示例覆盖当前
  dispatch mapping 的 exact39 action，missing=`[]`、unknown=`[]`。因此根 README
  已是当前用户手册真相，无需机械改写。
- `tests/README.md` 已登记 `tests/application/test_write_cli_dispatch.py`，并准确描述
  Protocol/AST、14+2 phase table、16-selector、exact39 mapping、真实
  `DayuCliArguments` parser 与 Phase E/F/H 错误边界。本 Slice 不重复添加。
- `dayu/README.md` 仍只描述旧的粗粒度 CLI 三层，未写明 `arguments.py` 以及已完成的
  `_write_*.py` / `_research_template_*.py` 真实 owner 拆分，是本 Slice 唯一需修正文档。
- 未发现命令、owner、README 职责或 final validation matrix 的 plan gap。

## 实现摘要

- `dayu/README.md` 的 UI 层说明加入 `arguments.py`：其拥有真实 argparse 参数对象与
  窄 dispatch Protocol。
- 明确 `commands/write.py` 与 `commands/research_template.py` 只保留入口编排和真实
  功能绑定，具体职责由 `_write_*.py` 与 `_research_template_*.py` 私有 owner 承载；
  测试与扩展代码不得为旧路径新增兼容转发。
- 开发者阅读顺序同步为
  `cli/arguments.py -> cli/arg_parsing.py -> cli/main.py -> cli/commands/`。

## 验证结果

### Slice 聚焦测试

```text
source .venv/bin/activate
python -m pytest tests/application/test_write_service.py \
  tests/application/test_write_cli_dispatch.py -v
```

结果：`164 passed in 0.87s`。

### Python 3.11 min-compat required lane

在隔离临时环境中使用 Python `3.11.15`，精确安装：

```text
python -m pip install --upgrade pip
pip install -e ".[test,dev,browser,web]" -c constraints/min-py311.txt
```

首次运行继承本机 `SERPER_API_KEY`，使
`test_search_with_serper_requires_api_key` 不再处于测试名要求的“缺 key”前置条件并
尝试访问本机代理；结果为 `7120 passed, 5 skipped, 1 failed, 9 deselected`。这不是
current diff 缺陷：本 Slice 的 Python 与 tests diff 均为零。

显式移除该本机密钥、复刻 CI 无密钥环境后重新运行完整命令：

```text
env -u SERPER_API_KEY pytest -q --timeout=60 \
  -m "not integration and not slow and not e2e"
```

结果：`7121 passed, 5 skipped, 9 deselected in 115.70s`。

### Pyright ratchet

```text
source .venv/bin/activate
python -m utils.ci_pr_pyright \
  --base "$(git merge-base origin/main HEAD)" \
  --head "$(git rev-parse HEAD)"
```

结果：PASS；HEAD=`219`、BASE=`219`，PR 新增诊断=`0`。

### Ruff

- accepted per-Slice 命令
  `ruff check dayu/cli/commands/ dayu/services/` 复现 HEAD 既有
  `335` 条全规则 finding；本 Slice 没有 Python diff，positive delta=`0`。
- `ruff check --select F,I dayu/cli/commands/ dayu/services/` 复现 HEAD 既有
  `35` 条 F/I finding；本 Slice没有 Python diff，positive delta=`0`。
- dual-model workflow 聚焦 Ruff 对 9 个 utils/tests 路径：PASS。

### Dual-model gate 聚焦测试

```text
pytest -q tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py \
  tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py \
  tests/test_prepare_deepseek_task.py
```

结果：`699 passed in 9.58s`。

### Machine-readable gates 与差分

```text
python -m utils.validate_handoff_docs --json
python -m utils.codex_review_gate --allow-waiting --json
python -m utils.dual_model_pipeline_check --json
git diff --check
```

结果：四项均 PASS；三个 JSON gate 均返回 `"ok": true`，diff whitespace 零问题。

### Coverage

本 Slice 实际修改 production Python 文件为零，因此没有可计算的 modified-production
statement coverage；coverage 门槛分类为 N/A。聚焦 164 tests 与 Python 3.11 全量
7121 tests 提供文档所描述 public CLI/dispatch/service 行为的回归证据。

## README 决策

- 根 `README.md` 的 write/research-template 示例已由真实 help、39-action mapping 和
  50 条 write 示例审计确认，无需修改。
- `tests/README.md` 已在前序 Slice 收录当前 dispatch 测试入口，内容与终态一致，
  无需重复修改。
- `dayu/README.md` 属开发者架构职责，且其 CLI 模块组织确实落后于当前终态，因此
  做了上述最小更新。

## Residual risk

- 全规则 Ruff `335` 与 F/I `35` 均为 HEAD 既有债务，本 Slice production/tests
  diff=0，分类为 pre-existing/out-of-scope/non-blocking；未通过“修文档”顺手改代码。
- Python 3.11 首次测试的单一失败来自本机注入密钥破坏测试前置条件；无密钥的 CI
  等价环境完整通过，分类为 local-environment/non-blocking。
- machine-readable gate、whitespace 与 diff-check 全部通过；当前没有未分类
  implementation risk。
- 未执行 `git add`、`git commit`、`git push` 或 `git stash`。
