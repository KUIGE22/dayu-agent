"""买方研究模板的可执行定义层。

该模块在既有 Markdown 研究模板之上，提供一层轻量、强类型的模板定义：
把每个行业模板的评分卡（scorecard）、证据要求（evidence requirements）、
否决红旗（red flags）与输出结构（output sections）从散文式的 Markdown 抽象为
可被 CLI 与后续工作流稳定读取的结构化资产。

设计约束：
- 定义资产为随包分发的 JSON 文件，命名为 ``{name}.definition.json``，与同名
  ``{name}.md`` Markdown 模板互补，不替代它。
- 加载器对结构、字段类型与完整性做严格校验，遇到畸形或残缺定义时抛出带上下文的
  ``ValueError``，未知模板抛出 ``FileNotFoundError``。
- 模块只负责「解析 + 校验 + 建模」，不承载任何写入、渲染或命令行副作用。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dayu.cli.research_template_assets import normalize_research_template_name
from dayu.startup.config_file_resolver import resolve_package_assets_path

DEFINITION_SCHEMA_VERSION = 1
_TEMPLATE_DIR_NAME = "research_templates"
_DEFINITION_SUFFIX = ".definition.json"


@dataclass(frozen=True)
class ScorecardDimension:
    """评分卡中的一个评估维度。

    Attributes:
        key: 稳定英文键，用于机器引用。
        title: 中文维度名称。
        weight: 该维度在评分卡中的权重（正整数）。
        description: 该维度考察什么、如何判断的说明。
    """

    key: str
    title: str
    weight: int
    description: str


@dataclass(frozen=True)
class EvidenceRequirement:
    """一条必查证据要求。

    Attributes:
        key: 稳定英文键，用于机器引用。
        description: 需要收集或验证的证据说明。
        data_sources: 该证据可能来源的占位数据源标识元组。
    """

    key: str
    description: str
    data_sources: tuple[str, ...]


@dataclass(frozen=True)
class OutputSection:
    """研究输出报告中的一个结构化章节。

    Attributes:
        key: 稳定英文键，用于机器引用。
        title: 中文章节名称。
        guidance: 该章节应写什么、如何组织证据的指引。
    """

    key: str
    title: str
    guidance: str


@dataclass(frozen=True)
class ResearchTemplateDefinition:
    """一个研究模板的完整可执行定义。

    Attributes:
        schema_version: 定义模式版本，当前恒为 ``1``。
        name: 稳定模板名，与文件名及同名 Markdown 模板一致。
        title: 中文模板标题。
        scorecard: 评分维度元组。
        evidence_requirements: 证据要求元组。
        red_flags: 否决红旗文本元组。
        output_sections: 输出结构章节元组。
    """

    schema_version: int
    name: str
    title: str
    scorecard: tuple[ScorecardDimension, ...]
    evidence_requirements: tuple[EvidenceRequirement, ...]
    red_flags: tuple[str, ...]
    output_sections: tuple[OutputSection, ...]


def load_research_template_definition(name: str) -> ResearchTemplateDefinition:
    """按稳定名加载并校验一个研究模板定义。

    Args:
        name: 模板名，如 ``common``、``consumer``、``cyclical``、``financial``、
            ``technology``；大小写与首尾空白会被规范化。

    Returns:
        校验通过的 :class:`ResearchTemplateDefinition` 实例。

    Raises:
        FileNotFoundError: 指定名称没有对应的定义资产文件。
        ValueError: 定义资产不是合法 JSON 对象，或结构、类型、完整性校验失败。
    """

    definition_path = _resolve_definition_path(name)
    payload = _load_json_object(definition_path)
    return _parse_definition(payload, source=definition_path)


def list_research_template_definitions() -> tuple[ResearchTemplateDefinition, ...]:
    """加载并校验所有随包分发的研究模板定义。

    Returns:
        按名称排序的定义元组。

    Raises:
        ValueError: 任一定义资产结构、类型或完整性校验失败。
    """

    definitions: list[ResearchTemplateDefinition] = []
    for definition_path in sorted(_resolve_definition_dir().glob(f"*{_DEFINITION_SUFFIX}")):
        payload = _load_json_object(definition_path)
        definitions.append(_parse_definition(payload, source=definition_path))
    return tuple(definitions)


def definition_to_payload(definition: ResearchTemplateDefinition) -> dict[str, object]:
    """把一个模板定义序列化为可直接 JSON 输出的字典。

    Args:
        definition: 已构建的模板定义。

    Returns:
        字段顺序稳定、可被 ``json.dumps`` 处理的字典。

    Raises:
        无。
    """

    return {
        "schema_version": definition.schema_version,
        "name": definition.name,
        "title": definition.title,
        "scorecard": [
            {
                "key": dimension.key,
                "title": dimension.title,
                "weight": dimension.weight,
                "description": dimension.description,
            }
            for dimension in definition.scorecard
        ],
        "evidence_requirements": [
            {
                "key": requirement.key,
                "description": requirement.description,
                "data_sources": list(requirement.data_sources),
            }
            for requirement in definition.evidence_requirements
        ],
        "red_flags": list(definition.red_flags),
        "output_sections": [
            {
                "key": section.key,
                "title": section.title,
                "guidance": section.guidance,
            }
            for section in definition.output_sections
        ],
    }


def scorecard_to_payload(definition: ResearchTemplateDefinition) -> dict[str, object]:
    """构建仅含评分卡的机器可读输出。

    Args:
        definition: 已构建的模板定义。

    Returns:
        含模板名、标题与评分维度列表的字典。

    Raises:
        无。
    """

    return {
        "name": definition.name,
        "title": definition.title,
        "scorecard": [
            {
                "key": dimension.key,
                "title": dimension.title,
                "weight": dimension.weight,
                "description": dimension.description,
            }
            for dimension in definition.scorecard
        ],
    }


def evidence_to_payload(definition: ResearchTemplateDefinition) -> dict[str, object]:
    """构建仅含证据要求的机器可读输出。

    Args:
        definition: 已构建的模板定义。

    Returns:
        含模板名、标题与证据要求列表的字典。

    Raises:
        无。
    """

    return {
        "name": definition.name,
        "title": definition.title,
        "evidence_requirements": [
            {
                "key": requirement.key,
                "description": requirement.description,
                "data_sources": list(requirement.data_sources),
            }
            for requirement in definition.evidence_requirements
        ],
    }


def _resolve_definition_dir() -> Path:
    """解析随包分发的研究模板定义目录。

    Returns:
        ``dayu/assets/research_templates`` 的绝对路径。

    Raises:
        FileNotFoundError: 目录不存在。
    """

    definition_dir = resolve_package_assets_path() / _TEMPLATE_DIR_NAME
    if not definition_dir.is_dir():
        raise FileNotFoundError(f"research template directory not found: {definition_dir}")
    return definition_dir


def _resolve_definition_path(name: str) -> Path:
    """把模板名解析为其定义资产文件路径。

    Args:
        name: 模板名。

    Returns:
        定义资产文件的绝对路径。

    Raises:
        FileNotFoundError: 指定名称没有对应的定义资产文件。
        ValueError: 名称为空或包含非法路径字符。
    """

    normalized = normalize_research_template_name(name)
    definition_path = _resolve_definition_dir() / f"{normalized}{_DEFINITION_SUFFIX}"
    if not definition_path.is_file():
        available = ", ".join(_list_definition_names()) or "(none)"
        raise FileNotFoundError(f"unknown research template definition {name!r}; available: {available}")
    return definition_path.resolve()


def _list_definition_names() -> tuple[str, ...]:
    """列出定义目录下所有可用的模板名。

    Returns:
        按字母序排序的模板名元组。

    Raises:
        FileNotFoundError: 定义目录不存在。
    """

    names = sorted(
        path.name[: -len(_DEFINITION_SUFFIX)]
        for path in _resolve_definition_dir().glob(f"*{_DEFINITION_SUFFIX}")
    )
    return tuple(names)


def _load_json_object(path: Path) -> dict[str, object]:
    """读取一个必须为 JSON 对象的定义资产文件。

    Args:
        path: 定义资产文件路径。

    Returns:
        解析后的顶层对象字典。

    Raises:
        ValueError: 文件不是合法 JSON，或顶层不是对象。
    """

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"research template definition is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"research template definition must contain an object: {path}")
    return payload


def _parse_definition(payload: dict[str, object], *, source: Path) -> ResearchTemplateDefinition:
    """把已解析的 JSON 对象校验并建模为模板定义。

    Args:
        payload: 定义资产顶层对象。
        source: 定义资产文件路径，用于错误信息定位。

    Returns:
        校验通过的模板定义。

    Raises:
        ValueError: 任一字段缺失、类型错误或内容不完整。
    """

    schema_version = _require_int(payload.get("schema_version"), "schema_version", source=source)
    if schema_version != DEFINITION_SCHEMA_VERSION:
        raise ValueError(
            f"research template definition schema_version must be {DEFINITION_SCHEMA_VERSION}, "
            f"got {schema_version}: {source}"
        )
    name = _require_str(payload.get("name"), "name", source=source)
    expected_name = source.name[: -len(_DEFINITION_SUFFIX)]
    if name != expected_name:
        raise ValueError(
            f"research template definition name mismatch: name={name!r} file={expected_name!r}: {source}"
        )
    title = _require_str(payload.get("title"), "title", source=source)
    scorecard = _parse_scorecard(payload.get("scorecard"), source=source)
    evidence_requirements = _parse_evidence_requirements(payload.get("evidence_requirements"), source=source)
    red_flags = _require_str_tuple(payload.get("red_flags"), "red_flags", source=source, allow_empty=False)
    output_sections = _parse_output_sections(payload.get("output_sections"), source=source)
    return ResearchTemplateDefinition(
        schema_version=schema_version,
        name=name,
        title=title,
        scorecard=scorecard,
        evidence_requirements=evidence_requirements,
        red_flags=red_flags,
        output_sections=output_sections,
    )


def _parse_scorecard(raw: object, *, source: Path) -> tuple[ScorecardDimension, ...]:
    """校验并构建评分卡维度元组。

    Args:
        raw: ``scorecard`` 字段原始值。
        source: 定义资产文件路径。

    Returns:
        评分维度元组。

    Raises:
        ValueError: 字段结构或维度键错误、权重非正、或维度为空。
    """

    entries = _require_object_list(raw, "scorecard", source=source, allow_empty=False)
    dimensions: list[ScorecardDimension] = []
    seen_keys: set[str] = set()
    for index, entry in enumerate(entries):
        field = f"scorecard[{index}]"
        key = _require_str(entry.get("key"), f"{field}.key", source=source)
        if key in seen_keys:
            raise ValueError(f"duplicate scorecard key {key!r}: {source}")
        seen_keys.add(key)
        weight = _require_int(entry.get("weight"), f"{field}.weight", source=source)
        if weight <= 0:
            raise ValueError(f"{field}.weight must be a positive integer, got {weight}: {source}")
        dimensions.append(
            ScorecardDimension(
                key=key,
                title=_require_str(entry.get("title"), f"{field}.title", source=source),
                weight=weight,
                description=_require_str(entry.get("description"), f"{field}.description", source=source),
            )
        )
    return tuple(dimensions)


def _parse_evidence_requirements(raw: object, *, source: Path) -> tuple[EvidenceRequirement, ...]:
    """校验并构建证据要求元组。

    Args:
        raw: ``evidence_requirements`` 字段原始值。
        source: 定义资产文件路径。

    Returns:
        证据要求元组。

    Raises:
        ValueError: 字段结构、键重复或内容不完整。
    """

    entries = _require_object_list(raw, "evidence_requirements", source=source, allow_empty=False)
    requirements: list[EvidenceRequirement] = []
    seen_keys: set[str] = set()
    for index, entry in enumerate(entries):
        field = f"evidence_requirements[{index}]"
        key = _require_str(entry.get("key"), f"{field}.key", source=source)
        if key in seen_keys:
            raise ValueError(f"duplicate evidence requirement key {key!r}: {source}")
        seen_keys.add(key)
        requirements.append(
            EvidenceRequirement(
                key=key,
                description=_require_str(entry.get("description"), f"{field}.description", source=source),
                data_sources=_require_str_tuple(
                    entry.get("data_sources"), f"{field}.data_sources", source=source, allow_empty=False
                ),
            )
        )
    return tuple(requirements)


def _parse_output_sections(raw: object, *, source: Path) -> tuple[OutputSection, ...]:
    """校验并构建输出结构章节元组。

    Args:
        raw: ``output_sections`` 字段原始值。
        source: 定义资产文件路径。

    Returns:
        输出结构章节元组。

    Raises:
        ValueError: 字段结构、键重复或内容不完整。
    """

    entries = _require_object_list(raw, "output_sections", source=source, allow_empty=False)
    sections: list[OutputSection] = []
    seen_keys: set[str] = set()
    for index, entry in enumerate(entries):
        field = f"output_sections[{index}]"
        key = _require_str(entry.get("key"), f"{field}.key", source=source)
        if key in seen_keys:
            raise ValueError(f"duplicate output section key {key!r}: {source}")
        seen_keys.add(key)
        sections.append(
            OutputSection(
                key=key,
                title=_require_str(entry.get("title"), f"{field}.title", source=source),
                guidance=_require_str(entry.get("guidance"), f"{field}.guidance", source=source),
            )
        )
    return tuple(sections)


def _require_str(raw: object, field: str, *, source: Path) -> str:
    """要求某字段为非空字符串。

    Args:
        raw: 字段原始值。
        field: 字段路径，用于错误信息。
        source: 定义资产文件路径。

    Returns:
        去除首尾空白后的字符串。

    Raises:
        ValueError: 值不是字符串或为空白。
    """

    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field} must be a non-empty string: {source}")
    return raw.strip()


def _require_int(raw: object, field: str, *, source: Path) -> int:
    """要求某字段为整数（拒绝布尔）。

    Args:
        raw: 字段原始值。
        field: 字段路径，用于错误信息。
        source: 定义资产文件路径。

    Returns:
        整数值。

    Raises:
        ValueError: 值不是整数或为布尔类型。
    """

    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{field} must be an integer: {source}")
    return raw


def _require_str_tuple(
    raw: object,
    field: str,
    *,
    source: Path,
    allow_empty: bool,
) -> tuple[str, ...]:
    """要求某字段为字符串列表。

    Args:
        raw: 字段原始值。
        field: 字段路径，用于错误信息。
        source: 定义资产文件路径。
        allow_empty: 是否允许空列表。

    Returns:
        字符串元组。

    Raises:
        ValueError: 值不是列表、元素非字符串或列表为空而不被允许。
    """

    if not isinstance(raw, list):
        raise ValueError(f"{field} must be a list: {source}")
    if not raw and not allow_empty:
        raise ValueError(f"{field} must not be empty: {source}")
    items: list[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field}[{index}] must be a non-empty string: {source}")
        items.append(item.strip())
    return tuple(items)


def _require_object_list(
    raw: object,
    field: str,
    *,
    source: Path,
    allow_empty: bool,
) -> list[dict[str, object]]:
    """要求某字段为对象列表。

    Args:
        raw: 字段原始值。
        field: 字段路径，用于错误信息。
        source: 定义资产文件路径。
        allow_empty: 是否允许空列表。

    Returns:
        对象字典列表。

    Raises:
        ValueError: 值不是列表、元素非对象或列表为空而不被允许。
    """

    if not isinstance(raw, list):
        raise ValueError(f"{field} must be a list: {source}")
    if not raw and not allow_empty:
        raise ValueError(f"{field} must not be empty: {source}")
    entries: list[dict[str, object]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{field}[{index}] must be an object: {source}")
        entries.append(item)
    return entries
