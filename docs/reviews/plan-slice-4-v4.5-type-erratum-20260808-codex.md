# Slice 4 W16 v4.5 类型勘误记录

- **日期**: 2026-08-08
- **Gate**: plan fix / erratum
- **基线计划**: v4.4 ACCEPTED / MIMO RE-REVIEW PASS
- **接受计划**: v4.5 ACCEPTED / DUAL PLAN RE-REVIEW PASS
- **控制项**: W16-CTRL-01
- **状态**: PLAN ERRATUM ACCEPTED / DUAL PLAN RE-REVIEW PASS

## 输入证据

- DeepSeek planreview:
  `docs/reviews/plan-review-20260808-002853.md`
- MiMo planreview:
  `docs/reviews/plan-review-20260808-002854.md`
- DeepSeek 初次 re-review:
  `docs/reviews/plan-review-20260808-004533.md`
- MiMo 初次 re-review:
  `docs/reviews/plan-review-20260808-004534.md`
- DeepSeek final re-review:
  `docs/reviews/plan-review-20260808-005559.md`
- MiMo final re-review:
  `docs/reviews/plan-review-20260808-005600.md`
- MiMo corrective re-review:
  `docs/reviews/plan-review-20260808-010404.md`
- Master plan:
  `docs/plans/2026-08-07-cli-write-architecture-refactor.md`
- 源码基线:
  `dayu/cli/commands/research_workbook.py`
- 直接测试:
  `tests/cli/test_research_template_command.py`

## 双路结论

两路独立 planreview 一致确认原 Slice 4 exact signature
`sections: list[dict[str, object]]` 会为模块级 helper 新增 `object` 参数，
直接违反 AGENTS “禁止使用 `object`、`Any` 或其他无法严格类型检查的签名”
硬约束。当前 nested helper 无参数签名，因此该问题必须在提取前以 plan
erratum 修正。

两路还共同确认：

- nested helper 当前仅构造固定 section/item 字段，适合模块私有 TypedDict。
- 传入同一个可变 `sections` 列表可完整保留 `len(sections)` 位置索引与重复
  heading/bullet 的 ID 防碰撞语义。
- public builder 的 `dict[str, object]` 返回类型及模块内同类签名是存量契约，
  不应在 W16 顺手全面治理。
- 现有测试已经覆盖完整结构、stable IDs、重复输入唯一性、BOM、category 和
  payload 自验证。

## Controller 裁决

Controller 接受 Medium plan contract finding，并采纳 MiMo 更精确的三个
TypedDict 方案：

1. `_ResearchWorkbookEvidence`
   - `source: str`
   - `reference: str`
   - `finding: str`
2. `_ResearchWorkbookItem`
   - `item_id: str`
   - `prompt: str`
   - `status: str`
   - `response: str`
   - `evidence: list[_ResearchWorkbookEvidence]`
   - `analyst_notes: str`
   - `evidence_required: bool`
3. `_ResearchWorkbookSection`
   - `section_id: str`
   - `title: str`
   - `category: str`
   - `items: list[_ResearchWorkbookItem]`

Exact helper contract 修正为：

```python
def _append_research_workbook_section(
    sections: list[_ResearchWorkbookSection],
    *,
    normalized: str,
    current_title: str,
    current_category: str,
    current_items: list[str],
) -> None:
```

同时要求局部 `sections: list[_ResearchWorkbookSection]` 与
`items: list[_ResearchWorkbookItem]` 类型精化，heading 切换和 EOF 两个
flush 调用点显式传递五个参数。不得新增 `Any`、`object`、`cast`、
`type: ignore` 或 glue wrapper。

## 替代方案裁决

- **原 `list[dict[str, object]]`**: REJECTED。直接违反 AGENTS 硬约束。
- **DeepSeek 两 TypedDict + `list[dict[str, str]]` evidence**: REJECTED。
  虽可通过类型检查，但 evidence 已有稳定的 `source/reference/finding` schema；
  独立 TypedDict 字段更精确、自文档化，且成本最小。
- **跨模块 `JsonObject` alias**: REJECTED。字段约束不足，并可能引入不必要的
  CLI→Fins 依赖。
- **手写递归 union**: REJECTED。无法清晰表达字段结构，脆弱且维护成本高。
- **Protocol**: REJECTED。目标是纯数据容器，不存在行为契约，属于过度设计。
- **保留 nested helper**: REJECTED。违背 W16 消除无必要嵌套函数的目标。
- **全面替换模块存量 `dict[str, object]` 签名**: DEFERRED /
  OUT OF SCOPE。本模块 15 个存量函数签名共含 19 处
  `dict[str, object]`（含 public builder 与 2 个私有 helper），均不是本次
  新增；全面治理需独立 work unit 与 public contract 评估。

## 初次 re-review 与 Controller 裁决

DeepSeek 与 MiMo 初次 re-review 均给出 PASS，且均无 High/Medium
finding。Controller 对 Low observations 逐项裁决如下：

- **DeepSeek L1 — “17 个存量签名”计数表述精度**:
  ACCEPTED / FIXED。源码精确事实为：本模块 15 个存量函数签名共含 19 处
  `dict[str, object]`，其中 13 个非私有函数签名共 17 处，另 2 个私有
  helper 各 1 处。Master plan 的 changelog、W16 摘要、Slice 4 实施段与
  尾部状态，以及本 artifact，已统一为该事实；W16 scope 不变。
- **DeepSeek L2 — `current_items = []` 时序未显式标注**:
  REJECTED / NON-DEFECT。计划已限定仅替换两个 flush 调用点并保持 helper
  逻辑、调用时序与 payload 语义；调用方现有 reset 留在原位，不属于新增
  helper contract。无需把既有相邻语句复制进计划。
- **DeepSeek L3 — `_ResearchWorkbookEvidence` 与
  `deepcopy(evidence_records)` 的类型分界**:
  REJECTED / NON-DEFECT。该观察指向未来全面 TypedDict 化；当前 W16 仅精化
  section 构造路径，公开 update 边界与存量 `dict[str, object]` 契约明确
  out of scope，不存在当前触发路径。
- **DeepSeek L4 — 未显式覆盖
  `from __future__ import annotations` 兼容性**:
  REJECTED / NON-DEFECT。源码已启用该 future import，初次 review 已验证
  TypedDict 兼容，且 plan 的 pyright 门禁直接覆盖；无需把已验证的语言机制
  再写成实施步骤。
- **MiMo LOW-01 — `items` 局部变量名遮蔽**:
  REJECTED / NON-DEFECT。两个 `items` 位于不同函数作用域，运行时与静态类型
  均无冲突；要求 docstring 解释内部局部变量名不构成功能契约。
- **MiMo LOW-02 —
  `from __future__ import annotations` 对 runtime introspection 的影响**:
  REJECTED / NON-DEFECT。当前模块无 TypedDict 注解运行时反射；观察仅描述
  假设性未来 schema 工具，不属于 W16 风险。
- **MiMo LOW-03 — `total=True` 与未来 schema 演进**:
  REJECTED / NON-DEFECT。当前固定 JSON shape 的全部字段均必填，
  `total=True` 是精确表达；未来新增可选字段应由独立 schema 变更处理。

除接受并修正 DeepSeek L1 外，其余 observations 均不要求扩大计划或修改
code/tests。

## Final dual re-review 与计数纠正闭环

- DeepSeek final re-review
  `docs/reviews/plan-review-20260808-005559.md`: PASS，open
  High/Medium/Low = 0，旧 findings 全部 CLOSED。
- MiMo final re-review
  `docs/reviews/plan-review-20260808-005600.md`: PASS，但其 LOW 计数把 4 处
  函数体局部变量注解误计入函数签名。
- MiMo corrective re-review
  `docs/reviews/plan-review-20260808-010404.md`: PASS；AST 仅检查参数与返回
  注解，确认精确事实仍为 15 个函数签名/19 处 occurrence
  （13 个非私有函数/17 处 + 2 个私有 helper/2 处）。005600 LOW 已标记为
  reviewer measurement error 并 CLOSED，最终 open High/Medium/Low = 0。

Controller 接受 corrective 结论。三 TypedDict、exact helper、两个 flush
调用点、35 项测试门禁、pyright 门禁与其他 slice 零语义变化均通过最终
复审；所有 findings 已闭环，v4.5 可接受。

## Master plan 更新

已完成：

- header、状态行和底部状态统一更新为
  `v4.5 ACCEPTED / DUAL PLAN RE-REVIEW PASS`。
- v4.4 ACCEPTED / MIMO RE-REVIEW PASS 作为历史版本保留。
- 审查来源追加两份 Slice 4 planreview。
- 新增 v4.4→v4.5 W16-CTRL-01 changelog。
- §1.7 W16 摘要与 Slice 4 实施段写入三 TypedDict 全字段、helper exact
  signature、局部类型精化、两调用点、禁止项和验证命令。
- 架构树 `_append_current_section` 错名改为
  `_append_research_workbook_section`。
- 其余 slices 零语义变化。

## 验证与范围

Plan 修订前只读基线：

```text
pytest tests/cli/test_research_template_command.py -k research_workbook -q
→ 35 passed, 177 deselected

pyright dayu/cli/commands/research_workbook.py \
  tests/cli/test_research_template_command.py
→ 0 errors, 0 warnings, 0 informations
```

本次只修改 master plan 并新增本 artifact；没有修改 code/tests/README。
最终执行版本锚点检索、W16 symbol/type 检索与 `git diff --check`。

## Residual risk 与下一 gate

- v4.5 已通过最终双路 plan re-review；可以按 accepted plan 实施 Slice 4。
- 本模块 15 个存量函数签名共含 19 处 `dict[str, object]`（含 public
  builder 与 2 个私有 helper），由未来独立 typed-workbook contract work
  unit 负责；W16 不扩 scope。
- 无 open High/Medium/Low finding，无未分类 plan risk。
