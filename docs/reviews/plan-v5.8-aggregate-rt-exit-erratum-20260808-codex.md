# CLI Write Master Plan v5.8 Aggregate Fix RT-01 勘误记录

- **日期**: 2026-08-08
- **分支**: `codex/dual-model-research-mvp`
- **基线**: `4d2535d gateflow: accept cli write architecture plan v5.7`
- **Accepted plan**: `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v5.8
- **Gate**: aggregate deepreview → plan fix
- **状态**: v5.8 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **唯一 Controller ID**: `AGG-RT-CTRL-01`

## 背景与直接证据

Aggregate 双路 deepreview 均发现 `_run_validate_source_map` 在 validator 返回
`{"ok": false, "errors": [...]}` 时仍固定返回 `0`。这会使 shell/CI/调度器把业务校验
失败误判为成功。

Git 审计证明该行为由 `7579e0d` 引入，不在 `origin/main=2115c86`，但已存在于
architecture baseline `5821014`。因此 Slice 9 stripped-docstring AST exact migration 与
Slice 10 behavior-preservation 没有制造回归，却把一个真实 PR defect 纳入了 accepted
behavior。修复必须先形成计划中的有界例外，不能让 implementation agent自行突破 exact
contract。

编号使用 `AGG-RT-CTRL-01`，而不是 handoff 中的通用 `AGG-CTRL-01`：master plan v5.6
已占用 `AGG-CTRL-01..03`，复用会破坏 Controller decision traceability；该去歧义经
Controller 确认，不改变任何实现语义。

## 方案比较与 Controller 决策

### 方案 A：保留固定返回 0

- **裁决**: REJECTED。
- 与 stdout `ok=false` 自相矛盾，不能满足 CLI automation 的退出码契约。

### 方案 B：校验失败抛出 `ValueError`

- **裁决**: REJECTED。
- 会把既有 JSON stdout 改成 entry 层 stderr `research-template error: ...`，同时改变异常
  边界和输出 schema，扩大行为差异。

### 方案 C：只按既有 result 决定 0/1

- **裁决**: ACCEPTED。
- 精确实现为 `return 0 if result.get("ok") is True else 1`。既有 rules/source-map 加载、
  validator 调用、JSON stdout、dispatch、owner、DAG 与异常传播全部保持；只有业务失败
  退出码从 0 变为 1。

### 方案 D：抽取通用 validate runner / 新增 Slice 14 / 顺手处理其他 deepreview 观察

- **裁决**: REJECTED。
- 违反最小 fix、accepted ownership 与 zero-glue 边界；WRITE label、Ruff residual、Engine、
  Security、Gate 观察均不是本次 accepted finding。

## v5.8 计划修改

1. Header、状态与 tail 更新为
   `v5.8 ACCEPTED / DUAL PLAN RE-REVIEW PASS`，
   baseline 保持 `4d2535d`；
   v5.7 ACCEPTED 历史保留。
2. 新增 `AGG-RT-CTRL-01`：
   - 只允许修改 `dayu/cli/commands/research_template.py` 与
     `tests/cli/test_research_template_command.py`；
   - 固定 return 改为 `0 if result.get("ok") is True else 1`；
   - docstring 精确写成功 0、校验失败 1；
   - invalid 回归精确用 `write_monitoring_rules_payload("financial", workspace_root=tmp_path)`
     与 `write_monitoring_source_map_payload("consumer", workspace_root=tmp_path)` 构造
     template mismatch，经真实 entry 断言退出 1、stdout `ok is False`、errors 非空；
   - valid 回归精确用 consumer rules + consumer source-map，经真实 entry 保持退出 0、
     stdout `ok is True`；不得手写 payload 或改用其他 inconsistency；
   - stdout、异常、dispatch、其他 runner、owner/DAG 不变。
3. 明确该项是 Slice 9/10 exact-behavior 的唯一例外；不修改 manual recovery application
   或 rollback 的默认 `run_label="configuration-application"`，不新增 Slice 14。
4. README decision：现有 README 只说明 `validate-source-map` 用于一致性校验，没有声明
   失败退出码，保持不变。

## 验证与 review gate

Aggregate Fix implementation 必须完成：

- `tests/cli/test_research_template_command.py -k "validate_source_map"`；
- aggregate behavior suite：write dispatch + research template + write service；
- `ci_pr_pyright` 无 PR 新增诊断；
- v5.7 固定 Ruff `0.16.1`/`5821014`/scope/Counter architecture ratchet positive=`{}`；
- production/tests 字节变化后真实重跑 Python 3.11 min-compat full suite，不复用此前
  `7121` 的 Git-object identity 证据；
- dual-model focused 699 与三个 JSON machine gates；
- `git diff --check`、secret/temp/conflict/status hygiene；
- 修后 DeepSeek + MiMo aggregate deepreview/re-review，RT-01 CLOSED 且 Controller
  open High/Medium/Low=`0/0/0`。

权威 origin/main Ruff residual 仍为 positive=`216` / exact10 codes，并继续作为 mandatory
PR-level residual；MiMo `183/12` 为 measurement error，不改变 hard gate 或本修复范围。

## 文件范围与非目标

本次 plan-fix 只修改：

- `docs/plans/2026-08-07-cli-write-architecture-refactor.md`；
- `docs/reviews/aggregate-code-review-adjudication-20260808-codex.md`；
- `docs/reviews/plan-v5.8-aggregate-rt-exit-erratum-20260808-codex.md`。

production、tests、README、CI workflow 与外部 review artifacts 均冻结。未启动
implementation、aggregate re-review、accepted commit 或 draft PR gate。

## Plan review observation 裁决

- DeepSeek：`docs/reviews/plan-review-20260808-v5.8-aggregate-rt-deepseek.md`，PASS，
  open High/Medium/Low=`0/0/1`。
- MiMo：`docs/reviews/plan-review-20260808-v5.8-aggregate-rt-mimo.md`，PASS，
  open High/Medium/Low=`0/0/0`。
- DeepSeek final corrective：
  `docs/reviews/plan-review-20260808-v5.8-aggregate-rt-final-deepseek.md`，PASS，
  L-PLAN-01 CLOSED，open High/Medium/Low=`0/0/0`。
- MiMo final：`docs/reviews/plan-review-20260808-v5.8-aggregate-rt-final-mimo.md`，PASS，
  open High/Medium/Low=`0/0/0`。
- **L-PLAN-01**：`accepted / FIXED`。原“语法有效但业务不一致”虽然可实施，但仍允许
  implementation agent 手写 JSON 或自行选择 failure mode。计划现已锁定既有最小模式：
  financial rules + consumer source-map 产生 template mismatch，consumer/consumer 作为
  valid 对称路径；两者均经真实 CLI entry。没有扩大文件、行为或验证 scope。
- DeepSeek final 与 MiMo final 均确认该 observation CLOSED、无新 finding；Controller
  plan-review open High/Medium/Low=`0/0/0`，v5.8 accepted。

## Residual 与下一步

- 唯一 accepted material finding：RT-01，owner 为 Aggregate Fix RT-01。
- 当前无 blocking open design question；plan review gate 已闭合。
- architecture Ruff hard gate positive=`0`；origin/main positive=`216/10` 继续由 aggregate
  deepreview residual 追踪，不在本 fix 机械清理。
- 下一步：创建 accepted plan checkpoint 后实施 Aggregate Fix RT-01；RT-01 code finding
  在 implementation 与双路 aggregate re-review 前仍为 open Medium exact1，不能因 plan
  accepted 提前关闭。
- 未执行 `git add`、`git commit`、`git push` 或 `git stash`。
