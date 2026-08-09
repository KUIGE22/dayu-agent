# Slice 2 AAPL Acceptance Round 3 Review Fix

- 时间：2026-08-09 15:30 CST
- 基线：`1c7e16160b23704558508e9c25522a116d67ad84`
- Codex review：`code-review-20260809-152500-codex.md` — FAIL，open H/M/L=0/1/0
- Terra review：`code-review-20260809-152501-terra.md` — PASS，open H/M/L=0/0/0
- Controller：R3-1 Medium **ACCEPTED / FIXED**；CR-1/CR-2/CR-3 保持 CLOSED
- 状态：**CLOSED / DUAL RE-REVIEW PASS**
- Live：**NOT AUTHORIZED / NOT RUN**

## R3-1 — shared CommandRecord stream lifecycle

共享 contract 现在先闭合 phase status/exit/termination，再由单一 stream lifecycle helper 判定进程是否明确未启动：

- `status=failed`、`exit_code=null`、`stop_reason=process_start_failed` 是唯一 start-failure 表示；
- `status=timeout`、`termination_action=not_started` 是 whole-wall 在 start 前耗尽的唯一表示；
- 上述两种记录必须同时令 `stdout_sha256`、`stderr_sha256` 为 null，且不得有 stream summary/evidence；
- 其它 passed/failed/timeout/signal records 均表示 Popen 已成功 start，两项 stream SHA 必须同时为合法小写 SHA-256；空流使用 `sha256(b"")`，不得双 null 或单边 null。

这保持 runner 既有合法生成语义：`process_start_failed` 与 `not_started` 没有伪造空流 digest；communication failure、nonzero、signal、semantic failure、terminate/kill timeout 继续记录成对真实 digest。

## Adversarial tests

- 对 passed `verify.json`、`write.json`、`validations.json` 分别执行双 null、仅 stdout null、仅 stderr null canonical mutation，共九个 cases；全部在 shared `parse_phase_receipt` contract 处 fail closed。
- 构造 canonical `process_start_failed` record/receipt，双 null strict round-trip 保持合法。
- 给同一 start-failure record伪造空字节 SHA pair会被拒绝，证明 null 不是可选审计字段而是明确未启动事实。

## Validation

| Gate | Result |
|---|---|
| focused | 195 passed |
| exact coverage | CLI 82%、contracts 87%、evaluator 87%、total 84.61% |
| six-file exact pyright | 0 errors / 0 warnings / 0 informations |
| Ruff default | pass |
| Ruff F/I | new utils/tests pass；formatter F pass，I001 为 HEAD baseline |
| key full-rule | new utils 0 findings |
| owner research-template | 128 passed / 88 deselected |
| owner source/write | 54 passed |
| deterministic fixture CLI | PASS / exit 0 |

## Scope / handoff

Production/test diff 仍限于 accepted 六文件；formatter production delta仍精确一行 status。没有修改 plan、README、fixtures 或其它 production/tests；没有 live/network/SEC/provider/model/paid调用；没有 commit、push、PR、review 或 Slice 3。

## Final dual re-review closure

Codex `code-review-20260809-153500-codex.md` 与 Terra `code-review-20260809-153501-terra.md` 对同一 frozen round 3 tree 均为 **PASS**，open H/M/L=`0/0/0`。R3-1 以及回归抽查的 CR-1/CR-2/CR-3 全部 CLOSED；原 Codex `150002`、Terra `150003`、Codex `151500`、Terra `151501`、Codex `152500`、Terra `152501` findings 全部 CLOSED。外部 DeepSeek/MiMo 402 状态继续如实保留。

历史 handoff 状态为 `REVIEW FIX APPLIED / AWAITING DUAL RE-REVIEW`；当前状态：**CLOSED / DUAL RE-REVIEW PASS**。
