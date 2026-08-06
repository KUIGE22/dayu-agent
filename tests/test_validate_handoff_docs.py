"""Tests for the DeepSeek/Codex handoff document validator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils import validate_handoff_docs as module

pytestmark = pytest.mark.unit


def test_validate_handoff_docs_accepts_waiting_state(tmp_path: Path) -> None:
    """A complete handoff document set may wait for a task without evidence."""

    _write_valid_handoff_docs(tmp_path)

    assert module.validate_handoff_docs(tmp_path) == []


def test_validate_handoff_docs_rejects_waiting_state_with_stale_outbox_metadata(tmp_path: Path) -> None:
    """Waiting-for-task outboxes must not retain stale assignment metadata."""

    _write_valid_handoff_docs(
        tmp_path,
        outbox_status=module.WAITING_FOR_TASK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md waiting state must reset Message ID: unassigned" in issues
    assert "docs/handoff/deepseek_outbox.md waiting state must reset Task: unassigned" in issues


def test_validate_handoff_docs_rejects_waiting_state_with_stale_inbox_metadata(tmp_path: Path) -> None:
    """Waiting-for-task inboxes must not retain stale assignment metadata."""

    inbox = (
        _waiting_deepseek_inbox()
        .replace("Message ID: unassigned", "Message ID: codex-task-1")
        .replace("Task: unassigned", "Task: TASK_1")
    )
    _write_valid_handoff_docs(tmp_path, inbox_text=inbox)

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_inbox.md waiting state must reset Message ID: unassigned" in issues
    assert "docs/handoff/deepseek_inbox.md waiting state must reset Task: unassigned" in issues


def test_json_report_is_machine_readable(tmp_path: Path) -> None:
    """The validator exposes a compact structured report."""

    _write_valid_handoff_docs(tmp_path)

    issues = module.validate_handoff_docs(tmp_path)
    report = module.to_jsonable_report(issues)

    assert report == {"ok": True, "issues": []}


def test_validate_handoff_docs_rejects_missing_required_file(tmp_path: Path) -> None:
    """Required top-level control files must be present."""

    _write_valid_handoff_docs(tmp_path)
    (tmp_path / "task.md").unlink()

    issues = module.validate_handoff_docs(tmp_path)

    assert "missing required file: task.md" in issues


def test_validate_handoff_docs_rejects_missing_cross_platform_continuation_doc(tmp_path: Path) -> None:
    """Cross-platform continuation guidance is part of the required handoff set."""

    _write_valid_handoff_docs(tmp_path)
    (tmp_path / "docs" / "handoff" / "cross_platform_continuation.md").unlink()

    issues = module.validate_handoff_docs(tmp_path)

    assert "missing required file: docs/handoff/cross_platform_continuation.md" in issues


@pytest.mark.parametrize(
    ("shortcut_path", "expected_target"),
    [
        ("DEEPSEEK_INBOX.md", "docs/handoff/deepseek_inbox.md"),
        ("CODEX_REVIEW.md", "docs/handoff/codex_review_checklist.md"),
    ],
)
def test_validate_handoff_docs_rejects_root_shortcut_target_drift(
    tmp_path: Path,
    shortcut_path: str,
    expected_target: str,
) -> None:
    """Root shortcut files must keep pointing to canonical handoff files."""

    _write_valid_handoff_docs(tmp_path)
    (tmp_path / shortcut_path).write_text("Read docs/handoff/other.md\n", encoding="utf-8")

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{shortcut_path} must point to {expected_target}" in issues


@pytest.mark.parametrize(
    "required_text",
    [
        "checked acceptance evidence must not say skipped, unverified, untested, pending, deferred, or not applicable",
        "Anti-Placeholder scan command must be exact and must not use shell control operators",
        "Anti-Placeholder scan command must not include unresolved angle-bracket markers",
        "Anti-Placeholder scan command must use `--` before the path list.",
        "Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Anti-Placeholder clean result markers inside the backticked scan command text do not count as scan result evidence",
        "Anti-Placeholder clean result evidence must appear on the same line as the parseable scan command",
        "Anti-Placeholder evidence must not say skipped, not executed, not scanned, or no scan",
    ],
)
def test_validate_handoff_docs_preserves_task_template_evidence_warnings(
    tmp_path: Path,
    required_text: str,
) -> None:
    """The reusable task template must keep evidence-quality warnings."""

    _write_valid_handoff_docs(tmp_path)
    template_path = tmp_path / "docs" / "handoff" / "deepseek_task_template.md"
    template_path.write_text(
        template_path.read_text(encoding="utf-8").replace(required_text, "removed evidence warning"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"docs/handoff/deepseek_task_template.md is missing required text: {required_text}" in issues


def test_validate_handoff_docs_preserves_task_template_broad_scope_warning(tmp_path: Path) -> None:
    """The reusable task template must keep broad allowed-scope warnings."""

    required_text = (
        "Allowed files must not use broad top-level directory scopes such as "
        "`dayu`, `docs`, `src`, `tests`, `utils`, `.github`, or `workspace`."
    )
    _write_valid_handoff_docs(tmp_path)
    template_path = tmp_path / "docs" / "handoff" / "deepseek_task_template.md"
    template_path.write_text(
        template_path.read_text(encoding="utf-8").replace(required_text, "removed broad scope warning"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"docs/handoff/deepseek_task_template.md is missing required text: {required_text}" in issues


def test_validate_handoff_docs_preserves_task_spec_broad_scope_warning(tmp_path: Path) -> None:
    """The JSON task-spec schema must keep broad allowed-scope warnings."""

    required_text = (
        "`allowed_files` must not use broad top-level directory scopes such as "
        "`dayu`, `docs`, `src`, `tests`, `utils`, `.github`, or `workspace`."
    )
    _write_valid_handoff_docs(tmp_path)
    schema_path = tmp_path / "docs" / "handoff" / "deepseek_task_spec_schema.md"
    schema_path.write_text(
        schema_path.read_text(encoding="utf-8").replace(required_text, "removed broad scope warning"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"docs/handoff/deepseek_task_spec_schema.md is missing required text: {required_text}" in issues


@pytest.mark.parametrize(
    "required_text",
    [
        "Checked acceptance evidence is not skipped or not-executed",
        "Checked acceptance evidence is not unverified or untested",
        "Checked acceptance evidence is not pending, deferred, or marked as not applicable",
        "Ready outbox Anti-Placeholder evidence is not an empty stand-in such as None, N/A, or no scan",
        "Ready outbox Anti-Placeholder evidence is not skipped, not-executed, or failing",
        "Ready outbox Anti-Placeholder clean result markers inside the backticked scan command text do not count as scan result evidence.",
        "Ready outbox Anti-Placeholder clean result evidence appears on the parseable scanner command line.",
    ],
)
def test_validate_handoff_docs_preserves_review_checklist_evidence_warnings(
    tmp_path: Path,
    required_text: str,
) -> None:
    """The Codex review checklist must keep evidence-quality warnings."""

    _write_valid_handoff_docs(tmp_path)
    checklist_path = tmp_path / "docs" / "handoff" / "codex_review_checklist.md"
    checklist_path.write_text(
        checklist_path.read_text(encoding="utf-8").replace(required_text, "removed evidence warning"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"docs/handoff/codex_review_checklist.md is missing required text: {required_text}" in issues


@pytest.mark.parametrize(
    "required_text",
    [
        "Cross-platform continuation instructions live in `docs/handoff/cross_platform_continuation.md`.",
        "Checked acceptance evidence that says verification was skipped or not executed is rejected",
        "Checked acceptance evidence that says coverage is unverified or untested is rejected",
        "Checked acceptance evidence that says coverage is pending, deferred, or not applicable is rejected",
        "Ready outbox Anti-Placeholder evidence must include the scanner command",
        "Ready outbox Anti-Placeholder scan command must not use shell control operators.",
        "Ready outbox Anti-Placeholder scan command must start with `rg` or `rg.exe`.",
        "Ready outbox Anti-Placeholder scan command must not include unresolved angle-bracket markers.",
        "Ready outbox Anti-Placeholder clean result evidence must appear on the parseable scanner command line.",
        "Verification result evidence that says a command was skipped or not executed is treated as failing",
        "Ready inbox `git diff --check` commands must mention every allowed file or directory scope as a path token.",
    ],
)
def test_validate_handoff_docs_preserves_workflow_evidence_warnings(
    tmp_path: Path,
    required_text: str,
) -> None:
    """The workflow guide must keep evidence-quality warnings."""

    _write_valid_handoff_docs(tmp_path)
    workflow_path = tmp_path / "docs" / "handoff" / "dual_model_development_workflow.md"
    workflow_path.write_text(
        workflow_path.read_text(encoding="utf-8").replace(required_text, "removed evidence warning"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"docs/handoff/dual_model_development_workflow.md is missing required text: {required_text}" in issues


@pytest.mark.parametrize(
    "required_text",
    [
        "## GitHub Continuation",
        "codex/dual-model-research-mvp",
        "git clone https://github.com/KUIGE22/dayu-agent.git",
        "git checkout codex/dual-model-research-mvp",
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
    ],
)
def test_validate_handoff_docs_preserves_cross_platform_continuation_guide(
    tmp_path: Path,
    required_text: str,
) -> None:
    """The continuation guide must keep clone, setup, and gate instructions."""

    _write_valid_handoff_docs(tmp_path)
    continuation_path = tmp_path / "docs" / "handoff" / "cross_platform_continuation.md"
    continuation_path.write_text(
        continuation_path.read_text(encoding="utf-8").replace(required_text, "removed continuation text"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"docs/handoff/cross_platform_continuation.md is missing required text: {required_text}" in issues


def test_validate_handoff_docs_rejects_ready_outbox_without_verification(tmp_path: Path) -> None:
    """A ready-for-review outbox cannot claim unrun verification."""

    _write_valid_handoff_docs(tmp_path, outbox_status=module.READY_FOR_REVIEW)

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready section cannot contain 'Not run': ## Verification Commands and Results" in issue for issue in issues)
    assert any("ready section cannot contain 'Not run': ## Anti-Placeholder Scan" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_outbox_with_lowercase_not_run(tmp_path: Path) -> None:
    """Ready outbox verification evidence cannot hide unrun commands by case."""

    _write_valid_handoff_docs(tmp_path, outbox_status=module.READY_FOR_REVIEW)
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace("Not run", "not run"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready section cannot contain 'Not run': ## Verification Commands and Results" in issue for issue in issues)


def test_validate_handoff_docs_rejects_skipped_ready_outbox_verification(tmp_path: Path) -> None:
    """Skipped verification is not accepted as clean evidence."""

    _write_valid_handoff_docs(tmp_path, outbox_status=module.READY_FOR_REVIEW)
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "`python -m pytest tests/example.py -q` skipped, exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox verification result must be clean for: pytest" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_outbox_without_concrete_metadata(tmp_path: Path) -> None:
    """Ready outbox metadata must name the assigned delivery."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8")
        .replace("Message ID: codex-task-1", "Message ID: unassigned")
        .replace("Task: TASK_1", "Task: <task>"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox must set a concrete Message ID" in issues
    assert "docs/handoff/deepseek_outbox.md ready outbox must set a concrete Task" in issues


def test_validate_handoff_docs_rejects_ready_outbox_metadata_stand_ins(tmp_path: Path) -> None:
    """Ready outbox metadata cannot use empty task stand-ins."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8")
        .replace("Message ID: codex-task-1", "Message ID: unknown")
        .replace("Task: TASK_1", "Task: TBD"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox Message ID must not use empty stand-in: unknown"
        in issues
    )
    assert "docs/handoff/deepseek_outbox.md ready outbox Task must not use empty stand-in: TBD" in issues


def test_validate_handoff_docs_rejects_ready_outbox_with_too_short_summary(tmp_path: Path) -> None:
    """Ready outbox summaries need enough detail for review triage."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "## Summary\n- Updated `src/example.py` for the assigned behavior.\n- Added verification evidence for `tests/example.py`.",
            "## Summary\n- Updated `src/example.py` for the assigned behavior.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox summary must include at least 2 concrete bullet items" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_outbox_generic_summary_item(tmp_path: Path) -> None:
    """Ready outbox summaries cannot be generic completion claims."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "- Updated `src/example.py` for the assigned behavior.",
            "- Implemented.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox summary item is too generic: Implemented." in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_outbox_without_changed_files(tmp_path: Path) -> None:
    """Ready outbox changed-file evidence must name at least one file."""

    _write_valid_handoff_docs(tmp_path, outbox_status=module.READY_FOR_REVIEW)
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace("- src/example.py", "- None"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox must list changed files" in issues


def test_validate_handoff_docs_rejects_ready_outbox_punctuated_no_change_evidence(tmp_path: Path) -> None:
    """Ready outbox changed-file evidence cannot hide empty evidence with punctuation."""

    _write_valid_handoff_docs(tmp_path, outbox_status=module.READY_FOR_REVIEW)
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace("- src/example.py", "- None."),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox must list changed files" in issues


def test_validate_handoff_docs_rejects_mixed_ready_outbox_no_change_and_paths(tmp_path: Path) -> None:
    """Ready outbox changed-file evidence cannot mix empty evidence and paths."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "- src/example.py",
            "- None.\n- src/example.py",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox changed files cannot mix no-change evidence with paths"
    ) in issues


def test_validate_handoff_docs_rejects_unsafe_ready_outbox_changed_file_paths(tmp_path: Path) -> None:
    """Ready outbox changed-file evidence must contain safe unique repository paths."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "- src/example.py",
            "\n".join(
                [
                    "- `../outside.py`",
                    "- `https://example.com/file.py`",
                    "- `src`bad.py`",
                    "- `src/example.py`",
                    "- `src/example.py`",
                ]
            ),
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("unsafe changed file path: ../outside.py" in issue for issue in issues)
    assert any("unsafe changed file path: https://example.com/file.py" in issue for issue in issues)
    assert any("unsafe changed file path: `src`bad.py`" in issue for issue in issues)
    assert any("duplicate changed file path: src/example.py" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_outbox_changed_file_outside_assigned_scope(tmp_path: Path) -> None:
    """Ready outbox changed files must stay inside assigned allowed scope."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace("- src/example.py", "- docs/extra.md"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.OUTBOX_PATH.as_posix()} changed file is outside assigned allowed scope: docs/extra.md" in issues


def test_validate_handoff_docs_rejects_ready_outbox_changed_file_inside_forbidden_scope(tmp_path: Path) -> None:
    """Ready outbox changed files must not touch assigned forbidden scope."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            allowed_files=["src/public.py", "tests/example.py"],
            forbidden_files=["src/private.py"],
        ),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace("- src/example.py", "- src/private.py"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.OUTBOX_PATH.as_posix()} changed file touches assigned forbidden scope: src/private.py" in issues


def test_validate_handoff_docs_rejects_handoff_control_file_as_changed_file(tmp_path: Path) -> None:
    """Ready outbox changed-file evidence cannot claim handoff control files."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "- src/example.py",
            "\n".join(
                [
                    "- `docs/handoff/deepseek_outbox.md`",
                    "- `DEEPSEEK_INBOX.md`",
                    "- `CODEX_REVIEW.md`",
                ]
            ),
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox changed files must not list "
        "handoff control file: docs/handoff/deepseek_outbox.md"
    ) in issues
    assert (
        "docs/handoff/deepseek_outbox.md ready outbox changed files must not list "
        "handoff control file: DEEPSEEK_INBOX.md"
    ) in issues
    assert (
        "docs/handoff/deepseek_outbox.md ready outbox changed files must not list "
        "handoff control file: CODEX_REVIEW.md"
    ) in issues


def test_validate_handoff_docs_rejects_workflow_control_file_as_changed_file(tmp_path: Path) -> None:
    """Ready outbox changed-file evidence cannot claim workflow control files."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write(tmp_path / "progress.md", "Updated progress.\n")
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace("- src/example.py", "- progress.md"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox changed files must not list "
        "workflow control file: progress.md"
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_changed_file_non_file_path(tmp_path: Path) -> None:
    """Ready outbox changed-file entries must point to files."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "- src/example.py",
            "- src\n- docs/missing.py",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox changed file path must point to a file: src"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox changed file path must point to a file: docs/missing.py"
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_missing_required_command(tmp_path: Path) -> None:
    """Ready outbox verification evidence must include the required commands."""

    _write_valid_handoff_docs(tmp_path, outbox_status=module.READY_FOR_REVIEW)
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        "\n".join(
            [
                "# DeepSeek Outbox",
                f"Status: {module.READY_FOR_REVIEW}",
                "Message ID: unassigned",
                "Task: unassigned",
                "## Summary",
                "- Waiting.",
                "## Changed Files",
                "- src/example.py",
                "## Verification Commands and Results",
                "- `python -m pytest tests/example.py -q` exited 0.",
                "- `git diff --check -- src/example.py` exited 0.",
                "## Acceptance Criteria",
                "- Waiting.",
                "## Scope Deviations",
                "- None.",
                "## Anti-Placeholder Scan",
                "- Scoped scan exited 0.",
                "## Unresolved Questions or Blockers",
                "- None.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: ruff" in issues


def test_validate_handoff_docs_rejects_unparseable_ready_outbox_verification_results(tmp_path: Path) -> None:
    """Ready outbox verification evidence must use parseable command result entries."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8")
        .replace("- `python -m pytest tests/example.py -q` exited 0.", "- python -m pytest tests/example.py -q exited 0.")
        .replace(
            "- `python -m ruff check src/example.py tests/example.py` exited 0.",
            "- python -m ruff check src/example.py tests/example.py exited 0.",
        )
        .replace(
            "- `git diff --check -- src/example.py tests/example.py` exited 0.",
            "- git diff --check -- src/example.py tests/example.py exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox verification must list parseable command result lines" in issues
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: pytest" in issues
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: ruff" in issues
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: git diff --check" in issues


def test_validate_handoff_docs_rejects_ready_outbox_non_bullet_verification_results(tmp_path: Path) -> None:
    """Ready outbox verification evidence must be listed as bullet result entries."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8")
        .replace(
            "- `python -m pytest tests/example.py -q` exited 0.",
            "Evidence: `python -m pytest tests/example.py -q` exited 0.",
        )
        .replace(
            "- `python -m ruff check src/example.py tests/example.py` exited 0.",
            "Evidence: `python -m ruff check src/example.py tests/example.py` exited 0.",
        )
        .replace(
            "- `git diff --check -- src/example.py tests/example.py` exited 0.",
            "Evidence: `git diff --check -- src/example.py tests/example.py` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox verification must list parseable command result lines" in issues
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: pytest" in issues
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: ruff" in issues
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: git diff --check" in issues


def test_validate_handoff_docs_rejects_ready_outbox_nonzero_verification_result(tmp_path: Path) -> None:
    """Ready outbox verification evidence must include clean command results."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m ruff check src/example.py tests/example.py` exited 0.",
            "`python -m ruff check src/example.py tests/example.py` exited 1.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox verification result must be clean for: ruff" in issues


def test_validate_handoff_docs_rejects_suffixed_verification_command_family(tmp_path: Path) -> None:
    """Ready outbox command-family evidence must use standalone command tokens."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m ruff check src/example.py tests/example.py` exited 0.",
            "`python -m ruffian check src/example.py tests/example.py` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: ruff" in issues


def test_validate_handoff_docs_rejects_chained_verification_command(tmp_path: Path) -> None:
    """Ready outbox command evidence cannot append a second shell command."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "`python -m pytest tests/example.py -q && echo ok` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready outbox verification command must not include shell control operators: "
        "python -m pytest tests/example.py -q && echo ok"
        in issue
        for issue in issues
    )
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: pytest" in issues


def test_validate_handoff_docs_rejects_wrapped_ready_outbox_verification_command(tmp_path: Path) -> None:
    """Ready outbox verification evidence must start with the verification tool itself."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "`powershell -Command python -m pytest tests/example.py -q` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox verification command must start with a direct pytest" in issue for issue in issues)
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: pytest" in issues


def test_validate_handoff_docs_rejects_diff_check_result_without_pathspec_delimiter(tmp_path: Path) -> None:
    """Ready outbox diff-check evidence must separate paths with --."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`git diff --check -- src/example.py tests/example.py` exited 0.",
            "`git diff --check src/example.py tests/example.py` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox git diff --check command must use -- before pathspecs: "
        "git diff --check src/example.py tests/example.py"
    ) in issues
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: git diff --check" in issues


def test_validate_handoff_docs_rejects_ready_outbox_unsafe_verification_flags(tmp_path: Path) -> None:
    """Ready outbox verification evidence cannot use flags that avoid real checks."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "`python -m pytest tests/example.py -q --deselect=tests/example.py::test_target` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: pytest" in issues


def test_validate_handoff_docs_rejects_ready_outbox_no_run_or_mutating_verification_flags(
    tmp_path: Path,
) -> None:
    """Ready outbox verification evidence cannot use listing-only or mutating flags."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    text = outbox_path.read_text(encoding="utf-8")
    text = text.replace(
        "`python -m pytest tests/example.py -q` exited 0.",
        "`python -m pytest tests/example.py -q --fixtures` exited 0.",
    )
    text = text.replace(
        "`python -m ruff check src/example.py tests/example.py` exited 0.",
        "`python -m ruff check src/example.py tests/example.py --fix-only` exited 0.",
    )
    outbox_path.write_text(text, encoding="utf-8")

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: pytest" in issues
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: ruff" in issues


def test_validate_handoff_docs_rejects_ready_outbox_rerun_only_or_early_stop_flags(
    tmp_path: Path,
) -> None:
    """Ready outbox evidence cannot use rerun-only or early-stop pytest flags."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "`python -m pytest tests/example.py -q --maxfail=1` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: pytest" in issues


def test_validate_handoff_docs_rejects_ready_outbox_rule_selection_or_config_override_flags(
    tmp_path: Path,
) -> None:
    """Ready outbox ruff evidence cannot override lint policy."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m ruff check src/example.py tests/example.py` exited 0.",
            "`python -m ruff check src/example.py tests/example.py --select=F401` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: ruff" in issues


def test_validate_handoff_docs_rejects_ready_outbox_pytest_config_or_import_override_flags(
    tmp_path: Path,
) -> None:
    """Ready outbox pytest evidence cannot override config or import scope."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "`python -m pytest tests/example.py -q --override-ini addopts=` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: pytest" in issues


def test_validate_handoff_docs_rejects_ready_outbox_pytest_node_selection_targets(
    tmp_path: Path,
) -> None:
    """Ready outbox pytest evidence cannot narrow execution to one test node."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "`python -m pytest tests/example.py::test_happy_path -q` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: pytest" in issues


def test_validate_handoff_docs_rejects_ready_outbox_mutating_verification_flags(tmp_path: Path) -> None:
    """Ready outbox verification evidence cannot use flags that mutate files."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m ruff check src/example.py tests/example.py` exited 0.",
            "`python -m ruff check src/example.py tests/example.py --fix` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: ruff" in issues


def test_validate_handoff_docs_rejects_ready_outbox_redirected_verification_command(tmp_path: Path) -> None:
    """Ready outbox verification evidence cannot redirect command output."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "`python -m pytest tests/example.py -q > result.txt` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox verification command must not include shell control operators" in issue for issue in issues)
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: pytest" in issues


def test_validate_handoff_docs_rejects_ready_outbox_shell_command_substitution(tmp_path: Path) -> None:
    """Ready outbox verification evidence cannot include shell command substitution."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "`python -m pytest tests/example.py -q $(python -c print(1))` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox verification command must not include shell control operators" in issue for issue in issues)
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: pytest" in issues


def test_validate_handoff_docs_rejects_ready_outbox_shell_variable_expansion(tmp_path: Path) -> None:
    """Ready outbox verification evidence cannot include shell variable expansion."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "`python -m pytest tests/example.py -q $env:PYTEST_ADDOPTS` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox verification command must not include shell control operators" in issue for issue in issues)
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: pytest" in issues


def test_validate_handoff_docs_rejects_ready_outbox_response_file_verification_argument(tmp_path: Path) -> None:
    """Ready outbox verification evidence cannot include hidden argument files."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "`python -m pytest tests/example.py -q @pytest.args` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready outbox verification command must not include response-file arguments" in issue for issue in issues)
    assert "docs/handoff/deepseek_outbox.md ready outbox verification must include: pytest" in issues


def test_validate_handoff_docs_rejects_negated_successful_verification_result(tmp_path: Path) -> None:
    """Ready outbox verification evidence cannot use negated success wording."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m ruff check src/example.py tests/example.py` exited 0.",
            "`python -m ruff check src/example.py tests/example.py` not successful.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox verification result must be clean for: ruff" in issues


def test_validate_handoff_docs_rejects_ready_outbox_missing_assigned_verification_result(tmp_path: Path) -> None:
    """Ready outbox verification must include the exact assigned command."""

    assigned_pytest = "python -m pytest tests/assigned.py -q"
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            verification_commands=(
                assigned_pytest,
                "python -m ruff check src/example.py tests/example.py",
                "git diff --check -- src/example.py tests/example.py",
            )
        ),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.OUTBOX_PATH.as_posix()} missing assigned verification command result: {assigned_pytest}" in issues


def test_validate_handoff_docs_rejects_success_marker_inside_assigned_command_text(tmp_path: Path) -> None:
    """A success marker inside the command literal is not result evidence."""

    assigned_pytest = "python -m pytest tests/example.py -q --label 'exited 0'"
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            verification_commands=(
                assigned_pytest,
                "python -m ruff check src/example.py tests/example.py",
                "git diff --check -- src/example.py tests/example.py",
            )
        ),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "- `python -m pytest tests/example.py -q` exited 0.",
            f"- `{assigned_pytest}`",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: {assigned_pytest}" in issues


def test_validate_handoff_docs_rejects_failing_assigned_verification_result(tmp_path: Path) -> None:
    """Ready outbox cannot hide a failed assigned command behind another clean command."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "\n".join(
                [
                    "`python -m pytest tests/example.py -q` not successful.",
                    "`python -m pytest tests/other.py -q` exited 0.",
                ]
            ),
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in issues


@pytest.mark.parametrize("failure_marker", ["timed out", "timeout", "cancelled", "interrupted", "error"])
def test_validate_handoff_docs_rejects_interrupted_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Ready outbox cannot present interrupted command evidence as clean."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in issues


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
def test_validate_handoff_docs_rejects_empty_suite_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Ready outbox cannot present an empty test suite as clean evidence."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in issues


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
def test_validate_handoff_docs_rejects_soft_failure_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Ready outbox cannot present soft pytest failures as clean evidence."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in issues


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
def test_validate_handoff_docs_rejects_partial_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Ready outbox cannot present partial verification as complete evidence."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in issues


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
def test_validate_handoff_docs_rejects_stale_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Ready outbox cannot present stale verification as current evidence."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in issues


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
def test_validate_handoff_docs_rejects_speculative_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Ready outbox cannot present speculative verification as clean evidence."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in issues


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
def test_validate_handoff_docs_rejects_substitute_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Ready outbox cannot present substitute verification as clean evidence."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in issues


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
def test_validate_handoff_docs_rejects_environment_mismatch_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Ready outbox cannot present environment-mismatched verification as clean evidence."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in issues


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
def test_validate_handoff_docs_rejects_tooling_failure_assigned_verification_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Ready outbox cannot present local tooling failures as clean evidence."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            f"`python -m pytest tests/example.py -q` {failure_marker}, exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command has failing result: "
        "python -m pytest tests/example.py -q"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: "
        "python -m pytest tests/example.py -q"
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_diff_check_missing_changed_file(tmp_path: Path) -> None:
    """Ready outbox diff-check evidence must cover changed files."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            verification_commands=(
                "python -m pytest tests/example.py -q",
                "python -m ruff check src/example.py tests/example.py",
                "git diff --check -- tests/example.py",
            )
        ),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`git diff --check -- src/example.py tests/example.py` exited 0.",
            "`git diff --check -- tests/example.py` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox git diff --check must mention changed file: "
        "src/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_diff_check_suffixed_changed_file_path(
    tmp_path: Path,
) -> None:
    """Diff-check evidence must mention changed files as path tokens."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            verification_commands=(
                "python -m pytest tests/example.py -q",
                "python -m ruff check src/example.py tests/example.py",
                "git diff --check -- src/example.py.bak tests/example.py",
            )
        ),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`git diff --check -- src/example.py tests/example.py` exited 0.",
            "`git diff --check -- src/example.py.bak tests/example.py` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox git diff --check must mention changed file: "
        "src/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_failing_diff_check_covering_changed_file(tmp_path: Path) -> None:
    """Diff-check coverage for a changed file must have a clean result."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            verification_commands=(
                "python -m pytest tests/example.py -q",
                "python -m ruff check src/example.py tests/example.py",
                "git diff --check -- tests/example.py",
            )
        ),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`git diff --check -- src/example.py tests/example.py` exited 0.",
            "\n".join(
                [
                    "`git diff --check -- src/example.py tests/example.py` not successful.",
                    "`git diff --check -- tests/example.py` exited 0.",
                ]
            ),
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox git diff --check result is failing for "
        "changed file: src/example.py"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox git diff --check result must be clean for "
        "changed file: src/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_ruff_missing_changed_python_file(tmp_path: Path) -> None:
    """Ready outbox ruff evidence must cover changed Python files."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            verification_commands=(
                "python -m pytest tests/example.py -q",
                "python -m ruff check tests/example.py",
                "git diff --check -- src/example.py tests/example.py",
            )
        ),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m ruff check src/example.py tests/example.py` exited 0.",
            "`python -m ruff check tests/example.py` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox ruff check must mention changed Python file: "
        "src/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_failing_ruff_covering_changed_python_file(tmp_path: Path) -> None:
    """Ruff coverage for a changed Python file must have a clean result."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            verification_commands=(
                "python -m pytest tests/example.py -q",
                "python -m ruff check tests/example.py",
                "git diff --check -- src/example.py tests/example.py",
            )
        ),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m ruff check src/example.py tests/example.py` exited 0.",
            "\n".join(
                [
                    "`python -m ruff check src/example.py tests/example.py` not successful.",
                    "`python -m ruff check tests/example.py` exited 0.",
                ]
            ),
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox ruff check result is failing for "
        "changed Python file: src/example.py"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox ruff check result must be clean for "
        "changed Python file: src/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_ruff_suffixed_changed_python_file_path(
    tmp_path: Path,
) -> None:
    """Ruff evidence must mention changed Python files as path tokens."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            verification_commands=(
                "python -m pytest tests/example.py -q",
                "python -m ruff check src/example.py.bak tests/example.py",
                "git diff --check -- src/example.py tests/example.py",
            )
        ),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "`python -m ruff check src/example.py tests/example.py` exited 0.",
            "`python -m ruff check src/example.py.bak tests/example.py` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox ruff check must mention changed Python file: "
        "src/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_pytest_missing_changed_test_file(tmp_path: Path) -> None:
    """Ready outbox pytest evidence must cover changed test files."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            verification_commands=(
                "python -m pytest tests/other.py -q",
                "python -m ruff check src/example.py tests/example.py",
                "git diff --check -- src/example.py tests/example.py",
            )
        ),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=[f"- `{_scan_command(['src/example.py', 'tests/example.py'])}` returned no matches."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8")
        .replace(
            "## Changed Files\n- src/example.py",
            "## Changed Files\n- src/example.py\n- tests/example.py",
        )
        .replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "`python -m pytest tests/other.py -q` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox pytest must mention changed test file: "
        "tests/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_failing_pytest_covering_changed_test_file(tmp_path: Path) -> None:
    """Pytest coverage for a changed test file must have a clean result."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            verification_commands=(
                "python -m pytest tests/other.py -q",
                "python -m ruff check src/example.py tests/example.py",
                "git diff --check -- src/example.py tests/example.py",
            )
        ),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=[f"- `{_scan_command(['src/example.py', 'tests/example.py'])}` returned no matches."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8")
        .replace(
            "## Changed Files\n- src/example.py",
            "## Changed Files\n- src/example.py\n- tests/example.py",
        )
        .replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "\n".join(
                [
                    "`python -m pytest tests/example.py -q` not successful.",
                    "`python -m pytest tests/other.py -q` exited 0.",
                ]
            ),
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox pytest result is failing for "
        "changed test file: tests/example.py"
    ) in issues
    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox pytest result must be clean for "
        "changed test file: tests/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_pytest_suffixed_changed_test_file_path(
    tmp_path: Path,
) -> None:
    """Pytest evidence must mention changed test files as path tokens."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            verification_commands=(
                "python -m pytest tests/example.py.bak -q",
                "python -m ruff check src/example.py tests/example.py",
                "git diff --check -- src/example.py tests/example.py",
            )
        ),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=[f"- `{_scan_command(['src/example.py', 'tests/example.py'])}` returned no matches."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8")
        .replace(
            "## Changed Files\n- src/example.py",
            "## Changed Files\n- src/example.py\n- tests/example.py",
        )
        .replace(
            "`python -m pytest tests/example.py -q` exited 0.",
            "`python -m pytest tests/example.py.bak -q` exited 0.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox pytest must mention changed test file: "
        "tests/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_without_checked_acceptance_evidence(tmp_path: Path) -> None:
    """Ready outbox acceptance evidence must list checked criteria."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(tmp_path, ["- Waiting."])

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox acceptance criteria must include checked evidence items"
        in issues
    )


def test_validate_handoff_docs_rejects_ready_outbox_generic_acceptance_summary(tmp_path: Path) -> None:
    """Checked acceptance evidence cannot be only a generic summary."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(tmp_path, ["- [x] All criteria verified."])

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox acceptance criteria must not use a generic summary" in issues


def test_validate_handoff_docs_rejects_ready_outbox_missing_assigned_acceptance_evidence(tmp_path: Path) -> None:
    """Ready outbox acceptance evidence must cover each assigned inbox criterion."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        [
            "- [x] Happy path verified.",
            "- [x] Error path verified.",
        ],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} missing checked acceptance evidence for assigned criterion: Scope verified."
        in issues
    )


def test_validate_handoff_docs_rejects_negative_checked_acceptance_evidence(tmp_path: Path) -> None:
    """Ready outbox checked acceptance evidence cannot be negative."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        [
            "- [x] Happy path verified.",
            "- [x] Error path verified. not verified in this change.",
            "- [x] Scope verified.",
        ],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox checked acceptance evidence is negative: "
        "Error path verified. not verified in this change."
    ) in issues


def test_validate_handoff_docs_rejects_skipped_checked_acceptance_evidence(tmp_path: Path) -> None:
    """Ready outbox checked acceptance evidence cannot claim skipped coverage."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        [
            "- [x] Happy path verified.",
            "- [x] Error path verified. skipped in this change.",
            "- [x] Scope verified.",
        ],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox checked acceptance evidence is negative: "
        "Error path verified. skipped in this change."
    ) in issues


@pytest.mark.parametrize("marker", ["unverified", "untested"])
def test_validate_handoff_docs_rejects_unverified_checked_acceptance_evidence(
    tmp_path: Path,
    marker: str,
) -> None:
    """Ready outbox checked acceptance evidence cannot claim absent coverage."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        [
            "- [x] Happy path verified.",
            f"- [x] Error path verified. {marker} in this change.",
            "- [x] Scope verified.",
        ],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox checked acceptance evidence is negative: "
        f"Error path verified. {marker} in this change."
    ) in issues


@pytest.mark.parametrize("marker", ["pending", "deferred", "not applicable", "n/a"])
def test_validate_handoff_docs_rejects_deferred_checked_acceptance_evidence(
    tmp_path: Path,
    marker: str,
) -> None:
    """Ready outbox checked acceptance evidence cannot defer coverage."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        [
            "- [x] Happy path verified.",
            f"- [x] Error path verified. {marker} in this change.",
            "- [x] Scope verified.",
        ],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox checked acceptance evidence is negative: "
        f"Error path verified. {marker} in this change."
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_scope_deviation(tmp_path: Path) -> None:
    """Ready outbox scope deviations must be clean before review."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "## Scope Deviations\n- None.",
            "## Scope Deviations\n- Added docs/extra.md without assignment.",
        ),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox lists scope deviation: "
        "Added docs/extra.md without assignment."
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_with_unresolved_blocker(tmp_path: Path) -> None:
    """Ready outboxes cannot carry unresolved blockers."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        unresolved_lines=["- Need product decision before merge."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox lists unresolved blocker: "
        "Need product decision before merge."
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_without_blocker_statement(tmp_path: Path) -> None:
    """Ready outboxes must explicitly state whether blockers remain."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        unresolved_lines=[],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox must explicitly state unresolved questions or blockers"
        in issues
    )


def test_validate_handoff_docs_rejects_ready_outbox_without_scan_command_evidence(tmp_path: Path) -> None:
    """Ready outbox scan evidence must include the executed scanner."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=["- Clean result recorded."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must include command evidence" in issues


def test_validate_handoff_docs_rejects_ready_outbox_without_clean_scan_result(tmp_path: Path) -> None:
    """Ready outbox scan evidence must include the clean scan result."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=["- `rg -n BLOCKED_PATTERN src/example.py` was executed."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must include clean result evidence" in issues


def test_validate_handoff_docs_rejects_scan_result_marker_inside_scan_command_text(tmp_path: Path) -> None:
    """A clean marker inside the scan command literal is not scan result evidence."""

    scan_command = f'{_scan_command(["src/example.py"])} --label "returned no matches"'
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=[f"- `{scan_command}`."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must include clean result evidence" in issues


def test_validate_handoff_docs_rejects_scan_result_marker_detached_from_scan_command_line(
    tmp_path: Path,
) -> None:
    """A clean scan result must be attached to the parseable scanner command line."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=[
            f"- `{_scan_command(['src/example.py'])}`.",
            "- returned no matches.",
        ],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan clean result "
        "must appear on a parseable scan command line"
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_scan_command_redirection(tmp_path: Path) -> None:
    """Ready outbox scan command must be an exact standalone command."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=["- `rg -n BLOCKED_PATTERN src/example.py > scan.txt` returned no matches."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready outbox Anti-Placeholder scan command must not include shell control operators" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_outbox_scan_variable_expansion(tmp_path: Path) -> None:
    """Ready outbox scan evidence cannot include shell variable expansion."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    command = f"{_scan_command(['src/example.py'])} $env:SCAN_PATHS"
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=[f"- `{command}` returned no matches."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready outbox Anti-Placeholder scan command must not include shell control operators" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_outbox_scan_response_file_argument(tmp_path: Path) -> None:
    """Ready outbox scan evidence cannot include hidden argument files."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    command = f"{_scan_command(['src/example.py'])} @scan.args"
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=[f"- `{command}` returned no matches."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready outbox Anti-Placeholder scan command must not include response-file arguments" in issue
        for issue in issues
    )
    assert any(
        "ready outbox Anti-Placeholder scan must mention changed file: src/example.py" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_outbox_non_rg_scan_command(tmp_path: Path) -> None:
    """Ready outbox scan evidence must name an actual ripgrep scan command."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=["- `Write-Output rg -n BLOCKED_PATTERN src/example.py` returned no matches."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready outbox Anti-Placeholder scan command must start with rg or rg.exe" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_outbox_scan_missing_configured_patterns(tmp_path: Path) -> None:
    """Ready outbox scan evidence must use the configured scanner expression."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    partial_command = (
        f'rg -n --pcre2 -e "{module.ANTI_PLACEHOLDER_SCANNER_PATTERNS[0]}" '
        "-- src/example.py"
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=[f"- `{partial_command}` returned no matches."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready outbox Anti-Placeholder scan command must include all configured scanner patterns" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_outbox_scan_missing_path_delimiter(tmp_path: Path) -> None:
    """Ready outbox scan evidence must separate scanner expressions from paths."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    command = _scan_command(["src/example.py"]).replace(" -- src/example.py", " src/example.py")
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=[f"- `{command}` returned no matches."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready outbox Anti-Placeholder scan command must use -- before the path list" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_outbox_scan_command_angle_marker(tmp_path: Path) -> None:
    """Ready outbox scan command must not leave unresolved markers."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=["- `rg -n <pattern> src/example.py` returned no matches."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready outbox Anti-Placeholder scan command must not include unresolved angle-bracket markers" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_scan_result_with_exit_code_only(tmp_path: Path) -> None:
    """Ready outbox scan evidence must say the scanner found no matches."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=["- `rg -n BLOCKED_PATTERN src/example.py` exited 0."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must include clean result evidence" in issues


def test_validate_handoff_docs_rejects_skipped_scan_result(tmp_path: Path) -> None:
    """Ready outbox scan evidence cannot be skipped and still claim no matches."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=["- `rg -n BLOCKED_PATTERN src/example.py` skipped, returned no matches."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must not use failing evidence" in issues


def test_validate_handoff_docs_rejects_not_scanned_result(tmp_path: Path) -> None:
    """Ready outbox scan evidence cannot claim clean results when not scanned."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=["- `rg -n BLOCKED_PATTERN src/example.py` not scanned, returned no matches."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must not use failing evidence" in issues


@pytest.mark.parametrize("failure_marker", ["timed out", "timeout", "cancelled", "interrupted", "error"])
def test_validate_handoff_docs_rejects_interrupted_scan_result(
    tmp_path: Path,
    failure_marker: str,
) -> None:
    """Ready outbox scan evidence cannot claim clean results after interruption."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=[f"- `rg -n BLOCKED_PATTERN src/example.py` {failure_marker}, returned no matches."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must not use failing evidence" in issues


@pytest.mark.parametrize("stand_in", ["None", "not applicable", "n/a", "no scan"])
def test_validate_handoff_docs_rejects_ready_outbox_empty_scan_evidence(
    tmp_path: Path,
    stand_in: str,
) -> None:
    """Ready outbox scan evidence cannot be a no-evidence stand-in."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=[f"- {stand_in}."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "docs/handoff/deepseek_outbox.md ready outbox Anti-Placeholder scan must not use empty evidence" in issues


def test_validate_handoff_docs_rejects_ready_outbox_scan_missing_changed_file(tmp_path: Path) -> None:
    """Ready outbox scan evidence must cover changed files."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=["- `rg -n BLOCKED_PATTERN tests/example.py` returned no matches."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox Anti-Placeholder scan must mention changed file: "
        "src/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_scan_suffixed_changed_file_path(tmp_path: Path) -> None:
    """Ready outbox scan evidence must mention changed files as path tokens."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=["- `rg -n BLOCKED_PATTERN src/example.py.bak tests/example.py` returned no matches."],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox Anti-Placeholder scan must mention changed file: "
        "src/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_ready_outbox_scan_path_only_in_note(tmp_path: Path) -> None:
    """Ready outbox scan coverage must come from the scanner command."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=[
            "- `rg -n BLOCKED_PATTERN tests/example.py` returned no matches; "
            "review note mentions src/example.py.",
        ],
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.OUTBOX_PATH.as_posix()} ready outbox Anti-Placeholder scan must mention changed file: "
        "src/example.py"
    ) in issues


def test_validate_handoff_docs_accepts_ready_outbox_scan_covering_multiple_changed_files(tmp_path: Path) -> None:
    """Ready outbox scan evidence can cover multiple changed files in one command."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.READY_FOR_REVIEW,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )
    _write_ready_outbox_with_acceptance(
        tmp_path,
        ["- [x] Happy path verified.", "- [x] Error path verified.", "- [x] Scope verified."],
        scan_lines=[f"- `{_scan_command(['src/example.py', 'tests/example.py'])}` returned no matches."],
    )
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_path.write_text(
        outbox_path.read_text(encoding="utf-8").replace(
            "## Changed Files\n- src/example.py",
            "## Changed Files\n- src/example.py\n- tests/example.py",
        ),
        encoding="utf-8",
    )

    assert module.validate_handoff_docs(tmp_path) == []


def test_validate_handoff_docs_ignores_body_ready_markers(tmp_path: Path) -> None:
    """Only top-level Status metadata controls handoff readiness."""

    _write_valid_handoff_docs(tmp_path)
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_text = outbox_path.read_text(encoding="utf-8")
    outbox_path.write_text(
        "\n".join(
            [
                outbox_text.rstrip(),
                "## Extra Notes",
                module.READY_FOR_REVIEW,
                f"Status: {module.READY_FOR_REVIEW}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert module.validate_handoff_docs(tmp_path) == []


def test_validate_handoff_docs_rejects_duplicate_top_level_metadata(tmp_path: Path) -> None:
    """Top-level metadata fields must be unique and keep the first value."""

    _write_valid_handoff_docs(tmp_path)
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_text = outbox_path.read_text(encoding="utf-8")
    outbox_path.write_text(
        outbox_text.replace("## Summary", f"Status: {module.READY_FOR_REVIEW}\n## Summary"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.OUTBOX_PATH.as_posix()} has duplicate metadata field: Status" in issues
    assert not any("ready section cannot contain" in issue for issue in issues)


def test_validate_handoff_docs_rejects_duplicate_inbox_gate_metadata(tmp_path: Path) -> None:
    """Duplicate inbox gate metadata is rejected before task handoff."""

    inbox = _waiting_deepseek_inbox().replace("## Operating Role", "CODEX_GATE: PASS\n## Operating Role")
    _write_valid_handoff_docs(tmp_path, inbox_text=inbox)

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.INBOX_PATH.as_posix()} has duplicate metadata field: CODEX_GATE" in issues


def test_validate_handoff_docs_rejects_duplicate_required_section_heading(tmp_path: Path) -> None:
    """Required handoff sections must not be duplicated."""

    _write_valid_handoff_docs(tmp_path)
    outbox_path = tmp_path / module.OUTBOX_PATH
    outbox_text = outbox_path.read_text(encoding="utf-8")
    outbox_path.write_text(
        outbox_text.replace("## Verification Commands and Results", "## Changed Files\n- extra.py\n## Verification Commands and Results"),
        encoding="utf-8",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.OUTBOX_PATH.as_posix()} has duplicate section heading: ## Changed Files" in issues


def test_validate_handoff_docs_accepts_bounded_ready_inbox(tmp_path: Path) -> None:
    """A ready DeepSeek task with concrete scope is valid."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    assert module.validate_handoff_docs(tmp_path) == []


def test_validate_handoff_docs_rejects_ready_inbox_with_too_few_acceptance_criteria(tmp_path: Path) -> None:
    """Ready inbox acceptance criteria must keep enough concrete checks."""

    inbox = _ready_deepseek_inbox().replace(
        "\n".join(
            [
                "## Acceptance Criteria",
                "- [ ] Happy path verified.",
                "- [ ] Error path verified.",
                "- [ ] Scope verified.",
                "## Verification Commands",
            ]
        ),
        "\n".join(
            [
                "## Acceptance Criteria",
                "- [ ] Happy path verified.",
                "## Verification Commands",
            ]
        ),
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.INBOX_PATH.as_posix()} ready inbox must include at least 3 unchecked acceptance items" in issues


def test_validate_handoff_docs_rejects_duplicate_ready_inbox_acceptance_criteria(tmp_path: Path) -> None:
    """Ready inbox acceptance criteria must be distinct."""

    inbox = _ready_deepseek_inbox().replace("- [ ] Error path verified.", "- [ ] Happy path verified.")
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.INBOX_PATH.as_posix()} ready inbox acceptance criterion is duplicated: Happy path verified."
        in issues
    )


def test_validate_handoff_docs_rejects_ready_inbox_angle_bracket_markers(tmp_path: Path) -> None:
    """Ready inbox text must not keep template angle-bracket markers."""

    inbox = _ready_deepseek_inbox().replace("- [ ] Scope verified.", "- [ ] <Scope verified.>")
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.INBOX_PATH.as_posix()} ready inbox has unresolved angle-bracket marker in section: "
        "## Acceptance Criteria"
    ) in issues


def test_validate_handoff_docs_rejects_ready_inbox_with_too_few_requirements(tmp_path: Path) -> None:
    """Ready inbox requirements must contain enough numbered implementation constraints."""

    inbox = _ready_deepseek_inbox().replace(
        "\n".join(
            [
                "## Requirements",
                "1. Preserve existing interfaces.",
                "2. Add focused tests.",
                "3. Keep errors visible.",
            ]
        ),
        "\n".join(
            [
                "## Requirements",
                "1. Preserve existing interfaces.",
            ]
        ),
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.INBOX_PATH.as_posix()} ready inbox must include at least 3 numbered requirements" in issues


def test_validate_handoff_docs_rejects_duplicate_ready_inbox_requirements(tmp_path: Path) -> None:
    """Ready inbox requirements must be distinct."""

    inbox = _ready_deepseek_inbox().replace(
        "2. Add focused tests.",
        "2. Preserve existing interfaces.",
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.INBOX_PATH.as_posix()} ready inbox requirement is duplicated: Preserve existing interfaces."
        in issues
    )


def test_validate_handoff_docs_rejects_ready_inbox_with_too_few_stop_conditions(tmp_path: Path) -> None:
    """Ready inbox stop conditions must keep enough boundary checks."""

    inbox = _ready_deepseek_inbox().replace(
        "\n".join(
            [
                "## Stop Conditions",
                "- Stop when the task needs files outside allowed scope.",
                "- Stop when interface or behavior is missing.",
                "- Stop when tests require weaker assertions.",
                "## Required Outbox",
            ]
        ),
        "\n".join(
            [
                "## Stop Conditions",
                "- Stop when the task needs files outside allowed scope.",
                "## Required Outbox",
            ]
        ),
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.INBOX_PATH.as_posix()} ready inbox must include at least 3 stop conditions" in issues


def test_validate_handoff_docs_rejects_duplicate_ready_inbox_stop_conditions(tmp_path: Path) -> None:
    """Ready inbox stop conditions must be distinct."""

    inbox = _ready_deepseek_inbox().replace(
        "## Required Outbox",
        "\n".join(
            [
                "- Stop when the task needs files outside allowed scope.",
                "- Stop when the task needs files outside allowed scope.",
                "## Required Outbox",
            ]
        ),
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.INBOX_PATH.as_posix()} ready inbox stop condition is duplicated: "
        "Stop when the task needs files outside allowed scope."
    ) in issues


def test_validate_handoff_docs_accepts_ready_inbox_with_bullet_verification_commands(tmp_path: Path) -> None:
    """Ready inbox verification commands may be backticked bullet items."""

    inbox = _ready_deepseek_inbox().replace(
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
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    assert module.validate_handoff_docs(tmp_path) == []


def test_validate_handoff_docs_rejects_ready_inbox_diff_check_missing_allowed_file(tmp_path: Path) -> None:
    """Ready inbox diff-check commands must cover the concrete allowed scope."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.INBOX_PATH.as_posix()} ready inbox git diff --check must mention allowed path: "
        "src/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_ready_inbox_diff_check_without_pathspec_delimiter(tmp_path: Path) -> None:
    """Ready inbox diff-check commands must separate pathspecs with --."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.INBOX_PATH.as_posix()} ready inbox git diff --check command must use -- before pathspecs: "
        "git diff --check src/example.py tests/example.py"
    ) in issues
    assert any("ready inbox verification must include: git diff --check" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_diff_check_missing_allowed_directory(
    tmp_path: Path,
) -> None:
    """Ready inbox diff-check commands must cover directory scopes."""

    inbox = _ready_deepseek_inbox(
        allowed_files=["src/example_pkg"],
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example_pkg",
            "git diff --check -- tests/example.py",
        ),
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.INBOX_PATH.as_posix()} ready inbox git diff --check must mention allowed path: "
        "src/example_pkg"
    ) in issues


def test_validate_handoff_docs_rejects_ready_inbox_ruff_missing_allowed_python_file(tmp_path: Path) -> None:
    """Ready inbox ruff commands must cover every allowed Python file."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.INBOX_PATH.as_posix()} ready inbox ruff check must mention allowed Python file: "
        "src/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_ready_inbox_pytest_missing_allowed_test_file(tmp_path: Path) -> None:
    """Ready inbox pytest commands must cover every allowed test Python file."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/other.py -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.INBOX_PATH.as_posix()} ready inbox pytest must mention allowed test file: "
        "tests/example.py"
    ) in issues


def test_validate_handoff_docs_rejects_ready_inbox_without_required_outbox_evidence_categories(tmp_path: Path) -> None:
    """A hand-written ready inbox must require full DeepSeek evidence."""

    complete_required_outbox = "\n".join(
        [
            "## Required Outbox",
            f"- {module.READY_FOR_REVIEW}",
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
            f"- {module.READY_FOR_REVIEW}",
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
    incomplete_required_outbox = "\n".join(
        [
            "## Required Outbox",
            f"- {module.READY_FOR_REVIEW}",
            "## Required Outbox Evidence",
            f"- {module.READY_FOR_REVIEW}",
        ]
    )
    inbox = _ready_deepseek_inbox().replace(complete_required_outbox, incomplete_required_outbox)
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox required outbox evidence must mention: changed files" in issue for issue in issues)
    assert any("ready inbox required outbox evidence must mention: concrete summary" in issue for issue in issues)
    assert any("ready inbox required outbox evidence must mention: verification commands" in issue for issue in issues)
    assert any(
        "ready inbox required outbox evidence must mention: clean result markers inside the backticked command text"
        in issue
        for issue in issues
    )
    assert any("ready inbox required outbox evidence must mention: checked acceptance" in issue for issue in issues)
    assert any("ready inbox required outbox evidence must mention: Anti-Placeholder scan" in issue for issue in issues)
    assert any(
        "ready inbox required outbox evidence must mention: "
        "Anti-Placeholder clean result evidence must appear on the same line"
        in issue
        for issue in issues
    )
    assert any("ready inbox required outbox evidence must mention: scope deviations" in issue for issue in issues)
    assert any(
        "ready inbox required outbox evidence must mention: unresolved questions or blockers" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_inbox_without_required_outbox_categories(
    tmp_path: Path,
) -> None:
    """The main required outbox section must carry the same evidence categories."""

    complete_required_outbox = "\n".join(
        [
            "## Required Outbox",
            f"- {module.READY_FOR_REVIEW}",
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
        ]
    )
    incomplete_required_outbox = "\n".join(
        [
            "## Required Outbox",
            f"- {module.READY_FOR_REVIEW}",
            "## Required Outbox Evidence",
        ]
    )
    inbox = _ready_deepseek_inbox().replace(complete_required_outbox, incomplete_required_outbox)
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox required outbox must mention: changed files" in issue for issue in issues)
    assert any("ready inbox required outbox must mention: concrete summary" in issue for issue in issues)
    assert any("ready inbox required outbox must mention: verification commands" in issue for issue in issues)
    assert any("ready inbox required outbox must mention: Anti-Placeholder scan" in issue for issue in issues)
    assert not any("ready inbox required outbox evidence must mention: changed files" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_without_required_outbox_evidence_section(tmp_path: Path) -> None:
    """A ready inbox must keep the dedicated outbox evidence section."""

    required_outbox_evidence_section = "\n".join(
        [
            "## Required Outbox Evidence",
            f"- {module.READY_FOR_REVIEW}",
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
    inbox = _ready_deepseek_inbox().replace(required_outbox_evidence_section, "")
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.INBOX_PATH.as_posix()} ready inbox has empty section: ## Required Outbox Evidence" in issues


def test_validate_handoff_docs_rejects_ready_inbox_with_incomplete_required_outbox_evidence_section(
    tmp_path: Path,
) -> None:
    """The dedicated outbox evidence section must carry the evidence categories."""

    complete_required_outbox_evidence = "\n".join(
        [
            "## Required Outbox Evidence",
            f"- {module.READY_FOR_REVIEW}",
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
    incomplete_required_outbox_evidence = "\n".join(
        [
            "## Required Outbox Evidence",
            f"- {module.READY_FOR_REVIEW}",
        ]
    )
    inbox = _ready_deepseek_inbox().replace(complete_required_outbox_evidence, incomplete_required_outbox_evidence)
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox required outbox evidence must include at least 11 bullet items" in issue for issue in issues)
    assert any("ready inbox required outbox evidence must mention: concrete summary" in issue for issue in issues)
    assert any("ready inbox required outbox evidence must mention: changed files" in issue for issue in issues)
    assert any(
        "ready inbox required outbox evidence must mention: changed-file evidence must not list workflow control files"
        in issue
        for issue in issues
    )
    assert any(
        "ready inbox required outbox evidence must mention: clean result markers inside the backticked command text"
        in issue
        for issue in issues
    )
    assert any(
        "ready inbox required outbox evidence must mention: "
        "Anti-Placeholder clean result evidence must appear on the same line"
        in issue
        for issue in issues
    )
    assert any("ready inbox required outbox evidence must mention: unresolved questions or blockers" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_without_same_line_scan_result_requirement(
    tmp_path: Path,
) -> None:
    """Ready inbox tasks must require scan results on the scanner command line."""

    inbox = _ready_deepseek_inbox().replace(
        "\n- Anti-Placeholder clean result evidence must appear on the same line as the parseable scan command",
        "",
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready inbox required outbox evidence must mention: "
        "Anti-Placeholder clean result evidence must appear on the same line"
        in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_duplicate_ready_inbox_required_outbox_evidence(tmp_path: Path) -> None:
    """Required outbox evidence bullets must be distinct."""

    inbox = _ready_deepseek_inbox().replace("- scope deviations", "- changed files")
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.INBOX_PATH.as_posix()} ready inbox required outbox evidence is duplicated: changed files"
        in issues
    )


def test_validate_handoff_docs_rejects_ready_inbox_with_unparseable_verification_commands(tmp_path: Path) -> None:
    """Ready inbox verification commands must be exact command entries."""

    inbox = _ready_deepseek_inbox().replace(
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
                "- Run pytest, ruff, and git diff --check before review.",
            ]
        ),
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification must list parseable commands" in issue for issue in issues)
    assert any("ready inbox verification must include: pytest" in issue for issue in issues)
    assert any("ready inbox verification must include: ruff" in issue for issue in issues)
    assert any("ready inbox verification must include: git diff --check" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_verification_command_substrings(tmp_path: Path) -> None:
    """Ready inbox verification command families must match command tokens."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytester tests/example.py -q",
            "python -m ruffian check src/example.py tests/example.py",
            "git diff --checked -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification must include: pytest" in issue for issue in issues)
    assert any("ready inbox verification must include: ruff" in issue for issue in issues)
    assert any("ready inbox verification must include: git diff --check" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_chained_verification_command(tmp_path: Path) -> None:
    """Ready inbox verification commands must be standalone commands."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py && echo ok",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must not include shell control operators" in issue for issue in issues)
    assert any("ready inbox verification must include: ruff" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_wrapped_verification_commands(tmp_path: Path) -> None:
    """Ready inbox verification commands must start with the verification tool itself."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "powershell -Command python -m pytest tests/example.py -q",
            "cmd /c python -m ruff check src/example.py tests/example.py",
            "bash -lc git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must start with a direct pytest" in issue for issue in issues)
    assert any("ready inbox verification must include: pytest" in issue for issue in issues)
    assert any("ready inbox verification must include: ruff" in issue for issue in issues)
    assert any("ready inbox verification must include: git diff --check" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_commented_verification_command(tmp_path: Path) -> None:
    """Ready inbox verification commands must not hide scope in command comments."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check tests/example.py # src/example.py",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must not include shell control operators" in issue for issue in issues)
    assert any("ready inbox verification must include: ruff" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_unsafe_verification_flags(tmp_path: Path) -> None:
    """Ready inbox verification commands cannot use flags that avoid real checks."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q -khappy_path",
            "python -m ruff check src/example.py tests/example.py --exclude src/example.py",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert any("ready inbox verification must include: pytest" in issue for issue in issues)
    assert any("ready inbox verification must include: ruff" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_no_run_or_mutating_verification_flags(tmp_path: Path) -> None:
    """Ready inbox verification commands cannot use listing-only or mutating flags."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q --co",
            "python -m pytest tests/example.py --setup-only",
            "python -m ruff check src/example.py tests/example.py --add-noqa",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert any("ready inbox verification must include: pytest" in issue for issue in issues)
    assert any("ready inbox verification must include: ruff" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_rerun_only_or_early_stop_flags(tmp_path: Path) -> None:
    """Ready inbox verification commands cannot use rerun-only or early-stop flags."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q --last-failed",
            "python -m pytest tests/example.py --maxfail 1",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert any("ready inbox verification must include: pytest" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_rule_selection_or_config_override_flags(
    tmp_path: Path,
) -> None:
    """Ready inbox ruff commands cannot override lint policy."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py --config ruff.toml",
            "python -m ruff check src/example.py tests/example.py --lint.select=F401",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert any("ready inbox verification must include: ruff" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_pytest_config_or_import_override_flags(
    tmp_path: Path,
) -> None:
    """Ready inbox pytest commands cannot override config or import scope."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q --rootdir tests",
            "python -m pytest tests/example.py --pyargs",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert any("ready inbox verification must include: pytest" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_pytest_node_selection_targets(
    tmp_path: Path,
) -> None:
    """Ready inbox pytest commands cannot narrow execution to one test node."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py::test_happy_path -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert any("ready inbox verification must include: pytest" in issue for issue in issues)


def test_unsafe_verification_flag_parser_allows_python_module_runner() -> None:
    """The parser must not confuse python -m with pytest marker filtering."""

    assert not module._has_unsafe_verification_flag("python -m pytest tests/example.py -q")
    assert not module._has_unsafe_verification_flag("python -m ruff check src/example.py")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py::test_happy_path -q")
    assert module._has_unsafe_verification_flag("pytest tests/example.py::TestCase::test_happy_path")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py -q -m slow")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py -q -k=happy")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py -q -kslow")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py -q -mslow")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py -q --co")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --fixtures")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --setup-only")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --setup-plan")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --lf")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --last-failed")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --ff")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --failed-first")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py -x")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --exitfirst")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --maxfail")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --maxfail=1")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --stepwise")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --stepwise-skip")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --sw")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --sw-skip")
    assert module._has_unsafe_verification_flag("python -m ruff check src/example.py --fix-only")
    assert module._has_unsafe_verification_flag("python -m ruff check src/example.py --add-noqa")
    assert module._has_unsafe_verification_flag("python -m ruff check src/example.py --show-files")
    assert module._has_unsafe_verification_flag("python -m ruff check src/example.py --show-settings")
    assert module._has_unsafe_verification_flag("python -m ruff check src/example.py --select F401")
    assert module._has_unsafe_verification_flag("python -m ruff check src/example.py --select=F401")
    assert module._has_unsafe_verification_flag("python -m ruff check src/example.py --extend-select F401")
    assert module._has_unsafe_verification_flag("python -m ruff check src/example.py --extend-ignore E501")
    assert module._has_unsafe_verification_flag("python -m ruff check src/example.py --lint.select F401")
    assert module._has_unsafe_verification_flag("python -m ruff check src/example.py --lint.ignore=E501")
    assert module._has_unsafe_verification_flag("python -m ruff check src/example.py --config ruff.toml")
    assert module._has_unsafe_verification_flag("python -m ruff check src/example.py --config=ruff.toml")
    assert module._has_unsafe_verification_flag("python -m ruff check src/example.py --isolated")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py -c pytest.ini")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py -q --override-ini addopts=")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py -q --override-ini=addopts=")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --rootdir tests")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --rootdir=tests")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --confcutdir tests")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --confcutdir=tests")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --import-mode importlib")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --import-mode=importlib")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py -o addopts=")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py -o=addopts=")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py -oaddopts=")
    assert module._has_unsafe_verification_flag("python -m pytest tests/example.py --pyargs")
    assert module._has_unsafe_verification_flag("python -m pytest --help")
    assert module._has_unsafe_verification_flag("python -m pytest -h")
    assert module._has_unsafe_verification_flag("python -m ruff check --version")
    assert module._has_unsafe_verification_flag("python -m ruff check -V")


def test_shell_control_operator_parser_rejects_command_substitution() -> None:
    """The shell-control parser rejects command substitution inside direct commands."""

    assert not module._has_shell_control_operator("python -m pytest tests/example.py -q")
    assert module._has_shell_control_operator("python -m pytest tests/example.py -q $(python -c print(1))")
    assert module._has_shell_control_operator(
        "python -m ruff check src/example.py tests/example.py `python -c print(1)`"
    )


def test_shell_control_operator_parser_rejects_variable_expansion() -> None:
    """The shell-control parser rejects shell variables inside direct commands."""

    assert not module._has_shell_control_operator("python -m pytest tests/example.py -q")
    assert not module._has_shell_control_operator("python -m pytest tests/example.py -q --cov-fail-under 80")
    assert module._has_shell_control_operator("python -m pytest tests/example.py -q $env:PYTEST_ADDOPTS")
    assert module._has_shell_control_operator("python -m pytest tests/example.py -q $PYTEST_ADDOPTS")
    assert module._has_shell_control_operator("python -m ruff check src/example.py ${RUFF_FLAGS}")
    assert module._has_shell_control_operator("git diff --check -- src/example.py %DIFF_PATHS%")


def test_response_file_argument_parser_rejects_at_file_tokens() -> None:
    """The response-file parser rejects hidden argument file tokens."""

    assert not module._has_response_file_argument("python -m pytest tests/example.py -q")
    assert not module._has_response_file_argument("python -m pytest tests/example.py -q user@example.test")
    assert module._has_response_file_argument("python -m pytest tests/example.py -q @pytest.args")
    assert module._has_response_file_argument('python -m ruff check src/example.py "@ruff.args"')
    assert module._has_response_file_argument("rg -n --pcre2 -e pattern -- @paths.txt")


def test_required_verification_command_matcher_rejects_shell_wrappers() -> None:
    """Command-family matching requires the verification tool at command start."""

    assert module._matches_required_verification_command("python -m pytest tests/example.py -q", "pytest")
    assert module._matches_required_verification_command("py -m pytest tests/example.py -q", "pytest")
    assert module._matches_required_verification_command("python.exe -m ruff check src/example.py", "ruff")
    assert module._matches_required_verification_command("git diff --check -- src/example.py", "git diff --check")

    assert module._has_wrapped_required_verification_command(
        "powershell -Command python -m pytest tests/example.py -q"
    )
    assert module._has_wrapped_required_verification_command(
        "cmd /c python -m ruff check src/example.py tests/example.py"
    )
    assert module._has_wrapped_required_verification_command(
        "bash -lc git diff --check -- src/example.py tests/example.py"
    )

    assert not module._matches_required_verification_command(
        "powershell -Command python -m pytest tests/example.py -q",
        "pytest",
    )


def test_validate_handoff_docs_rejects_ready_inbox_mutating_verification_flags(tmp_path: Path) -> None:
    """Ready inbox verification commands cannot use flags that mutate files."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py --unsafe-fixes",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must not include unsafe verification flags" in issue for issue in issues)
    assert any("ready inbox verification must include: ruff" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_redirected_verification_command(tmp_path: Path) -> None:
    """Ready inbox verification commands cannot redirect command output."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q > result.txt",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must not include shell control operators" in issue for issue in issues)
    assert any("ready inbox verification must include: pytest" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_shell_command_substitution(tmp_path: Path) -> None:
    """Ready inbox verification commands cannot include shell command substitution."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q $(python -c print(1))",
            "python -m ruff check src/example.py tests/example.py `python -c print(1)`",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must not include shell control operators" in issue for issue in issues)
    assert any("ready inbox verification must include: pytest" in issue for issue in issues)
    assert any("ready inbox verification must include: ruff" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_shell_variable_expansion(tmp_path: Path) -> None:
    """Ready inbox verification commands cannot include shell variable expansion."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q $env:PYTEST_ADDOPTS",
            "python -m ruff check src/example.py tests/example.py ${RUFF_FLAGS}",
            "git diff --check -- src/example.py tests/example.py %DIFF_PATHS%",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must not include shell control operators" in issue for issue in issues)
    assert any("ready inbox verification must include: pytest" in issue for issue in issues)
    assert any("ready inbox verification must include: ruff" in issue for issue in issues)
    assert any("ready inbox verification must include: git diff --check" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_response_file_verification_argument(tmp_path: Path) -> None:
    """Ready inbox verification commands cannot include hidden argument files."""

    inbox = _ready_deepseek_inbox(
        verification_commands=(
            "python -m pytest tests/example.py -q @pytest.args",
            "python -m ruff check src/example.py tests/example.py @ruff.args",
            "git diff --check -- src/example.py tests/example.py @diff.args",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox verification command must not include response-file arguments" in issue for issue in issues)
    assert any("ready inbox verification must include: pytest" in issue for issue in issues)
    assert any("ready inbox verification must include: ruff" in issue for issue in issues)
    assert any("ready inbox verification must include: git diff --check" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_duplicate_verification_commands(tmp_path: Path) -> None:
    """Ready inbox verification commands must be unique."""

    duplicated_command = "python -m pytest tests/example.py -q"
    inbox = _ready_deepseek_inbox(
        verification_commands=(
            duplicated_command,
            duplicated_command,
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert (
        f"{module.INBOX_PATH.as_posix()} ready inbox verification command is duplicated: {duplicated_command}"
        in issues
    )


def test_validate_handoff_docs_rejects_ready_inbox_without_scan_command(tmp_path: Path) -> None:
    """Ready inbox assignments must include a concrete scoped scan command."""

    inbox = _ready_deepseek_inbox().replace(
        (
            "## Anti-Placeholder Scan\n"
            "- Run scoped scan over changed files.\n"
            "```powershell\n"
            f"{_scan_command(['src/example.py', 'tests/example.py'])}\n"
            "```\n"
        ),
        "## Anti-Placeholder Scan\n- Run scoped scan over changed files.\n",
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox Anti-Placeholder scan must include a parseable command" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_template_scan_marker(tmp_path: Path) -> None:
    """Ready inbox scan commands must not retain template scanner markers."""

    inbox = _ready_deepseek_inbox().replace(
        module.ANTI_PLACEHOLDER_SCANNER_PATTERNS[0],
        "BLOCKED_SCANNER_PATTERN",
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox Anti-Placeholder scan command must include a concrete scanner expression" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_non_rg_scan_command(tmp_path: Path) -> None:
    """Ready inbox scan commands must start with the scanner executable."""

    inbox = _ready_deepseek_inbox().replace(
        "rg -n --pcre2",
        "Write-Output rg -n --pcre2",
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready inbox Anti-Placeholder scan command must start with rg or rg.exe" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_inbox_scan_missing_configured_patterns(tmp_path: Path) -> None:
    """Ready inbox scan commands must include the full configured scanner expression."""

    files = ["src/example.py", "tests/example.py"]
    partial_command = (
        f'rg -n --pcre2 -e "{module.ANTI_PLACEHOLDER_SCANNER_PATTERNS[0]}" '
        "-- src/example.py tests/example.py"
    )
    inbox = _ready_deepseek_inbox().replace(
        _scan_command(files),
        partial_command,
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready inbox Anti-Placeholder scan command must include all configured scanner patterns" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_inbox_scan_missing_path_delimiter(tmp_path: Path) -> None:
    """Ready inbox scan commands must separate scanner expressions from paths."""

    files = ["src/example.py", "tests/example.py"]
    command_without_delimiter = _scan_command(files).replace(
        " -- src/example.py tests/example.py",
        " src/example.py tests/example.py",
    )
    inbox = _ready_deepseek_inbox().replace(
        _scan_command(files),
        command_without_delimiter,
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready inbox Anti-Placeholder scan command must use -- before the path list" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_inbox_scan_variable_expansion(tmp_path: Path) -> None:
    """Ready inbox scan commands cannot include shell variable expansion."""

    files = ["src/example.py", "tests/example.py"]
    original_command = _scan_command(files)
    inbox = _ready_deepseek_inbox().replace(
        original_command,
        f"{original_command} ${{SCAN_PATHS}}",
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready inbox Anti-Placeholder scan command must not include shell control operators" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_inbox_scan_response_file_argument(tmp_path: Path) -> None:
    """Ready inbox scan commands cannot include hidden argument files."""

    files = ["src/example.py", "tests/example.py"]
    original_command = _scan_command(files)
    inbox = _ready_deepseek_inbox().replace(
        original_command,
        f"{original_command} @scan.args",
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready inbox Anti-Placeholder scan command must not include response-file arguments" in issue
        for issue in issues
    )
    assert any(
        "ready inbox Anti-Placeholder scan command must mention allowed file: src/example.py" in issue
        for issue in issues
    )
    assert any(
        "ready inbox Anti-Placeholder scan command must mention allowed file: tests/example.py" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_inbox_scan_missing_allowed_file(tmp_path: Path) -> None:
    """Ready inbox scan commands must cover every allowed file path token."""

    inbox = _ready_deepseek_inbox().replace(
        "-- src/example.py tests/example.py",
        "-- src/example.py",
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready inbox Anti-Placeholder scan command must mention allowed file: tests/example.py" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_inbox_missing_contract_sections(tmp_path: Path) -> None:
    """Ready inbox assignments must define input and output contracts."""

    inbox = (
        _ready_deepseek_inbox()
        .replace("## Input Contracts\n- Preserve existing inputs for the assigned files.\n", "")
        .replace("## Output Contracts\n- Preserve existing outputs for the assigned files.\n", "")
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.INBOX_PATH.as_posix()} ready inbox has empty section: ## Input Contracts" in issues
    assert f"{module.INBOX_PATH.as_posix()} ready inbox has empty section: ## Output Contracts" in issues
    assert any("ready inbox must include at least one input contract item" in issue for issue in issues)
    assert any("ready inbox must include at least one output contract item" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_duplicate_contract_items(tmp_path: Path) -> None:
    """Ready inbox contract items must carry distinct boundaries."""

    inbox = (
        _ready_deepseek_inbox()
        .replace(
            "- Preserve existing inputs for the assigned files.",
            "- Preserve existing inputs for the assigned files.\n- Preserve existing inputs for the assigned files.",
        )
        .replace(
            "- Preserve existing outputs for the assigned files.",
            "- Preserve existing outputs for the assigned files.\n- Preserve existing outputs for the assigned files.",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox input contract is duplicated" in issue for issue in issues)
    assert any("ready inbox output contract is duplicated" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_contract_stand_ins(tmp_path: Path) -> None:
    """Ready inbox contract items cannot be empty stand-ins."""

    inbox = (
        _ready_deepseek_inbox()
        .replace("- Preserve existing inputs for the assigned files.", "- None.")
        .replace("- Preserve existing outputs for the assigned files.", "- TBD")
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox input contract is an empty stand-in: None." in issue for issue in issues)
    assert any("ready inbox output contract is an empty stand-in: TBD" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_task_text_stand_ins(tmp_path: Path) -> None:
    """Ready inbox task-defining text cannot be empty stand-ins."""

    inbox = (
        _ready_deepseek_inbox(message_id="unknown")
        .replace("Task: TASK_1", "Task: TBD")
        .replace("- Add one deterministic example behavior.", "- None")
        .replace("1. Preserve existing interfaces.", "1. None")
        .replace("- [ ] Happy path verified.", "- [ ] unknown")
        .replace("python -m pytest tests/example.py -q", "pending")
        .replace("- Stop when the task needs files outside allowed scope.", "- None")
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox Message ID must not use empty stand-in: unknown" in issue for issue in issues)
    assert any("ready inbox Task must not use empty stand-in: TBD" in issue for issue in issues)
    assert any("ready inbox objective is an empty stand-in: None" in issue for issue in issues)
    assert any("ready inbox requirement is an empty stand-in: None" in issue for issue in issues)
    assert any("ready inbox acceptance criterion is an empty stand-in: unknown" in issue for issue in issues)
    assert any("ready inbox verification command is an empty stand-in: pending" in issue for issue in issues)
    assert any("ready inbox stop condition is an empty stand-in: None" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_without_worktree_baseline(tmp_path: Path) -> None:
    """A ready DeepSeek task must record the assignment-time worktree baseline."""

    inbox = _ready_deepseek_inbox().replace(
        "## Worktree Baseline\n- None.\n",
        "",
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.INBOX_PATH.as_posix()} ready inbox has empty section: ## Worktree Baseline" in issues


def test_validate_handoff_docs_rejects_unsafe_ready_inbox_required_reading_paths(tmp_path: Path) -> None:
    """A hand-written ready inbox must keep required-reading paths safe and unique."""

    inbox = (
        _ready_deepseek_inbox()
        .replace(
            "- docs/handoff/deepseek_inbox.md\n## Current Task",
            "- docs/handoff/deepseek_inbox.md\n- ../secret.md\n- docs/with space.md\n- .venv/pyvenv.cfg\n- N/A\n- None\n- spec.md\n## Current Task",
        )
        .replace(
            "- `docs/handoff/deepseek_inbox.md`\n## Allowed Files",
            "- `docs/handoff/deepseek_inbox.md`\n- `../secret.md`\n- `docs/with space.md`\n- `.venv/pyvenv.cfg`\n- `N/A`\n- `None`\n- `spec.md`\n## Allowed Files",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("unsafe required reading before editing path: ../secret.md" in issue for issue in issues)
    assert any("unsafe required reading before editing path: docs/with space.md" in issue for issue in issues)
    assert any("unsafe required reading before editing path: .venv/pyvenv.cfg" in issue for issue in issues)
    assert any("empty required reading before editing path stand-in: N/A" in issue for issue in issues)
    assert any("empty required reading before editing path stand-in: None" in issue for issue in issues)
    assert any("duplicate required reading before editing path: spec.md" in issue for issue in issues)
    assert any("unsafe required reading path: ../secret.md" in issue for issue in issues)
    assert any("unsafe required reading path: docs/with space.md" in issue for issue in issues)
    assert any("unsafe required reading path: .venv/pyvenv.cfg" in issue for issue in issues)
    assert any("empty required reading path stand-in: N/A" in issue for issue in issues)
    assert any("empty required reading path stand-in: None" in issue for issue in issues)
    assert any("duplicate required reading path: spec.md" in issue for issue in issues)


def test_validate_handoff_docs_rejects_non_file_ready_inbox_required_reading_paths(tmp_path: Path) -> None:
    """A ready inbox required-reading path must point to a file."""

    inbox = (
        _ready_deepseek_inbox()
        .replace(
            "- docs/handoff/deepseek_inbox.md\n## Current Task",
            "- docs/handoff/deepseek_inbox.md\n- docs/missing.md\n- docs/handoff\n## Current Task",
        )
        .replace(
            "- `docs/handoff/deepseek_inbox.md`\n## Allowed Files",
            "- `docs/handoff/deepseek_inbox.md`\n- `docs/missing.md`\n- `docs/handoff`\n## Allowed Files",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready inbox required reading before editing path must point to a file: docs/missing.md" in issue
        for issue in issues
    )
    assert any(
        "ready inbox required reading before editing path must point to a file: docs/handoff" in issue
        for issue in issues
    )
    assert any("ready inbox required reading path must point to a file: docs/missing.md" in issue for issue in issues)
    assert any("ready inbox required reading path must point to a file: docs/handoff" in issue for issue in issues)


def test_validate_handoff_docs_rejects_required_reading_section_mismatch(tmp_path: Path) -> None:
    """Ready inbox required-reading sections must stay in sync."""

    inbox = _ready_deepseek_inbox().replace(
        "- `docs/handoff/deepseek_inbox.md`\n## Allowed Files",
        "- `docs/handoff/deepseek_inbox.md`\n- `README.md`\n## Allowed Files",
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.INBOX_PATH.as_posix()} ready inbox required-reading sections must match" in issues


def test_validate_handoff_docs_rejects_missing_core_required_reading(tmp_path: Path) -> None:
    """Ready inbox assignments must keep core reading context."""

    inbox = _ready_deepseek_inbox().replace("- task.md\n", "").replace("- `task.md`\n", "")
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox required reading before editing must include core path: task.md" in issue for issue in issues)
    assert any("ready inbox required reading must include core path: task.md" in issue for issue in issues)


def test_validate_handoff_docs_allows_canonical_inbox_required_reading(tmp_path: Path) -> None:
    """The canonical inbox can remain task context for DeepSeek."""

    inbox = _ready_deepseek_inbox()
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert issues == []


def test_validate_handoff_docs_rejects_control_file_required_reading(tmp_path: Path) -> None:
    """Ready inbox required-reading paths cannot point at mutable control files."""

    inbox = (
        _ready_deepseek_inbox()
        .replace(
            "- docs/handoff/deepseek_inbox.md\n## Current Task",
            "- docs/handoff/deepseek_inbox.md\n- docs/handoff/deepseek_outbox.md\n- DEEPSEEK_INBOX.md\n- CODEX_REVIEW.md\n## Current Task",
        )
        .replace(
            "- `docs/handoff/deepseek_inbox.md`\n## Allowed Files",
            "- `docs/handoff/deepseek_inbox.md`\n- `docs/handoff/deepseek_outbox.md`\n- `DEEPSEEK_INBOX.md`\n- `CODEX_REVIEW.md`\n## Allowed Files",
        )
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready inbox required reading before editing path must not list handoff control file: "
        "docs/handoff/deepseek_outbox.md"
        in issue
        for issue in issues
    )
    assert any(
        "ready inbox required reading before editing path must not list handoff control file: DEEPSEEK_INBOX.md"
        in issue
        for issue in issues
    )
    assert any(
        "ready inbox required reading path must not list handoff control file: CODEX_REVIEW.md" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_inbox_with_unlisted_worktree_baseline(tmp_path: Path) -> None:
    """A ready DeepSeek task baseline must be an explicit bullet list."""

    inbox = _ready_deepseek_inbox().replace(
        "## Worktree Baseline\n- None.\n",
        "## Worktree Baseline\nCurrent tree is clean.\n",
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.INBOX_PATH.as_posix()} ready inbox worktree baseline must list None or paths" in issues


def test_validate_handoff_docs_rejects_unsafe_worktree_baseline_paths(tmp_path: Path) -> None:
    """A ready DeepSeek task baseline must contain safe unique repository paths."""

    inbox = _ready_deepseek_inbox().replace(
        "## Worktree Baseline\n- None.\n",
        "\n".join(
            [
                "## Worktree Baseline",
                "- None.",
                "- `../outside.py`",
                "- `src/example.py`",
                "- `src/example.py`",
                "",
            ]
        ),
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.INBOX_PATH.as_posix()} ready inbox worktree baseline cannot mix None with paths" in issues
    assert any("unsafe worktree baseline path: ../outside.py" in issue for issue in issues)
    assert any("duplicate worktree baseline path: src/example.py" in issue for issue in issues)


def test_validate_handoff_docs_rejects_worktree_baseline_overlapping_allowed_scope(tmp_path: Path) -> None:
    """A ready DeepSeek task baseline must not mask assigned-file changes."""

    inbox = _ready_deepseek_inbox().replace(
        "## Worktree Baseline\n- None.\n",
        "\n".join(
            [
                "## Worktree Baseline",
                "- `src/example.py`",
                "- `tests`",
                "",
            ]
        ),
    )
    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=inbox,
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("worktree baseline must not overlap allowed scope: src/example.py vs src/example.py" in issue for issue in issues)
    assert any("worktree baseline must not overlap allowed scope: tests vs tests/example.py" in issue for issue in issues)


def test_validate_handoff_docs_rejects_unbounded_ready_inbox(tmp_path: Path) -> None:
    """A ready DeepSeek task must include tight scope and verification commands."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            message_id="unassigned",
            allowed_files=[
                "src/a.py",
                "src/b.py",
                "src/c.py",
                "src/d.py",
                "src/e.py",
                "src/f.py",
            ],
            verification_commands=("python -m pytest tests/example.py -q",),
        ),
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="unassigned",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready inbox must set a concrete Message ID" in issue for issue in issues)
    assert any("ready inbox must limit allowed files to 5 or fewer" in issue for issue in issues)
    assert any("ready inbox verification must include: ruff" in issue for issue in issues)
    assert any("ready inbox verification must include: git diff --check" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_without_codex_gate_ok(tmp_path: Path) -> None:
    """Ready DeepSeek assignments require an explicit Codex gate release."""

    inbox_text = _ready_deepseek_inbox().replace("CODEX_GATE: PASS", "CODEX_GATE: REQUIRED")
    _write_valid_handoff_docs(tmp_path, inbox_text=inbox_text)

    issues = module.validate_handoff_docs(tmp_path)

    assert f"{module.INBOX_PATH.as_posix()} ready inbox must set CODEX_GATE: PASS" in issues


def test_validate_handoff_docs_rejects_unsafe_scope_paths(tmp_path: Path) -> None:
    """Assigned task scopes must stay repository-relative and non-overlapping."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            allowed_files=[
                "/tmp/example.py",
                "../outside.py",
                "https://example.com/file.py",
                "src`bad.py",
                "./src/example.py",
                "src/./example.py",
                "src/**/*.py",
                "src/example.py#L12",
                "src/example.py;extra",
                "src/$NAME.py",
                "src/example file.py",
                ".git/config",
                "src/__pycache__/module.py",
                "N/A",
                "None",
                "src/example.py",
                "src/example.py",
            ],
            forbidden_files=[
                "src",
                "private/*",
                "private/generated#note.py",
                "private/generated file.py",
                "node_modules/pkg/index.js",
                "TBD",
                "Not applicable",
            ],
        ),
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("unsafe allowed path: /tmp/example.py" in issue for issue in issues)
    assert any("unsafe allowed path: ../outside.py" in issue for issue in issues)
    assert any("unsafe allowed path: https://example.com/file.py" in issue for issue in issues)
    assert any("unsafe allowed path: `src`bad.py`" in issue for issue in issues)
    assert any("unsafe allowed path: ./src/example.py" in issue for issue in issues)
    assert any("unsafe allowed path: src/./example.py" in issue for issue in issues)
    assert any("unsafe allowed path: src/**/*.py" in issue for issue in issues)
    assert any("unsafe allowed path: src/example.py#L12" in issue for issue in issues)
    assert any("unsafe allowed path: src/example.py;extra" in issue for issue in issues)
    assert any("unsafe allowed path: src/$NAME.py" in issue for issue in issues)
    assert any("unsafe allowed path: src/example file.py" in issue for issue in issues)
    assert any("unsafe allowed path: .git/config" in issue for issue in issues)
    assert any("unsafe allowed path: src/__pycache__/module.py" in issue for issue in issues)
    assert any("unsafe forbidden path: private/*" in issue for issue in issues)
    assert any("unsafe forbidden path: private/generated#note.py" in issue for issue in issues)
    assert any("unsafe forbidden path: private/generated file.py" in issue for issue in issues)
    assert any("unsafe forbidden path: node_modules/pkg/index.js" in issue for issue in issues)
    assert any("empty allowed path stand-in: N/A" in issue for issue in issues)
    assert any("empty allowed path stand-in: None" in issue for issue in issues)
    assert any("empty forbidden path stand-in: TBD" in issue for issue in issues)
    assert any("empty forbidden path stand-in: Not applicable" in issue for issue in issues)
    assert any("duplicate allowed path: src/example.py" in issue for issue in issues)
    assert any("overlapping allowed and forbidden scope: src/example.py vs src" in issue for issue in issues)


def test_validate_handoff_docs_rejects_overlapping_scope_entries_in_same_list(tmp_path: Path) -> None:
    """Assigned allowed and forbidden scopes cannot overlap within their own lists."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            allowed_files=["src/example_pkg", "src/example_pkg/module.py"],
            forbidden_files=["private", "private/generated"],
        ),
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        "ready inbox has overlapping allowed scope: src/example_pkg vs src/example_pkg/module.py" in issue
        for issue in issues
    )
    assert any("ready inbox has overlapping forbidden scope: private vs private/generated" in issue for issue in issues)


def test_validate_handoff_docs_rejects_handoff_control_allowed_scope(tmp_path: Path) -> None:
    """Assigned implementation scope cannot include handoff control files."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            allowed_files=[
                "docs/handoff/deepseek_inbox.md",
                "DEEPSEEK_INBOX.md",
                "docs/handoff",
            ],
            forbidden_files=["src/other.py"],
        ),
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("handoff control file: docs/handoff/deepseek_inbox.md" in issue for issue in issues)
    assert any("handoff control file: DEEPSEEK_INBOX.md" in issue for issue in issues)
    assert any("handoff control file: docs/handoff" in issue for issue in issues)


def test_validate_handoff_docs_rejects_workflow_control_allowed_scope(tmp_path: Path) -> None:
    """Assigned implementation scope cannot include workflow control files."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            allowed_files=[
                "progress.md",
                "test_plan.md",
                "docs/handoff/deepseek_task_template.md",
                "utils/validate_handoff_docs.py",
            ],
            forbidden_files=["src/other.py"],
        ),
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any("workflow control file: progress.md" in issue for issue in issues)
    assert any("workflow control file: test_plan.md" in issue for issue in issues)
    assert any("workflow control file: docs/handoff/deepseek_task_template.md" in issue for issue in issues)
    assert any("workflow control file: utils/validate_handoff_docs.py" in issue for issue in issues)


@pytest.mark.parametrize(
    "allowed_scope",
    ["dayu", "docs", "src", "tests", "utils", ".github", "workspace"],
)
def test_validate_handoff_docs_rejects_broad_top_level_allowed_scope(
    tmp_path: Path,
    allowed_scope: str,
) -> None:
    """Assigned implementation scope cannot hand DeepSeek a whole top-level area."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(
            allowed_files=[allowed_scope],
            forbidden_files=["src/other.py"],
        ),
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert any(
        f"ready inbox allowed scope must not use broad top-level directory: {allowed_scope}" in issue
        for issue in issues
    )


def test_validate_handoff_docs_rejects_ready_inbox_with_unreset_outbox(tmp_path: Path) -> None:
    """Assigned tasks require an outbox state that waits for DeepSeek or Codex."""

    _write_valid_handoff_docs(tmp_path, inbox_text=_ready_deepseek_inbox())

    issues = module.validate_handoff_docs(tmp_path)

    assert any("ready task requires docs/handoff/deepseek_outbox.md Status" in issue for issue in issues)


def test_validate_handoff_docs_rejects_ready_inbox_with_blank_waiting_outbox_metadata(tmp_path: Path) -> None:
    """A waiting outbox for an assigned task must name the same delivery."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="",
        outbox_task="",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "handoff Message ID mismatch: inbox=codex-task-1 outbox=<empty>" in issues
    assert "handoff Task mismatch: inbox=TASK_1 outbox=<empty>" in issues


def test_validate_handoff_docs_rejects_message_id_mismatch(tmp_path: Path) -> None:
    """Inbox and outbox must describe the same assigned task."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="different-task",
        outbox_task="TASK_1",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "handoff Message ID mismatch: inbox=codex-task-1 outbox=different-task" in issues


def test_validate_handoff_docs_rejects_task_code_mismatch(tmp_path: Path) -> None:
    """Inbox and outbox task codes must match."""

    _write_valid_handoff_docs(
        tmp_path,
        inbox_text=_ready_deepseek_inbox(),
        outbox_status=module.WAITING_FOR_DEEPSEEK,
        outbox_message_id="codex-task-1",
        outbox_task="TASK_2",
    )

    issues = module.validate_handoff_docs(tmp_path)

    assert "handoff Task mismatch: inbox=TASK_1 outbox=TASK_2" in issues


def test_main_returns_nonzero_for_invalid_root(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI returns a failing status and prints validation issues."""

    result = module.main(["--root", str(tmp_path)])

    captured = capsys.readouterr()
    assert result == 1
    assert "handoff docs validation failed" in captured.err
    assert "missing required file" in captured.err


def test_main_can_print_json_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI can emit structured validation issues."""

    result = module.main(["--root", str(tmp_path), "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert result == 1
    assert captured.err == ""
    assert data["ok"] is False
    assert any("missing required file" in issue for issue in data["issues"])


def _write_valid_handoff_docs(
    root: Path,
    *,
    outbox_status: str = "WAITING_FOR_TASK",
    outbox_message_id: str = "unassigned",
    outbox_task: str = "unassigned",
    inbox_text: str | None = None,
) -> None:
    """Write a minimal valid handoff document set under ``root``."""

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
    _write(root / "src" / "example.py", "VALUE = 1\n")
    _write(root / "tests" / "example.py", "VALUE = 1\n")

    _write(handoff_dir / "deepseek_inbox.md", inbox_text or _waiting_deepseek_inbox())
    _write(
        handoff_dir / "deepseek_outbox.md",
        _deepseek_outbox(
            outbox_status,
            message_id=outbox_message_id,
            task=outbox_task,
        ),
    )
    _write(
        handoff_dir / "codex_review_checklist.md",
        "\n".join(
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
        + "\n",
    )
    _write(
        handoff_dir / "dual_model_development_workflow.md",
        "\n".join(
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
                "- Codex assigns and reviews.",
                "## Task Size Rules",
                "- Keep tasks small.",
                "## Required DeepSeek Task Template",
                "- Use the template.",
                "## Completion Is Not Self-Certifying",
                "- Codex verifies.",
            ]
        )
        + "\n",
    )
    _write(
        handoff_dir / "cross_platform_continuation.md",
        "\n".join(
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
        + "\n",
    )
    _write(
        handoff_dir / "deepseek_task_template.md",
        "\n".join(
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
                "- File list.",
                "## Forbidden Files",
                "- File list.",
                "## Worktree Baseline",
                "- None.",
                "Worktree baseline entries must not overlap allowed files.",
                "Requirements must be unique and include at least three numbered items.",
                "## Acceptance Criteria",
                "- Criteria.",
                "Acceptance criteria must be unique and include at least three unchecked items.",
                "Remove every angle-bracket marker before assigning the task.",
                "## Verification Commands",
                "- Command.",
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
                f"- {module.READY_FOR_REVIEW}",
            ]
        )
        + "\n",
    )
    _write(
        handoff_dir / "deepseek_assignment_examples.md",
        "\n".join(
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
                module.READY_FOR_REVIEW,
            ]
        )
        + "\n",
    )
    _write(
        handoff_dir / "deepseek_task_spec_schema.md",
        _task_spec_schema_text(),
    )
    _write(
        handoff_dir / "codex_review_template.md",
        "\n".join(
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
        + "\n",
    )


def _deepseek_outbox(status: str, *, message_id: str, task: str) -> str:
    lines = [
        "# DeepSeek Outbox",
        f"Status: {status}",
        f"Message ID: {message_id}",
        f"Task: {task}",
    ]
    if status == module.READY_FOR_REVIEW:
        lines.append(module.READY_FOR_REVIEW)
    lines.extend(
        [
            "## Summary",
            "- Waiting for a concrete implementation summary.",
            "- No implementation evidence has been submitted yet.",
            "## Changed Files",
            "- src/example.py",
            "## Verification Commands and Results",
            "- Not run",
            "## Acceptance Criteria",
            "- Waiting.",
            "## Scope Deviations",
            "- None.",
            "## Anti-Placeholder Scan",
            "- Not run",
            "## Unresolved Questions or Blockers",
            "- None.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_ready_outbox_with_acceptance(
    root: Path,
    acceptance_lines: list[str],
    *,
    unresolved_lines: list[str] | None = None,
    scan_lines: list[str] | None = None,
) -> None:
    blocker_lines = ["- None."] if unresolved_lines is None else unresolved_lines
    scan_result_lines = (
        [f"- `{_scan_command(['src/example.py'])}` returned no matches."]
        if scan_lines is None
        else scan_lines
    )
    (root / module.OUTBOX_PATH).write_text(
        "\n".join(
            [
                "# DeepSeek Outbox",
                f"Status: {module.READY_FOR_REVIEW}",
                "Message ID: codex-task-1",
                "Task: TASK_1",
                module.READY_FOR_REVIEW,
                "## Summary",
                "- Updated `src/example.py` for the assigned behavior.",
                "- Added verification evidence for `tests/example.py`.",
                "## Changed Files",
                "- src/example.py",
                "## Verification Commands and Results",
                "- `python -m pytest tests/example.py -q` exited 0.",
                "- `python -m ruff check src/example.py tests/example.py` exited 0.",
                "- `git diff --check -- src/example.py tests/example.py` exited 0.",
                "## Acceptance Criteria",
                *acceptance_lines,
                "## Scope Deviations",
                "- None.",
                "## Anti-Placeholder Scan",
                *scan_result_lines,
                "## Unresolved Questions or Blockers",
                *blocker_lines,
                "",
            ]
        ),
        encoding="utf-8",
    )


def _waiting_deepseek_inbox() -> str:
    return (
        "\n".join(
            [
                "# DeepSeek Inbox",
                "Status: WAITING_FOR_TASK",
                "Message ID: unassigned",
                "Task: unassigned",
                "CODEX_GATE: REQUIRED",
                "## Operating Role",
                "- Read only the assigned task.",
                "## Required Reading Before Editing",
                "- spec.md",
                "## Current Task",
                "- Waiting.",
                "## Global Implementation Rules",
                "- Keep scope small.",
                "## Anti-Placeholder Scan",
                "- Run scoped scans.",
                "## Required Outbox Evidence",
                f"- {module.READY_FOR_REVIEW}",
            ]
        )
        + "\n"
    )


def _ready_deepseek_inbox(
    *,
    message_id: str = "codex-task-1",
    allowed_files: list[str] | None = None,
    forbidden_files: list[str] | None = None,
    verification_commands: tuple[str, ...] = (
        "python -m pytest tests/example.py -q",
        "python -m ruff check src/example.py tests/example.py",
        "git diff --check -- src/example.py tests/example.py",
    ),
) -> str:
    files = allowed_files or ["src/example.py", "tests/example.py"]
    return (
        "\n".join(
            [
                "# DeepSeek Inbox",
                f"Status: {module.READY_FOR_DEEPSEEK}",
                f"Message ID: {message_id}",
                "Task: TASK_1",
                "CODEX_GATE: PASS",
                "## Operating Role",
                "- Implement one bounded task.",
                "## Required Reading Before Editing",
                "- AGENTS.md",
                "- spec.md",
                "- architecture.md",
                "- task.md",
                "- docs/handoff/deepseek_inbox.md",
                "## Current Task",
                "- Implement the example task.",
                "## Global Implementation Rules",
                "- Keep scope small.",
                "## Objective",
                "- Add one deterministic example behavior.",
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
                *[f"- `{file_path}`" for file_path in files],
                "## Forbidden Files",
                *[f"- `{file_path}`" for file_path in (forbidden_files or ["src/other.py"])],
                "## Worktree Baseline",
                "- None.",
                "## Requirements",
                "1. Preserve existing interfaces.",
                "2. Add focused tests.",
                "3. Keep errors visible.",
                "## Acceptance Criteria",
                "- [ ] Happy path verified.",
                "- [ ] Error path verified.",
                "- [ ] Scope verified.",
                "## Verification Commands",
                "```powershell",
                *verification_commands,
                "```",
                "## Anti-Placeholder Scan",
                "- Run scoped scan over changed files.",
                "```powershell",
                _scan_command(files),
                "```",
                "## Stop Conditions",
                "- Stop when the task needs files outside allowed scope.",
                "- Stop when interface or behavior is missing.",
                "- Stop when tests require weaker assertions.",
            "## Required Outbox",
            f"- {module.READY_FOR_REVIEW}",
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
            f"- {module.READY_FOR_REVIEW}",
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
        + "\n"
    )


def _scan_command(files: list[str]) -> str:
    pattern_args = " ".join(f'-e "{pattern}"' for pattern in module.ANTI_PLACEHOLDER_SCANNER_PATTERNS)
    return f"rg -n --pcre2 {pattern_args} -- {' '.join(files)}"


def _task_spec_schema_text() -> str:
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
    ) + "\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
