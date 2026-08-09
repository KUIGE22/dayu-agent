# Slice 0 AAPL Acceptance Code Review Fix

- Work unit：`investment-agent-aapl-acceptance`
- Slice：`0 — Characterization 与固定 contract`
- Baseline accepted plan commit：`5b5494e`
- Source reviews：
  - `docs/reviews/code-review-20260809-075007.md`
  - `docs/reviews/code-review-20260809-075509.md`
- Fix worker：Codex
- Status：**CLOSED / DUAL RE-REVIEW PASS**

## Scope Guard

本次只修改：

1. `tests/test_investment_agent_acceptance.py`
2. `docs/reviews/slice-0-aapl-acceptance-implementation-20260809-074642-codex.md` 的 status、validation 与 adjudication 记录
3. 本 fix artifact

7 个 fixture 与全部生产文件均保持不变。没有发现 fixture/production 的直接矛盾，没有触发 STOP；没有进入 Slice 1+，没有运行 SEC、Web、DeepSeek、MiMo 或其它 live/付费调用。

## Finding Adjudication and Fix Map

| Finding | Controller 裁决 | 本次处理 | Closure evidence |
|---|---|---|---|
| DS-001 run-summary owner↔fixture shape | **ACCEPT** | **FIXED** | 真实 `ExecutionSummaryBuilder` 输出与 `run-summary-v1.json` 逐层闭合顶层、`audit`、首个 `chapters` 元素、默认 `model_routing`、`model_roles` 及 role scene 字段集合。 |
| DS-002 hard gates / minima / report contract / item sums | **ACCEPT** | **FIXED** | 精确锁定 10 个 hard gate 名及顺序、5 个维度下限（含两个有意为 0 的维度）、5 个 required topic、4 个 evidence part；逐维验证 item score/max 求和、dimension minimum、总分 85/100；report headings 从 contract topics 映射，引用段数从 contract evidence parts 长度取得。 |
| DS-003 monitoring 负向断言归因 | **ACCEPT（仅 assertion-specificity）** | **FIXED** | 正向 plan 必须 `ok=true` 且 `errors=[]`；automation/live 反例必须分别包含精确错误 `automated_execution_allowed must be false` / `execution_mode must be dry_run`。 |
| DS-004 citation 日期/accession 闭合 | **ACCEPT** | **FIXED** | 每条正文与来源清单 citation date 均解析并验证 `<= inventory.as_of`；filing 的 `form / accession` 精确等于对应 inventory document，且 `latest_discovery` 与唯一 matching filing accession 闭合。 |
| DS-005 canonical 序列化不锁磁盘布局 | **REJECT（非缺陷）** | **NO CHANGE** | canonical 语义稳定与 Markdown byte stability 职责不同且是有意设计；不增加第二套 JSON 磁盘布局哈希。 |
| DS-006 测试文件覆盖率不是生产覆盖 | **REJECT（非缺陷）+ 文档澄清** | **CLARIFIED** | Slice 0 没有新增/修改生产 Python；实施 artifact 已明确 100% 只表示测试模块自身执行路径证据，不能当生产覆盖率证据。 |
| MiMo-1 dimension minima dead data | **ACCEPT，DS-002 duplicate** | **FIXED BY DS-002** | 精确 minima 映射、维度 key 闭合、逐维 `score >= minimum` 均已断言；两个 0 明确为“不设独立 hard minimum”。 |
| MiMo-2 RunManifest owner 接受范围被高估 | **REJECT（非缺陷）** | **NO CHANGE** | `RunManifest.from_dict` 接受当前 fixture 的陈述准确；独立 exact-shape 测试守护顶层闭包。signature/company_facets 不属于本次已接受 Slice 0 contract，不扩 scope。 |
| MiMo-3 monitoring fingerprint/bound-source tamper | **REJECT AS SLICE 0 DEFECT / DEFER TO SLICE 1** | **NO SLICE 0 BEHAVIOR EXPANSION** | Slice 0 只刻画 owner 生成的 dry-run/automation false 及精确拒绝原因；指纹漂移、bound-source tamper 与其它 strict failure classification 由 Slice 1 evaluator 测试负责。 |

## Open-question Decisions

- `tests/README.md`：**DEFERRED WITH OWNER = Slice 4**。accepted plan 的 Slice 0 精确白名单不含 README，不越权修改。
- Hard gate 名单：`contract-v1.json` 是 Slice 1 必须解析的 contract truth，不在 evaluator 另立 enum。测试模块中的 `_EXPECTED_HARD_GATES` 只用于锁定已接受 fixture 语义，代码注释明确禁止复制成第二套生产真源。
- `PENDING_MANUAL_REVIEW` / `FAIL` 质量状态：**DEFERRED WITH OWNER = Slice 1**。
- price snapshot `max_age_days` evaluator：**DEFERRED WITH OWNER = Slice 1**；Slice 0 只明确不声明 live freshness。

## Code Changes

`tests/test_investment_agent_acceptance.py` 新增或增强以下确定性断言：

- 精确 contract 常量及其与 fixture 的交叉闭合；
- quality dimension/item 两层 score 与 max-score 聚合；
- contract dimension minima（包括 intentional zero）执行；
- report topic heading 与 citation 四段数量由 contract 字段驱动；
- citation date/as-of 与 filing form/accession/latest-discovery 闭合；
- monitoring validator 正向无错误及两个安全开关的精确错误归因；
- production run-summary 与 fixture 的关键 shape closure。

所有新增/修改函数继续具有完整中文 Args、Returns、Raises docstring；本次未新增函数。

## Validation

在 `/Users/wsk/workspace/dayu-agent` 激活 `.venv` 后：

1. `python -m pytest tests/test_investment_agent_acceptance.py -q`
   - Exit：`0`
   - Result：`7 passed`
2. `pyright tests/test_investment_agent_acceptance.py`
   - Exit：`0`
   - Result：`0 errors, 0 warnings, 0 informations`
3. `ruff check --select F,I tests/test_investment_agent_acceptance.py`
   - Exit：`0`
   - Result：`All checks passed!`
4. `ruff check tests/test_investment_agent_acceptance.py`
   - Exit：`0`
   - Result：`All checks passed!`
5. `python -m pytest tests/test_investment_agent_acceptance.py -q --cov=tests.test_investment_agent_acceptance --cov-report=term-missing --cov-fail-under=100`
   - Exit：`0`
   - Result：`7 passed`；测试模块自身 `327 statements / 0 missed / 100%`。这是非生产测试执行路径证据，不是生产覆盖证据。
6. `git diff --check`，并对全部未跟踪文件逐项执行等价的 `git diff --no-index --check /dev/null <exact-file>`
   - Exit：`0`
   - Result：无 whitespace error。
7. exact allowed-path audit：合并 tracked diff 与 untracked 文件后排序去重，逐项匹配既有 Slice 0 白名单、2 个 source-review baseline 与本 fix artifact
   - Exit：`0`
   - Result：`OVERALL_ALLOWED_PATH_AUDIT PASS (12 paths; 2 source-review baseline + 10 Slice0 deliverables)`；本次 fix 实际编辑范围严格为测试、本实施 artifact 和本 fix artifact，fixture/production 零改动。

## Residual Risks

- Re-review 新 Low 001（`run_summary.budget` / `model_usage` nested shape 尚未绑定真实 `WriteModelUsageLedger`）为 `DEFERRED-WITH-OWNER = Slice 1`。目标落点是 `utils/investment_agent_acceptance_contracts.py` 严格解析和 `utils/investment_agent_acceptance_evaluator.py` budget/usage hard gates；Slice 1 在 `tests/test_investment_agent_acceptance.py` 通过真实 `WriteModelUsageLedger.build_summary()` / `build_budget_summary()` receipt 绑定 fixture nested shape，验证入口为 `python -m pytest tests/test_investment_agent_acceptance.py -q`。
- Slice 0 仍不实现 strict evaluator、`PENDING_MANUAL_REVIEW`/`FAIL` 状态、price max-age、monitoring 指纹或 bound-source tamper 分类；这些均按 accepted plan 和 Controller 裁决留给 Slice 1。
- `tests/README.md` 同步为 `DEFERRED-WITH-OWNER = Slice 4`，由 Slice 4 docs gate 验收。
- fixture 不证明 live freshness、外部服务可用性或模型语义质量。
- pytest 仍输出既有 `RequestsDependencyWarning`；与本 slice 断言无关，依赖修整不在白名单。

## Dual Re-review Closure

1. `docs/reviews/code-review-20260809-080255.md`
   - Verdict：**PASS**
   - DS-001..004 修复全部经 mutation probe 复核关闭。
   - 新 Low 001：Controller 裁决 `DEFERRED-WITH-OWNER = Slice 1`；owner/destination/validation entry point 已在上方 Residual Risks 精确记录。
2. `docs/reviews/code-review-20260809-080616.md`
   - Verdict：**PASS**
   - Open High/Medium/Low：`0/0/0`

Closure mapping：所有本 slice accepted findings 均 **CLOSED**；DS-005、DS-006、MiMo-2 的 rejection 保持成立；monitoring tamper、PENDING/FAIL、max-age 与新 budget/usage owner-binding 进入 Slice 1；`tests/README.md` 进入 Slice 4。Slice 0 已达 **DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**。

## Stop Status

- Plan gap：无。
- Fixture changes：无。
- Production changes：无。
- Live calls：无。
- Final fix status：**CLOSED / DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**。
