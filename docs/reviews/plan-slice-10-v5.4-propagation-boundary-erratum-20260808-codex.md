# Slice 10 v5.4 Dayu Propagation Boundary Erratum（Controller）

- **状态**: v5.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **日期**: 2026-08-08
- **分支**: `codex/dual-model-research-mvp`
- **基线**: `e329992 gateflow: accept cli write architecture plan v5.3`
- **修改范围**: 仅 master plan 与本 Controller artifact；当前 6 个 Slice 10 production WIP、tests、README、外部 review 全部冻结
- **审查输入**:
  - `docs/reviews/plan-review-20260808-111500-deepseek.md`
  - `docs/reviews/plan-review-20260808-111501-mimo.md`
  - `docs/reviews/plan-review-20260808-113000-deepseek.md`
  - `docs/reviews/plan-review-20260808-113001-mimo.md`

## 1. 触发证据

v5.3 把 `_build_fresh_application_routing_snapshot`、`_build_snapshot_for_args`、
`build_snapshot_builder` 收窄到 `DayuCliArguments` 后，四个仍接收
`argparse.Namespace` 的真实 caller 产生 `reportArgumentType`：

- `_write_config_rollback.py:71`：rollback runner；
- `_write_manual_recovery.py:392`：manual recovery application runner；
- `_write_manual_recovery.py:481`：manual recovery verification runner；
- `_write_manual_recovery.py:581`：manual recovery clearance runner。

三个 snapshot-chain helper 不读取 `research_template_action` 或未来 Write Protocol
字段；它们只捕获/透传 args，终点 `setup_write_config` 本身也接受
`argparse.Namespace`。因此该错误不是四个 caller 太宽，而是下层 helper 被错误收窄。

## 2. Controller 决策：S10-CTRL-06

采纳两路推荐的方案 B，按真实 consumer 停止 Dayu 传播：

| 函数 | v5.4 终态 args | 理由 |
|---|---|---|
| `_run_write_model_configuration_application` | `DayuCliArguments` | config application CLI runner，属于 Slice 10 entry-side mechanical propagation |
| `_build_fresh_application_routing_snapshot` | `argparse.Namespace` | 下层 snapshot infrastructure，最终交给宽类型 `setup_write_config` |
| `_build_snapshot_for_args` | `argparse.Namespace` | 仅透传 args |
| `build_snapshot_builder` | `argparse.Namespace` | 仅通过 partial 捕获 args，返回零参数 callback |

`DayuCliArguments` 是 `argparse.Namespace` 子类，窄入口传给宽 helper 符合 IS-A；
`Callable` 参数逆变事实也不要求把下层实现收窄。rollback runner 与
`_write_manual_recovery.py` exact15 个 functions 全部保持 Namespace。

## 3. 传播计数

当前精确传播为 **42 args + 1 parse return**：

- research-template entry 1 + runners 39 = 40；
- write entry = 1；
- config application runner = 1；
- `parse_arguments` return = 1（单独计数）。

三个 snapshot helper 不迁移，所以 v5.3 历史公式 `1+39+1+2+2=45` 由本 erratum
覆盖。MiMo review 表格中“config_application 2”若被理解为两个 Dayu 目标并不精确；
正确终态是 **1 Dayu runner + 1 Namespace helper**，但其最终 42 结论正确。

## 4. Finding 逐项裁决

| 来源 | Finding / 结论 | Controller 裁决 | 闭环 |
|---|---|---|---|
| DeepSeek 111500 | S10-CALLGRAPH-01 | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 三个下层 helper 恢复 Namespace，四个 reportArgumentType 根因消除 |
| DeepSeek 111500 | S10-LAYER-01 | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 明确 dispatch concrete type 不沿 snapshot infrastructure 反向扩散 |
| DeepSeek 111500 | S10-COUNT-01 | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 当前传播计数修正为 exact42 args + 1 return |
| MiMo 111501 | 方案 B / 42 结论 | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 采纳宽 helper + 窄 CLI runner；纠正其 config-application 分组措辞 |

### 拒绝的替代方案

- **方案 A（exact49）REJECT-WITH-REASON**：只因四个 runner 偶然调用 factory 就
  收窄其签名，向不使用 Dayu 字段的同域函数扩散 concrete type，并扩大 fixture/scope。
- **方案 C（rollback + 全部 manual runner）REJECT-WITH-REASON**：把 exact15 manual
  functions 全部收窄，明显超出当前需求与最小契约边界。
- cast、type-ignore、adapter、wrapper 或 glue 继续禁止。

## 5. 测试、静态与覆盖率门禁

- 42 个 Dayu 目标的 direct tests 构造真实 `DayuCliArguments`；三个宽 helper 的
  direct tests 继续用 `argparse.Namespace`，禁止 blanket fixture 迁移。
- 六个 owner 文件仍纳入 direct-call 审计；尤其
  `test_write_model_configuration_preapplication.py` 只迁 application runner fixture，
  snapshot helper fixtures 保持 Namespace。
- AST 断言 application runner exact Dayu；三个 helper exact Namespace；rollback
  runner + manual exact15 仍为 Namespace；snapshot-builder 的 Dayu import/reference=0。
- `pyright dayu/cli/` 必须为 0 errors，并显式覆盖先前四个失败点。
- coverage 只按相对 accepted HEAD **实际 modified production files** 逐文件精确
  `>=80%`。预期 modified 为 `arguments.py`、`arg_parsing.py`、
  `research_template.py`、`write.py`、`_write_config_application.py`；
  `_write_snapshot_builder.py` 若精确恢复 HEAD 后 diff=0，则不机械要求 coverage，若仍有
  真实 diff 则必须过线。
- Ruff F/I 与 HEAD full-rule finding-code multiset positive delta=0；相关 tests、
  import smoke、39 mapping/runtime/entry behavior、README decision、`git diff --check`
  均保留。

## 6. 冻结范围证据

计划编辑前记录：

- tracked 5-file production WIP diff SHA-256：
  `af0fc591de4e3f63bdc181efa6f446c6694b7f417b7b30d35fc508e308a756ea`；
- untracked `dayu/cli/arguments.py` SHA-256：
  `1114582b37ca7b1e26d6a1313a1cf139890c86252b3640886f9905dbc195c96a`。

收尾复算得到完全相同的两个 SHA-256，冻结检查 **PASS**。本 plan-only erratum 不修改
production/tests/README 或两份外部 review。

## 7. 自审结果

- master plan 顶部、状态、尾注均为
  `v5.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS`，HEAD=`e329992`；
- 当前 Slice 10 contract 中 exact42 args + 1 parse return 一致；三个 snapshot helper
  均精确为 Namespace，application runner 精确为 Dayu；
- `rg` 中其余 `45` 命中仅有 v5.2/v5.3 历史传播记录、v5.4 覆盖说明及 Slice 9
  functional-binding exact45，均非当前 Slice 10 stale contract；
- coverage gate 按相对 HEAD 实际 modified production file 判定，未机械豁免
  `_write_snapshot_builder.py`；
- `git diff --check`、两份工作文档 trailing-whitespace/final-newline 检查通过。

## 8. Final dual plan re-review

- DeepSeek `docs/reviews/plan-review-20260808-113000-deepseek.md`：**PASS**，
  open High/Medium/Low=`0/0/0`；
- MiMo `docs/reviews/plan-review-20260808-113001-mimo.md`：**PASS**，
  open High/Medium/Low=`0/0/0`；
- 初审 S10-CALLGRAPH-01、S10-LAYER-01、S10-COUNT-01 与 MiMo
  `config_application` 分组措辞纠正全部 **CLOSED**；
- DeepSeek 复审记录的两个实施期 Low residual——清理 `_write_snapshot_builder.py` 的
  `DayuCliArguments` import，以及在 docstring 中明确同模块宽/窄函数分层——均已由既有
  AST import/reference=0、完整具体中文 docstring 与 `pyright dayu/cli/` 门禁覆盖，
  不构成 plan defect。

Controller open High/Medium/Low=`0/0/0`。v5.4 已接受，Slice 10 可恢复实施；
S10-CTRL-05/S11-CTRL-01 structural conformance、S10-CTRL-03/04 行为及其他 slice
语义均不变。
