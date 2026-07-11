# Claude Outbox

Status: READY_FOR_CODEX_REVIEW
Message ID: codex-research-template-checklist-20260712-053720
Task: EXECUTE_RESEARCH_TEMPLATE_CHECKLIST

READY_FOR_CODEX_REVIEW

## 实现摘要

在既有可执行研究模板定义（`ResearchTemplateDefinition`）之上，新增一层「分析师检查单」桥接：
把评分卡、证据要求、否决红旗、输出结构落地为一份可勾选、可填写的研究检查单，并补充显式的
分析师填写字段。提供两条 CLI 命令：

- `research-template checklist <name>`：只读预览，默认 Markdown（复选框式任务项），`--json` 输出机器可读负载；不物化 workspace。
- `research-template materialize-checklist <name>`：可选写入，默认落到 `{base}/assets/research_templates/{name}.checklist.md`，支持 `--output` 自定义路径，`--overwrite` 缺省时保护已存在文件。

builder 层（`dayu/cli/research_template_checklist.py`）只负责「读取定义 + 组装结构 + 渲染」，
不承载写入/命令行副作用；文件写入复用 `copy_research_template` 相同的覆盖保护模式，位于命令层。

## 变更文件

- `dayu/cli/research_template_checklist.py`（新增）：`build_research_checklist_payload`、`render_research_checklist_markdown`、`CHECKLIST_ANALYST_FIELDS`。
- `dayu/cli/commands/research_template.py`：新增 `materialize_research_checklist` 写入助手、`_run_checklist`/`_run_materialize_checklist` 处理器、dispatch 分支与 import。
- `dayu/cli/arg_parsing.py`：注册 `checklist` 与 `materialize-checklist` 子命令。
- `tests/cli/test_research_template_command.py`：新增 14 个聚焦测试（happy path、未知模板、JSON、Markdown、写保护、overwrite、参数解析、既有命令回归由整文件覆盖）。
- `README.md`：在研究模板库小节补充 `checklist`/`materialize-checklist` 命令示例。

## 验证命令与结果

- `python -m pytest tests/cli/test_research_template_command.py tests/cli/test_research_template_definitions.py -q`
  → **221 passed**（含新增 14 个 checklist 测试；既有命令全部回归通过）。
- `ruff check dayu/cli/research_template_checklist.py dayu/cli/commands/research_template.py dayu/cli/arg_parsing.py tests/cli/test_research_template_command.py`
  → **All checks passed!**
- `pyright dayu/cli/research_template_checklist.py dayu/cli/commands/research_template.py dayu/cli/arg_parsing.py`
  → **0 errors, 0 warnings**（生产源全干净）。
- `pyright tests/cli/test_research_template_command.py`
  → **25 errors**；经 `git stash` 对比基线（HEAD）同样为 **25 errors**：本次改动未新增/扩散任何 pyright 报错，25 条均为既有测试代码中对 `dict[str, object]` 直接索引的历史问题，位于本次未触及的行（均 < 3430，新增测试从 ~4640 起）。新增测试代码经 `isinstance` 收窄，pyright 干净。
- 覆盖率：`--cov=dayu.cli.research_template_checklist` → **100%**（29/29 行）。
- 手工冒烟：`consumer/cyclical/financial/technology` 四模板的 `checklist`（Markdown 与 `--json`）均输出完整检查单；未知模板返回清晰错误并退出码 1；`materialize-checklist` 首次写入成功、二次未加 `--overwrite` 报 “already exists” 退出码 1、加 `--overwrite` 成功；`research-template list` 等既有命令不受影响。

## 接受标准对照

- `research-template list` 继续可用：✅（回归测试通过）。
- 四个行业模板可在不物化 workspace 的情况下预览完整检查单：✅。
- JSON 检查单包含 template name、scorecard、evidence、red flags、output sections、analyst fields：✅。
- Markdown 检查单可读且含复选框式分析师任务项：✅。
- 未知模板与 overwrite 冲突返回清晰错误：✅。
- 聚焦测试覆盖 happy path、未知模板、JSON、Markdown、写保护、overwrite、既有命令回归：✅。
- 受影响生产源 ruff/pyright 通过：✅（pyright 测试文件的既有 25 条报错已如上说明，非本次引入）。

## 范围偏差

- 无。严格限定在 `dayu/cli/` 检查单构建与两条 `research-template` 子命令、聚焦测试与相关 README。未触碰下载/Docling/Fins 存储/LLM runner/Web UI/WeChat UI/模型 provider；未新增网络调用或运行时依赖；未替换既有 Markdown 模板；未削弱既有 rollback/manifest/source-map/write 行为。未改动 `.codegraph/`、`docs/reviews/`、`docs/review/CLAUDE_TESTEVAL_CHECKLIST.md`、`docs/review/claude_status_last_hash.txt`；未提交、未推送。
