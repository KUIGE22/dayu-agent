# Plan Review: v5.1 Slice 9 Re-Review

- **审查时间**: 2026-08-08 08:20 UTC
- **审查人**: DeepSeek（planreview skill）
- **基线**: clean HEAD `1d0f9e6`
- **审查范围**: Slice 9 v5.1 CANDIDATE（含 Controller erratum `plan-slice-9-v5.1-ownership-dag-erratum-20260808-codex.md`）
- **初审引用**: `docs/reviews/plan-review-20260808-075500-deepseek.md`（本审查人，FAIL, 3H+3M+3L）、`docs/reviews/plan-review-20260808-075501-mimo.md`（MiMo, PASS with plan fixes）
- **审查模式**: 只读。独立 AST/callgraph 机器核验。禁止修改 plan/code/tests/README/Controller artifact。
- **对照文件**:
  - `AGENTS.md`（项目约束）
  - `docs/plans/2026-08-07-cli-write-architecture-refactor.md`（master plan v5.1, updated）
  - `docs/reviews/plan-slice-9-v5.1-ownership-dag-erratum-20260808-codex.md`（Controller erratum）
  - `dayu/cli/commands/research_template.py`（HEAD `1d0f9e6`, 4146 行）
  - `dayu/cli/commands/write.py`（lazy import caller, line 81）
  - `dayu/cli/main.py`（entry import）
  - `tests/cli/test_research_template_command.py`、`tests/cli/test_research_template_definitions.py`、`tests/application/test_write_cli_dispatch.py`

---

## Verdict: PASS（open High/Medium/Low = 0/0/2）

**根因**: v5.1 精确闭合了 v5.0 的所有 gaps。83 函数逐名 exact 且唯一分配（22/26/12/11/12），DAG 零 forbidden edge/cycle，45 functional bindings 零 false positive/negative，`__all__` 68→55 精确 13 项删除，dataclass 迁至 helpers 消除 cycle，存量 `object` 1→1。Slice 9 达到 code-generation-ready 标准，可实施。

---

## 0. 独立机器核验证据

以下所有核验在 clean HEAD `1d0f9e6` 上运行，结果直接来自 AST 解析，不依赖 plan 或 Controller 的中间计算。

### 0.1 顶层 Inventory

| 度量 | 独立核验 | v5.1 Plan | 一致 |
|---|---|---|---|
| 顶层 FunctionDef | **123** | 123 | ✅ |
| `_run_*` runner | **39** | 39 | ✅ |
| Entry | **1** (`run_research_template_command`) | 1 | ✅ |
| 保留函数 | **40** (39+1) | 40 | ✅ |
| 需迁移函数 | **83** (123−40) | 83 | ✅ |
| 顶层 ClassDef | **2** | 2 | ✅ |
| 模块常量（含 `__all__`） | **8** (5 Assign + 2 AnnAssign + `__all__`) | 8 | ✅ |

### 0.2 83 函数 Exact Ownership

| Owner | 独立核验 | v5.1 Plan | 一致 |
|---|---|---|---|
| `_research_template_helpers.py` | **22** | 22 | ✅ |
| `_research_template_core.py` | **26** | 26 | ✅ |
| `_research_template_bundle.py` | **12** | 12 | ✅ |
| `_research_template_monitoring.py` | **11** | 11 | ✅ |
| `_research_template_materialize.py` | **12** | 12 | ✅ |
| **合计** | **83** | 83 | ✅ |

**完整性**: missing `[]`、extra `[]`、overlap `[]`。所有 83 函数恰好且唯一分配。

### 0.3 跨 Owner DAG

AST free-global/call graph 验证结果（15 条边，0 forbidden，0 cycle）：

```
main → helpers ✓        main → core ✓          main → bundle ✓
main → monitoring ✓     main → materialize ✓
core → helpers ✓
bundle → core ✓         bundle → helpers ✓
monitoring → bundle ✓   monitoring → core ✓     monitoring → helpers ✓
materialize → monitoring ✓  materialize → bundle ✓
materialize → core ✓    materialize → helpers ✓
helpers → （零内部 project-domain dependency）✓
```

**Forbidden edges: 0**。**Cycles: 0**。helpers 是真正的叶子模块。

### 0.4 Main Functional Bindings（exact 45）

| Owner | 独立核验 | v5.1 Plan (6/18/6/9/6) | 一致 |
|---|---|---|---|
| helpers | **6** | 6 | ✅ |
| core | **18** | 18 | ✅ |
| bundle | **6** | 6 | ✅ |
| monitoring | **9** | 9 | ✅ |
| materialize | **6** | 6 | ✅ |
| **合计** | **45** | 45 | ✅ |

**False positives**: 0（plan 列出的 45 个函数全部被 retained entry/runner 直接调用）。
**False negatives**: 0（被 retained 调用但未在 plan binding 中的函数为 0）。
**Non-bound**: 38（=83−45，仅被其他迁移函数调用或为叶子工具）。

### 0.5 `__all__` 终态

| 度量 | 独立核验 | v5.1 Plan | 一致 |
|---|---|---|---|
| 当前 `__all__` 条目 | **68** | 68 | ✅ |
| 删除项 | **13**（全部在 `__all__` 中存在） | 13 | ✅ |
| 终态条目 | **55**（=68−13） | 55 | ✅ |

### 0.6 Dataclass & Constants

| 度量 | 独立核验 | v5.1 Plan | 一致 |
|---|---|---|---|
| Dataclass 总数 | **2** | 2 | ✅ |
| Dataclass 被 retained 直接使用 | **0** | 0 | ✅ |
| Dataclass 归属 | helpers | helpers | ✅ |
| 模块常量 | **7**（_TEMPLATE_DIR_NAME, _TEMPLATE_SUFFIX, _FALLBACK_TEMPLATE_NAME, _BUNDLE_ARTIFACT_KEYS, _COMMON_DATA_SOURCE_CANDIDATES, _TEMPLATE_DATA_SOURCE_CANDIDATES, _DATA_SOURCE_BINDING_CANDIDATES） | 7 | ✅ |
| 常量归属 | helpers | helpers | ✅ |

### 0.7 Object Occurrence

`_DATA_SOURCE_BINDING_CANDIDATES`（源码 line 99）的类型注解为 `dict[str, dict[str, object]]`。这是 **存量** 模块级常量类型，不是函数签名。迁移时 semantic occurrence **1→1**，不新增、不传播、不 escape。与 v5.1 claim 一致。✅

### 0.8 write.py Lazy Import

```bash
$ sed -n '81p' dayu/cli/commands/write.py
    from dayu.cli.commands.research_template import materialize_research_bundle_from_write_manifest
```

当前路径 → 需更新为 `dayu.cli.commands._research_template_materialize`。Plan §9e 已明确。✅

### 0.9 Slice 10 Impact

Slice 10 的 39 runner + entry 签名传播（`argparse.Namespace → DayuCliArguments`）**不受 Slice 9 影响**：
- 40 个 retained 函数定义仍在 `research_template.py`，Slice 10 可直接修改其签名
- `DayuCliArguments` 是 `argparse.Namespace` 子类，协变安全
- 两个 dataclass 已在 Slice 9 迁到 helpers，Slice 10 不重复迁移 ✅

### 0.10 Cross-file Import Impact

```
dayu/cli/main.py:51          → import run_research_template_command（retained, 不变）
dayu/cli/commands/write.py:81 → 迁至 _research_template_materialize（plan §9e 已覆盖）
tests/cli/test_research_template_command.py:13 → 63 imports, 按 plan §9d 拆分
tests/cli/test_research_template_definitions.py:12 → run_research_template_command（retained）
tests/application/test_write_cli_dispatch.py:36 → run_research_template_command（retained）
```

---

## 1. v5.0 Findings 闭环验证

| v5.0 Finding | 严重度 | v5.1 处置 | 核验结果 |
|---|---|---|---|
| H-01: 72≠83 函数计数不闭合 | HIGH | S9-CTRL-01: 改为 83, 22/26/12/11/12 | **CLOSED** ✅ |
| H-02: 无逐函数 ownership 表 | HIGH | S9-CTRL-01: §9a exact83 逐名列出 | **CLOSED** ✅ |
| H-03: Dataclass 留在 main 产生 cycle | HIGH | S9-CTRL-01: 两类迁至 helpers | **CLOSED** ✅ |
| M-01: `_print_definition_header` 归属模糊 | MEDIUM | S9-CTRL-01: 明确归 helpers(22), main 正常 import | **CLOSED** ✅ |
| M-02: Test 迁移方案缺失 | MEDIUM | S9-CTRL-03: §9d direct-owner/dispatch-owner 规则 | **CLOSED** ✅ |
| M-03: write.py 行号陈旧 | MEDIUM | S9-CTRL-04: 改为当前 line 81 | **CLOSED** ✅ |
| L-01: `__all__` 终态未定义 | LOW | S9-CTRL-03: §9d 精确删除 13→55 | **CLOSED** ✅ |
| L-02: DAG 未逐边验证 | LOW | S9-CTRL-02: §9b 十条边 + AST gate | **CLOSED** ✅ |
| L-03: runner import 需求未枚举 | LOW | S9-CTRL-03: §9c exact45 逐 owner 分布 | **CLOSED** ✅ |

**全部 9 项 v5.0 findings 已 CLOSED**。Controller 未采纳初审的 preliminary allocation（30/23/11/10/9），而是基于本地 AST 逐边复核给出了正确的闭合分配（22/26/12/11/12）。

---

## 2. Findings

### L-01 (LOW) — `write.py:81` lazy import 行号在 Slice 8 后可能漂移

- **位置**: Plan §9e（行 1425: "当前 line 81"）
- **问题类型**: 切片欠规格（轻微）
- **当前写法**: Plan 硬编码行号 81
- **反例/失败场景**: Slice 8（`_write_challenger + _write_config_rollback`）在 Slice 9 之前实施，可能改变 `write.py` 行号。若 Slice 8 在 `_materialize_research_after_write` 函数之前插入/删除代码，line 81 会漂移。
- **直接证据**: Slice 8 尚未实施，`write.py` 当前行数约 660（已通过 Slice 5-7 精简）。Slice 8 将进一步减少到约 660 行（仅保留 `run_write_command` + `_materialize_research_after_write`）。`_materialize_research_after_write` 函数的位置取决于 Slice 8 的最终代码布局。
- **影响**: 实施 Agent 需在 Slice 8 后重新确认行号（轻微搜索成本）
- **建议改法和验证点**: 在 Slice 9 实施时，用 `grep -n "from dayu.cli.commands.research_template import materialize_research_bundle_from_write_manifest" write.py` 动态确认行号，而非盲从 plan 中的硬编码值。Plan 可改为函数名锚点（如 "`_materialize_research_after_write` 函数内的 function-local import"）
- **修复风险**: 低（实施时用 grep 确认即可）
- **严重程度**: 低

### L-02 (LOW) — 五个新 owner 模块均不定义 `__all__`，star-import 行为与 `research_template.py` 有语义差

- **位置**: Plan §9d（行 1413: "五个私有 owner 模块均不定义 `__all__`，不扩大 star-import surface"）
- **问题类型**: 契约缺失（轻微）
- **当前写法**: Plan 明确五个私有模块不设 `__all__`。`research_template.py` 的 `__all__` 保留 55 项（含 17 个 workbook re-export）。
- **反例/失败场景**: 当前 `research_template.py` 的 `__all__` 包含 51 个本文件原生定义（49 函数 + 2 dataclass）。Slice 9 后这些函数/类分散到 5 个私有模块。若 consumer 代码（如 `from dayu.cli.commands.research_template import *`）依赖 star-import 获取迁移后的函数，将因 `__all__` 删除 13 项而出现 AttributeError。但这属于预期行为——plan 明确只保留 55 项，consumer 应直接从新 owner import。
- **为什么有问题**: 不是 bug，而是需在实施时确认所有已知 consumer（main.py、write.py、tests）均已更新 import 路径。Plan §9d 已明确覆盖 tests，§9e 已覆盖 write.py，main.py 仅 import `run_research_template_command`（保留项）。已知 consumer 均已处理。
- **影响**: 未知 consumer（若有）可能受影响，但不在已知 scope 内
- **建议改法和验证点**: 实施后 `rg "from dayu.cli.commands.research_template import"` 确认所有 import 路径均为保留项或已在 plan 中覆盖
- **修复风险**: 低（实施后 grep 审计即可）
- **严重程度**: 低

---

## 3. Open Questions

1. **Q1**: `tests/cli/test_research_template_command.py` 当前 63 个 direct import 迁移为 5 组 owner import 后，是否拆分为 5 个测试文件还是在原文件内按 owner 分组？Plan §9d 说"可在现有测试文件内按 owner 分组 import；是否拆测试文件只由可读性与真实分层决定，不是强制目标"——这留给实施 Agent 合理判断，可接受。

2. **Q2**: `tests/cli/test_research_template_definitions.py` 和 `tests/application/test_write_cli_dispatch.py` 仅 import `run_research_template_command`（保留项），理论上不受 Slice 9 影响。但 dispatch 测试中的 patch 路径若指向迁移函数（如 `research_template._run_*`），需更新为新 owner 路径。Plan §9d 的规则覆盖了这一点。

---

## 4. Residual Risks

| # | 风险 | 严重度 | 处置建议 |
|---|---|---|---|
| R1 | Slice 8 在 Slice 9 之前实施，可能改变 `write.py` 行号，导致 `write.py:81` 漂移 | LOW | Slice 9 实施时用函数名锚点（`_materialize_research_after_write`）定位，不用硬编码行号 |
| R2 | 83 函数从 4146 行文件迁至 5 个新文件，Pyright 在 5 个新模块的 fresh analysis 上可能产生不同于单文件分析的 warning（如 re-export 检测、未使用 import） | LOW | Plan 已要求 pyright `dayu/cli/` 0 errors，涵盖新模块 |
| R3 | Coverage 逐文件 `>=80%` 依赖现有 test corpus 的 import 路径迁移，若 test 迁移有遗漏，coverage 可能不达标 | LOW | Plan 已要求 7 个生产文件（main + 5 owners + write.py）逐文件 coverage >=80% |

---

## 5. 审查结论

**Verdict: PASS**（open High/Medium/Low = 0/0/2）

v5.1 精确闭合了 v5.0 的全部 9 项 findings。独立 AST/callgraph 机器核验确认：

- 83 函数逐名 exact 且唯一分配至 5 个 owner（22/26/12/11/12），missing/extra/overlap = 0
- DAG 15 条边（10 intra-owner + 5 main→owner），零 forbidden edge、零 cycle
- helpers 是真正的零内部 project-domain dependency 叶子模块
- 45 functional bindings 精确 6/18/6/9/6，零 false positive/negative
- 38 非 bound 函数零 compatibility re-export
- `__all__` 68→55，精确 13 项删除
- Dataclass 迁至 helpers 消除 import cycle
- 存量 `object` 1→1，不新增签名或传播
- write.py lazy import 路径明确
- Slice 10 影响独立且安全
- 全部门禁（AST/identity/DAG/import-smoke/pyright/Ruff/coverage/README/diff-check）在 plan 中明确定义

2 个 LOW findings（行号漂移、`__all__` 语义差）均为实施时的轻微确认工作，不影响 plan 的可实施性或正确性。

**Slice 9 v5.1 达到 code-generation-ready 标准，建议进入 implementation phase。**

**审查人**: DeepSeek（planreview skill）
**审查方式**: 独立 AST/callgraph 机器核验，只读，零修改
