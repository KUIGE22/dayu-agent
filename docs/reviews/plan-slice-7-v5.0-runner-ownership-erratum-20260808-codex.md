# Slice 7 v5.0 runner ownership erratum — Controller adjudication

- **日期**: 2026-08-08
- **分支**: `codex/dual-model-research-mvp`
- **实施基线**: clean HEAD `b55f794 gateflow: accept cli write application snapshot slice 6`
- **前一接受计划**: v4.9 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **接受计划**: v5.0 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **Gate**: plan-only runner-count / ownership erratum
- **状态**: v5.0 ACCEPTED / DUAL PLAN RE-REVIEW PASS

## 1. 范围

本轮只修改 master plan，以及新增本 Controller artifact。未修改
production code、tests、README 或外部 review artifact；未 stage、commit 或
push。Phase A、adapter、Protocol 与 Slice 8 的已接受语义不变。

## 2. 事实证据

对 clean HEAD `b55f794` 的 `dayu/cli/commands/write.py` 做 AST 与源码边界核对后，
得到：

- 文件精确 3096 行，共 32 个当前顶层辅助函数与
  `run_write_command`。
- `_run_write_stage` 与 `_run_write_preflight` 位于 197–478，即 execution
  owner exact 2。
- 14 个 `_run_write_model_configuration_manual_recovery_*` runner 位于
  579–1885；独立 Phase C `_check_write_model_configuration_manual_recovery_gate`
  位于 1888–1932。因此 manual owner 必须为 14 runner + 1 gate = exact 15。
- Slice 7 合计迁移 exact 17 definitions；`write.py` 旧 17 definitions 必须为
  0，并以正常顶层功能 import 保留 exact 17 个 dispatch/global-lookup binding。
- application、verification、clearance 三个 runner 使用
  `build_snapshot_builder`，label 分别为默认、
  `configuration-manual-recovery-verification`、
  `configuration-manual-recovery-clearance`。

两份外部 review 都正确发现 v4.9 当前文字的 12-vs-14 矛盾，但行号
证据中有少量包含尾行的 off-by-one 表述。v5.0 以实际 AST 函数结束行
1885 / 1932 与文件结束行 3096 为准，不照抄 review 中的 1886 / 1933 /
3097。MiMo 对旧 plan “explicit 13 functions total” 的概括也不够精确：旧文本
是“12 runner + gate”的隐含总数；v5.0 现在显式锁定 exact 15。

## 3. Controller 逐项裁决

### 3.1 DeepSeek `plan-review-20260808-061001-deepseek.md`

| Finding | 裁决 | 闭环文本 |
|---|---|---|
| H-01：Slice 7 runner count 12 ≠ 14 | **ACCEPT / CLOSED-by-plan-text** | S7-CTRL-01 与 Slice 7 逐名锁定 14 runner + Phase C gate = manual exact 15；execution exact 2；`write.py` old defs 0 / new owner bindings exact 17。 |
| M-01：§1.2 基线行范围已过期 | **ACCEPT / CLOSED-by-plan-text** | §1.1/§1.2 改为 HEAD `b55f794` 的 3096 行基线，精确记录 197–478、579–1885、1888–1932 及后续功能域。 |
| L-01：未逐名列出 14 runner | **ACCEPT / CLOSED-by-plan-text** | Slice 7 按源码顺序逐名列出 14 runner，另单独列出 Phase C gate。 |

### 3.2 MiMo `plan-review-20260808-061002-mimo.md`

| Finding | 裁决 | 闭环文本 |
|---|---|---|
| Finding 1 / Medium：Slice 7 manual count 错误 | **ACCEPT / CLOSED-by-plan-text** | 与 S7-CTRL-01 一致；manual exact 15、execution exact 2、总迁移 exact 17。 |
| Finding 2 / Low：§1.2 仍称 12 runner | **ACCEPT / CLOSED-by-plan-text** | §1.2 已改为当前 14 runner 范围，并将 Phase C gate 独立列行，避免把 dispatch 归属混合。 |
| Finding 3 / Low：Slice 7 缺少精确函数清单 | **ACCEPT / CLOSED-by-plan-text** | Slice 7 已提供完整 14+1 清单，并分别锁定三个 `ExecutionOptions` / factory runner。 |

### 3.3 首轮 re-review

- DeepSeek `docs/reviews/plan-review-20260808-061003-deepseek.md`：**PASS**，
  open High/Medium/Low = 0/0/0，确认初审 H-01/M-01/L-01 全部 CLOSED。
- MiMo `docs/reviews/plan-review-20260808-061004-mimo.md`：核心七项均 **PASS**，
  但新增 1 个 Low：§1.3 的 HEAD 5821014 行号与 awk 若被套用到当前
  3096 行 worktree 会空匹配。Controller 裁决为 **ACCEPT / FIXED**：
  S7-CTRL-04 明确这些行号只是历史取证，历史复现改为
  `git show 5821014:<path>`，当前 HEAD `b55f794` 改用
  `run_write_command` 函数、首尾 predicate/call 锚点与 AST 结构命令。

Controller 在首轮 re-review 裁决后的 open findings 为
**High=0 / Medium=0 / Low=0**；初审 6 个 reported findings 已关闭，
re-review 新 Low 已接受且修复。该 interim gate 现已被下节最终双路
PASS 取代。

### 3.4 最终双路 re-review 与接受结论

- DeepSeek `docs/reviews/plan-review-20260808-061005-deepseek.md`：**PASS**，
  open High/Medium/Low = 0/0/0；确认 S7-CTRL-01..04 完整闭环全部
  runner-count/range/inventory findings 与 061004 新 Low。
- MiMo `docs/reviews/plan-review-20260808-061006-mimo.md`：**PASS**，
  open High/Medium/Low = 0/0/0；确认 S7-CTRL-01..04、plan 与本
  Controller artifact 自洽，061004 Low 已 CLOSED。
- Controller 最终裁决：初审 6 个 reported findings 及 061004 新 Low，
  合计 7 项全部 **CLOSED**，
  S7-CTRL-01..04 全部 **accepted**；`v5.0 ACCEPTED / DUAL PLAN
  RE-REVIEW PASS`，Slice 7 达到 code-generation-ready 并可恢复实施。

## 4. 所有权、依赖与测试契约

- `_write_execution.py` 定义 exact 2，`_write_manual_recovery.py` 定义
  exact 15；`write.py` 删除旧 exact 17 定义并正常顶层 import exact 17。
- application / verification / clearance 三个 factory call 随 runner owner 迁移；
  `_write_manual_recovery → _write_snapshot_builder → _write_config_application`
  为唯一方向，禁止 reverse import、cycle、nested/lazy helper 或 compatibility/glue seam。
- 直接调用 runner 或验证其内部依赖的 test/patch 迁到真实 owner；验证
  `run_write_command` / dispatch global lookup 的 characterization 继续 patch
  `write.<symbol>` 正常功能 binding。该 binding 是运行时真实依赖，不是
  compatibility re-export。
- 结构门禁锁定 definitions/imports/identity/factory labels/AST nested helper/import
  DAG；行为门禁覆盖相关 application + engine tests、`pyright dayu/cli/`
  0 errors、Ruff F/I + HEAD full-rule finding-code multiset 实施 delta=0、
  `_write_execution.py` / `_write_manual_recovery.py` / `write.py` 逐文件精确
  statement coverage `>=80%`、`git diff --check` 与 README 责任判定。

## 5. 拒绝的替代方案

- **留下 incident-dossier 两 runner 在 `write.py`**：拒绝。两者属于同一
  manual-recovery 功能域且都是 Phase A 真实 dispatch target，留下会破坏新
  owner 完整性。
- **推迟两 runner 到 Slice 8**：拒绝。Slice 8 仍只拥有 exact 13 Challenger
  helper + rollback，不接管 manual recovery。
- **blanket 迁移所有 `write.<symbol>` patch**：拒绝。patch owner 由被测
  call site 的 function globals 决定。
- **compatibility re-export/wrapper/lazy import 或 DI glue**：拒绝。正常顶层
  functional import 已满足 dispatch global lookup，无需新 seam。

## 6. 计划自审

- header、顶部 status 与尾注均为
  `v5.0 ACCEPTED / DUAL PLAN RE-REVIEW PASS`。
- v4.9 ACCEPTED 只作为历史状态保留，当前实施基线是 clean HEAD
  `b55f794`。
- §1.2、架构树、Slice 7、risk 与 Ready-for-Review checklist 的当前数量已
  统一为 execution exact 2 + manual exact 15 = new-owner exact 17。
- Phase A / adapter / Protocol / Slice 8 语义未改变。
- status-anchor `rg` 精确找到 header / 顶部 status / tail 三处
  v5.0 accepted 状态；manual runner 逐名清单计数为 14，
  旧“12 runner” current-state 描述为 0。
- §1.3 当前 AST 验收命令已输出
  `Phase A=14, Phase B=2; current structural anchors PASS`；历史
  `git show` 复现计数为 16，当前-file 旧 4637–4822 awk 计数为 0。
- `git diff --check`、新 artifact whitespace check 与
  `rg '[[:blank:]]+$'` 均在收尾自审通过。
- residual risk：plan gate 无 open finding；Slice 7 可按 accepted v5.0 实施，
  实施阶段仍必须独立执行测试、静态、coverage 与双路 code-review 门禁。
