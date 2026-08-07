"""买方研究检查单（checklist）的构建层。

该模块把强类型的 :class:`~dayu.cli.research_template_definitions.ResearchTemplateDefinition`
桥接为一份可供分析师直接勾选、填写的研究检查单：在评分卡、证据要求、否决红旗、
输出结构之上，补充显式的「分析师填写字段」（analyst fill-in fields），从而把散落在
定义资产里的研究要求落地为一份可执行的工作清单。

设计约束：
- 本模块只负责「读取定义 + 组装检查单结构 + 渲染」，不承载任何写入、命令行或工作区
  物化副作用；文件写入由命令层复用既有的覆盖保护模式完成。
- 检查单不复制定义的建模职责：它直接读取 ``ResearchTemplateDefinition`` 的字段，只
  额外附加分析师填写语义，避免与定义层重复建模。
- JSON 输出面向机器消费，字段顺序稳定；Markdown 输出面向分析师，采用复选框式任务项。
"""

from __future__ import annotations

from dayu.cli.research_template_definitions import ResearchTemplateDefinition

# 检查单顶层的分析师填写字段（稳定英文键 -> 中文提示），用于机器输出与人读输出。
CHECKLIST_ANALYST_FIELDS: tuple[tuple[str, str], ...] = (
    ("analyst", "分析师"),
    ("review_date", "复核日期"),
    ("overall_conclusion", "总体结论"),
    ("recommendation", "投资建议"),
)


def build_research_checklist_payload(definition: ResearchTemplateDefinition) -> dict[str, object]:
    """把研究模板定义组装为机器可读的检查单负载。

    在定义的评分卡、证据要求、否决红旗、输出结构之上，为每一类研究项补充空白的
    分析师填写字段（如评分、是否已收集、是否触发、备注），并附加一个顶层的
    ``analyst_fields`` 对象供整份检查单的结论性填写。

    Args:
        definition: 已加载并校验的研究模板定义。

    Returns:
        字段顺序稳定、可直接被 ``json.dumps`` 处理的检查单字典；至少包含
        ``name``、``scorecard``、``evidence``、``red_flags``、``output_sections``
        与 ``analyst_fields``。

    Raises:
        无。
    """

    return {
        "name": definition.name,
        "title": definition.title,
        "schema_version": definition.schema_version,
        "scorecard": [
            {
                "key": dimension.key,
                "title": dimension.title,
                "weight": dimension.weight,
                "description": dimension.description,
                "analyst_score": None,
                "analyst_notes": "",
            }
            for dimension in definition.scorecard
        ],
        "evidence": [
            {
                "key": requirement.key,
                "description": requirement.description,
                "data_sources": list(requirement.data_sources),
                "collected": False,
                "analyst_notes": "",
            }
            for requirement in definition.evidence_requirements
        ],
        "red_flags": [
            {
                "flag": flag,
                "triggered": False,
                "analyst_notes": "",
            }
            for flag in definition.red_flags
        ],
        "output_sections": [
            {
                "key": section.key,
                "title": section.title,
                "guidance": section.guidance,
                "drafted": False,
                "analyst_notes": "",
            }
            for section in definition.output_sections
        ],
        "analyst_fields": {key: "" for key, _label in CHECKLIST_ANALYST_FIELDS},
    }


def render_research_checklist_markdown(definition: ResearchTemplateDefinition) -> str:
    """把研究模板定义渲染为分析师可读的 Markdown 检查单。

    每一类研究项均以复选框式任务项呈现，并在行内保留显式的分析师填写占位，方便
    分析师逐项勾选、评分与记录备注。

    Args:
        definition: 已加载并校验的研究模板定义。

    Returns:
        以换行分隔、以复选框（``- [ ]``）组织的 Markdown 文本，结尾带单个换行。

    Raises:
        无。
    """

    lines: list[str] = [f"# 研究检查单：{definition.name}\t{definition.title}", ""]

    lines.append("## 分析师信息")
    for key, label in CHECKLIST_ANALYST_FIELDS:
        lines.append(f"- [ ] {key}（{label}）：______")
    lines.append("")

    lines.append("## 评分卡")
    for dimension in definition.scorecard:
        lines.append(
            f"- [ ] [权重 {dimension.weight}] {dimension.key}（{dimension.title}）："
            f"{dimension.description} — 打分：____ 备注：____"
        )
    lines.append("")

    lines.append("## 证据要求")
    for requirement in definition.evidence_requirements:
        sources = "、".join(requirement.data_sources)
        lines.append(
            f"- [ ] {requirement.key}：{requirement.description}"
            f"（数据源：{sources}） — 备注：____"
        )
    lines.append("")

    lines.append("## 否决红旗")
    for flag in definition.red_flags:
        lines.append(f"- [ ] {flag} — 备注：____")
    lines.append("")

    lines.append("## 输出结构")
    for section in definition.output_sections:
        lines.append(
            f"- [ ] {section.key}（{section.title}）：{section.guidance} — 备注：____"
        )
    lines.append("")

    return "\n".join(lines) + "\n"
