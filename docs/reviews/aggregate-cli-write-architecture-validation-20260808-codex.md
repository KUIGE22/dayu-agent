# CLI Write 架构重构 Aggregate Validation 记录

- **日期**：2026-08-08
- **分支**：`codex/dual-model-research-mvp`
- **当前 HEAD**：`4d2535dbff21531b267b6054826520c9d0664393`
  （`gateflow: accept cli write architecture plan v5.7`）
- **PR baseline**：`origin/main=2115c86d5a9027bb51cbbc8a4d0175080732e4e6`
- **Architecture Ruff baseline**：`5821014`
- **Accepted plan**：
  `docs/plans/2026-08-07-cli-write-architecture-refactor.md`，
  `v5.7 ACCEPTED / DUAL PLAN RE-REVIEW PASS`
- **Gate**：aggregate pre-deepreview validation
- **状态**：`READY FOR AGGREGATE DEEPREVIEW`

## 1. Scope 与边界

本轮只验证 accepted Slice 0–13 的 aggregate terminal tree，并新增本 validation
artifact。没有修改 production、tests、README、master plan、CI workflow 或外部 review；
没有启动 aggregate deepreview，也没有进入 fix、commit、push 或 PR gate。

相对 `origin/main`，当前分支为 93 commits、445 changed files；这只是 aggregate review
规模信息，不替代 accepted v5.7 的结构、行为、类型与 Ruff hard gates。

## 2. Clean baseline 与证据复用边界

### 2.1 Preflight

- 开始验证时 `git status --short` 为空。
- 当前分支不是 protected trunk，HEAD 精确为 `4d2535d`。
- `git diff --quiet 2a4bafb..HEAD -- dayu tests README.md dayu/README.md
  tests/README.md` 返回 0；Slice 13 accepted commit 后只有 plan/review commits。
- `4c5bb1b..HEAD` 对相同路径也为零 diff，因此此前在 clean `4c5bb1b` 上执行的
  aggregate 结构、owner/DAG、379 tests 与 pyright ratchet 证据适用于当前字节树。

Git object 直接证据：

| 路径 | 当前 HEAD tree/blob | Slice 13 / 前次 aggregate 证据 | 结果 |
|---|---|---|---|
| `dayu/` | `5eb6a0e8762de333be4ed57451bd0793e33b98c3` | `2a4bafb` 与 `4c5bb1b` 同值 | 字节相同 |
| `tests/` | `2a7d71132f2be9a2cadeb6f34777fc0de73623d8` | `2a4bafb` 与 `4c5bb1b` 同值 | 字节相同 |
| `README.md` | `667e59603d01758bb4275b5b8fa0a9f9203cabd0` | `2a4bafb` 同值 | 字节相同 |
| `dayu/README.md` | `0cf8c934b7520e4d9e28f7604d62a40adc6b8264` | `2a4bafb` 同值 | 字节相同 |
| `tests/README.md` | `f71057a51dd3e098407c18d0f0b647e998d5f801` | `2a4bafb` 同值 | 字节相同 |

### 2.2 精确复用的 hard-gate 证据

此前已在相同 `dayu`/`tests` tree 上直接执行并通过：

- Aggregate 结构/owner/DAG/identity：PASS。
  - `write.py` 顶层 FunctionDef exact18，其中 adapter exact16；Phase A/B tables
    exact14+2。
  - `research_template.py` 顶层 FunctionDef exact41、runner exact39、dispatch
    exact39、`__all__` exact55。
  - research owner FunctionDef exact `22/26/12/11/12`，互斥并集 exact83；functional
    bindings exact `6/18/6/9/6`，合计45。
  - research owner DAG 与 manual→snapshot→config-application DAG 均 PASS；零 reverse
    import、零 compatibility binding/re-export。
- Aggregate 行为聚焦：

  ```text
  pytest -q tests/application/test_write_cli_dispatch.py \
    tests/cli/test_research_template_command.py \
    tests/application/test_write_service.py
  ```

  结果：`379 passed`。
- Pyright ratchet：

  ```text
  python -m utils.ci_pr_pyright \
    --base "$(git merge-base origin/main HEAD)" \
    --head "$(git rev-parse HEAD)"
  ```

  结果：PASS；HEAD=`219`、BASE=`219`、PR 新增诊断=`0`。
- Python 3.11 min-compat full suite：Slice 13 artifact
  `docs/reviews/slice-13-readme-docs-final-gates-implementation-20260808-codex.md`
  已在 Python `3.11.15`、无本机 `SERPER_API_KEY` 的 CI 等价环境运行：
  `7121 passed, 5 skipped, 9 deselected in 115.70s`。

这些证据只因上述 Git object 精确相同而复用；不是以“最近运行过”替代当前树验证。

## 3. v5.7 Architecture Ruff Hard Gate

固定 leaf command：

```text
uv run --no-project --with ruff==0.16.1 ruff check --no-cache \
  --output-format=json dayu/cli/commands/ dayu/services/
```

本轮在当前 HEAD、`git archive 5821014` 与 `git archive 2115c86` 三棵临时树上运行
完全相同的命令，并按 JSON finding rule code 构造 `Counter`。临时树由
`TemporaryDirectory` 自动清理。

### 3.1 Architecture baseline `5821014`

| 指标 | 结果 |
|---|---:|
| HEAD total | 335 |
| BASE total | 364 |
| positive | `{}`（0） |
| negative | `{I001: 11, TRY004: 17, UP035: 1}`（29） |

断言 `Counter(HEAD) - Counter(BASE) == {}` 通过；这是 accepted v5.7 的 blocking
architecture hard gate，结果为 **PASS**。

### 3.2 Mandatory PR-level residual

相同 Ruff 版本、命令、scope 与 Counter 算法比较 `origin/main=2115c86`：

- HEAD total=`335`
- BASE total=`143`
- per-code positive total=`216`
- exact 10 codes：
  - `B009:53`
  - `BLE001:3`
  - `FURB162:12`
  - `ISC004:1`
  - `RUF010:22`
  - `RUF022:2`
  - `SIM102:1`
  - `TRY004:118`
  - `UP012:2`
  - `UP035:2`

该 positive216 不阻断 architecture-scoped validation，但它是 aggregate deepreview 的
**mandatory PR-level residual input**。后续 deepreview 不得省略、淡化或误称为 CI 已覆盖；
遗漏会阻止 deepreview closeout。

## 4. Dual-model Focused Tests 与 Machine Gates

### 4.1 Focused 699

当前 HEAD 在 `.venv`（Python 3.13.13）运行：

```text
pytest -q tests/test_validate_handoff_docs.py tests/test_codex_review_gate.py \
  tests/test_dual_model_pipeline_check.py tests/test_dual_model_gates_workflow.py \
  tests/test_prepare_deepseek_task.py
```

结果：`699 passed in 9.40s`。

### 4.2 三个 JSON machine gates

```text
python -m utils.validate_handoff_docs --json
python -m utils.codex_review_gate --allow-waiting --json
python -m utils.dual_model_pipeline_check --json
```

结果：三项退出码均为 0，且均返回 `"ok": true`。

- handoff docs：`issues=[]`
- codex review gate：`WAITING_FOR_TASK`，`issues=[]`、`blocked_term_hits=[]`、
  `secret_key_hits=[]`
- dual-model pipeline：handoff docs、codex review gate、text whitespace、blocked term
  scan、secret key shape scan 全部 `ok=true`

## 5. Repository Hygiene 与 README 真相

- `git diff --check`：PASS。
- 写 artifact 前 `git status --short`：为空；`git ls-files -u`：为空。
- 排除 `.venv/` 与 `.git/` 环境元数据后，仓库内 `.coverage*`、
  `coverage*.json`、`*.rej`、`*.orig`：0。
- production/plan 之外的冲突标记扫描：0。
- machine gate `secret_key_hits=[]`，secret/blocked-term 扫描均 PASS。
- 根 README 的当前 CLI 示例、`dayu/README.md` 的 `arguments.py` / `_write_*.py` /
  `_research_template_*.py` owner 说明，以及 `tests/README.md` 的
  `test_write_cli_dispatch.py` 入口均与 Slice 13 accepted 字节完全一致，无需更新。

本轮没有生成或删除用户文件；只读 Ruff 临时归档已自动清理。

## 6. Gate 汇总

| Gate | 结果 | 证据方式 |
|---|---|---|
| clean branch / accepted v5.7 | PASS | 当前 HEAD 直接核对 |
| terminal structure / owner / DAG / identity | PASS | 同字节 tree 复用 |
| aggregate behavior focused 379 | PASS | 同字节 tests/production 复用 |
| pyright ratchet 219/219/new0 | PASS | 同字节 tests/production 复用 |
| Python 3.11 full 7121 | PASS | Slice 13 证据 + Git object identity |
| architecture Ruff positive0 / negative29 | PASS | 当前 HEAD 直接复跑 |
| origin/main PR residual216 | RECORDED / MANDATORY | 当前 HEAD 直接复跑 |
| dual-model focused 699 | PASS | 当前 HEAD 直接复跑 |
| three JSON machine gates | PASS | 当前 HEAD 直接复跑 |
| diff / status / conflict / secret / temp | PASS | 当前 HEAD 直接复跑 |

## 7. README / Docs 决策

Aggregate validation 不改变接口、命令、架构或测试入口，因此不修改根 README、
`dayu/README.md` 或 `tests/README.md`。本 artifact 是本轮唯一输出。

## 8. Residual Risk

- `origin/main` 同 scope 的 Ruff positive216 是已分类、必须交给 aggregate deepreview
  裁决的 PR-level residual；CI required lane 不检查 production Ruff。它不阻断当前
  architecture validation，但在 deepreview closeout 前不得遗失。
- 本轮没有重复运行耗时的 Python 3.11 full suite、379 行为集或 pyright ratchet；复用依据
  是当前与证据 commits 的 production/tests Git tree object 精确相同。若这些路径在后续
  commit 发生任何字节变化，复用立即失效并必须重跑。
- 没有未分类 residual，没有 hard-gate failure，也没有 code/tests/README/plan fix。

## 9. Completion

Accepted v5.7 aggregate pre-deepreview validation 的全部 blocking hard gates 已通过；
PR-level Ruff residual216 已完整记录并指定给 aggregate deepreview。当前状态为：

`READY FOR AGGREGATE DEEPREVIEW`

本轮未执行 `git add`、`git commit`、`git push` 或 `git stash`。
