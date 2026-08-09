# AAPL acceptance manual-review handoff — durable plan closure

- 日期：2026-08-09
- Gate：Gateflow plan acceptance closure only
- 分支：`feat/investment-agent-acceptance`
- 基线：`504d74730d9ffc099c07d7732804d51152972875`
- Target：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- 状态：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- Manual-review code correction：**PLAN HANDOFF-READY**
- Slice 4 docs：**WAITING FOR CODE CORRECTION ACCEPTANCE**
- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**

## Acceptance decision

Controller 接受 manual-review handoff plan revision。双路证据为：

1. `docs/reviews/plan-review-20260809-173027.md` — 用户明确授权的 Codex Controller plan review，**PASS-WITH-RISKS**，open High/Medium/Low = **0/0/0**。
2. `docs/reviews/plan-review-20260809-manual-review-handoff-terra.md` — 独立 Terra plan review，**PASS**，open High/Medium/Low = **0/0/0**。

MiM provider 401 导致其未参与本 gate；本 closure 不宣称、暗示或计入 MiM PASS。Codex Controller + independent Terra 是本次实际使用且可追溯的两路复核证据。

## Review / fix / closure chain

1. `docs/reviews/plan-fix-20260809-manual-review-handoff-codex.md` — Controller-adjudicated candidate fix，锁定 exact pending skeleton handoff、terminal-absent independent verify、passed-only terminal与same-plan no-resume。
2. `docs/reviews/plan-review-20260809-173027.md` — Codex Controller PASS-WITH-RISKS/open 0；确认两文件 owner足够，无material finding或blocking question。
3. `docs/reviews/plan-review-20260809-manual-review-handoff-terra.md` — independent Terra PASS/open 0；验证真实runner、evaluator、receipt loader与发布顺序事实。
4. `docs/reviews/plan-acceptance-20260809-manual-review-handoff-codex.md` — 本 durable accepted closure。

前序 Slice 2 durable closure `docs/reviews/plan-acceptance-20260809-134500-codex.md` 与 Slice 3 durable closure `docs/reviews/plan-acceptance-20260809-slice3-resume-codex.md` 保持有效，未被本 gate重写。

## Closed plan contract

- planned phases全部passed且quality review仍是evaluator builder的strict canonical exact pending skeleton时，`run` 返回canonical `PENDING_MANUAL_REVIEW`/exit 3；不派生/启动terminal Popen，不写terminal/source inventory/acceptance receipt，不把pending持久化为non-passed receipt。
- operator完整填写review后只运行独立 `verify --plan --fingerprint --json`；完整passed planned prefix允许terminal缺席，PASS/FAIL均不创建terminal receipt或修改planned receipt bytes。
- malformed/secret/PII、plan/receipt/repository/artifact drift在acceptance-owned outputs发布前fail closed；strict-valid非exact skeleton不能借handoff shortcut绕过owner path。
- persisted terminal保持passed-only；旧failed/signal/timeout/incomplete/non-passed terminal继续在evaluator前拒绝，无schema兼容或receipt cleanup路径。
- repeated same-plan `run` 继续在process factory/Popen前拒绝，不形成自动/隐式resume。

最终 open High = **0**，open Medium = **0**，open Low = **0**；无blocking open question或新plan gap。

## Accepted implementation boundary

下一步最小production correction只允许：

1. `utils/investment_agent_acceptance.py`
2. `tests/test_investment_agent_acceptance.py`

不得由本 closure推导出 contracts/evaluator/dayu/README/docs修改权限，不新增flag/action/schema/marker。实现仍须完成focused tests、类型/格式检查、双路code review与Controller adjudication；plan acceptance不是code acceptance。

Slice 4 docs继续等待该code correction accepted后再按原三文件allowlist实施。Slice 5仍须单独live authorization；本 closure不授权SEC、Web、DeepSeek、MiMo、网络、密钥读取或付费调用。

## Residual risks and destinations

- `run` 前strict-valid但非exact review仍走既有terminal strict path；code review必须验证partial pending没有被误分类。
- live verify必须在全部strict ingress、repository/artifact closure与evaluator安全检查后才发布acceptance-owned outputs；由本correction state-machine tests与code review承接。
- exact canonical bytes比较有意把仅格式化/重排的skeleton归为非exact；这是fail-closed安全取舍。
- evaluator时间字段、owner formatter drift、fixture lock、future same-plan recovery及target plan第14节其它residual destinations保持不变。
- MiM provider 401只是review availability事实，不改变已接受plan contract；不得在后续报告改写为MiM review PASS。

## Changed files and validation

- Modified：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- Modified：`docs/reviews/plan-fix-20260809-manual-review-handoff-codex.md`
- Added：`docs/reviews/plan-acceptance-20260809-manual-review-handoff-codex.md`
- Validation：scoped diff-check、untracked no-index whitespace、LF/final-newline、status/review-path/scope audit。
- 未修改 code、tests、README、source review artifacts；未运行pytest、pyright、Ruff、SEC/Web/模型/网络/付费调用；未commit/push/PR。

## Final declaration

Manual-review handoff plan状态为 **ACCEPTED / DUAL PLAN RE-REVIEW PASS**，两路实际证据为Codex Controller PASS-WITH-RISKS/open 0与independent Terra PASS/open 0。MiM provider 401未参与且未记为通过。两文件production correction plan handoff-ready；Slice 4 docs等待code correction accepted，Slice 5保持 **LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**。
