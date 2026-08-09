# AAPL acceptance Slice 2 round 3 final corrective re-review

## Scope

- Mode: current changes, final round 3 corrective re-review
- Branch: `feat/investment-agent-acceptance`
- Base / HEAD: `1c7e16160b23704558508e9c25522a116d67ad84`
- Reviewed at: 2026-08-09 15:34 CST
- Output file: `docs/reviews/code-review-20260809-153500-codex.md`
- Included scope: R3-1 shared `CommandRecord` stream-SHA lifecycle；CR-1/CR-2/CR-3 regression sample；updated implementation/adjudication/fix artifacts
- Excluded scope: live/network/SEC/provider/model/paid、commit/push、其它 slice；不修改 production/tests/plan/既有 artifacts
- Parallel review coverage: 无；所有静态判断与 canonical 复现均由本 reviewer 独立完成
- Verdict: **PASS**
- Open findings: **High 0 / Medium 0 / Low 0**

## Findings

未发现新的实质性 H/M/L 问题。

## R3-1 closure

| Attack / legitimate lifecycle | Verdict | Independent evidence |
|---|---|---|
| passed terminal/write/validations 双 null | **REJECTED / CLOSED** | shared `_validate_command_record_streams()` 只把明确 start failure 与 `timeout/not_started` 视为未启动，其它记录任一 SHA 为 null 都拒绝。九个真实 canonical loader mutations（3 phases × 双 null/仅 stdout null/仅 stderr null）全部通过 fail-closed 测试。 |
| passed 任一单 null | **REJECTED / CLOSED** | 本轮直接构造 canonical passed receipt，`parse_phase_receipt()` 对仅 stdout null、仅 stderr null 均抛 `ContractError`。 |
| 真实 `process_start_failed` 双 null | **LEGAL** | `status=failed`、`exit_code=null`、`stop_reason=process_start_failed`、无 termination/partial/evidence/summary 的 canonical receipt strict round-trip 成功；双 SHA 或任一单 SHA 均拒绝。 |
| 真实 `timeout/not_started` 双 null | **LEGAL** | `status=timeout`、`exit_code=null`、`termination_action=not_started`、`partial_by_timeout=true` 的 canonical receipt strict round-trip 成功；双 SHA 或任一单 SHA 均拒绝。 |
| 已启动 failed/timeout/signal | **PAIR REQUIRED / CLOSED** | 本轮分别构造 lifecycle-valid canonical receipts：成对空流 SHA 均接受；双 null、仅 stdout null、仅 stderr null 均由 parser 拒绝。runner 的 communication failure、nonzero/signal、terminate/kill/unconfirmed 路径继续为已启动结果提供 bytes，`_command_record()` 因而生成成对 SHA。 |

共享 contract 的判定顺序也保持一致：先闭合 phase status/exit/termination，再闭合 stream lifecycle；明确未启动必须双 null 且不得含 summary/evidence，明确已启动必须双 SHA。没有 phase-local 复制规则或 loader bypass。

## CR-1 / CR-2 / CR-3 regression sample

| Finding | Verdict | Evidence |
|---|---|---|
| CR-1 pre-persistence sanitizer | **No regression** | `_stream_summary()` 仍在截断/serialization 前调用统一 `_redact_cli_text()`；单一 field pattern继续覆盖 `[:=]`、大小写、连字符/下划线 Authorization/Cookie/API key/token/secret/password。3 variants × 4 ingress tests 包含在 195 focused pass 中。 |
| CR-2 terminal passed-only/no-resume | **No regression** | `_validate_terminal_receipt()` 仍要求 phase与唯一 record均 passed、exit 0、无 stop/termination/partial、evidence null；failed/signal/timeout canonical terminal mutations均拒绝且 sentinel acceptance receipt不被覆盖。 |
| CR-3 material plan SHA binding | **No regression** | `_validate_persisted_material_evidence()` 仍分别绑定 `price_json_sha256 == plan.price_snapshot_sha256` 与 `price_material_sha256 == plan.price_material_sha256`；两字段独立 tamper tests均通过。 |

## Static and scope audit

- R3 改动没有弱化 receipt-derived discovery、owner strict grammar、repository closure、timeout/Popen deadline、evaluator scoring truth 或 formatter一行 delta。
- acceptance 三个 production modules 与对应 tests 未发现新增 `Any`、`object`、`cast`、type-ignore、`getattr`/`hasattr` 逃逸；精确 Pyright/Ruff通过。
- formatter production diff仍精确一行：ticker 后、summary 前唯一输出 `- status: {result.status}`。
- production/test scope仍限 accepted 六文件；其余当前新增文件为本 Slice review/fix artifacts。`git diff --check` 通过。

## Verification evidence

```text
independent shared-contract canonical matrix
PASSED_double-null=REJECT
PASSED_stdout-null=REJECT
PASSED_stderr-null=REJECT
start-failure_double-null=ACCEPT
start-failure_non-double-null=REJECT
not-started_double-null=ACCEPT
not-started_non-double-null=REJECT
started-failed_pair=ACCEPT missing=REJECT
started-timeout_pair=ACCEPT missing=REJECT
started-signal_pair=ACCEPT missing=REJECT

targeted R3 + CR-1/2/3 pytest selection
18 passed, 168 deselected

python -m pytest tests/test_investment_agent_acceptance.py \
  tests/fins/test_cli_formatters_coverage.py -q -p no:randomly
195 passed in 3.39s

pyright <exact six allowlist files>
0 errors, 0 warnings, 0 informations

ruff check <exact six allowlist files>
All checks passed!

git diff --check
exit 0
```

## Open Questions

- 无。R3-1 两侧 lifecycle 均有 shared-parser 与真实 loader 可执行证据。

## Residual Risk

- 未执行 live/SEC/provider/model/paid workflow；这是明确未授权范围，不影响 deterministic lifecycle closure。
- 未重跑 full repository suite；focused 195、exact Pyright/Ruff 与 canonical adversarial matrix覆盖本轮变更边界。

## Final decision

**PASS — open High/Medium/Low = 0/0/0.** R3-1 已真实闭合，CR-1/CR-2/CR-3 未回归；当前 round 3 corrective tree 未发现新的 H/M/L finding。
