# Slice 3 AAPL acceptance integration deep code review（Terra）

## Scope

- Mode: current uncommitted changes（tests-only Slice 3 implementation）
- Branch: `feat/investment-agent-acceptance`
- Base: `46446ef88979668a14b4a898e16c62fa260a5611`（review start HEAD）
- Reviewed at: 2026-08-09 16:45:50 CST（本机时钟）
- Output file: `docs/reviews/code-review-20260809-slice3-integration-terra.md`
- Included scope: `tests/test_investment_agent_acceptance.py`、`tests/cli/test_research_template_command.py`、accepted Slice 3 plan/closure、implementation artifact，以及相关 production parser/dispatch、phase-spec builder、receipt loader/evaluator boundary、materialization rollback owner。
- Excluded scope: production implementation修改、plan/fixture/README修改、live/network/SEC/Web/provider/model/paid、commit/push/PR。
- Parallel review coverage: 无；本轮由单一 reviewer 沿真实入口与失败路径完成。
- Conclusion: **FAIL**
- Open findings: **High 0 / Medium 2 / Low 0**

## Findings

### S3-TERRA-001-未修复-中-所谓 complete exact argv 测试以待测 plan 自身作为 expected，多个 plan-owned 关键 token 与跨 phase 顺序仍可静默漂移

- **入口/函数**: `test_slice3_real_parser_dispatch_locks_complete_aapl_command_contract()` 经真实 acceptance `main(run ...)` 进入 `run_acceptance()` 与 fake process boundary。
- **文件(行号)**: `tests/test_investment_agent_acceptance.py:5695-5814`，核心自引用在 `:5749-5755`，不完整 semantic spot checks 在 `:5757-5814`。
- **输入场景**: `build_phase_specs()` 发生 accepted contract 漂移，例如某条 download/process/upload argv 的 `--ticker` 不再是 AAPL、upload 的 `--material-name`/`--report-date` 漂移、price import 不再紧邻并先于唯一 process、write 的 `--base` 漂移，或 validators 的 action/order/path漂移；runner仍按同一个改变后的 builder生成和执行 plan。
- **实际分支**: 测试先由 `_prepare_slice2_run()` 使用production builder生成 `prepared.plan.phase_specs`，随后把该同一对象展平为 `planned_commands`，再断言fake实际调用等于它。`run_acceptance()`同样用production builder重建canonical specs，因此builder与执行共同漂移时`:5755`仍成立。
- **预期行为**: Accepted plan §9 Slice 3 line 407与§10 lines 480–579要求本测试独立锁定AAPL三组download、price upload后一次process、完整model/budget、两条write隔离参数、五个validator与全命令顺序；任一这些semantic token或顺序漂移都应使测试失败。
- **实际行为**: 后续assertions只检查download forms/windows、前五条命令的base、upload forms/document-id/files、process数量，以及write部分参数。它们没有独立检查每条owner命令的AAPL ticker、upload material-name/report-date/quiet、明确action sequence `download×3 → upload → process → write-preflight → write → validators×5`、write base、validator actions/order/paths。由同一plan派生的expected无法补上这些遗漏。
- **直接证据**:
  - Test `:5749` 从`prepared.plan.phase_specs`构造expected，`:5755`只证明runner执行了它刚生成的plan，不证明plan符合accepted外部semantic snapshot。
  - Test `:5784-5790`用filter+count找upload/process，没有断言二者相邻或upload先于process，也不检查material-name/report-date。
  - Test `:5800-5814`未检查write `--base`；整个新增测试没有validator action/order/path断言。
  - Production `build_phase_specs()`在`utils/investment_agent_acceptance.py:1288-1452`拥有这些实际tokens；fake owner stdout又固定输出AAPL/report-date而不是执行real owner，因此缺失assertion不能由fake运行结果间接弥补。
- **影响**: Slice 3 code gate可能在错误ticker、错误价格日期/材料身份、错误仓储base或错误phase/validator顺序下仍然全绿。进入获授权live lane后，这会变成错误外部数据操作、错误输入闭包、验证遗漏或费用运行失败，而不是仅测试命名不准确。
- **建议改法和验证点**:
  1. 保留plan canonical equality作为runner遵循signed plan的断言，但另加一个独立、冻结的semantic projection，按13条命令顺序核对action、ticker、forms/window、material-name/document-id/files/report-date、base/config/quiet、models/template/output/research-base/no-resume/budget及五个validator action/path。
  2. 至少显式断言`tuple(command[3] / validator action)`的全序列，且upload index紧邻并先于process；不要用filter+count替代order contract。
  3. 验证一个未被当前spot-check覆盖的token变异会使该test失败，防止expected再次从待测builder原样派生。
- **修复风险（低/中/高）**: 低；tests-only加强，不需production seam或第二套runtime builder。
- **严重程度（低/中/高/严重）**: 中。

### S3-TERRA-002-未修复-中-planned_nonpassed 用例实际因失败后仍存在后续 receipts 被拒绝，没有验证最终 planned non-passed 完整前缀的核心 gate

- **入口/函数**: `test_slice3_public_live_verify_rejects_untrusted_receipt_before_evaluator(..., receipt_case="planned_nonpassed")` 经public `verify_acceptance(live)`进入strict receipt loader。
- **文件(行号)**: `tests/test_investment_agent_acceptance.py:5817-5908`，尤其`:5855-5874`；实际production分支为`utils/investment_agent_acceptance.py:3813-3838`与`:3858-3862`。
- **输入场景**: 当前test先生成完整成功run，然后把中段`write.json`改为failed，却保留其后的`validations.json`与`verify.json`。真正需要锁定的反例是最后一个planned phase（validations）为truthful non-passed、没有terminal receipt的完整planned prefix。
- **实际分支**: Loader读取failed write后将`stopped=True`（production`:3836-3837`）；下一轮发现仍存在validations receipt，直接在`:3818-3819`以`phase receipts不得 skip/reorder`拒绝。测试只接受任意`ContractError`，因此并未走到`:3859-3862`对“planned集合完整但任一status非passed”的gate。
- **预期行为**: Accepted closure要求failed/signal/timeout/incomplete/non-passed persisted prefix通过public loader并在trusted evaluator前被拒绝。planned non-passed用例应证明失败本身不可被提升为PASS，而不是只证明“失败后又有非法suffix”会被拒绝。
- **实际行为**: 即使未来意外删除或弱化`_validate_terminal_receipt()`中`any(item.status != "passed")`检查，当前`planned_nonpassed`仍会因保留suffix在更早分支失败，测试继续绿色。测试因此不能防止final planned validations failed/full-length prefix到达trusted evaluator；raw evaluator按accepted架构不承担lifecycle gate。
- **直接证据**:
  - Test `:5855`选择中段`write.json`，但没有删除后续`validations.json`与`verify.json`；`:5890`不匹配具体拒绝原因。
  - Production `_load_planned_receipt_prefix()`在failed receipt后遇到任何后续receipt先报skip/reorder（`:3818-3819`）。
  - 只有final planned receipt non-passed且无terminal时，loader才以完整长度进入`_validate_terminal_receipt()`并依赖`:3859`的`any(status != passed)`拒绝；这条关键分支当前新增测试未覆盖。
- **影响**: Slice 3的核心trust-boundary回归门禁存在假阳性。未来若final planned lifecycle检查回归，failed validations可能被送入trusted evaluator并产生看似有效的acceptance结果，破坏“partial/non-passed永不PASS”的accepted contract。
- **建议改法和验证点**:
  1. 将planned non-passed样本改为`validations.json`的最后一条record/phase truthful failed（aggregate与record闭合），并删除`verify.json`以形成真实完整planned prefix。
  2. 继续断言public `verify_acceptance()`抛`ContractError`、evaluator call count=0、acceptance/source-inventory/partial/receipt bytes不变；同时匹配“全部 planned phase 成功”一类稳定contract reason，证明命中目标gate。
  3. 保留现有failed-write-with-suffix情形时应把它单列为suffix-after-failure/order-tamper测试，不能替代planned non-passed prefix。
- **修复风险（低/中/高）**: 低；只调整persisted test样本与assertion，不改production lifecycle ownership。
- **严重程度（低/中/高/严重）**: 中。

## Confirmed closures / non-regressions

- Production code、fixtures、README、accepted plan均为零diff；workspace code changes只在accepted的两份tests，另有implementation artifact。
- Real acceptance `main(run)` parser/dispatch确实被调用；runtime identity、environment presence、Git state、clock、process factory与repository facts均为deterministic fake，没有SEC/Web/provider/model/network/paid调用。
- Owner materialization late-failure测试对13个protected artifacts逐字节比较rollback前后，并由`inspect_research_artifacts()`确认inventory healthy、issues empty；没有在acceptance层实现第二套rollback。
- Terminal failed/signal/timeout/incomplete四类样本均通过public live verify/strict loader，evaluator call count为0，acceptance receipt、source inventory、partial artifact与phase receipts保持字节不变。
- Same-plan rerun在已有download failure receipt后于factory/Popen前拒绝；两条write各精确一个`--no-resume`，旧receipt/partial bytes不变；fresh root重新prepare产生不同fingerprint且仅有新`prepare.json`。
- Unbound technology owner plan保持structurally valid、`dry_run`、automation disabled、`blocked_unbound_sources`；final evaluator residuals保留readiness、blocked task count与全部unbound source。
- 新diff未引入`Any`、`object`、`cast`、ignore/noqa、compatibility wrapper、authorization marker、resume action/schema或glue seam。对private `_evaluate_live_plan`的spy是accepted plan明确要求的composition-boundary观察点；rollback owner test中的private path helper没有进入production coupling。

## Validation evidence

- `python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py -q`：**203 passed**。
- `python -m pytest tests/cli/test_research_template_command.py -k "materialize or research_workbook or workbook_report or source_map or monitoring" -q`：**128 passed, 88 deselected**。
- Slice 3 + owner late rollback定向选择：**9 passed, 401 deselected**。
- `pyright tests/test_investment_agent_acceptance.py tests/cli/test_research_template_command.py`：**0 errors / 0 warnings**。
- Ruff default与`--select F,I`：**PASS**；`git diff --check`：**PASS**。
- Ruff 0.15.11 full-rule独立HEAD/current聚合与implementation artifact一致：acceptance test `1112 → 1199`，owner test `1315 → 1321`；新增diagnostics仅为tests assertions/docstring/private-boundary等已记录类别，无default-rule regression或ignore隐藏。
- 未执行live/network/SEC/Web/provider/model/paid；未修改现有文件，除本review artifact外未写repository artifact。

## Open Questions

- 无。两个finding均可由当前code path与accepted plan直接裁决，不需要用户补充事实。

## Residual Risk

- Existing-terminal-only（没有任何planned receipt但有`verify.json`）的tampered inventory guard未在Slice 3单独构造；正常成功run必然已有planned receipts，因此当前same-plan test会先命中planned guard。可在修复时作为低成本附加case，但不单列finding。
- 本轮未重复implementation artifact的per-module coverage采集；production无diff，受影响完整test/owner suites、pyright与Ruff已独立复跑。coverage数值本身不改变上述两个直接test-path findings。
- Future same-plan recovery、live inputs/费用/fingerprint与unbound source binding仍按accepted plan归future work/Slice 5授权gate，不属于本Slice implementation缺陷。

## Final conclusion

**FAIL — open High/Medium/Low = 0 / 2 / 0.** Rollback、terminal persisted receipt、fresh-root/no-resume、unbound residual与production-zero-diff均闭合；但exact argv integration测试仍有self-derived expected盲区，planned non-passed测试又命中了suffix-after-failure分支而非目标lifecycle gate。关闭S3-TERRA-001/002后再标记Slice 3 code-review PASS。
