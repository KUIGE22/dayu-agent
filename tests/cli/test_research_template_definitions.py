"""研究模板可执行定义层（definition）单元测试。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from dayu.cli.arguments import DayuCliArguments
from dayu.cli.commands.research_template import run_research_template_command
from dayu.cli.research_template_definitions import (
    ResearchTemplateDefinition,
    list_research_template_definitions,
    load_research_template_definition,
)

_ALL_DEFINITION_NAMES = ("common", "consumer", "cyclical", "financial", "technology")

_VALID_DEFINITION = {
    "schema_version": 1,
    "name": "common",
    "title": "示例模板",
    "scorecard": [
        {"key": "growth", "title": "增长", "weight": 60, "description": "增长质量。"},
        {"key": "cash", "title": "现金流", "weight": 40, "description": "现金流质量。"},
    ],
    "evidence_requirements": [
        {"key": "financials", "description": "财报证据。", "data_sources": ["financial_statements"]},
    ],
    "red_flags": ["一次性收入被当作长期成长。"],
    "output_sections": [
        {"key": "conclusion", "title": "结论", "guidance": "一句话结论。"},
    ],
}


def _write_definition_dir(base: Path, payload: object, *, name: str = "common") -> Path:
    """在临时目录构造一个 research_templates 定义目录并写入指定内容。"""

    definition_dir = base / "research_templates"
    definition_dir.mkdir(parents=True, exist_ok=True)
    target = definition_dir / f"{name}.definition.json"
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    target.write_text(text, encoding="utf-8")
    return target


@pytest.mark.unit
def test_load_research_template_definition_happy_path() -> None:
    definition = load_research_template_definition("common")

    assert isinstance(definition, ResearchTemplateDefinition)
    assert definition.name == "common"
    assert definition.schema_version == 1
    assert definition.scorecard
    assert definition.evidence_requirements
    assert definition.red_flags
    assert definition.output_sections
    total_weight = sum(dimension.weight for dimension in definition.scorecard)
    assert total_weight > 0


@pytest.mark.unit
def test_list_research_template_definitions_includes_all_packaged() -> None:
    names = {definition.name for definition in list_research_template_definitions()}

    assert set(_ALL_DEFINITION_NAMES) <= names


@pytest.mark.unit
def test_all_packaged_definitions_validate() -> None:
    # 资产校验：所有随包分发定义都应能通过加载器的严格校验。
    for name in _ALL_DEFINITION_NAMES:
        definition = load_research_template_definition(name)
        keys = [dimension.key for dimension in definition.scorecard]
        assert len(keys) == len(set(keys))


@pytest.mark.unit
def test_load_research_template_definition_unknown_name(tmp_path: Path) -> None:
    with patch(
        "dayu.cli.research_template_definitions.resolve_package_assets_path",
        return_value=tmp_path,
    ):
        _write_definition_dir(tmp_path, _VALID_DEFINITION)
        with pytest.raises(FileNotFoundError):
            load_research_template_definition("does-not-exist")


@pytest.mark.unit
def test_load_research_template_definition_malformed_json(tmp_path: Path) -> None:
    with patch(
        "dayu.cli.research_template_definitions.resolve_package_assets_path",
        return_value=tmp_path,
    ):
        _write_definition_dir(tmp_path, "{not valid json]")
        with pytest.raises(ValueError, match="not valid JSON"):
            load_research_template_definition("common")


@pytest.mark.unit
def test_load_research_template_definition_incomplete_definition(tmp_path: Path) -> None:
    incomplete = {**_VALID_DEFINITION, "scorecard": []}
    with patch(
        "dayu.cli.research_template_definitions.resolve_package_assets_path",
        return_value=tmp_path,
    ):
        _write_definition_dir(tmp_path, incomplete)
        with pytest.raises(ValueError, match="scorecard must not be empty"):
            load_research_template_definition("common")


@pytest.mark.unit
def test_load_research_template_definition_wrong_field_type(tmp_path: Path) -> None:
    broken = {**_VALID_DEFINITION, "title": 123}
    with patch(
        "dayu.cli.research_template_definitions.resolve_package_assets_path",
        return_value=tmp_path,
    ):
        _write_definition_dir(tmp_path, broken)
        with pytest.raises(ValueError, match="title must be a non-empty string"):
            load_research_template_definition("common")


@pytest.mark.unit
def test_load_research_template_definition_name_mismatch(tmp_path: Path) -> None:
    mismatched = {**_VALID_DEFINITION, "name": "consumer"}
    with patch(
        "dayu.cli.research_template_definitions.resolve_package_assets_path",
        return_value=tmp_path,
    ):
        _write_definition_dir(tmp_path, mismatched)
        with pytest.raises(ValueError, match="name mismatch"):
            load_research_template_definition("common")


@pytest.mark.unit
def test_run_scorecard_command_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    args = DayuCliArguments(research_template_action="scorecard", name="consumer", json=False)

    result = run_research_template_command(args)

    assert result == 0
    out = capsys.readouterr().out
    assert "评分卡" in out
    assert "consumer" in out


@pytest.mark.unit
def test_run_scorecard_command_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    args = DayuCliArguments(research_template_action="scorecard", name="financial", json=True)

    result = run_research_template_command(args)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "financial"
    assert payload["scorecard"]
    assert all("weight" in dimension for dimension in payload["scorecard"])


@pytest.mark.unit
def test_run_evidence_command_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    args = DayuCliArguments(research_template_action="evidence", name="cyclical", json=True)

    result = run_research_template_command(args)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "cyclical"
    assert payload["evidence_requirements"]
    assert all(item["data_sources"] for item in payload["evidence_requirements"])


@pytest.mark.unit
def test_run_schema_command_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    args = DayuCliArguments(research_template_action="schema", name="technology", json=True)

    result = run_research_template_command(args)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "technology"
    assert {"scorecard", "evidence_requirements", "red_flags", "output_sections"} <= set(payload)


@pytest.mark.unit
def test_run_scorecard_command_unknown_template_returns_error(capsys: pytest.CaptureFixture[str]) -> None:
    args = DayuCliArguments(research_template_action="scorecard", name="does-not-exist", json=False)

    result = run_research_template_command(args)

    assert result == 1
    assert "research-template error" in capsys.readouterr().err


@pytest.mark.unit
def test_markdown_list_command_still_works(capsys: pytest.CaptureFixture[str]) -> None:
    # 向后兼容：新增 definition 命令不得影响既有 Markdown 模板命令。
    args = DayuCliArguments(research_template_action="list", json=True)

    result = run_research_template_command(args)

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert {item["name"] for item in payload} >= set(_ALL_DEFINITION_NAMES)


@pytest.mark.unit
def test_markdown_show_command_still_works(capsys: pytest.CaptureFixture[str]) -> None:
    args = DayuCliArguments(research_template_action="show", name="common")

    result = run_research_template_command(args)

    assert result == 0
    assert "DAYU_RESEARCH_TEMPLATE" in capsys.readouterr().out
