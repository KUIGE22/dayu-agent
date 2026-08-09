# AAPL acceptance manual-review handoff — corrective review fix artifact（DeepSeek V4 Flash）

- 日期：2026-08-09
- Gate：Controller adjudication 后窄修复（Terra re-review 两项均 ACCEPT；仅修复
  MRH-001-remaining 与 RER-001，不扩大 scope）；非 controller，不启动 gateflow，
  不进入 commit/push/PR/live
- 分支：`feat/investment-agent-acceptance`
- 基线：`4d91a16`（accepted plan baseline）
- Source：Controller 裁决与 `docs/reviews/manual-review-handoff-code-review-terra.md` 的
  Terra re-review（两项 ACCEPT）
- 状态：**CONTROLLER + TERRA REVIEW PASS / READY FOR ACCEPTED COMMIT**（closure：Controller
  adjudication `docs/reviews/manual-review-handoff-code-adjudication-20260809-codex.md`
  CODE REVIEW ACCEPTED / READY FOR ACCEPTED COMMIT；Terra final artifact re-review
  `docs/reviews/manual-review-handoff-code-final-rereview-terra.md` PASS/open H/M/L=0。
  历史 FAIL/fix/timepoint 状态全部保留，快照未重写。Terra final re-review 唯一 Low
  MRH-004-regression 已 ACCEPT，final artifact-only fix 已应用，见
  `docs/reviews/manual-review-handoff-final-artifact-fix-20260809-deepseek-flash.md`。
  MiM provider 未参与本 gate 且不计为 PASS（free service ended, browser auth pending）
- Slice 4 docs：本 correction 已 accepted，Slice 4 docs handoff-ready
- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**

## Changed files（精确 allowlist）

1. `utils/investment_agent_acceptance.py`（MRH-001-remaining 生产修复）
2. `tests/test_investment_agent_acceptance.py`（MRH-001-remaining 测试 + RER-001 类型修复）
3. 更新 `docs/reviews/manual-review-handoff-implementation-20260809-deepseek-flash.md`
4. 更新 `docs/reviews/manual-review-handoff-review-fix-20260809-deepseek-flash.md`
5. 新增 `docs/reviews/manual-review-handoff-corrective-review-fix-20260809-deepseek-flash.md`（本 artifact）

未触碰：`utils/investment_agent_acceptance_contracts.py`、`utils/investment_agent_acceptance_evaluator.py`、
全部 `dayu/`、fixtures、README、plan 与其它 reviews。无新 flag/action/schema/marker。

## MRH-001-remaining — reviewer 元数据 email/PII 未覆盖 evidence_paths（ACCEPT）

### 修复

`_assert_reviewer_metadata_sanitized(review: QualityReview)` 扩展为统一收集并检查以下
全部文本的 canonical email（含 `@` 即 ContractError）：

- `reviewer_role`；
- `reviewer_id_label`；
- 全部 rubric dimension item 的 `evidence_paths`（`review.dimensions[].items[].evidence_paths`）；
- 全部 manual finding 的 `evidence_paths`（`review.findings[].evidence_paths`）。

secret/header/home-path 形状仍由 `_assert_quality_review_sanitized` 对完整载荷的既有
静态扫描覆盖（覆盖上述所有字段），本函数只补充 evaluator `_evaluate_reviewer_metadata`
独有的 email 拒绝，不复制 evaluator 私有 pattern，不修改 evaluator。`_read_quality_review_canonical`
调用顺序不变：strict parse → canonical bytes → 整体载荷扫描 → reviewer 元数据扫描，
因此 run（handoff 判定）与独立 verify（`_evaluate_live_plan` quality ingress）均在
terminal 派生、Popen、evaluator 与任何 acceptance outputs 之前 ContractError。

### 测试（新增 4 用例）

- `_inject_evidence_path_email(payload, field)`：把 `alice@example.com` 注入 rubric
  item `evidence_paths` 或 manual finding `evidence_paths`（构造 strict-valid finding：
  finding_id/severity/status/summary/evidence_paths）。
- `test_manual_review_pii_evidence_paths_fails_closed_in_run`（parametrize
  rubric_evidence/finding_evidence）：run 在 planned 12 命令后 ContractError
  （`match="个人标识"`）；terminal Popen 计数 12（未派生 terminal）；
  `verify.json`、`source-inventory.json`、`acceptance-receipt.json` 均不存在。
- `test_manual_review_pii_evidence_paths_fails_closed_in_verify`（parametrize 同）：
  独立 verify ContractError；patch `acceptance_cli_module.evaluate_acceptance` 断言
  调用计数 0；source-inventory/acceptance-receipt/verify.json 均不存在。

### 验证

focused 220 passed；pyright 0 errors；ruff F,I passed；CLI coverage 88%。

## RER-001 — 新增 test helper 使用 dict[str, object]（ACCEPT）

### 修复

`_seed_real_live_chain` 中 `source_meta` 与 `material_meta` 两处
`dict[str, object]` 改为测试文件已 import 的严格 `JsonObject` 类型别名
（`from utils.investment_agent_acceptance_contracts import JsonObject`）；
无 `Any`/`object`/`cast`/`type-ignore` 新增或遗留。

### 验证

目标 pyright 0 errors（含测试文件）；ruff F,I passed。

## Validation（全部命令与结果）

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/test_investment_agent_acceptance.py -q` | **220 passed** |
| `python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py tests/cli/test_research_template_command.py -q` | **445 passed** |
| `python -m pytest tests/test_investment_agent_acceptance.py -q --cov=utils.investment_agent_acceptance --cov=utils.investment_agent_acceptance_contracts --cov=utils.investment_agent_acceptance_evaluator --cov-report=term` | CLI **88%** / contracts 87% / evaluator 87% |
| `pyright utils/investment_agent_acceptance.py utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py tests/test_investment_agent_acceptance.py` | **0 errors, 0 warnings** |
| `ruff check --select F,I utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | **All checks passed** |
| `git diff --check -- utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | clean |
| 全仓 `python -m pytest -q`（上一轮） | **7365 passed, 1 failed, 6 skipped**；唯一失败 `test_web_tools.py::test_search_with_serper_requires_api_key` 为基线环境依赖失败（本机 `SERPER_API_KEY` 已设置），与本 corrective fix 无关 |
| 全仓 `pyright` | 17 errors 全部位于 docling_processor/test_web_tools（既有 baseline）；目标文件 0 errors |

最终工作树状态（如实）：

```text
 M tests/test_investment_agent_acceptance.py
 M utils/investment_agent_acceptance.py
?? docs/reviews/manual-review-handoff-code-rereview-terra.md
?? docs/reviews/manual-review-handoff-code-review-terra.md
?? docs/reviews/manual-review-handoff-corrective-review-fix-20260809-deepseek-flash.md
?? docs/reviews/manual-review-handoff-implementation-20260809-deepseek-flash.md
?? docs/reviews/manual-review-handoff-review-fix-20260809-deepseek-flash.md
```

两处 `M` 为实现 allowlist；五个 `??` 分别为 Terra re-review、source review、本
corrective artifact、implementation artifact 与 review-fix artifact（均未纳入索引，
如实列示，MRH-004）。

## Residuals

- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**；未读取密钥、
  未调用 SEC/Web/模型/网络/付费。
- 本 corrective fix 未 commit / push / PR / 进入 Slice 4 或 Slice 5（历史时点：当时等待
  最终双路 code re-review（DeepSeek + MiMo）与 Controller adjudication；现已由
  Controller + Terra PASS/open H/M/L=0 闭合，MiM provider 未参与且未记 PASS）。
- `_seed_real_live_chain` 依赖 fixture 语料与固定 SEC accession，仅用于 deterministic
  回归，不声明 live freshness；不进入生产路径。
- 全仓 pyright 17 条既有错误与 SERPER 环境失败为 baseline，不修白名单外文件。

## Final declaration

MRH-001-remaining 与 RER-001 窄修复完成并验证，final artifact-only fix
（MRH-004-regression）已应用并获 Controller + Terra 双路验收：focused 220 全绿、
目标文件 pyright 0 errors、ruff F/I 通过、diff-check clean、CLI 行覆盖 88% ≥ 80%、
精确 allowlist 仅两文件 + 四份 review artifacts。状态 **CONTROLLER + TERRA REVIEW
PASS / READY FOR ACCEPTED COMMIT**；MiM provider 未参与且未记为 PASS（free service
ended, browser auth pending）。完成即停止，不 commit/push/review/Slice4。
