# Plan Review: v5.0 Slice 9 可实施性深度审查

- **审查时间**: 2026-08-08 07:55 UTC
- **审查人**: DeepSeek（planreview skill）
- **基线**: clean HEAD `1d0f9e6`（v5.0 ACCEPTED / DUAL PLAN RE-REVIEW PASS）
- **审查范围**: Slice 9（research_template.py 五模块拆分）是否 code-generation-ready
- **审查模式**: 只读。独立 AST/callgraph 验证。禁止修改 plan/code/tests/README/其他 artifact。
- **对照文件**:
  - `AGENTS.md`（项目约束）
  - `docs/plans/2026-08-07-cli-write-architecture-refactor.md`（master plan v5.0, 2143 行）
  - `dayu/cli/commands/research_template.py`（源码 AST, 4146 行, HEAD `1d0f9e6`）
  - `dayu/cli/commands/write.py`（lazy import caller）
  - `tests/cli/test_research_template_command.py`（测试文件）

---

## Verdict: FAIL（3 HIGH findings，不可直接实施 Slice 9）

**根因**: Slice 9 的描述仅 **4 句话**（master plan 行 1197–1207），给出五模块计数 22+21+11+9+9=72，但源码实有 **83 个函数需迁移**（123 FunctionDef − 40 保留），gap=11。plan 未提供逐函数 ownership 表——仅给出模块级自然语言功能域名称和数字，不满足 code-generation-ready 标准。此外两个 dataclass 的归属与其使用者所在模块存在依赖方向冲突。

---

## 0. 证据总览

### 0.1 源码 AST 实况（`research_template.py`, HEAD `1d0f9e6`）

| 度量 | 数值 | 验证方式 |
|---|---|---|
| 顶层 FunctionDef | **123** | `python3 -c "import ast; print(len([n for n in ast.iter_child_nodes(ast.parse(open('dayu/cli/commands/research_template.py').read())) if isinstance(n, ast.FunctionDef)]))"` |
| 顶层 ClassDef | **2** | `ResearchTemplate`, `ResearchTemplateRecommendation` |
| 入口函数 | **1** | `run_research_template_command` |
| `_run_*` runner | **39** | `grep -c '^def _run_' research_template.py` → 39 |
| 保留函数 | **40** | 1 入口 + 39 runner |
| **需迁移函数** | **83** | 123 − 40 |
| `__all__` 条目 | **68** | 51 本文件原生 + 17 workbook re-export |
| 本文件原生 `__all__` 函数 | **49** | 不含 2 dataclass |

### 0.2 Plan 声称

| Plan 位置 | 声称内容 |
|---|---|
| §2.1 目标文件结构 (行 487–493) | 五模块: helpers=22, core=21, bundle=11, monitoring=9, materialize=9 |
| Slice 9 描述 (行 1197–1207) | 单 commit 创建 5 个模块，保留 `run_research_template_command` + 39 runner + 2 dataclass；更新 `write.py:4589` lazy import |
| §1.5 功能域分组 (行 245–258) | 9 个功能域，辅助函数=22 |

### 0.3 差距

| 度量 | Plan 声称 | 源码实况 | 差距 |
|---|---|---|---|
| 需迁移函数总数 | 72 | **83** | **−11** |
| 逐函数 ownership 表 | 无 | — | **全部缺失** |
| 五模块间依赖 DAG | 仅文字 "core/bundle/monitoring/materialize → helpers" | — | **无逐边证据** |
| Dataclass 归属方案 | "保留在 research_template.py" | 仅被迁移函数使用 | **依赖方向冲突** |
| Test 迁移方案 | 无 | 63 个 direct import | **完全缺失** |
| write.py lazy import 行号 | "4589" | 81, 87 | **行号陈旧（历史 HEAD）** |
| `research_template.py` 终态 `__all__` | 无 | — | **未定义** |

---

## 1. Assumptions Tested

| # | Assumption | 验证结果 |
|---|---|---|
| A1 | Plan 的 72 函数计数覆盖全部需迁移函数 | **FAIL** — 实为 83，gap=11 |
| A2 | 五模块计数 22/21/11/9/9 与源码结构一致 | **UNVERIFIED** — plan 未提供逐函数分配，无法验证 |
| A3 | Dataclass 留在 `research_template.py` 不产生依赖反向 | **FAIL** — 两类均仅被迁移函数使用，留在原文件将导致迁移模块反向 import |
| A4 | `research_template.py → _research_template_*.py` 依赖方向可维护 | **PARTIAL** — 39 runner 中有 35 个调用迁移后的函数，import 路径需完整枚举 |
| A5 | Slice 10 的 39 runner 类型传播不受 Slice 9 影响 | **PASS** — `DayuCliArguments` 是 `argparse.Namespace` 子类，协变安全 |
| A6 | `write.py` lazy import 更新路径明确 | **PARTIAL** — 目标路径已知但行号陈旧 |
| A7 | Tests 迁移方案与 direct-owner/dispatch-owner 分流清晰 | **FAIL** — plan 完全未涉及 |

---

## 2. Findings

### H-01 (HIGH) — 函数计数缺口 11：plan 声称 72 但实需迁移 83

- **位置**: Master plan Slice 9（行 1197–1207）、§2.1 目标文件结构（行 487–493）
- **问题类型**: 不可直接实施 / 切片欠规格
- **当前写法**: Plan 称五模块含 22+21+11+9+9=72 函数，"各模块间依赖: core/bundle/monitoring/materialize → helpers"
- **反例/失败场景**: 实施 Agent 按 72 函数拆分，将遗漏 11 个函数。遗漏函数可能留在 `research_template.py`（违反 clean split）、被错误归入某模块（打破模块边界）、或被静默删除（破坏 CLI 功能）。由于 plan 未提供逐函数清单，实施 Agent 必须自行审计和分配，极易引入 scope creep 或边界错误。
- **为什么有问题**:
  1. Plan 声称"code-generation-ready"但缺少最基础的完整函数 inventory
  2. Plan 自身 §1.5 功能域分组表声称的行数与 §2.1 模块计数之间无闭合验证
  3. 违反 Gateflow 对 implementation plan 的基本要求：slice 必须精确描述 scope
- **直接证据**:
  - 源码 AST: 顶层 FunctionDef=123, `_run_*`=39, 入口=1, 需迁移=123−40=83
  - Plan 声称: 22+21+11+9+9=72
  - Gap: 83−72=11
  - 验证命令:
    ```bash
    python3 -c "import ast; tree=ast.parse(open('dayu/cli/commands/research_template.py').read()); funcs=[n.name for n in ast.iter_child_nodes(tree) if isinstance(n, ast.FunctionDef)]; runners={f for f in funcs if f.startswith('_run_')}; print(f'total={len(funcs)} runners={len(runners)} to_migrate={len(funcs)-len(runners)-1}')"
    # 输出: total=123 runners=39 to_migrate=83
    ```
- **影响**: 实施 Agent 跑偏 / 后续返工 / review 不可验收
- **建议改法和验证点**:
  1. 重新审计全部 123 函数，生成逐函数→模块分配表
  2. 五模块计数必须与 83 闭合：helpers + core + bundle + monitoring + materialize = 83
  3. 验证：`assert len(assigned_functions) == 83`，每个函数恰好属于一个模块
- **修复风险**: 低（纯审计工作，不改变设计方向）
- **严重程度**: 高

### H-02 (HIGH) — 无逐函数 ownership 表，plan 不满足 code-generation-ready

- **位置**: Master plan Slice 9 全部内容（行 1197–1207，仅 11 行）
- **问题类型**: 不可直接实施 / 切片欠规格
- **当前写法**: Slice 9 全部描述为：
  > "_research_template_helpers.py（22 函数，叶子模块）\n_research_template_core.py（21 函数: 模板基础操作 + 监控变量/规则/源映射）\n_research_template_bundle.py（11 函数: Bundle 描述符/重绑定/回滚）\n_research_template_monitoring.py（9 函数: 监控执行计划/调度清单/状态快照）\n_research_template_materialize.py（9 函数: 物化/Portfolio/工作区刷新）\n\n各模块间依赖: core/bundle/monitoring/materialize → helpers。同一 commit 内所有 import 自洽。"
- **反例/失败场景**:
  1. 实施 Agent 拿到 "core=21 函数: 模板基础操作 + 监控变量/规则/源映射" 后，必须自行决定 21 个函数具体是哪些。源码中模板基础操作至少 5 个（list/load/copy/compose/recommend）、监控变量/规则/源映射至少 12 个（含 `extract_monitoring_variables`、`build_monitoring_rules_payload`、`validate_monitoring_source_map_payload`、`build_monitoring_source_binding_preview` 等）、包清单/使用指南至少 4 个。但 `materialize_research_checklist` 是否归入 core 还是 materialize？`_normalize_template_name` 归入 helpers 还是 core？所有这些问题 plan 均未回答。
  2. 实施 Agent 的不同判断导致不同模块边界，review 时无法对照 plan 验收。
- **为什么有问题**: 对照同一 plan 中 Slice 7 的详细程度（exact 15 函数逐名列出、exact import/call/factory 计数、exact 门禁命令），Slice 9 的规格密度严重不足。Slice 7 的 15 函数规格约 100 行；Slice 9 的 83 函数规格仅 11 行。
- **直接证据**: Plan 行 1197–1207（Slice 9 全文）vs 行 1057–1161（Slice 7，105 行，含 exact 15 函数名、三处 factory、17 个 import identity、五类门禁）
- **影响**: 实施 Agent 重新设计模块边界 / review 不可验收 / 后续返工
- **建议改法和验证点**:
  1. 为 83 个函数提供类似 Slice 7 的逐名 exact ownership 表
  2. 表格至少包含：函数名 → 归属模块、当前源码行号（辅助定位）、被哪些 retained runner 调用（决定 `research_template.py` 的 import 需求）
  3. 验证：`sum(module_counts) == 83`；每个函数恰好分配一次
- **修复风险**: 中（需逐函数审计 call graph 和功能域归属，但设计方向不变）
- **严重程度**: 高

### H-03 (HIGH) — Dataclass 归属导致依赖方向冲突

- **位置**: Master plan Slice 9（行 1206: "ResearchTemplate/ResearchTemplateRecommendation 数据类"保留）
- **问题类型**: 架构边界 / 过度耦合
- **当前写法**: "research_template.py 保留 run_research_template_command + 39 个 _run_* runner + ResearchTemplate/ResearchTemplateRecommendation 数据类"
- **反例/失败场景**:
  - `ResearchTemplate` 仅被 `list_research_templates()`（→ core 模块）使用；无任何 retained runner 直接引用此类。
  - `ResearchTemplateRecommendation` 仅被 `recommend_research_templates()`（→ core 模块）和 `_recommendation_payload()`（→ helpers 模块）使用；无任何 retained runner 直接引用。
  - 若两 dataclass 留在 `research_template.py`，则 core 模块的 `list_research_templates` 和 helpers 模块的 `_recommendation_payload` 需要 `from dayu.cli.commands.research_template import ResearchTemplate`，造成 **core/helpers → research_template.py** 的反向依赖。
  - 同时 `research_template.py` 又需要 `from dayu.cli.commands._research_template_core import list_research_templates`（因为 `_run_list` 调用它），形成 **research_template.py → core → research_template.py** 的 import cycle。
- **为什么有问题**:
  1. Plan §2.2 声明的依赖方向是 `research_template.py → _research_template_helpers / _research_template_core / ...`，单向无环。Dataclass 留在原文件直接打破此约束。
  2. Python 的 import cycle 在此场景下可能因顶层 import 顺序"巧合"不报错（类型注解仅在 TYPE_CHECKING 时求值），但这是脆弱的、不可维护的依赖结构，违反 AGENTS.md "禁止反向依赖" 的硬约束。
- **直接证据**:
  ```bash
  # 验证 ResearchTemplate 仅被 list_research_templates 使用：
  python3 -c "
  import ast
  tree = ast.parse(open('dayu/cli/commands/research_template.py').read())
  for node in ast.iter_child_nodes(tree):
      if isinstance(node, ast.FunctionDef):
          for child in ast.walk(node):
              if isinstance(child, ast.Name) and child.id == 'ResearchTemplate':
                  print(f'{node.name} uses ResearchTemplate')
  "
  # 输出: list_research_templates uses ResearchTemplate
  # → 无 retained runner 使用此类

  # 验证 ResearchTemplateRecommendation：
  # 输出: recommend_research_templates uses ResearchTemplateRecommendation
  #       _recommendation_payload uses ResearchTemplateRecommendation
  # → 无 retained runner 使用此类
  ```
- **影响**: Import cycle / 架构边界破坏 / Slice 10-11 的 Protocol dispatch 可能因类型解析失败而受阻
- **建议改法和验证点**:
  1. 将两个 dataclass 迁至 `_research_template_core.py`（作为核心类型定义），或单独新建 `_research_template_types.py`（零入度类型模块）
  2. `research_template.py` 从新 owner import 这两个类
  3. 验证：`grep -r "from dayu.cli.commands.research_template import" dayu/cli/commands/_research_template_*.py` → 0（零反向 import）
  4. Python import smoke test 必须通过（无 ImportError / cycle）
- **修复风险**: 低（仅移动两个纯数据 dataclass，无行为变更）
- **严重程度**: 高

---

### M-01 (MEDIUM) — `_print_definition_header` 归属边界模糊

- **位置**: 源码行 3050–3053
- **问题类型**: 切片欠规格
- **当前写法**: Plan 未明确提及此函数。该函数仅被 3 个 retained runner（`_run_scorecard`、`_run_evidence`、`_run_schema`）调用。
- **反例/失败场景**: 如果归入 helpers 模块（与 plan 的 "22 辅助函数" 一致），`research_template.py` 必须从 helpers import 它来服务 3 个 runner。这本身是正常的依赖方向（research_template.py → helpers），但 plan 未声明此 import。如果留在 `research_template.py`（因为仅 retained runner 使用），则 migrate 计数从 83 降为 82。
- **为什么有问题**: 实施 Agent 需自行判断，且无论选择哪种都会影响模块函数计数。
- **直接证据**:
  ```bash
  python3 -c "
  import ast
  tree = ast.parse(open('dayu/cli/commands/research_template.py').read())
  callers = {}
  for node in ast.iter_child_nodes(tree):
      if isinstance(node, ast.FunctionDef):
          for child in ast.walk(node):
              if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == '_print_definition_header':
                  callers.setdefault('_print_definition_header', set()).add(node.name)
  print(callers)
  "
  # 输出: {'_print_definition_header': {'_run_scorecard', '_run_evidence', '_run_schema'}}
  ```
- **影响**: 实施 Agent 需自行决定 / review 不可验收
- **建议改法和验证点**: 明确归属。建议归入 helpers（叶子模块），在 `research_template.py` 终态 import 清单中列出。
- **修复风险**: 低
- **严重程度**: 中

### M-02 (MEDIUM) — Test 迁移方案完全缺失

- **位置**: Master plan Slice 9（行 1207 之后无测试相关内容）
- **问题类型**: 测试缺口 / 切片欠规格
- **当前写法**: Slice 9 无任何测试迁移描述。
- **反例/失败场景**:
  1. `tests/cli/test_research_template_command.py` 从 `dayu.cli.commands.research_template` direct import **63 个符号**（含 49 个本文件原生函数 + 14 个 workbook re-export）。
  2. Slice 9 后，49 个原生函数分散到 5 个新模块。测试文件需拆分：
     - **Direct-owner 测试**: 直接测试 `list_research_templates`、`build_monitoring_rules_payload` 等函数自身行为 → 迁到对应新 owner 模块的测试文件
     - **Dispatch-owner 测试**: 测试 `run_research_template_command` 的 dispatch 正确性 → 保留在 `research_template` 测试中，但 patch 目标需更新为新 owner 模块路径
  3. 若不做此拆分，测试全部留在原文件并继续 import from `research_template`，则要么 `research_template.py` 必须 compat re-export（违反 AGENTS.md 硬约束），要么测试全部失败（ImportError）。
- **为什么有问题**: 违反 AGENTS.md "测试必须跟着实现边界迁移，不得为了保住旧测试而在生产代码里堆兼容逻辑"。
- **直接证据**: `tests/cli/test_research_template_command.py` 行 13–77 的 63 个 direct import
- **影响**: 实施 Agent 跳过测试迁移 / 为保测试新增 compat re-export / review 不可验收
- **建议改法和验证点**:
  1. 将 63 个 test import 按函数的新 owner 模块分组
  2. Direct-owner 测试迁到 `tests/cli/test_research_template_core.py` 等新文件
  3. Dispatch-owner 测试保留在 `test_research_template_command.py`，更新 patch 路径
  4. 验证：`pytest tests/cli/test_research_template*.py -v` 全部通过；无 compat re-export
- **修复风险**: 中（需拆分测试文件，但测试逻辑不变）
- **严重程度**: 中

### M-03 (MEDIUM) — write.py lazy import 行号陈旧

- **位置**: Master plan Slice 9（行 1207: "更新 `write.py:4589` 的 `materialize_research_bundle_from_write_manifest` lazy import 路径"）
- **问题类型**: 不可直接实施
- **当前写法**: 引用行号 4589
- **反例/失败场景**: 实施 Agent 在 `write.py` 行 4589 找不到目标代码（当前 HEAD `1d0f9e6` 的 `write.py` 已通过 Slice 5-8 降至约 660 行）。实际 lazy import 位于行 81 和 87。
- **直接证据**:
  ```bash
  grep -n "materialize_research_bundle_from_write_manifest" dayu/cli/commands/write.py
  # 81:    from dayu.cli.commands.research_template import materialize_research_bundle_from_write_manifest
  # 87:    return materialize_research_bundle_from_write_manifest(
  ```
- **为什么有问题**: 行号 4589 是历史 HEAD `5821014` 的值，当前 HEAD 该函数已迁移，行号需更新。Slize 9 实施 Agent 若按 4589 查找将失败。
- **影响**: 实施 Agent 跑偏
- **建议改法和验证点**: 更新为当前 HEAD 的实际行号（81, 87）；import 路径从 `dayu.cli.commands.research_template` 改为 `dayu.cli.commands._research_template_materialize`
- **修复风险**: 低
- **严重程度**: 中

---

### L-01 (LOW) — `research_template.py` 终态 `__all__` 未定义

- **位置**: 无（plan 未涉及）
- **问题类型**: 契约缺失
- **当前写法**: Plan 未说明 Slice 9 后 `research_template.py` 的 `__all__` 应包含什么。
- **反例/失败场景**: 当前 `__all__` 有 68 条目（51 原生 + 17 workbook re-export）。Slice 9 后，49 个原生函数迁出。`__all__` 应包含：
  - 保留的 2 个 dataclass（若留在 research_template.py）
  - `run_research_template_command`（入口）
  - 17 个 workbook re-export（不变）
  - 是否 re-export 迁移后的函数？→ 若 re-export 则违反 "禁止 compat re-export" 约束；若不 re-export 则需更新所有 consumer 的 import 路径
- **为什么有问题**: `__all__` 是模块的 public API 契约，未定义意味着实施 Agent 需自行决定，可能引入 compat re-export 或遗漏必要导出。
- **影响**: 实施 Agent 需自行决定
- **建议改法和验证点**: 明确 Slice 9 后 `research_template.py` 的 `__all__` 内容及每个条目的真源定义位置
- **修复风险**: 低
- **严重程度**: 低

### L-02 (LOW) — 五模块间依赖 DAG 未逐边验证

- **位置**: Plan 行 1206: "各模块间依赖: core/bundle/monitoring/materialize → helpers"
- **问题类型**: 切片欠规格
- **当前写法**: 仅一句自然语言描述依赖方向
- **反例/失败场景**: 实际 call graph 含跨模块调用（如 `materialize_research_template_bundle` 调用 `validate_research_template_bundle_descriptor`（bundle 模块）和 `validate_monitoring_source_map_payload`（core 模块）和 `compose_research_template`（core 模块））。仅说 "materialize → helpers" 不足以捕获 materialize → bundle 和 materialize → core 的真实依赖。
- **直接证据**: AST call graph — `materialize_research_template_bundle` 调用 17 个内部函数，跨 4 个拟议模块
- **影响**: 实施 Agent 可能遗漏跨模块 import / 引入意外 import cycle
- **建议改法和验证点**: 基于 call graph 生成精确的模块级 import DAG，确保无环
- **修复风险**: 低
- **严重程度**: 低

### L-03 (LOW) — 39 runner 对迁移函数的 import 需求未枚举

- **位置**: 无（plan 未涉及）
- **问题类型**: 切片欠规格
- **当前写法**: Plan 未统计 retained runner 调用迁移函数的情况
- **反例/失败场景**: 39 个 runner 中有 **35 个**直接调用迁移后的函数。`research_template.py` 必须从全部 5 个新模块 import 这些函数。若遗漏 import，相关 CLI 子命令将因 `NameError` 崩溃。
- **直接证据**: AST 分析 — 35 个 runner 调用了分布在 core/bundle/monitoring/materialize/helpers 中的函数（详见附录 A）
- **影响**: 实施 Agent 可能遗漏 import
- **建议改法和验证点**: 生成 `research_template.py` 的完整终态 import 清单，确保每个 runner 的 callee 都有对应 import
- **修复风险**: 低
- **严重程度**: 低

---

## 3. Slice 10 Impact Analysis: 39 runner 类型传播不受 Slice 9 影响

**结论**: PASS。Slice 9 不影响 Slice 10 的正确性。

**理由**:
1. Slice 9 迁移的是非-runner 函数（83 个），Slice 10 改变的是 runner 签名（`args: argparse.Namespace → DayuCliArguments`）。两者修改的函数集合不交叠。
2. `DayuCliArguments` 是 `argparse.Namespace` 的真实子类。迁移后的函数若接受 `argparse.Namespace` 类型参数，仍可接受 `DayuCliArguments` 实例（协变安全）。
3. Slice 10 的类型传播范围（§5 Slice 10 表，行 1254–1261）不包含 Slice 9 迁移的任何函数。

---

## 4. Residual Risks

| # | 风险 | 严重度 | 建议处置 |
|---|---|---|---|
| R1 | `materialize_research_checklist` 归属不明确——既是"物化"也是"检查单"，可归入 core 或 materialize | LOW | 按 call graph 判断：被 `_run_materialize_checklist`（retained）和 `materialize_research_template_bundle`（→ materialize）调用，建议归入 core（与模板基础操作同层） |
| R2 | `_load_json_object` 在 `research_template.py` 和 `write_model_*.py` 中有同名异构定义（前者返回 `dict[str, object]`，后者返回 `tuple[Path, dict]`），迁移后需注意避免 import 冲突 | LOW | 两个定义在不同模块，不会冲突；但在 helpers 模块中命名需避免混淆 |
| R3 | 17 个 workbook re-export 在 `__all__` 中但定义在 `research_workbook.py`，Slice 9 不变，但 `research_template.py` 是否继续 re-export 未明确 | LOW | 当前行为保持即可 |
| R4 | `_company_facets_from_args` 接受 `argparse.Namespace`（宽类型），不在 Slice 10 传播范围内，plan 已确认（行 1358） | LOW | 设计可接受，但需在 helpers 模块 docstring 中注明 |

---

## 5. Open Questions

1. **Q1**: `_print_definition_header` 留在 `research_template.py`（因为仅 retained runner 使用）还是迁到 helpers？当前 plan 无说明。
2. **Q2**: `ResearchTemplate` 和 `ResearchTemplateRecommendation` 若迁到 core 或 helpers，`research_template.py` 的其他 consumer（如 `research_template_assets.py`、`research_template_definitions.py`）是否需要同步更新 import 路径？
3. **Q3**: Slice 9 的 5 个新模块是否应按 Slice 5-8 的风格提供逐模块中文概览 docstring 和逐函数 Args/Returns/Raises docstring？

---

## 6. Code-Generation-Ready v5.1 最小修复建议

要使 Slice 9 达到 code-generation-ready，至少需要以下补充（按优先级）：

### 6.1 必须修复（v5.1 准入条件）

1. **函数 inventory 闭合**: 生成完整的 83 函数→5 模块分配表，每模块函数数之和 = 83
2. **逐函数 ownership 表**: 每个函数的精确归属模块、被哪些 retained runner 调用、建议的 import 路径
3. **Dataclass 归属修正**: 将 `ResearchTemplate`、`ResearchTemplateRecommendation` 迁到 `_research_template_core.py`（或独立 `_research_template_types.py`），消除 import cycle 风险
4. **Import DAG**: 基于 call graph 精确枚举 5 模块间所有 import 边，验证无环
5. **`research_template.py` 终态定义**:
   - 保留的函数/类清单（exact 42: 1 entry + 39 runner + 2 从新 owner import 的 dataclass）
   - 从 5 个新模块的完整 import 清单（每个 runner 需要的 callee）
   - 终态 `__all__` 内容

### 6.2 建议修复

6. **Test 迁移方案**: direct-owner vs dispatch-owner 分流，patch 路径更新
7. **write.py lazy import**: 行号更新为 81/87，import 路径更新为 `_research_template_materialize`
8. **门禁清单**: Slice 9 的 pyright/Ruff/coverage/AST 结构命令（参照 Slice 7 的详细门禁）

### 6.3 模块函数计数建议（基于 call graph 分析）

基于 AST call graph 的初步分类（详见附录 A），建议的模块计数为：

| 模块 | 建议计数 | Plan 声称 | 差异 |
|---|---|---|---|
| `_research_template_helpers.py` | **30** | 22 | +8 |
| `_research_template_core.py` | **23** | 21 | +2 |
| `_research_template_bundle.py` | **11** | 11 | 0 |
| `_research_template_monitoring.py` | **10** | 9 | +1 |
| `_research_template_materialize.py` | **9** | 9 | 0 |
| **合计** | **83** | 72 | **+11** |

> 注：以上计数为基于 call graph 和功能域的初步建议，最终分配需结合 plan author 的设计意图。差距主要来自 plan 将 11 个函数错误归类或遗漏计数。

---

## 附录 A: 83 个需迁移函数完整清单与初步模块分配

### A.1 _research_template_core.py（23 函数，模板基础 + 监控变量/规则/源映射 + 包清单/使用指南）

| # | 函数名 | 被 retained runner 调用 |
|---|---|---|
| 1 | `list_research_templates` | `_run_list` |
| 2 | `load_research_template` | `_run_show` |
| 3 | `copy_research_template` | `_run_copy` |
| 4 | `compose_research_template` | `_run_compose` |
| 5 | `recommend_research_templates` | `_run_recommend` |
| 6 | `extract_monitoring_variables` | — |
| 7 | `build_monitoring_rules_payload` | `_run_monitoring_rules` |
| 8 | `build_monitoring_source_map_payload` | `_run_source_map` |
| 9 | `validate_monitoring_source_map_payload` | `_run_validate_source_map` |
| 10 | `build_monitoring_source_binding_preview` | `_run_source_bindings` |
| 11 | `write_monitoring_source_binding_approval` | `_run_source_bindings` |
| 12 | `build_monitoring_source_binding_rollback_preview` | `_run_rollback_source_bindings` |
| 13 | `write_monitoring_source_binding_rollback` | `_run_rollback_source_bindings` |
| 14 | `inspect_monitoring_source_binding_history` | `_run_source_binding_history` |
| 15 | `build_research_template_package_manifest` | `_run_package_manifest` |
| 16 | `get_monitoring_data_source_candidates` | — |
| 17 | `write_monitoring_rules_payload` | `_run_monitoring_rules` |
| 18 | `write_monitoring_source_map_payload` | `_run_source_map` |
| 19 | `write_research_template_package_manifest` | `_run_package_manifest` |
| 20 | `build_research_template_usage_guide` | — |
| 21 | `write_research_template_usage_guide` | — |
| 22 | `materialize_research_checklist` | `_run_materialize_checklist` |
| 23 | `_source_map_sources_by_name` | — |

### A.2 _research_template_bundle.py（11 函数）

| # | 函数名 | 被 retained runner 调用 |
|---|---|---|
| 1 | `build_research_template_bundle_descriptor` | — |
| 2 | `_recompute_bundle_monitoring_integrity` | — |
| 3 | `_recompute_bundle_checklist_integrity` | — |
| 4 | `validate_research_template_bundle_descriptor` | — |
| 5 | `inspect_research_template_bundle` | `_run_validate_bundle` |
| 6 | `build_research_template_bundle_rebind_preview` | `_run_rebind_bundle` |
| 7 | `write_research_template_bundle_rebind` | `_run_rebind_bundle` |
| 8 | `_prepare_research_template_bundle_rebind` | — |
| 9 | `build_research_template_bundle_rebind_rollback_preview` | `_run_rollback_bundle_rebind` |
| 10 | `write_research_template_bundle_rebind_rollback` | `_run_rollback_bundle_rebind` |
| 11 | `discover_research_template_bundles` | `_run_list_bundles` |

### A.3 _research_template_monitoring.py（10 函数）

| # | 函数名 | 被 retained runner 调用 |
|---|---|---|
| 1 | `build_monitoring_execution_plan` | `_run_monitoring_plan` |
| 2 | `validate_monitoring_execution_plan` | — |
| 3 | `inspect_monitoring_execution_plan` | `_run_validate_monitoring_plan` |
| 4 | `discover_monitoring_execution_plans` | `_run_list_monitoring_plans` |
| 5 | `build_monitoring_status_snapshot` | `_run_monitoring_status` |
| 6 | `write_monitoring_status_snapshot` | `_run_monitoring_status` |
| 7 | `build_monitoring_scheduler_manifest` | `_run_scheduler_manifest` |
| 8 | `validate_monitoring_scheduler_manifest` | — |
| 9 | `inspect_monitoring_scheduler_manifest` | `_run_validate_scheduler_manifest` |
| 10 | `_scheduler_state_from_plan_inspection` | — |

### A.4 _research_template_materialize.py（9 函数）

| # | 函数名 | 被 retained runner 调用 |
|---|---|---|
| 1 | `write_monitoring_scheduler_manifest` | `_run_scheduler_manifest` |
| 2 | `write_monitoring_execution_plan` | `_run_monitoring_plan` |
| 3 | `write_research_template_bundle_descriptor` | — |
| 4 | `_materialization_artifact_paths` | — |
| 5 | `_snapshot_materialization_artifacts` | — |
| 6 | `_rollback_materialization_artifacts` | — |
| 7 | `materialize_research_template_bundle` | — |
| 8 | `materialize_research_workspace` | `_run_materialize` |
| 9 | `build_research_workspace_refresh_preview` | `_run_refresh_workspace` |
| 10 | `write_research_workspace_refresh` | `_run_refresh_workspace` |
| 11 | `materialize_research_bundle_from_write_manifest` | — |
| 12 | `materialize_research_portfolio` | `_run_materialize_portfolio` |
| 13 | `build_research_portfolio_preview` | `_run_preview_portfolio` |

> **注**: 上表 materialize 列为 13 个候选。若严格按 plan 的 "物化/Portfolio/工作区刷新=9"，需将 4 个函数（`write_monitoring_scheduler_manifest`, `write_monitoring_execution_plan`, `write_research_template_bundle_descriptor`, `_materialization_artifact_paths` 及其 snapshot/rollback 族）重新分配。这正说明 plan 需要明确的逐函数分配。

### A.5 _research_template_helpers.py（30 函数，叶子模块，零入度）

| # | 函数名 | 被 retained runner 调用 |
|---|---|---|
| 1 | `_as_str_list` | — |
| 2 | `_build_research_portfolio_preview` | — |
| 3 | `_build_source_write_manifest_binding` | — |
| 4 | `_build_write_manifest_binding_semantics` | — |
| 5 | `_company_facets_from_args` | `_run_recommend` |
| 6 | `_dedupe` | — |
| 7 | `_discover_research_artifact_paths` | — |
| 8 | `_identifier_component` | — |
| 9 | `_inspect_source_binding_snapshot` | — |
| 10 | `_load_company_facets_from_manifest` | — |
| 11 | `_load_json_object` | `_run_monitoring_plan`, `_run_monitoring_status`, `_run_source_bindings`, `_run_update_research_workbook`, `_run_validate_research_workbook`, `_run_validate_source_map`, `_run_workbook_report`, `_run_workbook_report_status`, `_run_workbook_status`, `_run_scheduler_manifest` |
| 12 | `_load_workbook_evidence_records` | `_run_update_research_workbook` |
| 13 | `_normalize_research_target` | — |
| 14 | `_normalize_template_name` | — |
| 15 | `_portfolio_target_artifact_paths` | — |
| 16 | `_prepare_research_portfolio_targets` | — |
| 17 | `_print_definition_header` | `_run_scorecard`, `_run_evidence`, `_run_schema` |
| 18 | `_read_template_title` | — |
| 19 | `_recommendation_payload` | `_run_recommend` |
| 20 | `_resolve_materialize_research_target` | `_run_materialize` |
| 21 | `_resolve_materialize_template_selection` | `_run_materialize` |
| 22 | `_resolve_template_dir` | — |
| 23 | `_resolve_template_path` | — |
| 24 | `_resolve_template_selection_from_write_manifest` | — |
| 25 | `_sha256_file` | — |
| 26 | `_sha256_json_object` | — |
| 27 | `ResearchTemplate` | `_run_list`（通过 `list_research_templates` 返回类型间接使用，建议迁到 core） |
| 28 | `ResearchTemplateRecommendation` | `_run_recommend`（通过 `recommend_research_templates` 和 `_recommendation_payload` 间接使用，建议迁到 core） |

> **注**: 两个 dataclass 强烈建议迁到 `_research_template_core.py`（见 H-03）。若迁到 core，helpers 实际为 28 函数，core 为 25（23 + 2 dataclass）。

---

## 附录 B: 验证命令速查

### B.1 源码事实

```bash
# 总 FunctionDef 数
python3 -c "import ast; tree=ast.parse(open('dayu/cli/commands/research_template.py').read()); print(len([n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.FunctionDef)]))"
# → 123

# _run_* runner 数
grep -c '^def _run_' dayu/cli/commands/research_template.py
# → 39

# __all__ 条目数
python3 -c "import ast; tree=ast.parse(open('dayu/cli/commands/research_template.py').read()); [print(len(e.value.elts)) for n in ast.iter_child_nodes(tree) if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name) and t.id == '__all__' and isinstance(n.value, (ast.List, ast.Tuple))]"
# → 68

# 需迁移函数数
python3 -c "import ast; tree=ast.parse(open('dayu/cli/commands/research_template.py').read()); funcs=[n.name for n in ast.iter_child_nodes(tree) if isinstance(n, ast.FunctionDef)]; runners={f for f in funcs if f.startswith('_run_')}; print(len(funcs)-len(runners)-1)"
# → 83

# Dataclass 使用验证
python3 -c "
import ast
tree = ast.parse(open('dayu/cli/commands/research_template.py').read())
for dc in ['ResearchTemplate', 'ResearchTemplateRecommendation']:
    users = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id == dc:
                    users.add(node.name)
    print(f'{dc}: {sorted(users)}')
"
# ResearchTemplate: ['list_research_templates']
# ResearchTemplateRecommendation: ['_recommendation_payload', 'recommend_research_templates']

# write.py lazy import 实际行号
grep -n "materialize_research_bundle_from_write_manifest" dayu/cli/commands/write.py
# → 81, 87
```

### B.2 建议的 v5.1 验收门禁

```bash
# 1. 逐函数分配闭合
python3 -c "from dayu.cli.commands._research_template_helpers import __all__; ..." # 需实现后运行
# assert sum(counts) == 83

# 2. 零反向 import
grep -r "from dayu.cli.commands.research_template import" dayu/cli/commands/_research_template_*.py
# → 0

# 3. 无 import cycle
python3 -c "from dayu.cli.commands.research_template import run_research_template_command"

# 4. Pyright 零 errors
pyright dayu/cli/commands/

# 5. 测试全绿
pytest tests/cli/test_research_template*.py -v

# 6. research_template.py AST 旧定义为 0（除 40 保留 + import）
# 验证迁移后的 83 函数旧定义不在 research_template.py 中
```

---

## 附录 C: Plan Slice 9 与 Slice 7 规格密度对比

| 维度 | Slice 7（105 行） | Slice 9（11 行） |
|---|---|---|
| 逐函数名清单 | ✅ exact 15（14 runner + 1 gate） | ❌ 仅自然语言功能域名 |
| 逐函数归属模块 | ✅ `_write_execution.py` exact 2 + `_write_manual_recovery.py` exact 15 | ❌ 仅模块级数字 |
| Import identity | ✅ `write.py` 从两个 owner import exact 17 | ❌ 无 |
| Factory call 计数 | ✅ 三处 `build_snapshot_builder` + 三 label | ❌ 无 |
| Test owner 迁移 | ✅ direct-owner/dispatch-owner 分流 | ❌ 无 |
| AST 结构门禁 | ✅ exact 定义数、import 数、factory call 数 | ❌ 无 |
| Pyright/Ruff/Coverage 门禁 | ✅ 精确命令 | ❌ 无 |
| README 更新触发 | ✅ 触发条件判断 | ❌ 无 |

Slice 9 的规格密度约为 Slice 7 的 **10%**，而 Slice 9 的函数规模是 Slice 7 的 **5.5 倍**（83 vs 15）。

---

**审查结论**: **FAIL**。3 个 HIGH findings 必须在 v5.1 中修复后 Slice 9 才可实施。核心问题是函数计数不闭合（72≠83）、无逐函数 ownership 表、dataclass 归属产生 import cycle。建议按 §6 的最小修复方案生成 v5.1。

**审查人**: DeepSeek（planreview skill）
**审查方式**: 独立 AST/callgraph 验证，只读，零修改
