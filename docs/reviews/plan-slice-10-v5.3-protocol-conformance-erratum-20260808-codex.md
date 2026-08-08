# Slice 10/11 v5.3 Protocol Conformance Erratum（Controller）

- **状态**: v5.3 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **日期**: 2026-08-08
- **分支**: `codex/dual-model-research-mvp`
- **基线**: `0573d63 gateflow: accept cli write architecture plan v5.2`
- **修改范围**: 仅 master plan 与本 Controller artifact；当前 Slice 10 production WIP、tests、README、外部 review 全部冻结
- **审查输入**:
  - `docs/reviews/plan-review-20260808-103000-deepseek.md`
  - `docs/reviews/plan-review-20260808-103001-mimo.md`
  - `docs/reviews/plan-review-20260808-104500-deepseek.md`（final PASS，open High/Medium/Low=0/0/0）
  - `docs/reviews/plan-review-20260808-104501-mimo.md`（final PASS，open High/Medium/Low=0/0/0）

## 1. 触发证据

当前 Slice 10 WIP 的 `run_research_template_command(args: DayuCliArguments)` 会把
`args` 传给 `_resolve_research_template_action(args: ResearchTemplateDispatchArguments)`。
v5.2 的 Dayu 类体没有声明 `research_template_action`，因此 pyright 精确报
`reportArgumentType`。同一缺口会在 Slice 11 的 Write predicate consumer 上重现。

DeepSeek 的 isolated full-instantiation spike 进一步证明：让 Dayu nominally 多继承
data-attribute Protocol 虽可通过参数兼容检查，却会在
`DayuCliArguments()` 触发 `reportAbstractUsage`。MiMo 的 runtime/MRO/argparse 证据只证明
Python 运行时可工作，未覆盖这个静态实例化门禁，不能据此采纳多继承。

## 2. Controller 决策

采用“显式字段 + structural subtyping”：Protocol 定义 consumer 最小契约，Dayu
concrete class 作为 parser producer 显式声明对应字段；Dayu 只继承
`argparse.Namespace`，不继承任何 Protocol。

### 2.1 Slice 10：S10-CTRL-05

`arguments.py` 定义顺序必须为：

1. `ResearchTemplateDispatchArguments(Protocol)`，exact1 字段
   `research_template_action: str`；
2. `DayuCliArguments(argparse.Namespace)`，显式声明同一个 exact1 字段。

Dayu 无字段默认值、无 `__init__`、无 Protocol inheritance。真实
`parse_args(namespace=DayuCliArguments())`、45 args + 1 return 传播、39-key mapping、
selector fallback 与 entry error behavior 均保持 v5.2 不变。

### 2.2 Slice 11：S11-CTRL-01

`WriteDispatchArguments(Protocol)` 的真实精确字段数为 **20**，不是 DeepSeek review
所写的 22：

- Phase A bool（11）：
  `revalidate_write_model_configuration_manual_recovery_incident_dossier`、
  `inspect_write_model_configuration_manual_recovery_incident`、
  `audit_write_model_configuration_manual_recovery_history`、
  `revalidate_write_model_configuration_manual_recovery_gate_verification`、
  `verify_write_model_configuration_manual_recovery_gate`、
  `check_write_model_configuration_manual_recovery_gate`、
  `revoke_write_model_configuration_manual_recovery_clearance`、
  `restart_write_model_configuration_manual_recovery_after_clearance_revocation`、
  `clear_write_model_configuration_manual_recovery`、
  `verify_write_model_configuration_manual_recovery`、
  `recover_write_model_configuration`；
- Phase B bool（2）：`apply_write_model_configuration`、
  `rollback_write_model_configuration`；
- Phase D/F/G bool（3）：`summary`、`preflight_only`、`reprice_costs`；
- Phase A optional path（3）：
  `challenger_config_manual_recovery_receipt_input`、
  `challenger_config_manual_recovery_plan_output`、
  `challenger_config_manual_recovery_approval_output`；
- Phase F optional path（1）：`routing_challenger_run_approval_input`。

Slice 11 新增该 exact20-field Protocol 时，必须在既有 Dayu 类原子追加同名同类型的
20 字段。Dayu 终态为 exact21 个 `AnnAssign`（research 1 + write 20），不是 23。
两个 Protocol 的字段并集必须与 Dayu 字段集合精确相等，零 missing、零 extra。

表外 `command` 等 argparse 字段继续由 parser 动态写入；runner 内表外存量
`getattr` 仍是 non-goal。此设计不把 Dayu 扩为所有 argparse 字段的 god bag。

## 3. Finding 逐项裁决

| 来源 | Finding | Controller 裁决 | 计划闭环 |
|---|---|---|---|
| DeepSeek 103000 | S10-TYPE-01 | **ACCEPT / CLOSED-BY-PLAN-TEXT** | S10-CTRL-05 为 Research Protocol 与 Dayu 各声明 exact1 字段，消除 structural conformance gap |
| DeepSeek 103000 | S11-TYPE-01 | **ACCEPT / CLOSED-BY-PLAN-TEXT** | S11-CTRL-01 新增 Write Protocol exact20，并向 Dayu 原子追加 exact20；review 的 22/23 纠正为 20/21 |
| DeepSeek 103000 | V53-MECH-01 | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 禁止 Protocol inheritance，保留 `DayuCliArguments()` 可静态实例化 |
| DeepSeek 103000 | V53-COUPLING-01 | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 明确 consumer Protocol / producer Dayu 职责，并以字段集合 equality gate 防漂移 |
| DeepSeek 103000 | V53-EXT-01 | **ACCEPT / CLOSED-BY-PLAN-TEXT** | Slice 11 明确 Protocol 与 Dayu20字段必须同一原子修改 |
| MiMo 103001 | H01（空 Dayu 不满足 Protocol） | **ACCEPT / CLOSED-BY-PLAN-TEXT** | 事实根因并入 S10-CTRL-05/S11-CTRL-01 |
| MiMo 103001 | Protocol 多继承推荐 | **REJECT-WITH-REASON** | runtime/MRO 证据不足；isolated full instantiation pyright 报 `reportAbstractUsage`，违反 pyright0 与真实 namespace 构造契约 |

Controller 接受两路关于 v5.2 conformance 缺口的直接事实；拒绝多继承修复机制。方案
type alias、字段默认值、`__init__` 填充、cast、type-ignore、adapter、glue 与“声明全部
argparse 字段”的 god bag 均不采用。

## 4. 精确门禁

- Slice 10：Research Protocol `AnnAssign` exact1；Dayu `AnnAssign` exact1；字段集合
  相等；Dayu bases 仅 `argparse.Namespace`；defaults/`__init__`/Protocol inheritance 0。
- Slice 11：Research Protocol exact1；Write Protocol exact20；Dayu exact21；
  `protocol_union <= dayu_fields` 且 `dayu_fields == protocol_union`，零 extra。
- 真实 `parse_args(namespace=DayuCliArguments())` 返回 Dayu/Namespace 双重 runtime
  identity，并保存 parser 字段；selector/predicate 接收 Dayu；`pyright dayu/cli/` 0。
- S10-CTRL-03/04、45 args + 1 return、39 mapping、unknown/caught-exception behavior
  原门禁全部保留。
- 对 plan 中当前 Slice10/11 计数做 scoped 审计：stale write-field 22、Dayu-total 23、
  Protocol 多继承实施方案均为 0；历史 review 计数纠正说明不计作 stale contract。

## 5. 冻结范围证据

编辑计划前记录：

- tracked production WIP diff SHA-256：
  `af0fc591de4e3f63bdc181efa6f446c6694b7f417b7b30d35fc508e308a756ea`；
- untracked `dayu/cli/arguments.py` SHA-256：
  `9d1e34d065881aa41fcb8a3b0ce7a815893e1ac0a1824514212c72ee754920c3`。

收尾复算得到相同两个 SHA-256，冻结校验 **PASS**。本 erratum 不修改
production/tests/README 或两份外部 review。

## 6. 自审结果

- master plan Slice 10 code block：Research Protocol fields=1，Dayu fields=1；
- master plan Slice 11 code block：Write Protocol fields=20，Dayu final fields=21；
- 顶部、状态与尾注均为 `v5.3 ACCEPTED / DUAL PLAN RE-REVIEW PASS`，v5.2
  accepted 历史保留；
- scoped current-contract 审计没有残留 22/23 计数或 Protocol-inheritance 实施方案；
  review measurement-error 与 rejected-alternative 说明是有意保留的证据；
- `git diff --check`、两份工作文档 trailing-whitespace/final-newline 检查通过。

## 7. Final dual plan re-review

- DeepSeek 104500：**PASS**；S10-TYPE-01、S11-TYPE-01、V53-MECH-01、
  V53-COUPLING-01、V53-EXT-01 共 5/5 全部 CLOSED；确认其 22/23 measurement
  error 已由 plan 纠正为 20/21；open High/Medium/Low=0/0/0。
- MiMo 104501：**PASS**；H01 CLOSED，并基于完整实例化 pyright 证据撤回 Protocol
  多继承建议；确认 S10-CTRL-05/S11-CTRL-01；open High/Medium/Low=0/0/0。
- 合计 5 项 DeepSeek findings + MiMo H01 全部 CLOSED，无剩余 finding；v5.3
  `ACCEPTED / DUAL PLAN RE-REVIEW PASS`。

## 8. Residual

双路计划复审已闭环，Slice 10 可恢复 implementation。除 Protocol
conformance/字段 ownership 外，其他 slice 零语义变化。
