# AAPL acceptance Slice 2 corrective re-review

## Scope

- Mode: current changes corrective re-review
- Branch: `feat/investment-agent-acceptance`
- Base / HEAD: `1c7e16160b23704558508e9c25522a116d67ad84`
- Reviewed at: 2026-08-09 15:11 CST
- Output file: `docs/reviews/code-review-20260809-151500-codex.md`
- Included scope: 当前六个 production/test allowlist 文件；updated implementation/adjudication/review-fix artifacts；新 `slice-2-aapl-acceptance-final-review-fix-20260809-150224-codex.md`；150002 的 H1/H2/H3/M1/M2/L1 闭合；修复引入的新回归
- Excluded scope: live、network、SEC、provider/model、付费调用、commit/push；不修改 production/tests/plan/既有 artifacts
- Parallel review coverage: 无；本报告的三个复现均为独立本地验证。并行 reviewer artifact 未作为输入读取或采纳
- Verdict: **FAIL**
- Open findings: **High 2 / Medium 1 / Low 0**

## Findings

### CR-1-未修复-高-静态 sanitizer 仍会把等号 Authorization/Cookie 与连字符 API key 原文写入 receipt

- **入口/函数**: `_execute_phase()` / `_command_record()` → `_stream_summary()` → `_redact_cli_text()`
- **文件(行号)**: `utils/investment_agent_acceptance.py:108-122, 2047-2065, 2705-2738`；对照 evaluator 真源 `utils/investment_agent_acceptance_evaluator.py:89-99, 2357-2384`
- **输入场景**: owner/第三方 stderr、title prefix 或 structure-reject 行包含 `Authorization = Bearer <value>`、`Cookie=<value>`、`api-key=<value>`。这些都是 evaluator 明确以 `[:=]` 与 `api[_-]?key` 识别的敏感形状。
- **实际分支**: runner header regex 只允许冒号；assignment regex 只识别以 `API_KEY`/`TOKEN`/`SECRET`/`PASSWORD` 结尾的下划线名字。等号 Authorization/Cookie 和连字符 `api-key` 均不匹配，随后 fragment 被直接拼进 summary。
- **预期行为**: accepted plan §5.1/§7/§8.1 要求 acceptance-owned receipt 在持久化前排除任意 Authorization、cookie、secret shape/provider body；runner 至少应覆盖 evaluator 已声明的同一敏感形状闭集。
- **实际行为**: 原值进入 `stdout_summary`/`stderr_summary`，后置 evaluator 即使判 FAIL 也无法撤销已落盘 secret。
- **直接证据**: 本轮直接调用 `_stream_summary(..., category="stderr_present")` 的输出为：
  - `fragment=Authorization = Bearer review-secret-value-123`
  - `fragment=Cookie=session=review-cookie-value-123`
  - `fragment=api-key=review-api-key-value-123`
  evaluator 的 `_SECRET_PATTERNS` 在 `89-94` 对前两类使用 `[:=]`，对 API key 使用 `api[_-]?key`；runner 的两个 regex 明显更窄。新增 sanitizer test 只注入冒号 headers 与 `MIMO_API_KEY=...`，未覆盖这些 evaluator-supported variants。
- **影响**: secret/credential persistence；失败 run root 按设计保留，扩大本机泄漏与误归档风险。150002 H3 仅部分闭合。
- **建议改法和验证点**: 不再维护比 evaluator 更窄的第二套模式。把 acceptance-owned pre-persistence 静态 sanitizer 与 evaluator 的静态 shape contract收敛为一个公共、无环境值读取的真源，或最少补齐 `authorization|proxy-authorization|cookie|set-cookie` 的 `[:=]` 与 `api[_-]?key|access[_-]?token|secret` assignments。对 stderr/prefix/reject/CLI 四入口参数化验证冒号、等号、下划线、连字符与 JSON key 写法，断言 canonical receipt bytes 不含原值。
- **修复风险（低/中/高）**: 中；过宽表达式可能吞掉诊断尾部，但保留 category/line 与 raw stream SHA 即可维持取证。
- **严重程度（低/中/高/严重）**: 高

### CR-2-未修复-高-failed/signal terminal receipt 被 loader 接受且 evaluator 不产生 finding

- **入口/函数**: outer `run_acceptance()` 写 `verify.json` → 独立 `verify_acceptance()` → `_load_and_validate_receipt_prefix()` → `_validate_terminal_receipt()` → `_build_runtime_evidence()` / `_evaluate_wall_clock()`
- **文件(行号)**: `utils/investment_agent_acceptance.py:1696-1715, 1747-1752, 3836-3883, 4457-4482`；`utils/investment_agent_acceptance_evaluator.py:1406-1427`
- **输入场景**: terminal verify subprocess 非零或被 signal，outer run 如实写 `verify.json` 且返回 failed；之后 operator/外部状态修复生产产物并调用独立 verify，或 receipt 被 canonical 改写成 lifecycle-valid `status=failed/signal`。
- **实际分支**: `_validate_terminal_receipt()` 只检查 identity、time、argv/digest 与 null evidence，不要求 terminal/record `status="passed"`。它把 failed/signal terminal 返回并纳入 runtime；evaluator wall gate只对 `timeout` 或 `partial_by_timeout` 产生 finding，对普通 failed/signal 无 gate。
- **预期行为**: plan 规定任一 semantic/nonzero/timeout/signal 后停止且不自动 resume；可选 persisted terminal 一旦存在，独立 verify 只能接受完整 passed 自动链，不能把 outer run 的失败终态提升为可通过验收。
- **实际行为**: 独立 verify 可越过 failed/signal terminal。若当前 artifacts 已满足 evaluator，其结果可为 PASS/PENDING 并原子写新的 `acceptance-receipt.json`，与 outer run 的失败事实冲突。
- **直接证据**: 本轮用真实 builder/fake runner生成完整 canonical receipts，再仅把 terminal phase/record改为 lifecycle-valid `failed`、`exit_code=7`、非空 stop reason 并 canonicalize；`_load_and_validate_receipt_prefix()` 接受，复现输出：`FAILED_TERMINAL_ACCEPTED failed wall_findings []`。`_evaluate_wall_clock()` 源码只检查 timeout/partial。现有 terminal wall test只覆盖 passed terminal 的时间纳入，没有 failed/signal terminal reload test。
- **影响**: execution failure 可被后续 verification 提升为接受结果，破坏 terminal state、no-resume 与 audit truth；这是 acceptance correctness 的 High。
- **建议改法和验证点**: `_validate_terminal_receipt()` 在存在 terminal 时强制 phase status passed、唯一 record passed/exit 0（contract aggregate虽机械闭合，loader仍应显式 gate）。同时 evaluator runtime defensively 对任意非-passed receipt产生 High finding。新增 failed、signal、timeout 三态 canonical terminal reload tests，断言 loader拒绝且不写/替换 acceptance receipt。
- **修复风险（低/中/高）**: 低；只收紧已完成自动链的 terminal gate，不改变 outer run 的真实失败 receipt 写入。
- **严重程度（低/中/高/严重）**: 高

### CR-3-未修复-中-material persisted evidence 的 plan price hashes 可被 canonical 篡改而仍通过 reload

- **入口/函数**: `_load_planned_receipt_prefix()` → `_validate_persisted_phase_evidence()` → `_validate_persisted_material_evidence()` → `_require_persisted_semantic_pass()`
- **文件(行号)**: `utils/investment_agent_acceptance.py:3815-3826, 3886-3925, 3980-4016, 3433-3459`；schema 字段 `utils/investment_agent_acceptance_contracts.py:959-1038`
- **输入场景**: 保持 receipt schema、argv digest、repository primary SHA、document ID/report date 全部合法，只把 material evidence 必填的 `price_json_sha256` 和/或 `price_material_sha256` 改为其它小写 64 hex并 canonicalize。
- **实际分支**: material validator检查 raw argv document/report date、owner semantic、current repository primary SHA，以及 ok 分支 current meta；它从不把 evidence 的 `price_json_sha256`/`price_material_sha256` 与 `plan.price_snapshot_sha256`/`plan.price_material_sha256` 比较。`_owner_semantic_stop_reason()` 也只比较 repository primary SHA。
- **预期行为**: accepted plan §5.1 明确规定 material evidence 记录并绑定 plan price JSON/Markdown SHA；final fix artifact也声称 reload 重放 “plan SHA/ID”。
- **实际行为**: persisted audit record 可对两份 plan-owned price输入陈述虚假 hash，同时 verify loader认为证据闭合。
- **直接证据**: 本轮生成完整 passed run 后，把两个字段分别改为 `e*64`/`f*64`；loader输出 `TAMPER_ACCEPTED eeee... ffff...`。代码搜索显示两字段只在 evidence生成处赋 plan值，reload validator没有消费；新 tamper参数集未包含这两个字段。
- **影响**: 当前 evaluator仍通过独立 plan/file/repository检查获得正确 price truth，因此未证明可直接改变 verdict；但 per-command persisted audit evidence可被伪造，150002 H2 的 authenticity closure不完整。
- **建议改法和验证点**: 在 `_validate_persisted_material_evidence()` 精确比较 `evidence.price_json_sha256 == plan.price_snapshot_sha256`、`evidence.price_material_sha256 == plan.price_material_sha256`；对 skipped evidence 的非空 source fingerprint也应与 current repository fact相等。新增每个字段独立 canonical tamper test。
- **修复风险（低/中/高）**: 低；字段与 plan已有单一真源，属于缺失 equality gate。
- **严重程度（低/中/高/严重）**: 中

## 150002 六项逐项 closure

| 150002 finding | Closure | 独立证据 |
|---|---|---|
| H1 material report-date / truthful failed receipt | **CLOSED** | evaluator `2063-2096` 对 filing严格 `filing_date`、material严格 `report_date`并映射 frozen date；canonical argv仍只传 report date。phase runner `2241-2289` 捕获 parsed evidence后的 `ContractError`，保留 evidence/streams并写 `owner_semantic_contract_reject` failed record。focused test `4494-4597` 覆盖 source-kind date 与 repository error receipt。 |
| H2 persisted phase/domain evidence authenticity | **PARTIAL / OPEN CR-3** | type/null、download status/summary/forms/window、non-domain、current material/process repository drift已重验且 tests覆盖；但 material plan price JSON/Markdown evidence hashes没有 equality gate，canonical tamper仍接受。 |
| H3 pre-persistence sanitizer | **PARTIAL / OPEN CR-1** | 冒号 Authorization/Cookie/X-API-Key、下划线 token/secret/password、provider token/home path已在落盘前替换；等号 auth/cookie与连字符 api-key仍泄漏。 |
| M1 TimeoutExpired partial/cumulative drain | **CLOSED** | `_execute_command()` 捕获 `TimeoutExpired.output/stderr`；terminate/kill 后 bounded `communicate()`，complete非空优先且不拼接，unconfirmed保留 partial。terminate/kill/unconfirmed三态 digest tests通过。真实 adapter直接转发 `Popen.communicate()` 的 cumulative retry语义。 |
| M2 terminal wall + slow Popen deadline | **CLOSED for stated timing defect; new terminal-status defect CR-2** | `_execute_command()` 在 start前立 deadline、Popen后重算 child timeout；loader返回 optional terminal并纳入 phase receipts/acceptance outputs/首尾 actual wall，独立 clock不参与。slow-start与 terminal-wall tests通过。terminal status gate是另一个执行终态缺口。 |
| L1 Git pattern single truth | **CLOSED** | CLI在 import处直接复用 contracts exported `GIT_OBJECT_ID_PATTERN`，provider `1038`调用同一对象；test锁 40/64 lowercase与对象 identity。 |

## 修复回归与架构审计

- H1 的 source-kind 日期分支没有把 material report-date fallback污染到 filing；repository storage仍只经 Fins protocols/owner Fs composition root。
- H2 validator新增为私有纯校验路径，没有调用 `source-inventory.json` writer；process/material current repository closure仍为只读。CR-3 是缺失 equality，不是建议新增第三个真源。
- Timeout path没有重新引入 `wait()`-only空流伪造；terminate/kill OSError仍保留最后 partial bytes。
- Formatter production diff仍精确一个 `- status: ...` 可执行行；ok/cancelled顺序/唯一性 tests通过。
- 当前新增 acceptance utils/tests未发现 `Any`、`object`、新增 `cast`、type-ignore、`getattr`/`hasattr` 或 glue wrapper逃逸。formatter coverage file里的既有 `cast` 不在本轮新增 diff。

## Verification evidence

全部命令只读；临时复现仅写系统临时目录并自动清理，没有 live/network/paid side effect。

```text
git diff --check
exit 0

python -m pytest tests/test_investment_agent_acceptance.py \
  tests/fins/test_cli_formatters_coverage.py -q -p no:randomly
168 passed in 2.81s

pyright <exact six allowlist files>
0 errors, 0 warnings, 0 informations

ruff check <exact six allowlist files>
All checks passed!
```

Green tests是真实结果，但缺少 CR-1 的 evaluator-equivalent敏感 variants、CR-2 的 failed/signal terminal reload，以及 CR-3 的 material plan-hash tamper，因此不能支持 PASS。

## Open Questions

- 无。三个 finding均有静态同链证据与可执行复现，不依赖 live行为。

## Residual Risk

- 未执行 live/SEC/provider/model/paid workflow；不影响三个确定性 finding与其严重度判断。
- 未重跑 full repository tests；focused 168、exact Pyright、Ruff与diff-check均通过。
- force-kill/stale runtime artifacts仍按 accepted operator recovery residual管理，本轮未发现新的 lock/cleanup defect。

## Final decision

**FAIL — open High/Medium/Low = 2/1/0.** CR-1仍可在持久化前泄漏凭据，CR-2可把 failed/signal terminal自动链提升为后续可验收状态；在这两个 High与 CR-3 audit authenticity缺口关闭前，不应进入 accepted commit/merge。
