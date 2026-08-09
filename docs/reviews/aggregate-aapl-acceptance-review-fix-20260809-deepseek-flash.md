# AAPL acceptance aggregate AGG-AAPL-001 — review fix artifact（DeepSeek V4 Flash）

- 日期：2026-08-09
- Gate：Controller-adjudicated **AGG-AAPL-001（Terra High）ACCEPTED / FIX REQUIRED**；非 controller，
  不启动 gateflow，不处理未接受/额外重构，不进入 commit/push/PR/review/live
- 分支：`feat/investment-agent-acceptance`
- Source review：`docs/reviews/aggregate-aapl-acceptance-deepreview-terra.md`（FAIL，open H/M/L = 1/0/0）
- Controller 裁决：`docs/reviews/aggregate-aapl-acceptance-review-adjudication-20260809-codex.md`
  （AGG-AAPL-001 **ACCEPTED / FIX REQUIRED**，open H/M/L = 1/0/0）
- 状态：**CLOSED / DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**
  （Terra 与 MiM corrective 双路 PASS，open H/M/L = 0/0/0；可进入 aggregate accepted commit）
- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**

## Changed files（精确 allowlist）

1. `utils/investment_agent_acceptance.py`（AGG-AAPL-001 生产修复）
2. `tests/test_investment_agent_acceptance.py`（AGG-AAPL-001 回归测试修复与四态新增）
3. 新增 `docs/reviews/aggregate-aapl-acceptance-review-fix-20260809-deepseek-flash.md`（本 artifact）

未触碰：`utils/investment_agent_acceptance_contracts.py`、`utils/investment_agent_acceptance_evaluator.py`、
全部 `dayu/`（含 formatter）、fixtures、README/runbook、plan 与其它 reviews。无新
flag/action/schema/marker，`AcceptancePlan` v2 与 `PhaseReceipt` v3 保持不变。
本 artifact 不修改 Controller adjudication 文件。

## AGG-AAPL-001 — exact pending handoff 可被独立 verify 提前发布 acceptance outputs（高）

### 根因

`run_acceptance()` 在 12 个 planned phases 通过且 quality review 仍为 exact pending
skeleton 时正确返回 `PENDING_MANUAL_REVIEW`/exit 3，不写 terminal/acceptance outputs；
但 public live `verify_acceptance()` 只验证 receipt prefix 后即调用 `_evaluate_live_plan()`
（其内部 strict 读取 quality review 仅做 malformed/secret/PII 检查，不要求完成），随后
无条件覆盖写 `acceptance-receipt.json`，`_evaluate_live_plan()` 还会发布
`source-inventory.json`。exact skeleton 与任何 `is_complete == False` 的部分填写状态
都被当作可正式 verify 的状态，破坏 pending handoff 的 receipt truth 与人工受理边界。

### 修复（生产）

`verify_acceptance()` live 分支在 `_load_and_validate_receipt_prefix()` 之后、
`_evaluate_live_plan()`/任何写入之前，调用新增 `_load_completed_quality_review(plan)`：

- 复用既有 `_read_quality_review_canonical()`（普通非 symlink 文件 → strict parse →
  canonical bytes → 整体 secret/home-path 扫描 → reviewer 元数据 PII 扫描）作为唯一
  quality strict ingress；
- 解析后的 `QualityReview.is_complete == False` 时抛稳定 `ContractError`
  （"live verify 要求人工质量复核已完成"），CLI `main()` 既有 `(ContractError, OSError)`
  分支映射为 exit 2；
- 拒绝路径不调用 evaluator，不创建/改写 `source-inventory.json` 与
  `acceptance-receipt.json`，既有 planned phase receipts 逐字节不变；
- `_evaluate_live_plan()` 签名增加 `quality: QualityReview` 参数，删除内部重复读取
  （单一 ingress truth：同一次 verify 只 strict 读取一次 quality review）；
- 完整人工 review 继续允许独立 verify：完整且达标 PASS、完整但不达标生成正式 FAIL
  receipt；`_verify_fixture()` 不读取 quality review，fixture verify 行为不变。

### 测试

- **重写** `test_slice2_live_verify_binds_plan_receipts_and_atomically_replaces_repeat_receipt`：
  原测试构造 pending `EvaluationResult` 并断言 pending verify 写 receipt，锁定了错误行为；
  改为完整 PASS review + 真实 `_seed_real_live_chain`，断言 live verify 绑定完整前缀、
  同 fixed clock 重复 verify 原子替换为相同 canonical receipt 字节、evaluator 恰好调用 2 次、
  planned receipts 字节不变、verify.json 不存在。
- **新增四态 public live verify 回归** `test_agg_aapl_001_live_verify_four_quality_states_public_boundary`
  （parametrize：exact_pending / partial_incomplete / complete_pass / complete_fail）：
  - exact_pending：12 planned 命令 handoff 后 verify → `ContractError`（match
    "人工质量复核"）、evaluator 调用 0 次、source-inventory/acceptance-receipt 不存在、
    planned receipts 字节快照不变；
  - partial_incomplete：`_fill_quality_review_as_non_exact`（strict-valid 但仅填
    reviewer_role）→ 同上全部 fail-closed 断言；
  - complete_pass（PASS/85）与 complete_fail（FAIL/50）：`monkeypatch.undo()` +
    `_seed_real_live_chain` + `_write_complete_quality_review` 后走真实仓储链，
    evaluator spy 恰好调用 1 次、verdict 正确、acceptance-receipt 字节等于真实 evaluator
    `canonical_bytes()`、source-inventory 存在、verify.json 不存在、planned receipts
    字节快照不变。
- **新增 CLI 边界** `test_agg_aapl_001_main_live_verify_pending_skeleton_exits_2`：
  exact pending skeleton 经 `main(("verify", "--plan", ..., "--fingerprint", ..., "--json"))`
  返回 exit 2，stdout 为空，stderr 含 "人工质量复核"，source-inventory/acceptance-receipt
  均不存在。

### 验证

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/test_investment_agent_acceptance.py -q` | **225 passed**（220 基线 + 四态 4 + CLI exit-2 1） |
| `python -m pytest tests/test_investment_agent_acceptance.py -q --cov=utils.investment_agent_acceptance --cov-report=term-missing` | CLI **88%** ≥ 80%；新增 `_load_completed_quality_review` 四行全部覆盖 |
| `pyright utils/investment_agent_acceptance.py utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py dayu/fins/cli_formatters.py tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py` | **0 errors, 0 warnings** |
| `ruff check --select F,I utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | **All checks passed** |
| `ruff check utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py`（default rules） | **All checks passed** |
| `python -m pytest tests/fins/test_cli_formatters_coverage.py tests/cli/test_research_template_command.py -q` | **225 passed**（owner formatter / research template 无回归） |
| `python -m utils.investment_agent_acceptance verify --fixture tests/fixtures/investment_agent/aapl_acceptance --json` | PASS（total_score 85，verdict PASS，fixture 不变） |
| `python -m utils.validate_handoff_docs --json` / `codex_review_gate --allow-waiting` / `dual_model_pipeline_check` | 全部 ok |
| `git diff --check -- utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | clean |
| 全仓 `python -m pytest -q` | **7374 passed, 1 failed, 6 skipped**；唯一失败 `test_web_tools.py::test_search_with_serper_requires_api_key` 为基线环境失败（本机代理 127.0.0.1:7897 不可达，ProxyError），stash 后基线与当前字节一致，与本 fix 无关 |
| 全仓 `pyright` | 17 errors 全部位于 docling_processor/test_web_tools（既有 baseline）；目标文件 0 errors，无新增/扩散 |

## Residuals

- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**；未读取密钥、
  未调用 SEC/Web/模型/网络/付费，无 commit/push/PR/review。
- 四态/重复 verify 测试依赖 `_seed_real_live_chain` 的 fixture 语料与固定 SEC accession，
  仅用于 deterministic 回归，不声明 live freshness，不进入生产路径。
- `monkeypatch.undo()` 仅用于完整 PASS/FAIL 变体以恢复真实仓储函数，撤销范围与既有
  handoff PASS/FAIL 测试一致（两个 run 阶段 stub）。
- 拒绝消息 "live verify 要求人工质量复核已完成" 为新的稳定 contract 文本，被四态测试与
  CLI exit-2 测试锁定；不在评估器中新增生命周期 gate。
- 全仓 pyright 17 条既有错误与 SERPER 环境失败为 baseline，不修白名单外文件。

## Final declaration

AGG-AAPL-001 已按 Controller 精确修复契约完整实施：live `verify_acceptance()` 在调用
evaluator、写 `source-inventory.json` 或写 `acceptance-receipt.json` 前单次 strict 读取
canonical quality review；`is_complete == False`（exact skeleton 与 partial incomplete）
稳定 `ContractError`/CLI exit 2、evaluator 0 次、两个 acceptance-owned 输出不创建/不改写、
planned receipts 字节不变；已解析 `QualityReview` 传入 live evaluator adapter 避免重复读；
完整 PASS/FAIL 继续正式 verify，fixture verify 不变；四态 public tests + CLI exit-2 锁定
evaluator 调用次数、两个 acceptance-owned 输出与 planned receipt bytes。focused 225
passed、focused coverage 88% ≥ 80%、目标文件 pyright 0 errors、Ruff F/I/default 通过、
owner 相关测试与 docs/fixture gates 通过、diff-check clean、精确 allowlist 仅两文件 + 本
artifact。状态 **FIX APPLIED / READY FOR CORRECTIVE DUAL RE-REVIEW**；完成即停止。

## Corrective closure（gate 更新）

- Terra corrective：`docs/reviews/aggregate-aapl-acceptance-corrective-rereview-terra.md` —
  **PASS**，open H/M/L = `0/0/0`；沿 `verify_acceptance -> _load_completed_quality_review ->
  _evaluate_live_plan -> evaluator/output` 真实调用链复核，225 focused、88% coverage、
  pyright 0 errors、Ruff/owner/fixture/docs gates 与 diff-check 全部通过。
- MiM corrective：`docs/reviews/aggregate-aapl-acceptance-corrective-rereview-mim.md` —
  **PASS**，open H/M/L = `0/0/0`；修复契约矩阵逐项对齐，exact_pending/partial_incomplete
  锁定 evaluator 0 次调用与两个 acceptance-owned 输出缺席，complete PASS/FAIL 与 fixture
  verify 无回归。
- 双路 corrective PASS / open0 后，本 artifact 状态更新为
  **CLOSED / DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**；aggregate closure 以
  `docs/reviews/aggregate-aapl-acceptance-closure-20260809-deepseek-flash.md` 为准，
  Controller 裁决保持 `aggregate-aapl-acceptance-review-adjudication-20260809-codex.md`。
