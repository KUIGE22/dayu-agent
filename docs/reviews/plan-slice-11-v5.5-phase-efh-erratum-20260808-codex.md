# Slice 11 v5.5 Phase E/F/H Plan Erratum Controller 记录

- **日期**: 2026-08-08
- **基线**: `8c63d80 gateflow: accept cli write architecture slice 10`
- **分支**: `codex/dual-model-research-mvp`
- **Gate**: plan fix before Slice 11 implementation
- **接受计划**: v5.5 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **状态**: v5.5 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **Controller open H/M/L**: `0/0/0`

## 输入与直接证据

- DeepSeek focused review：`docs/reviews/plan-review-20260808-122456.md`，FAIL，
  1 High + 1 Medium + 1 Low。
- MiMo focused review：`docs/reviews/plan-review-20260808-122457.md`，FAIL，
  1 High + 2 Medium，另有 2 Low observations。
- DeepSeek final re-review：`docs/reviews/plan-review-20260808-124536.md`，PASS，
  open High/Medium/Low=`0/0/0`。
- MiMo final re-review：`docs/reviews/plan-review-20260808-124537.md`，PASS，
  open High/Medium/Low=`0/0/0`。
- Accepted predecessor：master plan v5.4 ACCEPTED / DUAL PLAN RE-REVIEW PASS。
- HEAD 真源：clean `8c63d80` 的
  `dayu/cli/commands/write.py::run_write_command`。

Controller 逐语句复核确认：Phase A/B inventory 为 exact14+2，
`_build_execution_options` 当前共有 4 个真实调用点（clear/verify/recover 各 1，
Phase A 后共享 1）；Phase E 是 inline required/build/boundary/error block，仓库生产代码
不存在 focused review 指出的 phantom helper。Phase F 保留 fail-loud assert，Phase H
保留三组异常边界与 partial-success exit 2。

DeepSeek artifact 的示例字段中出现
`routing_challenger_run_plan_approval_request/output/input`，这是 review 转录误差；HEAD
真实字段是 `routing_challenger_run_approval_request/output/input`，v5.5 按 HEAD 真名锁定，
不把错误拼写写入当前 contract。

## Controller 方案裁决

### 方案 A — bounded Phase A/B replacement + 精确保留 Phase E/F/H

- **裁决**: `ACCEPTED / CLOSED-BY-PLAN-TEXT`
- Slice 11 只替换 Phase A 的 14 个 if 与 Phase B 的 2 个 if；其余函数体以 HEAD
  为真源。
- Phase E 保留 inline 四字段 required-any、真实 builder、output-boundary assert、
  5 类异常与 return 2。
- Phase F 只把已进入 Write Protocol 的 approval selector 改为直接属性，保留
  `assert challenger_run_plan is not None`。
- Phase H 保留 plan rebuild 四异常、两个 challenger-config build 调用点的
  `ValueError` 与 materialize `Exception` partial-success；变量名保持
  `write_exit_code`。
- Phase C/D/G/H 只允许 exact20 selector 直接访问；table-out argparse 字段继续
  HEAD `getattr`，Dayu 不扩字段。

### 方案 B — 正式新建 Phase E helper

- **裁决**: `REJECTED-WITH-REASON / CLOSED`
- 新 helper 不属于 C3 Phase A/B dispatch；必须重新决定 owner、签名、错误返回与测试，
  会扩大 scope。
- HEAD inline block直接返回 2；抽成返回 plan/None 的 helper 会改变错误表达或迫使
  增加 glue result contract。
- 该方案还会引入新的类型/owner/API 设计压力，与 accepted plan 的禁止 glue、禁止
  无需求 helper 以及本次最小修复目标冲突。

## Findings 逐项裁决

### DeepSeek 3（High）— Phase E phantom helper

- **裁决**: `ACCEPTED / CLOSED-BY-PLAN-TEXT`
- §11f 已从 stale 完整函数示意改为 code-generation-ready bounded replacement；当前
  contract 只保留 HEAD inline Phase E，明确禁止新 helper。
- 新增 phantom-zero、Phase E subtree AST、required/build/boundary/5-exception 门禁。

### DeepSeek 4（Medium）— Phase F assert 被 silent guard 替代

- **裁决**: `ACCEPTED / CLOSED-BY-PLAN-TEXT`
- v5.5 锁定 direct Protocol selector + HEAD fail-loud assert；新增真实 invariant
  regression，禁止 `plan is not None and selector` 静默 guard。

### DeepSeek 5（Low）— Phase C/D“不变”措辞不精确

- **裁决**: `ACCEPTED / CLOSED-BY-PLAN-TEXT`
- 当前措辞改为“语义不变，exact20 selector 随 Protocol 改为直接属性”，区分语义
  保持与授权的访问方式变化。

### MiMo H-01 — Phase E phantom / 丢失 inline error boundary

- **裁决**: `ACCEPTED / CLOSED-BY-PLAN-TEXT`
- 与 DeepSeek 3 同源。v5.5 完整锁定 required-any、真实 builder、boundary assert、
  5 类异常、精确日志和 return 2。

### MiMo M-01 — Phase F fail-loud invariant 漂移

- **裁决**: `ACCEPTED / CLOSED-BY-PLAN-TEXT`
- 与 DeepSeek 4 同源。Controller 采纳直接属性但保留 assert；不采纳 MiMo 建议的
  blanket HEAD `getattr`，因为该 selector 已是 accepted Write Protocol 字段。

### MiMo M-02 — Phase H 三组异常处理遗漏

- **裁决**: `ACCEPTED / CLOSED-BY-PLAN-TEXT`
- v5.5 逐组锁定 plan rebuild 四异常、preflight/main 两个 challenger-config
  `ValueError` 分支及 materialize `Exception` partial-success exit 2，并新增行为测试。

### MiMo L-01 — `write_exit` 与 HEAD `write_exit_code` 不一致

- **裁决**: `ACCEPTED / CLOSED-BY-PLAN-TEXT`
- 当前 contract 明确变量名只能使用 `write_exit_code`，后续判断与返回保持一致。

### MiMo L-02 — Phase C/D/G 的访问方式边界不清

- **裁决**: `ACCEPTED / CLOSED-BY-PLAN-TEXT`
- v5.5 新增逐阶段 exact20 direct-access 表；其余 table-out 字段必须保留 HEAD
  `getattr`，禁止扩充 Dayu 或 blanket direct-access rewrite。

## v5.5 计划修改摘要

1. Header、HEAD、status、tail 统一为
   `v5.5 ACCEPTED / DUAL PLAN RE-REVIEW PASS`，基线 `8c63d80`；v5.4 accepted
   作为历史保留。
2. 审查来源追加 122456/122457 与双路终审 124536/124537；changelog 新增
   S11-CTRL-02。
3. §11f 删除会误导 implementation 的 stale 全函数示意，改为唯一 Phase A/B
   replacement、exact20 direct-access 边界、Phase E/F/H 精确保留契约。
4. 新增 16-action matrix、Phase E/F/H 错误行为、AST/顺序/调用计数、phantom-zero、
   coverage、pyright、Ruff、README 与 stop-condition 门禁。
5. Slice 11 的 Protocol exact20、Dayu exact21、contexts、adapters、phase tables 与其他
   slices 语义不变。

## 自审与验证

- master plan current header/status/tail：v5.5 accepted，一致。
- v5.4 accepted 历史：保留。
- 当前 Slice 11 contract 中 phantom helper 引用：0；生产源码定义/调用：0。
- Phase E current fenced block：四字段、builder、boundary、5 exceptions、return 2
  完整。
- Phase F：direct selector + assert；Phase H 三组异常与 `write_exit_code` 均有精确
  contract。
- code、tests、README 与两份外部 review 未修改。
- `git diff --check`、两份允许文档 trailing whitespace 与 final newline：PASS。

## 双路终审闭环

- DeepSeek `docs/reviews/plan-review-20260808-124536.md`：PASS，open
  High/Medium/Low=`0/0/0`。
- MiMo `docs/reviews/plan-review-20260808-124537.md`：PASS，open
  High/Medium/Low=`0/0/0`。
- 两路均确认 DeepSeek 122456 与 MiMo 122457 的 8/8 findings 全部 CLOSED，
  无新 finding；Controller open High/Medium/Low=`0/0/0`。
- S11-CTRL-02 已接受，Slice 11 达到 code-generation-ready，可恢复实施。

## Residual risk 与下一步

1. v5.5 已通过双路 plan re-review 并成为 accepted plan；Slice 11 可实施。
2. 实施期必须以 bounded replacement 和 HEAD AST 为双真源，只改 Phase A/B 与
   exact20 selector access；任何新的 Phase E/F/H 差异都触发 stop condition。
3. 当前 Controller open High/Medium/Low=`0/0/0`，没有 deferred 或未分类风险。
4. 未执行 `git add`、`git commit`、`git push` 或 `git stash`。
