# Slice 3 AAPL acceptance review-fix — Codex corrective code re-review

## Scope

- Mode: current changes，closure-only corrective re-review
- Review time: 2026-08-09 17:06:08 CST
- Branch: `feat/investment-agent-acceptance`
- Base: `HEAD 46446ef88979668a14b4a898e16c62fa260a5611`
- Output file: `docs/reviews/code-review-20260809-slice3-integration-rereview-codex.md`
- Included scope: current two-test diff；updated implementation/adjudication/review-fix artifacts；Codex `S3-CODE-001` 与 Terra `S3-TERRA-001/002` 的 closure；相关 production parser/main/dispatch、write validation、Fins service boundary、research validators、receipt loader/contracts
- Excluded scope: production/fixture/README/accepted-plan redesign；live/network/SEC/Web/provider/model/paid；commit/push/PR
- Parallel review coverage: 无；本次由单 reviewer 独立复现

## Findings

未发现实质性问题。

## Finding closure

### S3-CODE-001 — CLOSED

原测试只让 acceptance harness parser 解析 `run`，并在 child Dayu CLI 之前以 process factory截断。当前修复分成两个互相独立的证明层：

1. acceptance `main(run)` 仍经真实 parser/runner执行，并要求实际13次 factory调用逐 token等于独立 golden；
2. golden中的全部12条 `python -m dayu.cli` planned argv随后逐条进入真实 `dayu.cli.main()`，从真实 `parse_arguments()` 分发到 Fins、write或research-template owner。

Fake边界没有退回到参数token观察：

- download/upload/process先通过真实 Fins parser、`run_fins_command()`与typed command payload builder，只把 `_build_fins_ops_service`替换为typed result stream；捕获的五个 `FinsCommand`类型、顺序及AAPL/upload/process payload字段均被断言。
- 两条write先通过真实 parser、top-level main dispatch、`run_write_command()`、`setup_paths()`与`_validate_research_materialization_args()`，再在post-validation、Host/model前的typed Phase-A entry停止。非法 `preflight + materialize + research-base`负控返回2且没有增加sentinel计数，直接证明validation没有被fake绕过；两条合法argv均越过同一validation并命中sentinel。
- 五条research-template validator argv在真实materialized technology workspace上经真实parser/main/owner dispatch返回0，没有替换validator。

因此原 PF-EXTRA-001 风险已转化为持久测试门禁；当前测试不再依赖reviewer临时命令证明write组合合法。

### S3-TERRA-001 — CLOSED

`_slice3_golden_command_contract()`没有读取 `prepared.plan.phase_specs`，不调用 `build_phase_specs()`或`build_terminal_verify_command()`；它只接收不可硬编码的runtime identity（Python绝对路径、隔离run root、resolved package config和已签名fingerprint），其余accepted语义均为显式固定token。

Golden精确列出13条命令并锁定：

- 三组AAPL download ticker/forms/五年或两年window/end/base/config/quiet；
- price upload的subcommand、ticker、`MATERIAL_OTHER`、material name、固定document ID、Markdown path、`2025-01-15`、base/config/quiet；
- upload后紧邻且唯一的AAPL process；
- 两条write的DeepSeek/MiMo、technology、output、四项budget、data base/config、精确一个`--no-resume`，以及preflight/paid materialization与research-base隔离；
- 五个validator action/order/输入path/research base/config；
- terminal module、plan path、fingerprint和`--json`。

测试分别要求production plan flatten和runner observed calls等于该golden；builder与runner共同漂移不能再通过。额外固定subcommand全序列与stable material ID literal，避免filter/count替代跨phase顺序。

### S3-TERRA-002 — CLOSED

`planned_failed`与`planned_signal`现在都选择最后一个planned phase `validations.json`，只修改其最后一个record和phase aggregate状态：此前四个validation records仍passed，最后record分别是parser-valid failed或signal，故形成完整长度planned prefix。测试删除terminal receipt且不添加suffix/unknown receipt。

Public `verify_acceptance(live)`精确匹配 `live verify 要求全部 planned phase 成功`。仓库内该文本只来自 `_validate_terminal_receipt()` 的完整长度且 `any(status != "passed")` 分支，因此该用例不再可能由较早的suffix-after-failure/skip-reorder gate假绿。两个用例均断言 evaluator call count为0，acceptance/source-inventory/partial sentinel与保留phase receipts bytes不变。

## Adversarial / architecture review

- **Fake真实性**: Fins fake位于真实payload builder之后；write fake位于真实materialization validation之后，并由非法组合负控证明call ordering；validators不fake。没有SEC/Web/provider/model/network/paid调用。
- **Private seam耦合**: write test使用私有 `_WRITE_PHASE_EARLY_RECOVERY` / `_EarlyWriteSubcommandEntry` 作为post-validation stop seam，确有对owner内部dispatch形状的测试耦合。但本Slice禁止production seam，且该耦合只存在tests；它精确观测“validation前拒绝、validation后才停止”的必要顺序，未复制业务规则，也未暴露为production contract。当前不构成material maintainability finding。
- **Golden重复**: 13-command golden是accepted CLI policy的test oracle，不是production builder或运行时第二真源；production仍由唯一 `build_phase_specs()`执行。显式重复是防止self-derived expected的必要回归快照。
- **13-artifact validator**: owner真实物化technology workspace；独立rollback测试仍锁定`REQUIRED_RESEARCH_ARTIFACTS`精确13项及byte-exact恢复；golden五个validator对该workspace的固定13件路径执行真实owner validation。
- **Scope**: production、fixtures、README、tests README与accepted plan零diff。没有新增action/flag/schema/marker/wrapper/evaluator gate、compatibility glue、`Any`/`object`传播、cast、ignore或`noqa`。
- **Full-rule delta**: default Ruff和F/I clean。ALL/preview新增项来自test assertions、中文docstring convention、显式golden literals、private observation seam、typed async test stream与单个test函数局部变量；未掩盖类型/控制流错误，也没有ignore。`RUF029`对应必须实现`AsyncIterator`的单yield fake stream；`SLF001`对应上述有意的composition/owner test seam。它们不阻塞本tests-only closure。

## Executable validation

- `python -m pytest tests/test_investment_agent_acceptance.py -k 'slice3_real_parser_dispatch or slice3_public_live_verify' -q` — **7 passed, 188 deselected**。
- `python -m pytest tests/test_investment_agent_acceptance.py tests/fins/test_cli_formatters_coverage.py -q` — **204 passed**。
- `python -m pytest tests/cli/test_research_template_command.py -q` — **216 passed**。
- `pyright tests/test_investment_agent_acceptance.py tests/cli/test_research_template_command.py` — **0 errors / 0 warnings / 0 informations**。
- `ruff check`与`ruff check --select F,I`（两份tests）— **PASS**。
- `git diff --check` — **PASS**。
- Scope audit — diff仍只含两份accepted tests；production/fixtures/README/plan均零diff。

## Open Questions

- 无。

## Residual Risk

- `existing terminal only`的tampered receipt-root rerun仍未单独参数化；正常completed run必然同时含planned receipts并被现有pre-Popen gate拒绝，因此不影响本轮三个finding closure。可作为后续defense-in-depth，但不是当前H/M/L。
- Write测试刻意不进入Host/model/provider执行；Slice 3只验证parser/dispatch/validation边界，不证明live write成功。Slice 5继续为`NOT AUTHORIZED / NOT RUN`。
- Future same-plan recovery仍属于独立、重新授权的work unit；当前diff正确未实现marker/action/schema或resume路径。

## Conclusion

**PASS — open High/Medium/Low = 0 / 0 / 0。** `S3-CODE-001`、`S3-TERRA-001`与`S3-TERRA-002`均已通过独立golden、真实owner parser/main/validation/validator路径及目标receipt gate证据闭合；未发现修复引入的新H/M/L回归。
