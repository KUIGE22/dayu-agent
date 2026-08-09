# Slice 3 AAPL acceptance corrective code re-review（Terra）

## Scope

- Mode: corrective current-changes code re-review
- Branch: `feat/investment-agent-acceptance`
- Base: `46446ef88979668a14b4a898e16c62fa260a5611`（review start HEAD）
- Reviewed at: 2026-08-09 17:06:04 CST（本机时钟）
- Output file: `docs/reviews/code-review-20260809-slice3-integration-rereview-terra.md`
- Source reviews: `code-review-20260809-slice3-integration-codex.md`、`code-review-20260809-slice3-integration-terra.md`
- Adjudication/fix: `slice-3-aapl-acceptance-review-adjudication-20260809-codex.md`、`slice-3-aapl-acceptance-review-fix-20260809-codex.md`
- Included scope: S3-CODE-001、S3-TERRA-001、S3-TERRA-002 closure；13-command golden、real child parser/main dispatch、write/validator boundary、persisted non-passed prefix及相邻Slice 3 regressions。
- Excluded scope: production/fixture/plan/README修改、live/network/SEC/Web/provider/model/paid、commit/push/PR。
- Parallel review coverage: 无；单一 reviewer 沿真实入口、typed fake boundary与receipt state machine复核。
- Conclusion: **PASS**
- Open findings: **High 0 / Medium 0 / Low 0**

## Findings

未发现实质性问题。

## Corrective finding closure

| Finding | Closure | Direct evidence |
|---|---|---|
| Codex S3-CODE-001: child Dayu parser/dispatch在fake前未执行 | **CLOSED** | `tests/test_investment_agent_acceptance.py:6093-6095`把全部12条Dayu golden argv逐条送入真实`dayu.cli.main()`；production main再真实进入Fins/write/research-template dispatch。Fins只在`_build_fins_ops_service` typed service边界替换（`:6079-6082`），真实command payload在`:6097-6116`被观察；write fake位于`run_write_command()` materialization validation之后，非法preflight组合返回2且未进入fake runner（`:6117-6127`）。五个research validators未被patch，读取`:6071-6076`真实owner物化的13件并全部返回0。 |
| Terra S3-TERRA-001: expected由production plan自身派生且token/order断言不全 | **CLOSED** | `_slice3_golden_command_contract()`（`:5705-5907`）不调用production phase/terminal builder，独立固定13条逐token argv：三组download、upload identity/report-date、process、两条write完整model/budget/base/output/research参数、五validator action/path和terminal plan/fingerprint。Production plan flatten与actual factory calls分别等于golden（`:6041-6043`），完整action order另在`:6044-6057`锁定；stable material ID以独立literal与owner builder结果交叉（`:6058`）。 |
| Terra S3-TERRA-002: planned non-passed实际命中failure suffix/order gate | **CLOSED** | `planned_failed`与`planned_signal`选择最后planned phase `validations.json`及其最后record（`:6130-6189`），aggregate/record lifecycle同步后删除`verify.json`（`:6193-6195`），形成无terminal、无suffix的完整planned prefix。Public verify精确匹配`live verify 要求全部 planned phase 成功`，evaluator call count 0，acceptance/source-inventory/partial/全部保留receipts byte-identical（`:6197`以后）；定向执行两case均通过。 |

## Adversarial verification

### Independent 13-command contract

- Golden只接收runtime-variable scalars：Python path、run root、resolved package config与plan fingerprint；forms/windows、AAPL、material name/ID/report date、model roles、budget、no-resume、paths、validator actions/order均是accepted external snapshot，而非从`prepared.plan.phase_specs`回读。
- `planned_commands == golden[:-1]`锁住builder语义，`factory.calls == golden`独立锁住runner实际执行与terminal derivation；两条链不再共享同一个expected source。
- Action sequence精确为`download×3 → upload_material → process → write preflight → paid write → research-template validators×5`；upload紧邻并先于process。
- Terminal command同样逐token进入golden，绑定run-owned plan path、exact fingerprint与`--json`。

### Real parser/main dispatch and minimum fake boundary

- 第一层acceptance `main(run)`仍真实解析并执行signed plan；其process factory只用于捕获本来会跨进程的argv，不用于声称owner parser已执行。
- 第二层明确把captured golden child argv剥去`python -m dayu.cli`前缀后写入`sys.argv`并调用真实`dayu.cli.main()`，因此owner argparse、top-level router与command dispatch都实际执行。
- Fins download/upload/process经过真实`run_fins_command()`和payload builder；只在会进入外部仓储/网络执行的typed service builder处替换为`_Slice3FinsService`。隔离`data-workspace`使用真实`FsCompanyMetaRepository`预置upload所需company事实，没有伪造argv或绕过owner preparation。
- Write经过真实parser、`setup_paths()`与`_validate_research_materialization_args()`；catch-all early entry位于production validation之后。合法preflight/paid各命中一次，非法`preflight + materialize + research-base`返回2且第三次runner没有发生，直接证明validation未被fake短路。
- 五个validator dispatch完全真实；它们对owner物化的13 artifacts执行，未patch parser、validator action或artifact reads。

### Persisted non-passed receipt truth

- `planned_failed`与`planned_signal`均从canonical passed validations receipt出发，只把最后record与phase aggregate改为闭合的non-passed终态；strict parser成功后才到达目标error，否则测试的精确error match不会通过。
- `verify.json`在snapshot前已删除，receipt root只有prepare与六个planned receipts；没有未知文件、terminal或失败后suffix可抢先触发其它gate。
- Production `_load_planned_receipt_prefix()`因此得到完整长度、末phase non-passed的prefix，再由`_validate_terminal_receipt()`的planned-success gate拒绝；raw evaluator没有成为lifecycle ingress。
- Rejection后evaluator计数、acceptance receipt、source inventory、partial artifact与receipt bytes全部保持不变。

## Confirmed non-regressions

- 13件materialization late-failure rollback仍逐文件byte-exact，随后acceptance inspector返回`inventory_ok=true`、`issues=()`。
- Terminal failed/signal/timeout/incomplete四类public-loader拒绝、same-plan pre-Popen拒绝、fresh root/new fingerprint、两条write exact `--no-resume`、unbound blocked residual均保持。
- Production、fixtures、accepted plan、README与其它tests零diff；code changes仍精确为accepted两份tests，review/implementation artifacts在`docs/reviews/`。
- 未新增production seam、wrapper、flag/action/schema、resume marker、evaluator lifecycle gate、`Any`/`object`/cast/ignore/noqa或glue code。
- Private seams已收窄到测试观察/外部停止点：Fins service builder在typed command构造后；write early dispatch entry在真实materialization validation后；materialization private path helper只在owner rollback test交叉验证public 13-name contract。没有private object进入production API。
- README未在本Slice修改与accepted tests-only allowlist一致；用户文档同步仍归Slice 4，未提前扩scope。

## Executable validation

- Parser/dispatch + receipt trust定向：**7 passed, 188 deselected**。
- `python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py -q`：**204 passed**。
- `python -m pytest tests/cli/test_research_template_command.py -q`：**216 passed**。
- `pyright tests/test_investment_agent_acceptance.py tests/cli/test_research_template_command.py`：**0 errors / 0 warnings / 0 informations**。
- Ruff default与`--select F,I`：**PASS**；`git diff --check`：**PASS**。
- Ruff 0.15.11 full-rule HEAD/current独立聚合：acceptance test `1112 → 1207`，owner test `1315 → 1321`。新增diagnostics来自test golden/assert/docstring/typed fake/private observation类别；default无回归，diff中无ignore/`noqa`。
- 未执行live/network/SEC/Web/provider/model/paid；除本review artifact外未修改现有repository文件。

## Open Questions

- 无。

## Residual Risk

- `_WRITE_PHASE_EARLY_RECOVERY`与`_EarlyWriteSubcommandEntry`是private test interception point；它避免Host/model/live执行并通过负控锁定其位于materialization validation之后。未来write内部dispatch重构可能需要同步测试，但当前没有跨production耦合或语义绕过，故不构成open finding。
- Fins fake不证明SEC/download或repository side effects；这正是Slice 5 live authorization范围。当前Slice只证明golden argv可被真实owner parser/dispatch收窄成正确typed command。
- 本轮未重复per-module coverage采集；production零diff，corrective目标由完整受影响suites、pyright、Ruff与定向真实dispatch测试覆盖。
- Future same-plan recovery、live runtime inputs/费用/fingerprint与unbound source binding仍按accepted plan归未来work unit/Slice 5 gate。

## Final conclusion

**PASS — open High/Medium/Low = 0 / 0 / 0.** S3-CODE-001、S3-TERRA-001与S3-TERRA-002均已闭合；independent 13-command golden、12条真实Dayu parser/main dispatch、write/validator真实边界与final planned failed/signal完整prefix均获得直接测试证据，未发现新的High/Medium/Low回归。
