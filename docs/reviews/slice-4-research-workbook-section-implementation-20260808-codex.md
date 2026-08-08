# Slice 4 W16 研究手册章节 helper 实现记录

- **日期**: 2026-08-08
- **Gate**: implementation
- **Work unit**: CLI Write 架构重构
- **Slice**: Slice 4 / W16
- **基线**: `86538d2 gateflow: accept cli write architecture plan v4.5`
- **分支**: `codex/dual-model-research-mvp`
- **接受计划**:
  `docs/plans/2026-08-07-cli-write-architecture-refactor.md`
- **状态**: DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT

## 范围与非目标

允许范围：

- `dayu/cli/commands/research_workbook.py`
- 必要的直接测试与 `tests/README.md`
- 本实现记录

实际修改：

- `dayu/cli/commands/research_workbook.py`
- `docs/reviews/slice-4-research-workbook-section-implementation-20260808-codex.md`

非目标：

- 不改变 public API、研究手册 JSON shape、ID 生成材料或校验规则。
- 不修改 public builder 返回签名以及模块内既有的 15 个
  `dict[str, object]` 函数签名/19 处 occurrence。
- 不治理模块内其他嵌套结构、存量类型契约或存量 Ruff finding。
- 不进入后续 slice、code review、commit、push 或 PR gate。

## 实现摘要

1. 新增三个模块私有 TypedDict，字段全部 required：
   - `_ResearchWorkbookEvidence`
   - `_ResearchWorkbookItem`
   - `_ResearchWorkbookSection`
2. 新增 exact helper：
   `_append_research_workbook_section(
   sections: list[_ResearchWorkbookSection], *,
   normalized: str, current_title: str, current_category: str,
   current_items: list[str]) -> None`。
3. helper 保留原 nested 实现的 early return、`len(sections)` 位置索引、
   section/item 哈希材料、截断长度、默认字段和值以及 append 时序。
4. 删除 nested `append_current_section`，把 heading 切换与 EOF 两个 flush
   改为直接调用模块 helper；heading flush 后的 `current_items = []` 仍由
   caller 在原位置执行。
5. 将 builder 局部 `sections` 精化为
   `list[_ResearchWorkbookSection]`，helper 局部 `items` 精化为
   `list[_ResearchWorkbookItem]`。
6. 模块概览、helper 与修改后的 public builder 使用中文文档说明；两个函数
   均包含 Args、Returns、Raises。
7. 未新增 `Any`、`object`、`cast`、`type: ignore` 或 glue seam。

## 测试与 README 决策

未修改测试。现有 35 项 `research_workbook` 聚焦测试已直接覆盖本次边界：

- 完整 section/item shape 与默认字段；
- stable IDs；
- 重复 heading/bullet 的 section/item ID 唯一性；
- UTF-8 BOM；
- 生成 payload 自验证；
- update、rollback、report、status 等既有调用路径。

因此新增只验证私有实现形态的测试会耦合内部结构，不能增加真实行为保障。

未修改 README。本次是私有 helper 提取与局部类型精化，不改变用户命令、
导入路径、参数、输出或架构边界；根 README 与 `tests/README.md` 均没有失配
内容。

## 验证结果

### 聚焦行为测试

```text
source .venv/bin/activate
pytest tests/cli/test_research_template_command.py -k "research_workbook" -q
→ 35 passed, 177 deselected
```

完整直接测试文件：

```text
source .venv/bin/activate
pytest tests/cli/test_research_template_command.py -q
→ 212 passed
```

### 类型检查

```text
source .venv/bin/activate
pyright dayu/cli/commands/research_workbook.py \
  tests/cli/test_research_template_command.py
→ 0 errors, 0 warnings, 0 informations

pyright dayu/cli/
→ 0 errors, 0 warnings, 0 informations
```

### Ruff

```text
source .venv/bin/activate
ruff check --select F,I dayu/cli/commands/research_workbook.py
→ All checks passed
```

全规则 HEAD 差分：

```text
current → 5 × TRY004
HEAD    → 5 × TRY004
delta   → 0
```

5 个 TRY004 均为本次未触及的存量位置；没有新增 Ruff finding。

### 精确单文件覆盖率

使用独立临时 coverage data file、`--timid --branch` 和完整 212 项直接测试：

```text
dayu/cli/commands/research_workbook.py
covered lines: 553 / 617
covered branches: 220 / 284
exact total coverage: 85.79356270810212%
exact statement coverage: 89.62722852512155%
→ PASS（>= 80%）
```

### 结构与契约审计

```text
nested append_current_section definitions → 0
module _append_research_workbook_section definitions → 1
direct _append_research_workbook_section calls → 2
```

AST 仅统计函数参数和返回注解：

```text
dict[str, object] signature functions → 15
dict[str, object] signature occurrences → 19
```

JSON shape、stable ID、重复输入、BOM 与 payload 自验证语义由上述 35 项聚焦
测试通过证明。`git diff --check` 通过。

## 初审与 Controller 裁决

初审输入：

- DeepSeek:
  `docs/reviews/code-review-20260808-011443.md`
  （PASS，LOW-01/LOW-02）
- MiMo:
  `docs/reviews/code-review-20260808-011444.md`
  （PASS，open High/Medium/Low = 0）

Controller 裁决：

- **DeepSeek LOW-01**: ACCEPTED / FIXED。helper Raises 文案由绝对的“无。”
  改为“本函数不显式抛出异常。”，不枚举系统级不可恢复错误。
- **DeepSeek LOW-02**: REJECTED / NON-DEFECT / OUT OF SCOPE。模块概览及本次
  新增、修改函数使用完整中文 docstring 是 AGENTS 要求；其余存量英文函数
  未由 W16 修改，不扩大治理范围。
- **MiMo O-1**: REJECTED / OUT OF SCOPE。public builder TypedDict 化会改变
  accepted plan 明确保留的存量 public contract。
- **MiMo O-2**: REJECTED / STYLE OBSERVATION。AGENTS 要求完整异常说明，
  因此不省略 Raises 段。

Fix 记录：
`docs/reviews/slice-4-research-workbook-section-fix-20260808-codex.md`。

## 双路 re-review 闭环

- DeepSeek:
  `docs/reviews/code-review-20260808-012228.md`
  （PASS，open High/Medium/Low = 0）
- MiMo:
  `docs/reviews/code-review-20260808-012229.md`
  （PASS，open High/Medium/Low = 0）

两路复审均确认 LOW-01 的 docstring 修复精确且无行为变化，LOW-02、O-1、
O-2 的 Controller 裁决与 scope 边界正确。初审 4 项全部 CLOSED，W16 exact
contract、测试、pyright、coverage、Ruff 与结构门禁保持 PASS；没有 open
finding。

## Plan gap 与 residual risk

- **Plan gap**: 无。accepted exact contract 可直接实施，未发现契约冲突。
- **当前功能风险**: 无已知未覆盖风险；heading 与 EOF 两条 flush 路径均由
  现有行为测试覆盖。
- **存量 Ruff TRY004**: 非本次引入，HEAD delta 为零；归入未来独立 lint
  cleanup work unit，不扩大 W16 scope。
- **下一 gate**: accepted slice commit。当前实现状态为
  DUAL RE-REVIEW PASS / READY FOR ACCEPTED COMMIT。
