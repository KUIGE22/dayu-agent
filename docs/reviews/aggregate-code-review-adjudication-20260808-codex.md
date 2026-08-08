# Aggregate Deepreview Controller 裁决记录

- **日期**: 2026-08-08
- **分支**: `codex/dual-model-research-mvp`
- **当前 HEAD**: `4d2535d gateflow: accept cli write architecture plan v5.7`
- **PR base**: `origin/main=2115c86`
- **CLI architecture baseline**: `5821014`
- **Gate**: aggregate deepreview finding adjudication → plan fix
- **状态**: v5.8 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **Controller accepted material finding**: exact 1（RT-01）
- **Controller aggregate code-finding open High/Medium/Low**: `0/1/0`（RT-01 等待 implementation 与 aggregate re-review；未因 plan accepted 而关闭）
- **Controller plan-review open High/Medium/Low**: `0/0/0`（全部 plan findings CLOSED）

## 输入 artifact

- Aggregate validation：
  `docs/reviews/aggregate-cli-write-architecture-validation-20260808-codex.md`。
- DeepSeek aggregate deepreview：
  `docs/reviews/code-review-20260808-aggregate-deepseek.md`。
- MiMo aggregate deepreview：
  `docs/reviews/code-review-20260808-aggregate-mimo.md`。
- Accepted plan：
  `docs/plans/2026-08-07-cli-write-architecture-refactor.md` v5.7
  ACCEPTED / DUAL PLAN RE-REVIEW PASS。
- 本次 plan fix：
  `docs/reviews/plan-v5.8-aggregate-rt-exit-erratum-20260808-codex.md`。
- DeepSeek v5.8 plan review：
  `docs/reviews/plan-review-20260808-v5.8-aggregate-rt-deepseek.md`，PASS，open
  High/Medium/Low=`0/0/1`，L-PLAN-01。
- MiMo v5.8 plan review：
  `docs/reviews/plan-review-20260808-v5.8-aggregate-rt-mimo.md`，PASS，open
  High/Medium/Low=`0/0/0`。
- DeepSeek v5.8 final corrective plan re-review：
  `docs/reviews/plan-review-20260808-v5.8-aggregate-rt-final-deepseek.md`，PASS，
  L-PLAN-01 CLOSED，open High/Medium/Low=`0/0/0`。
- MiMo v5.8 final plan re-review：
  `docs/reviews/plan-review-20260808-v5.8-aggregate-rt-final-mimo.md`，PASS，open
  High/Medium/Low=`0/0/0`。

## Controller 总结

双路 review 共同指出 `_run_validate_source_map` 在业务校验结果 `ok=false` 时仍固定返回
`0`。源码、引入提交与测试证明这是相对 `origin/main` 的真实 PR correctness defect；但该
行为早于 architecture baseline，Slice 9/10 又以 exact AST/behavior-preservation 明确保留，
因此必须先用 v5.8 plan erratum 建立唯一有界例外，再进入 Aggregate Fix RT-01。

除 RT-01 外没有 accepted finding。Write label、research owner、lexical path、assert 与其余
观察均是 accepted design、pre-existing-to-work-unit、事实错误、不可复现的假设性风险或
维护建议；不能借 aggregate fix 扩大成跨模块重构。production、tests、README、CI 与外部
review 在本次 adjudication/plan-fix gate 保持冻结。

## ACCEPTED：RT-01（DeepSeek RT-01 / MiMo MIMO-RT-01）

- **裁决**: `accepted / PLAN ACCEPTED / IMPLEMENTATION REQUIRED`
- **严重度**: Medium
- **源码证据**:
  - `dayu/cli/commands/research_template.py::_run_validate_source_map` 调用
    `validate_monitoring_source_map_payload`，打印完整 JSON 后固定 `return 0`。
  - validator 会对模板不一致、缺少数据源等语法有效但业务无效的 payload 返回
    `{"ok": False, "errors": [...]}`，不会抛出异常。
  - `tests/cli/test_research_template_command.py` 已覆盖 validator 的 valid/invalid 结果，
    但缺少真实 CLI invalid exit-code 回归。
- **Git 证据**: 行为由 `7579e0d` 引入；该提交不是 `origin/main=2115c86` 的祖先，却是
  architecture baseline `5821014` 的祖先。Slice 9 commit `8eface5` 与 Slice 10 accepted
  behavior contract 忠实保留该行为。
- **影响**: shell、CI 或调度器仅看退出码时会把失败的 source-map 一致性校验误判为成功。
- **处理**: v5.8 `AGG-RT-CTRL-01` 只授权
  `return 0 if result.get("ok") is True else 1`、准确 Returns docstring 与真实 CLI
  valid/invalid 回归；stdout、异常、dispatch、owner/DAG 及其他 runner 不变。

## Write findings

### WRITE-01 / MIMO-WRITE-01 与 WRITE-05

- **裁决**: `rejected-with-reason / CLOSED (ACCEPTED-DESIGN)`
- v4.9 S6-W12-CYCLE-01 与 v5.0 S7-CTRL-02 精确锁定 application/rollback 使用
  snapshot factory 默认 `run_label="configuration-application"`，verification/clearance
  才使用各自专属 label；迁移前 nested closures 同样未显式传 label。
- 默认 label 描述底层 configuration-application snapshot/preflight 域，而非外层 action。
  修改 manual/rollback label 会违反 accepted contract，不能作为 RT-01 附带修复。

### WRITE-02

- **裁决**: `rejected-with-reason / CLOSED (PRE-EXISTING / NON-DEFECT)`
- `assert rollback_approval_output is not None` 位于 request/output 配对 validator 之后，
  是私有执行路径的已验证不变量和类型收窄；input pairing 与真实执行路径已有测试。
- 该语句来自迁移前实现，review 没有提供通过 public CLI 绕过 validator 的复现。

### WRITE-04 / MIMO-WRITE-04

- **裁决**: `rejected-with-reason / CLOSED (PRE-EXISTING / HYPOTHETICAL)`
- `_build_auto_bootstrap_args` 的浅拷贝由 `7579e0d` 引入并在 Slice 8 exact 迁移；当前保留
  字段为标量，review 没有共享可变对象被后续修改的真实 caller 证据。
- 改用 `deepcopy` 会改变对象身份和存量行为，不属于 Aggregate Fix RT-01。

## Research Template 其余 findings

| Finding | 裁决 | 直接理由 |
|---|---|---|
| DeepSeek RT-02 / MiMo MIMO-RT-02 | `rejected-with-reason / CLOSED` | 所谓“三处相同”不成立：definitions loader 具有领域化 JSON 异常包装；其余实现早于 Slice 9，统一会改变错误契约或引入新的 owner 依赖。属于维护建议，不是 current correctness defect。 |
| DeepSeek RT-03 | `rejected-with-reason / CLOSED` | 私有模板常量按 owner 本地持有是 v5.1 accepted DAG 的结果；强行单一真源会增加跨 owner 依赖。 |
| DeepSeek RT-04 | `rejected-with-reason / CLOSED (EVIDENCE INVALID)` | v5.1 明确从主模块 `__all__` 删除 `materialize_research_bundle_from_write_manifest`，真实 owner 是 `_research_template_materialize.py`；缺少 main re-export 是计划目标，不是遗漏。 |
| DeepSeek RT-05 | `rejected-with-reason / CLOSED` | 四处 assert 是结构检查后的私有不变量，来自 `7579e0d` 并由 Slice 9 exact AST 迁移；没有 `-O` 下 public invalid-input 行为差异复现。 |
| DeepSeek RT-06 | `rejected-with-reason / CLOSED` | 两处标准化逻辑属于迁移前不同 owner；review 只提出可能漂移，没有当前差异或失败 corpus。 |

## Engine findings

- **ENG-01 / MIMO-ENG-01**：`rejected-with-reason / CLOSED`。SQLite store 已配置 WAL、
  `timeout=5` 与 `busy_timeout=5000` 并 fail-loud 传播事务错误；review 自认只在极端并发
  下理论触发，没有可复现 crash。应用层重试是独立可靠性设计，不是 Aggregate Fix。
- **ENG-02**：`rejected-with-reason / CLOSED (INTENTIONAL)`。HALF_OPEN 唯一 probe 被
  abandoned 时重新打开 circuit 是释放 in-flight probe 的 fail-safe 语义，已有明确测试。
- **ENG-03/04/05/06/08/09**：`rejected-with-reason / CLOSED`。session 生命周期、event-loop
  关闭、畸形 SSE、auth fingerprint 集、retry race 与 message 聚合均未提供失败复现；相关
  engine/host 文件在 architecture baseline 后没有本 work unit delta，属于假设性增强或
  既有独立 work unit 风险。
- **ENG-10**：`rejected-with-reason / CLOSED (INTENTIONAL)`。负 usage counter 归零是已有
  单元测试锁定的输入净化行为。
- **ENG-07**：DeepSeek artifact 没有该 ID 的 finding body，不能从 `ENG-02~ENG-10`
  范围文字推导一个未提交 finding，按 `NO SUBMITTED FINDING` 关闭。

## Security / storage findings

- **DeepSeek SEC-01**：`rejected-with-reason / CLOSED`。embedded NUL 会由 Path/open 边界
  拒绝；review 没有 traversal/bypass 复现，且该 Fins helper 不属于本 CLI work unit delta。
- **DeepSeek SEC-02 / MiMo MIMO-SEC-01**：
  `rejected-with-reason / CLOSED (ACCEPTED-DESIGN)`。`is_subpath` 使用
  `Path.relative_to`，不是字符串前缀；v4.1 SA-02 明确要求 lexical、non-resolve 语义，
  并有 symlink characterization。调用方负责各自 resolve/absolute 边界。
- **DeepSeek SEC-05**：`rejected-with-reason / CLOSED (PRE-EXISTING / OUT-OF-SCOPE)`。
  非原子 sources/report 写入早于本 architecture work unit；review 没有本轮数据损坏复现。
- **SEC-03/04**：没有 finding body，按 `NO SUBMITTED FINDING` 关闭。

## Gate / utils findings

- **GATE-01/02/04/08/09**：全部
  `rejected-with-reason / CLOSED (PRE-EXISTING-TO-WORK-UNIT / NON-MATERIAL)`。
  对 baseline overlap、灾难性 cwd 消失、pyright stderr、重复 scope normalization 与
  handoff path 双重校验的描述均没有当前失败复现；相关 utils 在 architecture baseline 后
  无本 work unit delta，699 focused tests 与三个 JSON machine gates 全部通过。
- GATE-09 的第二次 path resolution 是写入前重新验证，而不是 review 所称的单纯放大窗口；
  改为一次解析反而会削弱当前防护。
- **GATE-03/05/06/07/10/11**：DeepSeek artifact 没有 finding body，不能从
  `GATE-01~GATE-11` 范围文字补造 findings，按 `NO SUBMITTED FINDING` 关闭。

## Review 计数与 Ruff measurement 纠正

### DeepSeek finding 计数自相矛盾

DeepSeek summary 声称 `5 Medium / 11 Low`，但 Finding Summary 表实际逐项列出
`5 Medium / 22 Low`：Write Low 2、Engine Low 8、Security Low 3、Research Low 4、
Gate Low 5。`ENG-07`、`SEC-03/04`、`GATE-03/05/06/07/10/11` 又没有 finding body。
Controller 只裁决有正文证据的 exact IDs，不接受范围缩写生成的幽灵 findings。

### MiMo Ruff `183/12` 是 measurement error

v5.7 固定 Ruff `0.16.1`、固定 scope、固定 archive/Counter 算法的权威复测为：

- architecture baseline `5821014`：HEAD=`335`、BASE=`364`、positive=`0`、
  negative=`29`（`I001:11 / TRY004:17 / UP035:1`）；
- `origin/main=2115c86`：HEAD=`335`、BASE=`143`、positive=`216`，exact 10 codes：
  `B009:53`、`BLE001:3`、`FURB162:12`、`ISC004:1`、`RUF010:22`、`RUF022:2`、
  `SIM102:1`、`TRY004:118`、`UP012:2`、`UP035:2`。

MiMo 表只列出这 10 个 positive codes，其数值合计也是 216，却报告 BASE=154、
positive=183/12；因此 `183/12` 裁决为 `REJECTED / CLOSED (MEASUREMENT ERROR)`。
DeepSeek Ruff 段也混用了 HEAD finding totals 与 positive delta；只保留其“PR residual 必须
进入 aggregate deepreview”的定性结论，计量一律以权威 `216/10` 为准。

## Gate 状态与下一步

- accepted material issue：RT-01 exact1；由两路不同 ID 指向同一根因。
- 其余有正文 findings 全部 rejected-with-reason/CLOSED；缺少正文的范围 ID 不计 finding。
- DeepSeek L-PLAN-01：`accepted / FIXED`。invalid CLI regression 已精确锁定
  `write_monitoring_rules_payload("financial", workspace_root=tmp_path)` +
  `write_monitoring_source_map_payload("consumer", workspace_root=tmp_path)` 的 template
  mismatch；valid 回归锁定 consumer/consumer。两者都必须经真实
  `run_research_template_command`，禁止手写 payload 或另选不一致模式。
- DeepSeek final corrective 与 MiMo final plan re-review 均 PASS/open0；L-PLAN-01 CLOSED，
  全部 plan findings CLOSED，Controller plan-review open High/Medium/Low=`0/0/0`。
- v5.8 已 accepted，下一步进入 Aggregate Fix RT-01 implementation → 双路 aggregate re-review；
  通过后才可创建 accepted deepreview commit。
- RT-01 是尚未修复的 aggregate code finding，Controller aggregate code-finding open
  High/Medium/Low 仍为 `0/1/0`；plan-review PASS 只代表实现契约已接受，不代表 code
  finding 已关闭。
- 未执行 `git add`、`git commit`、`git push` 或 `git stash`。
