# Slice 3 AAPL acceptance integration implementation

- 日期：2026-08-09
- Gate：Gateflow Slice 3 implementation
- Work unit：`investment-agent-aapl-acceptance`
- Baseline：`46446ef88979668a14b4a898e16c62fa260a5611`
- Accepted plan：`docs/plans/2026-08-09-investment-agent-aapl-acceptance.md`
- Plan acceptance：`docs/reviews/plan-acceptance-20260809-slice3-resume-codex.md`
- 状态：**DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**
- Live / paid：**NOT AUTHORIZED / NOT RUN**

## Scope and non-goals

本 Slice 只补现有生产边界的 tests-only integration 与恢复事实，不修改 production、fixture、README 或 accepted plan。精确变更文件为：

1. `tests/test_investment_agent_acceptance.py`
2. `tests/cli/test_research_template_command.py`
3. `docs/reviews/slice-3-aapl-acceptance-integration-implementation-20260809-codex.md`
4. `docs/reviews/slice-3-aapl-acceptance-review-adjudication-20260809-codex.md`
5. `docs/reviews/slice-3-aapl-acceptance-review-fix-20260809-codex.md`

未新增 CLI action/flag、compatibility wrapper、authorization marker、resume schema、receipt cleanup workaround 或 evaluator lifecycle gate；未进入 Slice 4/5，未执行 SEC、Web、DeepSeek、MiMo、网络或付费调用。

## Implemented plan items

### 1. Independent golden contract and real owner parser/dispatch

- 测试内独立、显式列出 12 条 planned argv 加 1 条 terminal argv；期望不读取 `phase_specs`，也不调用 `build_phase_specs()` / `build_terminal_verify_command()`。Production plan 与 runner calls 都必须逐 token 等于同一外部 golden contract。
- Golden 精确锁定三组 AAPL forms/windows、全部 base/config/quiet、price upload 的 `MATERIAL_OTHER`、material-name、固定 ID、Markdown、`2025-01-15`，以及 upload 紧邻唯一 process。
- Golden 精确锁定 DeepSeek/MiMo、technology、完整 requests/token/cost/currency budget、write base/output、preflight 与 paid materialization 隔离、五个 validators 的 action/order/path/base/config，以及 terminal plan/fingerprint。
- 全部 12 条 Dayu argv 随后逐条进入真实 `dayu.cli.main -> parse_arguments -> dispatch`。Fins 五条命令保留真实 `run_fins_command` / payload builder，只在 `_build_fins_ops_service` 外部服务边界返回 typed stream；隔离真实 company-meta repository 预置前序 fake download 本应建立的 AAPL meta。
- 两条 write 保留真实 parser、`run_write_command()`、`setup_paths()` 与 materialization-argument validator，仅以 typed Phase-A entry 在验证后、Host/model 前停止；合法两条均命中，非法 `preflight + materialize + research-base` 负控返回 2 且不越过该边界。
- 五个 validators 读取 `materialize_research_workspace()` 在隔离 research root 真实生成的 13 个 technology artifacts，并经真实 research-template dispatch 全部返回 0；无 SEC/Web/provider/model/network/paid 调用。

### 2. Owner materialization rollback observed by acceptance inspector

- 复用 `materialize_research_workspace()` 现有 late-guide fault injection。
- 先物化 AAPL/technology 的 owner 13 文件并保存逐文件原始 bytes，再以 overwrite 的 MSFT 变更触发 late failure。
- 失败后 13 个受保护路径逐字节等于故障前 snapshot；随后由 acceptance `inspect_research_artifacts()` 观察到 inventory healthy、issues empty。验收器没有实现第二套 rollback。

### 3. Untrusted persisted receipt ingress

- 参数化覆盖 terminal failed、signal、timeout、missing required field，以及 final planned failed/signal 六类 v3 persisted receipt。
- 攻击输入只通过 public `verify_acceptance()` / strict loader；不 direct-call raw evaluator。
- 两个 planned non-passed 样本都保留完整 successful planned prefix，只把最终 validations command/phase 改为 failed/signal，删除 terminal 且不存在 suffix/unknown receipt；精确命中“全部 planned phase 成功”gate，而非较早的 skip/reorder gate。
- 每类都在 `_evaluate_live_plan` composition boundary 前抛 `ContractError`，evaluator call count 为 0。
- `acceptance-receipt.json`、`source-inventory.json`、partial output sentinel 与全部 phase receipt bytes 在拒绝前后不变。

### 4. Fresh-run/no-resume recovery truth

- 首个 download 非零后保留 truthful receipt 与 partial artifact。
- 同 plan 再次 `run_acceptance()` 在 process factory/Popen 前因已有 phase receipt fail closed；第二 factory calls 为 0，evaluator calls 为 0，旧 receipt/partial bytes 不变。
- 当前可执行恢复只测试全新 run root 重新 `prepare`：新 root 得到不同 plan fingerprint，且仅生成新的 `prepare.json`；旧 run 仍保持原样。
- 未创建 test-local marker，future same-plan recovery 继续归 accepted plan 指定的独立 Gateflow work unit 与新 operator authorization。

### 5. Unbound technology residual truth

- 真实 technology monitoring owner plan 通过结构 validator，保持 `dry_run`、`automated_execution_allowed=false`，同时 readiness 为 `blocked_unbound_sources`。
- 最终 evaluator receipt 仍可按完整 fixture 质量 contract 得到 PASS，但 residuals 精确包含 readiness、blocked task count 与每个 unbound source；没有伪造 ready/bound 状态。

## Validation evidence

### Focused and owner tests

- parser/dispatch 与 persisted receipt trust 定向场景：**7 passed, 188 deselected**。
- `python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py -q`：**204 passed**。
- `python -m pytest tests/cli/test_research_template_command.py -q`：**216 passed**。

### Coverage execution evidence

仓库原组合 coverage 命令在 collection 前触发本机 NumPy `cannot load module more than once per process`。Coverage 7.15.4 不接受历史 `COVERAGE_CORE=timid` 字面量（报 `Unknown core value: 'timid'`）；本版本的 pure-Python 等价 core 是 `pytrace`。未为环境问题添加 seam、pragma 或 ignore。

使用 fresh 单进程、独立 `mktemp` `COVERAGE_FILE` 与 `COVERAGE_CORE=pytrace` 逐 source 复证：

- `utils.investment_agent_acceptance`：**204 passed，82%**。
- `utils.investment_agent_acceptance_contracts`：**204 passed，87%**。
- `utils.investment_agent_acceptance_evaluator`：并行首跑因三个测试进程竞争固定 fixture lock 得到 1 个 lock failure；撤销并发、fresh 独立复跑为 **204 passed，87%**。这是验证命令并发互扰，不是代码失败。
- owner rollback 新增场景以 `--cov=dayu.cli.commands` 单独执行：**1 passed**；目标 `_research_template_materialize.py` 分支被执行（单场景 30%，production 未修改，本 Slice 不把该单测覆盖率误作 owner 全文件门禁）。

### Static and scope gates

- `pyright tests/test_investment_agent_acceptance.py tests/cli/test_research_template_command.py`：**0 errors / 0 warnings**。
- Ruff `--select F,I`：**PASS**。
- Ruff default：**PASS**。
- Ruff full-rule HEAD/current audit：没有 default-rule regression。`tests/test_investment_agent_acceptance.py` 为 1207/1112；新增 code multiset 为 `COM812 +2, D202 +7, D400 +8, D413 +7, D415 +8, EM102 +1, PLR2004 +2, PT018 +1, RUF002 +4, S101 +50, SLF001 +2, TC003 +1, TRY003 +1, TRY004 +1`。`tests/cli/test_research_template_command.py` 仍为 1321/1315，delta `PLR2004 +1, S101 +4, SLF001 +1`。新增 diagnostics 只来自 tests 的 explicit golden literals/assertions、中文 docstrings、typed async fake boundary 与必要私有 owner phase seam；未以 `noqa`/ignore 隐藏。
- `git diff --check`：**PASS**。
- 允许路径审计：只包含上述两份测试与本 artifact；production/fixtures/README/plan 均无 diff。

## Documentation decision

README 更新明确属于 accepted Slice 4，且本 Slice 白名单禁止 README。本 Slice 只写 Gateflow durable implementation artifact，不提前修改用户文档或测试手册。

## Dual re-review closure

- Initial reviews：`docs/reviews/code-review-20260809-slice3-integration-codex.md`、`docs/reviews/code-review-20260809-slice3-integration-terra.md`。
- Final re-reviews：`docs/reviews/code-review-20260809-slice3-integration-rereview-codex.md`、`docs/reviews/code-review-20260809-slice3-integration-rereview-terra.md`。
- Final conclusions：Codex **PASS**、Terra **PASS**；两路 open High/Medium/Low 均为 **0 / 0 / 0**。
- Finding closure：`S3-CODE-001`、`S3-TERRA-001`、`S3-TERRA-002` 全部 **CLOSED**，没有新 finding、blocking question 或未分类 residual。
- Artifact-only closure 前冻结测试 SHA-256：`tests/test_investment_agent_acceptance.py = 015bd9a1b5a0be2b7bd04780d96a6d0808d55a05a846d3ceb7973577aa1a2ea9`；`tests/cli/test_research_template_command.py = 52d27d074656dc0555c51ca7aed4bc2804358ba2fbe95bffbc6d8622473f897f`。Closure 未修改两份测试。

## Plan gaps and residual risks

- 新 plan gap：**无**。Package config dir 可由真实 resolver 直接进入全部 owner CLI argv；Markdown material 可由现有 `MATERIAL_OTHER` upload/process/stable-ID contract 闭合。
- Future same-plan retry/resume：由 accepted plan 指定的未来独立 recovery work unit负责 durable authorization、receipt ownership、phase selection、idempotency/replay 与 budget/wall续算；当前未实现、未授权。
- Slice 5 external/live risk：继续由 Slice 5 live authorization gate承接；本 Slice 的 fake/process-owner integration不证明一次 live AAPL run 已通过。
- 用户 workspace custom templates、unbound technology sources、workbook open items：继续如实进入 accepted plan的 residual/completion-report destinations。

## Completion signal

Slice 3 tests-only implementation 与三项 accepted review findings 已经双路 re-review 闭合；当前状态为 **DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**。Implementer 未 commit、push、创建 PR、执行 live 或进入 Slice 4。
