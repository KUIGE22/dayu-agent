# Code Review

## Scope

- Mode: current changes（相对 `1c7e161` 的当前 Slice 2 未提交 diff）
- Branch: `feat/investment-agent-acceptance`
- Base: `1c7e16160b23704558508e9c25522a116d67ad84`
- Output file: `docs/reviews/code-review-20260809-151501-terra.md`
- Included scope: accepted Slice 2 六文件实现/测试、更新后的 implementation/adjudication/review-fix artifacts、`slice-2-aapl-acceptance-final-review-fix-20260809-150224-codex.md`，以及上一轮 Terra `TERRA-001`、Codex `H1/H2/H3/M1/M2/L1` 的修复路径。
- Excluded scope: 真实 SEC/Web/模型/provider/live 调用、Slice 3+、README/操作文档；均未执行或改动。
- Parallel review coverage: 无。此为同一树的独立 corrective re-review，未启动子 agent。

## Findings

未发现实质性问题。

## 修复闭合核验

| 项目 | 裁决 | 直接证据 |
|---|---|---|
| Terra TERRA-001 / Codex H3：落盘前 stream sanitizer | **CLOSED** | `_command_record()` 仍只在写 receipt 前生成 summary，而 `_stream_summary()` 先调用 `_redact_cli_text()`；静态规则覆盖 Authorization/Proxy-Authorization、Cookie/Set-Cookie、X-API-Key、常见 API key/token/secret/password assignment、`sk-`/`AIza` 与 POSIX/Windows home path。`test_slice2_static_stream_sanitizer_covers_receipt_and_cli_output` 对 stderr、prefix noise、structure reject、CLI error 逐路断言原文不在 receipt/stdout-stderr。 |
| Codex H1：material 日期真源与 repository exception | **CLOSED** | evaluator ingress 对 filing 要求 `filing_date`，对 material 要求 `report_date`；runner 在 evidence 解析后将 repository/semantic `ContractError` 归一为 truthful failed record，不再让 exit-0 误报通过。 |
| Codex H2：persisted evidence authenticity | **CLOSED** | `_load_planned_receipt_prefix()` 在 canonical/argv binding 后调用 `_validate_persisted_phase_evidence()`；download 绑定 raw forms/canonical forms/start/end 并重放 semantic gate，material/process 重放语义和当前 repository closure，non-domain 与 terminal evidence 强制 null。修复测试覆盖 null/cross-type/cancelled/failed/wrong-window/wrong-form tamper。 |
| Codex M1：timeout partial/cumulative stream | **CLOSED** | `_execute_command()` 捕获 `TimeoutExpired.output/stderr`，终止路径 bounded drain 后选择完整或已捕获 partial bytes；168-test suite 对 terminate/kill/unconfirmed 的 SHA 与已脱敏摘要均有断言。 |
| Codex M2：terminal wall 与 slow Popen | **CLOSED** | loader 返回首次 persisted terminal receipt；`_build_runtime_evidence()` 用 receipt 首末时间计算原始 automated run wall，不使用当前独立 verify 时钟；child `communicate()` timeout 在 start 后按同一 monotonic deadline 重算。 |
| Codex L1：Git object-id 单一真源 | **CLOSED** | CLI 直接导入 contracts 的 `GIT_OBJECT_ID_PATTERN`；40/64 lower-case 接受与非法长度/大小写拒绝测试存在。 |
| 原 DS/MiMo findings 与 final plan observations | **CLOSED** | receipt-derived discovery、v3 per-command evidence、formatter one-line status delta、strict owner grammar、material status/action、process repository quality、Popen cwd/DEVNULL/env、timeout/lock/source-inventory/evaluator scoring truth 均未被 corrective patch 撤销或弱化。 |

## Open Questions

- 无。

## Residual Risk

- 未执行 live/SEC/Web/provider/模型/网络/付费调用；Slice 5 仍为未授权状态。
- `dayu/fins/cli_formatters.py` 的 import-order I001 是 HEAD 已有基线；本轮 formatter 的可执行生产 delta 仍仅为 download status 一行，未新增 lint debt。

## 验证记录

- `python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py -q -p no:randomly`：168 passed。
- six-file `pyright`：0 errors / 0 warnings / 0 informations。
- `ruff check` 新 acceptance modules/tests 与 formatter F rule：通过。
- `git diff --check`：通过。

## Conclusion

**PASS** — open High/Medium/Low = **0 / 0 / 0**。上一轮 TERRA-001 已在 receipt 持久化前闭合；本轮未发现 Codex H1/H2/H3/M1/M2/L1 或其 corrective patch 引入的新 H/M/L。
