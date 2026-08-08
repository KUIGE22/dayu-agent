# Plan Re-Review: v5.4 Slice 10 Propagation Boundary Erratum — Dual Re-Review (DeepSeek)

- **日期**: 2026-08-08 11:30
- **审查类型**: v5.4 S10-CTRL-06 plan erratum re-review — 初审 3 findings 闭环验证 + 6 项合约逐条核查
- **审查计划**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md`（v5.4 CANDIDATE / AWAITING DUAL RE-REVIEW）
- **审查 Controller artifact**: `docs/reviews/plan-slice-10-v5.4-propagation-boundary-erratum-20260808-codex.md`
- **初审来源**: `docs/reviews/plan-review-20260808-111500-deepseek.md`（DeepSeek, FAIL, H=1/M=1/L=1）
- **对审来源**: `docs/reviews/plan-review-20260808-111501-mimo.md`（MiMo, 方案 B 推荐）
- **审查 HEAD**: `e329992`（gateflow: accept cli write architecture plan v5.3）
- **WIP 状态**: 冻结（production 6 files + untracked arguments.py，禁止修改）
- **审查人**: DeepSeek (planreview skill, focused dual re-review)
- **范围**: S10-CTRL-06 plan erratum 完整性；初审 3 findings CLOSED 映射；6 项合约逐条验证；不覆盖 Slice 0–9/11–13 或其他非 Slice 10 传播内容

---

## 0. 复审基线：Change Delta

### 0.1 v5.3 → v5.4 唯一变更

| 条目 | v5.3 原文 | v5.4 修正（S10-CTRL-06） |
|---|---|---|
| `_build_fresh_application_routing_snapshot` args | `DayuCliArguments` | `argparse.Namespace`（不变，保留下层宽类型） |
| `_build_snapshot_for_args` args | `DayuCliArguments` | `argparse.Namespace`（不变） |
| `build_snapshot_builder` args | `DayuCliArguments` | `argparse.Namespace`（不变） |
| `_run_write_model_configuration_application` args | `DayuCliArguments` | `DayuCliArguments`（保持） |
| 传播计数 | 45（`1+39+1+2+2`） | 42（`1+39+1+1`） |
| rollback + manual exact16 | 不在传播表（但 call-graph 不闭合） | 明确保持 Namespace，不纳入传播 |
| Plan status | v5.3 ACCEPTED | v5.4 CANDIDATE / AWAITING DUAL RE-REVIEW |

**变更范围**: 纯 plan 文本。三个 snapshot helper 的终态类型从 `DayuCliArguments` 回退为 `argparse.Namespace`；传播计数从 45 修正为 42；新增 S10-CTRL-06 分层边界说明。不涉及 Slice 0–9/11–13、Protocol 定义、dispatch mapping、entry 行为或任何 production code 语义变更。

---

## 1. 初审 Findings → v5.4 CLOSED 映射

### 1.1 S10-CALLGRAPH-01（高）→ CLOSED

| 维度 | 状态 |
|---|---|
| **初审描述** | call-graph 闭合缺口：snapshot-builder 收窄为 Dayu 后 4 个 Namespace caller 产生 reportArgumentType |
| **v5.4 修复** | S10-CTRL-06 将三个 snapshot helper 保持 `argparse.Namespace`；`_run_write_model_configuration_application` 为唯一 Dayu CLI 入口 |
| **闭合证据** | ① 传播表（plan lines 1605/1607）显式标注 `_build_fresh_application_routing_snapshot`、`_build_snapshot_for_args`、`build_snapshot_builder` → `argparse.Namespace`（不变）；② rollback runner + manual exact15 明确不传播（plan lines 1622-1623）；③ `DayuCliArguments` IS-A `argparse.Namespace`，CLI 入口传 Dayu 给宽 helper 类型安全（plan lines 1620-1621）；④ 修复后 pyright 预期 `dayu/cli/` 零 errors |
| **裁决** | **CLOSED** — 根因已消除，call-graph 闭合，无残留 pyright 风险 |

### 1.2 S10-LAYER-01（中）→ CLOSED

| 维度 | 状态 |
|---|---|
| **初审描述** | 基础设施层类型收窄反模式：snapshot-builder 不读取 Dayu 专有字段却被收窄为 Dayu |
| **v5.4 修复** | S10-CTRL-06 分层边界说明（plan lines 1617-1623）：三个 helper 最终把 args 交给 `setup_write_config(args: argparse.Namespace, ...)`，不读取 `research_template_action` 或未来 Write Protocol 字段 |
| **闭合证据** | ① 依赖链事实：`build_snapshot_builder` 仅 `functools.partial` → `_build_snapshot_for_args` 仅透传 → `_build_fresh_application_routing_snapshot` → `setup_write_config(args)` 仅 `getattr`；② plan 明确 "终态精确保持 `argparse.Namespace`"；③ `DayuCliArguments` 作为子类可安全传入宽 helper |
| **裁决** | **CLOSED** — 架构分层已纠正，不再有 CLI 具体类型反向传播到基础设施层 |

### 1.3 S10-COUNT-01（低）→ CLOSED

| 维度 | 状态 |
|---|---|
| **初审描述** | 传播计数不闭合：45 = `1+39+1+2+2` 不含 4 个间接 caller |
| **v5.4 修复** | 计数修正为 exact42（`1+39+1+1`）+ 1 parse return |
| **闭合证据** | ① plan line 1531: "42 个 args 签名 + 1 个 parse return"；② plan line 1609: "42 个 args 签名（research entry 1 + research runners 39 + write entry 1 + config application runner 1）"；③ Controller erratum §3 逐项复核 40+1+1=42 |
| **裁决** | **CLOSED** — 计数与传播表完全自洽 |

### 1.4 初审 Open H/M/L 终态

| 严重度 | 初审 open | v5.4 状态 |
|---|---|---|
| High | 1（S10-CALLGRAPH-01） | **CLOSED** |
| Medium | 1（S10-LAYER-01） | **CLOSED** |
| Low | 1（S10-COUNT-01） | **CLOSED** |
| **合计** | **3** | **0 open** |

---

## 2. 六项合约逐条验证

### 2.1 合约 1：三个 snapshot-chain helper 终态精确 argparse.Namespace ✅

**验证标准**: plan 传播表中 `_build_fresh_application_routing_snapshot`、`_build_snapshot_for_args`、`build_snapshot_builder` 的 "Slice 10 后" 列必须为 `argparse.Namespace`。

**证据**:
- Plan line 1605: `_build_fresh_application_routing_snapshot` → `argparse.Namespace`（下层基础设施，保持不变）
- Plan line 1607: `_build_snapshot_for_args`、`build_snapshot_builder` → `argparse.Namespace`（下层基础设施，保持不变）
- Plan lines 1617-1620: S10-CTRL-06 文字描述，明确其不读取 Dayu 字段、终态精确保持 Namespace
- Controller erratum §2 表格: 三个函数终态精确 `argparse.Namespace`

**结论**: ✅ PASS。三处终态类型一致，无歧义。

### 2.2 合约 2：仅 config application runner 为 DayuCliArguments ✅

**验证标准**: `_write_config_application.py` 的两个函数中，仅 `_run_write_model_configuration_application` → `DayuCliArguments`，`_build_fresh_application_routing_snapshot` → `argparse.Namespace`。

**证据**:
- Plan line 1606: `_run_write_model_configuration_application` → `DayuCliArguments`
- Plan line 1605: `_build_fresh_application_routing_snapshot` → `argparse.Namespace`（不变）
- 同模块内两函数类型不同是**有意的**——一个 CLI runner（Dayu），一个下层 infrastructure（Namespace）

**结论**: ✅ PASS。同模块两函数类型分工明确，符合架构意图。

### 2.3 合约 3：exact42 args + 1 parse return 计数 ✅

**验证标准**: 逐项计数自洽，且出现位置全部一致（无 stale 45 残留）。

**逐项分解**:

| 目标 | 数量 | 类型 |
|---|---|---|
| `run_research_template_command` | 1 | args → `DayuCliArguments` |
| 39 个 `_run_*` research-template runners | 39 | args → `DayuCliArguments` |
| `run_write_command` | 1 | args → `DayuCliArguments` |
| `_run_write_model_configuration_application` | 1 | args → `DayuCliArguments` |
| **args 签名合计** | **42** | |
| `parse_arguments` 返回 | 1 | return → `DayuCliArguments` |

**证据**:
- Plan line 1531: "42 个 args 签名 + 1 个 parse 返回"
- Plan line 1609: "42 个 args 签名（research entry 1 + research runners 39 + write entry 1 + config application runner 1）"
- Plan line 36: v5.3→v5.4 changelog "传播计数由 v5.3 历史 exact45 修正为当前 exact42"
- Controller erratum §3: "40 + 1 + 1 = 42 args + 1 parse return"
- Plan line 1595: "不计入下方 42 个签名"（selector 不计入，与 v5.3 一致）

**stale 45 检查**:
- Plan line 34: "45 args + 1 return" — 在 v5.2→v5.3 changelog 中，属于历史记录，非当前 contract
- Plan line 1617: "S10-CTRL-06" 是新文本，使用 42
- `rg 45` 在 Slice 10 当前节无其他残留

**MiMo 算术小误差**（Controller 已识别，不影响结论）:
MiMo review line 248 的中间展开式 `1+40+1+2-0` 若按字面计算得 44，但其最终结论 42 正确。Controller erratum line 52-53 已纠正: "config_application:2 并不精确；正确终态是 1 Dayu runner + 1 Namespace helper"。这是 presentation 层面的小误差，不构成 plan defect。

**结论**: ✅ PASS。42 计数在 plan 的 changelog、Slice 10 传播表、S10-CTRL-06 文本、Controller erratum 四处自洽一致。

### 2.4 合约 4：rollback runner 与 manual exact15 保持 Namespace ✅

**验证标准**: `_write_config_rollback.py` 的 1 个 runner 与 `_write_manual_recovery.py` 的 exact15 个 functions 全部保持 `argparse.Namespace`，不在 Slice 10 传播范围。

**证据**:
- Plan lines 1622-1623: "`_run_write_model_configuration_rollback` 与 `_write_manual_recovery.py` 的 exact15 个 functions 全部保持 Namespace，不纳入本 Slice 传播"
- Controller erratum §2: "rollback runner 与 _write_manual_recovery.py exact15 个 functions 全部保持 Namespace"
- 当前 WIP 确认: `_write_config_rollback.py` line 27 `args: argparse.Namespace`；`_write_manual_recovery.py` 全部 15 个函数 `args: argparse.Namespace`
- 方案 A exact49（含 4 caller）、方案 C 全量收窄均被 Controller REJECTED

**结论**: ✅ PASS。这 16 个函数的 Namespace 状态是 v5.4 plan 的明确意图，不是遗漏。

### 2.5 合约 5：4 个 pyright reportArgumentType 根因可关闭 ✅

**验证标准**: S10-CTRL-06 修复后，4 个先前报错的 call site 不再产生类型错误。

**根因链路复现**:
```
v5.3 错误路径:
  rollback/manual runner (args: Namespace)
    → build_snapshot_builder(args=args)  ← args 要求 Dayu, 实际 Namespace → reportArgumentType

v5.4 修正路径:
  rollback/manual runner (args: Namespace)
    → build_snapshot_builder(args=args)  ← args 要求 Namespace, 实际 Namespace → ✅

  config_application runner (args: Dayu)
    → _build_fresh_application_routing_snapshot(args=args)  ← args 要求 Namespace, 实际 Dayu IS-A Namespace → ✅
```

**证据**:
- `build_snapshot_builder` 终态接受 `argparse.Namespace`（合约 1）
- 四个 caller 保持 `argparse.Namespace`（合约 4）
- `DayuCliArguments` IS-A `argparse.Namespace`（继承关系），CLI 入口传 Dayu 给宽 helper 类型安全
- 修复后 `pyright dayu/cli/` 预期 0 errors
- 不引入 cast、type: ignore、adapter、wrapper 或 glue

**结论**: ✅ PASS。根因（下层被错误收窄）已消除，无替代方案（A/C/cast/glue）的副作用。

### 2.6 合约 6：结构性不变量未退化 ✅

**验证标准**: S10-CTRL-05（Protocol structural conformance）、S10-CTRL-03/04（mapping/entry 行为）、fixtures、coverage、no-cast/no-glue 约束不因 v5.4 erratum 退化。

**6a. Structural conformance（S10-CTRL-05/S11-CTRL-01）**:

| 约束 | v5.3 状态 | v5.4 状态 | 退化？ |
|---|---|---|---|
| `DayuCliArguments` 只继承 `argparse.Namespace` | ✅ | ✅ 不变 | 否 |
| `ResearchTemplateDispatchArguments(Protocol)` → `research_template_action: str` | ✅ exact1 | ✅ 不变 | 否 |
| Dayu 显式声明同名字段，structural subtyping 对接 | ✅ | ✅ 不变 | 否 |
| 禁止 Protocol inheritance / cast / ignore / adapter / glue | ✅ | ✅ 不变 | 否 |
| Slice 11 Write Protocol exact20 / Dayu exact21 | ✅ | ✅ 不变 | 否 |

**6b. Mapping/entry 行为（S10-CTRL-03/04）**:

| 约束 | v5.3 状态 | v5.4 状态 | 退化？ |
|---|---|---|---|
| 39-key mapping 完整 | ✅ | ✅ 不变 | 否 |
| `_resolve_research_template_action` selector 精确契约 | ✅ | ✅ 不变 | 否 |
| `setup_loglevel(args)` → selector → mapping → runner 顺序 | ✅ | ✅ 不变 | 否 |
| 未知 action 静默 `1` + caught exceptions stderr `1` | ✅ | ✅ 不变 | 否 |
| 禁止 Log/MODULE/新输出/return 2 | ✅ | ✅ 不变 | 否 |

**6c. Fixtures**:
- 42 个 Dayu 目标的 direct tests → 构造真实 `DayuCliArguments`
- 3 个宽 snapshot helper 的 direct tests → 保持 `argparse.Namespace`
- 16 个 rollback/manual Namespace functions → 保持 `argparse.Namespace`
- 禁止 blanket fixture 迁移（Controller erratum §5）
- **无退化**: fixtures 按函数终态类型精确分配，比 v5.3 的 blanket mechanical narrowing 更精确

**6d. Coverage**:
- Controller erratum §5: 按相对 accepted HEAD **实际 modified production files** 逐文件 `>=80%`
- 预期 modified: `arguments.py`、`arg_parsing.py`、`research_template.py`、`write.py`、`_write_config_application.py`
- `_write_snapshot_builder.py`：若精确恢复 HEAD（diff=0）→ 不机械要求 coverage；若有真实 diff → 必须过线
- `_write_config_rollback.py`、`_write_manual_recovery.py`：不在 Slice 10 modified 范围，不触发 coverage gate
- **无退化**: coverage gate 按实际 modified file 判定，snapshot_builder 不因 "名义上在 Slice 10 scope 内" 而被豁免

**6e. No-cast/no-glue**:
- Controller erratum §4: "cast、type-ignore、adapter、wrapper 或 glue 继续禁止"
- v5.4 erratum 不引入任何新的类型转换
- `DayuCliArguments` → `argparse.Namespace` 的参数传递由子类关系自然保证，不需 cast
- **无退化**: 零 cast/glue 约束不变

**结论**: ✅ PASS。六项子检查全部通过，无结构性退化。

---

## 3. 交叉验证：Controller Erratum 与 Master Plan 一致性

| Controller 声明 | Master Plan 对应 | 一致？ |
|---|---|---|
| S10-CTRL-06 采纳方案 B | Plan lines 1617-1623 S10-CTRL-06 分层边界 | ✅ |
| 三个 snapshot helper 终态 Namespace | Plan lines 1605/1607 传播表 | ✅ |
| config application runner 终态 Dayu | Plan line 1606 传播表 | ✅ |
| 42 args + 1 parse return | Plan lines 1531/1609 计数 | ✅ |
| rollback + manual exact15 保持 Namespace | Plan lines 1622-1623 | ✅ |
| 方案 A/C REJECTED | Plan line 36 changelog: "拒绝方案 A exact49…与方案 C 全 runner 扩 scope" | ✅ |
| 禁止 cast/ignore/adapter/glue | Plan line 1561: "禁止用 cast、type: ignore…adapter 或 glue" | ✅ |
| Coverage 按 actual modified file | Controller erratum §5 | （Controller artifact 自身约束，不在 master plan 正文） |
| MiMo config_application:2 表述不精确但 42 结论正确 | Controller line 52-53 已识别并纠正 | ✅ |

**零不一致**。Controller erratum 的所有裁决均在 master plan v5.4 中有逐项对应。

---

## 4. Adversarial Pass：v5.4 的潜在弱点扫描

### 4.1 同模块两函数不同类型是否造成混淆？

`_write_config_application.py` 中 `_build_fresh_application_routing_snapshot`（Namespace）与 `_run_write_model_configuration_application`（Dayu）类型不同。

**评估**: **无风险**。两者职责清晰分离：
- `_build_fresh_application_routing_snapshot` 是纯 infrastructure——构造 WriteCliConfig、调 preflight、构建路由快照，对 `args` 的使用全通过 `setup_write_config(args: Namespace, ...)` 的 `getattr` 间接完成
- `_run_write_model_configuration_application` 是 CLI runner——直接 `getattr(args, "challenger_config_application_plan_input", ...)` 访问 CLI 参数，是 `args` 的直接消费者

S10-CTRL-06 的分层边界说明（plan lines 1617-1623）已解释此分工。同模块内两个不同层次的函数使用不同参数类型，是 layer co-location 的正常结果。

### 4.2 `_write_snapshot_builder.py` 的 Dayu import 需移除

当前 WIP 的 `_write_snapshot_builder.py` line 8: `from dayu.cli.arguments import DayuCliArguments`。实施 S10-CTRL-06 后，该 import 不再被使用，需移除。

**评估**: **实施注意事项**。Controller erratum §5 AST gate "snapshot-builder 的 Dayu import/reference=0" 已覆盖。plan 传播表（line 1607）标注 "保持不变" 暗示 import 也需回退。这不构成 plan defect，但实施 Agent 需注意同步清理 import。

### 4.3 `_write_config_application.py` 的 Dayu import 部分使用

实施后 `_write_config_application.py` 中 `_run_write_model_configuration_application` 仍需 `DayuCliArguments`，但 `_build_fresh_application_routing_snapshot` 不需要。该模块的 `from dayu.cli.arguments import DayuCliArguments` 保留为 runner 所用。

**评估**: **无风险**。import 保留是正确的——生产代码有真实 consumer（runner）。不需特殊处理。

### 4.4 未来 Slice 8 的 `write.py` rollback factory call

当前 `write.py`（Slice 8 后终态）有一个 `build_snapshot_builder` 默认-label call 服务于 rollback runner。Slice 7 后该 call 仍在 `write.py` 或因 runner migration 移动。v5.4 对 `build_snapshot_builder` 的 Namespace 签名的保持不影响此 call——`write.py` 的 `run_write_command(args: DayuCliArguments)` 内通过 dispatch 间接调用 rollback runner（args: Namespace），类型正确。

**评估**: **无风险**。`build_snapshot_builder` 签名不依赖 `DayuCliArguments`，对任何 Namespace 子类 caller 均类型安全。

---

## 5. Residual Risks

| 风险 | 跟踪目标 | 严重度 |
|---|---|---|
| 实施后 `_write_snapshot_builder.py` 的 `DayuCliArguments` import 未移除 → pyright 可能报 unused-import（取决于 pyright 配置） | S10-CTRL-06 implementation 时 AST gate `Dayu import/reference=0` 覆盖 | LOW |
| 后续开发者看到同模块两函数不同类型，可能误解为遗漏并 "修复" 为全 Dayu | 模块 docstring 注明 `_build_fresh_application_routing_snapshot(args: argparse.Namespace)` 是有意的分层设计——此函数是 snapshot infrastructure，不依赖 CLI 具体类型 | LOW |

---

## 6. Final Plan Re-Review Conclusion

**Verdict: PASS**

**Open High/Medium/Low = 0/0/0**

**原因**: v5.4 S10-CTRL-06 plan erratum 完整且精确地关闭了初审全部 3 项 findings：
  - S10-CALLGRAPH-01（高）：call-graph 闭合缺口 → CLOSED。三个 snapshot helper 保持 Namespace，caller 类型匹配。
  - S10-LAYER-01（中）：基础设施层类型收窄反模式 → CLOSED。S10-CTRL-06 分层边界说明明确纠正。
  - S10-COUNT-01（低）：传播计数不闭合 → CLOSED。42 计数四处自洽。

六项合约逐条验证全部 PASS：
  1. 三个 snapshot helper → Namespace ✅
  2. 仅 config application runner → Dayu ✅
  3. exact42 args + 1 parse return ✅
  4. rollback + manual exact15 → Namespace ✅
  5. 四个 reportArgumentType 根因可关闭 ✅
  6. structural conformance / mapping / entry / fixtures / coverage / no-cast-no-glue 未退化 ✅

Controller erratum 与 master plan v5.4 的 10 项交叉声明全部一致。Adversarial pass 发现 2 个 LOW residual risks（import 清理、docstring 注明），均在实施 gate 覆盖范围内，不构成 plan defect。

**v5.4 已达 code-generation-ready 标准。Slice 10 可恢复实施。**
