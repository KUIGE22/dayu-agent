# Plan Review: v5.3 Slice 10 Dayu Propagation Call-Graph Closure — Focused Adversarial Review

- **日期**: 2026-08-08 11:15
- **审查类型**: Slice 10 call-graph closure focused review — 单一问题：DayuCliArguments 传播到 snapshot-builder 后 4 个 Namespace caller 的 pyright reportArgumentType 如何收敛
- **审查计划**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md`（v5.3 ACCEPTED / DUAL PLAN RE-REVIEW PASS）
- **审查 HEAD**: `e329992`（gateflow: accept cli write architecture plan v5.3）
- **WIP 冻结状态**: Slice 10 部分实施，rollback.py + manual.py 的 `args` 仍为 `argparse.Namespace`
- **审查人**: DeepSeek (planreview skill, focused adversarial pass)
- **范围**: 仅 Slice 10 DayuCliArguments 传播的 call-graph closure；不覆盖 Slice 0–9/11–13、Protocol 类型、dispatch、tests 或 README

---

## 0. 直接证据：当前 pyright 报错

```text
$ source .venv/bin/activate && pyright dayu/cli/commands/_write_config_rollback.py dayu/cli/commands/_write_manual_recovery.py

dayu/cli/commands/_write_config_rollback.py:71:14 - error:
  Argument of type "Namespace" cannot be assigned to parameter "args"
  of type "DayuCliArguments" in function "build_snapshot_builder"
    "Namespace" is not assignable to "DayuCliArguments" (reportArgumentType)

dayu/cli/commands/_write_manual_recovery.py:392:14 - error:
  Argument of type "Namespace" cannot be assigned to parameter "args"
  of type "DayuCliArguments" in function "build_snapshot_builder"
    "Namespace" is not assignable to "DayuCliArguments" (reportArgumentType)

dayu/cli/commands/_write_manual_recovery.py:481:14 - error:
  Argument of type "Namespace" cannot be assigned to parameter "args"
  of type "DayuCliArguments" in function "build_snapshot_builder"
    "Namespace" is not assignable to "DayuCliArguments" (reportArgumentType)

dayu/cli/commands/_write_manual_recovery.py:581:14 - error:
  Argument of type "Namespace" cannot be assigned to parameter "args"
  of type "DayuCliArguments" in function "build_snapshot_builder"
    "Namespace" is not assignable to "DayuCliArguments" (reportArgumentType)

4 errors, 0 warnings, 0 informations
```

### 错误定位

| 文件 | 行 | caller 函数 | 调用 |
|---|---|---|---|
| `_write_config_rollback.py` | 71 | `_run_write_model_configuration_rollback(args: argparse.Namespace)` | `build_snapshot_builder(args=args)` |
| `_write_manual_recovery.py` | 392 | `_run_write_model_configuration_manual_recovery_application(args: argparse.Namespace)` | `build_snapshot_builder(args=args)` |
| `_write_manual_recovery.py` | 481 | `_run_write_model_configuration_manual_recovery_verification(args: argparse.Namespace)` | `build_snapshot_builder(args=args)` |
| `_write_manual_recovery.py` | 581 | `_run_write_model_configuration_manual_recovery_clearance(args: argparse.Namespace)` | `build_snapshot_builder(args=args)` |

### 根因

v5.3 plan 的 Slice 10 传播表（§5 Slice 10 机械类型传播表）将 `_write_snapshot_builder.py` 的两个函数（`_build_snapshot_for_args`、`build_snapshot_builder`）的 `args` 从 `argparse.Namespace` 收窄为 `DayuCliArguments`。当前 WIP 已执行该收窄，但 snapshot-builder 的 4 个 caller —— `_write_config_rollback.py` 的 1 个 runner 与 `_write_manual_recovery.py` 的 3 个 runner —— 的 `args` 仍为 `argparse.Namespace`，且这些 caller **不在** Slice 10 传播表的范围内，造成 call-graph closure 不闭合。

---

## 1. 调用图事实

### 1.1 当前类型状态（WIP HEAD e329992）

| 模块 | 函数 | 当前 args 类型 | 是否调用 build_snapshot_builder | 是否在 Slice 10 传播表 |
|---|---|---|---|---|
| `arguments.py` | `DayuCliArguments` | —（类定义） | — | ✅（新建） |
| `arg_parsing.py` | `parse_arguments()` | 返回 `DayuCliArguments` | — | ✅ |
| `research_template.py` | `run_research_template_command` | `DayuCliArguments` | — | ✅ |
| `research_template.py` | 39 个 `_run_*` | `DayuCliArguments` | — | ✅ |
| `write.py` | `run_write_command` | `DayuCliArguments` | — | ✅ |
| `_write_config_application.py` | `_build_fresh_application_routing_snapshot` | `DayuCliArguments` | — | ✅ |
| `_write_config_application.py` | `_run_write_model_configuration_application` | `DayuCliArguments` | ✅（partial 调用同模块 `_build_fresh_...`） | ✅ |
| `_write_snapshot_builder.py` | `_build_snapshot_for_args` | `DayuCliArguments` | ✅（透传到 `_build_fresh...`） | ✅ |
| `_write_snapshot_builder.py` | `build_snapshot_builder` | `DayuCliArguments` | ✅（partial 调用 `_build_snapshot_for_args`） | ✅ |
| `_write_config_rollback.py` | `_run_write_model_configuration_rollback` | `argparse.Namespace` ❌ | ✅（line 71） | ❌ **不在表内** |
| `_write_manual_recovery.py` | `_run_write_model_configuration_manual_recovery_application` | `argparse.Namespace` ❌ | ✅（line 392） | ❌ **不在表内** |
| `_write_manual_recovery.py` | `_run_write_model_configuration_manual_recovery_verification` | `argparse.Namespace` ❌ | ✅（line 481） | ❌ **不在表内** |
| `_write_manual_recovery.py` | `_run_write_model_configuration_manual_recovery_clearance` | `argparse.Namespace` ❌ | ✅（line 581） | ❌ **不在表内** |
| `_write_manual_recovery.py` | 其余 12 runner/gate 函数 | `argparse.Namespace` | ❌ | ❌ |

### 1.2 调用链

```
run_write_command(args: DayuCliArguments)                      ← Slice 10 传播 ✅
  └─ _run_write_model_configuration_application(args: Dayu)    ← Slice 10 传播 ✅
       └─ functools.partial(_build_fresh_application_routing_snapshot, args=args)
            └─ setup_write_config(args, ...)  ← 接受 argparse.Namespace，使用 getattr

_run_write_model_configuration_rollback(args: Namespace) ❌    ← 不在 Slice 10 表
  └─ build_snapshot_builder(args=args)          ← 要求 Dayu ❌ reportArgumentType
       └─ partial(_build_snapshot_for_args, args, ...)
            └─ _build_fresh_application_routing_snapshot(args=args)
                 └─ setup_write_config(args, ...)  ← Namespace 足够

_run_write_..._manual_recovery_application(args: Namespace) ❌  ← 不在 Slice 10 表
  └─ build_snapshot_builder(args=args)          ← 同上报错
_run_write_..._manual_recovery_verification(args: Namespace) ❌  ← 同上
  └─ build_snapshot_builder(args=args)          ← 同上报错
_run_write_..._manual_recovery_clearance(args: Namespace) ❌     ← 同上
  └─ build_snapshot_builder(args=args)          ← 同上报错
```

### 1.3 关键代码事实

- `setup_write_config(args: argparse.Namespace, ...)`（`dependency_setup.py:716`）**仅使用 `getattr(args, ...)`** 访问字段，不需 `DayuCliArguments` 的具体字段声明
- `_build_fresh_application_routing_snapshot` 将 `args` 传给 `setup_write_config`，其内部也不直接访问 `DayuCliArguments` 特有字段
- `_build_snapshot_for_args` 仅透传 `args` 到 `_build_fresh_application_routing_snapshot`
- `build_snapshot_builder` 仅用 `functools.partial` 绑定 `_build_snapshot_for_args` 的参数
- 对比：`_run_write_model_configuration_application` 确实使用 `getattr(args, "challenger_config_application_plan_input", ...)` 等字段访问，但这些字段 Slice 11 才在 `WriteDispatchArguments` Protocol 中声明——当前 `DayuCliArguments` 类只有 `research_template_action: str` 一个字段，这些 write 字段尚未声明

---

## 2. 方案评估

### 2.1 方案 A：收窄 4 个 caller 的 `args` 为 `DayuCliArguments`

**操作**：将 `_run_write_model_configuration_rollback` 和 manual 的 application/verification/clearance（共 4 个函数）的 `args` 改为 `DayuCliArguments`。

**优点**：
- 所有 `build_snapshot_builder` 的 caller 类型一致
- plan 的 "45 机械传播" 逻辑可扩展为 "49"

**缺点**：
- `_write_manual_recovery.py` 有 15 个函数，仅 3 个调用 `build_snapshot_builder`，其余 12 个不接触 snapshot builder。若只改 3 个、另 12 个保留 `argparse.Namespace`，同一模块内类型不一致——违反终态 API 一致性（plan 自身标明的目标）
- 若为一致性将所有 15 个 manual runner 收窄为 `DayuCliArguments`，则 12 个不需要此类型的函数也被迫接受更窄的类型，比例 3:15 = 仅为偶然调用链（snapshot builder 依赖）收窄
- `DayuCliArguments` 当前只声明 `research_template_action: str`，write 相关的具体字段要到 Slice 11 才追加。这 4 个 runner 使用 `getattr(args, "challenger_config_...", ...)` 访问 write 字段，在 Slice 10 阶段 `DayuCliArguments` 上这些字段**尚未声明**——pyright 的 `getattr` 不报错，但若将来新增直接属性访问则需 Slice 11 字段声明先行
- **计数**: 45 → 49（snapshot-builder 3 个保留 Dayu + 新增 4 个 caller Dayu），但 snapshot-builder 的 3 个本身就值得质疑（见方案 B）

**严重程度**: 中。可实施但违反终态一致性（同模块类型不一致），且 12 个不相关 runner 被排除在外是人为划线。

**裁决**: 不推荐。

---

### 2.2 方案 B（推荐）：保持 3 个 snapshot-builder 函数为 `argparse.Namespace`

**操作**：
- `_build_fresh_application_routing_snapshot(args: argparse.Namespace, ...)` — 回退为 `Namespace`
- `_build_snapshot_for_args(args: argparse.Namespace, ...)` — 回退为 `Namespace`
- `build_snapshot_builder(args: argparse.Namespace, ...)` — 回退为 `Namespace`
- `_run_write_model_configuration_application(args: DayuCliArguments, ...)` — 保持 `DayuCliArguments`

**类型流转**：
```python
# application.py
def _run_write_model_configuration_application(*, args: DayuCliArguments, ...) -> int:
    snapshot_builder = functools.partial(
        _build_fresh_application_routing_snapshot,  # 接受 argparse.Namespace
        args=args,  # DayuCliArguments IS-A argparse.Namespace → ✅
        ...
    )

# rollback.py（不变）
def _run_write_model_configuration_rollback(*, args: argparse.Namespace, ...) -> int:
    snapshot_builder = build_snapshot_builder(
        args=args,  # Namespace → Namespace → ✅
        ...
    )

# manual.py（不变）
def _run_..._application(*, args: argparse.Namespace, ...) -> int:
    snapshot_builder = build_snapshot_builder(
        args=args,  # Namespace → Namespace → ✅
        ...
    )
```

**优点**：
1. **架构正确**：snapshot-builder 是纯基础设施层，其职责是绑定参数并构造零参数回调（`Callable[[], Mapping[...]]`）。它不关心 `args` 是普通 `Namespace` 还是 `DayuCliArguments`——底层 `setup_write_config` 只用 `getattr`。窄类型不应向不需要它的层级传播
2. **继承安全**：`DayuCliArguments` IS-A `argparse.Namespace`，所以 `_run_write_model_configuration_application` 可以安全地将 `DayuCliArguments` 传给接受 `Namespace` 的 `_build_fresh_application_routing_snapshot`
3. **零冗余收窄**：4 个 caller 保持 `Namespace`，无需为 snapshot builder 的 type narrowing 而连锁收窄不相关的 12 个 manual runner
4. **Slice 11 兼容**：Slice 11 引入 `WriteDispatchArguments(Protocol)` 并向 `DayuCliArguments` 追加 exact20 write 字段后，Phase B adapter `_ConfigurationWriteSubcommandEntry.runner: Callable[[_WriteConfigurationContext], int]` 从 context 中取出 `args: DayuCliArguments`，传给 `build_snapshot_builder(args=args)` —— Dayu 作为 Namespace 传入，类型安全
5. **计划可闭合**：传播计数从 45 修正为 **42**（`1+39+1+1` = 42 args 签名 + 1 `parse_arguments` 返回），plan erratum 是局部的计数修正，不改变其余 Slice 语义
6. **pyright 归零**：4 个 reportArgumentType 全部消失

**缺点**：
- plan 的 "机械传播到所有 args 签名" 原则被削弱——但 plan 自身在 §4.3 已承认 Callable 逆变允许接受宽类型的 runner 用于窄类型 dispatch，机械收窄仅为 "终态 API 一致与 rg 可审计"。此处 snapshot-builder 恰是机械收窄产生反效果（创建 call-graph 不闭合）的证据
- 若未来 `setup_write_config` 改为直接属性访问 `args.some_field`，snapshot-builder 保持 `Namespace` 也不会引入新 pyright 错误（因为 `setup_write_config` 仍接受 `Namespace`，而调用方传入的总是具体子类实例）

**计数**: 45 → 42（`_build_fresh_application_routing_snapshot`、`_build_snapshot_for_args`、`build_snapshot_builder` 三个 `args` 签名从 Dayu 回退为 Namespace；`_run_write_model_configuration_application` 保持 Dayu）

**严重程度**: 低（plan 需要一处局部的、精确的 erratum）

**裁决**: **推荐**。最符合架构分层、产生零 pyright 错误、不扩散不必要的类型收窄、与 Slice 11 future context 兼容。

---

### 2.3 方案 C：所有 write internal runner 统一为 `DayuCliArguments`

**操作**：rollback runner + 全部 15 个 manual recovery 函数（包括 12 个不调用 snapshot builder 的）+ 可能其他 write 相关 runner 全部收窄为 `DayuCliArguments`。

**优点**：
- 终态类型完全一致

**缺点**：
1. **范围过大**：Slice 10 scope 从 45 扩展到远大于 49（15+1+ 可能其他 runner），且大部分函数不需要 `DayuCliArguments` 的任何特有字段
2. **时机错误**：`DayuCliArguments` 在 Slice 10 阶段只声明 `research_template_action: str` 一个字段，write 相关字段要 Slice 11 才追加。将这些 write runner 的 `args` 改为 Slice-10 阶段的半成品 Dayu 类，语义不确定
3. **违反 Slice 边界**：Slice 7/8 是 `_write_manual_recovery.py` 和 `_write_config_rollback.py` 的 owner，Slice 10 是类型系统 owner。Slice 10 不应越界大规模修改 Slice 7/8 已成型的模块
4. **测试波及面大**：15 个 manual runner 的 direct tests 全部需要 fixture 改为构造 `DayuCliArguments`，然而这些 runner 的内部逻辑不依赖 `DayuCliArguments`
5. **违反 plan 的 explicit non-goal**："不传播到表外 helper"

**严重程度**: 高。大幅扩大 scope、时机错误、违反 Slice 边界。

**裁决**: 不推荐。

---

### 2.4 方案选择总结

| 维度 | 方案 A | 方案 B（推荐） | 方案 C |
|---|---|---|---|
| pyright 错误 | 0（但需连锁改 16 个函数） | 0 | 0（但需改 >16 个函数） |
| Slice scope 扩大 | 中（4→16 函数） | 无（反向缩小 3 函数） | 大（远 >16 函数） |
| 架构分层 | 部分破坏（infra 用 Dayu） | ✅ 保持（infra 用 Namespace） | 全量破坏 timing |
| 终态一致性 | 同模块不一致（3/15 vs 12/15） | ✅ Namespace 在此层一致 | ✅ 全 Dayu |
| Slice 11 兼容 | 需字段声明先行 | ✅ 无需变更 | 需字段声明先行 |
| Plan erratum 规模 | 中等（计数 + 传播表修正） | 小（仅计数 + 传播表 3 行） | 大（重新划分 Slice 边界） |

**结论：方案 B 是唯一同时满足架构分层、零 pyright 错误、最小 plan erratum 的选择。**

---

## 3. Findings

### 3.1 编号-S10-CALLGRAPH-01-未修复-高-call-graph 闭合缺口

- **位置**: §5 Slice 10 机械类型传播表；`_write_snapshot_builder.py` 的 `_build_snapshot_for_args` / `build_snapshot_builder` → `DayuCliArguments`
- **问题类型**: 架构边界 / 过度耦合 / 切片过粗
- **当前写法**: Slice 10 传播表将 `_write_snapshot_builder.py` 的两个函数的 `args` 收窄为 `DayuCliArguments`，但 snapshot builder 的 4 个 caller（`_write_config_rollback.py` 的 1 个 runner、`_write_manual_recovery.py` 的 3 个 runner）不在传播表中，它们的 `args` 仍为 `argparse.Namespace`
- **反例/失败场景**: WIP 已实施 snapshot-builder 收窄 → `pyright dayu/cli/` 报 4 个 `reportArgumentType`（rollback:71, manual:392,481,581）。按 plan 原样实施必然产生此 4 个类型错误，违反 AGENTS "禁止新增、扩散、掩盖或绕过类型错误" 硬约束
- **为什么有问题**: snapshot-builder 是纯基础设施层（绑定参数 → 返回 `Callable[[], Mapping[...]]`），其内部和下游 `setup_write_config(args: argparse.Namespace, ...)` 仅用 `getattr` 访问字段。将 infra 层收窄为具体 CLI 类型违反了依赖方向——下层不应依赖上层类型。且 `DayuCliArguments` 在 Slice 10 阶段仅声明 `research_template_action` 一个 write-irrelevant 字段，write runner 需要的字段要到 Slice 11 才追加
- **直接证据**:
  1. `pyright` 实测 4 errors（零 false positive）
  2. `dependency_setup.py:716`: `setup_write_config(args: argparse.Namespace, ...)` — 接受宽类型
  3. `dependency_setup.py:731-753`: 全部使用 `getattr(args, ...)` — 不需 Dayu 字段声明
  4. Plan 传播表只列出 6 个文件的 45 个签名，rollback/manual 不在内
  5. Plan §4.3 自身承认 Callable 逆变允许宽类型 → 窄 dispatch 的类型安全
  6. `_write_manual_recovery.py` 定义 15 个函数，仅 3 个调用 `build_snapshot_builder`
- **影响**: 实施 Agent 按 plan 实施 → pyright 报错 → 被迫在方案 A/C 或 glue 之间选择 → 返工
- **建议改法和验证点**:
  1. 在 plan 传播表中将以下 3 个函数从 `DayuCliArguments` 改回 `argparse.Namespace`：
     - `_build_fresh_application_routing_snapshot`（`_write_config_application.py`）
     - `_build_snapshot_for_args`（`_write_snapshot_builder.py`）
     - `build_snapshot_builder`（`_write_snapshot_builder.py`）
  2. `_run_write_model_configuration_application` 保持 `DayuCliArguments`
  3. 更新传播计数：45 → 42（`1+39+1+1` = 42 args + 1 return）
  4. 更新 §5 Slice 10 机械类型传播表，对应 3 行 target 列改为 `argparse.Namespace`（不变）
  5. 更新 targeted gates 中 `rg` 命令：删除对 `_write_config_application.py` / `_write_snapshot_builder.py` 中 `argparse.Namespace` 命中为 0 的要求（或改为确认相关函数签名仍为 `argparse.Namespace`）
  6. 验证: `pyright dayu/cli/` → 0 errors（包含 rollback/manual）
- **修复风险（低）**: 纯 plan 文本修正，不改代码。snapshot-builder 接受 `Namespace` 是 HEAD 创建时的原始签名，只是回退 plan 的过早收窄
- **严重程度（高）**: 若不修正，plan 不可实施——pyright 必然报错，违反 AGENTS 硬约束

---

### 3.2 编号-S10-LAYER-01-未修复-中-基础设施层类型收窄反模式

- **位置**: §5 Slice 10 传播表，snapshot-builder 函数 `args: DayuCliArguments`
- **问题类型**: 架构边界 / 最佳实践偏离
- **当前写法**: plan 将 `build_snapshot_builder` 的 `args` 收窄为 `DayuCliArguments`，暗示该基础设施函数需要 CLI 具体类型
- **反例/失败场景**: 若未来有新 caller（例如 `_write_dispatch.py` 的 adapter）从非 `DayuCliArguments` 上下文调用 `build_snapshot_builder`，会创建不必要的类型依赖。实际上 `build_snapshot_builder` 只将 `args` 绑定到 partial，不访问其任何字段——它对 `args` 的类型需求为**零**
- **为什么有问题**: 这是典型的 "类型向上泄漏"——CLI 层的具体类型传播到不依赖该类型的纯基础设施函数。违反了 AGENTS 编码硬约束 "模块间依赖最小化，优先接口或协议" 和架构硬约束 "设计下层组件接口时必须假设上层组件不存在，不向上泄漏实现细节"。此处 `argparse.Namespace` 就是正确的协议级别——它是 stdlib 的宽接口，不携带 CLI 具体字段的知识
- **直接证据**:
  1. `build_snapshot_builder` 的函数体: `return functools.partial(_build_snapshot_for_args, args, paths_config=paths_config, execution_options=execution_options, run_label=run_label)` ——不访问 `args` 的任何属性
  2. `_build_snapshot_for_args` 的函数体: `return _build_fresh_application_routing_snapshot(args=args, ...)` ——仅透传
  3. `_build_fresh_application_routing_snapshot` → `setup_write_config(args, ...)` → 仅 `getattr`
  4. Plan 本身创建的依赖 DAG `_write_manual_recovery → _write_snapshot_builder → _write_config_application` 定义了 CLI 内部单向依赖——`_write_snapshot_builder` 是被依赖的叶子，不应反向依赖 CLI 类型
- **影响**: 实施 Agent 按 plan 收窄 snapshot-builder → 产生 4 个 caller 的 pyright 错误 → 必须在三个方案中选择 → 若选 A 或 C 则进一步扩散类型污染
- **建议改法和验证点**: 同 S10-CALLGRAPH-01。保持 snapshot-builder 函数为 `argparse.Namespace`
- **修复风险（低）**: 同 S10-CALLGRAPH-01
- **严重程度（中）**: 即便其他方案可绕过 pyright 错误，架构反模式本身值得纠正

---

### 3.3 编号-S10-COUNT-01-未修复-低-传播计数不闭合

- **位置**: §5 Slice 10，"45 个 args 签名（1+39+1+2+2）"
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: `1(RT entry)+39(RT runners)+1(write entry)+2(config_app)+2(snapshot_builder)` = 45
- **反例/失败场景**: 若按算术实施——snapshot_builder 收窄的同时 rollback + 3 个 manual runner 不收窄——4 个 pyright 错误必然出现。计数中缺少这 4 个间接 caller，意味着 "45" 实际不闭合
- **为什么有问题**: 计数是 plan 的实施边界承诺——实施 Agent 依赖此计数验证完整性。一个不闭合的计数误导实施 Agent 认为 45 个修改即可通过 pyright，实则至少需要处理 4 个额外的 reportArgumentType
- **直接证据**:
  1. 45 = `1+39+1+2+2`，其中 `2+2` 是 config_app(2) + snapshot_builder(2) = 4
  2. pyright 报错恰是 snapshot_builder 的 4 个 caller
  3. 这 4 个 caller 不在 `1+39+1+2+2` 的任何一组中
- **影响**: 实施 Agent 在 45 修改后运行 pyright → 4 errors → 困惑/返工
- **建议改法和验证点**: 将计数修正为 42（回退 3 个 snapshot-builder 函数的 Dayu 收窄），并显式注明 `_build_fresh_application_routing_snapshot`、`_build_snapshot_for_args`、`build_snapshot_builder` 保留 `argparse.Namespace`，`_run_write_model_configuration_application` 为 Dayu
- **修复风险（低）**: 纯 plan 算术修正
- **严重程度（低）**: 可与 S10-CALLGRAPH-01 一并修正

---

## 4. Open Questions

无。三个方案的技术完整性和 pyright 行为均已通过直接代码证据验证。方案 B 的 `DayuCliArguments` → `argparse.Namespace` 参数传递已由 `DayuCliArguments(argparse.Namespace)` 继承关系保证。

## 5. Residual Risks

| 风险 | 跟踪目标 |
|---|---|
| Slice 11 Phase B adapter 通过 `_WriteConfigurationContext` 向 `build_snapshot_builder` 传 `DayuCliArguments`——此时 `build_snapshot_builder` 接受 `Namespace`，类型安全（IS-A），但需确保 adapter 代码不假设 `args` 是窄类型 | Slice 11 plan review 时显式验证 adapter → snapshot_builder 调用链的类型流转 |
| 若未来 `DayuCliArguments` 字段声明完成后有人将 `build_snapshot_builder` 再次收窄为 `DayuCliArguments`，call-graph closure 问题会重现 | 在 `_write_snapshot_builder.py` 模块 docstring 注明 `args: argparse.Namespace` 是有意选择——此模块是纯基础设施，不依赖 CLI 具体类型 |

## 6. Final Plan Review Conclusion

**Verdict: FAIL**

**原因**: v5.3 Slice 10 的 "45 传播" 包含一个 call-graph closure 缺口：将 `_build_snapshot_for_args` 和 `build_snapshot_builder` 的 `args` 收窄为 `DayuCliArguments` 后，其 4 个 caller（`_write_config_rollback.py` ×1、`_write_manual_recovery.py` ×3）仍为 `argparse.Namespace`，产生 4 个 `reportArgumentType`。按 plan 原样实施必然违反 AGENTS "禁止新增类型错误" 硬约束。

**HML: High=1, Medium=1, Low=1（open High/Medium/Low = 1/1/1）**

**Plan Erratum（精确修正）**:

1. **§5 Slice 10 机械类型传播表**，以下 3 行 `Slice 10 后` 列从 `DayuCliArguments` 改为 `argparse.Namespace`（即**不变**）：

   | 模块 | 精确目标 | Slice 10 前 | Slice 10 后 |
   |---|---|---|---|
   | `_write_config_application.py` | `_build_fresh_application_routing_snapshot` | `argparse.Namespace` | `argparse.Namespace`（不变） |
   | `_write_snapshot_builder.py` | `_build_snapshot_for_args` | `argparse.Namespace` | `argparse.Namespace`（不变） |
   | `_write_snapshot_builder.py` | `build_snapshot_builder` | `argparse.Namespace` | `argparse.Namespace`（不变） |

   `_run_write_model_configuration_application` 保持 `DayuCliArguments`。

2. **传播计数修正**：`45` → `42`（`1(RT entry)+39(RT runners)+1(write entry)+1(config_app application runner)` = 42 args 签名 + 1 `parse_arguments` 返回签名 = 43 处类型传播）

3. **§5 Slice 10 targeted gates**：删除要求 `_write_config_application.py` 和 `_write_snapshot_builder.py` 中 `argparse.Namespace` 命中为 0 的 `rg` 门禁；改为确认 `_build_fresh_application_routing_snapshot`、`_build_snapshot_for_args`、`build_snapshot_builder` 三个签名为 `argparse.Namespace`，`_run_write_model_configuration_application` 为 `DayuCliArguments`

4. (**可选**) 在 §2.2 依赖方向或 Slice 10 描述中增加一条理由：snapshot-builder 是基础设施层，接受 `argparse.Namespace` 宽类型；`DayuCliArguments` IS-A `Namespace`，CLI 入口可安全传入；下层不依赖上层具体类型。

**修正后预期**: `pyright dayu/cli/` → 0 errors，call-graph 完全闭合，Slice 10 可恢复实施。
