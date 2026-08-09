# Slice 1 AAPL acceptance implementation

- Status: **DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**
- Work unit: `investment-agent-aapl-acceptance` / Slice 1
- Accepted baseline: Slice 0 commit `61ba80c`
- Accepted plan commit: `5b5494e`
- Branch observed: `feat/investment-agent-acceptance`
- Implementer role: Codex implementation worker；未执行 plan review、code review、deep review、commit、push 或 PR 操作
- Runtime boundary: 仅 deterministic fixture 与临时物化产物；未发起 SEC、Web、DeepSeek、MiMo 或其它外部/付费调用，未读取 secret 值

## Scope and files

本 Slice 严格限制在以下白名单：

- `utils/investment_agent_acceptance_contracts.py`（新建）
- `utils/investment_agent_acceptance_evaluator.py`（新建）
- `tests/test_investment_agent_acceptance.py`（修改）
- 本实现记录（新建）

未修改 fixture、`dayu/`、README、tests/README 或 Slice 2+ 文件。README/operator docs 按已接受计划保留到 Slice 4。

## Contract and owner boundaries

### Strict contracts

- 用 frozen dataclass 与 TypedDict 表达 plan、phase receipt、inventory、rubric、owner 收窄事实和 acceptance receipt。
- 所有 class/function 具有中文 docstring，并包含 `Args`、`Returns`、`Raises`；公开与内部签名均显式类型化。
- strict parser 拒绝未知/缺失字段、NaN、非 JSON 值及 bool-as-int；canonical JSON 使用固定 UTF-8、键排序、紧凑分隔符并提供 SHA-256。
- package 输入通过 `resolve_package_config_path()` 和 `resolve_package_assets_path()` 解析：配置 regular-file canonical tree、诊断关键文件、`research_templates` 全部 `.md`/`.definition.json` 与根级 `定性分析模板.md` 均进入闭包；symlink、非普通文件和重复 canonical locator fail closed。
- 新验收模块未使用 `Any`、`object`、`cast`、`type: ignore`、`getattr`、`hasattr` 或 `noqa` 逃逸。

### Single owner ingress

- `write_run_summary_v3`、write manifest 与 repository owner 宽载荷只在单一 ingress 解析为不可变窄事实；未修改 owner 实现。
- repository inventory 只依赖 `SourceDocumentRepositoryProtocol`、`ProcessedDocumentRepositoryProtocol`、`DocumentBlobRepositoryProtocol`，不遍历或拼接 `workspace/portfolio`。
- repository 和 fixture ingress 均使用 frozen request dataclass，避免宽参数袋或 glue wrapper 在 evaluator 内传播。

### Deterministic evaluator

- 不执行 subprocess、网络或模型，不写 stdout；仅对已给定 fixture/artifact root 做有界只读解析。
- 检查 AAPL/Apple/technology 身份、DeepSeek 主写/MiMo 审计、fallback 禁用、run summary 发布与章节/audit closure、usage/cost/budget 和总 wall-clock/timeout receipts。
- 检查三组显式 SEC 窗口、as-of/future date、10-K/10-Q/DEF 14A、latest discovery、ingest、primary SHA、processed 状态指纹/reprocess 与价格 max-age/币种/日期/material 一致性。
- 检查 thesis、bear case、valuation、catalyst、risk、每章 `证据与出处` 四段非空、日期/locator、最终 source list、inventory/manifest closure 与唯一估值参考价格记录。
- 检查 13 个真实研究产物的 containment、symlink、绑定 SHA、workbook/report stale/tamper、bundle、source-map、三份 status snapshot、monitoring fingerprint/bound-source authenticity、`dry_run` 与 `automation=false`。
- sanitizer 仅扫描 acceptance-owned JSON 和 phase receipts；生产 artifacts 保持 byte-identical，不因 owner 内嵌 package 绝对路径单独失败，receipt 仅保存 package-relative locator + SHA-256。
- rubric 聚合严格产生 `PASS` / `PENDING_MANUAL_REVIEW` / `FAIL`；固定 clock 下 receipt canonical bytes 稳定。
- receipt residuals 明示 workbook open 状态、monitoring blocked/unbound source、自定义模板未纳入与可选 8-K 缺失等事实。

## Test coverage of plan assertions

focused 文件现有 40 个测试，覆盖：

- happy fixture 精确 85 分、13 个 artifact references、两次固定时钟字节一致且无 stdout；
- contract/plan/phase/inventory/rubric/receipt strict schema、unknown field、NaN 与 bool-as-int；
- 未填/部分人工 rubric 为 pending，完整低分为 fail；
- 缺 bear case、断 citation、三段 evidence、future source、processed missing/reprocess、价格/币种/日期不一致与 max-age；
- blocked budget、audit skipped、cost/wall-clock/timeout；
- 真实 `WriteModelUsageLedger.build_summary()` / `build_budget_summary()` 嵌套形状；
- stale/tampered progress、fake monitoring ready、monitoring input fingerprint 与 forged bound source；
- artifact symlink、绑定 SHA tamper、三份 status snapshot tamper；
- base template、`technology.definition.json`、`common.md`、`technology.md`、`consumer.md` 与 config manifest 漂移；package symlink/FIFO/duplicate locator；
- secret/auth/cookie/API key、POSIX/Windows home path、phase receipt 与 reviewer PII；
- 生产 artifact 内 owner 绝对路径不被复制、不触发单独失败且原字节不变；
- 三个 repository Protocol 是 inventory 唯一 owner 接口。

## Validation evidence

以下命令均在 2026-08-09 执行；摘要不包含 secret 值。

| Command | Exit | Evidence |
|---|---:|---|
| `uv run python -m pytest tests/test_investment_agent_acceptance.py -q` | 0 | initial `40 passed`；dual-review fix 后最终 `46 passed` |
| focused pytest + exact two-module coverage | 0 | dual-review fix 后 contracts `799 stmts / 94 miss / 88%`；evaluator `856 stmts / 115 miss / 87%`；total `87%`；`46 passed` |
| `uv run python -m pytest tests/cli/test_research_template_command.py -k "materialize or research_workbook or workbook_report or source_map or monitoring" -q` | 0 | `128 passed, 88 deselected` |
| `uv run python -m pytest tests/engine/test_source_list_builder.py tests/engine/test_execution_summary_builder.py tests/application/test_write_service.py -q` | 0 | `54 passed` |
| `uv run pyright utils/investment_agent_acceptance_contracts.py utils/investment_agent_acceptance_evaluator.py tests/test_investment_agent_acceptance.py` | 0 | `0 errors, 0 warnings, 0 informations` |
| `uv run pyright` | 1 | 17 diagnostics，全部位于未修改的 `dayu/engine/processors/docling_processor.py`、`tests/engine/test_docling_processor_helpers.py`、`tests/engine/test_web_tools.py`；无白名单文件诊断。主要为当前 docling export 与 requests 测试替身类型环境基线；未越界修改 |
| `uv run ruff check ...`（三个 Slice 文件） | 0 | default rules 全通过 |
| `uv run ruff check --select F,I ...`（三个 Slice 文件） | 0 | 全通过 |
| production key full-rule delta：`C416,C901,E501,FBT,PERF401,PLR0912,PLR0913,PLR0915,PLR2004,RUF022,TC001` | 0 | 两个新 production 模块全通过；无 God-function/高复杂度、长行或类型逃逸残留 |
| `ruff --select ALL` code multiset audit | nonzero（审计命令） | production 剩余仅中文 docstring/标点、显式异常消息风格：`COM812,D202,D400,D413,D415,EM101,EM102,RUF002,TRY003`；不属于项目 default，且与完整中文 docstring/已脱敏 domain exception 约束张力明确。测试另有项目 test idiom rules |
| HEAD same-file PLR/FURB stdin audit | nonzero（基线证明） | HEAD 同名 Slice 0 测试已存在 `PLR0915` 精确 `76`/`93` statements 与 `FURB162`；当前数值相同，未由 Slice 1 放大 |
| AST docstring audit | 0 | 两个新模块所有 class/function 均含 `Args`、`Returns`、`Raises` |
| forbidden escape `rg` audit | 1（无匹配是预期） | 无 `Any/object/cast/getattr/hasattr/type: ignore/noqa` |
| `git diff --check --` 三个代码白名单文件 | 0 | 无 whitespace error |

说明：全仓 pytest、handoff gates 与 `utils.investment_agent_acceptance` CLI verify 不属于本 Slice 白名单产物；CLI 尚未实现，按计划归 Slice 2。没有将未执行项表述为通过。

## Docs decision and residual ownership

- Slice 1 不修改文档入口；`docs/acceptance/investment-agent-aapl.md`、根 README 与 tests/README 明确归 Slice 4。
- Slice 2 owner：薄 CLI、prepare/preflight、allowlisted fake/live runner、阶段 argv/termination 与 plan drift-before-subprocess 集成。
- Slice 3 owner：现有 CLI 集成、恢复/重入、blocked monitoring 与正式 run artifact orchestration。
- Slice 4 owner：operator runbook、README 导航、deterministic/live lane 隔离说明。
- Slice 5 owner：只有重新取得精确 price/budget/token/request/wall-clock/external-call 授权后，才可执行一次 live acceptance；本实现不授权。
- 持续 residual：chapter evidence closure 不是逐句事实核验；fixed fixture 不能证明未来模型 prose 一致；package research tree 是保守闭包；technology monitoring 仍可有 unbound sources；workbook open count 与投资质量 verdict 必须分开报告。

## Handoff

实现无已知 plan gap。双路初审裁决与修复分别记录于：

- `docs/reviews/slice-1-aapl-acceptance-review-adjudication-20260809-013917-codex.md`
- `docs/reviews/slice-1-aapl-acceptance-review-fix-20260809-013917-codex.md`

双路复审结果：

- MiMo `docs/reviews/code-review-20260809-094216.md`：**PASS / ACCEPT**，open `H0/M0/L0`。
- DeepSeek `docs/reviews/code-review-20260809-094218.md`：overall **PASS**；报告中的 `M2/L1` observations 经 Controller 裁决均为 **REJECT/CLOSED non-defect**：固定 AAPL 验收语义无需引入 generic registry；固定四段 evidence 是已接受 contract，未来 schema evolution 保留为 residual；`.md` 不是 JSON，所有 `.json` 已在 path-only owner 调用前 strict preflight，已知 owner boundary limitation 不形成绕过。
- Controller closure 后，本 Slice 当前 open finding 为 `H0/M0/L0`。
- DS2/MiMo2 仍由 Slice 2 runner 与 Slice 3 partial receipt integration 承担；DS3 仍由 Slice 2 verify mode/preflight 的 deterministic/live plan binding 承担。fixture IDs 有意按 artifact 独立，绝不要求相等。

当前状态为 **DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT**。仅 Controller 可创建 accepted commit；implementation worker 未 commit/push/PR，也未进入 Slice 2。
