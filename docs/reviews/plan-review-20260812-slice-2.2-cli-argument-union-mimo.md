# Slice 2.2 CLI typed-field exact union 计划审核

- **审核者**：MiMo independent
- **Gate**：Gateflow plan-fix；S22-CTRL-010 最小勘误
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md` §S22-CTRL-010
- **目标修复文档**：`docs/reviews/plan-fix-20260812-slice-2.2-cli-argument-union-codex.md`
- **仓库**：`/Users/wsk/workspace/dayu-agent`，branch `codex/investment-platform`，HEAD `37cac2f`
- **审核范围**：根因、最小 allowlist、类型/base/default/init 合同、验证与 STOP

## 1. 结论

**PASS / open H/M/L=0/0/0**

S22-CTRL-010 勘误的动机成立，根因定位准确，最小修复方案正确且完备。无 open finding。

## 2. 根因挑战

### 2.1 根因是否真实？

**是**。直接证据链闭合：

1. `dayu/cli/arguments.py:44-71`：`DayuCliArguments` 已有 25 个 `AnnAssign`，包含 `platform_action`、`tenant_id`、`worker_id`、`scheduler_id` 四个平台字段（第 47-50 行）。
2. `tests/application/test_write_cli_dispatch.py:1332-1333`：测试断言 `dayu_fields == research_fields | write_fields` 且 `len(dayu_fields) == 21`。当前 `DayuCliArguments` 有 25 字段，`Research ∪ Write = 21`，差值恰好为 4 个平台字段。
3. 目标计划 §3 implementation allowlist 只列了 `tests/cli/test_platform_command.py` 与 `tests/cli/test_main.py` 作为 CLI tests；`tests/application/test_write_cli_dispatch.py` 未列入，实施者不能合法修改该文件的 AST 断言。

**根因不是平台 typed field 实现错误，而是 implementation allowlist 遗漏了拥有跨命令 AST 合同的既有测试文件。** 定位正确。

### 2.2 根因是否被高估？

**否**。这是一个阻塞性合同失败：clean non-integration 直接暴露，且在 S22-CTRL-010 的 allowlist 内无法合法修复。必须通过 plan-fix 扩大测试 allowlist。

### 2.3 替代方案评估

Codex 修复文档正确拒绝了三种替代方案：
- 删除平台字段：掩盖真实合同，不可接受
- 放宽 AST 断言：破坏既有精确性约束，不可接受
- 改动 write/research 字段：不属于本勘误范围，不可接受

## 3. 最小 allowlist 挑战

### 3.1 Production allowlist

**不扩大**。唯一修改的 production 文件是 `dayu/cli/arguments.py`，已在目标计划 §3 allowlist 内。新增 `PlatformDispatchArguments(Protocol)` 类定义属于该文件既有职责边界。

### 3.2 Test allowlist

**精确扩大一个文件**：`tests/application/test_write_cli_dispatch.py`。只允许修改 `test_protocol_and_dayu_fields_form_exact_union` 及该文件模块说明中与 exact field/protocol 计数直接冲突的文字。其它 phase table、selector、mapping、fixture 与行为断言保持字节不变。

**验证**：该文件其它测试（`TestWritePhaseTableStructure`、`TestWritePhaseTableGroup1PhaseABool`、`TestResearchTemplateDispatchMapping` 等）不依赖 `DayuCliArguments` 的字段总数，只依赖 `WriteDispatchArguments` 的结构性 conformance 和 `_make_write_args()` 的字段覆盖。修改 union 断言不影响它们。

### 3.3 Allowlist 是否最小？

**是**。不需要新增 production 路径；不需要修改 `arguments.py` 之外的 production 文件；不需要修改 `test_write_cli_dispatch.py` 之外的测试文件。STOP 条件全部满足。

## 4. 类型/base/default/init 合同验证

### 4.1 ResearchTemplateDispatchArguments — exact 1

`arguments.py:13-16`：一个 `AnnAssign`，`research_template_action: str`。✓

### 4.2 WriteDispatchArguments — exact 20

`arguments.py:19-42`：20 个 `AnnAssign`，名字与类型均不变。测试 `WRITE_FIELDS` 集合（`test_write_cli_dispatch.py:1270-1291`）精确列出 20 个字段名。✓

### 4.3 PlatformDispatchArguments — exact 4（待新增）

计划要求：
```
platform_action: str
tenant_id: str
worker_id: str | None
scheduler_id: str | None
```

与 `DayuCliArguments` 第 47-50 行逐字匹配。✓

### 4.4 DayuCliArguments — exact 25

`arguments.py:44-71`：25 个 `AnnAssign`。逐字段核对：
- 4 个平台字段（第 47-50 行）
- 1 个 research 字段（第 51 行）
- 20 个 write 字段（第 52-71 行）
- 总计 25，三集合无重叠。✓

### 4.5 单一 base

`arguments.py:44`：`class DayuCliArguments(argparse.Namespace)`。只继承 `argparse.Namespace`，不继承任何 Protocol。✓

### 4.6 零 class default

所有 25 个 `AnnAssign` 均无 `value`（即 `AnnAssign.value is None`）。测试第 1337-1340 行精确断言此点。✓

### 4.7 零 custom init

`DayuCliArguments` 无 `__init__` 方法。测试第 1341-1345 行精确断言此点。✓

### 4.8 字段 disjointness

- Research: `{research_template_action}`
- Write: `{revalidate_write_model_configuration_manual_recovery_incident_dossier, ...}` (20 fields)
- Platform: `{platform_action, tenant_id, worker_id, scheduler_id}`

三集合 pairwise 交集为空。✓

## 5. 验证门禁评估

计划 §S22-CTRL-010 指定的门禁顺序：

```
1. uv run pytest tests/application/test_write_cli_dispatch.py::TestWritePhaseTableStructure::test_protocol_and_dayu_fields_form_exact_union -q
2. uv run pytest tests/application/test_write_cli_dispatch.py tests/cli/test_platform_command.py tests/cli/test_main.py -q -m "not integration and not slow and not e2e"
3. uv run pyright dayu/cli/arguments.py tests/application/test_write_cli_dispatch.py
4. uv run ruff check dayu/cli/arguments.py tests/application/test_write_cli_dispatch.py
5. uv run ruff check --select F,I dayu/cli/arguments.py tests/application/test_write_cli_dispatch.py
6. uv run ruff format --check dayu/cli/arguments.py tests/application/test_write_cli_dispatch.py
7. env -u SERPER_API_KEY uv run pytest -q -m "not integration and not slow and not e2e"
8. git diff --check
```

**门禁完备性**：覆盖 focused AST、CLI 回归、pyright、Ruff（default + F/I）、format、clean-env full non-integration、diff check。✓

**Serper 处理**：`env -u SERPER_API_KEY` 显式移除继承环境变量，避免 `test_search_with_serper_requires_api_key` 进入 live request。与 CLI union 无因果关系，正确分类为环境残余。✓

**门禁是否可执行**：所有命令在目标仓库当前 HEAD 可直接运行。✓

## 6. STOP 条件检查

逐项核对计划 §12 中与本勘误相关的 STOP 条件：

| STOP 条件 | 状态 |
|---|---|
| 需要新增 production 路径 | 不需要 ✓ |
| 需要修改 `arguments.py` 之外的 production 文件 | 不需要 ✓ |
| 需要修改新增 allowlist 以外的测试文件 | 不需要 ✓ |
| Research exact1、Write exact20、Platform exact4、Dayu exact25 无法同时满足 | 可以同时满足 ✓ |
| 字段类型、单一 base、零 class default、零 custom init 任一合同违反 | 无违反 ✓ |
| 试图删除平台字段、放宽并集、Protocol 多继承、动态字段 bag | 未采用 ✓ |
| 试图修改 Serper 代码/测试 | 未涉及 ✓ |

**无 STOP 触发。**

## 7. 与 DeepSeek 独立性声明

本审核完全独立进行，未读取 DeepSeek review 文档。所有分析基于：
- 目标计划原文 §S22-CTRL-010
- Codex 修复文档
- `dayu/cli/arguments.py` 源码
- `tests/application/test_write_cli_dispatch.py` 源码
- AGENTS.md 项目约束

## 8. Open Findings

**无。**

## 9. 裁决

| 维度 | 结果 |
|---|---|
| 动机成立 | 是 |
| 根因定位准确 | 是 |
| 最小修复 | 是 |
| 类型/base/default/init 合同 | 全部满足 |
| 验证门禁 | 完备且可执行 |
| STOP 条件 | 无触发 |
| open H | 0 |
| open M | 0 |
| open L | 0 |
| **裁决** | **PASS** |
