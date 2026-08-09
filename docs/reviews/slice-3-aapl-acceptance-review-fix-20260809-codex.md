# Slice 3 AAPL acceptance code-review fix

- 日期：2026-08-09
- Gate：Gateflow Slice 3 code-review fix
- Adjudication：`docs/reviews/slice-3-aapl-acceptance-review-adjudication-20260809-codex.md`
- 状态：**CLOSED / DUAL RE-REVIEW PASS**
- Plan gap：**无**
- Live / paid：**NOT AUTHORIZED / NOT RUN**

## Applied fixes

### S3-CODE-001 / S3-TERRA-001

新增独立 `_slice3_golden_command_contract()`，不用 production phase/terminal builder 构造 expected。它显式返回以下固定顺序：

1. AAPL `download 10K`，五年窗口；
2. AAPL `download 10Q`，两年窗口；
3. AAPL `download 8K DEF14A`，两年窗口；
4. `upload_material MATERIAL_OTHER`，固定 material-name/document-id/Markdown/report-date；
5. 唯一 `process`；
6. DeepSeek/MiMo write preflight，无 research-base/materialize；
7. 同模型/预算 paid write，带隔离 output/research-base/materialize；
8. 五个固定 action/order/path 的 research validators；
9. terminal live verify，绑定 plan path/fingerprint。

Plan flatten 与实际 runner calls 分别逐 token 等于该 golden。随后所有 12 条 Dayu 命令逐条通过真实 `dayu.cli.main()` parser/dispatch：

- download/upload/process 命中真实 `run_fins_command()` 与 command payload builder，只在 Fins service 外部边界返回 typed result stream；
- preflight/paid write 命中真实 `run_write_command()`、`setup_paths()` 与 materialization 参数校验，只在该校验后的 typed phase entry 停止 Host/model；
- 非法 preflight+materialize+research-base 负控返回 2，未越过 fake boundary；
- 五 validators 对隔离 owner `materialize_research_workspace()` 生成的 13 artifacts 真实执行并全部返回 0。

### S3-TERRA-002

Persisted receipt 参数化用例不再把中段 write 改坏后保留 suffix。新 `planned_failed` / `planned_signal` 均保留 download 至 validations 的完整 receipt prefix，只修改 validations 最后一条 record 与 aggregate status，删除 terminal receipt且不增加未知/suffix文件。Public live verify 精确报“要求全部 planned phase 成功”，`_evaluate_live_plan` 0 次；acceptance/source-inventory/partial sentinel 与全部保留 receipt bytes 前后相同。

## Executable evidence

- 定向 parser/dispatch + receipt trust：**7 passed, 188 deselected**。
- Acceptance + formatter owner suite：**204 passed**。
- Research-template owner suite：**216 passed**。
- Coverage（fresh 单进程、独立 `COVERAGE_FILE`、`COVERAGE_CORE=pytrace`）：acceptance CLI **82%**，contracts **87%**，evaluator **87%**，各最终 **204 passed**。Evaluator 并行首次采集只因共享 fixture lock 与另两进程冲突；顺序复跑 clean pass。
- Pyright 两文件：**0 errors / 0 warnings / 0 informations**。
- Ruff default 与 `--select F,I`：**PASS**。
- Ruff full-rule HEAD/current：acceptance test `1112 -> 1207`，research test `1315 -> 1321`；新增均为 test golden/assert/docstring/typed fake/private owner seam 类别，无 default regression、ignore 或 `noqa`。
- `git diff --check`、final-newline、allowed-path、production-zero-diff：见最终 scope audit，均要求 PASS。

## Scope and handoff

允许变更只包括两份 tests 与 implementation/adjudication/fix artifacts。Source review 文件保持原文；production、fixtures、accepted plan、README 和其它 tests 不动。未 commit、push、创建 PR、执行 live 或进入 Slice 4。

## Dual re-review closure

- Initial reviews：`docs/reviews/code-review-20260809-slice3-integration-codex.md`、`docs/reviews/code-review-20260809-slice3-integration-terra.md`。
- Final re-reviews：`docs/reviews/code-review-20260809-slice3-integration-rereview-codex.md`、`docs/reviews/code-review-20260809-slice3-integration-rereview-terra.md`。
- Codex final：**PASS — open 0 / 0 / 0**。
- Terra final：**PASS — open 0 / 0 / 0**。
- `S3-CODE-001`、`S3-TERRA-001`、`S3-TERRA-002`：全部 **CLOSED**。
- Final handoff：**CLOSED / DUAL RE-REVIEW PASS**；implementation 已达到 **READY FOR ACCEPTED COMMIT**。
