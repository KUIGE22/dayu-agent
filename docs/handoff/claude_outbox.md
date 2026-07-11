# Claude Outbox

Status: READY_FOR_CODEX_REVIEW
Message ID: codex-research-template-v2-20260712-051503
Task: EXECUTE_RESEARCH_TEMPLATE_V2

## Summary

在既有 Markdown 研究模板之上新增了一层轻量、强类型的「可执行模板定义」层。每个行业模板的
评分卡（scorecard）、证据要求（evidence requirements）、否决红旗（red flags）与输出结构
（output sections）被抽象为随包分发的 JSON 资产，并通过三个只读 CLI 命令暴露：
`scorecard`、`evidence`、`schema`。既有 Markdown 命令（`list`/`show`/`compose`/物化流水线等）
完全保持向后兼容，未做任何行为改动。

## Changed Files

新增：
- `dayu/cli/research_template_definitions.py` — 强类型定义模型（`ResearchTemplateDefinition` 等
  frozen dataclass）+ 严格校验加载器 + JSON 序列化助手。
- `dayu/assets/research_templates/common.definition.json`
- `dayu/assets/research_templates/consumer.definition.json`
- `dayu/assets/research_templates/cyclical.definition.json`
- `dayu/assets/research_templates/financial.definition.json`
- `dayu/assets/research_templates/technology.definition.json`
- `tests/cli/test_research_template_definitions.py` — 15 个聚焦单测。

修改：
- `dayu/cli/commands/research_template.py` — 新增 `scorecard`/`evidence`/`schema` 三个只读命令的
  分发与处理函数，及导入。未改动任何既有函数。
- `dayu/cli/arg_parsing.py` — 为三个新命令新增子解析器（各带 `name` 位置参数与 `--json`）。
- `pyproject.toml` — `dayu.assets` package-data 新增 `research_templates/*.definition.json`，
  使定义资产随 wheel/sdist 分发。
- `README.md` — 研究模板库示例新增三个只读命令，并补充一行说明（无需物化 workspace 即可查看）。

## Design Notes

- 定义资产命名为 `{name}.definition.json`，与同名 `{name}.md` 互补而非替代；既有 Markdown 加载器
  仍只 glob `*.md`，不受影响。
- 加载器对结构、类型、完整性做严格校验：`schema_version` 必须为 1；文件名与 `name` 字段必须一致；
  scorecard/evidence/red_flags/output_sections 均不得为空；key 去重；weight 必须为正整数；
  畸形 JSON 与类型错误抛出带文件路径与字段路径的 `ValueError`，未知模板抛出 `FileNotFoundError`。
- 公共模型全部为具体类型（`str`/`int`/`tuple[...]`）；`object` 仅出现在 JSON 解析边界，与本模块既有
  `dict[str, object]` + isinstance 收窄的惯用法一致。
- `data_sources` 标识与既有 monitoring source-map 层（`_TEMPLATE_DATA_SOURCE_CANDIDATES` /
  `_DATA_SOURCE_BINDING_CANDIDATES`）中的命名保持一致，便于后续工作流衔接。

## Verification Commands & Results

1. 新增单测（venv: `.venv/Scripts/python.exe`）
   - `python -m pytest tests/cli/test_research_template_definitions.py -q`
   - 结果：**15 passed**。
2. 既有 research-template 命令回归
   - `python -m pytest tests/cli/test_research_template_command.py -q`
   - 结果：**192 passed**（向后兼容未破坏）。
3. Ruff（受影响文件）
   - `python -m ruff check dayu/cli/research_template_definitions.py dayu/cli/commands/research_template.py dayu/cli/arg_parsing.py tests/cli/test_research_template_definitions.py`
   - 结果：**All checks passed!**
4. Pyright（受影响文件）
   - `python -m pyright dayu/cli/research_template_definitions.py dayu/cli/commands/research_template.py dayu/cli/arg_parsing.py tests/cli/test_research_template_definitions.py`
   - 结果：生产代码 **0 error**。测试文件仅报 1 条 `Import "pytest" could not be resolved (reportMissingImports)`，
     属 **既有环境基线**——对既有 `tests/cli/test_research_template_command.py` 运行 pyright 会在
     同一行 `import pytest` 报出完全相同的错误（该文件另有 26 条既有报错）。本次改动未新增或扩散任何
     生产代码类型错误。
5. 打包发现（wheel 构建）
   - 通过 `setuptools.build_meta.build_wheel` 构建 `dayu_agent-0.1.4-py3-none-any.whl`。
   - 结果：5 个 `*.definition.json` 均被打入 wheel；6 个 `research_templates/*.md` 仍在（未受影响）。
   - 构建产生的 `build/`、`*.egg-info/` 临时目录已删除，工作树保持干净。
6. CLI 端到端冒烟（真实入口 `python -m dayu.cli`）
   - `research-template scorecard consumer` → rc=0，输出评分卡。
   - `research-template schema technology --json` → keys 为
     `[evidence_requirements, name, output_sections, red_flags, schema_version, scorecard, title]`，
     权重 `[30, 25, 25, 20]`。
   - `research-template evidence nope` → rc=1，stderr 明确列出可用模板。
   - `research-template list` → rc=0，仍列出 5 个 Markdown 模板。

## Acceptance Criteria Mapping

- `research-template list` 继续工作 → 验证 5、6。
- 无需物化 workspace 即可查看 scorecard 与 evidence → `scorecard`/`evidence` 直接读取包内资产（验证 6）。
- 加载器对畸形/残缺定义给出清晰错误 → 单测 `malformed_json`/`incomplete_definition`/
  `wrong_field_type`/`name_mismatch`（验证 1）。
- 打包发现包含定义资产 → 验证 5。
- 聚焦测试覆盖 happy-path、unknown、malformed、CLI scorecard/evidence、Markdown 向后兼容 → 验证 1、2。
- 受影响 ruff/pyright 通过 → 验证 3、4（pyright 生产代码 0 error，测试仅 1 条既有基线报错）。

## Scope Deviations

无。严格限定在 inbox 的 Allowed Scope 内：仅新增定义层与只读命令，未触及 filing 下载、Docling、
Fins storage、LLM runners、Web/WeChat UI、模型供应商配置；未引入网络调用或新运行时依赖；未替换或
改动任何既有 Markdown 模板与 rollback/manifest/source-map/write 流水线行为；未修改无关未跟踪文件
（`.codegraph/`、`docs/reviews/`、`docs/review/CLAUDE_TESTEVAL_CHECKLIST.md` 等均未触碰）。

Ready for Codex review and commit.
