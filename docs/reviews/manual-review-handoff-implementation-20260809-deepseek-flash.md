# AAPL acceptance manual-review handoff — implementation artifact（DeepSeek V4 Flash）

- 日期：2026-08-09
- Gate：manual-review handoff production correction implementation（非 controller，非 review，不进入 commit/push/PR/live）
- 分支：`feat/investment-agent-acceptance`
- 基线：`4d91a16`（accepted plan baseline）
- 状态：**CONTROLLER + TERRA REVIEW PASS / READY FOR ACCEPTED COMMIT**（closure：Controller
  adjudication `docs/reviews/manual-review-handoff-code-adjudication-20260809-codex.md` 为
  CODE REVIEW ACCEPTED / READY FOR ACCEPTED COMMIT，Terra final artifact re-review
  `docs/reviews/manual-review-handoff-code-final-rereview-terra.md` 为 PASS/open H/M/L=0；
  历史 FAIL/fix/timepoint 状态全部保留于各轮 artifact，快照未重写。MiM provider 未参与
  本 gate 且不计为 PASS：MiMo Auto (free) 服务已结束、官方浏览器授权尚未完成。历史链见
  `docs/reviews/manual-review-handoff-review-fix-20260809-deepseek-flash.md`、
  `docs/reviews/manual-review-handoff-corrective-review-fix-20260809-deepseek-flash.md` 与
  `docs/reviews/manual-review-handoff-final-artifact-fix-20260809-deepseek-flash.md`）
- Slice 4 docs：本 correction 已 accepted，Slice 4 docs handoff-ready
- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**

## Changed files（精确 allowlist，仅两文件 + 本 artifact）

1. `utils/investment_agent_acceptance.py`（生产 correction）
2. `tests/test_investment_agent_acceptance.py`（状态机测试）
3. 新增 `docs/reviews/manual-review-handoff-implementation-20260809-deepseek-flash.md`（本 artifact）

工作树验证（2026-08-09，review 后复核）：`git status --short` 如实输出：

```text
 M tests/test_investment_agent_acceptance.py
 M utils/investment_agent_acceptance.py
?? docs/reviews/manual-review-handoff-code-review-terra.md
?? docs/reviews/manual-review-handoff-implementation-20260809-deepseek-flash.md
```

其中两处 `M` 为本实现 allowlist；`?? implementation-artifact` 为本 artifact（尚未纳入索引，
MRH-004 要求如实记录）；`?? code-review-terra.md` 为独立 code review worker 的 source
review 产物（非本实现创建，仅如实列示）。

## Implemented contract（与 accepted plan §4.2/§5.4/§7/§9 及 plan-fix 逐条对应）

### 1. prepare 行为不变

`prepare_acceptance()` 与 `_write_run_skeleton()` 未改动；仍调用 evaluator
`build_pending_quality_review(f"live-{plan.fingerprint[:16]}")` 生成唯一 null rubric 骨架，
`parse_quality_review` strict round-trip 后写 canonical JSON。无第二模板真源。

### 2. exact pending handoff（run 终态）

`run_acceptance()` 在全部 planned phases 通过后、`build_terminal_verify_command()` 派生前，
先 strict 读取磁盘 `quality-review.json` 并与同一 builder canonical bytes 精确比较：

- 新增 `_read_quality_review_canonical(plan)`：普通非 symlink 文件 → `parse_json_bytes`
  → `parse_quality_review` strict schema → `raw == canonical_json_bytes(payload)`
  （noncanonical 即 fail closed）→ `_assert_quality_review_sanitized` →
  `_assert_reviewer_metadata_sanitized`。
- 新增 `_assert_quality_review_sanitized(payload)`：复用 CLI 既有静态 pattern
  （`_STATIC_SECRET_FIELD_PATTERN`、`SECRET_KEY_PATTERN`、`_GOOGLE_API_KEY_PATTERN`、
  `_POSIX_HOME_PATH_PATTERN`、`_WINDOWS_HOME_PATH_PATTERN`），命中即 ContractError，
  不复制 evaluator rubric/阈值，不新建 schema/flag/action/marker。
- 新增 `_assert_reviewer_metadata_sanitized(review)`（MRH-001 + corrective MRH-001-remaining）：
  secret/home-path 已由整体载荷扫描覆盖全部字段；本函数补充 evaluator
  `_evaluate_reviewer_metadata` 独有的 canonical email 拒绝，统一覆盖
  reviewer_role、reviewer_id_label、全部 rubric item evidence_paths 与全部
  manual finding evidence_paths（任一含 `@` 即 ContractError），run 与独立 verify
  都在 terminal/evaluator/acceptance outputs 前 fail closed。
- 新增 `_quality_review_is_exact_pending(plan)`：`canonical_json_bytes(build_pending_quality_review(...))`
  与 round-trip 后 canonical bytes 精确比较。
- exact 时返回 `RunResult(succeeded=False, pending_manual_review=True, completed_phases=六阶段, stop_phase=None)`：
  - `succeeded` 恒为 `False`，不宣称 PASS；
  - 不派生/启动 terminal subprocess（terminal argv/wall check/process factory/Popen 均未触碰）；
  - 不创建 `phase-receipts/verify.json`、`source-inventory.json`、`acceptance-receipt.json`；
  - planned receipts 保持 passed 且字节稳定。
- `RunResult` 仅新增 `pending_manual_review: bool = False` 字段（默认值，向后兼容既有 4 参构造）。

### 3. main 的 run dispatch

`main()` 对 `pending_manual_review` 输出 canonical JSON（`_emit_json`），至少含
`status`/`verdict` 均表达 `PENDING_MANUAL_REVIEW`、`completed_phases` 与空 `terminal: null`，
返回退出码 3；其它 run 结果保持原 `succeeded`/exit 0/1 契约。

### 4. 独立 verify（terminal-absent 合法）

`verify_acceptance()` 与 `_load_and_validate_receipt_prefix()` 未改动：
完整 passed planned prefix + terminal absent 已是合法输入；PASS 与合法 FAIL 均
原子写 canonical `source-inventory.json` 与 normalized `acceptance-receipt.json`，
不创建/更新 phase receipt，不补写 terminal receipt。

### 5. fail-closed 时序

- `_evaluate_live_plan()` 把 quality strict ingress（`parse_quality_review(_read_quality_review_canonical(plan))`）
  提前到 source-inventory 发布之前：malformed/noncanonical/secret/PII quality 在任何
  acceptance-owned output 发布前即 ContractError。
- MRH-002：`source-inventory.json` 的原子发布移到 price material、contract、manifest、
  summary、report、research artifacts、runtime 与 `evaluate_acceptance` 全部成功之后；
  任一 repository/artifact/evaluator 异常时 source-inventory 与 acceptance-receipt 均
  保持不存在或 sentinel byte-identical，planned receipts 不变。
- malformed/unknown/missing/type/non-canonical quality → ContractError（fail closed）；
- secret/PII/home-path shape → `_assert_quality_review_sanitized` → ContractError（fail closed）；
- canonical email/PII（reviewer_role/reviewer_id_label 含 `@`）→
  `_assert_reviewer_metadata_sanitized` → ContractError（fail closed）；
- plan/receipt/repository/artifact drift → 既有 preflight/loader gate 不变，均在任何
  subprocess 或输出前拒绝。

### 6. strict-valid 非 exact 与 partial

- exact pending → handoff（上述）。
- strict-valid 但非 exact（人工预填/partial）→ 不触发 handoff shortcut，保持 terminal
  strict path：`run` 派生并启动 terminal verify；terminal 返回非零时按 passed-only
  契约不持久化 `verify.json`，run 以 `succeeded=False, stop_phase="verify"` 停止。
- 格式化/重排/非 canonical 载荷 → 因 `raw != canonical` 判为 fail closed，不得伪装
  成 prepare skeleton（严格 canonical bytes 是安全取舍）。

### 7. persisted terminal 与 no-resume

- `_execute_terminal_verify()` 改为 passed-only：仅 `result.status == "passed"` 时写
  精确单 record 的 `verify.json`；pending/failed/signal/timeout/whole-wall 耗尽
  terminal 一律不持久化。
- 旧 failed/signal/timeout/incomplete/non-passed persisted terminal 仍由 strict
  loader 在 evaluator 前拒绝（`_validate_terminal_receipt()` 不变），sentinel 输出与
  receipt bytes 不变。
- handoff 后同 plan 再次 `run` 仍在 process factory/Popen 前因已有 planned receipts
  拒绝（`_assert_no_existing_run_receipts()` 不变），无自动/隐式 resume。

### 8. 未触碰的冻结面

`utils/investment_agent_acceptance_contracts.py`、`utils/investment_agent_acceptance_evaluator.py`、
全部 `dayu/`、fixtures、README、plan 与其它 reviews 均未修改。无新 flag/action/
schema/marker/second builder/evaluator lifecycle gate。无 `Any`/`object`/`cast`/
`type-ignore`/`getattr`/`hasattr`/glue 新增；全部新增函数带完整中文 docstring。

## Tests（tests/test_investment_agent_acceptance.py）

### 适配既有状态机（旧 unconditional-terminal 语义 → 新 handoff 语义）

- `test_slice2_runner_executes_exact_allowlisted_order_and_writes_success_prefix`：
  运行前把 quality review 改为 strict-valid 非 exact 载荷以走 terminal 路径。
- `test_slice2_whole_wall_exhaustion_is_not_started_timeout[terminal]`：断言 terminal
  whole-wall 耗尽形成 timeout 但 verify.json 不持久化。
- `test_slice2_runner_nonzero_stops_at_every_exact_allowed_prefix[12-verify]`：
  terminal 失败不再持久化 verify.json（`assert not terminal_receipt.exists()`）。
- `test_slice2_persisted_nonpassed_terminal_is_rejected_without_resume`、
  `test_slice2_started_passed_receipt_requires_both_stream_hashes[verify]`、
  `test_slice2_runtime_evidence_includes_persisted_terminal_without_current_clock`、
  `test_slice3_real_parser_dispatch_locks_complete_aapl_command_contract`、
  `test_slice3_public_live_verify_rejects_untrusted_receipt_before_evaluator`：
  运行前填充非 exact review 以复现"人工填写后 run/verify"路径。

### 新增状态机测试（10 个用例 / 13 个 parametrize 变体）

| 用例 | 断言 |
|---|---|
| `test_manual_review_handoff_exact_pending_run_returns_pending_without_terminal` | run 返回 `pending_manual_review=True`/`succeeded=False`；Popen 计数 12（terminal=0）；verify.json/source-inventory/acceptance-receipt 均不存在；六 planned receipts 全 passed；loader 允许 terminal-absent |
| `test_manual_review_handoff_main_emits_canonical_pending_and_exit_3` | main exit 3；stdout 为 canonical JSON（`canonical_json_bytes` 重构一致）；`status`/`verdict`=PENDING_MANUAL_REVIEW；`terminal`=null；completed_phases 六阶段 |
| `test_manual_review_independent_verify_pass_and_fail_preserve_planned_receipts_without_terminal`（PASS 85 / FAIL 50） | 完整 strict-valid review（`is_complete=True`）→ 真实仓储链 + 真实 evaluator → verify 得 PASS/FAIL（MRH-003 修复：不再替换 `_evaluate_live_plan`）；`phase-receipts/` 字节快照前后不变；verify.json 不存在；acceptance-receipt 字节 = 真实 evaluator canonical bytes |
| `test_manual_review_bad_quality_run_fails_closed_without_handoff_or_terminal`（missing/malformed_schema/noncanonical/secret） | run 在 planned 12 命令后 ContractError；无 handoff/terminal/source-inventory/acceptance-receipt |
| `test_manual_review_verify_bad_quality_fails_closed_before_source_inventory`（malformed_schema/secret） | patch `acceptance_cli_module.evaluate_acceptance`（真实 consumer，MRH-003 修复）；`_evaluate_live_plan` 在 source-inventory 写入前拒绝；evaluator 调用计数 0；无任何 acceptance outputs |
| `test_manual_review_pii_reviewer_metadata_fails_closed_in_run_and_verify`（email/home-path × role/id/evidence_path，MRH-001） | canonical email 与 home-path PII 在 run 的 terminal 前 fail closed；无 handoff/terminal/acceptance outputs |
| `test_manual_review_pii_evidence_paths_fails_closed_in_run` / `..._in_verify`（rubric_evidence/finding_evidence，corrective MRH-001-remaining） | rubric item 与 manual finding 的 evidence_paths 含 email 时 run/verify 均在 terminal/evaluator/outputs 前 ContractError；Popen 计数 12、evaluator 调用计数 0，verify.json/source-inventory/acceptance-receipt 均不存在 |
| `test_manual_review_pii_reviewer_email_verify_fails_closed_before_outputs`（MRH-001） | canonical email reviewer label 在独立 verify 的 outputs 发布前 ContractError；evaluator 调用计数 0；无 source-inventory/acceptance-receipt/verify.json |
| `test_manual_review_live_verify_drift_fails_closed_before_any_output`（manifest/report/material/evaluator，MRH-002） | repository/artifact/evaluator drift 在任一 acceptance output 发布前 fail closed；source-inventory 与 acceptance-receipt 保持 sentinel byte-identical；planned receipts 字节快照不变；evaluator 调用计数 0（evaluator 分支以抛异常注入） |
| `test_manual_review_nonexact_partial_review_keeps_terminal_strict_path` | partial 预填不触发 handoff shortcut；terminal 被启动（Popen 13）；terminal exit 3 → 不持久化 verify.json；`pending_manual_review=False` |
| `test_manual_review_same_plan_rerun_after_handoff_is_rejected_before_popen` | handoff 后同 plan rerun 在 process factory/Popen 前拒绝；receipt bytes 快照不变 |

旧 nonpassed terminal 拒绝与 same-plan no-resume 继续由既有
`test_slice2_persisted_nonpassed_terminal_is_rejected_without_resume` 与
`test_slice3_public_live_verify_rejects_untrusted_receipt_before_evaluator`、
`test_slice3_existing_receipt_blocks_same_plan_rerun_and_requires_fresh_root` 覆盖。

## Validation（全部命令与结果）

工作区状态（final artifact fix 后最终）：`git status --short` 如实输出两处 `M`
（`tests/test_investment_agent_acceptance.py`、`utils/investment_agent_acceptance.py`）与
未跟踪项 `?? docs/reviews/manual-review-handoff-code-final-rereview-terra.md`、
`?? docs/reviews/manual-review-handoff-code-rereview-terra.md`、
`?? docs/reviews/manual-review-handoff-code-review-terra.md`、
`?? docs/reviews/manual-review-handoff-implementation-20260809-deepseek-flash.md`、
`?? docs/reviews/manual-review-handoff-review-fix-20260809-deepseek-flash.md`、
`?? docs/reviews/manual-review-handoff-corrective-review-fix-20260809-deepseek-flash.md`、
`?? docs/reviews/manual-review-handoff-final-artifact-fix-20260809-deepseek-flash.md`
（MRH-004 及其 corrective MRH-004-regression：本 artifact 及 Terra final re-review /
Terra re-review / source review / fix / corrective / final-artifact-fix 产物均为
未跟踪状态，如实记录）。

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/test_investment_agent_acceptance.py -q` | **220 passed**（216 + 4 新增 corrective evidence-path email 用例） |
| `python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py tests/cli/test_research_template_command.py -q` | **445 passed** |
| `python -m pytest tests/test_investment_agent_acceptance.py -q --cov=utils.investment_agent_acceptance --cov=utils.investment_agent_acceptance_contracts --cov=utils.investment_agent_acceptance_evaluator --cov-report=term` | CLI **88%** / contracts 87% / evaluator 87%（目标单文件 ≥80% 达成） |
| `pyright utils/investment_agent_acceptance.py utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py tests/test_investment_agent_acceptance.py` | **0 errors, 0 warnings** |
| `ruff check --select F,I utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | **All checks passed** |
| `git diff --check -- utils/investment_agent_acceptance.py tests/test_investment_agent_acceptance.py` | clean（无 whitespace/EOF 问题） |
| 全仓 `python -m pytest -q` | **7365 passed, 1 failed, 6 skipped**；唯一失败 `tests/engine/test_web_tools.py::test_search_with_serper_requires_api_key` 为基线环境依赖失败：本机 `SERPER_API_KEY` 已设置而该测试断言缺失即抛错；该文件与基线字节一致（`git show HEAD:...` SHA-256 与工作树相同），与本 correction 无关 |
| 全仓 `pyright` | **17 errors**，全部位于 `dayu/engine/processors/docling_processor.py`、`tests/engine/test_docling_processor_helpers.py`、`tests/engine/test_web_tools.py`（docling_core 外部依赖漂移），确认为既有 baseline，目标文件 0 errors，白名单外文件不修 |
| `ruff check --select F,I` 全目标集 | 唯一 I001 位于未修改的 `dayu/fins/cli_formatters.py`（既有基线问题）；两个修改文件通过 |

## Docs decision

- 本次为两文件 production correction + 本 implementation artifact，不触发任何 README 更新：
  未修改 `dayu/`、`dayu/cli/`、`dayu/render/`、`utils/analyze_tool_trace.py`、配置入口或
  分层装配，根 README / 包 README / tests README 职责均不受影响。
- Slice 4 操作文档（`docs/acceptance/investment-agent-aapl.md`、根 README、tests README）
  本 correction 已 accepted，Slice 4 docs 按原三文件 allowlist handoff-ready。
- `docs/reviews/` 既有 review artifacts 未修改。

## Residuals

- Slice 5 / live：**LIVE AUTHORIZATION REQUIRED / NOT AUTHORIZED / NOT RUN**；未读取密钥、
  未调用 SEC/Web/模型/网络/付费。
- 本 correction 与 review fix 均未 commit / push / PR / 进入 Slice 4 或 Slice 5（历史时点：
  当时等待双路 code re-review（DeepSeek + MiMo）与 Controller adjudication；现已由
  Controller + Terra PASS/open H/M/L=0 闭合，MiM provider 未参与且未记 PASS）。
- 严格 canonical-bytes 判定有意把仅格式化/重排的 skeleton 归为 fail closed；这是
  plan-fix 已接受的防伪装安全取舍。
- non-exact partial 预填在 run 前会走 terminal strict path（terminal 被启动并评估），
  由 operator 按 runbook 改为独立 verify；plan §8.1 恢复合同不变。
- 真实 live 仓储链测试（`_seed_real_live_chain`）依赖 fixture 语料与固定 accession；
  仅用于 deterministic 回归，不声明 live freshness。
- 全仓 pyright 17 条既有错误与 `test_web_tools.py::test_search_with_serper_requires_api_key`
  环境失败为 baseline，不修白名单外文件。

## Final declaration

初始实现、MRH-001..004 定向修复、corrective MRH-001-remaining/RER-001 与 final
artifact-only fix（MRH-004-regression）均已完成并获 Controller + Terra 双路验收：
focused 测试 220 全绿、目标文件 pyright 0 errors、ruff F/I 通过、diff-check clean、
CLI 行覆盖 88% ≥ 80%、精确 allowlist 仅两文件 + 四份 review artifacts。状态
**CONTROLLER + TERRA REVIEW PASS / READY FOR ACCEPTED COMMIT**；MiM provider 未参与
且未记为 PASS（free service ended, browser auth pending）。完成即停止，
不 commit/push/review/Slice4。
