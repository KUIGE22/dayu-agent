"""Tests for the dual-model pipeline health check utility."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from utils import codex_review_gate
from utils import dual_model_pipeline_check as module
from tests.test_validate_handoff_docs import _write_valid_handoff_docs

pytestmark = pytest.mark.unit


def test_pipeline_check_ok_when_inputs_are_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The aggregate result is ok when all component checks are clean."""

    _stub_component_checks(monkeypatch)

    results = module.run_pipeline_check(tmp_path)

    assert all(result.ok for result in results)


def test_pipeline_check_json_report_is_machine_readable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aggregate results can be converted to JSON-safe data."""

    _stub_component_checks(monkeypatch)

    results = module.run_pipeline_check(tmp_path)
    data = module.to_jsonable_results(results)
    checks = cast(list[dict[str, object]], data["checks"])

    assert data["ok"] is True
    assert len(checks) == 5
    assert json.loads(json.dumps(data))["ok"] is True


def test_pipeline_json_reports_non_utf8_canonical_inbox(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证聚合 JSON gate 对损坏 canonical inbox 返回结构化失败。"""

    _write_valid_handoff_docs(tmp_path)
    (tmp_path / module.validate_handoff_docs.INBOX_PATH).write_bytes(b"\xff\xfe")

    result = module.main(["--root", str(tmp_path), "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    handoff_check = next(check for check in data["checks"] if check["name"] == "handoff docs")
    assert result == 1
    assert captured.err == ""
    assert data["ok"] is False
    assert (
        "required file must be UTF-8 text: docs/handoff/deepseek_inbox.md"
        in handoff_check["details"]
    )


def test_pipeline_check_reports_handoff_issues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Handoff validation issues are preserved in the aggregate result."""

    _stub_component_checks(monkeypatch)
    monkeypatch.setattr(module.validate_handoff_docs, "validate_handoff_docs", lambda root: ["missing task"])

    results = module.run_pipeline_check(tmp_path)
    handoff_result = _find_result(results, "handoff docs")

    assert not handoff_result.ok
    assert handoff_result.details == ("missing task",)


def test_pipeline_check_uses_require_ready_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The aggregate check forwards readiness policy to the review gate."""

    observed: dict[str, bool] = {}

    def _review_gate(root: Path, *, allow_waiting: bool) -> codex_review_gate.ReviewGateResult:
        del root
        observed["allow_waiting"] = allow_waiting
        return _clean_review_result()

    _stub_component_checks(monkeypatch)
    monkeypatch.setattr(module.codex_review_gate, "run_review_gate", _review_gate)

    module.run_pipeline_check(tmp_path, require_ready=True)

    assert observed["allow_waiting"] is False


def test_text_health_paths_cover_ci_and_task_spec_docs() -> None:
    """Aggregate text scans should cover workflow and task-spec control files."""

    paths = {path.as_posix() for path in module.TEXT_HEALTH_PATHS}

    assert ".github/workflows/dual-model-gates.yml" in paths
    assert "docs/handoff/deepseek_assignment_examples.md" in paths
    assert "docs/handoff/deepseek_task_spec_schema.md" in paths
    assert "tests/test_dual_model_gates_workflow.py" in paths


def test_blocked_term_health_paths_cover_scoped_gate_files() -> None:
    """Aggregate blocked-term scans should cover scoped gate files."""

    paths = {path.as_posix() for path in module.BLOCKED_TERM_HEALTH_PATHS}

    assert "utils/validate_handoff_docs.py" in paths
    assert "utils/prepare_deepseek_task.py" in paths
    assert "tests/test_prepare_deepseek_task.py" in paths
    assert "docs/handoff/deepseek_task_template.md" in paths
    assert "tests/test_dual_model_gates_workflow.py" in paths
    assert "progress.md" in paths


def test_scan_whitespace_reports_trailing_text(tmp_path: Path) -> None:
    """Text health scanning reports trailing spaces."""

    target = tmp_path / "spec.md"
    target.write_text("bad   \n", encoding="utf-8")

    details = module._scan_whitespace(root=tmp_path, paths=(Path("spec.md"),))

    assert details == ["spec.md:1: trailing whitespace"]


def test_scan_text_files_redacts_secret_shapes(tmp_path: Path) -> None:
    """Secret-shaped values are redacted in aggregate details."""

    key_value = "sk-" + ("A" * 20)
    target = tmp_path / "spec.md"
    target.write_text(f"value={key_value}\n", encoding="utf-8")

    details = module._scan_text_files(
        root=tmp_path,
        paths=(Path("spec.md"),),
        pattern=module.codex_review_gate.SECRET_KEY_PATTERN,
        redact=True,
    )

    assert details == ["spec.md:1: <redacted>"]


def test_scan_text_files_ignores_embedded_task_list_css_text(tmp_path: Path) -> None:
    """Secret-shaped scanning should ignore embedded task-list selector text."""

    target = tmp_path / "style.css"
    target.write_text(
        ".markdown-body .contains-task-list .task-list-item-control-enabled { color: red; }\n",
        encoding="utf-8",
    )

    details = module._scan_text_files(
        root=tmp_path,
        paths=(Path("style.css"),),
        pattern=module.codex_review_gate.SECRET_KEY_PATTERN,
        redact=True,
    )

    assert details == []


def test_scan_text_files_reports_blocked_terms(tmp_path: Path) -> None:
    """Blocked-term scan details include the file, line, and preview."""

    blocked = "TO" + "DO"
    target = tmp_path / "progress.md"
    target.write_text(f"{blocked}\n", encoding="utf-8")

    details = module._scan_text_files(
        root=tmp_path,
        paths=(Path("progress.md"),),
        pattern=module.codex_review_gate.BLOCKED_TERM_PATTERN,
        redact=False,
    )

    assert details == [f"progress.md:1: {blocked}"]


def test_pipeline_check_reports_blocked_term_scan_hits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aggregate results include scoped blocked-term scan hits."""

    blocked = "TO" + "DO"
    (tmp_path / "progress.md").write_text(f"{blocked}\n", encoding="utf-8")
    monkeypatch.setattr(module.validate_handoff_docs, "validate_handoff_docs", lambda root: [])
    monkeypatch.setattr(
        module.codex_review_gate,
        "run_review_gate",
        lambda root, allow_waiting: _clean_review_result(),
    )
    monkeypatch.setattr(module, "_scan_whitespace", lambda root, paths: [])

    results = module.run_pipeline_check(tmp_path)
    blocked_result = _find_result(results, "blocked term scan")

    assert not blocked_result.ok
    assert blocked_result.details == (f"progress.md:1: {blocked}",)


def test_main_returns_nonzero_when_any_check_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """CLI status reflects failed aggregate checks."""

    monkeypatch.setattr(
        module,
        "run_pipeline_check",
        lambda root, require_ready: (module.CheckResult(name="handoff docs", ok=False, details=("bad",)),),
    )

    assert module.main(["--root", str(tmp_path)]) == 1


def test_main_can_print_json_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI can print a machine-readable JSON report."""

    _stub_component_checks(monkeypatch)

    result = module.main(["--root", str(tmp_path), "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert result == 0
    assert data["ok"] is True
    assert [item["name"] for item in data["checks"]] == [
        "handoff docs",
        "codex review gate",
        "text whitespace",
        "blocked term scan",
        "secret key shape scan",
    ]


def _stub_component_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module.validate_handoff_docs, "validate_handoff_docs", lambda root: [])
    monkeypatch.setattr(
        module.codex_review_gate,
        "run_review_gate",
        lambda root, allow_waiting: _clean_review_result(),
    )
    monkeypatch.setattr(module, "_scan_whitespace", lambda root, paths: [])
    monkeypatch.setattr(module, "_scan_text_files", lambda root, paths, pattern, redact: [])


def _clean_review_result() -> codex_review_gate.ReviewGateResult:
    return codex_review_gate.ReviewGateResult(
        ready_for_review=False,
        status="WAITING_FOR_TASK",
        message_id="unassigned",
        task="unassigned",
        changed_files=(),
        issues=(),
        blocked_term_hits=(),
        secret_key_hits=(),
    )


def _find_result(results: tuple[module.CheckResult, ...], name: str) -> module.CheckResult:
    for result in results:
        if result.name == name:
            return result
    raise AssertionError(f"missing result: {name}")
