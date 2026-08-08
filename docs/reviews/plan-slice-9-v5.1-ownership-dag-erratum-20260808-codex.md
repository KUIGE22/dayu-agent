# Slice 9 v5.1 Ownership / DAG Plan Erratum

- **Gate**: Gateflow plan fix
- **状态**: v5.1 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **基线**: clean HEAD `1d0f9e6`
- **分支**: `codex/dual-model-research-mvp`
- **目标计划**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md`
- **DeepSeek review**: `docs/reviews/plan-review-20260808-075500-deepseek.md`
- **MiMo review**: `docs/reviews/plan-review-20260808-075501-mimo.md`
- **DeepSeek re-review**: `docs/reviews/plan-review-20260808-082000-deepseek.md`（PASS，初审 9 项全 CLOSED，open High/Medium/Low=0/0/2）
- **MiMo re-review**: `docs/reviews/plan-review-20260808-082001-mimo.md`（PASS，初审 findings 全 CLOSED，open High/Medium/Low=0/0/0）
- **DeepSeek corrective re-review**: `docs/reviews/plan-review-20260808-083500-deepseek.md`（PASS，082000 L-01/L-02 CLOSED，open High/Medium/Low=0/0/0）
- **允许修改**: master plan 与本 Controller artifact
- **冻结范围**: production、tests、README、外部 review artifacts

## 1. 根因与 Controller 证据

HEAD `1d0f9e6` 的 `research_template.py` 顶层 AST 为 123 个
FunctionDef、39 个 `_run_*`、1 个 entry 与 2 个 ClassDef。主模块终态若只定义
entry + runners，则迁移集合必须为 `123 - 39 - 1 = 83`，旧计划
`22 + 21 + 11 + 9 + 9 = 72` 缺少 11 个 owner，不能实施。

Controller 在本地逐函数、逐边验证后得到唯一闭合分配：

| Owner | FunctionDef | ClassDef | 额外定义 |
|---|---:|---:|---|
| `_research_template_helpers.py` | 22 | 2 | 7 constants |
| `_research_template_core.py` | 26 | 0 | — |
| `_research_template_bundle.py` | 12 | 0 | — |
| `_research_template_monitoring.py` | 11 | 0 | — |
| `_research_template_materialize.py` | 12 | 0 | — |
| `research_template.py` | 40 | 0 | entry 1 + runners 39 |

83 个迁移函数在五 owner 中恰好出现一次；missing、extra、overlap 均为 0。
`ResearchTemplate` 与 `ResearchTemplateRecommendation` 迁至 helpers，消除新
owner 反向 import main 的 cycle。七个常量也迁至 helpers，其中存量
`_DATA_SOURCE_BINDING_CANDIDATES` 的 `object` 语义 occurrence 1→1，不新增
签名、传播或 escape。

逐边 free-global/call graph 只产生下列 DAG：

```text
main → helpers + core + bundle + monitoring + materialize
core → helpers
bundle → core + helpers
monitoring → bundle + core + helpers
materialize → monitoring + bundle + core + helpers
helpers → zero internal project-domain dependencies
```

retained entry + 39 runners 对迁移函数的真实引用精确闭合为
helpers/core/bundle/monitoring/materialize `6/18/6/9/6 = 45`；这些是正常功能
binding。其余 38 个迁移函数不得为兼容旧路径重新绑定。

## 2. DeepSeek findings 裁决

| Finding | Controller 裁决 | v5.1 处置 |
|---|---|---|
| H-01：72 与实际 83 不闭合 | **ACCEPTED** | S9-CTRL-01 改为 exact83，并以 `22/26/12/11/12` 闭合 |
| H-02：缺少逐函数 ownership | **ACCEPTED** | Slice 9 逐名列出全部 83 个函数、2 dataclass 与 7 constants |
| H-03：dataclass 留在 main 会反向依赖/cycle | **ACCEPTED** | 两类统一迁至零内部 domain dependency 的 helpers；禁止新 owner import main |
| M-01：`_print_definition_header` owner 不明 | **ACCEPTED** | 明确归 helpers，计入 exact22；主模块以真实 runner binding import |
| M-02：tests owner 迁移欠规格 | **ACCEPTED** | direct definition/import/dependency patch 迁真实 owner；entry/runner global lookup 才保留 main；新增 identity45 |
| M-03：`write.py:4589` 行号陈旧 | **ACCEPTED** | 改为当前 line 81 的 function-local import，并锁定新 materialize owner 路径 |
| L-01：终态 `__all__` 未定义 | **ACCEPTED** | 当前68删除exact13、保留exact55；禁止 solely-for-compat import；私有 owner 不设 `__all__` |
| L-02：DAG 未逐边验证 | **ACCEPTED** | S9-CTRL-02 写入完整逐层 DAG 与 AST free-global gate |
| L-03：runner import 需求未枚举 | **ACCEPTED** | S9-CTRL-03 逐 owner 列出 exact45 functional bindings 与 `6/18/6/9/6` gate |

DeepSeek 附录提出的 `30/23/11/10/9` 只是 preliminary allocation，不作为
finding 的修复方案采纳。直接反例：其把
`_resolve_template_selection_from_write_manifest` 等会调用 core 的函数放入
helpers，会形成 helpers→core 反向边，破坏 leaf contract。Controller 只接受其
计数、ownership、cycle、tests、lazy import 与 DAG 欠规格等事实 findings。

## 3. MiMo findings 裁决

| Finding | Controller 裁决 | v5.1 处置 |
|---|---|---|
| #1：非 runner/dispatcher 实为83，旧“100辅助/72迁移”不正确 | **ACCEPTED** | §1.1/§1.5/Slice9 全部改为 AST exact123 = 83 + 39 + 1 |
| #2：五模块计数/私有函数分配不一致 | **ACCEPTED** | 采用逐边验证后的 `22/26/12/11/12` exact inventory |
| #3：dataclass 留在 main 会 cycle | **ACCEPTED** | 两 dataclass 迁 helpers，main ClassDef exact0，Slice10 不重复迁移 |
| #4：`_DATA_SOURCE_BINDING_CANDIDATES` 含存量 `object` | **ACCEPTED** | 记录为有界存量常量迁移，semantic occurrence 1→1；不是新增函数签名/escape，不在纯 owner migration 中改变业务值结构 |

MiMo 的 preliminary 分配与整体算术不采纳：其文本同时给出“迁移78”与“主模块
FunctionDef 41”，合计119，不能闭合当前123；另将
`_print_definition_header` 留在 main，与 Controller 已锁定的 main exact40 冲突。
Controller 接受其 83-count、dataclass cycle、存量 `object` 与 owner 欠规格等事实
findings，但以本地 AST 逐边结果替换未闭合的建议分配。

## 4. v5.1 计划改动

Master plan 已完成：

1. header/status/tail 当前为 `v5.1 ACCEPTED / DUAL PLAN RE-REVIEW PASS`，
   保留 v5.0 accepted 历史并加入初审、re-review 与 corrective re-review
   sources。
2. 新增 S9-CTRL-01..04 changelog；修正当前 baseline、§1.1、§1.5、架构树、
   依赖方向与当前 `write.py` 事实。
3. Slice 9 逐名写入 exact83 ownership、2 dataclass、7 constants、完整 DAG、
   exact45 functional imports、exact55 `__all__`、tests owner、write lazy import、
   Slice10 handoff 与全部结构/行为/coverage 门禁。
4. Slice 10 明确 dataclass 已由 Slice 9 helpers 持有，但 entry + 39 runners 的
   `DayuCliArguments` 传播保持不变。
5. 风险、硬约束与 Ready-for-Review checklist 同步加入 Slice 9 的精确闭环。

## 5. Re-review observations 裁决

两路 re-review 均确认 v5.1 核心计划 PASS、初审 findings 全部 CLOSED。Controller
对新 observations 的逐项裁决如下：

| Observation | Controller 裁决 | 理由 |
|---|---|---|
| DeepSeek L-01：`write.py:81` 可能因 Slice 8 尚未实施而漂移 | **REJECTED-WITH-REASON / CLOSED** | factual error。HEAD `1d0f9e6` 正是 Slice 8 accepted 后基线，line 81 是当前实测，不是未来预测；§9e 同时以 `_materialize_research_after_write` 内 function-local import 作为语义锚点，并以旧 owner path exact0 / 新 owner path exact1 验收，不依赖实施者盲从行号。无需 plan 语义修正 |
| DeepSeek L-02：private owners 不设 `__all__` 可能影响未知 star consumer | **REJECTED-WITH-REASON / CLOSED** | non-defect。review 自身明确“不是 bug”；plan 已锁定 private owner `__all__` exact0、main 68 删除13→55、direct-owner tests/known consumers 迁移、compatibility binding exact0、import smoke 与旧/new lazy 路径。仓库内无未知 star consumer 证据，为下划线私有模块新增 `__all__` 会扩大 star-import surface 与契约，违反最小 private surface 目标 |
| MiMo PASS / open High/Medium/Low=0/0/0 | **ACCEPTED** | 独立复核确认 exact83、DAG、exact45、`__all__`、dataclass/constants、tests/lazy import 与门禁全部闭合 |

**Controller 结论**: 初审 findings 与两项新 Low observations 全部 CLOSED；当前
open High/Medium/Low=0/0/0。两项 Low 均不触发语义 plan fix，现有 S9-CTRL-01..04
与 Slice 9 实施契约保持不变。DeepSeek corrective 083500 已确认两项裁决正确并
PASS/open0；与 MiMo 082001 PASS/open0 共同完成 final dual plan re-review。

## 6. 验证与残余风险

已执行的 plan-only 自审：

- AST exact counts：`123 total / 40 retained / 83 assigned`；五 owner
  `22/26/12/11/12`。
- ownership：missing `[]`、extra `[]`、overlap `[]`。
- call graph：只含 plan 允许的十条跨 owner 边，零 reverse/cycle。
- main functional binding：`6/18/6/9/6 = 45`。
- dataclass exact2、required constants exact7 均存在。

**残余风险**: 无未分类 plan risk。DeepSeek 083500 与 MiMo 082001 已完成双路
zero-open 闭环；production/tests/README 未修改，Slice 9 可按 accepted v5.1
恢复 implementation。

## 7. 状态

**v5.1 ACCEPTED / DUAL PLAN RE-REVIEW PASS**。DeepSeek corrective 083500 与
MiMo 082001 均 PASS/open High/Medium/Low=0/0/0；初审 13 项（DeepSeek 9 +
MiMo 4）与 DeepSeek 082000 两项 Low 全部 CLOSED。S9-CTRL-01..04 accepted，
Slice 9 code-generation-ready，可实施。
