"""Tests for the dual-model pipeline health check utility."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from utils import codex_review_gate
from utils import dual_model_pipeline_check as module
from tests.test_validate_handoff_docs import _DeniedTextReader, _write_valid_handoff_docs

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


def test_pipeline_json_redacts_secret_shape_in_caller_details() -> None:
    """验证 aggregate serializer 会防御性净化 check details。"""

    key_value = "sk-" + ("A" * 20)
    results = (
        module.CheckResult(
            name="handoff docs",
            ok=False,
            details=(f"metadata mismatch: {key_value}",),
        ),
    )

    data = module.to_jsonable_results(results)
    serialized = json.dumps(data)

    assert key_value not in serialized
    assert "<redacted>" in serialized


def test_print_results_redacts_secret_shape_in_caller_results(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 aggregate plain formatter 会防御性净化调用方结果。"""

    key_value = "sk-" + ("A" * 20)
    results = (
        module.CheckResult(
            name=f"handoff {key_value}",
            ok=False,
            details=(f"metadata mismatch: {key_value}",),
        ),
    )

    module._print_results(results)

    captured = capsys.readouterr()
    assert key_value not in captured.out
    assert "[fail] handoff <redacted>" in captured.out
    assert "  - metadata mismatch: <redacted>" in captured.out


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


def test_scan_whitespace_reports_unreadable_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 whitespace scan 会把读取错误作为失败证据。"""

    target = tmp_path / "spec.md"
    target.write_text("valid\n", encoding="utf-8")
    monkeypatch.setattr(
        Path,
        "read_text",
        _DeniedTextReader(),
    )

    details = module._scan_whitespace(root=tmp_path, paths=(Path("spec.md"),))

    assert details == ["spec.md: unreadable text"]


def test_scan_whitespace_rejects_symlink_outside_repository(tmp_path: Path) -> None:
    """验证 whitespace scan 不会跟随外链读取仓库外正文。"""

    root = tmp_path / "repo"
    root.mkdir()
    external_file = tmp_path / "outside.md"
    external_file.write_text("external trailing whitespace   \n", encoding="utf-8")
    scan_path = root / "progress.md"
    try:
        scan_path.symlink_to(external_file)
    except OSError:
        pytest.skip("当前平台不允许创建测试用符号链接")

    details = module._scan_whitespace(root=root, paths=(Path("progress.md"),))

    assert details == ["progress.md: path must stay within repository root"]


def test_scan_text_files_reports_non_utf8_text(tmp_path: Path) -> None:
    """验证安全扫描不会把非 UTF-8 文件静默视为 clean。"""

    target = tmp_path / "progress.md"
    target.write_bytes(b"\xff\xfe")

    details = module._scan_text_files(
        root=tmp_path,
        paths=(Path("progress.md"),),
        pattern=module.codex_review_gate.BLOCKED_TERM_PATTERN,
        redact=False,
    )

    assert details == ["progress.md: non-utf8 text"]


def test_scan_text_files_rejects_symlink_outside_repository(tmp_path: Path) -> None:
    """验证 pattern scan 不会泄漏仓库外外链目标的命中正文。"""

    root = tmp_path / "repo"
    root.mkdir()
    external_file = tmp_path / "outside.md"
    blocked = "TO" + "DO"
    external_file.write_text(f"{blocked}: external content\n", encoding="utf-8")
    scan_path = root / "progress.md"
    try:
        scan_path.symlink_to(external_file)
    except OSError:
        pytest.skip("当前平台不允许创建测试用符号链接")

    details = module._scan_text_files(
        root=root,
        paths=(Path("progress.md"),),
        pattern=module.codex_review_gate.BLOCKED_TERM_PATTERN,
        redact=False,
    )

    assert details == ["progress.md: path must stay within repository root"]
    assert all("external content" not in detail for detail in details)


def test_scan_text_files_allows_symlink_target_inside_repository(tmp_path: Path) -> None:
    """验证 pattern scan 仍允许真实目标位于仓库内的符号链接。"""

    target = tmp_path / "docs" / "target.md"
    target.parent.mkdir(parents=True)
    blocked = "TO" + "DO"
    target.write_text(f"{blocked}: internal content\n", encoding="utf-8")
    scan_path = tmp_path / "progress.md"
    try:
        scan_path.symlink_to(target)
    except OSError:
        pytest.skip("当前平台不允许创建测试用符号链接")

    details = module._scan_text_files(
        root=tmp_path,
        paths=(Path("progress.md"),),
        pattern=module.codex_review_gate.BLOCKED_TERM_PATTERN,
        redact=False,
    )

    assert details == [f"progress.md:1: {blocked}: internal content"]


def test_scan_text_files_redacts_secret_shapes(tmp_path: Path) -> None:
    """Secret-shaped values are redacted in aggregate details."""

    key_value = "sk-" + ("A" * 20)
    target = tmp_path / "spec.md"
    target.write_text(f"value={key_value}\n", encoding="utf-8")

    details = module._scan_text_files(
        root=tmp_path,
        paths=(Path("spec.md"),),
        pattern=module.validate_handoff_docs.SECRET_KEY_PATTERN,
        redact=True,
    )

    assert details == ["spec.md:1: <redacted>"]


def test_pipeline_check_reports_unreadable_text_without_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证聚合 pipeline 在权限错误下返回所有相关失败结果。"""

    target = tmp_path / "AGENTS.md"
    target.write_text("# Rules\n", encoding="utf-8")
    monkeypatch.setattr(
        Path,
        "read_text",
        _DeniedTextReader(),
    )

    results = module.run_pipeline_check(tmp_path)

    handoff_result = _find_result(results, "handoff docs")
    whitespace_result = _find_result(results, "text whitespace")
    secret_result = _find_result(results, "secret key shape scan")
    assert "required file must be readable: AGENTS.md" in handoff_result.details
    assert whitespace_result.details == ("AGENTS.md: unreadable text",)
    assert secret_result.details == ("AGENTS.md: unreadable text",)


def test_pipeline_check_reports_external_blocked_scan_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证聚合 blocked-term check 对外链路径返回 containment 失败。"""

    root = tmp_path / "repo"
    root.mkdir()
    external_file = tmp_path / "outside.md"
    external_file.write_text("TO" + "DO: external content\n", encoding="utf-8")
    scan_path = root / "progress.md"
    try:
        scan_path.symlink_to(external_file)
    except OSError:
        pytest.skip("当前平台不允许创建测试用符号链接")
    monkeypatch.setattr(module.validate_handoff_docs, "validate_handoff_docs", lambda root: [])
    monkeypatch.setattr(
        module.codex_review_gate,
        "run_review_gate",
        lambda root, allow_waiting: _clean_review_result(),
    )
    monkeypatch.setattr(module, "_scan_whitespace", lambda root, paths: [])

    results = module.run_pipeline_check(root)

    blocked_result = _find_result(results, "blocked term scan")
    assert not blocked_result.ok
    assert blocked_result.details == ("progress.md: path must stay within repository root",)


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
        pattern=module.validate_handoff_docs.SECRET_KEY_PATTERN,
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


def test_scan_text_files_redacts_secret_shape_on_blocked_term_line(tmp_path: Path) -> None:
    """验证 aggregate blocked-term detail 不会泄漏同一行的 secret-shaped 值。"""

    blocked = "TO" + "DO"
    key_value = "sk-" + ("A" * 20)
    target = tmp_path / "progress.md"
    target.write_text(f"{blocked} token={key_value}\n", encoding="utf-8")

    details = module._scan_text_files(
        root=tmp_path,
        paths=(Path("progress.md"),),
        pattern=module.codex_review_gate.BLOCKED_TERM_PATTERN,
        redact=False,
    )

    assert details == ["progress.md:1: <redacted>"]
    assert all(key_value not in detail for detail in details)


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
