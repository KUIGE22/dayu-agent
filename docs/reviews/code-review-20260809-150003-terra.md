# Code Review

## Scope

- Mode: current changes（相对 `1c7e161` 的当前 Slice 2 未提交 diff）
- Branch: `feat/investment-agent-acceptance`
- Base: `1c7e16160b23704558508e9c25522a116d67ad84`
- Output file: `docs/reviews/code-review-20260809-150003-terra.md`
- Included scope: Slice 2 六个 allowlist 文件、对应 focused tests、accepted plan、DS/MiMo source reviews、三轮 plan fixes、最终双路 plan reviews，以及 implementation/adjudication/review-fix artifacts。
- Excluded scope: Slice 3+、README/docs implementation、真实 SEC/Web/模型/provider 调用；均不在本次只读 re-review 边界内。
- Parallel review coverage: 无。本报告是 DeepSeek/MiMo 由于 402 无法完成后的独立 Terra lane；未启动子 agent。

## Findings

### TERRA-001-未修复-高-流摘要只脱敏 provider key，仍会把 Authorization/Cookie 写入 phase receipt

- **入口/函数**: `_execute_phase()` 处理带前缀或 grammar reject 的 owner stdout，以及 `_command_record()` 处理任意非空 stderr。
- **文件(行号)**: `utils/investment_agent_acceptance.py:2611-2613, 2639-2647`；安全 gate 的对照在 `utils/investment_agent_acceptance_evaluator.py:2367-2379`。
- **输入场景**: 任一 `dayu.cli` 子进程或其第三方依赖把 `Authorization: Bearer ...`、`Cookie: ...` 或类似 header/body 片段输出到 stderr；或 download/upload/process 的 title 前缀、结构拒绝行携带该文本。
- **实际分支**: `_command_record()` 无条件把非空 stderr 传给 `_stream_summary(..., category="stderr_present")`。该函数会把选中的原始行拼进 `stderr_summary`；stdout 的 `prefix_noise`/`structure_reject` 也走同一分支。唯一净化调用 `_redact_cli_text()` 只使用 `dayu.redaction.SECRET_KEY_PATTERN`，其模式只匹配 `sk-...` / `AIza...` provider token，并不匹配 Authorization 或 Cookie header。
- **预期行为**: phase receipt 只能含有静态脱敏、512-byte 有界诊断，不能持久化凭据、Authorization header、cookie 或 provider body。accepted plan §6.1 gate 9 与 §7（`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md:257,264`）对此是明确 hard contract。
- **实际行为**: receipt 在 `_write_phase_receipt()` 时已经把未净化的 `stdout_summary`/`stderr_summary` 原子持久化。后续 evaluator 虽会用 `_SECRET_PATTERNS` 和 `_SENSITIVE_KEYS` 检出 header/cookie 并将 verdict 判为 FAIL，但这是**事后检测**：秘密已经落入 run root 中保留以供审计的 receipt，不能满足“不保存”的安全承诺。
- **直接证据**: evaluator 的 `_SECRET_PATTERNS` 明确包含 `authorization`、`proxy-authorization`、`cookie`、`set-cookie`（`investment_agent_acceptance_evaluator.py:80-94,2367-2379`），但 runner 的 `_stream_summary()` 没有调用或等价实现这些规则。现有 `test_slice1_sanitizer_rejects_secret_and_posix_windows_home_shapes` 已把 `Authorization` 和 `Cookie` 作为敏感值（`tests/test_investment_agent_acceptance.py:2824-2839`），却只覆盖 evaluator 的事后 finding，没有覆盖 receipt writer 的落盘前脱敏。
- **影响**: 真实 provider/network 失败、第三方 warning 或 malformed owner 输出可以把 bearer token/cookie 写入 `.gitignore` 运行目录。该目录按设计在失败后保留，扩大了本机泄漏与误归档风险；这也使本 Slice 的 secret-handling hard gate 不能被视为闭合。
- **建议改法和验证点**: 在 `_stream_summary()` 进入 summary 之前实施一个**不读取环境值**的静态 redact helper：至少覆盖 evaluator 同等的 Authorization/Cookie header key/value 形状、`sk-`/`AIza` provider token 和 home path；然后再做 UTF-8 byte 截断。不要复用会枚举 `os.environ` 值的动态 redactor。新增 fake-runner tests：分别从 stderr、prefix noise 与 structure-reject stdout 注入 Authorization/Cookie/provider-body 字样，断言写出的 `CommandRecord`、canonical receipt 和 CLI stderr 都不含原文，且摘要仍有分类/行号；并保留 evaluator sanity assertion。
- **修复风险（低/中/高）**: 低。修改集中在 acceptance harness 的静态 summary sanitizer 与测试，不需要改 owner formatter 或 live 行为。
- **严重程度（低/中/高/严重）**: 高。

## 原 findings 与计划观察的闭合核验

| 来源 | 复核结果 | 直接证据 |
|---|---|---|
| DS H-1 / H-2 | 已闭合 | v3 `CommandRecord` 逐条保存 download evidence；`_receipt_discovery()` 仅从 receipt 取 latest discovery，未从待检 inventory 回推。 |
| DS M-1..M-5 / L-1..L-5 | 已闭合或按 accepted adjudication 保留 | repo-private fixture root/owner lock、`timeout/not_started`、material primary SHA、strict dirty、atomic source inventory、单一 window/form/regex 真源均存在；unknown receipt 与 composition-root concrete owner 依 accepted disposition 继续 fail-closed。 |
| MiMo H-1 / M-3 / M-5 / M-6 / M-7 / L-1..L-7 | 已闭合 | evaluator 持有 score/hard-gate 真源；Popen 明确 repo cwd/DEVNULL/env；whole-wall 和 `termination_unconfirmed` 有实际 tests；`--json` 为 required ingress。 |
| MiMo M-2 / M-4 | **未闭合（本报告 TERRA-001）** | unexpected `Exception` 已只输出静态类型，但 command stream diagnostics 的 header/cookie 脱敏仍缺失。 |
| DS F-001..F-008、MiMo corrective observations、C-001 | 已闭合 | owner formatter title anchor、download status 单行 delta、download/upload/process strict grammar、opaque tail、receipt terminal writer 与 static env policy均与 accepted plan 一致。 |
| DS G-001..G-003、MiMo final L-1/L-2/open question | 已闭合 | upload action/status 正交，process 行内只收 document ID，空 form 分类 reject，稀疏 upload grammar 与 files header 均被实现和 focused tests覆盖。 |

## Open Questions

- 无。TERRA-001 的触发输入、持久化路径和缺失的净化规则均能在同一执行链中静态证明。

## Residual Risk

- focused tests、类型检查与 diff whitespace 均通过；`ruff --select F,I` 对 `dayu/fins/cli_formatters.py` 报告一个与本次单行 formatter delta 无关的既有 I001 import-order 基线，故该组合命令非零。该基线不改变 TERRA-001 的结论。
- 未执行任何 live/SEC/Web/provider/网络/付费调用；Slice 5 仍未授权。

## 验证记录

- `python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py -q -p no:randomly`：150 passed。
- `pyright` 六个 Slice 2 allowlist 文件：0 errors / 0 warnings / 0 informations。
- `git diff --check`：通过。

## Conclusion

**FAIL** — open High/Medium/Low = **1 / 0 / 0**。除 TERRA-001 外，已逐项验证 source review、plan-review observations 与 accepted adjudication 的实现闭合；但 receipt 在写盘前的静态脱敏不完整，当前 diff 不应进入 Slice 2 accepted commit 或后续 Slice 3。
