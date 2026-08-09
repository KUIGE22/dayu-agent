# AAPL acceptance Slice 2 final corrective code re-review

- Review mode: current uncommitted workspace changes, read-only final corrective re-review
- Repository: `/Users/wsk/workspace/dayu-agent`
- Branch: `feat/investment-agent-acceptance`
- Review base / HEAD: `1c7e16160b23704558508e9c25522a116d67ad84`
- Reviewed at: 2026-08-09 14:41 CST
- Verdict: **FAIL**
- Open findings: **High 3 / Medium 2 / Low 1**

## Findings

### H-1 — price material 缺少 `filing_date`，真实 process repository closure 确定性抛错且不写失败 receipt

- Entry/function: `build_phase_specs()` → owner `upload_material` → `_owner_semantic_stop_reason()` → `_process_repository_stop_reason()` → `build_source_inventory_from_repositories()` → `_source_document_from_owner()`
- Files/lines: `utils/investment_agent_acceptance.py:1312-1328, 2220-2258, 3393-3426`; `dayu/fins/pipelines/sec_upload_workflow.py:400-408`; `dayu/fins/pipelines/docling_upload_service.py:476-511`; `utils/investment_agent_acceptance_evaluator.py:2063-2092`
- Trigger: 按 canonical plan 执行 price snapshot material import。builder 只传 `--report-date <market-date>`，不传 `--filing-date`；随后 process 成功并进入 repository truth closure。
- Actual branch: owner upload 把 `filing_date=None` 与 `report_date=<market-date>` 原样放入 `base_meta`；`_build_upsert_meta()` 仅复制该 mapping，不提供日期回退。process closure 枚举该 material 后，`_source_document_from_owner()` 对 filing/material 两类文档都无条件调用 `_owner_required_date(source, "filing_date", ...)`，因此抛 `ContractError`。`_execute_phase()` 只捕获 `_OwnerOutputError`，没有捕获此处明确声明可抛的 `ContractError`，所以甚至来不及 append record/write `process.json`。
- Expected: canonical price material 应能以 plan 规定的 market/report date 进入 source inventory；若 repository closure 失败，phase 至少应持久化真实的 failed record 与静态 stop reason 后停止。
- Actual: live Slice 2 无法完成 process phase；异常越过 phase receipt 写入，破坏 repository closure 与可审计失败语义。
- Direct evidence:
  - canonical argv 在 `investment_agent_acceptance.py:1324-1325` 只有 `--report-date`；
  - owner workflow 在 `sec_upload_workflow.py:400-408` 同时写入 `filing_date`/`report_date`，前者保持 `None`；
  - `_build_upsert_meta()` 在 `docling_upload_service.py:503-511` 仅复制并补 ingestion 字段；
  - 本地纯函数复现：以 material meta `{"document_id": ..., "report_date": "2025-01-15"}` 调用 `_source_document_from_owner()`，得到 `ContractError: source_meta[material-aapl-price-snapshot] 缺少 filing_date`；
  - `investment_agent_acceptance.py:2244` 的唯一 semantic parse catch 是 `_OwnerOutputError`。
- Impact: 这是 canonical live happy path 的确定性阻断，不依赖网络返回差异；当前实现不能声称 Slice 2 可执行验收闭环。
- Recommended fix: 在 plan 真源中明确 material 日期语义并统一实现。优先让 material inventory 使用 required `report_date`，仅 filing source 要求 `filing_date`；若决定命令同时传 `--filing-date`，需同步 accepted plan/argv/fingerprint tests。另把 repository `ContractError` 收敛为真实 failed `CommandRecord`，保留 evidence/stream digests 后原子写 receipt。
- Fix risk: 日期字段会参与 source sorting/window/freshness，不能用全局 `report_date -> filing_date` 回退污染 filing 语义；需添加真实 Fs repository 的 material-only integration test。

### H-2 — v3 receipt reload 未把 evidence 与 phase/argv/domain 绑定，篡改后的 passed receipt 可进入 evaluator

- Entry/function: `parse_phase_receipt()` / `_parse_command_record()` / `_load_planned_receipt_prefix()` / `_validate_record_argv_prefix()` / `_receipt_discovery()` / `_evaluate_live_plan()`
- Files/lines: `utils/investment_agent_acceptance_contracts.py:1235-1267, 2785-2848, 3379-3434, 3491-3515, 4089-4131`; `utils/investment_agent_acceptance.py:3463-3496, 3681-3726, 3776-3805, 4084-4115`
- Trigger: canonical phase receipt bytes被本地篡改后重新 canonicalize，例如：
  1. passed process record 的 `evidence=null`；
  2. download phase 的 record 换成 material/process evidence；
  3. passed download evidence 保留 usable rows，但 `owner_status="cancelled"` 或 `summary.failed>0`；
  4. evidence 的 forms/start/end 与对应 planned argv 不一致，或某 record 携带另一条 download command 的窗口。
- Actual branch: contract parser 只解析 `CommandEvidence | None` 的 union shape 和通用 lifecycle；`_load_planned_receipt_prefix()` 只闭合 phase identity、record count/order、safe argv/digest、时间和聚合 status；没有 phase-specific evidence validator。`_receipt_discovery()` 仅要求 record passed 且 evidence 是 download，再聚合 downloaded/skipped rows；不重放 `owner_status/failed/forms/start/end/row-in-window` semantic gates。material/process persisted evidence 在 live evaluation 中不再消费。
- Expected: receipt 是不可信持久化输入。每个 passed domain command 必须有与 phase 和该条 raw argv 精确绑定的 evidence，并在 reload 时重放运行期 hard-stop；非 domain phase/terminal 必须为 null。process/material repository evidence 也必须参与后续真源闭环，而不是只在生成 receipt 的同一进程中检查一次。
- Actual: v3 提供了 per-command envelope，却没有 verification-time domain authenticity；攻击者或磁盘损坏可把运行期本会停止的状态重写成 canonical passed receipt，verify 仍继续。
- Direct evidence:
  - `_parse_command_evidence()` 在 contracts `3491-3515` 明确允许 `None` 和任意三种 union member；
  - `_validate_command_record_status()` 在 `4089-4131` 只检查退出/stream lifecycle，不检查 evidence；
  - `_validate_record_argv_prefix()` 在 CLI `3797-3805` 只比较 index/safe argv/digest；
  - `_receipt_discovery()` 在 `3476-3496` 未检查 `owner_status`、summary、canonical forms、start/end；
  - 独立构造/parse 复现确认 passed download + cancelled evidence 和 passed process + null evidence 均被 strict parser 接受；
  - 现有 round-trip test 只验证正确 union 样例和字段 schema mutation，没有验证 phase/evidence 错配或 domain tamper。
- Impact: DS H-1/H-2 与 corrective plan 的 receipt-derived discovery、per-command evidence、material/process semantic closure 只是生成时闭合，没有跨持久化边界闭合；审计证据可被伪造并影响 freshness/acceptance 结论。
- Recommended fix: 在 `_load_planned_receipt_prefix()` 增加 phase-aware evidence validator：download 的每个 passed record 必须精确一个 `DownloadCommandEvidence` 并绑定该命令 forms/start/end；material/process 分别必须精确对应 evidence；write/preflight/validations/terminal 必须 null。重放 `_owner_semantic_stop_reason()` 的纯语义部分；repository 部分用 persisted identity 与当前 repository truth 重验。为上述四类 canonical tamper 添加 verify rejection tests。
- Fix risk: 不要直接调用会写 `source-inventory.json` 的路径来做 loader 验证；应拆出纯 validator，避免 verify load 产生额外副作用或 circular trust。

### H-3 — pre-persistence stream summary 会把 Authorization/Cookie/API-key 原文写入 phase receipt

- Entry/function: `_command_record()` → `_stream_summary()` → `_redact_cli_text()`
- Files/lines: `utils/investment_agent_acceptance.py:2031-2044, 2608-2652`; `dayu/redaction.py:28-37`
- Trigger: owner stdout prefix/noise、structure reject line 或任意 stderr 包含 `Authorization: Bearer ...`、`Cookie: ...`、`Set-Cookie: ...`、`X-API-Key: ...`/`API_KEY=...` 等非 `sk-`/`AIza` 形状。
- Actual branch: `_stream_summary()` 选取原始行 fragment，只调用共享 `SECRET_KEY_PATTERN` 和 home-path mask，然后把 fragment 放入 command record。共享 pattern 只覆盖 `sk-...` 与 `AIza...`；它不覆盖 header/cookie/key-value token。evaluator 的后置 sensitive-shape gate 即使最终 FAIL，也发生在 secret 已写盘之后。
- Expected: plan §7 要求 receipt 只持久化静态分类和有界、静态脱敏摘要；Authorization/cookie/secret/provider body 从不进入持久化 evidence。
- Actual: secret value 以可恢复明文进入 `phase-receipts/*.json`。
- Direct evidence: 本地调用 `_stream_summary(..., category="stderr_present")` 分别得到：
  - `fragment=Authorization: Bearer test-secret-token-123`
  - `fragment=Cookie: session=test-cookie-secret-123`
  - `fragment=X-API-Key: test-api-secret-123`
  `dayu/redaction.py:28-31` 的实际 regex 与该结果一致。本结论在未读取并行 reviewer artifact 的前提下独立复现。
- Impact: 高严重度凭据泄漏；receipt 是长期审计产物，后置拒绝不能撤销落盘。
- Recommended fix: 最稳妥方案是不持久化 raw fragment，只记录 category/line/digest。若必须保留 fragment，增加不枚举环境值的静态 header/key-value sanitizer，至少覆盖 Authorization/Proxy-Authorization、Cookie/Set-Cookie、常见 `*_API_KEY|*_TOKEN|*_SECRET|PASSWORD` assignments，并在截断前替换完整 value。
- Fix risk: 过宽 regex 可能误删普通诊断，过窄 regex 会继续泄漏；用参数化 tests 同时覆盖 stdout prefix、structure reject、stderr 和 Unicode/超长输入。

### M-1 — timeout 丢弃已产生的 stdout/stderr，receipt 把真实非空 stream 伪记为空流 SHA

- Entry/function: `_execute_command()` → `_terminate_timed_out_process()` → `_command_record()`
- File/lines: `utils/investment_agent_acceptance.py:2378-2424, 2477-2540, 2608-2613`
- Trigger: child 在超时前已输出内容，`communicate(timeout=...)` 抛出的 `TimeoutExpired` 含 partial `output`/`stderr`，随后 terminate 或 kill 成功。
- Actual branch: exception 未绑定为变量；termination helper 只调用 `wait()`，所有路径固定返回 `stdout=b""`, `stderr=b""`，既不保留 exception partial bytes，也不在终止后 `communicate()` drain pipes。之后 record 为两个空 byte string 计算 SHA。
- Expected: 已启动 command 的 receipt 应记录完整可取得 raw stream digest；timeout 可标 partial，但不能把已观察到的非空字节伪造成空流。
- Actual: audit digest 与真实执行不符，且 pipe 未 drain；失败诊断丢失。
- Direct evidence: `investment_agent_acceptance.py:2420-2424` 丢弃 exception payload；`2495-2540` 四条返回路径全部硬编码空 streams。fake process 在 `tests/test_investment_agent_acceptance.py:579-594` 抛不带 partial output 的 `TimeoutExpired`，因此 150 个 focused tests 未覆盖该情况。
- Impact: timeout 是最需要 forensic evidence 的路径，当前 receipt 会提供错误的摘要事实。
- Recommended fix: 捕获 `TimeoutExpired` 的 partial bytes，terminate/kill 后通过 bounded `communicate()` drain，再按 Python cumulative-output 语义去重/选择最终 bytes；termination_unconfirmed 也至少保留已捕获 partial bytes。添加 partial stdout/stderr 的 terminate、kill 和 unconfirmed tests。
- Fix risk: 重复拼接可能使 digest 也错误；测试应模拟 `communicate()` 第二次返回 cumulative 与 incremental 两种 adapter 行为，协议只选择一种明确语义。

### M-2 — 首次 terminal verify 未计入 evaluator 的 actual wall/phase receipts，且 Popen 启动耗时未从 child timeout 扣除

- Entry/function: `_load_and_validate_receipt_prefix()` / `_validate_terminal_receipt()` / `_evaluate_live_plan()` / `_execute_command()`
- File/lines: `utils/investment_agent_acceptance.py:2200-2216, 2324-2340, 2378-2419, 3619-3648, 3729-3773, 4167-4174`
- Trigger: outer `run` 已生成成功 `verify.json`，随后 terminal 有非零耗时；或 `Popen.start()` 本身耗时明显而 child 接近 whole-run deadline。
- Actual branch: `_validate_terminal_receipt()` 解析并验证 terminal 后丢弃对象，loader 只返回六个 planned receipts；`actual_wall_seconds` 因而止于 validations receipt，`phase_receipts`/`acceptance_owned_outputs` 也排除首次 terminal。另一方面 phase 在 Popen 前计算 remaining，`_execute_command()` 完成 Popen 后仍把旧 remaining 全量传给 `communicate()`。
- Expected: accepted plan §7/§8.1 明确要求 full-run actual wall 从首实际 phase/record 到 terminal/last phase；首次 terminal verify 属于自动链。child timeout 应基于 Popen 后的真实剩余预算，不能允许启动开销造成 ceiling overshoot。
- Actual: evaluator 系统性低估 outer run，且慢进程创建可越过 hard ceiling；虽然 outer loop事后会停止，receipt/evaluator 的上限事实不精确。
- Direct evidence: loader 在 `3645-3648` 调用 terminal validator但只返回 planned tuple；terminal validator返回 `None`；`4167-4174` 用 planned tuple 的首尾；`2201-2215`/`2325-2339` 在调用 `_execute_command()` 前计算剩余，而 `2405-2419` 不重新扣除 start 时长。
- Impact: budget/wall evaluator 真源与 accepted timing contract 不一致；接近上限的 run 可能被错误报告为未超限。
- Recommended fix: 返回一个明确的 `validated_terminal_receipt` 或全链 runtime span，outer-run verify 使用 terminal ended_at；独立人工 verify 则保持 fixed phase receipts 不变但继续读取首次 terminal。process start 后用同一 monotonic deadline重算 communicate timeout。
- Fix risk: 不要把后续独立 verify 时间重复计入 original automated run；应区分 persisted first terminal receipt 与当前 verification timestamp。

### L-1 — accepted MiMo L-4 未闭合：Git object-id regex 仍是第二份本地真源

- Entry/function: `GitRepositoryStateProvider.read()`
- File/lines: `utils/investment_agent_acceptance.py:1022`; `utils/investment_agent_acceptance_contracts.py:39, 4739`
- Trigger: object-id policy今后扩展或收窄时只修改 contracts 常量。
- Actual branch: CLI 仍调用本地 `re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head)`，没有导入/复用 `GIT_OBJECT_ID_PATTERN`；contracts 使用另一写法 `^[0-9a-f]{40}(?:[0-9a-f]{24})?$`。
- Expected: `plan-fix-20260809-121500-codex.md` 明确接受 MiMo L-4 并要求复用 contracts regex。
- Actual: 两份目前等价但独立的 policy truth 仍存在；review-fix artifact 对该项的 closed 声明不准确。
- Impact: 当前行为未立即出错，未来 drift 风险低但真实存在。
- Recommended fix: 导出并直接复用 contracts validator/constant，或让 repository provider调用唯一 `_require_git_object_id` 边界。
- Fix risk: 很低；保持现有 40/64 lowercase 行为并补单一真源测试。

## Original findings and plan-observation closure

| Source item | Final state | Evidence / remaining gap |
|---|---|---|
| DeepSeek H-1 receipt-derived freshness | **PARTIAL / REOPENED by H-2** | inventory fallback 已删除，discovery 来自 receipt；但 reload 未重验 download semantic/window binding，可由篡改 receipt 注入。 |
| DeepSeek H-2 per-command phase receipt | **PARTIAL / REOPENED by H-2** | v3 records、digests、prefix lifecycle已实现；evidence 未 phase/argv/domain 绑定。 |
| DeepSeek M-1 + MiMo M-7 fixture lock/cleanup | **CLOSED with documented force-kill residual** | repo-private lock、owner metadata、stale diagnosis 与 cleanup precedence tests 存在；本轮未发现可复现的新同级缺陷。 |
| DeepSeek M-2 not-started timeout | **CLOSED** | first-command/terminal exhaustion 均为 timeout/not_started/partial，fake clock tests 覆盖。 |
| DeepSeek M-3 + MiMo M-4 stream digest/summary | **PARTIAL / REOPENED by H-3 and M-1** | SHA/bounded summary fields已加；pre-persistence sanitizer 不完整，timeout 又丢 partial bytes并写空 SHA。 |
| DeepSeek M-4 material SHA closure | **PARTIAL / REOPENED by H-1** | material document id/source fingerprint/primary SHA closure 已实现；canonical material 因缺 filing_date 不能进入 inventory。 |
| DeepSeek M-5 untracked dirty | **REJECTED as planned / CLOSED** | 保持 fail-closed dirty policy；无规避。 |
| DeepSeek L-1 source inventory file | **CLOSED** | live evaluator 从 repository 构建、strict round-trip 并 atomic write-or-assert-same。 |
| DeepSeek L-2 / MiMo L-3 forms truth | **CLOSED** | `_WINDOW_FORMS` 驱动 builder/window/evidence，production `normalize_form` 被复用。 |
| DeepSeek L-3 / MiMo L-5 magic fixture values | **CLOSED** | 已迁到具名 constants/evaluator builders。 |
| DeepSeek L-4 temp residue | **REJECTED as planned / CLOSED** | 未知 receipt fail closed 属恢复策略。 |
| DeepSeek L-5 concrete composition dependencies | **REJECTED as planned / CLOSED** | composition root保留 owner Fs implementations；本轮未发现额外业务逻辑外泄。 |
| MiMo H-1 evaluator scoring truth | **CLOSED** | live/fixture contract与 rubric builders已迁 evaluator；CLI 不再维护评分常量真源。 |
| MiMo M-2 unexpected exception redaction | **PARTIAL / REOPENED by H-3** | main 异常路径静态收敛，无 traceback；但 receipt stream fragment 的落盘前 sanitizer 更窄。 |
| MiMo M-3 Popen cwd/stdin/shell/env | **CLOSED, timing caveat M-2** | repo cwd、DEVNULL、shell false、explicit copied env 均锁定；whole-run deadline 在 start 后未重算。 |
| MiMo M-5/M-6 timeout tests | **CLOSED for original cases** | exhaustion 与 terminate/kill OSError tests 存在；partial-output timeout 新缺口见 M-1。 |
| MiMo L-1 `--flag=/abs` | **CLOSED** | safe argv 右值绝对路径拒绝已覆盖。 |
| MiMo L-2 parser normalization | **CLOSED on live canonical-byte boundary** | parser内部仍 normalize，但 plan/receipt 文件 canonical-byte equality拒绝被篡改排序/空白；未升级为本轮 finding。 |
| MiMo L-4 Git regex | **OPEN / L-1** | 明确 accepted 的 single-truth fix 未实现。 |
| MiMo L-6 actual wall | **PARTIAL / REOPENED by M-2** | planned phases改为端到端首尾，但遗漏 persisted first terminal。 |
| MiMo L-7 dead `--json` | **CLOSED** | acceptance CLI prepare/run/verify contract 与 owner invocations显式消费既定 output mode；无 dead dataclass flag。 |
| DS F-001/G-003 process six-section grammar | **CLOSED** | 六节唯一有序、source_kind/status由 header派生、行内只信 document_id；repository quality 为真源。 |
| DS F-002 + MiMo owner stdout prefix concern | **CLOSED except H-3 sanitizer** | unique title anchor、static env、prefix summary实现；raw fragment落盘防泄漏不足。 |
| DS F-003/G-001/G-002 material action/status state machine | **CLOSED at parse/run time; persistence gap H-2** | create/update 与 ok/skipped 正交，delete/unknown拒绝；reload 不重放状态机。 |
| DS F-004/MiMo H-2 trusted structure vs opaque tail | **CLOSED** | 固定标题/summary/section，reason/message/file rows不进入结构证据。 |
| DS F-005 material TODO branch | **CLOSED at parse/run time; persistence gap H-2** | TODO 与 counts 互斥且 semantic stop；tampered persisted process evidence 不重验。 |
| DS F-006 canonical form normalization | **CLOSED** | production normalizer为唯一 canonicalizer。 |
| DS F-007 accession/source invariant | **CLOSED at generated-evidence path; persistence gap H-2** | fresh run/SEC accession checks存在，但 receipt reload 可绕过 per-command window/status重验。 |
| DS F-008 terminal receipt ownership | **PARTIAL / M-2** | outer run写固定 terminal、独立 verify不改 phase receipts；runtime span/evaluator outputs遗漏 terminal。 |
| MiMo M-1 usable download sections | **CLOSED at runtime; persistence gap H-2** | only downloaded/skipped、failed semantic stop、duplicate IDs拒绝；reload只保留其中一部分检查。 |
| MiMo M-2 closed evidence union | **STRUCTURALLY CLOSED / SEMANTICALLY OPEN H-2** | discriminator/schema严格，新增成员需 bump；phase membership/requiredness不严格。 |
| MiMo M-3 bounded stdout summary | **OPEN / H-3** | clean null/prefix/reject category实现，但静态 fragment sanitizer不足。 |
| MiMo corrective L-1 empty form | **CLOSED** | categorized structure rejection和行号测试存在。 |
| MiMo corrective L-2 upload sparse grammar | **CLOSED** | 必需五行、可选行顺序、files header/opaque rows均有 positive/negative tests。 |

## Architecture and coupling pass

- Evaluator remains the scoring/hard-gate truth; no new score/rubric duplication was found in the CLI.
- Owner formatter production delta is exactly one output line in `_format_download_result()` (`- status: ...`), with order/uniqueness tests for `ok` and `cancelled`; no acceptance-specific formatter branch was introduced.
- Repository protocols remain the read boundary and owner Fs implementations are constructed at composition roots. H-1 is a schema/semantic mismatch at that boundary, not a recommendation to add another repository abstraction.
- No `Any`, `object`, `cast`, `# type: ignore`, `getattr`, `hasattr`, or loose glue-layer escape was found in the changed acceptance utilities/tests by focused search. Existing owner modules outside the review delta retain their pre-existing broad types.

## Verification evidence

Commands were read-only and performed without live/network/model/paid actions:

```text
git diff --check
PASS

source .venv/bin/activate && python -m pytest \
  tests/test_investment_agent_acceptance.py \
  tests/fins/test_cli_formatters_coverage.py \
  -q -p no:randomly
150 passed in 2.59s

source .venv/bin/activate && pyright \
  dayu/fins/cli_formatters.py \
  tests/fins/test_cli_formatters_coverage.py \
  tests/test_investment_agent_acceptance.py \
  utils/investment_agent_acceptance_contracts.py \
  utils/investment_agent_acceptance_evaluator.py \
  utils/investment_agent_acceptance.py
0 errors, 0 warnings, 0 informations

source .venv/bin/activate && ruff check <same six files>
All checks passed!
```

Green gates are genuine but insufficient: the focused tests use synthetic metadata that supplies material `filing_date`, timeout fakes never attach partial output, v3 tests mutate schema rather than phase/domain association, and wall tests do not assert terminal inclusion.

## Scope and exclusions

Included production/test delta:

- `dayu/fins/cli_formatters.py`
- `utils/investment_agent_acceptance.py` (untracked review target)
- `utils/investment_agent_acceptance_contracts.py`
- `utils/investment_agent_acceptance_evaluator.py`
- `tests/fins/test_cli_formatters_coverage.py`
- `tests/test_investment_agent_acceptance.py`

Required context fully reviewed:

- root `AGENTS.md`
- accepted plan `docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- source code reviews `code-review-20260809-114000-deepseek.md`, `code-review-20260809-114001-mimo.md`
- plan fixes `plan-fix-20260809-121500-codex.md`, `plan-fix-20260809-124500-codex.md`, `plan-fix-20260809-131500-codex.md`
- final plan reviews `plan-review-20260809-133000-deepseek.md`, `plan-review-20260809-133001-mimo.md`
- implementation/adjudication/fix artifacts `slice-2-aapl-acceptance-implementation-20260809-113054-codex.md`, `code-review-adjudication-20260809-141932-codex.md`, `slice-2-aapl-acceptance-review-fix-20260809-141932-codex.md`

Excluded: live execution, network, external services, paid model calls, commit/push, and unrelated workspace changes. No production/test/plan/existing artifact was modified. A parallel reviewer artifact appeared in the workspace after this review had independently reproduced H-3; it was not used as evidence or copied.

## Open questions

None required to establish the verdict. The implementation must first choose and document the material date truth for H-1; that is a corrective design decision, not a reason to accept the current code.

## Residual risks

- No live run was authorized, so owner CLIs were not exercised against external SEC/model services. H-1 is nonetheless established by deterministic argv and local repository code paths.
- Force-kill between filesystem operations can still leave repo-private lock/staging artifacts as already documented operational recovery residuals.
- Full-repository pytest was not rerun in this independent pass; the targeted 150 tests plus exact-file Pyright/Ruff passed. This does not mitigate the six open findings above.

## Final decision

**FAIL.** The current diff must not advance to acceptance/merge while any High finding is open. H-1 blocks the canonical live path, H-2 breaks the persisted audit boundary, and H-3 can persist credentials before the evaluator rejects them.
