# AAPL acceptance Slice 4 — docs implementation artifact（DeepSeek V4 Flash）

- 日期：2026-08-09
- Gate：Slice 4（操作文档与 README 同步）implementation；非 controller，不启动 review/commit/push/live
- 分支：`feat/investment-agent-acceptance`
- 基线：`6129122`（accepted manual-review handoff commit，worktree clean）
- 前置：manual-review handoff production correction 已由 Controller + Terra 双路验收（`docs/reviews/manual-review-handoff-code-adjudication-20260809-codex.md` CODE REVIEW ACCEPTED，Terra final artifact re-review PASS/open H/M/L=0），Slice 4 docs handoff-ready
- 状态：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**（Controller 裁决 Terra S4D-001 Low ACCEPT，修复见 `docs/reviews/slice-4-aapl-acceptance-docs-review-fix-20260809-deepseek-flash.md`；Terra final + MiM corrective 双路复审已闭合，见文末 Dual-loop closure）；Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**
- Source review：`docs/reviews/slice-4-aapl-acceptance-docs-review-terra.md`（S4D-001 Low，Controller ACCEPT）

## Changed files（精确 allowlist，三文件 + 本 artifact）

1. 新建 `docs/acceptance/investment-agent-aapl.md`（operator runbook）
2. 修改 `README.md`（§3.8 最短入口 + §9 文档导航）
3. 修改 `tests/README.md`（fixture 真源边界 + live 禁止 CI）
4. 新增 `docs/reviews/slice-4-aapl-acceptance-docs-implementation-20260809-deepseek-flash.md`（本 artifact）

未修改：code、tests、fixtures、plan、config、`dayu/`、`utils/investment_agent_acceptance*.py`、contracts/evaluator、其它 README。

工作树验证（implementation 完成后）：`git status --short` 如实输出：

```text
 M README.md
 M tests/README.md
?? docs/acceptance/
```

## 零编辑核对（先核对真实 CLI，再写文档）

以下事实全部先于文档通过直接证据核对，未依据计划文档假设：

| 核对项 | 证据 | 结果 |
|---|---|---|
| 顶层入口 | `python -m utils.investment_agent_acceptance`（无子命令）实测 | 打印 `usage: investment-agent-acceptance [-h]` + `错误: 必须指定 prepare、run 或 verify`，exit 2 |
| 顶层 `--help` | `python -m utils.investment_agent_acceptance --help` 实测 | 打印 `usage: investment-agent-acceptance [-h]` + `错误: 子命令必须是 prepare、run 或 verify`，exit 2；顶层不提供子命令列表，仅 `prepare`/`run`/`verify` 可进入各自的 `--help` |
| 三个子命令 `--help` | `prepare --help` / `run --help` / `verify --help` 实测 | 均 exit 0，各自打印完整参数面；参数面证据以下列三条为准 |
| prepare 参数 | `prepare --help` | `--ticker --company --template --as-of --run-root --price-snapshot --max-model-requests --max-total-tokens --max-estimated-cost --budget-currency --max-wall-seconds --json`，无默认预算 |
| run 参数 | `run --help` | `--plan --fingerprint --json` |
| verify 参数 | `verify --help` | `--fixture` 或 `--plan --fingerprint`，`--json`；`--fixture` 与 `--plan/--fingerprint` 严格互斥（exit 2） |
| 缺 `--json` / 缺参 / 互斥 | 实测 | 均 exit 2 |
| exit 3 handoff | `main()`/`run_acceptance()`（`utils/investment_agent_acceptance.py`） | exact pending skeleton → `PENDING_MANUAL_REVIEW` JSON + exit 3；terminal Popen=0；不写 verify.json/source-inventory/acceptance-receipt |
| 三组 download 窗口 | `build_phase_specs()` | `10-K` start=as-of−5y、`10-Q` start=as-of−2y、`8-K DEF 14A` start=as-of−2y，均 `--end as-of` + resolved `--config` + 一个 `--quiet` |
| price material | `build_phase_specs()` + `prepare_acceptance()` | `upload_material --forms MATERIAL_OTHER --material-name aapl-price-snapshot --document-id <stable> --files inputs/price-snapshot.material.md --report-date <market-date>`；stable ID 来自 `build_material_ids(form_type="MATERIAL_OTHER", material_name="aapl-price-snapshot", fiscal_year=None, fiscal_period=None)` |
| process | `build_phase_specs()` | 仅一次 `process --ticker AAPL --quiet` |
| write | `build_phase_specs()` | preflight：`--preflight-only --no-resume` + 四预算；paid：`--materialize-research --research-base --no-resume` + 四预算 |
| validators | `build_phase_specs()` | 5 条 `research-template validate-*`，均 `--base <run-root>/research --config <resolved-config>` |
| 13 产物 | `REQUIRED_RESEARCH_ARTIFACTS`（contracts） | 与 runbook 清单逐项一致 |
| 评分 | evaluator `_TOTAL_POINTS=100`/`_MINIMUM_TOTAL_SCORE=85`/`_DIMENSION_MINIMUMS`（20/24/20/0/0） | runbook §6 一致 |
| 环境变量名称 | `REQUIRED_ENVIRONMENT_NAMES`（contracts） | `DEEPSEEK_API_KEY`、`MIMO_API_KEY`、`SEC_USER_AGENT`，仅 presence |
| env policy | `SUBPROCESS_ENV_POLICY` | `TQDM_DISABLE=1`、`HF_HUB_DISABLE_PROGRESS_BARS=1`、`TRANSFORMERS_VERBOSITY=error` |
| run root 约束 | `_validate_new_run_root()` + `_RUN_PARENT_LOCATOR` | 精确位于 `workspace/acceptance/investment-agent-aapl/`、run-id `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`、目标不存在 |
| fixture verify | 实测 | `PASS` / `total_score=85` / exit 0；临时根 `workspace/tmp/investment-agent-aapl-fixture-verify` 被 `.gitignore` 覆盖，运行后无残留 |

## 文档内容对照（plan §9 Slice 4 + §14 Docs decision）

`docs/acceptance/investment-agent-aapl.md` 覆盖计划要求的两条 lane（deterministic/live）、package config/template 真源（resolver + `research_templates/` canonical tree + 根级 `定性分析模板.md`）、三组 download 窗口、price snapshot JSON→canonical Markdown material/stable document id→upload→process、prepare 审 plan/fingerprint/budget/wall/env、run 12 planned phases 后 exact pending exit 3/no terminal/no outputs、人工完整填写后独立 verify PASS/FAIL、preflight 与请求/token/成本/币种授权、run root/receipts/13 artifacts/评分、no-resume 失败现场只读保留 + 新 run root 重新 prepare、secret/PII/sanitizer/cleanup、monitoring unbound/workbook open residuals、fixture 非 freshness 真源/live 禁止 CI。根 README 只加最短入口与导航，未复制完整 rubric；tests README 说明 fixture 不是 freshness 真源、live 禁止 CI。

约束执行：
- 示例只使用当前真实参数名；live 预算、wall、price snapshot、run-id 全部使用 `<占位符>`，未提供任何默认值（未写入 60/1,500,000/12 CNY 等示例）。
- 无 API key 示例值；环境变量只出现名称。
- 无 future design 表述；`- materials 处理: 未实现（TODO）` 是 owner 真实固定文案，属于当前实现描述。
- 未引入新 flag/action/schema/marker。

## Validation（全部命令与结果）

| 命令 | 结果 |
|---|---|
| `git diff --check` | clean（无 whitespace/EOF 问题） |
| `python -m utils.validate_handoff_docs --json` | `{"ok": true, "issues": []}` |
| `python -m utils.codex_review_gate --allow-waiting --json` | ok；`WAITING_FOR_TASK` 状态与基线一致，`issues: []` |
| `python -m utils.dual_model_pipeline_check --json` | `"ok": true` |
| `python -m utils.investment_agent_acceptance verify --fixture tests/fixtures/investment_agent/aapl_acceptance --json` | `verdict: PASS`、`total_score: 85`、exit 0 |
| `python -m pytest tests/test_investment_agent_acceptance.py -q` | **220 passed** |
| README/tests README 链接目标 | `docs/acceptance/investment-agent-aapl.md`、`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md` 均存在 |
| CLI 示例参数核对 | runbook 中 prepare/run/verify/download/upload_material/process/write/validator 示例 flag 与 `--help` 及 `build_phase_specs()` 逐一一致 |

文档仅新增/修改 README 与 tests README，未触碰任何 code/test/fixtures/plan/config，因此 pyright/ruff/coverage 目标集无变化；focused acceptance 测试 220 passed 确认既有实现基线未受影响。工作树中的临时目录（`workspace/acceptance/`、`workspace/tmp/`）均为空且被 `.gitignore` 覆盖，无残留。

## Docs decision

- 命中根 README 触发规则：项目级使用方式（投资 Agent 验收入口）变化 → 只更新 §3.8 最短入口与 §9 文档导航，不复制 rubric，符合用户手册职责。
- 命中 tests README 触发规则：tests fixture 语义说明 → 只更新 §1 目录分层与 §2 运行方式，说明 fixture 非 freshness 真源与 live 禁止 CI。
- 不修改 `dayu/README.md`、Engine/Host/Fins/config README：本 slice 不改变分层、公共契约、Fins 机制或配置格式（与 plan §14 Docs decision 一致）。
- `docs/acceptance/` 为新建目录，职责为 acceptance operator runbook，不与任何包 README 职责重叠。

## Residuals

- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**；未读取密钥、未调用 SEC/Web/模型/网络/付费。
- 本 slice 未 commit / push / PR；等待 final re-review（Terra S4D-001 Low ACCEPT 已修复，见 `docs/reviews/slice-4-aapl-acceptance-docs-review-fix-20260809-deepseek-flash.md`）。
- runbook 中 `download` 等 Fins owner 命令的标题锚（如 `下载结果`）为当前 formatter 文案；owner 文案变更会导致验收可用性中断，属 plan §14 已记录 residual，由结构 drift 测试与重新 plan 承接。
- 本 artifact 未改动 `docs/reviews/` 既有 review artifacts；README/tests README/runbook/code/tests/plan/source review 均未修改。

## Final declaration

Slice 4 三文件文档实现已完成并全部验证：先零编辑核对真实 CLI help、`build_phase_specs()`、13 产物清单、评分常量与环境/run-root 约束，再写文档；runbook 覆盖两条 lane、真源、三组 download、price material import、process、人工质量三态、timeout、preflight 与显式费用授权、产物目录、评分、恢复和 cleanup；根 README 仅最短入口与导航，tests README 守住 fixture 非 freshness 真源与 live 禁止 CI。示例只用当前真实参数，live 预算/price snapshot 不给默认。docs gates（validate_handoff_docs / codex_review_gate / dual_model_pipeline_check）全绿，diff-check clean，focused acceptance 220 passed。Terra S4D-001 Low 已按 Controller ACCEPT 裁决完成 artifact-only 修复：顶层无子命令与顶层 `--help` 均精确记录为打印 usage + “子命令必须是 prepare、run 或 verify”并 exit 2，仅 `prepare`/`run`/`verify` 三个子命令 `--help` exit 0 并作为参数面证据；状态更新为 **REVIEW FIX APPLIED / AWAITING FINAL RE-REVIEW**。完成即停止，不启动 review/commit/push/live。

## Dual-loop closure（Gate 追加，2026-08-09 20:03:53 CST）

本 slice 的 artifact-only 双路复审已全部闭合，进入本地 accepted commit 前置状态：

| 审查方 | artifact | 结论 |
|---|---|---|
| Terra final re-review | `docs/reviews/slice-4-aapl-acceptance-docs-final-rereview-terra.md` | **PASS**，open H/M/L=`0/0/0`；五条 CLI 命令独立复跑与修复后 artifact 精确一致，冻结 SHA 复核通过 |
| MiM corrective re-review | `docs/reviews/slice-4-aapl-acceptance-docs-review-corrective-mim.md` | **PASS**，open H/M/L=`0/0/0`；原 M-001/M-002 两项 finding 撤回并闭合 |
| Controller adjudication | `docs/reviews/slice-4-aapl-acceptance-docs-adjudication-20260809-codex.md` | **CLOSED / DUAL RE-REVIEW PASS**；Slice 4 可进入 artifact-only closure 与本地 accepted commit |

### Finding 处置

- **S4D-001（Terra Low）**：ACCEPTED / **FIXED / CLOSED**。artifact-only 修复已把顶层无子命令与顶层 `--help` 精确记录为打印 usage + “子命令必须是 prepare、run 或 verify”并 exit 2，仅三个子命令 `--help` exit 0 并作为参数面证据；Terra final 独立复跑确认一致。
- **M-001（MiM 原 Medium）**：REJECTED-WITH-REASON / **MEASUREMENT-ERROR / CLOSED**。implementation artifact 的精确命令 `python -m pytest tests/test_investment_agent_acceptance.py -q` 复测为 `220 passed`；MiM 初审误加 `tests/fins/test_cli_formatters_coverage.py` 得到 229，非同一命令，corrective 复审已撤回。
- **M-002（MiM 原 Low）**：REJECTED-WITH-REASON / **NON-DEFECT / CLOSED**。runbook 职责为 operator 操作指引，无需记录 CLI 内部错误文案差异；真实行为已由 implementation/fix artifact 精确留证。

### Gate 审计（本 closure）

- `git diff --check`：clean（exit 0）。
- trailing whitespace：三份 Slice 4 文档产物与全部 review artifacts 均 0 行；README 中 6 行既有 Markdown 双空格硬换行属基线，diff 新增行 0 行引入，非回归。
- final newline：上述全部文件均以单个 LF（0x0a）结尾。
- 冻结路径 SHA-256：`README.md=ac0fca5258e0149f77356499d1e7d411882e997b9a1ae7346ca3fcb2d3b4d2ef`、`tests/README.md=53d016e4a416ee29bfd626d72c5e07e4b17936b7c5b9d3655cd32fdf6f7dd9bc`、`docs/acceptance/investment-agent-aapl.md=741cf861c79eb92092dab12bfc5410baf6740e458ae5a6e3ca0b302eb0920e6b`、`docs/reviews/slice-4-aapl-acceptance-docs-review-terra.md=9cf473e2ce221910e73f35a33982fc93f8cf244736c06caf1a6a9f1cbef93f22`，与 review-fix / Terra final 记录一致；冻结文件 mtime（19:38:37 / 19:38:48 / 19:38:24 / 19:47:09）早于本轮且未再写入。
- worktree 仅含 Slice 4 实现 allowlist（`M README.md`、`M tests/README.md`、`?? docs/acceptance/`）与 Slice 4 review artifacts；无 code/tests/fixtures/plan 变动。

### Residuals

- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**；未读取密钥、未调用 SEC/Web/模型/网络/付费。
- 本 closure 未 commit / push / PR；等待 Controller 授权本地 accepted commit。
- runbook 中 download 等 Fins owner 命令的标题锚为当前 formatter 文案，owner 文案变更会导致验收可用性中断，属 plan §14 已记录 residual，由结构 drift 测试与重新 plan 承接。

### Final declaration

Slice 4 双路复审（Terra final PASS / MiM corrective PASS，open H/M/L 均 `0/0/0`）与 Controller adjudication（CLOSED / DUAL RE-REVIEW PASS）全部闭合：S4D-001 已按 ACCEPT 裁决 artifact-only 修复，M-001 为 measurement/command-scope error、M-002 为 non-defect，均已撤回闭合。本 artifact 状态更新为 **DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**；README、tests README、runbook、code、tests、fixtures、plan、Controller 与 reviewer source artifacts 均未修改。Slice 5 / live 仍 NOT AUTHORIZED。完成即停止，不启动 review/commit/push/live。
