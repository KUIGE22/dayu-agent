# Plan Review: v5.3 Slice 10/11 Protocol Conformance — Targeted Re-Review

- **日期**: 2026-08-08 10:45
- **审查类型**: v5.3 targeted re-review（基于 103000 初审 S10-TYPE-01 等 5 findings 逐项核验）
- **初审 artifact**: `docs/reviews/plan-review-20260808-103000-deepseek.md`（FAIL, 5 findings: S10-TYPE-01/S11-TYPE-01/V53-MECH-01 HIGH, V53-COUPLING-01 MEDIUM, V53-EXT-01 LOW）
- **Controller erratum**: `docs/reviews/plan-slice-10-v5.3-protocol-conformance-erratum-20260808-codex.md`
- **审查计划**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md`（v5.3 CANDIDATE / AWAITING DUAL RE-REVIEW）
- **审查 HEAD**: `0573d63`
- **审查人**: DeepSeek (planreview skill, targeted re-review pass)

---

## 1. Re-Review 范围

仅核验 103000 初审的 5 项 findings 是否被 v5.3 erratum + Controller 裁决完全修正：

1. S10-TYPE-01 — `DayuCliArguments` 空子类不满足 `ResearchTemplateDispatchArguments`
2. S11-TYPE-01 — 同根因在 Slice 11 的 20 字段 Write Protocol 重现
3. V53-MECH-01 — v5.3 原始提案 Protocol 多继承触发 `reportAbstractUsage`
4. V53-COUPLING-01 — Protocol/Dayu 字段"重复"声明的耦合评估
5. V53-EXT-01 — Slice 11 字段追加流程不明确

同时核验 103000 的 22/23 计数误差是否已纠正为 Controller 确认的 20/21。

---

## 2. 逐项核验

### S10-TYPE-01（HIGH）— DayuCliArguments 空子类不满足 ResearchTemplateDispatchArguments

| 证据来源 | 位置 | 内容 |
|---|---|---|
| S10-CTRL-05 | plan `:32` | Dayu 显式声明 `research_template_action: str`，通过 structural subtyping 对接 Protocol |
| Slice 10 代码块 | plan §Slice 10 | `class DayuCliArguments(argparse.Namespace):` 类体含 `research_template_action: str` |
| 定义顺序 | plan §Slice 10 | Research Protocol → Dayu concrete class |
| Dayu 不继承 Protocol | plan §Slice 10 | "只继承 `argparse.Namespace`，不得继承任何 Protocol" |
| Isolated spike S10 | `/tmp/v53_rr_s10.py` | pyright `0 errors, 0 warnings, 0 informations`；runtime `PASS` |
| Dayu bases | spike | `['Namespace']` — 仅 argparse.Namespace |

**裁决: CLOSED** — v5.3 S10-CTRL-05 锁定 Slice 10 的 Research Protocol exact1 + Dayu exact1，structural subtyping 提供类型兼容。isolated spike 验证 pyright 0 errors、runtime PASS、Dayu bases 仅 Namespace。S10-TYPE-01 的 `reportArgumentType` 根因已消除。

---

### S11-TYPE-01（HIGH）— DayuCliArguments 不满足 WriteDispatchArguments（同根因）

| 证据来源 | 位置 | 内容 |
|---|---|---|
| S11-CTRL-01 | plan `:32` | Write Protocol exact20（11+2+3 bool + 3+1 optional path）；Dayu 终态 exact21 |
| Slice 11 代码块 | plan §Slice 11 11a | `class WriteDispatchArguments(Protocol):` exact20 字段逐项列出 |
| Dayu 终态代码块 | plan §Slice 11 11a | `class DayuCliArguments(argparse.Namespace):` exact21 `AnnAssign`（research1 + write20） |
| 字段并集相等 | plan `:32` | "Protocol 字段并集必须与 Dayu 字段集合精确相等，零 extra" |
| Dayu bases gate | plan §Slice 11 gate | "Dayu bases 仅 `argparse.Namespace`；defaults/`__init__`/Protocol inheritance 0" |
| Isolated spike S11 | `/tmp/v53_rr_s11.py` | pyright `0 errors, 0 warnings, 0 informations`；runtime `PASS` |
| 字段计数验证 | spike | `Research=1 Write=20 Dayu=21 Protocol_union==Dayu — PASS` |

**裁决: CLOSED** — v5.3 S11-CTRL-01 锁定 Write Protocol exact20 + Dayu 终态 exact21，字段并集精确相等。my 103000 的 22/23 计数是 measurement error，已按 Controller 逐字段实数纠正。isolated spike 验证 pyright 0 errors、predicate lambda 编译通过、structural subtyping 全链路兼容。

---

### V53-MECH-01（HIGH）— v5.3 Protocol 多继承触发 reportAbstractUsage

| 证据来源 | 位置 | 内容 |
|---|---|---|
| Dayu 不继承 Protocol | plan `:32` | "禁止 Protocol inheritance" |
| Slice 10 代码块 | plan §Slice 10 | `class DayuCliArguments(argparse.Namespace):` — 仅 argparse.Namespace 父类 |
| Slice 11 代码块 | plan §Slice 11 11a | `class DayuCliArguments(argparse.Namespace):` — 仅 argparse.Namespace 父类 |
| MRO 验证 | spike | Protocol 不在 MRO：`len(protocol_in_mro) == 0` |
| 实例化 | spike | `DayuCliArguments()` — pyright 0 errors（无 abstract class 错误） |
| Controller rejection | erratum `:87` | MiMo 的 Protocol 多继承推荐被 REJECT-WITH-REASON：runtime/MRO 证据不足，full instantiation pyright 报 `reportAbstractUsage` |

**裁决: CLOSED** — v5.3 明确禁止 Protocol inheritance。Dayu 仅继承 `argparse.Namespace`，Protocol 在 MRO 中完全不存在。`DayuCliArguments()` 可以静态实例化（pyright 0 errors）。Controller 正式拒绝了 Protocol 多继承机制。

---

### V53-COUPLING-01（MEDIUM）— 字段"重复"声明的耦合评估

| 证据来源 | 位置 | 内容 |
|---|---|---|
| 职责边界 | plan §Slice 10 | "Protocol 是 selector 的 consumer 最小契约；Dayu 是 parser namespace producer" |
| 字段 equality gate | plan §Slice 11 gate | "Protocol 字段并集必须与 Dayu 字段集合精确相等，零 missing、零 extra" |
| AST gate | plan `:95-96` | `protocol_union <= dayu_fields` 且 `dayu_fields == protocol_union` |
| 禁止 god bag | plan §Slice 10 | "表外 argparse 字段不因本 Slice 被机械加入 Dayu 类" |
| 禁止 defaults | plan §Slice 10 | "类体必须有 exact1 个无默认值 `AnnAssign`，不得新增 `__init__`" |

**裁决: CLOSED** — Consumer Protocol / producer Dayu 的职责边界已在 plan 正文和 gate 中显式文档化。Protocol union == Dayu fields 的精确相等性由 AST gate 锁定。103000 指出的"重复"本质是 interface satisfaction（Protocol 声明契约，Dayu 声明实现），已被 Controller 采纳为 design intent。

---

### V53-EXT-01（LOW）— Slice 11 字段追加流程不明确

| 证据来源 | 位置 | 内容 |
|---|---|---|
| 原子追加说明 | plan §Slice 11 11a | "Slice 11 必须同时把这 20 个字段原子追加到既有 Dayu 类" |
| 终态代码块 | plan §Slice 11 11a | Dayu 类体完整 21 字段（含注释分组：Slice 10 research selector 1、Phase A bool 11、Phase B bool 2、Phase D/F/G bool 3、Phase A path 3、Phase F path 1） |
| AST gate | plan erratum `:95-96` | Slice 10 Dayu `AnnAssign` exact1；Slice 11 Dayu `AnnAssign` exact21 |
| 字段追加 gate | plan erratum `:95` | "Slice 11 新增该 exact20-field Protocol 时，必须在既有 Dayu 类原子追加同名同类型的 20 字段" |

**裁决: CLOSED** — Slice 11 的 Dayu 字段追加流程已显式描述：Protocol 20 + Dayu 20 同一原子修改。AST gate 锁定计数 1→21。implementation agent 有明确的实施步骤和验证命令。

---

## 3. 辅助核验

### 3.1 冻结范围 hash 校验

| 项目 | Controller erratum 记录 | 当前实测 | 匹配 |
|---|---|---|---|
| tracked production WIP diff SHA-256 | `af0fc591de4e3f63bdc181efa6f446c6694b7f417b7b30d35fc508e308a756ea` | `af0fc591...a756ea` | ✅ |
| untracked `dayu/cli/arguments.py` SHA-256 | `9d1e34d065881aa41fcb8a3b0ce7a815893e1ac0a1824514212c72ee754920c3` | `9d1e34d0...920c3` | ✅ |

两个 freeze hash 完全匹配，WIP 未被修改。

### 3.2 v5.2 behavior 不变量保持

| 不变量 | v5.3 状态 |
|---|---|
| S10-CTRL-03 dispatch/error 行为 | 不变——`setup_loglevel` 顺序、try/except/mapping、未知 action `return 1`、三异常 exact stderr |
| S10-CTRL-04 selector exact body | 不变——`str(getattr(args, "research_template_action", "") or "").strip().lower()` |
| 45 args + 1 return 签名传播 | 不变——1+39+1+2+2 = 45 args，1 parse return |
| 39-key mapping 完整 | 不变——39 条目逐项对应 |
| 其他 slice 零语义变化 | 不变——Slice 0–9、Slice 12–13 均不修改 |

### 3.3 v5.3 增量变更约束

| 约束 | 计划证据 |
|---|---|
| 无字段默认值 | plan "无默认值 `AnnAssign`" |
| 无 `__init__` | plan "不得新增 `__init__`" |
| 无 Protocol inheritance | plan Dayu bases 仅 `argparse.Namespace` |
| 无 cast/ignore/adapter/glue | plan 显式禁止 |
| 无 god bag 扩张 | plan "表外 argparse 字段不因本 Slice 被机械加入" |
| 模块仍 stdlib-only | plan "只能 import 标准库" |

### 3.4 Stale contract 审计

| 审计项 | 结果 |
|---|---|
| Write Protocol 22 字段残留（103000 计数误差） | 0 — plan 中无 `:22` 关联的 Write 字段计数；slice 10 与 erratum 均写 20 |
| Dayu 终态 23 字段残留 | 0 — plan 中 Dayu 终态 exact21 |
| Protocol 多继承实施方案 | 0 — Controller 已 REJECT，plan 不包含 |
| stale `class DayuCliArguments(argparse.Namespace, ...Protocol...)` 写法 | 0 — 无此模式 |

### 3.5 pyright 与 runtime spike 汇总

| Spike | Slice | pyright | runtime | 关键验证点 |
|---|---|---|---|---|
| `/tmp/v53_rr_s10.py` | 10 | 0 errors | PASS | Research exact1, Dayu exact1, bases=`[Namespace]` |
| `/tmp/v53_rr_s11.py` | 11 | 0 errors | PASS | Write exact20, Dayu exact21, protocol_union==Dayu, predicate lambda 编译通过 |
| `/tmp/v53_re-review_spike.py` | 10+11 合并 | syntax error（AST 解析代码 bug） | N/A | 不影响独立验证结论；已拆分为两个 clean spike |

---

## 4. 103000 计数误差校正声明

103000 的 Write Protocol 字段数写为 "22"、Dayu 终态写为 "23"，比实际多计 2 个字段。
Controller erratum 已纠正为实数：Write Protocol exact20、Dayu 终态 exact21。
差异根因是 103000 在 Spike `protocol_spike_v53_full.py` 中声明 Protocol 字段时
多写了两个字段（具体多写字段已无关，v5.3 candidate plan 中不存在）。

此误差属于 **measurement error**，不影响 103000 的核心 structural 诊断：
- `DayuCliArguments` 必须显式声明字段满足 structural subtyping ✅
- Protocol inheritance 触发 `reportAbstractUsage` ✅
- Consumer Protocol / producer Dayu 职责分离 ✅
这三点在 v5.3 修正方案中保持不变，仅字段计数从 22/23 纠正为 20/21。

---

## 5. Verdict

**PASS** — 5/5 初审 findings 全部 CLOSED。

| Finding | 103000 Severity | v5.3 Status | Controller | Evidence |
|---|---|---|---|---|
| S10-TYPE-01 | HIGH | **CLOSED** | S10-CTRL-05 | Research exact1, Dayu exact1, structural subtyping |
| S11-TYPE-01 | HIGH | **CLOSED** | S11-CTRL-01 | Write exact20, Dayu exact21, union equality gate |
| V53-MECH-01 | HIGH | **CLOSED** | Protocol inheritance REJECTED | Dayu bases=`[Namespace]`, MRO 零 Protocol |
| V53-COUPLING-01 | MEDIUM | **CLOSED** | 职责边界已文档化 | consumer/producer contract pattern + equality gate |
| V53-EXT-01 | LOW | **CLOSED** | Slice 11 flow 已显式描述 | 原子追加 20 字段 + AST gate exact21 |

open High/Medium/Low = **0/0/0**。

v5.3 Slice 10/11 Protocol conformance 设计已达到 code-generation-ready：
- Structural subtyping 方案已验证 pyright 0 errors + runtime PASS
- Consumer Protocol / producer Dayu 字段精确 closure
- 无 Protocol inheritance / defaults / `__init__` / cast / adapter / glue
- v5.2 behavior 不变量（S10-CTRL-03/04、45+1、39-mapping、entry error）全部保持
- WIP freeze hashes 匹配，旧 plan 版本保留历史
- 103000 的 22/23 counting error 已纠正为实数 20/21

---

*本 review 仅评估 plan correctness，不修改任何 production/test/README 文件。所有 spike 可通过独立脚本复现。*
