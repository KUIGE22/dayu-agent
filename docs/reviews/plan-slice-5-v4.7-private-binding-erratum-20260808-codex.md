# Slice 5 C1 v4.7 Private Binding / Lint 勘误记录

- **日期**: 2026-08-08
- **Gate**: plan fix / focused dependency-lint erratum
- **基线计划**: v4.6 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **接受计划**: v4.7 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **控制项**: S5-CTRL-04
- **状态**: v4.7 ACCEPTED / DUAL PLAN RE-REVIEW PASS

## 范围

本轮只修改 master plan 并新增本 Controller artifact。当前 Slice 5 的
production、tests 与 implementation artifact 全部冻结；未 stage、commit 或
push。本轮不改变任何运行时语义，只校正 v4.6 对 `write.py` private binding
数量及 owner 的错误计划契约。

## 输入证据

- DeepSeek focused planreview:
  `docs/reviews/plan-review-20260808-023020.md`
- MiMo focused planreview:
  `docs/reviews/plan-review-20260808-023021.md`
- DeepSeek re-review:
  `docs/reviews/plan-review-20260808-024405.md`
- MiMo re-review:
  `docs/reviews/plan-review-20260808-024406.md`
- MiMo corrective re-review:
  `docs/reviews/plan-review-20260808-025255.md`
- Master plan:
  `docs/plans/2026-08-07-cli-write-architecture-refactor.md`
- 历史 v4.6 Controller artifact:
  `docs/reviews/plan-slice-5-v4.6-dependency-erratum-20260808-codex.md`

两路 focused review 均确认：

- open High = 0；
- open Medium = 2；
- open Low = 1；
- 删除两个无生产 caller 的 compatibility re-export，并把测试 direct import
  迁到真实 owner，是唯一满足依赖最小化、禁止 compatibility code 与 Ruff
  零新增 finding 的最小方案。

## 源码事实

1. `_validate_challenger_run_plan_args` 与
   `_validate_live_smoke_plan_args` 在 `write.py` 只有 import binding，
   没有生产 caller。
2. 两者的真实生产 caller 都在 `_write_params_validation.py` 内部；保留
   `write.py` binding 只服务旧测试路径或 identity 断言，属于禁止的
   compatibility re-export。
3. 显式同名 alias 触发 `PLC0414` 两项；改为普通 import 会触发 `F401`
   两项。删除无 caller import 才能同时满足语义与 lint 门禁。
4. `write.py` 的真实功能 private binding 是 config 4 个加 params 2 个，共
   6 个：
   - `_resolve_write_model_override_name`
   - `_resolve_write_company_name`
   - `_build_write_run_config`
   - `_log_write_preflight_result`
   - `_challenger_requested`
   - `_validate_research_materialization_args`
5. `MODULE` 是独立的正常功能 import，不是 private function，不计入上述
   6 个。
6. 两个新模块的定义范围没有收缩：
   `_write_config_helpers.py` exact 4 个函数，
   `_write_params_validation.py` exact 4 个函数，合计 exact 8 个定义。

## Controller 裁决

### v4.7-F01 — ACCEPT

接受 DeepSeek 与 MiMo 关于无 caller private binding 的 Medium finding。
`write.py` 删除并禁止对以下两个符号的 compatibility re-export：

- `_validate_challenger_run_plan_args`
- `_validate_live_smoke_plan_args`

`write.py` 仅正常顶层 import/rebind 6 个有真实功能 caller 的 private
function；`MODULE` 另行正常 import。

### v4.7-F02 — ACCEPT

接受 DeepSeek 与 MiMo 关于 `PLC0414` 两项的 Medium finding。不得使用
普通 unused import、同名 alias、`__all__`、`noqa`、dummy usage、wrapper
或其他兼容 seam 绕过 lint。删除两个 dead import 后，Ruff F/I 与 HEAD
full-rule finding-code multiset 的 gate rule 保持不变；实施目标
delta = 0。

### v4.7-F03 — ACCEPT

接受 DeepSeek 与 MiMo 关于 v4.6 计划证据错误的 Low finding。Master plan
所有当前规范性 “8 个 write private import/direct path/identity” 表述均改为：

- 两个新模块各 exact 4、合计 exact 8 个定义；
- `write.py` 仅保留 6 个 functional private binding；
- dispatch identity 只锁定这 6 个 binding；
- `_validate_live_smoke_plan_args` 的 engine direct import 迁到真实 owner
  `_write_params_validation`；
- `_validate_challenger_run_plan_args` 没有旧 direct test，只保留新 owner
  模块定义。

v4.6 accepted 历史不重写；v4.7 changelog 明确记录该历史契约被真实 caller
证据收窄。

## Review 证据措辞纠正

DeepSeek review 在不变项表中把 `_write_params_validation.py` 描述为
“exact 8 个符号”，并附加了不存在于 accepted Slice 5 exact contract 的
“4 个内部 detail”。该计数措辞不作为 Controller 事实依据。

准确契约是：

- `_write_config_helpers.py` exact 4 个函数；
- `_write_params_validation.py` exact 4 个函数；
- 两个新模块合计 exact 8 个函数定义。

此纠正只记录在 Controller artifact 与 master plan；不修改外部 review
artifact。

## 精确实施契约

1. `_write_config_helpers.py` 与 `_write_params_validation.py` 各 exact 4 个
   函数、合计 exact 8 个定义，定义与函数语义均不变。
2. `write.py` 顶层：
   - 从 `_write_config_helpers` import `MODULE` 与 config 4 个函数；
   - 从 `_write_params_validation` 只 import `_challenger_requested` 与
     `_validate_research_materialization_args`；
   - 不 import/re-export 两个无 caller validator。
3. `tests/engine/test_cli_running_config.py` 对
   `_validate_live_smoke_plan_args` 的 direct import 改从
   `_write_params_validation` 获取。
4. `tests/application/test_write_cli_dispatch.py` 的 identity 断言只覆盖 6 个
   functional binding。
5. `_validate_challenger_run_plan_args` 无旧 direct test，不新建
   `write.py` 兼容路径。

## 保持不变的门禁

- 旧 `write.setup_model_name` patch 0、新
  `_write_config_helpers.setup_model_name` patch exact 13；
- `MODULE = "APP.WRITE"` 仅在 `_write_config_helpers.py` 定义；
- `_challenger_requested` 的 write run-path / params validator-path 双 owner；
- engine test 约 line 5934 的 write owner patch 保持；
- Slice 8 剩余 Challenger 组 exact 13；
- 两个新模块和修改后的 `write.py` 精确单文件 coverage 均 `>= 80%`；
- `pyright dayu/cli/` 零新增 error；
- Ruff F/I 与 HEAD 全规则 finding-code multiset delta 0；
- import/cycle smoke、相关 application/engine tests 与 `git diff --check`。

## 替代方案裁决

- `__all__`: REJECTED。不能消除根本的 compatibility re-export。
- 普通 unused import: REJECTED。产生 `F401`。
- 同名 alias: REJECTED。产生 `PLC0414`。
- `noqa` 或 dummy usage: REJECTED。掩盖 dead binding，不修复 owner。
- 保留旧 direct import/identity: REJECTED。测试必须跟随真实模块边界。
- 扩大迁移范围或改变 validator 语义: REJECTED。本勘误只校正 private
  binding，不改变 Slice 5 其余实施契约。

## Master plan 更新

- header、状态与底部状态统一为
  `v4.7 ACCEPTED / DUAL PLAN RE-REVIEW PASS`；
- 保留 v4.6 ACCEPTED / DUAL PLAN RE-REVIEW PASS 历史；
- 审查来源追加两份 focused review；
- changelog 新增 S5-CTRL-04；
- 更新 monkeypatch 契约、Slice 5 exact scope、验证命令与
  Ready-for-Review item；
- setup exact 13、MODULE 单一真源、双 owner、line 5934、Slice 8 exact 13
  与 coverage/pyright/Ruff 门禁零语义变化。

## 双路 re-review observations 与 Controller 裁决

输入：

- DeepSeek `docs/reviews/plan-review-20260808-024405.md`: PASS，open
  High/Medium/Low = 0。该 review 完整读取 master plan、前序 DeepSeek
  review 与 Controller artifact，并通过本地检索确认当前规范性
  stale 8-write-binding 表述为 0。
- MiMo `docs/reviews/plan-review-20260808-024406.md`: PASS，新增 3 个 Low
  observations；该 review 明确说明因会话信息限制未直接读取 master plan，
  且未交叉读取前序 DeepSeek review。

逐项裁决：

- **MiMo v4.7r2-F01 — REJECT / CLOSED**。该 finding 的依据是 reviewer
  未直接读取 master plan，而不是 plan 缺陷。DeepSeek 024405 已完整读取并
  逐处核对，本地 `rg` 也确认当前规范性 stale 8-write-binding 表述为 0。
  Plan 中保留的“8 个迁移定义”精确指两个新模块 4 + 4 个函数定义，不是
  `write.py` binding 数；与 6 个 functional binding 不矛盾。
- **MiMo v4.7r2-F02 — REJECT / CLOSED**。这是 reviewer 输入信息限制，
  不是 plan defect。DeepSeek 024405 已完整读取前序 DeepSeek review
  023020，并核对 Controller 对其 `_write_params_validation.py` 计数误述的
  纠正；无需修改外部 review 或扩大 plan。
- **MiMo v4.7r2-F03 — ACCEPT / TEXT CLARIFIED**。原门禁句可能被误读为
  当前 delta 值不变。Controller 已精确改为：
  “Ruff F/I 与 HEAD full-rule finding-code multiset 的 gate rule 保持不变；
  实施目标 delta = 0。”该澄清不改变 master plan 的既有门禁或实施语义。

Controller 裁决后的 open High/Medium/Low = 0；本阶段保留三项裁决证据，
最终状态由下述 MiMo corrective re-review 闭环。

## Final 双路 plan re-review 结论

- DeepSeek `docs/reviews/plan-review-20260808-024405.md`: PASS，open
  High/Medium/Low = 0。
- MiMo `docs/reviews/plan-review-20260808-024406.md`: PASS，提出 3 个 Low
  observations；Controller 已逐项裁决。
- MiMo corrective
  `docs/reviews/plan-review-20260808-025255.md`: PASS，前序
  v4.7r2-F01/F02/F03 全部 CLOSED，无新增 finding，open
  High/Medium/Low = 0。
- 初审 v4.7-F01/F02/F03 与 MiMo re-review
  v4.7r2-F01/F02/F03 合计 6 项全部 CLOSED。
- 两个新模块 exact 4 + 4 definitions、`write.py` exact 6 functional
  private bindings、MODULE 单独正常 import、两个 compatibility re-export
  为 0 的契约完成双路闭环。

## Residual risk

Plan gate 无未关闭 High/Medium/Low finding。v4.7 已达到
code-generation-ready 标准，Slice 5 可按 accepted S5-CTRL-01..04 契约恢复
实施；production/tests/implementation artifact 的既有冻结状态仅在实施恢复
后按 accepted plan 解冻。
