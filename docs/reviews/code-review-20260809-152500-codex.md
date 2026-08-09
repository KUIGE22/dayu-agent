# AAPL acceptance Slice 2 round 3 corrective re-review

## Scope

- Mode: current changes, final corrective re-review
- Branch: `feat/investment-agent-acceptance`
- Base / HEAD: `1c7e16160b23704558508e9c25522a116d67ad84`
- Reviewed at: 2026-08-09 15:24 CST
- Output file: `docs/reviews/code-review-20260809-152500-codex.md`
- Included scope: CR-1/CR-2/CR-3 round2 fixes、对应 production paths/tests、updated implementation/adjudication/fix artifacts；抽查前轮 H1/M1/M2/L1
- Excluded scope: live/network/SEC/provider/model/paid、commit/push、其它 slice；不修改 production/tests/plan/既有 artifacts
- Parallel review coverage: 无；所有静态判断与复现均由本 reviewer 独立完成
- Verdict: **FAIL**
- Open findings: **High 0 / Medium 1 / Low 0**

## Findings

### R3-1-未修复-中-passed terminal 可删除成对 stream SHA 后仍被 strict loader 接受

- **入口/函数**: `verify_acceptance()` → `_load_and_validate_receipt_prefix()` → `_validate_terminal_receipt()`；底层 `CommandRecord.__post_init__()` → `_validate_command_record_status()`
- **文件(行号)**: `utils/investment_agent_acceptance.py:3841-3898`；`utils/investment_agent_acceptance_contracts.py:4102-4131`；accepted plan `docs/plans/2026-08-09-investment-agent-aapl-acceptance.md:133-134`
- **输入场景**: 对真实生成的 canonical passed `verify.json` 保持 phase/record status passed、exit 0、argv/digest/time/evidence 全部不变，仅把 `stdout_sha256` 与 `stderr_sha256` 同时改成 null 并重新 canonicalize。
- **实际分支**: terminal validator检查 passed、单 record、exit/stop/termination/partial 和 null evidence，但不要求 stream SHA 非空。contract validator只在两项 SHA 有且只有一项非空时拒绝；两项同时 null 会被解释为“未启动”，却没有把该事实与 `status=passed/exit_code=0` 联动。
- **预期行为**: plan明确规定成功 start 后即使空流也必须记录空字节 SHA，只有 start failure 才能为 null。passed/exit 0 证明 command已启动，因此必须保留成对 SHA。
- **实际行为**: canonical persisted terminal 可删除完整 raw stream digest evidence，loader仍把它当作“完整 passed lifecycle”并允许独立 verify继续。
- **直接证据**: 本轮生成完整 passed run 后执行上述双-null mutation，复现输出：`PASSED_TERMINAL_NULL_STREAM_SHA_ACCEPTED None None`。源码 `contracts.py:4123-4131` 只检查“任一存在则成对”和“全空时不得有 summary/evidence”，没有 `passed -> started` gate。round2 terminal tests只覆盖 failed/signal/timeout，未覆盖 passed + missing pair。
- **影响**: 不直接改变 price/source/evaluator业务结论，但允许篡改或损坏后的 receipt 丢失 plan要求的 terminal取证摘要，削弱 persisted audit authenticity；同一 contract gap也适用于其它没有 domain evidence的 passed records。
- **建议改法和验证点**: 在共享 command lifecycle contract 中要求 `status=passed` 时 stdout/stderr SHA 均非 null；更一般地，除 `process_start_failed` 与 `not_started` timeout 外，所有已尝试启动的终态都要求成对 SHA。新增 passed terminal及 write/validation record“双-null” canonical tamper tests，断言 loader拒绝且 existing acceptance-receipt sentinel不被覆盖。
- **修复风险（低/中/高）**: 低；真实 runner已为成功启动的空流计算 SHA，不改变合法生成路径，只收紧 persisted reload。
- **严重程度（低/中/高/严重）**: 中

## CR-1 / CR-2 / CR-3 closure

| Finding | Closure | 独立证据 |
|---|---|---|
| CR-1 evaluator-equivalent sanitizer | **CLOSED** | 单一 `_STATIC_SECRET_FIELD_PATTERN` 在 byte truncation/serialization前处理 `[:=]`、大小写、连字符/下划线 Authorization/Proxy-Authorization/Cookie/Set-Cookie/API key/access token/token/secret/password；`_redact_cli_text()` 同时供 receipt与CLI使用。12个四-ingress参数化 cases通过。本轮直接验证冒号/等号、连字符/下划线与 access-token均输出 `<redacted>`。 |
| CR-2 non-passed terminal no-resume | **CLOSED for failed/signal/timeout; R3-1 exposes a distinct passed-lifecycle gap** | `_validate_terminal_receipt()` 明确要求 phase/唯一 record passed、exit 0、无 stop/termination/partial、evidence null。failed/signal/timeout三态 canonical mutation均在 loader阶段拒绝；本轮独立复现确认预置 sentinel byte-identical。 |
| CR-3 material plan SHA binding | **CLOSED** | material validator同时比较 `evidence.price_json_sha256 == plan.price_snapshot_sha256` 和 `evidence.price_material_sha256 == plan.price_material_sha256`。本轮分别单独篡改两个字段，均由 loader抛 `ContractError`。 |

## Previous-fix regression sample

- H1: material仍严格以 report date进入 frozen inventory；parsed semantic/repository `ContractError` 仍收敛 truthful failed receipt。
- M1: `TimeoutExpired` partial/cumulative drain、terminate/kill/unconfirmed分支未改变，三态 digest tests通过。
- M2: Popen后重算 deadline、persisted terminal纳入 actual wall仍存在且 focused tests通过。
- L1: CLI仍直接使用 contracts导出的同一 `GIT_OBJECT_ID_PATTERN`。
- formatter production delta仍精确一个 status行；未发现新增 `Any`/`object`/cast/ignore/getattr/hasattr/glue逃逸。

## Verification evidence

```text
targeted CR-1/CR-2/CR-3 pytest selection
17 passed, 159 deselected

python -m pytest tests/test_investment_agent_acceptance.py \
  tests/fins/test_cli_formatters_coverage.py -q -p no:randomly
185 passed in 3.66s

pyright <exact six allowlist files>
0 errors, 0 warnings, 0 informations

ruff check <exact six allowlist files>
All checks passed!

git diff --check
exit 0

independent canonical mutations
ROUND3_CANONICAL_REJECTIONS_OK terminal=failed,signal,timeout sentinel=preserved material=price_json_sha256,price_material_sha256
PASSED_TERMINAL_NULL_STREAM_SHA_ACCEPTED None None
```

## Open Questions

- 无。R3-1 由 accepted plan、shared lifecycle contract与可执行复现直接证明。

## Residual Risk

- 未执行 live/SEC/provider/model/paid workflow；不影响 deterministic closure与 R3-1 判断。
- 未重跑 full repository suite；focused 185、exact Pyright/Ruff、diff-check均通过。

## Final decision

**FAIL — open High/Medium/Low = 0/1/0.** CR-1/CR-2/CR-3 的指定攻击场景已真实闭合，但 persisted passed lifecycle仍允许成对 stream SHA 同时缺失；关闭 R3-1 前不应给最终 PASS。
