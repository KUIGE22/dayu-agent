"""Tests for the local Codex review gate utility."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from utils import codex_review_gate as module

pytestmark = pytest.mark.unit


def test_review_gate_allows_waiting_state_when_requested(tmp_path: Path) -> None:
    """A waiting outbox is valid before DeepSeek receives a task."""

    _write_doc_set(tmp_path, outbox=_waiting_outbox())

    result = module.run_review_gate(tmp_path, allow_waiting=True)

    assert not result.ready_for_review
    assert result.issues == ()
    assert result.changed_files == ()


def test_review_gate_rejects_waiting_state_by_default(tmp_path: Path) -> None:
    """Codex review requires an explicit ready marker by default."""

    _write_doc_set(tmp_path, outbox=_waiting_outbox())

    result = module.run_review_gate(tmp_path)

    assert any("is not marked READY_FOR_CODEX_REVIEW" in issue for issue in result.issues)


def test_review_gate_ignores_body_ready_markers(tmp_path: Path) -> None:
    """Only top-level Status metadata controls review readiness."""

    outbox = "\n".join(
        [
            _waiting_outbox().rstrip(),
            "## Extra Notes",
            "READY_FOR_CODEX_REVIEW",
            "Status: READY_FOR_CODEX_REVIEW",
            "",
        ]
    )
    _write_doc_set(tmp_path, outbox=outbox)

    result = module.run_review_gate(tmp_path, allow_waiting=True)

    assert not result.ready_for_review
    assert result.status == "WAITING_FOR_TASK"
    assert result.issues == ()


def test_review_gate_rejects_duplicate_top_level_status(tmp_path: Path) -> None:
    """Duplicate top-level status fields are rejected without changing the first status."""

    outbox = _waiting_outbox().replace("## Summary", "Status: READY_FOR_CODEX_REVIEW\n## Summary")
    _write_doc_set(tmp_path, outbox=outbox)

    result = module.run_review_gate(tmp_path, allow_waiting=True)

    assert not result.ready_for_review
    assert result.status == "WAITING_FOR_TASK"
    assert f"{module.OUTBOX_PATH.as_posix()} has duplicate metadata field: Status" in result.issues


def test_review_gate_accepts_ready_outbox_with_clean_changed_file(tmp_path: Path) -> None:
    """A ready outbox with real verification and clean changed files succeeds."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )

    result = module.run_review_gate(tmp_path)

    assert result.ready_for_review
    assert result.issues == ()
    assert result.blocked_term_hits == ()
    assert result.secret_key_hits == ()
    assert result.changed_files == (Path("src/example.py"),)


def test_review_gate_rejects_task_code_mismatch(tmp_path: Path) -> None:
    """Codex review surfaces inbox/outbox task-code drift."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace("Task: TASK_1", "Task: TASK_2")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert "handoff Task mismatch: inbox=TASK_1 outbox=TASK_2" in result.issues


def test_review_gate_rejects_changed_assigned_verification_command(tmp_path: Path) -> None:
    """Ready outbox evidence must include each exact command assigned by Codex."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "python -m pytest tests/example.py -q",
        "python -m pytest tests/other.py -q",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md missing assigned verification command result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


def test_review_gate_rejects_suffixed_assigned_verification_command(tmp_path: Path) -> None:
    """Ready outbox command evidence must equal the assigned command."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        "`python -m pytest tests/example.py -q --deselect=tests/example.py::test_target` exited 0.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md missing assigned verification command result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues
    assert any(
        "ready outbox verification command must not include unsafe verification flags" in issue
        for issue in result.issues
    )


def test_review_gate_rejects_changed_bullet_verification_command(tmp_path: Path) -> None:
    """Backticked bullet verification commands are exact assigned commands."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "python -m ruff check src/example.py tests/example.py",
        "python -m ruff check src/other.py tests/example.py",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox_with_bullet_commands(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md missing assigned verification command result: "
        "python -m ruff check src/example.py tests/example.py"
    ) in result.issues


def test_review_gate_rejects_nonzero_assigned_verification_result(tmp_path: Path) -> None:
    """Exact assigned command evidence must include a clean result marker."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        "`python -m pytest tests/example.py -q` exited 1.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


def test_review_gate_rejects_success_marker_inside_assigned_command_text(tmp_path: Path) -> None:
    """A success marker inside the command literal is not command-result evidence."""

    assigned_pytest = "python -m pytest tests/example.py -q --label 'exited 0'"
    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        f"`{assigned_pytest}`",
    )
    inbox = _ready_deepseek_inbox(allowed_files=["src/example.py"]).replace(
        "python -m pytest tests/example.py -q",
        assigned_pytest,
    )
    _write_doc_set(
        tmp_path,
        inbox=inbox,
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command lacks clean result: "
        f"{assigned_pytest}"
    ) in result.issues


def test_review_gate_rejects_unbulleted_assigned_verification_result(tmp_path: Path) -> None:
    """Ready outbox command evidence must be a parseable bullet result entry."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "- `python -m pytest tests/example.py -q` exited 0.",
        "`python -m pytest tests/example.py -q` exited 0.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md missing assigned verification command result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


def test_review_gate_rejects_negated_successful_assigned_verification_result(tmp_path: Path) -> None:
    """Negated success wording is not clean command evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        "`python -m pytest tests/example.py -q` not successful.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


def test_review_gate_rejects_skipped_assigned_verification_result(tmp_path: Path) -> None:
    """Skipped assigned verification is not clean command evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        "`python -m pytest tests/example.py -q` skipped, exited 0.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues
    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


@pytest.mark.parametrize("failure_marker", ["timed out", "timeout", "cancelled", "interrupted", "error"])
def test_review_gate_rejects_interrupted_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Interrupted assigned verification is not clean command evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues
    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


@pytest.mark.parametrize(
    "failure_marker",
    [
        "collected 0 items",
        "no tests ran",
        "no tests collected",
        "empty test suite",
        "all deselected",
        "2 deselected",
    ],
)
def test_review_gate_rejects_empty_suite_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Empty pytest suites are not clean assigned-command evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues
    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


@pytest.mark.parametrize(
    "failure_marker",
    [
        "1 xfailed",
        "1 xpassed",
        "expected failure",
        "unexpectedly passed",
        "warnings-only",
        "warnings only",
        "only warnings",
    ],
)
def test_review_gate_rejects_soft_failure_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Soft pytest failures are not clean assigned-command evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues
    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


@pytest.mark.parametrize(
    "failure_marker",
    [
        "partial verification",
        "partial run",
        "partial result",
        "subset run",
        "subset only",
        "smoke-only",
        "smoke only",
        "sample-only",
        "sample only",
        "not full suite",
    ],
)
def test_review_gate_rejects_partial_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Partial verification is not clean assigned-command evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues
    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


@pytest.mark.parametrize(
    "failure_marker",
    [
        "cached result",
        "cache result",
        "from cache",
        "previous run",
        "previous result",
        "prior run",
        "prior result",
        "old result",
        "stale result",
        "from earlier run",
        "from previous run",
        "not rerun",
        "not re-run",
        "reused result",
    ],
)
def test_review_gate_rejects_stale_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Stale verification is not clean assigned-command evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues
    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


@pytest.mark.parametrize(
    "failure_marker",
    [
        "assumed exit 0",
        "assumed exited 0",
        "assumed success",
        "assumed successful",
        "expected to exit 0",
        "expected to succeed",
        "would exit 0",
        "would succeed",
        "should exit 0",
        "should succeed",
        "likely exit 0",
        "likely succeeded",
        "planned result",
    ],
)
def test_review_gate_rejects_speculative_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Speculative verification is not clean assigned-command evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues
    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


@pytest.mark.parametrize(
    "failure_marker",
    [
        "dry run",
        "dry-run",
        "manual only",
        "manual-only",
        "manual verification",
        "manually verified",
        "not actually run",
        "not actually executed",
        "simulated run",
        "simulated result",
        "synthetic result",
        "fabricated result",
        "invented result",
        "estimated result",
    ],
)
def test_review_gate_rejects_substitute_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Substitute verification is not clean assigned-command evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues
    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


@pytest.mark.parametrize(
    "failure_marker",
    [
        "wrong environment",
        "different environment",
        "not project environment",
        "outside project environment",
        "wrong env",
        "different env",
        "not project env",
        "outside project env",
        "wrong interpreter",
        "different interpreter",
        "wrong python executable",
        "different python executable",
        "not project venv",
        "outside project venv",
        "using system python",
        "used system python",
        "without pythonpath",
        "wrong working directory",
        "different working directory",
        "wrong cwd",
        "different cwd",
        "not from repo root",
        "not from repository root",
        "outside repo root",
        "outside repository root",
    ],
)
def test_review_gate_rejects_environment_mismatch_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Environment-mismatched verification is not clean assigned-command evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues
    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


@pytest.mark.parametrize(
    "failure_marker",
    [
        "command not found",
        "not recognized as",
        "no module named",
        "module not found",
        "dependency missing",
        "missing dependency",
        "package missing",
        "missing package",
        "cannot import",
        "could not import",
        "unable to import",
        "no such file or directory",
        "permission denied",
        "access denied",
    ],
)
def test_review_gate_rejects_tooling_failure_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Local tooling failures are not clean assigned-command evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues
    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


def test_review_gate_rejects_conflicting_assigned_verification_results(tmp_path: Path) -> None:
    """A failing result for an assigned command is surfaced even with a later clean result."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "- `python -m pytest tests/example.py -q` exited 0.",
        "\n".join(
            [
                "- `python -m pytest tests/example.py -q` exited 1.",
                "- `python -m pytest tests/example.py -q` exited 0.",
            ]
        ),
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


def test_review_gate_rejects_nonzero_assigned_verification_exit_code(tmp_path: Path) -> None:
    """Any nonzero assigned-command exit code is failing evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "- `python -m pytest tests/example.py -q` exited 0.",
        "\n".join(
            [
                "- `python -m pytest tests/example.py -q` exited 2.",
                "- `python -m pytest tests/example.py -q` exited 0.",
            ]
        ),
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in result.issues


def test_review_gate_rejects_missing_assigned_acceptance_evidence(tmp_path: Path) -> None:
    """Ready outbox checked evidence must cover each assigned acceptance criterion."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "- [x] Error path verified.",
        "- [x] Different behavior verified.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert "docs/handoff/deepseek_outbox.md missing checked acceptance evidence: Error path verified." in result.issues


def test_review_gate_rejects_acceptance_evidence_with_prefixed_criterion(tmp_path: Path) -> None:
    """Checked evidence must start with the assigned criterion it covers."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "- [x] Error path verified.",
        "- [x] Covered by targeted regression: Error path verified.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert "docs/handoff/deepseek_outbox.md missing checked acceptance evidence: Error path verified." in result.issues


def test_review_gate_rejects_negative_checked_acceptance_evidence(tmp_path: Path) -> None:
    """Checked acceptance evidence cannot include negated completion wording."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "- [x] Error path verified.",
        "- [x] Error path verified. not verified in this change.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md checked acceptance evidence is negative: "
        "Error path verified. not verified in this change."
    ) in result.issues


def test_review_gate_rejects_skipped_checked_acceptance_evidence(tmp_path: Path) -> None:
    """Checked acceptance evidence cannot claim skipped verification."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "- [x] Error path verified.",
        "- [x] Error path verified. skipped in this change.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md checked acceptance evidence is negative: "
        "Error path verified. skipped in this change."
    ) in result.issues


@pytest.mark.parametrize("marker", ["unverified", "untested"])
def test_review_gate_rejects_unverified_checked_acceptance_evidence(
    tmp_path: Path,
    marker: str,
) -> None:
    """Checked acceptance evidence cannot claim absent verification."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "- [x] Error path verified.",
        f"- [x] Error path verified. {marker} in this change.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md checked acceptance evidence is negative: "
        f"Error path verified. {marker} in this change."
    ) in result.issues


@pytest.mark.parametrize("marker", ["pending", "deferred", "not applicable", "n/a"])
def test_review_gate_rejects_deferred_checked_acceptance_evidence(
    tmp_path: Path,
    marker: str,
) -> None:
    """Checked acceptance evidence cannot defer verification."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "- [x] Error path verified.",
        f"- [x] Error path verified. {marker} in this change.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md checked acceptance evidence is negative: "
        f"Error path verified. {marker} in this change."
    ) in result.issues


def test_review_gate_accepts_assigned_acceptance_evidence_with_details(tmp_path: Path) -> None:
    """Ready outbox checked evidence may include details after the assigned criterion."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "- [x] Error path verified.",
        "- [x] Error path verified. Covered by targeted regression.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert result.issues == ()


def test_review_gate_rejects_clean_git_claimed_changed_file(tmp_path: Path) -> None:
    """Ready outbox changed-file evidence must map to git worktree evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(
            changed_file="src/example.py",
            verification_diff_paths="src src/example.py tests/example.py",
        ),
    )
    _init_git_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")

    result = module.run_review_gate(tmp_path)

    assert "changed file is not dirty in git status: src/example.py" in result.issues


def test_review_gate_accepts_git_dirty_claimed_changed_file(tmp_path: Path) -> None:
    """Ready outbox changed-file evidence accepts an actual git worktree change."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )
    _init_git_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    _write_changed_file(tmp_path, "src/example.py", "VALUE = 2\n")

    result = module.run_review_gate(tmp_path)

    assert result.issues == ()


def test_review_gate_rejects_unreported_allowed_scope_worktree_change(tmp_path: Path) -> None:
    """Ready outbox changed files must include dirty files inside allowed scope."""

    _write_changed_file(tmp_path, "src/example_pkg/example.py", "VALUE = 1\n")
    _write_changed_file(tmp_path, "src/example_pkg/extra.py", "VALUE = 1\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example_pkg"]),
        outbox=_ready_outbox(
            changed_file="src/example_pkg/example.py",
            verification_diff_paths="src/example_pkg src/example_pkg/example.py tests/example.py",
        ),
    )
    _init_git_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    _write_changed_file(tmp_path, "src/example_pkg/example.py", "VALUE = 2\n")
    _write_changed_file(tmp_path, "src/example_pkg/extra.py", "VALUE = 2\n")

    result = module.run_review_gate(tmp_path)

    assert "worktree change inside allowed scope is missing from outbox: src/example_pkg/extra.py" in result.issues


def test_review_gate_ignores_baseline_worktree_change(tmp_path: Path) -> None:
    """Pre-assignment worktree baseline paths are not treated as new task changes."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_changed_file(tmp_path, "docs/extra.md", "before\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(
            allowed_files=["src/example.py"],
            forbidden_files=["private"],
            worktree_baseline=["docs/extra.md"],
        ),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )
    _init_git_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    _write_changed_file(tmp_path, "src/example.py", "VALUE = 2\n")
    _write_changed_file(tmp_path, "docs/extra.md", "after\n")

    result = module.run_review_gate(tmp_path)

    assert result.issues == ()


def test_review_gate_rejects_stale_worktree_baseline_path(tmp_path: Path) -> None:
    """Baseline paths must still be dirty before they can suppress worktree issues."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_changed_file(tmp_path, "docs/extra.md", "unchanged\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(
            allowed_files=["src/example.py"],
            worktree_baseline=["docs/extra.md"],
        ),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )
    _init_git_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    _write_changed_file(tmp_path, "src/example.py", "VALUE = 2\n")

    result = module.run_review_gate(tmp_path)

    assert "worktree baseline path is not dirty in git status: docs/extra.md" in result.issues


def test_review_gate_rejects_non_none_worktree_baseline_stand_in(tmp_path: Path) -> None:
    """Codex review requires exact None for clean assignment-time worktree evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_changed_file(tmp_path, "tests/example.py", "def test_example():\n    assert True\n")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Tester")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    (tmp_path / "src" / "example.py").write_text("VALUE = 2\n", encoding="utf-8")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(
            allowed_files=["src/example.py"],
            worktree_baseline=["Clean."],
        ),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_inbox.md ready inbox worktree baseline must use explicit None or paths, "
        "not stand-in: Clean."
    ) in result.issues


def test_review_gate_accepts_baselined_handoff_root_shortcut_worktree_changes(tmp_path: Path) -> None:
    """Root shortcut handoff changes are allowed only when captured in the baseline."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(
            allowed_files=["src/example.py"],
            worktree_baseline=["DEEPSEEK_INBOX.md", "CODEX_REVIEW.md"],
        ),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )
    _write_changed_file(tmp_path, "DEEPSEEK_INBOX.md", "See docs/handoff/deepseek_inbox.md\n")
    _write_changed_file(tmp_path, "CODEX_REVIEW.md", "See docs/handoff/codex_review_checklist.md\n")
    _init_git_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    _write_changed_file(tmp_path, "src/example.py", "VALUE = 2\n")
    _write_changed_file(
        tmp_path,
        "DEEPSEEK_INBOX.md",
        "# DeepSeek Inbox Shortcut\ndocs/handoff/deepseek_inbox.md\nUpdated note\n",
    )
    _write_changed_file(
        tmp_path,
        "CODEX_REVIEW.md",
        "# Codex Review Shortcut\ndocs/handoff/codex_review_checklist.md\nUpdated note\n",
    )

    result = module.run_review_gate(tmp_path)

    assert result.issues == ()


def test_review_gate_rejects_handoff_control_file_changed_entry(tmp_path: Path) -> None:
    """Ready outbox changed-file evidence cannot claim handoff control files."""

    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="DEEPSEEK_INBOX.md"),
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "changed file is a handoff control file, not an implementation file: DEEPSEEK_INBOX.md"
    ) in result.issues


def test_review_gate_rejects_workflow_control_file_changed_entry(tmp_path: Path) -> None:
    """Ready outbox changed-file evidence cannot claim workflow control files."""

    _write_changed_file(tmp_path, "progress.md", "before\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="progress.md"),
    )

    result = module.run_review_gate(tmp_path)

    assert "changed file is a workflow control file, not an implementation file: progress.md" in result.issues


def test_review_gate_rejects_unreported_post_assignment_worktree_change(tmp_path: Path) -> None:
    """New worktree changes outside the baseline must be disclosed in the outbox."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_changed_file(tmp_path, "docs/extra.md", "before\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )
    _init_git_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    _write_changed_file(tmp_path, "src/example.py", "VALUE = 2\n")
    _write_changed_file(tmp_path, "docs/extra.md", "after\n")

    result = module.run_review_gate(tmp_path)

    assert "post-assignment worktree change is missing from outbox: docs/extra.md" in result.issues


def test_review_gate_rejects_unreported_workflow_control_worktree_change(tmp_path: Path) -> None:
    """New workflow control file changes after assignment block Codex review."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_changed_file(tmp_path, "progress.md", "before\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )
    _init_git_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    _write_changed_file(tmp_path, "src/example.py", "VALUE = 2\n")
    _write_changed_file(tmp_path, "progress.md", "after\n")

    result = module.run_review_gate(tmp_path)

    assert "workflow control file changed after assignment: progress.md" in result.issues


def test_review_gate_rejects_unreported_handoff_control_worktree_change(tmp_path: Path) -> None:
    """New handoff control file changes after assignment block Codex review."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )
    _init_git_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    _write_changed_file(tmp_path, "src/example.py", "VALUE = 2\n")
    _write_changed_file(
        tmp_path,
        "DEEPSEEK_INBOX.md",
        "# DeepSeek Inbox Shortcut\ndocs/handoff/deepseek_inbox.md\nextra mutation\n",
    )

    result = module.run_review_gate(tmp_path)

    assert "workflow control file changed after assignment: DEEPSEEK_INBOX.md" in result.issues


def test_review_gate_rejects_unreported_forbidden_scope_worktree_change(tmp_path: Path) -> None:
    """Dirty files inside forbidden scope are surfaced even when omitted from outbox."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_changed_file(tmp_path, "src/private/example.py", "VALUE = 1\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(
            allowed_files=["src/example.py"],
            forbidden_files=["src/private"],
        ),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )
    _init_git_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    _write_changed_file(tmp_path, "src/example.py", "VALUE = 2\n")
    _write_changed_file(tmp_path, "src/private/example.py", "VALUE = 2\n")

    result = module.run_review_gate(tmp_path)

    assert "worktree change touches forbidden scope: src/private/example.py" in result.issues


def test_review_gate_finds_blocked_terms_in_changed_file(tmp_path: Path) -> None:
    """Changed files are scanned for unfinished-work markers."""

    _write_changed_file(tmp_path, "src/example.py", ("TO" + "DO") + ": finish this\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )

    result = module.run_review_gate(tmp_path)

    assert len(result.blocked_term_hits) == 1
    assert result.blocked_term_hits[0].path == Path("src/example.py")
    assert result.blocked_term_hits[0].line_number == 1


def test_review_gate_finds_stand_in_terms_in_changed_file(tmp_path: Path) -> None:
    """Changed files are scanned for stand-in data markers."""

    marker = "du" + "mmy"
    _write_changed_file(tmp_path, "src/example.py", f"VALUE = '{marker}'\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )

    result = module.run_review_gate(tmp_path)

    assert len(result.blocked_term_hits) == 1
    assert result.blocked_term_hits[0].path == Path("src/example.py")


def test_review_gate_finds_blocked_terms_in_outbox(tmp_path: Path) -> None:
    """The task outbox is scanned for unfinished-work markers."""

    marker = "TO" + "DO"
    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = "\n".join(
        [
            _ready_outbox(changed_file="src/example.py"),
            "## Extra Notes",
            f"- {marker}: unresolved implementation note",
            "",
        ]
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert any(hit.path == module.OUTBOX_PATH for hit in result.blocked_term_hits)


def test_review_gate_rejects_skipped_scanner_evidence(tmp_path: Path) -> None:
    """Review gate inherits failing Anti-Placeholder scan evidence checks."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    scan_command = _scan_command(["src/example.py"])
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        f"`{scan_command}` returned no matches.",
        f"`{scan_command}` skipped, returned no matches.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must not use failing evidence"
        in result.issues
    )


@pytest.mark.parametrize("failure_marker", ["timed out", "timeout", "cancelled", "interrupted", "error"])
def test_review_gate_rejects_interrupted_scanner_evidence(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Review gate inherits interrupted Anti-Placeholder scan evidence checks."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    scan_command = _scan_command(["src/example.py"])
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        f"`{scan_command}` returned no matches.",
        f"`{scan_command}` {failure_marker}, returned no matches.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must not use failing evidence"
        in result.issues
    )


def test_review_gate_redacts_secret_key_shapes(tmp_path: Path) -> None:
    """Secret-shaped values are reported without printing the value."""

    key_value = "sk-" + ("A" * 20)
    _write_changed_file(tmp_path, "src/example.py", f"VALUE = '{key_value}'\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )

    result = module.run_review_gate(tmp_path)

    assert len(result.secret_key_hits) == 1
    assert result.secret_key_hits[0].preview == "<redacted>"


def test_review_gate_ignores_embedded_task_list_css_text(tmp_path: Path) -> None:
    """Secret scanning should not treat ordinary task-list CSS selectors as keys."""

    _write_changed_file(
        tmp_path,
        "src/example.css",
        ".markdown-body .contains-task-list .task-list-item-control-enabled { color: red; }\n",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.css"]),
        outbox=_ready_outbox(changed_file="src/example.css"),
    )

    result = module.run_review_gate(tmp_path)

    assert result.secret_key_hits == ()


def test_review_gate_redacts_secret_key_shapes_in_inbox(tmp_path: Path) -> None:
    """Secret-shaped values in the task inbox are included in review scans."""

    key_value = "sk-" + ("A" * 20)
    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    inbox = "\n".join(
        [
            _ready_deepseek_inbox(allowed_files=["src/example.py"]),
            "## Extra Notes",
            f"- accidental value {key_value}",
            "",
        ]
    )
    _write_doc_set(
        tmp_path,
        inbox=inbox,
        outbox=_ready_outbox(changed_file="src/example.py"),
    )

    result = module.run_review_gate(tmp_path)

    assert any(hit.path == module.INBOX_PATH for hit in result.secret_key_hits)
    assert all(hit.preview == "<redacted>" for hit in result.secret_key_hits)


def test_review_gate_redacts_secret_key_shapes_in_root_shortcut(tmp_path: Path) -> None:
    """Secret-shaped values in root shortcuts are included in review scans."""

    key_value = "sk-" + ("A" * 20)
    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )
    _write_changed_file(
        tmp_path,
        "DEEPSEEK_INBOX.md",
        f"# DeepSeek Inbox Shortcut\ndocs/handoff/deepseek_inbox.md\n{key_value}\n",
    )

    result = module.run_review_gate(tmp_path)

    assert any(hit.path == Path("DEEPSEEK_INBOX.md") for hit in result.secret_key_hits)
    assert all(hit.preview == "<redacted>" for hit in result.secret_key_hits)


def test_review_gate_json_report_is_machine_readable(tmp_path: Path) -> None:
    """Review gate results can be converted to JSON-safe data."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )

    result = module.run_review_gate(tmp_path)
    data = module.to_jsonable_result(result)

    assert data["ok"] is True
    assert data["changed_files"] == ["src/example.py"]
    assert json.loads(json.dumps(data))["ok"] is True


def test_review_gate_json_report_is_not_ok_on_scan_hits(tmp_path: Path) -> None:
    """Scan hits make the JSON report fail closed."""

    marker = "TO" + "DO"
    _write_changed_file(tmp_path, "src/example.py", f"VALUE = '{marker}'\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )

    result = module.run_review_gate(tmp_path)
    data = module.to_jsonable_result(result)

    assert data["ok"] is False
    assert data["blocked_term_hits"]


def test_review_gate_rejects_changed_file_outside_allowed_scope(tmp_path: Path) -> None:
    """Changed files must be included in the ready inbox allowed scope."""

    _write_changed_file(tmp_path, "src/outside.py", "VALUE = 1\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/outside.py"),
    )

    result = module.run_review_gate(tmp_path)

    assert "changed file is outside allowed scope: src/outside.py" in result.issues


def test_review_gate_rejects_changed_file_in_forbidden_scope(tmp_path: Path) -> None:
    """Changed files must not touch the ready inbox forbidden scope."""

    _write_changed_file(tmp_path, "src/private_root/private/example.py", "VALUE = 1\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(
            allowed_files=["src/private_root"],
            forbidden_files=["src/private_root/private"],
        ),
        outbox=_ready_outbox(changed_file="src/private_root/private/example.py"),
    )

    result = module.run_review_gate(tmp_path)

    assert "changed file touches forbidden scope: src/private_root/private/example.py" in result.issues


def test_review_gate_rejects_parent_traversal_changed_file(tmp_path: Path) -> None:
    """Changed file entries must not escape the repository root."""

    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="../outside.py"),
    )

    result = module.run_review_gate(tmp_path)

    assert "changed file path must be a safe repository-relative path: ../outside.py" in result.issues


def test_review_gate_rejects_dot_segment_changed_file(tmp_path: Path) -> None:
    """Changed file entries inherit raw handoff path safety checks."""

    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/./example.py"),
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox has unsafe changed file path: src/./example.py"
        in result.issues
    )


def test_review_gate_rejects_url_changed_file(tmp_path: Path) -> None:
    """Changed file entries must not be URLs."""

    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="https://example.com/file.py"),
    )

    result = module.run_review_gate(tmp_path)

    assert "changed file path must be a safe repository-relative path: https:/example.com/file.py" in result.issues


def test_review_gate_rejects_malformed_changed_file_code_span(tmp_path: Path) -> None:
    """Changed file entries must not contain embedded markdown backticks."""

    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example_pkg"]),
        outbox=_ready_outbox(
            changed_file="src/example_pkg`bad.py",
            verification_diff_paths="src/example_pkg src/example_pkg/example.py tests/example.py",
        ),
    )

    result = module.run_review_gate(tmp_path)

    assert "changed file path must be a safe repository-relative path: `src/example_pkg`bad.py`" in result.issues


def test_review_gate_rejects_duplicate_changed_file_entries(tmp_path: Path) -> None:
    """Changed file entries should not be duplicated in the outbox."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox_with_changed_files(["src/example.py", "src/example.py"]),
    )

    result = module.run_review_gate(tmp_path)

    assert "changed file path is duplicated in outbox: src/example.py" in result.issues


def test_review_gate_rejects_directory_changed_file_entry(tmp_path: Path) -> None:
    """Changed file entries must name concrete files, not directories."""

    (tmp_path / "src" / "example_pkg").mkdir(parents=True)
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example_pkg"]),
        outbox=_ready_outbox(
            changed_file="src/example_pkg",
            verification_diff_paths="src/example_pkg src/example_pkg/example.py tests/example.py",
        ),
    )

    result = module.run_review_gate(tmp_path)

    assert "changed file listed in outbox must be a file: src/example_pkg" in result.issues


def test_review_gate_rejects_declared_scope_deviation(tmp_path: Path) -> None:
    """Declared scope deviations require Codex review attention."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "## Scope Deviations\n- None.",
        "## Scope Deviations\n- Added docs/extra.md without assignment.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md lists scope deviations requiring Codex review: "
        "Added docs/extra.md without assignment."
    ) in result.issues


def test_review_gate_rejects_non_none_scope_deviation_stand_in(tmp_path: Path) -> None:
    """Codex review requires exact None for clean scope-deviation evidence."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "## Scope Deviations\n- None.",
        "## Scope Deviations\n- No scope deviations.",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md lists scope deviations requiring Codex review: "
        "No scope deviations."
    ) in result.issues


def test_review_gate_rejects_empty_scope_deviation_section(tmp_path: Path) -> None:
    """Ready outboxes must explicitly state whether scope deviations exist."""

    _write_changed_file(tmp_path, "src/example.py", "VALUE = 1\n")
    outbox = _ready_outbox(changed_file="src/example.py").replace(
        "## Scope Deviations\n- None.\n## Anti-Placeholder Scan",
        "## Scope Deviations\n## Anti-Placeholder Scan",
    )
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=outbox,
    )

    result = module.run_review_gate(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox must explicitly state scope deviations or None" in result.issues


def test_main_returns_success_for_waiting_state_when_allowed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI supports a pre-assignment health check mode."""

    _write_doc_set(tmp_path, outbox=_waiting_outbox())

    result = module.main(["--root", str(tmp_path), "--allow-waiting"])

    captured = capsys.readouterr()
    assert result == 0
    assert "codex review gate ok" in captured.out


def test_main_can_print_json_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI can print a machine-readable JSON report."""

    _write_doc_set(tmp_path, outbox=_waiting_outbox())

    result = module.main(["--root", str(tmp_path), "--allow-waiting", "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert result == 0
    assert data["ok"] is True
    assert data["status"] == "WAITING_FOR_TASK"


def test_main_returns_nonzero_for_secret_scan_hit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI fails when secret-shaped values are found."""

    key_value = "sk-" + ("A" * 20)
    _write_changed_file(tmp_path, "src/example.py", f"VALUE = '{key_value}'\n")
    _write_doc_set(
        tmp_path,
        inbox=_ready_deepseek_inbox(allowed_files=["src/example.py"]),
        outbox=_ready_outbox(changed_file="src/example.py"),
    )

    result = module.main(["--root", str(tmp_path)])

    captured = capsys.readouterr()
    assert result == 1
    assert "<redacted>" in captured.out
    assert key_value not in captured.out


def _write_doc_set(root: Path, *, outbox: str, inbox: str | None = None) -> None:
    handoff_dir = root / "docs" / "handoff"
    handoff_dir.mkdir(parents=True)

    _write(root / "AGENTS.md", "# Agent Rules\n")
    _write(root / "DEEPSEEK_INBOX.md", "# DeepSeek Inbox Shortcut\ndocs/handoff/deepseek_inbox.md\n")
    _write(root / "CODEX_REVIEW.md", "# Codex Review Shortcut\ndocs/handoff/codex_review_checklist.md\n")
    _write(root / "spec.md", "# Project Spec\n")
    _write(root / "architecture.md", "# Architecture Entry Point\n")
    _write(root / "task.md", "# Current Task Entry Point\n")
    _write(root / "progress.md", "# Progress Entry Point\n")
    _write(root / "decisions.md", "# Decisions\n")
    _write(root / "test_plan.md", "# Test Plan Entry Point\n")
    _write(handoff_dir / "deepseek_inbox.md", inbox or _deepseek_inbox())
    _write(handoff_dir / "deepseek_outbox.md", outbox)
    _write(handoff_dir / "codex_review_checklist.md", _codex_checklist())
    _write(handoff_dir / "dual_model_development_workflow.md", _workflow())
    _write(handoff_dir / "cross_platform_continuation.md", _cross_platform_continuation())
    _write(handoff_dir / "deepseek_task_template.md", _task_template())
    _write(handoff_dir / "deepseek_task_spec_schema.md", _task_spec_schema())
    _write(handoff_dir / "deepseek_assignment_examples.md", _assignment_examples())
    _write(handoff_dir / "codex_review_template.md", _review_template())


def _deepseek_inbox() -> str:
    return "\n".join(
        [
            "# DeepSeek Inbox",
            "Status: WAITING_FOR_TASK",
            "Message ID: unassigned",
            "Task: unassigned",
            "CODEX_GATE: REQUIRED",
            "## Operating Role",
            "- Worker.",
            "## Required Reading Before Editing",
            "- spec.md",
            "## Current Task",
            "- Waiting.",
            "## Global Implementation Rules",
            "- Stay scoped.",
            "## Anti-Placeholder Scan",
            "- Run the scan.",
            "## Required Outbox Evidence",
            "- READY_FOR_CODEX_REVIEW",
        ]
    )


def _ready_deepseek_inbox(
    *,
    allowed_files: list[str],
    forbidden_files: list[str] | None = None,
    worktree_baseline: list[str] | None = None,
) -> str:
    diff_check_paths = " ".join(dict.fromkeys([*allowed_files, "src/example.py", "tests/example.py"]))
    baseline_lines = (
        [f"- `{file_path}`" for file_path in worktree_baseline]
        if worktree_baseline
        else ["- None."]
    )
    return "\n".join(
        [
            "# DeepSeek Inbox",
            "Status: READY_FOR_DEEPSEEK",
            "Message ID: task-1",
            "Task: TASK_1",
            "CODEX_GATE: PASS",
            "## Operating Role",
            "- Worker.",
            "## Required Reading Before Editing",
            "- AGENTS.md",
            "- spec.md",
            "- architecture.md",
            "- task.md",
            "- docs/handoff/deepseek_inbox.md",
            "## Current Task",
            "- Implement one bounded change.",
            "## Global Implementation Rules",
            "- Stay scoped.",
            "## Objective",
            "- Implement the requested behavior.",
            "## Input Contracts",
            "- Preserve existing inputs for the assigned files.",
            "## Output Contracts",
            "- Preserve existing outputs for the assigned files.",
            "## Required Reading",
            "- `AGENTS.md`",
            "- `spec.md`",
            "- `architecture.md`",
            "- `task.md`",
            "- `docs/handoff/deepseek_inbox.md`",
            "## Allowed Files",
            *[f"- `{file_path}`" for file_path in allowed_files],
            "## Forbidden Files",
            *[f"- `{file_path}`" for file_path in (forbidden_files or ["src/forbidden.py"])],
            "## Worktree Baseline",
            *baseline_lines,
            "## Requirements",
            "1. Keep behavior deterministic.",
            "2. Preserve public interfaces.",
            "3. Add focused tests.",
            "## Acceptance Criteria",
            "- [ ] Happy path verified.",
            "- [ ] Error path verified.",
            "- [ ] Scope verified.",
            "## Verification Commands",
            "```powershell",
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py",
            f"git diff --check -- {diff_check_paths}",
            "```",
            "## Anti-Placeholder Scan",
            "- Run scoped scan.",
            "```powershell",
            _scan_command(allowed_files),
            "```",
            "## Stop Conditions",
            "- Stop if scope expands.",
            "- Stop if behavior is missing.",
            "- Stop if tests require weaker assertions.",
            "## Required Outbox",
            "- READY_FOR_CODEX_REVIEW",
            "- concrete summary with at least two bullet items",
            "- changed files",
            "- changed-file evidence must not list workflow control files",
            "- verification commands and exact results",
            "- clean result markers inside the backticked command text do not count as verification evidence",
            "- verification evidence must not say dry-run, manual-only, simulated, synthetic, or fabricated",
            "- checked acceptance evidence",
            "- Anti-Placeholder scan command and clean result",
            "- Anti-Placeholder clean result evidence must appear on the same line as the parseable scan command",
            "- scope deviations",
            "- unresolved questions or blockers",
            "## Required Outbox Evidence",
            "- READY_FOR_CODEX_REVIEW",
            "- concrete summary with at least two bullet items",
            "- changed files",
            "- changed-file evidence must not list workflow control files",
            "- verification commands and exact results",
            "- clean result markers inside the backticked command text do not count as verification evidence",
            "- verification evidence must not say dry-run, manual-only, simulated, synthetic, or fabricated",
            "- checked acceptance evidence",
            "- Anti-Placeholder scan command and clean result",
            "- Anti-Placeholder clean result evidence must appear on the same line as the parseable scan command",
            "- scope deviations",
            "- unresolved questions or blockers",
        ]
    )


def _scan_command(files: list[str]) -> str:
    pattern_args = " ".join(
        f'-e "{pattern}"' for pattern in module.validate_handoff_docs.ANTI_PLACEHOLDER_SCANNER_PATTERNS
    )
    return f"rg -n --pcre2 {pattern_args} -- {' '.join(files)}"


def _ready_deepseek_inbox_with_bullet_commands(*, allowed_files: list[str]) -> str:
    return _ready_deepseek_inbox(allowed_files=allowed_files).replace(
        "\n".join(
            [
                "## Verification Commands",
                "```powershell",
                "python -m pytest tests/example.py -q",
                "python -m ruff check src/example.py tests/example.py",
                "git diff --check -- src/example.py tests/example.py",
                "```",
            ]
        ),
        "\n".join(
            [
                "## Verification Commands",
                "- `python -m pytest tests/example.py -q`",
                "- `python -m ruff check src/example.py tests/example.py`",
                "- `git diff --check -- src/example.py tests/example.py`",
            ]
        ),
    )


def _waiting_outbox() -> str:
    return "\n".join(
        [
            "# DeepSeek Outbox",
            "Status: WAITING_FOR_TASK",
            "Message ID: unassigned",
            "Task: unassigned",
            "## Summary",
            "- Waiting.",
            "## Changed Files",
            "- None",
            "## Verification Commands and Results",
            "- Not run",
            "## Acceptance Criteria",
            "- Not applicable",
            "## Scope Deviations",
            "- None",
            "## Anti-Placeholder Scan",
            "- Not run",
            "## Unresolved Questions or Blockers",
            "- Waiting.",
        ]
    )


def _ready_outbox(
    *,
    changed_file: str,
    verification_diff_paths: str = "src/example.py tests/example.py",
) -> str:
    return _ready_outbox_with_changed_files(
        [changed_file],
        verification_diff_paths=verification_diff_paths,
    )


def _ready_outbox_with_changed_files(
    changed_files: list[str],
    *,
    verification_diff_paths: str = "src/example.py tests/example.py",
) -> str:
    return "\n".join(
        [
            "# DeepSeek Outbox",
            "Status: READY_FOR_CODEX_REVIEW",
            "Message ID: task-1",
            "Task: TASK_1",
            "READY_FOR_CODEX_REVIEW",
            "## Summary",
            "- Updated `src/example.py` for the assigned behavior.",
            "- Added verification evidence for `tests/example.py`.",
            "## Changed Files",
            *[f"- `{changed_file}`" for changed_file in changed_files],
            "## Verification Commands and Results",
            "- `python -m pytest tests/example.py -q` exited 0.",
            "- `python -m ruff check src/example.py tests/example.py` exited 0.",
            f"- `git diff --check -- {verification_diff_paths}` exited 0.",
            "## Acceptance Criteria",
            "- [x] Happy path verified.",
            "- [x] Error path verified.",
            "- [x] Scope verified.",
            "## Scope Deviations",
            "- None.",
            "## Anti-Placeholder Scan",
            f"- `{_scan_command(list(changed_files))}` returned no matches.",
            "## Unresolved Questions or Blockers",
            "- None.",
        ]
    )


def _codex_checklist() -> str:
    return "\n".join(
        [
            "# Codex Review Checklist",
            "## Blocking Checks",
            "- Check scope.",
            "- Ready outbox acceptance criteria are listed as checked `- [x] ...` evidence items.",
            "- Ready outbox checked acceptance evidence covers every assigned inbox criterion.",
            "- Ready outbox checked acceptance evidence starts with the assigned criterion.",
            "- Checked acceptance evidence is not skipped or not-executed.",
            "- Checked acceptance evidence is not unverified or untested.",
            "- Checked acceptance evidence is not pending, deferred, or marked as not applicable.",
            "- Ready outbox Anti-Placeholder evidence includes both scanner command and clean result.",
            "- Ready outbox Anti-Placeholder evidence is not an empty stand-in such as None, N/A, or no scan.",
            "- Ready outbox Anti-Placeholder evidence is not skipped, not-executed, or failing.",
            "- Ready outbox Anti-Placeholder clean result markers inside the backticked scan command text do not count as scan result evidence.",
            "- Ready outbox Anti-Placeholder clean result evidence appears on the parseable scanner command line.",
            "- Ready outbox Anti-Placeholder scan evidence uses parseable backticked bullet command result entries.",
            "- Ready outbox Anti-Placeholder scan command uses exact command text without shell control operators.",
            "- Ready outbox Anti-Placeholder scan command starts with `rg` or `rg.exe`.",
            "- Ready outbox Anti-Placeholder scan command includes every configured scanner pattern.",
            "- Ready outbox Anti-Placeholder scan command uses `--` before the path list.",
            "- Ready outbox Anti-Placeholder scan command does not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
            "- Ready outbox Anti-Placeholder scan command does not use response-file or splatting arguments such as `@args.txt`.",
            "- Ready outbox Anti-Placeholder scan command does not include unresolved angle-bracket markers.",
            "- Ready outbox Anti-Placeholder scan command mentions every changed file as a path token.",
            "- Ready outbox command-family evidence uses standalone command tokens.",
            "- Ready outbox verification evidence starts with direct command families, not shell wrappers.",
            "- Ready outbox verification evidence does not use shell redirection.",
            "- Ready outbox verification evidence does not use command substitution such as `$(...)` or backticks.",
            "- Ready outbox verification evidence does not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
            "- Ready outbox verification evidence does not use response-file or splatting arguments such as `@args.txt`.",
            "- Exact assigned-command matching covers fenced commands and backticked bullet commands.",
            "- Each assigned verification command has clean result evidence such as `exited 0`.",
            "- Clean result markers inside the backticked command text do not count as verification evidence.",
            "- Any failing result for an assigned verification command is a review issue, even if another result line is clean.",
            "- Verification result evidence that says a command was dry-run, manual-only, simulated, synthetic, or fabricated is treated as failing.",
            "- Ready outbox coverage-specific verification results are clean.",
            "- Ready outbox verification evidence does not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.",
            "- No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.",
            "- Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.",
            "- Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.",
            "- Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.",
            "- Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.",
            "- Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.",
            "- Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.",
            "- Ready outbox `pytest` evidence mentions every changed test Python file as a path token.",
            "- Ready outbox `ruff check` evidence mentions every changed Python file as a path token.",
            "- Ready outbox `git diff --check` evidence mentions every changed file as a path token.",
            "- Ready outbox `git diff --check` evidence with pathspecs uses `--` before the path list.",
            "- Ready outbox changed files stay within ready inbox allowed scope and outside forbidden scope.",
            "- Ready outbox changed-file evidence must not list workflow control files.",
            "- Pipeline check includes a scoped blocked-term scan over handoff utilities, focused tests, templates, `test_plan.md`, and `progress.md`.",
            "- Ready inbox allowed scope must not include workflow control files.",
            "- Ready inbox allowed scope must not use broad top-level directory scopes.",
            "- Ready inbox allowed and forbidden scope entries do not overlap entries in the same list.",
            "- Ready inbox path entries do not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes.",
            "- Review-ready workflow control file worktree changes must either appear in the assignment-time baseline or block Codex review.",
            "- Review-ready handoff control file worktree changes must either appear in the assignment-time baseline or block Codex review.",
            "- Ready inbox requirements are unique and include at least three numbered items.",
            "- Ready inbox acceptance criteria are unique and include at least three unchecked items.",
            "- Ready inbox stop conditions are unique and include at least three items.",
            "- Ready inbox sections do not contain unresolved angle-bracket markers.",
            "- Ready inbox required-reading entries may include the canonical inbox.",
            "- Ready inbox required-reading sections include `AGENTS.md`, `spec.md`, `architecture.md`, `task.md`, and `docs/handoff/deepseek_inbox.md`.",
            "- Ready inbox includes non-empty `## Input Contracts` and `## Output Contracts` sections.",
            "- Ready inbox contract items cannot be empty stand-ins such as None, N/A, TBD, or unknown.",
            "- Ready inbox task text values must not use empty stand-ins such as None, N/A, TBD, or unknown.",
            "- Ready inbox path entries do not use empty stand-ins such as None, N/A, TBD, or unknown.",
            "- Ready inbox path entries do not contain wildcards or glob metacharacters.",
            "- Ready inbox path entries do not contain embedded whitespace.",
            "- Ready inbox path entries do not target VCS, dependency, or cache directories.",
            "- Ready inbox includes a dedicated `## Required Outbox Evidence` section.",
            "- Ready inbox `## Required Outbox` section lists the same evidence categories required from DeepSeek.",
            "- Ready inbox `## Required Outbox Evidence` section lists changed files, verification commands, checked acceptance, scan, scope deviations, and unresolved questions or blockers.",
            "- Ready inbox required outbox evidence says Anti-Placeholder clean result evidence must appear on the same line as the parseable scan command.",
            "- Ready inbox required outbox evidence entries are unique and listed as at least eight bullet items.",
            "- Ready outbox summary uses at least two concrete bullet items and not generic completion wording.",
            "- Ready inbox worktree baseline entries do not overlap allowed files.",
            "- Review-ready worktree baseline entries must still be dirty in git status.",
            "- Ready inbox verification commands are unique.",
            "- Ready inbox verification commands use standalone command tokens and no shell control operators.",
            "- Ready inbox verification commands start with direct command families, not shell wrappers.",
            "- Ready inbox verification commands do not use shell redirection.",
            "- Ready inbox verification commands do not use command substitution such as `$(...)` or backticks.",
            "- Ready inbox verification commands do not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
            "- Ready inbox verification commands do not use response-file or splatting arguments such as `@args.txt`.",
            "- Ready inbox verification commands do not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.",
            "- No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.",
            "- Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.",
            "- Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.",
            "- Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.",
            "- Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.",
            "- Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.",
            "- Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.",
            "- Ready inbox verification commands mention each concrete allowed file as a path token.",
            "- Ready inbox `git diff --check` commands mention every allowed file or directory scope as a path token.",
            "- Ready inbox `git diff --check` commands with pathspecs use `--` before the path list.",
        "- Ready inbox Anti-Placeholder scan command includes a concrete scanner expression.",
        "- Ready inbox Anti-Placeholder scan command starts with `rg` or `rg.exe`.",
        "- Ready inbox Anti-Placeholder scan command includes every configured scanner pattern.",
        "- Ready inbox Anti-Placeholder scan command uses `--` before the path list.",
        "- Ready inbox Anti-Placeholder scan command does not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "- Ready inbox Anti-Placeholder scan command does not use response-file or splatting arguments such as `@args.txt`.",
        "- Ready inbox Anti-Placeholder scan command mentions every allowed file as a path token.",
            "- `## Unresolved Questions or Blockers` is explicit.",
            "## Risk Review",
            "- Check regressions.",
            "## Output Format",
            "- Findings first.",
        ]
    )


def _workflow() -> str:
    return "\n".join(
        [
            "# Dual-Model Development Workflow",
            "Cross-platform continuation instructions live in `docs/handoff/cross_platform_continuation.md`.",
            "Ready outbox changed files must stay within ready inbox allowed scope and outside forbidden scope.",
            "Ready outbox checked acceptance evidence must cover every assigned inbox criterion.",
            "Checked acceptance evidence that says verification was skipped or not executed is rejected.",
            "Checked acceptance evidence that says coverage is unverified or untested is rejected.",
            "Checked acceptance evidence that says coverage is pending, deferred, or not applicable is rejected.",
        "Ready outbox Anti-Placeholder evidence must include the scanner command.",
        "Ready outbox Anti-Placeholder scan command must not use shell control operators.",
        "Ready outbox Anti-Placeholder scan command must start with `rg` or `rg.exe`.",
        "Ready outbox Anti-Placeholder scan command must include every configured scanner pattern.",
        "Ready outbox Anti-Placeholder scan command must use `--` before the path list.",
        "Ready outbox Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Ready outbox Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`.",
        "Ready outbox Anti-Placeholder scan command must not include unresolved angle-bracket markers.",
        "Ready outbox Anti-Placeholder clean result markers inside the backticked scan command text do not count as scan result evidence.",
        "Ready outbox Anti-Placeholder clean result evidence must appear on the parseable scanner command line.",
            "Ready outbox Anti-Placeholder scan command must mention every changed file as a path token.",
            "Verification result evidence that says a command was skipped or not executed is treated as failing.",
            "Verification result evidence that says a command was dry-run, manual-only, simulated, synthetic, or fabricated is treated as failing.",
            "Clean result markers inside the backticked command text do not count as verification evidence.",
            "Ready outbox verification results must include every assigned inbox command with clean result evidence.",
            "Ready outbox coverage-specific verification results must be clean.",
            "Ready outbox verification evidence must start with direct command families, not shell wrappers.",
            "Ready outbox verification evidence must not use shell redirection.",
            "Ready outbox verification evidence must not use command substitution such as `$(...)` or backticks.",
            "Ready outbox verification evidence must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
            "Ready outbox verification evidence must not use response-file or splatting arguments such as `@args.txt`.",
            "Ready outbox verification evidence must not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.",
            "No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.",
            "Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.",
            "Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.",
            "Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.",
            "Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.",
            "Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.",
            "Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.",
            "Ready outbox `pytest` evidence must mention every changed test Python file as a path token.",
            "Ready outbox `ruff check` evidence must mention every changed Python file as a path token.",
            "Ready outbox `git diff --check` evidence must mention every changed file as a path token.",
            "Ready outbox `git diff --check` evidence with pathspecs must use `--` before the path list.",
            "Ready outbox changed-file evidence must not list workflow control files.",
            "Pipeline check includes a scoped blocked-term scan over handoff utilities, focused tests, templates, `test_plan.md`, and `progress.md`.",
            "Ready inbox allowed scope must not include workflow control files.",
            "Ready inbox allowed scope must not use broad top-level directory scopes.",
            "Ready inbox allowed and forbidden scope entries do not overlap entries in the same list.",
            "Ready inbox path entries must not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes.",
            "Review-ready workflow control file worktree changes must either appear in the assignment-time baseline or block Codex review.",
            "Review-ready handoff control file worktree changes must either appear in the assignment-time baseline or block Codex review.",
            "Ready inbox requirements must be unique and include at least three numbered items.",
            "Ready inbox acceptance criteria must be unique and include at least three unchecked items.",
            "Ready inbox stop conditions must be unique and include at least three items.",
            "Ready inbox sections with unresolved angle-bracket markers are rejected.",
            "Ready inbox required-reading paths may include the canonical inbox.",
            "Both ready inbox required-reading sections must include `AGENTS.md`, `spec.md`, `architecture.md`, `task.md`, and `docs/handoff/deepseek_inbox.md`.",
            "Ready inbox tasks must include non-empty `## Input Contracts` and `## Output Contracts` sections.",
            "Ready inbox contract items must not be empty stand-ins such as None, N/A, TBD, or unknown.",
            "Ready inbox task text values must not use empty stand-ins such as None, N/A, TBD, or unknown.",
            "Ready inbox path entries must not use empty stand-ins such as None, N/A, TBD, or unknown.",
            "Ready inbox path entries must not contain wildcards or glob metacharacters.",
            "Ready inbox path entries must not contain embedded whitespace.",
            "Ready inbox path entries must not target VCS, dependency, or cache directories.",
            "Ready inbox tasks must keep a dedicated `## Required Outbox Evidence` section.",
            "Ready inbox `## Required Outbox` section must list the same evidence categories required from DeepSeek.",
            "Ready inbox `## Required Outbox Evidence` section must list changed files, verification commands, checked acceptance, scan, scope deviations, and unresolved questions or blockers.",
            "Ready inbox required outbox evidence must say Anti-Placeholder clean result evidence appears on the same line as the parseable scan command.",
            "Ready inbox required outbox evidence entries must be unique and listed as at least eight bullet items.",
            "Ready outbox summary must use at least two concrete bullet items and not generic completion wording.",
            "Worktree baseline entries must not overlap allowed files.",
            "Review-ready worktree baseline entries must still be dirty in git status.",
            "Ready inbox verification commands must be unique.",
            "Ready inbox verification commands must use standalone command tokens and no shell control operators.",
            "Ready inbox verification commands must start with direct command families, not shell wrappers.",
            "Ready inbox verification commands must not use shell redirection.",
            "Ready inbox verification commands must not use command substitution such as `$(...)` or backticks.",
            "Ready inbox verification commands must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
            "Ready inbox verification commands must not use response-file or splatting arguments such as `@args.txt`.",
            "Ready inbox verification commands must not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.",
            "No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.",
            "Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.",
            "Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.",
            "Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.",
            "Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.",
            "Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.",
            "Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.",
            "Ready inbox verification commands must mention each concrete allowed file as a path token.",
            "Ready inbox `git diff --check` commands must mention every allowed file or directory scope as a path token.",
            "Ready inbox `git diff --check` commands with pathspecs must use `--` before the path list.",
        "Ready inbox Anti-Placeholder scan command must include a concrete scanner expression.",
        "Ready inbox Anti-Placeholder scan command must start with `rg` or `rg.exe`.",
        "Ready inbox Anti-Placeholder scan command must include every configured scanner pattern.",
        "Ready inbox Anti-Placeholder scan command must use `--` before the path list.",
        "Ready inbox Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Ready inbox Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`.",
        "Ready inbox Anti-Placeholder scan command must mention every allowed file as a path token.",
            "## Flow",
            "- Codex assigns.",
            "## Task Size Rules",
            "- Small.",
            "## Required DeepSeek Task Template",
            "- Template.",
            "## Completion Is Not Self-Certifying",
            "- Codex verifies.",
        ]
    )


def _cross_platform_continuation() -> str:
    return "\n".join(
        [
            "# Cross-Platform Continuation Guide",
            "## GitHub Continuation",
            "codex/dual-model-research-mvp",
            "git clone https://github.com/KUIGE22/dayu-agent.git",
            "git checkout codex/dual-model-research-mvp",
            "git log -1 --oneline",
            "## macOS / Linux Setup",
            "python3.11 -m venv .venv",
            "source .venv/bin/activate",
            "## Windows Setup",
            "py -3.11 -m venv .venv",
            ".\\.venv\\Scripts\\Activate.ps1",
            "## Required Gate Commands",
            "python -m utils.validate_handoff_docs --json",
            "python -m utils.codex_review_gate --allow-waiting --json",
            "python -m utils.dual_model_pipeline_check --json",
            "Do not reuse absolute local paths from another computer.",
        ]
    )


def _task_template() -> str:
    return "\n".join(
        [
            "# Current Task: <short title>",
            "Status: READY_FOR_DEEPSEEK",
            "Message ID: <id>",
            "Task: <task>",
            "CODEX_GATE: PASS",
            "## Objective",
            "- Objective.",
            "## Required Reading",
            "- `AGENTS.md`",
            "- `spec.md`",
            "- `architecture.md`",
            "- `task.md`",
            "- `docs/handoff/deepseek_inbox.md`",
            "## Input Contracts",
            "Do not use empty stand-ins such as None, N/A, TBD, or unknown as a contract.",
            "## Output Contracts",
            "## Allowed Files",
            "- Files.",
            "## Forbidden Files",
            "- Files.",
            "## Worktree Baseline",
            "- None.",
            "Worktree baseline entries must not overlap allowed files.",
            "Requirements must be unique and include at least three numbered items.",
            "## Acceptance Criteria",
            "- Criteria.",
            "Acceptance criteria must be unique and include at least three unchecked items.",
            "Remove every angle-bracket marker before assigning the task.",
            "## Verification Commands",
            "- Commands.",
            "Verification commands must be unique standalone command tokens and must not use shell control operators.",
            "Verification commands must start with direct command families, not shell wrappers.",
            "Verification commands must not use shell redirection.",
            "Verification commands must not use command substitution such as `$(...)` or backticks.",
            "Verification commands must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
            "Verification commands must not use response-file or splatting arguments such as `@args.txt`.",
            "Verification commands must not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.",
            "No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.",
            "Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.",
            "Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.",
            "Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.",
            "Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.",
            "Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.",
            "Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.",
            "Verification commands must mention each concrete allowed file as a path token.",
            "Git diff-check commands must mention every allowed file or directory scope as a path token.",
            "Git diff-check commands with pathspecs must use `--` before the path list.",
            "Path values must not use wildcards or glob metacharacters.",
            "Path values must not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes.",
            "Path values must not use empty stand-ins such as None, N/A, TBD, or unknown.",
            "Path values must not contain embedded whitespace.",
            "Path values must not target VCS, dependency, or cache directories.",
            "Task text values must not use empty stand-ins such as None, N/A, TBD, or unknown.",
            "Allowed files must not include workflow control files such as handoff docs, root task plans, gate utilities, or CI gates.",
            "Allowed files must not use broad top-level directory scopes such as `dayu`, `docs`, `src`, `tests`, `utils`, `.github`, or `workspace`.",
            "Allowed and forbidden files must not contain overlapping scope entries within the same list.",
            "Generated worktree baseline entries must not overlap `allowed_files`.",
            "## Anti-Placeholder Scan",
            "- Scan.",
        "Replace `BLOCKED_SCANNER_PATTERN` with the actual scanner expression before assigning the task.",
        "Anti-Placeholder scan command must start with `rg` or `rg.exe`.",
        "Anti-Placeholder scan command must include every configured scanner pattern.",
        "Anti-Placeholder scan command must use `--` before the path list.",
        "Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`.",
        "Anti-Placeholder scan command must mention every allowed file as a path token.",
            "## Stop Conditions",
            "- Stop.",
            "Stop conditions must be unique and include at least three items.",
            "## Required Outbox",
            "- concrete summary with at least two bullet items",
            "- changed-file evidence must not list workflow control files",
            "- checked `- [x] ...` evidence items",
            "- verification evidence must not say dry-run, manual-only, simulated, synthetic, or fabricated",
            "- checked acceptance evidence must not say skipped, unverified, untested, pending, deferred, or not applicable",
            "- Anti-Placeholder scan command and clean result",
            "- Anti-Placeholder scan command must be exact and must not use shell control operators",
            "- Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`",
            "- Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`",
            "- Anti-Placeholder scan command must not include unresolved angle-bracket markers",
            "- Anti-Placeholder clean result markers inside the backticked scan command text do not count as scan result evidence",
            "- Anti-Placeholder clean result evidence must appear on the same line as the parseable scan command",
            "- Anti-Placeholder evidence must not say skipped, not executed, not scanned, or no scan",
            "- explicit `None` when no unresolved questions or blockers remain",
            "- READY_FOR_CODEX_REVIEW",
        ]
    )


def _assignment_examples() -> str:
    return "\n".join(
        [
            "# DeepSeek Assignment Examples",
            "## Preview First",
            "python -m utils.prepare_deepseek_task",
            "--dry-run",
            "## Write And Reset",
            "--reset-outbox",
            "--validate-repository",
            "## Spec File Variant",
            "--spec-file",
            "Extra required-reading entries must not list mutable handoff control files",
            "## Validate",
            "python -m utils.validate_handoff_docs --json",
            "python -m utils.dual_model_pipeline_check --json",
            "## Review",
            "python -m utils.codex_review_gate --json",
            "READY_FOR_CODEX_REVIEW",
        ]
    )


def _task_spec_schema() -> str:
    return "\n".join(
        [
            "# DeepSeek Task Spec Schema",
            "python -m utils.prepare_deepseek_task --spec-file",
            "## Required Fields",
            "`message_id`",
            "`allowed_files`",
            "`requirements` entries must be unique and include at least 3 items.",
            "`acceptance_criteria` entries must be unique and include at least 3 items.",
            "`stop_conditions` entries must be unique and include at least 3 items.",
            "Spec values must not contain angle-bracket markers.",
            "`verification_commands`",
            "`input_contracts`",
            "`output_contracts`",
            "`input_contracts` and `output_contracts` entries cannot be empty stand-ins such as None, N/A, TBD, or unknown.",
            "Spec-file list-type errors report the field name and 1-based item index for a non-string entry.",
            "Task text values must not use empty stand-ins such as None, N/A, TBD, or unknown.",
            "Path values must not use wildcards or glob metacharacters.",
            "Path values must not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes.",
            "Path values must not use empty stand-ins such as None, N/A, TBD, or unknown.",
            "Path values must not contain embedded whitespace.",
            "Path values must not target VCS, dependency, or cache directories.",
            "`allowed_files` and `forbidden_files` must not contain overlapping scope entries within the same list.",
            "Verification commands must use standalone command tokens and no shell control operators.",
            "Verification commands must start with direct command families, not shell wrappers.",
            "Verification commands must not use shell redirection.",
            "Verification commands must not use command substitution such as `$(...)` or backticks.",
            "Verification commands must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
            "Verification commands must not use response-file or splatting arguments such as `@args.txt`.",
            "Verification commands must not include unsafe verification flags such as `--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.",
            "No-run or mutating verification flags such as `--co`, `--fixtures`, `--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.",
            "Rerun-only or early-stop verification flags such as `--lf`, `--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.",
            "Rule-selection or config-override verification flags such as `--select`, `--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.",
            "Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, `--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.",
            "Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.",
            "Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.",
            "Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.",
            "Verification commands must mention each concrete allowed file as a path token.",
            "Git diff-check commands must mention every allowed file or directory scope as a path token.",
        "Git diff-check commands with pathspecs must use `--` before the path list.",
        "Generated assignments include a concrete Anti-Placeholder scan command over `allowed_files`.",
        "Generated Anti-Placeholder scan commands start with `rg`.",
        "Generated Anti-Placeholder scan commands include every configured scanner pattern.",
        "Generated Anti-Placeholder scan commands use `--` before the path list.",
        "Generated Anti-Placeholder scan commands do not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Generated Anti-Placeholder scan commands do not use response-file or splatting arguments such as `@args.txt`.",
        "`allowed_files` must not include workflow control files such as handoff docs, root task plans, gate utilities, or CI gates.",
        "`allowed_files` must not use broad top-level directory scopes such as `dayu`, `docs`, `src`, `tests`, `utils`, `.github`, or `workspace`.",
            "Generated worktree baseline entries must not overlap `allowed_files`.",
            "## Optional Fields",
            "`required_reading`",
            "Generated assignments always include `AGENTS.md`, `spec.md`, `architecture.md`, `task.md`, and `docs/handoff/deepseek_inbox.md`.",
            "`stop_conditions`",
            "## Validation",
            "--dry-run",
            "--reset-outbox",
            "--validate-repository",
            "The `--spec-file` value must be a readable JSON file, not a directory.",
            "The `--spec-file` content must be UTF-8 JSON text.",
            "embedded Markdown backticks",
            "`required_reading` must not list mutable handoff control files",
        ]
    )


def _review_template() -> str:
    return "\n".join(
        [
            "# Codex Review Record",
            "Status: DRAFT",
            "Reviewed Message ID: <id>",
            "Reviewed Task: <task>",
            "## Blocking Issues",
            "- None.",
            "## Acceptance Criteria Verification",
            "- Pending.",
            "## Verification Performed by Codex",
            "- Pending.",
            "## Anti-Placeholder Scan",
            "- Pending.",
            "## Scope Check",
            "- Pending.",
            "## Decision",
            "- Pending.",
        ]
    )


def _write_changed_file(root: Path, relative_path: str, text: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(path, text)


def _write(path: Path, text: str) -> None:
    path.write_text(text + "\n", encoding="utf-8")


def _init_git_repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "codex@example.invalid")
    _git(root, "config", "user.name", "Codex Test")


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=True,
        text=True,
    )
