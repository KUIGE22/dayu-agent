# Manual-review handoff plan review（Terra）

- 审查日期：2026-08-09
- 当前 gate：manual-review handoff plan review
- 审查角色：Gateflow-governed 独立 Terra plan reviewer（非 controller）
- 结论：**PASS**
- Open：High / Medium / Low = **0 / 0 / 0**

## Reviewed target and scope

- Reviewed target：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md` 当前未提交 manual-review handoff revision。
- Source fix：`docs/reviews/plan-fix-20260809-manual-review-handoff-codex.md`。
- 已读取的直接事实：根 `AGENTS.md`、目标计划、source fix、`utils/investment_agent_acceptance.py`、`utils/investment_agent_acceptance_contracts.py`、`utils/investment_agent_acceptance_evaluator.py` 及 `tests/test_investment_agent_acceptance.py` 中相关 runner / verify / receipt / evaluator 测试。
- 审查边界：仅审查 planned phases 到人工 quality review 的 handoff state machine。未实施、未运行 live、未修改计划/生产/tests/README，也未进入下一 gate。

## Assumptions tested

1. **动机成立且根因同源。** 当前 `run_acceptance()` 在全部 planned phases passed 后无条件构造 terminal argv 并调用 `_execute_terminal_verify()`（CLI 第 1702–1714 行）；terminal subprocess 的 exit 3 会被写成 non-passed `verify.json`。而 strict loader 对 persisted terminal 要求 `passed`、精确一条 record、exit 0（第 3841–3899 行）。这与 source fix 第 12–23 行的根因陈述一致，属于真实 blocker，而非风险放大。
2. **exact pending skeleton 只有 evaluator 真源。** `build_pending_quality_review()` 生成唯一 null rubric skeleton 并调用 strict parser 自检（evaluator 第 568–615 行）；计划第 118 行及 Slice 4 第 442–445 行要求 CLI 对同一 `live-{fingerprint[:16]}` builder 结果做 strict round-trip + canonical bytes 比较。它没有复制 rubric、阈值或第二 builder。
3. **handoff 的时序可在冻结 owner 内完成。** 计划要求在 terminal argv、terminal whole-wall check、process factory/Popen 前返回 canonical `PENDING_MANUAL_REVIEW`/exit 3（计划第 442–443 行；source fix 第 27–32 行）。`RunResult`、run dispatch payload 和 run exit mapping 都位于 `utils/investment_agent_acceptance.py`（第 1652–1727、1865–1892 行），所以只改该 owner 即可完成，毋须 schema 或 evaluator 变更。
4. **独立 verify 的 terminal-absent 前缀已经是合法读取契约。** `_load_and_validate_receipt_prefix()` 先机械校验完整 planned prefix，再由 `_validate_terminal_receipt()` 在 terminal 缺席时返回 `None`（第 3730–3759、3841–3899 行）。因此人工填写后可直接走 `verify --plan --fingerprint --json`，不需要恢复、补写或兼容 terminal receipt。
5. **PASS/FAIL 独立 verify 的所有权边界明确。** `verify_acceptance()` 只读 loader 的 receipts、计算 live result、原子写 acceptance receipt（第 1730–1758 行）；它并不写 phase receipt。计划进一步指定 PASS/FAIL 均保持 planned receipt 字节不变且不创建 terminal（第 443–446 行），并以状态机测试锁定。
6. **persisted terminal 与 no-resume 仍 fail closed。** 现有 `_validate_terminal_receipt()` 对旧 failed/signal/timeout/incomplete/non-passed terminal 在 evaluator 前拒绝；`_assert_no_existing_run_receipts()` 对任何已有 planned 或 terminal receipt 在进程前拒绝再次 run（第 3720–3727 行）。计划和 source fix 都保留这些不变量，未引入 cleanup、marker 或 resume 分支。
7. **发布前拒绝的顺序被具体指定。** 当前 `_evaluate_live_plan()` 在 strict inventory 后会先写 `source-inventory.json`（第 4406–4426 行），随后才解析 quality review（第 4445 行），这正是此修正必须在 CLI owner 内重排/延迟发布的直接事实。计划 Slice 4 第 445 行和 source fix 第 39 行明确要求 malformed、secret/PII、plan/receipt/repository/artifact drift 在任何 acceptance-owned output 发布前 fail closed，并将其列为必须测试的可验收行为；实现不需要修改 evaluator/contract。
8. **allowlist、冻结与授权边界足够且最小。** 未来实现仅允许 `utils/investment_agent_acceptance.py` 与 `tests/test_investment_agent_acceptance.py`（source fix 第 48–55 行）；这与上述所有权一致。计划第 449 行冻结 Slice 4 文档，且第 921、928–932 行继续冻结 Slice 5/live，因此无文档、schema、生产 formatter 或外部授权回归。
9. **测试覆盖是状态机导向而非 happy-path-only。** source fix 第 57–65 行逐项要求 exact pending、PASS、合法 FAIL、malformed/secret/drift、non-exact pending、persisted non-passed terminal 和 same-plan rerun；计划第 442–447 行重复该可执行断言。它们同时验证 terminal argv/process factory/Popen 都为零、outputs/receipt bytes 不变和 evaluator 前拒绝，足以防止本次回归。

## Findings

无 material finding。

## Architecture / best practice / optimality review

- **架构边界**：判定、CLI 返回码和 output sequencing 都归 CLI 编排层；rubric skeleton、质量规则与三态语义仍归 pure evaluator；严格 parser 与 receipt schema 仍归 contracts。依赖方向未反转。
- **最佳实践**：以 raw canonical bytes 加 strict parser 双重条件识别初始 skeleton，避免 partial/reordered/pre-filled review 被语义等价或宽松解析误判；以 persisted receipt loader 作为 public ingress，避免 evaluator 承担不可信 lifecycle 解析。
- **最优性**：相对新增 marker、terminal pending receipt、第二 action 或 schema migration，本方案只在 terminal dispatch 前插入一个确定性分支，直接消除不可恢复的 non-passed terminal，变更面最小。
- **不过度设计 / 不过度耦合**：没有新增 facade、compatibility parser、resume protocol、跨模块写入或生产 CLI flag。现有 `RunResult` 与 main dispatch 是完成 canonical pending output/exit 3 的本地 owner，tests 也集中在既有 acceptance 测试文件。

## Open questions

无阻塞性的 open question。

实现时唯一需按计划已写明的验收点是：将 live verify 的 acceptance-owned 输出发布置于全部 strict ingress、repository/artifact closure 和 evaluator 安全检查之后；这不是 plan 缺口，而是 Slice 4 明确要求的实现与测试顺序。

## Residual risks and suggested tracking destination

- evaluator 时间字段、owner formatter drift、fixture lock 与未来 same-plan recovery 保持原计划第 14 节既有跟踪去向；本修正不扩大其范围。
- exact pending 判定有意要求 canonical bytes 完全相等；operator 仅格式化或重排原 skeleton 也不会走 handoff，而会落入 strict non-pending path。这是防止伪装 skeleton 的安全取舍，已由 source fix 第 40、63 行要求测试。
- Slice 5 仍为 `LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN`；本审查没有授予 SEC、Web、模型、网络、密钥或付费调用权限。

## Final plan review conclusion

**PASS。** 本 revision 已把已证实的 terminal lifecycle 死锁收敛为可直接实施的最小状态机修正，并以足够的 failure-path 测试定义守住 terminal-absent、发布顺序、persisted terminal fail-closed 和 same-plan no-resume。Open High / Medium / Low = **0 / 0 / 0**。依当前 gate，后续仍须由 controller 完成双路裁决；本 reviewer 不进入下一 gate。
