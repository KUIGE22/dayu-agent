# AAPL acceptance manual-review handoff — review fix artifact（DeepSeek V4 Flash）

- 日期：2026-08-09
- Gate：Controller-accepted review fix（MRH-001..004 全部 accepted / 必须全修）；非 controller，
  不启动 gateflow，不处理未接受/额外重构，不进入 commit/push/PR/live
- 分支：`feat/investment-agent-acceptance`
- 基线：`4d91a16`（accepted plan baseline）
- Source review：`docs/reviews/manual-review-handoff-code-review-terra.md`（NOT PASS — FIX REQUIRED，open H/M/L = 0/2/2）
- 状态：**CONTROLLER + TERRA REVIEW PASS / READY FOR ACCEPTED COMMIT**（closure：Controller
  adjudication `docs/reviews/manual-review-handoff-code-adjudication-20260809-codex.md`
  CODE REVIEW ACCEPTED / READY FOR ACCEPTED COMMIT；Terra final artifact re-review
  `docs/reviews/manual-review-handoff-code-final-rereview-terra.md` PASS/open H/M/L=0。
  历史 FAIL/fix/timepoint 状态全部保留，快照未重写。Terra re-review 两项均 ACCEPT；
  corrective MRH-001-remaining 与 RER-001 已应用；Terra final re-review 唯一 Low
  MRH-004-regression 已 ACCEPT 并按 artifact-only 修复，见
  `docs/reviews/manual-review-handoff-corrective-review-fix-20260809-deepseek-flash.md`
  与 `docs/reviews/manual-review-handoff-final-artifact-fix-20260809-deepseek-flash.md`。
  MiM provider 未参与本 gate 且不计为 PASS（free service ended, browser auth pending）
- Slice 4 docs：本 correction 已 accepted，Slice 4 docs handoff-ready
- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**

## Changed files（精确 allowlist）

1. `utils/investment_agent_acceptance.py`（MRH-001/MRH-002 生产修复）
2. `tests/test_investment_agent_acceptance.py`（MRH-001..003 测试修复与新增）
3. 更新 `docs/reviews/manual-review-handoff-implementation-20260809-deepseek-flash.md`（MRH-004 工作树事实）
4. 新增 `docs/reviews/manual-review-handoff-review-fix-20260809-deepseek-flash.md`（本 artifact）

未触碰：`utils/investment_agent_acceptance_contracts.py`、`utils/investment_agent_acceptance_evaluator.py`、
全部 `dayu/`、fixtures、README、plan 与其它 reviews。无新 flag/action/schema/marker。

## MRH-001 — quality review 的 PII 未在 strict ingress 拒绝（中）

### 修复

`_read_quality_review_canonical()` 在既有 `_assert_quality_review_sanitized`（整体载荷
secret/home-path 静态扫描，复用 CLI 既有 pattern 集合）之后，新增
`_assert_reviewer_metadata_sanitized(review: QualityReview)`：

- 对 `reviewer_role`、`reviewer_id_label` 检查 canonical email（含 `@` 即 ContractError），
  与 evaluator `_evaluate_reviewer_metadata` 的 PII 规则同等；secret/home-path 形状已由
  整体载荷扫描对全部字段（含这三类字段与所有 evidence_paths）覆盖，不复制 evaluator
  私有 pattern，不修改 evaluator。
- `run`（handoff 判定内）与独立 verify（`_evaluate_live_plan` quality ingress）均在
  terminal 派生、Popen、evaluator 与任何 acceptance outputs 之前 ContractError。

### 测试

- `test_manual_review_pii_reviewer_metadata_fails_closed_in_run_and_verify`
  （parametrize：reviewer_id_label/reviewer_role 填 `alice@example.com`、
  `reviewer_id_label` 填 `/Users/alice/private`、evidence_path 填
  `/Users/alice/private/report.md`）：run 在 planned 12 命令后 ContractError，
  terminal Popen=0，verify.json/source-inventory/acceptance-receipt 均不存在。
- `test_manual_review_pii_reviewer_email_verify_fails_closed_before_outputs`：
  独立 verify 对 email reviewer label ContractError；patch
  `acceptance_cli_module.evaluate_acceptance` 断言调用计数 0；source-inventory、
  acceptance-receipt 与 verify.json 均不存在。

### 验证

focused 216 passed；pyright 0 errors；ruff F,I passed；CLI coverage 88%。

## MRH-002 — live verify 在 repository/artifact/evaluator 闭合前发布 source inventory（中）

### 修复

`_evaluate_live_plan()` 把 `_atomic_write_or_assert_same(run_root / "source-inventory.json")`
从 inventory round-trip 后立即发布，移动到 price material identity、contract、manifest、
summary、report、research artifacts、runtime evidence 全部闭合并且
`evaluate_acceptance(inputs, evaluated_at=...)` 成功返回之后（return 前）。任一
repository/artifact/evaluator 异常时 source-inventory 与 acceptance-receipt 保持不存在
或 sentinel byte-identical；planned phase receipts 不被读取侧修改。

### 测试

`test_manual_review_live_verify_drift_fails_closed_before_any_output`（parametrize：
manifest config 缺失 / report 文件删除 / material primary blob 篡改 / evaluator 抛异常）：
- 真实 `_seed_real_live_chain`（真实 Fins 仓储 + write 产物 + 13 research artifacts）下
  `verify_acceptance` 全部 ContractError；
- source-inventory 与 acceptance-receipt 保持 `sentinel-*` 字节不变；
- `phase-receipts/` 字节快照不变；
- 非 evaluator 分支 patch `acceptance_cli_module.evaluate_acceptance` 断言调用计数 0；
  evaluator 分支以真实抛异常函数注入并断言 sentinel 保持。

### 验证

focused 216 passed；pyright 0 errors；ruff F,I passed；CLI coverage 88%。

## MRH-003 — 新增测试对 evaluator 与独立 PASS/FAIL 路径的观测不真实（低）

### 修复

- `test_manual_review_verify_bad_quality_fails_closed_before_source_inventory` 改为 patch
  `acceptance_cli_module.evaluate_acceptance`（CLI 真实 consumer 的模块级绑定），
  `evaluator.call_count == 0` 观测真实调用点。
- `test_manual_review_independent_verify_pass_and_fail_preserve_planned_receipts_without_terminal`
  不再替换整个 `_evaluate_live_plan`：handoff 后 `monkeypatch.undo()` 恢复真实仓储函数，
  由 `_seed_real_live_chain` 构造真实 Fins 仓储（3 filing + 1 material + processed 状态 +
  primary blobs）、write manifest/run summary/report（fixture 语料替换为真实 document_id/
  accession/material ID 引用）与 `materialize_research_workspace` 13 产物，再经真实
  `verify_acceptance → _load_and_validate_receipt_prefix → _evaluate_live_plan →
  evaluate_acceptance` 得到真实 PASS（85）与真实 FAIL（50）verdict；
  - 以 spy（转发真实 `acceptance_cli_module.evaluate_acceptance`）断言调用次数恰为 1 且
    acceptance-receipt 字节等于真实 evaluator `canonical_bytes()`；
  - `phase-receipts/` 字节快照前后不变；verify.json 不存在；source-inventory 存在。

### 验证

真实 PASS/FAIL 两变体通过（探针验证 verdict=PASS/FAIL，随后移除探针）；focused 216 passed。

## MRH-004 — implementation artifact 的工作树事实不准确（低）

### 修复

`docs/reviews/manual-review-handoff-implementation-20260809-deepseek-flash.md` 的
Changed files 与 Validation 部分如实记录最终 `git status --short`：

```text
 M tests/test_investment_agent_acceptance.py
 M utils/investment_agent_acceptance.py
?? docs/reviews/manual-review-handoff-code-review-terra.md
?? docs/reviews/manual-review-handoff-implementation-20260809-deepseek-flash.md
?? docs/reviews/manual-review-handoff-review-fix-20260809-deepseek-flash.md
```

两处 `M` 为实现 allowlist；三个 `??` 分别为 source review、implementation artifact 与
本 fix artifact（均未纳入索引，如实列示）。artifact 状态更新为
**REVIEW FIX APPLIED / AWAITING RE-REVIEW**。

## Validation（全部命令与结果）

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/test_investment_agent_acceptance.py -q` | **220 passed**（含 corrective MRH-001-remaining evidence-path email 四用例） |
| `python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py tests/cli/test_research_template_command.py -q` | **445 passed** |
| `python -m pytest tests/test_investment_agent_acceptance.py -q --cov=utils.investment_agent_acceptance --cov=utils.investment_agent_acceptance_contracts --cov=utils.investment_agent_acceptance_evaluator --cov-report=term` | CLI **88%** / contracts 87% / evaluator 87% |
| `pyright utils/investment_agent_acceptance.py utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py tests/test_investment_agent_acceptance.py` | **0 errors, 0 warnings** |
| `ruff check --select F,I utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | **All checks passed** |
| `git diff --check -- utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | clean |
| 全仓 `python -m pytest -q` | **7365 passed, 1 failed, 6 skipped**；唯一失败 `test_web_tools.py::test_search_with_serper_requires_api_key` 为基线环境依赖失败（本机 `SERPER_API_KEY` 已设置），与基线字节一致，与本 fix 无关 |
| 全仓 `pyright` | 17 errors 全部位于 docling_processor/test_web_tools（既有 baseline）；目标文件 0 errors |
| 全目标集 `ruff --select F,I` | 唯一 I001 位于未修改的 `dayu/fins/cli_formatters.py`（既有 baseline） |

## Residuals

- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**；未读取密钥、
  未调用 SEC/Web/模型/网络/付费。
- 本 fix 未 commit / push / PR / 进入 Slice 4 或 Slice 5（历史时点：当时等待双路
  code re-review（DeepSeek + MiMo）与 Controller adjudication；现已由 Controller +
  Terra PASS/open H/M/L=0 闭合，MiM provider 未参与且未记 PASS）。
- `_seed_real_live_chain` 依赖 fixture 语料与固定 SEC accession，仅用于 deterministic
  回归，不声明 live freshness；不进入生产路径。
- 真实链测试中 `monkeypatch.undo()` 仅撤销 `_stub_runner_repository_closure` 的两个
  run 阶段 stub，恢复真实 `_price_material_repository_facts`/`_process_repository_stop_reason`。
- 全仓 pyright 17 条既有错误与 SERPER 环境失败为 baseline，不修白名单外文件。

## Final declaration

MRH-001、MRH-002、MRH-003、MRH-004 全部修复完成并验证，corrective MRH-001-remaining 与
RER-001 已应用，final artifact-only fix（MRH-004-regression）已应用并获 Controller +
Terra 双路验收：focused 220 全绿、目标文件 pyright 0 errors、ruff F/I 通过、diff-check
clean、CLI 行覆盖 88% ≥ 80%、精确 allowlist 仅两文件 + 四份 review artifacts。状态
**CONTROLLER + TERRA REVIEW PASS / READY FOR ACCEPTED COMMIT**；MiM provider 未参与
且未记为 PASS（free service ended, browser auth pending）。完成即停止，
不 commit/push/review/Slice4。
