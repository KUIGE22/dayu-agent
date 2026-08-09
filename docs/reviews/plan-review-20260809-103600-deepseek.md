# Plan Re-Review（final corrective）：Slice 2 PRR2 observation 闭合核对

- Reviewer lane: DeepSeek（只读 final corrective re-review）
- Date: 2026-08-09
- Branch: `feat/investment-agent-acceptance`
- Baseline: `a6cc350`
- Review 对象: `docs/plans/2026-08-09-investment-agent-aapl-acceptance.md` 当前未提交 diff
- 前序真源: `docs/reviews/plan-review-20260809-102800-deepseek.md`（PASS，PRR2-M1 / PRR2-L1）
- Scope: **仅**核对 PRR2-M1、PRR2-L1 与 MiMo 同步指出的 §8.2 身份枚举三项。未广审，未复审已关闭 findings，未修改任何文件，未运行 live/付费/联网命令。

## Verdict

**PASS**

Open High **0** / Open Medium **0** / Open Low **0**。

三项 observation 全部闭合，均为定点修正，未引入新表述矛盾。本 lane 无剩余阻断项。

---

## 1. 逐项闭合核对

### PRR2-M1（M）§5.4 产物 inventory 未随 v2 同步 — **CLOSED**

前序缺口有两处，均已修正：

**(a) terminal verify receipt 落点**。§5.4 固定树新增第八项：

```
│   └── verify.json                 # 全部 planned specs 成功后才允许出现的 terminal receipt
```

文件名由 plan 钉死为 `verify.json`，implementer 不再需要自行发明——这正是前序 finding 的核心诉求（receipt 身份必须 plan-owned）。行内注释同时复述了出现条件，与 §5.1「terminal verify receipt 只允许在全部 specs 成功后出现」同口径。§5.4 末段另补「`verify.json` 是可选 terminal receipt，只能在全部 planned specs 成功后出现」，把「可选性」显式化——这一点在前序文本中缺失，而它对 receipt 前缀闭合逻辑是必要的：失败前缀场景下 `verify.json` 必须允许不存在，否则 §5.1 的前缀闭合规则与固定树清单会互相矛盾。此处补得比我建议的更完整。

**(b) 字段清单**。§5.4 末段由

> `status/started_at/ended_at/duration_seconds/remaining_wall_seconds/**argv**/exit_code/stop_reason`

改为

> `status/started_at/ended_at/duration_seconds/remaining_wall_seconds/safe_argv/argv_digests/exit_code/stop_reason`，不得持久化 raw argv。

`argv` → `safe_argv` + `argv_digests` 的拆分与 §5.1 的 v2 契约（三 placeholder 安全 token matrix + 每条 raw argv canonical JSON 的 SHA-256）精确对应；复数 `argv_digests` 与「一个 phase spec 含 one-or-more argv token tuples」的多命令 phase（`download.json` 三条、`validations.json` 五条）一致，无单复数歧义。尾句「不得持久化 raw argv」使 §5.4 从「字段清单」升级为可独立执行的约束，消除了它被当作权威清单读取时与 §5.1 冲突的风险。

### PRR2-L1（L）`_PHASE_SCHEMA_VERSION` 常量化未明写 — **CLOSED**

§5.1 相应句由「`_PLAN_SCHEMA_VERSION` 升为 2，parser 使用常量而非 magic literal」改为：

> `_PLAN_SCHEMA_VERSION` 与 `_PHASE_SCHEMA_VERSION` 均升为 2，两个 parser 都使用**对应**常量而非 magic literal，并明确拒绝 v1、不写兼容分支。

两个 parser 双双点名，「对应常量」措辞排除了误用同一常量的可能。这直接覆盖我上轮指出的代码事实：`utils/investment_agent_acceptance_contracts.py:1834-1836` 的 `parse_phase_receipt` 硬编码字面量 `1`，本轮必改，现在 plan 已规定改法为常量引用（常量 `_PHASE_SCHEMA_VERSION` 已存在于 `:34`），implementer 照写字面量 `2` 即违反 plan，而非只违反 AGENTS.md:41。「明确拒绝 v1、不写兼容分支」同时适用于两个 parser，与 AGENTS.md:51 一致；工作树无任何已生成 `acceptance-plan.json` 或 phase receipt，拒绝 v1 无现存数据代价（上轮已复证）。

### MiMo 同步指出的 §8.2 身份枚举 — **CLOSED**

§8.2 首条复现枚举已补入三个 v2 新字段，现文为：

> 任何 as-of、三组窗口、price JSON/Markdown、预算、模型、代码、package config canonical tree/诊断用关键文件、package `research_templates/` canonical tree、根级 `定性分析模板.md`、**canonical run root**、**ordered phase specs**、**required environment presence**、timeout grace 或命令变化都生成新 run-id/plan。

与 §5.1 的 v2 字段集逐项对照：

| v2 fingerprinted 字段 | §8.2 覆盖 |
|---|---|
| canonical run root | 已显式列出 |
| ordered phase specs | 已显式列出 |
| required environment names + presence | 「required environment presence」覆盖（names 与 presence 同源于同一组三个固定名，names 漂移必然改变该结构） |
| primary/audit 模型绑定 | 「模型」 |
| terminal action | 见下方说明 |
| 其余（as-of/窗口/price/预算/代码/package inputs/grace） | 原有条目已覆盖 |

关于 terminal action 未被单独列名：该字段按 §5.1 第 (5) 项「terminal action 精确等于 `verify`」是**固定枚举常量**，parser 要求其精确等值，因此它在合法 plan 中不存在可变取值，不构成独立漂移源；且「或命令变化」在语义上已兜住。故不构成枚举缺口，本轮不开 finding。

§8.2 与 §13 stop conditions（L643 已含 run root 漂移）现已同口径，复现章节不再是 v2 身份的滞后描述。

---

## 2. 结论

- PRR2-M1、PRR2-L1 与 §8.2 身份枚举三项 **全部 CLOSED**，修正为定点、可复证，未产生新的表述矛盾或新真源。
- 本 lane 对该 revision 判定 **PASS**，Open High 0 / Medium 0 / Low 0。
- 放行仍以 gate 规则为准：需 DeepSeek 与 MiMo 双路对**同一** revision 均 PASS、Controller 关闭全部 plan findings 后，Slice 2 方可恢复实施。本 review 本身不构成放行。
- 不授权 SEC / Web / DeepSeek / MiMo / 真实凭据检查或付费运行；Slice 5 维持 `LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED`。

## 3. Review 边界声明

- 只读；未修改 plan / 生产代码 / 测试 / README / fixture。
- 未运行 live、付费、联网命令；未运行 pytest / pyright（本轮为 plan re-review）。
- 本轮只核对三项指定 observation，未重审已在 `plan-review-20260809-101700-deepseek.md` / `plan-review-20260809-102800-deepseek.md` 中关闭的 findings，未独立复核 MiMo lane 的其它结论，未审 Slice 0/1/3/4/5 与仓库其它模块。
- 引用的代码事实取自 baseline `a6cc350` 工作树：`utils/investment_agent_acceptance_contracts.py:34`、`:1834-1836`。
