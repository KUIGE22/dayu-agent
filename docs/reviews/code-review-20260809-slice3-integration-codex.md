# Slice 3 AAPL acceptance tests-only implementation — Codex deep code review

## Scope

- Mode: current changes（用户指定仅审当前未提交 Slice 3 diff）
- Review time: 2026-08-09 16:45:12 CST
- Branch: `feat/investment-agent-acceptance`
- Base: `HEAD 46446ef88979668a14b4a898e16c62fa260a5611`
- Output file: `docs/reviews/code-review-20260809-slice3-integration-codex.md`
- Included scope: `tests/test_investment_agent_acceptance.py`、`tests/cli/test_research_template_command.py`、implementation artifact，以及为核对真实入口而只读追踪的 acceptance CLI、Dayu CLI parser/dispatch/write validation、receipt loader/contracts、materialization owner/evaluator
- Excluded scope: 已 accepted production、fixtures、README、plan 的重新设计；live SEC/Web/provider/model/paid execution；commit/push/PR
- Parallel review coverage: 无；本次为独立单 reviewer 审查
- Scope fact: production、fixture、README、plan 均为零 diff；当前 workspace production/test change 精确为两份 tests，另有一份 implementation artifact

## Findings

### S3-CODE-001-未修复-中-所谓真实 parser/dispatch 测试在 Dayu CLI parser 之前就被 fake 截断，不能守卫 accepted argv contract

- **入口/函数**: `test_slice3_real_parser_dispatch_locks_complete_aapl_command_contract()`；被测入口为 acceptance harness `main(("run", ...))`
- **文件(行号)**: `tests/test_investment_agent_acceptance.py:5695-5814`；真实 child parser/dispatch 位于 `dayu/cli/main.py:17-65`，write 组合 validation 位于 `dayu/cli/commands/write.py:533-566` 与 `dayu/cli/commands/_write_params_validation.py:1939-1955`
- **输入场景**: acceptance builder 生成的任一 `python -m dayu.cli ...` argv 不再被当前 Dayu parser 接受，或仍可 parse 但被真实 write validation 拒绝；已发生过的同源反例就是 `--preflight-only` 与 materialization/`--research-base` 冲突，accepted plan-fix PF-EXTRA-001 因而明确把真实 parser/validation 锁定分配给 Slice 3。
- **实际分支**: 测试只让 acceptance harness 的 parser 解析 `run --plan ... --fingerprint ... --json`（`utils/investment_agent_acceptance.py:1830-1875`）。随后 monkeypatch 把 `SubprocessFactory` 换为 `_FakeProcessFactory`（test `:5716-5733`）；12 条 child `dayu.cli` 命令只被记录并直接返回 fake success，从未进入 `dayu.cli.arg_parsing.parse_arguments()`、`dayu.cli.main()` 或 `run_write_command()` 的 `_validate_research_materialization_args()`。
- **预期行为**: Slice 3 应以真实 Dayu parser/dispatch/validation 消费 acceptance 生成的 child argv，把 fake 边界放在外部 I/O、仓储、Host/model/provider 执行层之后；至少两条 write argv 必须真正通过 owner parser 与 materialization validation，才能关闭 PF-EXTRA-001。测试还应以独立期望锁定 price import 的 `--report-date` 以及 `upload_material → process` 顺序。
- **实际行为**: `factory.calls == prepared.plan.phase_specs`（test `:5749-5755`）只是把执行观察值与同一 production builder 产出的 plan 再比较；它不能发现 builder 与 owner CLI 同步之外的契约漂移。后续 token assertions虽检查 preflight/paid 的部分 flag，却没有调用真实 validation，也没有断言 upload `--report-date`，仅断言 process 数量为 1 而未断言它紧随 upload（test `:5784-5790`）。因此一个 owner parser/validation 会 exit 2 的 plan，或一个 process 被移到 import 之前/缺 report date 的 coordinated builder change，仍可能让本测试通过。
- **直接证据**:
  1. `acceptance_cli_module.main()` 只解析 acceptance 子命令；child command 在 `services.process_factory.start()` 才会跨进程（`utils/investment_agent_acceptance.py:2442`）。测试将该 factory 完全替换为只记录 argv 的 fake。
  2. 新测试没有 import/call `dayu.cli.arg_parsing.parse_arguments`、`dayu.cli.main.main`、`run_write_command` 或 `_validate_research_materialization_args`。
  3. Review-only executable check 把当前两条 captured write argv 分别送入真实 Dayu parser 和真实 `_validate_research_materialization_args()`，得到 `write:preflight=True/materialize=False -> None` 与 `write:preflight=False/materialize=True -> None`。这证明当前 argv 是合法的，也证明该关键检查只能由 reviewer临时命令发现，并未成为本 Slice 的持久回归门禁。
  4. Accepted plan `:407` 要求“真实 parser/dispatch（外部边界 fake）”；PF-EXTRA-001 明确要求 Slice 3 用真实 parser/validation 锁定 preflight/materialization 组合。
- **影响**: 当前 production 恰好合法，但 Slice 3 声称完成的集成 gate 未实际建立。未来 owner parser、write validation 或 acceptance builder 任一侧漂移时，CI 可继续显示 PASS，而获授权 live run 才在 child exit 2 停止；若顺序漂移，price material 还可能在 process 之后才导入，破坏付费 write 前的 source closure。该缺口阻止把本 tests-only Slice 标记为 code-review accepted。
- **建议改法和验证点**: 仍只改 Slice 3 两份允许 tests：让 captured planned argv 进入真实 `dayu.cli` parser，并让 preflight/paid write 进入真实 dispatch/`run_write_command` validation；只在 validation 后的 Host/model/provider/仓储执行边界 fake。若完整 dispatch 的 setup 太重，至少用真实 `parse_arguments()` 解析每条 argv，并对两条 parsed write namespace 调用真实 owner validation，再补一个 dispatch sentinel证明命中正确 command owner。独立断言 child subcommand有序序列、upload `--material-name aapl-price-snapshot`、`--report-date 2025-01-15`、upload 紧接 process，以及 AAPL ticker。新增负控：给 preflight 注入 `--research-base`/`--materialize-research`，必须由真实 owner validation exit 2，而合法的两条 builder argv均通过。
- **修复风险（低/中/高）**: 低；只需修 tests，production contract 无需改变，也不得新增 wrapper/flag/seam。
- **严重程度（低/中/高/严重）**: 中

## Verified closure / adversarial evidence

除上述 finding 外，下列 Slice 3 合同已得到直接证据支持：

- **Receipt trust boundary**: 五类参数化输入覆盖 terminal failed/signal/timeout/missing-field 与 planned non-passed；全部只经 public `verify_acceptance()`/strict loader，`_evaluate_live_plan` call count 为 0，acceptance/source inventory/partial sentinel 与全部 phase receipt bytes不变。failed/signal/timeout 构造满足 v3 record lifecycle；missing-field由 strict parser拒绝，planned non-passed由 prefix/terminal closure拒绝。
- **13-file rollback**: owner先真实物化 AAPL/technology 13 个受保护路径，snapshot逐文件 bytes；MSFT overwrite 在 late guide注入 `OSError` 后，13 文件 byte-exact恢复，随后同一 acceptance `inspect_research_artifacts()` 观察到 `inventory_ok=true`、`issues=()`。测试用 owner私有路径枚举，但同时独立与 public required 13-name tuple及 acceptance inspector交叉闭合，未复制第二套 rollback实现。
- **No-resume/fresh-root**: 首个 download exit 7 产生 truthful failure receipt；同 plan再次 run 在 factory/Popen前因已有 planned receipt拒绝，第二 factory calls=0、evaluator calls=0、旧 receipt/partial bytes不变。fresh root重新 prepare得到不同 plan fingerprint且仅创建新 `prepare.json`。两条 write argv均各含精确一个 `--no-resume`，无 `--resume`、marker、cleanup workaround或新 action/schema。
- **Unbound technology truth**: 真实 owner monitoring plan结构 validator返回 healthy；acceptance inspection同时保持 `dry_run`、`automated_execution_allowed=false`、`blocked_unbound_sources`、非零 blocked tasks与unbound sources；最终 fixture-quality receipt可 PASS但逐项保留 residual，没有伪造 ready/bound。
- **Architecture/scope**: production零 diff；未新增 wrapper、flag、action、schema、marker、evaluator lifecycle gate、`Any`/`object`传播、cast/ignore/noqa或production glue。tests 对私有 `_evaluate_live_plan`/materialization seam 的使用仅用于边界调用计数和现有 fault injection，未把私有对象变成生产契约。

## Executable validation

- `python -m pytest tests/test_investment_agent_acceptance.py tests/cli/test_research_template_command.py -k 'slice3 or workspace_materialize_rolls_back_bundle_and_plan_after_late_failure' -q` — **9 passed, 401 deselected**。
- `python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py -q` — **203 passed**。
- `python -m pytest tests/cli/test_research_template_command.py -k 'materialize or research_workbook or workbook_report or source_map or monitoring' -q` — **128 passed, 88 deselected**。
- `python -m pytest tests/cli/test_research_template_command.py -q` — **216 passed**。
- `pyright tests/test_investment_agent_acceptance.py tests/cli/test_research_template_command.py` — **0 errors / 0 warnings / 0 informations**。
- `ruff check` 与 `ruff check --select F,I`（两份 tests）— **PASS**。
- `git diff --check` — **PASS**。
- Review-only real owner parser/validation reproduction — 当前两条 write argv均 parse成功且 `_validate_research_materialization_args()` 返回 `None`；此证据确认当前 argv事实，但不能替代缺失的 committed regression test。

## Open Questions

- 无。

## Residual Risk

- 当前 same-plan test直接覆盖 planned failure receipt gate；terminal-only receipt presence是 `_assert_no_existing_run_receipts()` 的独立防御分支，但正常 completed run同时已有 planned receipts，仍会被前一分支拒绝。可在修复 S3-CODE-001 时追加 terminal-only corruption场景以增强 defense-in-depth；本次未把它单独定为 material finding。
- 本 Slice 没有、也不得声称证明 SEC/Web/provider/model/live AAPL execution；Slice 5 仍为 `NOT AUTHORIZED / NOT RUN`。
- Future same-plan recovery仍是独立 work unit，需新 operator authorization、原 fingerprint绑定及 receipt/idempotency/replay/budget设计；当前 tests正确没有实现它。

## Conclusion

**FAIL — open High/Medium/Low = 0 / 1 / 0。** Receipt ingress、rollback、fresh-run/no-resume、unbound residual与scope gates均有真实证据；但核心 parser/dispatch integration test把 fake边界放在整个 child Dayu CLI之前，未把 acceptance生成的 argv送入真实 owner parser/validation，也未独立锁定 material report date与 import→process顺序。关闭 S3-CODE-001 后再做 corrective code re-review。
