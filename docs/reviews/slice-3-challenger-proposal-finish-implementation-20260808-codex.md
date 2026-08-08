# Slice 3 Challenger proposal `finish()` 内联实现记录

- **日期**: 2026-08-08
- **Gate**: implementation
- **Work unit**: CLI write architecture refactor
- **Slice**: Slice 3 / W15
- **基线**: `4e90a69` (`gateflow: accept write artifact callers slice 2b`)
- **分支**: `codex/dual-model-research-mvp`
- **Approved plan**:
  `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v4.4 Slice 3
- **状态**: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT

## Scope 与 non-goals

允许修改：

- `dayu/services/write_model_challenger_proposal.py`
- 必要的直接测试与 `tests/README.md`（仅测试确有缺口时）
- 本实现记录

实际代码修改：

- `dayu/services/write_model_challenger_proposal.py`
- `docs/reviews/slice-3-challenger-proposal-finish-implementation-20260808-codex.md`

现有测试已经覆盖五条返回路径，并通过独立运行时 spy 锁定 finalize 调用次数与
参数，因此没有修改测试；测试入口、公共接口和用户工作流均未变化，
`tests/README.md` 无需更新。

本 slice 未改变分支条件、payload 字段写入顺序、finalize 参数、公共 API、
持久化或验证逻辑，也未进入后续 Slice 4 及 CLI 模块拆分范围。

## 实现内容

`build_write_model_challenger_proposal` 的嵌套 `finish()` 仅捕获五个既有局部值并
透传给 `_finalize_payload`，没有独立业务语义。按 accepted W15：

1. 删除嵌套 `def finish()`。
2. 将 global-block、not-needed、ambiguous、blocked、ready 五处
   `return finish()` 原位替换为直接 `return _finalize_payload(...)`。
3. 五处调用保持同一 `payload` identity，并精确传入：
   `normalized_history_fingerprint`、`selected_run_count`、
   `recent_run_count`、`baseline_run_count`。
4. 补齐被修改 public builder 的中文 Args/Returns/Raises docstring。

结构审计结果：

```text
nested_finish_defs=0
return_finish_calls=0
direct_finalize_returns=5
```

新增 `Any`、`object`、`cast`、`type: ignore` 或 glue seam 均为零。

## 五路径基线与差分证据

修改前后均运行同一无文件写入的 `unittest.mock.patch.object(..., wraps=...)`
spy harness。每个 case 同时断言 status、`_finalize_payload` 调用次数、payload
identity 与全部关键字参数：

| 路径 | 预期 status | 基线 | 修改后 |
|---|---|---:|---:|
| global-block | `blocked` | 1 次 finalize | 1 次 finalize |
| no role decisions | `not_needed` | 1 次 finalize | 1 次 finalize |
| ambiguous | `ambiguous` | 1 次 finalize | 1 次 finalize |
| blocked role | `blocked` | 1 次 finalize | 1 次 finalize |
| ready | `ready` | 1 次 finalize | 1 次 finalize |

五条路径的调用参数均为：

```text
history_fingerprint = sha256:111...111
selected_run_count = 5
recent_run_count = 5
baseline_run_count = 0
```

既有 `test_write_model_challenger_proposal.py` 已分别锁定五条业务路径和最终
payload/fingerprint 行为，因此无需新增只为内部结构服务的测试 seam。

## 验证结果

### 聚焦与相关测试

```text
source .venv/bin/activate
pytest tests/application/test_write_model_challenger_proposal.py -q
```

修改前与修改后均为 `8 passed`。

```text
pytest tests/application \
  --ignore=tests/application/test_streamlit_chat_stream_runtime.py \
  --ignore=tests/application/test_streamlit_chat_tab.py \
  --ignore=tests/application/test_streamlit_filing_runtime.py \
  --ignore=tests/application/test_streamlit_filing_tab.py \
  -k challenger_proposal -q
```

结果：`11 passed, 1 skipped, 1308 deselected`。四个 ignore 仅绕过当前环境未安装
可选 `streamlit` 时的无关 collection failure。

### Pyright

```text
source .venv/bin/activate
pyright dayu/services/
```

结果：`0 errors, 0 warnings, 0 informations`。

### Ruff

```text
ruff check --select F,I001 \
  dayu/services/write_model_challenger_proposal.py
```

结果：`All checks passed!`

全规则通过 `git show HEAD:<path> | ruff check --stdin-filename ... -` 与当前文件
比较 rule-code multiset：HEAD 与当前均为 `TRY004 × 4`、`UP035 × 1`，零新增、
零扩散。

### 精确单文件覆盖率

直接在 Coverage tracer 下加载 application conftest 会触发仓库已知的 Python
3.13/NumPy 导入问题。使用先 preload application conftest，再移除目标模块并
以 `Coverage(source=[module_name], timid=True)` 重新加载目标模块的 workaround
运行同一 8 个 proposal 测试：

```text
254 / 302 statements covered
48 missing
exact coverage = 84.11%
```

精确覆盖率达到 `>= 80%` 门槛。preload 产生一条 pytest assert-rewrite warning，
不影响测试或 coverage 数据。

### 范围与 diff 门禁

```text
rg '^    def finish\(' dayu/services/write_model_challenger_proposal.py
rg 'return finish\(\)' dayu/services/write_model_challenger_proposal.py
rg 'return _finalize_payload\(' dayu/services/write_model_challenger_proposal.py
git diff -U0 | rg '^\+.*(\bAny\b|\bobject\b|cast\(|type:\s*ignore)'
git diff --check
```

结果：前两项零匹配、direct finalize return 恰为 5、禁止类型逃逸零新增、
`git diff --check` 通过。

## Docs decision

这是不改变公共接口、测试入口或用户工作流的内部控制流简化。现有
`tests/README.md` 入口仍准确，根 README 与开发手册均未触发更新。

## 双路初审与 Controller 裁决

- DeepSeek 初审:
  `docs/reviews/code-review-slice-3-20260808-deepseek.md`
- MiMo 初审:
  `docs/reviews/code-review-slice-3-20260808-mimo.md`
- Controller 裁决:
  `docs/reviews/slice-3-code-review-adjudication-20260808-codex.md`

两路初审均为 **PASS** 并确认无需代码 fix。Controller 将 DS L-01/L-02 与
MiMo L1/L2/L3 全部裁决为 REJECT / non-defect：五处参数重复是 accepted
W15 的 direct-inline 设计，docstring 已按功能完整覆盖用户可见 `ValueError`，
Ruff `UP035 × 1` 与 `TRY004 × 4` 均为 HEAD pre-existing、zero-delta
baseline。Controller 裁决后 open High/Medium/Low 均为 `0`，随后进入双路
re-review。

## 双路 re-review 闭环

- DeepSeek:
  `docs/reviews/code-rereview-slice-3-20260808-deepseek.md`
- MiMo:
  `docs/reviews/code-rereview-slice-3-20260808-mimo.md`

两路复审均为 **PASS**，确认 DS L-01/L-02 与 MiMo L1/L2/L3 共 5 项
observation 全部 **CLOSED**，open High/Medium/Low 均为 `0`。核心等价性结论
维持，且无需 production/test/README/plan fix；Slice 3 已达到 accepted commit
门槛。

## Plan gaps 与 residual risk

- 未发现 accepted plan 不一致或 blocking open question。
- 五分支、调用次数、参数与 payload identity 已在当前 slice 通过基线/差分
  spy 验证，归类为 **fixed and covered in current slice**。
- 直接调用的参数重复是 accepted W15 的明确设计结果；当前 pyright、测试与
  code review gate 负责防止漂移，不需要生产 glue seam。
- Streamlit collection 与 Python 3.13/NumPy tracer 均为当前可选依赖/测量环境
  限制，已有明确 workaround，不是产品 residual risk。
- 无未分类 residual risk，已到达本 slice implementation stop condition。

## Artifact

`docs/reviews/slice-3-challenger-proposal-finish-implementation-20260808-codex.md`
