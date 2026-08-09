# AAPL acceptance Slice 4 — docs review fix artifact（DeepSeek V4 Flash）

- 日期：2026-08-09
- Gate：Slice 4 docs review fix；非 controller，不启动 review/commit/push/live
- 分支：`feat/investment-agent-acceptance`
- 基线：`6129122`（accepted manual-review handoff commit，worktree clean）
- Source review：`docs/reviews/slice-4-aapl-acceptance-docs-review-terra.md`（S4D-001 Low）
- Controller 裁决：Terra S4D-001 Low **ACCEPT**，仅 artifact-only 修复
- 状态：**CLOSED / DUAL RE-REVIEW PASS**；Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**

## S4D-001（Low，Controller ACCEPT）— implementation artifact 错报顶层 CLI help 的实际结果

### Finding（Terra 原文要点）

`docs/reviews/slice-4-aapl-acceptance-docs-implementation-20260809-deepseek-flash.md:33` 声称“`python -m utils.investment_agent_acceptance --help` / 无子命令 exit 2 | 仅 `prepare`、`run`、`verify`”。实测顶层 `--help` 与无子命令都只打印 `usage: investment-agent-acceptance [-h]` 后接“子命令必须是 prepare、run 或 verify”（无子命令为“必须指定 prepare、run 或 verify”）并 exit 2，并不列出三个子命令；三个具体子命令的 `--help` 才正常 exit 0。该行验证记录不可复现，削弱审查链准确性（不影响 runbook 命令/预算/live 隔离语义）。

### 修复（仅 implementation artifact，无 code/tests/README/runbook/plan/source review 改动）

在 `docs/reviews/slice-4-aapl-acceptance-docs-implementation-20260809-deepseek-flash.md`：

1. 零编辑核对表首两行改为精确事实：
   - 顶层入口（无子命令）：实测打印 `usage: investment-agent-acceptance [-h]` + “错误: 必须指定 prepare、run 或 verify”，exit 2；
   - 顶层 `--help`：实测打印 `usage: investment-agent-acceptance [-h]` + “错误: 子命令必须是 prepare、run 或 verify”，exit 2；顶层不提供子命令列表，仅 `prepare`/`run`/`verify` 可进入各自的 `--help`；
   - 三个子命令 `--help`：均 exit 0，各自打印完整参数面；参数面证据以下列三条为准。
2. 原“缺 `--json` / 缺参 / 互斥 / 无子命令”改为“缺 `--json` / 缺参 / 互斥”（无子命令已由顶层入口行覆盖）。
3. 头部状态改为 **REVIEW FIX APPLIED / AWAITING FINAL RE-REVIEW**，加入 source review 路径 `docs/reviews/slice-4-aapl-acceptance-docs-review-terra.md`。
4. Residuals 与 Final declaration 同步 closure 事实（S4D-001 accepted/fixed）。

未修改：`README.md`、`tests/README.md`、`docs/acceptance/investment-agent-aapl.md`、code、tests、fixtures、plan、`docs/reviews/slice-4-aapl-acceptance-docs-review-terra.md`（source review 原样保留）。

## 修复后精确验证（5 命令证据）

| # | 命令 | 实测结果 |
|---|---|---|
| 1 | `python -m utils.investment_agent_acceptance`（无子命令） | exit 2；`usage: investment-agent-acceptance [-h]` + `error: 必须指定 prepare、run 或 verify` |
| 2 | `python -m utils.investment_agent_acceptance --help` | exit 2；`usage: investment-agent-acceptance [-h]` + `error: 子命令必须是 prepare、run 或 verify` |
| 3 | `python -m utils.investment_agent_acceptance prepare --help` | exit 0；完整 prepare 参数面 |
| 4 | `python -m utils.investment_agent_acceptance run --help` | exit 0；`--plan --fingerprint --json` |
| 5 | `python -m utils.investment_agent_acceptance verify --help` | exit 0；`--fixture`/`--plan --fingerprint` + `--json` |

以上 5 条命令在本次修复时重新实测（exit code 单独捕获，不经过管道），与修复后 artifact 记录完全一致。

## Validation（scoped audit only）

| 命令 | 结果 |
|---|---|
| `git diff --check` | clean（无 whitespace/EOF 问题） |
| trailing whitespace / final newline 审计 | 两份更新 artifact 均无 trailing whitespace、均以单个 final newline 结尾 |
| `git status --short` exact audit | `M README.md`、`M tests/README.md`、`?? docs/acceptance/`、`?? docs/reviews/slice-4-aapl-acceptance-docs-implementation-20260809-deepseek-flash.md`、`?? docs/reviews/slice-4-aapl-acceptance-docs-review-fix-20260809-deepseek-flash.md`、`?? docs/reviews/slice-4-aapl-acceptance-docs-review-terra.md`，与预期一致（README/tests README 为 Slice 4 实现 allowlist，本轮未改动；source review 为独立 worker 产物，未改动） |
| 未改动文件 freeze（mtime + SHA-256 快照） | 本轮修复时间戳为 19:48–19:49；`README.md`(19:38:37)、`tests/README.md`(19:38:48)、`docs/acceptance/investment-agent-aapl.md`(19:38:24)、`docs/reviews/slice-4-aapl-acceptance-docs-review-terra.md`(19:47:09) 的 mtime 均早于本修复且本轮未再写入。当前 SHA-256 快照：`README.md=ac0fca5258e0149f77356499d1e7d411882e997b9a1ae7346ca3fcb2d3b4d2ef`、`tests/README.md=53d016e4a416ee29bfd626d72c5e07e4b17936b7c5b9d3655cd32fdf6f7dd9bc`、`docs/acceptance/investment-agent-aapl.md=741cf861c79eb92092dab12bfc5410baf6740e458ae5a6e3ca0b302eb0920e6b`、`docs/reviews/slice-4-aapl-acceptance-docs-review-terra.md=9cf473e2ce221910e73f35a33982fc93f8cf244736c06caf1a6a9f1cbef93f22`（无修复前基线，快照仅证明当前冻结状态） |

本轮未运行 pytest/pyright/ruff/coverage（artifact-only 修复，production/tests/README/runbook 未改动；上一轮 focused acceptance 220 passed 保持有效）。

## Residuals

- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**；未读取密钥、未调用 SEC/Web/模型/网络/付费。
- 本 review fix 未 commit / push / PR；Terra final re-review（PASS/open H/M/L=0/0/0）与 MiM corrective re-review（PASS/open H/M/L=0/0/0）已双路闭合，Controller adjudication 为 CLOSED / DUAL RE-REVIEW PASS；closure 见 `docs/reviews/slice-4-aapl-acceptance-docs-closure-20260809-deepseek-flash.md`。
- 全仓既有 pyright baseline 与 SERPER 环境失败不在本 artifact-only 修复 scope 内。

## Final declaration

Terra S4D-001（Low）已按 Controller ACCEPT 裁决完成 artifact-only 修复：implementation artifact 的零编辑核对表把顶层结果改为精确事实（顶层无子命令与顶层 `--help` 均打印 usage + “子命令必须是 prepare、run 或 verify”并 exit 2，只有 prepare/run/verify 三个子命令 `--help` exit 0 并作为参数面证据），状态更新为 **REVIEW FIX APPLIED / AWAITING FINAL RE-REVIEW**，头部加入 source review 路径。5 条 CLI 命令重新实测并逐条记录；diff-check 与 whitespace/LF 审计通过；README/tests README/runbook/code/tests/plan/source review 均未改动（mtime 早于本修复，当前 SHA-256 快照已冻结记录）。完成即停止，不启动 review/commit/push/live。
