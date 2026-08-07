"""Regression tests for the focused dual-model GitHub Actions workflow."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


WORKFLOW_PATH = Path(".github/workflows/dual-model-gates.yml")


def test_dual_model_gates_workflow_runs_structured_gate_reports() -> None:
    """The workflow should keep every machine-readable gate command wired."""

    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "python -m utils.validate_handoff_docs --json" in text
    assert "python -m utils.codex_review_gate --allow-waiting --json" in text
    assert "python -m utils.dual_model_pipeline_check --json" in text


def test_dual_model_gates_workflow_runs_focused_tests() -> None:
    """The workflow should include each local gate test module."""

    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "tests/test_validate_handoff_docs.py" in text
    assert "tests/test_codex_review_gate.py" in text
    assert "tests/test_dual_model_pipeline_check.py" in text
    assert "tests/test_dual_model_gates_workflow.py" in text
    assert "tests/test_prepare_deepseek_task.py" in text


def test_dual_model_gates_workflow_lints_workflow_test_module() -> None:
    """The focused lint step should cover the workflow regression test."""

    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    lint_step = text.split("- name: Run focused lint", 1)[1].split("- name:", 1)[0]

    assert "ruff check" in lint_step
    assert "tests/test_dual_model_gates_workflow.py" in lint_step


def test_dual_model_gates_workflow_runs_diff_whitespace_check() -> None:
    """The workflow should reject whitespace errors before gate reports."""

    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "git diff --check" in text


def test_dual_model_gates_workflow_watches_handoff_docs() -> None:
    """The workflow should run when handoff documentation changes."""

    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "docs/handoff/**" in text


def test_dual_model_gates_workflow_covers_task_spec_schema() -> None:
    """The workflow scope should include JSON task spec schema changes."""

    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "docs/handoff/**" in text
    assert "tests/test_prepare_deepseek_task.py" in text
