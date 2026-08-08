# Plan Review: v5.2 Slice 10/11 Protocol Conformance — Focused Adversarial Review

- **日期**: 2026-08-08 10:30
- **审查类型**: Slice 10/11 Protocol conformance focused review
- **审查计划**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md`（v5.2 ACCEPTED）
- **审查 HEAD**: `0573d63`（gateflow: accept cli write architecture plan v5.2）
- **WIP 证据**: `dayu/cli/arguments.py` WIP、`dayu/cli/commands/research_template.py` WIP
- **审查人**: DeepSeek (planreview skill, focused adversarial pass)
- **范围**: 仅 Slice 10/11 的 Protocol 类型一致性；production/test/README 及其他 slice 不在 scope

---

## 0. 直接证据：pyright 报错

### 0.1 WIP 实测

```text
$ source .venv/bin/activate && pyright dayu/cli/arguments.py dayu/cli/commands/research_template.py

dayu/cli/commands/research_template.py:131:48 - error:
  Argument of type "DayuCliArguments" cannot be assigned to parameter "args"
  of type "ResearchTemplateDispatchArguments" in function
  "_resolve_research_template_action"
    "DayuCliArguments" is incompatible with protocol
    "ResearchTemplateDispatchArguments"
      "research_template_action" is not present (reportArgumentType)
1 error, 0 warnings, 0 informations
```

### 0.2 错误定位

| 文件 | 行 | 调用 | 问题 |
|---|---|---|---|
| `research_template.py:131` | `_resolve_research_template_action(args)` | `args: DayuCliArguments` → `args: ResearchTemplateDispatchArguments` | `DayuCliArguments` 不含 `research_template_action`，不满足 Protocol |

### 0.3 根因

`dayu/cli/arguments.py` WIP 定义：

```python
class DayuCliArguments(argparse.Namespace):
    """保存 argparse 解析结果并提供稳定的运行时类型身份。"""

class ResearchTemplateDispatchArguments(Protocol):
    research_template_action: str
```

`DayuCliArguments` 是一个**空** `argparse.Namespace` 子类，pyright 的 structural subtyping 检查发现它不包含 Protocol 声明的 `research_template_action: str` 属性，因此拒绝 `DayuCliArguments` 赋值给 `ResearchTemplateDispatchArguments`。

### 0.4 Slice 11 相同问题确认

Slice 11 的 `WriteDispatchArguments` Protocol 声明 22 个字段（Phase A bool × 11、Phase B bool × 2、Phase D/F/G bool × 3、Phase A path × 4、Phase F path × 1），predicate lambda 签名为 `Callable[[WriteDispatchArguments], bool]`。

同样的问题将在 Slice 11 的 `entry.predicate(args)` 调用点重现，因为 `args: DayuCliArguments` 同样不满足 `WriteDispatchArguments` Protocol 的结构子类型检查——这是**同一根因**，不是两个独立问题。

---

## 1. 方案评估

### 1.1 方案矩阵

| 方案 | 描述 | pyright 状态 | 违规项 |
|---|---|---|---|
| **A (v5.3 原始提案)** | `DayuCliArguments(argparse.Namespace, ResearchProtocol[, WriteProtocol])` — Protocol 多继承 | 类型兼容 ✅ / 实例化 ❌ `reportAbstractUsage` | `DayuCliArguments()` 触发 abstract class 错误 |
| **B** | Dayu 复制全部字段（无 Protocol） | ✅ | 无 Protocol 消费方类型边界，失去静态字段校验 |
| **C** | 改 selector/entry 类型为 `argparse.Namespace` | ✅ | 放弃 Protocol 类型安全，违反 S10-CTRL-01/02 |
| **D** | cast / adapter / ignore | ✅（压制） | 违反零 cast/零 type: ignore 硬约束 |
| **v5.3 修正** | `DayuCliArguments(argparse.Namespace)` 显式声明全部字段；Protocol 不继承，structural subtyping 提供兼容 | ✅ 0 errors | 无 |

### 1.2 方案 A 失败分析（v5.3 原始提案）

**类型兼容层**（function parameter passing）：✅ 0 errors。
当 `DayuCliArguments` 继承 Protocol 时，pyright 将其视为 Protocol 的 nominal subtype，接受 `run_research_template_command(args)` → `_resolve_research_template_action(args)` 的类型流转。

**实例化层**（`DayuCliArguments()`）：❌ `reportAbstractUsage`。
Protocol 声明的 data attributes 在 pyright 中视为 abstract members。即使子类通过 nominal 继承宣称满足 Protocol，pyright 仍要求在类体或 `__init__` 中显式声明这些属性，否则拒绝 `DayuCliArguments()` 调用。

**隔离 spike 实测**（完整 22 字段 WriteDispatchArguments + ResearchTemplateDispatchArguments，双 Protocol 继承）：

```text
/tmp/protocol_spike_v53_full.py:47:6 - error:
  Cannot instantiate abstract class "DayuCliArguments"
    "WriteDispatchArguments.revalidate_..." is not implemented
    "WriteDispatchArguments.inspect_..." is not implemented
    and 19 more... (reportAbstractUsage)
```

影响：`arg_parsing.py:2022` 的 `parser.parse_args(namespace=DayuCliArguments())` 将报 `reportAbstractUsage`。虽然仅 1 处实例化点，但违反 AGENTS 的 "禁止新增、扩散、掩盖或绕过类型错误" 硬约束。

### 1.3 方案 B/C/D 逐一排除

- **B**：删除 Protocol，Dayu 直接声明全部字段 → 失去 selector/predicate 的最小消费方接口，Slice 11 predicate lambda `lambda a: bool(a.apply_...)` 失去字段访问静态校验（Spike 1/2 验证的核心能力）。
- **C**：selector/entry 退化为 `argparse.Namespace` → 违反 S10-CTRL-01（DayuCliArguments 运行时类型身份）与 S10-CTRL-02（45 签名机械传播）。
- **D**：cast/adapter/glue → 直接违反 plan 已明确 REJECTED 的方案 C，且违反编码硬约束。

**结论**：B/C/D 均已被 v5.2 plan 的 explicit rejection 覆盖，无需重新评估。

### 1.4 v5.3 修正方案：显式字段声明 + structural subtyping

**核心设计**：

```python
# --- arguments.py Slice 10 ---
import argparse
from typing import Protocol


class ResearchTemplateDispatchArguments(Protocol):
    """声明 research-template selector 读取的最小参数字段。"""
    research_template_action: str


class DayuCliArguments(argparse.Namespace):
    """保存 argparse 解析结果并提供稳定的运行时类型身份。

    字段声明与 Protocol 声明同构——Protocol 是 consumer 最小契约，
    这里是 producer 全量字段。不通过继承实现 Protocol，避免
    abstract class 实例化限制；structural subtyping 提供类型兼容。
    """
    research_template_action: str
```

```python
# --- arguments.py Slice 11（原子扩展，不替换 Slice 10 已有定义）---
class WriteDispatchArguments(Protocol):
    """声明 write dispatch selector 字段。"""
    # Phase A bool（11）
    revalidate_write_model_configuration_manual_recovery_incident_dossier: bool
    inspect_write_model_configuration_manual_recovery_incident: bool
    audit_write_model_configuration_manual_recovery_history: bool
    revalidate_write_model_configuration_manual_recovery_gate_verification: bool
    verify_write_model_configuration_manual_recovery_gate: bool
    check_write_model_configuration_manual_recovery_gate: bool
    revoke_write_model_configuration_manual_recovery_clearance: bool
    restart_write_model_configuration_manual_recovery_after_clearance_revocation: bool
    clear_write_model_configuration_manual_recovery: bool
    verify_write_model_configuration_manual_recovery: bool
    recover_write_model_configuration: bool
    # Phase B bool（2）
    apply_write_model_configuration: bool
    rollback_write_model_configuration: bool
    # Phase D/F/G bool（3）
    summary: bool
    preflight_only: bool
    reprice_costs: bool
    # Phase A path（3）
    challenger_config_manual_recovery_receipt_input: str | None
    challenger_config_manual_recovery_plan_output: str | None
    challenger_config_manual_recovery_approval_output: str | None
    # Phase F path（1）
    routing_challenger_run_approval_input: str | None


class DayuCliArguments(argparse.Namespace):
    """保存 argparse 解析结果并提供稳定的运行时类型身份。"""
    # Slice 10: research template
    research_template_action: str
    # Slice 11: write — Phase A bool
    revalidate_write_model_configuration_manual_recovery_incident_dossier: bool
    inspect_write_model_configuration_manual_recovery_incident: bool
    audit_write_model_configuration_manual_recovery_history: bool
    revalidate_write_model_configuration_manual_recovery_gate_verification: bool
    verify_write_model_configuration_manual_recovery_gate: bool
    check_write_model_configuration_manual_recovery_gate: bool
    revoke_write_model_configuration_manual_recovery_clearance: bool
    restart_write_model_configuration_manual_recovery_after_clearance_revocation: bool
    clear_write_model_configuration_manual_recovery: bool
    verify_write_model_configuration_manual_recovery: bool
    recover_write_model_configuration: bool
    # Slice 11: write — Phase B bool
    apply_write_model_configuration: bool
    rollback_write_model_configuration: bool
    # Slice 11: write — Phase D/F/G bool
    summary: bool
    preflight_only: bool
    reprice_costs: bool
    # Slice 11: write — Phase A path
    challenger_config_manual_recovery_receipt_input: str | None
    challenger_config_manual_recovery_plan_output: str | None
    challenger_config_manual_recovery_approval_output: str | None
    # Slice 11: write — Phase F path
    routing_challenger_run_approval_input: str | None
```

**关键约束**：
1. `DayuCliArguments` **不继承** Protocol——Protocol 仅定义 consumer 契约。
2. `DayuCliArguments` 显式声明所有 Protocol 字段——满足 pyright 的 structural subtyping 检查。
3. `argparse.Namespace.__init__(**kwargs)` 保持不变——argparse 运行时 `setattr` 正常。
4. 模块仅 import 标准库（`argparse`、`typing.Protocol`），零 `dayu.cli` 模块 import。

### 1.5 隔离 spike 验证结果

**pyright 验证**（完整 22 字段 WriteDispatchArguments + ResearchTemplateDispatchArguments）：

```text
0 errors, 0 warnings, 0 informations
```

**runtime 验证**（argparse 解析 → 实例化 → 类型流转 → predicate lambda）：

```text
Full pipeline: PASS
Predicate lambda: compile PASS, result=False
```

**验证覆盖点**：
- `DayuCliArguments()` 实例化 — ✅（0 errors）
- `_resolve_research_template_action(args: ResearchProtocol)` 接受 `DayuCliArguments` — ✅
- `predicate=lambda a: bool(a.apply_write_model_configuration)` 字段访问 — ✅
- `_EarlyWriteSubcommandEntry(predicate=...)` 类型 `Callable[[WriteDispatchArguments], bool]` 赋值 — ✅
- `parser.parse_args(namespace=DayuCliArguments())` — ✅
- Runtime `isinstance(args, DayuCliArguments)` — ✅
- Runtime `isinstance(args, argparse.Namespace)` — ✅

---

## 2. Findings

### S10-TYPE-01 — 高 — DayuCliArguments 空子类不满足 ResearchTemplateDispatchArguments

- **位置**: v5.2 plan §Slice 10 `:1510-1522`（`DayuCliArguments` 定义）、`:1542`（`_resolve_research_template_action` 签名）
- **问题类型**: 不可直接实施
- **当前写法**:

  ```python
  class DayuCliArguments(argparse.Namespace):
      """保存 argparse 解析结果并提供稳定的运行时类型身份。"""

  class ResearchTemplateDispatchArguments(Protocol):
      research_template_action: str
  ```

  `DayuCliArguments` 不声明 `research_template_action`，pyright structural subtyping 拒绝 `DayuCliArguments` → `ResearchTemplateDispatchArguments`。

- **反例/失败场景**: `run_research_template_command(args: DayuCliArguments)` 内调用 `_resolve_research_template_action(args)` 时，pyright 报 `reportArgumentType`。WIP 实测已确认此错误。
- **为什么有问题**: v5.2 声称 "code-generation-ready" 但 implementation agent 无法在不引入 cast/ignore/glue 的前提下编译通过。Plan 正文从未讨论 `DayuCliArguments` 如何满足 Protocol structural subtyping 约束。
- **直接证据**:
  - WIP pyright: `research_template.py:131:48 - error: Argument of type "DayuCliArguments" cannot be assigned...`
  - Plan `:1515-1517`: `class DayuCliArguments(argparse.Namespace)` — 空类体，无字段声明
  - Plan `:1519-1522`: `class ResearchTemplateDispatchArguments(Protocol): research_template_action: str`
  - Plan `:1542`: `def _resolve_research_template_action(args: ResearchTemplateDispatchArguments) -> str` — 需要 `research_template_action` 属性
  - Plan `:1634`: `def run_research_template_command(args: DayuCliArguments) -> int` — 入口签名
  - Plan `:1647`: `action = _resolve_research_template_action(args)` — 类型流转失败点
- **影响**: 实施 Agent 无法编译通过，被迫引入 cast/ignore/glue 或修改 plan 未覆盖的类型边界
- **建议改法和验证点**:
  1. `DayuCliArguments` 显式声明 `research_template_action: str` 字段（不继承 Protocol）
  2. 验证: `pyright dayu/cli/arguments.py dayu/cli/commands/research_template.py` → 0 errors
  3. 验证: `parser.parse_args(namespace=DayuCliArguments())` 运行时正常
- **修复风险**: 低（单文件单字段声明，不改变运行行为）
- **严重程度**: 高

### S11-TYPE-01 — 高 — DayuCliArguments 不满足 WriteDispatchArguments（同根因）

- **位置**: v5.2 plan §Slice 11 `:1711-1749`（`WriteDispatchArguments` Protocol）、`:1845-1914`（phase 表 predicate lambda）
- **问题类型**: 不可直接实施（与 S10-TYPE-01 同根因）
- **当前写法**: `WriteDispatchArguments` 声明 22 个字段；predicate `lambda a: bool(a.apply_...)` 类型为 `Callable[[WriteDispatchArguments], bool]`；`entry.predicate(args)` 接收 `args: DayuCliArguments`
- **反例/失败场景**: Slice 11 的 `for entry in _WRITE_PHASE_EARLY_RECOVERY: if entry.predicate(args)` 中，如果 `DayuCliArguments` 不声明所有 22 个 Protocol 字段，pyright structural subtyping 报 `reportArgumentType`
- **为什么有问题**: S10-TYPE-01 的同根因在 Slice 11 更高成本重现（22 字段 vs 1 字段）。v5.2 未识别此问题
- **直接证据**:
  - Plan `:1717-1749`: `WriteDispatchArguments` 22 字段 Protocol
  - Plan `:1792`: `predicate: Callable[[WriteDispatchArguments], bool]`
  - Plan `:1847`: `predicate=lambda a: bool(a.revalidate_...)` —— `a` 类型为 `WriteDispatchArguments`
  - Plan `:2016-2017`: `for entry in _WRITE_PHASE_EARLY_RECOVERY: if entry.predicate(args)` —— `args` 类型为 `DayuCliArguments`
- **影响**: Slice 11 同样不可实施，22 字段的 Protocol 兼容性缺口更宽
- **建议改法和验证点**:
  1. 同 S10-TYPE-01 的修正——`DayuCliArguments` 声明全部 23 字段（1 research + 22 write）
  2. Slice 10 先声明 1 字段，Slice 11 原子扩至 23 字段
  3. 验证: `pyright dayu/cli/` → 0 errors；predicate lambda 可编译
- **修复风险**: 低（原子追加字段声明，不改行为）
- **严重程度**: 高

### V53-MECH-01 — 高 — v5.3 原始提案（Protocol 多继承）触发 reportAbstractUsage

- **位置**: 用户 v5.3 提案 `class DayuCliArguments(argparse.Namespace, ResearchTemplateDispatchArguments[, WriteDispatchArguments])`
- **问题类型**: 实例化错误
- **当前写法**: Protocol 多继承，`DayuCliArguments()` 在 `parse_arguments()` 唯一实例化点触发 `reportAbstractUsage`
- **反例/失败场景**: `arg_parsing.py:2022` 的 `parser.parse_args(namespace=DayuCliArguments())` 报 pyright `reportAbstractUsage`。Protocol 声明的 data attributes 在 pyright 中作为 abstract members 处理；即使通过 nominal 继承宣称满足 Protocol，pyright 仍要求子类显式声明这些属性后才允许实例化
- **为什么有问题**: Plan 禁止新增或扩散类型错误；v5.3 提案将 `reportArgumentType`（1 个调用点）替换为 `reportAbstractUsage`（1 个实例化点）——错误类型变了但数量未减
- **直接证据**:
  - Spike `/tmp/protocol_spike_v53_full.py`（完整 22 字段，双 Protocol 继承）: `1 error: Cannot instantiate abstract class "DayuCliArguments"`
  - Spike `/tmp/protocol_spike_v53_instant.py`（3 字段，双 Protocol 继承，含 `parse_arguments` 流程）: `1 error: Cannot instantiate abstract class`
  - Spike `/tmp/protocol_spike_v53_nominal.py`（22 字段，显式声明，不继承 Protocol）: `0 errors, 0 warnings`
  - Spike `/tmp/protocol_spike_v53_final.py`（完整 pipeline，显式声明 + structural subtyping）: pyright `0 errors` + runtime `Full pipeline: PASS`
- **影响**: 采纳原始 v5.3 提案将产生新的类型错误，不能实现 "pyright0" 目标
- **建议改法和验证点**:
  1. 采用 1.4 节修正方案：`DayuCliArguments` 显式声明字段，不继承 Protocol
  2. 删除 plan 中 `class DayuCliArguments(argparse.Namespace, ResearchTemplateDispatchArguments[, WriteDispatchArguments])` 的继承写法
  3. 验证: pyright `arguments.py` → 0 errors；`parser.parse_args(namespace=DayuCliArguments())` → 无 abstract 错误
- **修复风险**: 低（仅修改 plan 中的类定义写法，无 runtime 影响）
- **严重程度**: 高

### V53-COUPLING-01 — 中 — 字段"重复"声明的耦合评估

- **位置**: v5.3 修正方案的 `DayuCliArguments` 字段声明与 Protocol 字段声明
- **问题类型**: 过度耦合检查
- **当前写法**: Protocol 声明 consumer 所需字段（最小接口），`DayuCliArguments` 声明 producer 全部字段（完整集合）
- **反例/失败场景**: 新增 Protocol 字段时需同步更新 `DayuCliArguments`；误删 `DayuCliArguments` 字段会导致 structural subtyping 断裂
- **为什么有问题**: 表面上 Protocol 和 `DayuCliArguments` 的字段声明是"重复"的。但从类型系统角度，这是必要的接口实现——Protocol 是 consumer 契约（predicate/selector 的最小视图），`DayuCliArguments` 是 producer 实现（argparse 参数全集）。两者不是"重复定义"而是"契约实现"关系
- **直接证据**:
  - Protocol 字段声明 = consumer 最小接口（22 字段）
  - DayuCliArguments 字段声明 = producer 全集（23 字段，含 research_template_action）
  - 每个 Protocol 字段在 DayuCliArguments 中都有对应声明——这是 structural subtyping 的必要条件
  - 无 Protocol 继承 = 无 abstract class 实例化限制
- **影响**: 维护成本（23 字段 × 2 声明处），但远低于方案 B/C/D 的架构退化成本
- **建议改法和验证点**:
  1. 在 `arguments.py` 模块 docstring 中明确 Protocol vs DayuCliArguments 的职责边界
  2. Slice 11 添加 `DayuCliArguments` 字段追加时，确保与 `WriteDispatchArguments` 逐字段对应
  3. 验证: `rg "^    [a-z_]+: (str|bool|str \| None)$" dayu/cli/arguments.py` 枚举全部声明字段，与两个 Protocol 声明做 set difference 必须为空
- **修复风险**: 低（文档+discipline 化，不改类型系统）
- **严重程度**: 中

### V53-EXT-01 — 低 — 扩展 Protocol 字段时的维护路径不明确

- **位置**: Slice 10→11 的 `DayuCliArguments` 字段追加流程
- **问题类型**: 切片过粗/不可直接实施
- **当前写法**: v5.2 plan 说 "Slice 11 只向已存在的 `arguments.py` 追加 `WriteDispatchArguments`，不重复创建 `DayuCliArguments`"
- **反例/失败场景**: Slice 11 implementation agent 不知道需要在 `DayuCliArguments` 上追加 22 个字段声明（因为 Protocol 不继承，structural subtyping 需要显式字段），可能只追加 Protocol 定义而漏掉 `DayuCliArguments` 字段
- **为什么有问题**: v5.2 plan 从未讨论 `DayuCliArguments` 需要显式字段声明以支持 structural subtyping，implementation agent 可能按原始 v5.3 思路（Protocol 继承）实施
- **直接证据**: Plan §Slice 11 `:1711-1714` 仅提及 "只向 Slice 10 已原子创建的 `arguments.py` 追加 `WriteDispatchArguments`；不得重复定义/替换 `DayuCliArguments`"，未说明 Slice 11 需同时向 `DayuCliArguments` 追加 22 字段声明
- **影响**: Slice 11 可能遗漏 `DayuCliArguments` 字段追加，导致 predicate lambda 无法编译
- **建议改法和验证点**:
  1. Plan §Slice 11 显式说明：追加 `WriteDispatchArguments` Protocol 的同时，在 `DayuCliArguments` 类体中原子追加 22 个对应字段声明
  2. Slice 11 gate 新增：`DayuCliArguments` 类体中 declared fields 数量 = Slice 10 的 1 + Slice 11 的 22 = 23
  3. 验证: AST 审计 `DayuCliArguments` 的 AnnAssign 节点数
- **修复风险**: 低（plan 文本补全 + gate 追加）
- **严重程度**: 低

---

## 3. 剩余风险评估

| 风险 | 类别 | 建议跟踪 |
|---|---|---|
| `DayuCliArguments` 声明的字段类型与 argparse `add_argument` 的 type/default 不一致，pyright 可能在特定参数组合下产生新 `reportArgumentType` | 类型系统边缘 | Slice 10/11 gate 增加 "`pyright dayu/cli/` 0 errors" |
| 表外 `getattr(args, ...)` 不受 Protocol 保护——selector 的有界例外已记录，但其他 39 runner 内部的存量 `getattr` 不在 Slice 10/11 scope | 已知 non-goal | 已是 v5.2 non-goal，由 targeted gate 限制 |
| `str \| None` 字段的 pyright strict 模式可能产生额外检查 | 类型严格性 | 当前 project pyright 配置不包含 strict，无立即风险 |

---

## 4. Open Questions

- Q1: `DayuCliArguments` 是否需要为 `argparse` 默认字段（如 `command: str`）提供显式声明？当前 `main.py` 仅访问 `args.command`，不在任何 Protocol 中。如果 pyright 对未声明字段的 `getattr` 不报错（`Namespace` 支持动态属性），则可保持不声明——但建议验证 `main.py` pyright 结果。

---

## 5. Verdict

**FAIL** — 2 HIGH findings（S10-TYPE-01、V53-MECH-01），v5.2 accepted plan 在 Slice 10/11 的 Protocol conformance 上**不可直接实施**。

| Finding | Severity | 根因 | 修正 |
|---|---|---|---|
| S10-TYPE-01 | HIGH | `DayuCliArguments` 空子类不满足 `ResearchTemplateDispatchArguments` structural subtyping | `DayuCliArguments` 显式声明 `research_template_action: str` |
| S11-TYPE-01 | HIGH | 同根因，22 字段 Protocol 兼容性缺口 | 同修正，Slice 11 追加 22 字段声明 |
| V53-MECH-01 | HIGH | v5.3 Protocol 多继承触发 `reportAbstractUsage` | 不继承 Protocol，改用 structural subtyping |
| V53-COUPLING-01 | MEDIUM | 字段"重复"声明需明确职责边界 | 文档化 Protocol vs DayuCliArguments 契约关系 |
| V53-EXT-01 | LOW | Slice 11 字段追加流程不明确 | Plan 正文显式描述追加步骤+gate |

**关键判据**：
1. WIP pyright 实测确认 `reportArgumentType` 错误 `research_template.py:131`
2. Spike 实测确认 v5.3 原始提案（Protocol 多继承）的 `reportAbstractUsage` 错误
3. Spike 实测确认 v5.3 修正方案（显式字段声明 + structural subtyping）pyright 0 errors + runtime PASS

**修正后可达 code-generation-ready**：v5.3 修正方案（§1.4）已通过隔离 spike 的完整 pipeline pyright + runtime 验证。plan 修正量小（仅修改 `DayuCliArguments` 定义方式，不改变架构、slice 顺序、门禁、测试或其他模块），修复风险低。

---

## 6. Code-Generation-Ready Exact Plan 修正

### 6.1 Plan 文本修正位置

**§Slice 10 `:1509-1523`（`arguments.py` 定义）**——替换为：

```python
"""定义 Dayu CLI 参数的运行时类型与 dispatch 协议。

本模块只依赖 Python 标准库，集中提供 argparse 解析结果的稳定运行时身份，以及
research-template / write 的 consumer 端最小静态字段边界。

Protocol 是 consumer 契约——声明 selector/predicate 所需的最小字段集合。
DayuCliArguments 是 producer 实现——声明 argparse 参数全集。两者通过
structural subtyping 桥接，DayuCliArguments 不继承 Protocol，避免
Protocol data attribute 的 abstract class 实例化限制。
"""

from __future__ import annotations

import argparse
from typing import Protocol


class ResearchTemplateDispatchArguments(Protocol):
    """声明 research-template selector 读取的最小参数字段。"""

    research_template_action: str


class DayuCliArguments(argparse.Namespace):
    """保存 argparse 解析结果并提供稳定的运行时类型身份。

    类体中的字段声明与 Protocol 声明同构——Protocol 定义 consumer 最小契约，
    DayuCliArguments 声明 producer 全量字段。argparse 在运行时通过 setattr
    为实例赋值具体字段值。
    """

    research_template_action: str
```

**§Slice 11 `:1711-1749`（`WriteDispatchArguments` 追加 + `DayuCliArguments` 扩展）**——替换为在已有 `DayuCliArguments` 类体中追加 22 字段声明（而非 Protocol 继承）。在 plan 中增加以下说明：

> Slice 11 向 `arguments.py` 追加两层变更：
> 1. 新增 `WriteDispatchArguments(Protocol)`，声明 22 字段（见原 plan `:1717-1749`）
> 2. 在 `DayuCliArguments` 类体中原子追加 22 个对应字段声明，使类体 total 23 个 `AnnAssign`（Slice 10 的 1 + Slice 11 的 22）
>
> `DayuCliArguments` 不继承任何 Protocol。Protocol 仅作为 `_WriteCommandContext` predicate 与
> selector 的参数类型边界使用。

**§Slice 11 gate 追加**：

```text
# DayuCliArguments 字段计数 gate
python -c "
import ast
from pathlib import Path
mod = ast.parse(Path('dayu/cli/arguments.py').read_text())
for node in mod.body:
    if isinstance(node, ast.ClassDef) and node.name == 'DayuCliArguments':
        ann_count = sum(1 for n in ast.walk(node) if isinstance(n, ast.AnnAssign))
        assert ann_count == 23, f'DayuCliArguments AnnAssign={ann_count}, expected 23'
        print(f'DayuCliArguments declared fields: {ann_count} PASS')
"
# Protocol 字段与 DayuCliArguments 字段 set difference gate
python -c "
import ast
from pathlib import Path
mod = ast.parse(Path('dayu/cli/arguments.py').read_text())
protocol_fields = set()
dayu_fields = set()
for node in mod.body:
    if isinstance(node, ast.ClassDef):
        if 'Protocol' in {b.id for b in node.bases if isinstance(b, ast.Name)}:
            protocol_fields |= {n.target.id for n in ast.walk(node) if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
        elif node.name == 'DayuCliArguments':
            dayu_fields |= {n.target.id for n in ast.walk(node) if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
missing = protocol_fields - dayu_fields
assert not missing, f'DayuCliArguments missing Protocol fields: {missing}'
extra = dayu_fields - protocol_fields
# research_template_action 在 ResearchProtocol 中，command 等其他 argparse 默认字段不在此范围
expected_extra = set()
assert extra == expected_extra, f'DayuCliArguments has unexpected extra fields: {extra}'
print('Protocol-DayuCliArguments field closure PASS')
"
```

### 6.2 不变更项

以下 plan 元素**不需要修改**：

- Slice 0–9 全部内容
- Slice 12–13 全部内容
- 45 args + 1 return 签名传播计数
- `parse_arguments()` 的 `namespace=DayuCliArguments()` 契约
- 39-key mapping 与入口 dispatch/error 不变量（S10-CTRL-03/04）
- Phase table、adapter 函数、predicate lambda 结构
- 所有 gate：pyright、Ruff、coverage、AST、rg pattern、git diff --check
- Spike §0 的证据——Protocol predicate 字段校验能力保持不变

---

*本 review 仅评估 plan correctness，不修改任何 production/test/README 文件。所有 spike 命令可独立复现。*
