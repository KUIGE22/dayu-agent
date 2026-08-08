# v5.6 Aggregate Gate Erratum Controller 记录

- 日期：2026-08-08
- 基线：`2a4bafb`
- 分支：`codex/dual-model-research-mvp`
- Gate：aggregate validation 前的 plan fix
- Master plan：`docs/plans/2026-08-07-cli-write-architecture-refactor.md`
- DeepSeek plan review：`docs/reviews/plan-review-20260808-150148.md`
- MiMo plan review：`docs/reviews/plan-review-20260808-150149.md`
- DeepSeek re-review：`docs/reviews/plan-review-20260808-152220.md`
- MiMo re-review：`docs/reviews/plan-review-20260808-152221.md`
- MiMo corrective re-review：`docs/reviews/plan-review-20260808-153009.md`
- 状态：`v5.6 ACCEPTED / DUAL PLAN RE-REVIEW PASS / CLOSED`

## 1. 直接证据

- 当前 `write.py` 为 1014 行，`research_template.py` 为 1369 行；两者仅作为信息性测量，不再作为完成门槛。
- 当前 `write.py` 顶层 `FunctionDef` 精确为 18：16 个 `_adapter`、`_materialize_research_after_write` 与 `run_write_command`；两张 `Final` phase table 分别为 14 和 2 项。
- 当前 `research_template.py` 顶层 `FunctionDef` 精确为 41：entry 1、Slice 10 新增 selector 1、runner 39；`ClassDef` 为 0，dispatch mapping 为 39 项，`__all__` 为 55 项。
- Slice 9 的历史基线仍是 `FunctionDef=123`，即迁移 83 个函数并保留 40 个函数，`83+40=123`。终态 41 来自 Slice 10 后续新增 selector，不是 Slice 9 历史漏计。

## 2. Controller 裁决

### 2.1 DeepSeek `plan-review-20260808-150148.md`

- `AGG-01`：`ACCEPTED / CLOSED-BY-PLAN-TEXT`。`write.py` 的绝对 LOC gate 已失真；改用精确函数、phase table、owner binding、AST、DAG 与 zero-compat 门禁。
- `AGG-02`：`ACCEPTED / CLOSED-BY-PLAN-TEXT`。`research_template.py` 的绝对 LOC gate 已失真；改用精确函数、dispatch mapping、`__all__`、owner inventory、AST、DAG 与 zero-compat 门禁。
- `AGG-03`：`ACCEPTED / CLOSED-BY-PLAN-TEXT`。aggregate 终态由 40 修正为精确 41，并显式区分 Slice 9 历史 40 与 Slice 10 后新增 selector。
- `AGG-04`：`ACCEPTED / CLOSED-BY-PLAN-TEXT`。不新增 Slice 14；本次只修正 aggregate gate 文本。
- `AGG-05`：`ACCEPTED / CLOSED-BY-PLAN-TEXT`。为追逐旧 LOC 继续拆分会逆转已接受的 owner 与行为契约；aggregate stop condition 改为结构、行为、类型、lint delta 和 machine gate 的可复现失败。

### 2.2 MiMo `plan-review-20260808-150149.md`

- `H01`：失真事实 `ACCEPTED`；建议把上限任意放宽为 1400 行 `REJECTED-WITH-REASON`。新数值同样会再次漂移，Controller 采用精确结构门禁。
- `M01`：aggregate 终态 41 的事实 `ACCEPTED`；把 Slice 9 历史基线改为 124 `REJECTED-WITH-REASON`。Slice 9 当时精确为 `83+40=123`，selector 是 Slice 10 后续增量。
- `L01`：失真事实 `ACCEPTED`；建议把上限任意放宽为 1050 行 `REJECTED-WITH-REASON`。Controller 采用精确结构门禁，不建立新的任意 LOC ceiling。

Controller 当前 open High/Medium/Low 为 `0/0/0`。没有 code、tests、README 或额外 slice 修复。

### 2.3 双路 re-review observations

- DeepSeek `plan-review-20260808-152220.md`：`PASS / open High/Medium/Low = 0/0/0`；初审 8 项全部闭环，未产生新 finding。
- MiMo `plan-review-20260808-152221.md` 的核心结论为 `PASS`；其中 `M-01` 为 `REJECTED-WITH-REASON / CLOSED / NON-DEFECT`。本轮受审 source 是 master plan，§9 已内联完整 AST 脚本以及 pytest、pyright、diff 和 machine gates，并逐项列出 owner inventory、DAG、zero-compat 与 Ruff delta 要求；Controller artifact 已明确指向该唯一计划真源，无需重复整块命令。
- MiMo `L-01` 为 `REJECTED-WITH-REASON / CLOSED / MEASUREMENT-ERROR`。该 review 使用 `git diff HEAD~3..HEAD` 只检查已提交 commits，遗漏当前 working-tree plan diff；`git diff HEAD -- docs/plans/2026-08-07-cli-write-architecture-refactor.md` 明确非零，且 master plan header/status/tail 已是 v5.6 candidate。
- MiMo corrective `plan-review-20260808-153009.md`：`PASS / open High/Medium/Low = 0/0/0`，确认 `M-01` 为 non-defect、`L-01` 为 working-tree measurement error，两项均 CLOSED。
- 双路 final re-review 结论为 PASS/open `0/0/0`；初审 8 项与 re-review 2 项全部 CLOSED，Controller accepted v5.6，aggregate validation 可恢复。

## 3. Plan 修订

- header、当前状态与 tail 统一为 `v5.6 ACCEPTED / DUAL PLAN RE-REVIEW PASS`，基线锁定 `2a4bafb`，保留 v5.5 accepted 历史。
- 新增 `AGG-CTRL-01..03`，锁定精确结构门禁、历史/终态计数边界以及 aggregate stop conditions。
- §8 将 1014/1369 明确为 information-only measurement，删除绝对 LOC 完成门槛。
- §9 新增 aggregate pre-deepreview 的 AST、owner inventory、DAG、zero-compat、focused tests、pyright、Ruff delta、diff 与 machine gate 命令。
- §11 用精确结构闭环替换 LOC 门槛，并把 Slice 9 历史 40 与 Slice 10 后终态 41 分开记录。

## 4. 明确拒绝的替代方案

- 不引入 Slice 14，也不为满足失真的 LOC 数字改 code、tests 或 README。
- 不采用 1050/1400 等任意放宽的 LOC 上限。
- 不把 Slice 9 历史基线从 123 改成 124。

## 5. 验证结果

- 限定路径审计：PASS；仅 master plan 与本 Controller artifact 属于本轮写范围，两份外部 review 保持冻结。
- 状态与历史锚点审计：PASS；v5.6 当前状态一致，v5.5 accepted 与 Slice 9 `83+40=123` 历史证据保留。
- 当前结构锚点审计：PASS；terminal `research_template.py` 精确 41 已进入架构树、aggregate gate 与完成标准。
- arbitrary LOC 审计：PASS；master plan 不含 1050/1400 新上限，1014/1369 仅标记为信息性测量。
- 尾随空白、文件末尾换行与 `git diff --check`：PASS。

## 6. Residual

- DeepSeek 152220 与 MiMo corrective 153009 均 PASS/open 0；v5.6 plan review loop 已关闭，aggregate validation 可恢复。
- 当前无代码层残余风险；本轮没有改动 production、tests、README 或外部 review artifacts。
