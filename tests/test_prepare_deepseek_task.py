"""Tests for the DeepSeek task preparation utility."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from utils import prepare_deepseek_task as module
from utils import validate_handoff_docs

pytestmark = pytest.mark.unit


def test_render_task_creates_ready_inbox_text() -> None:
    """Rendered task text satisfies the ready-inbox validator."""

    text = module.render_task(_valid_spec())

    assert f"Status: {validate_handoff_docs.READY_FOR_DEEPSEEK}" in text
    assert "CODEX_GATE: PASS" in text
    assert "## Input Contracts" in text
    assert "## Output Contracts" in text
    assert module.DEFAULT_INPUT_CONTRACTS[0] in text
    assert module.DEFAULT_OUTPUT_CONTRACTS[0] in text
    assert "rg -n --pcre2 -e" in text
    for pattern in validate_handoff_docs.ANTI_PLACEHOLDER_SCANNER_PATTERNS:
        assert f'-e "{pattern}"' in text
    assert "-- src/example.py tests/example.py" in text
    assert validate_handoff_docs._validate_ready_inbox(text) == []


def test_render_task_rejects_invalid_spec() -> None:
    """Ready inbox rendering must not expose invalid task metadata."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task="unassigned",
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=base.verification_commands,
    )

    with pytest.raises(ValueError) as exc_info:
        module.render_task(spec)

    assert "task spec validation failed" in str(exc_info.value)
    assert "task must be concrete" in str(exc_info.value)


def test_render_task_describes_ready_outbox_evidence_requirements() -> None:
    """Rendered task text tells DeepSeek how to provide review evidence."""

    text = module.render_task(_valid_spec())

    assert "concrete summary with at least two bullet items" in text
    assert "checked acceptance criteria evidence" in text
    assert "checked acceptance evidence must not say skipped, unverified, untested, pending, deferred" in text
    assert "Anti-Placeholder scan command and clean result" in text
    assert "Anti-Placeholder scan command must be exact and must not use shell control operators" in text
    assert "Anti-Placeholder scan command must not include unresolved angle-bracket markers" in text
    assert (
        "Anti-Placeholder clean result markers inside the backticked scan command text do not count "
        "as scan result evidence"
    ) in text
    assert (
        "Anti-Placeholder clean result evidence must appear on the same line as the parseable "
        "scan command"
    ) in text
    assert "Anti-Placeholder evidence must not say skipped, not executed, not scanned, or no scan" in text
    assert "Anti-Placeholder scan command must mention every allowed file as a path token" in text
    assert "Anti-Placeholder scan command must start with `rg` or `rg.exe`." in text
    assert "Anti-Placeholder scan command must include every configured scanner pattern." in text
    assert "Anti-Placeholder scan command must use `--` before the path list." in text
    assert "Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`." in text
    assert "Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`." in text
    assert "Do not report empty stand-ins such as None, N/A, or no scan" in text
    assert "every assigned verification command result includes a clean marker such as `exited 0`" in text
    assert "clean result markers inside the backticked command text do not count as verification evidence" in text
    assert "verification evidence must not say dry-run, manual-only, simulated, synthetic, or fabricated" in text
    assert "explicit None when no unresolved questions or blockers remain" in text
    assert "Verification commands must mention each concrete allowed file as a path token." in text
    assert "Verification commands must start with direct command families, not shell wrappers." in text
    assert "Verification commands must not use shell redirection." in text
    assert "Verification commands must not use command substitution such as `$(...)` or backticks." in text
    assert "Verification commands must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`." in text
    assert "Verification commands must not use response-file or splatting arguments such as `@args.txt`." in text
    assert "Verification commands must not include unsafe verification flags" in text
    assert "No-run or mutating verification flags such as `--co`, `--fixtures`, " in text
    assert "Rerun-only or early-stop verification flags such as `--lf`, " in text
    assert "Rule-selection or config-override verification flags such as `--select`, " in text
    assert "Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, " in text
    assert "Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe." in text
    assert "Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe." in text
    assert "Attached short filter forms such as `-kslow` or `-mslow` are unsafe too." in text
    assert "Git diff-check commands with pathspecs must use `--` before the path list." in text
    assert "Git diff-check commands must mention every allowed file or directory scope as a path token." in text
    assert "Path values must not use wildcards or glob metacharacters." in text
    assert "Path values must not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes." in text
    assert "Path values must not use empty stand-ins such as None, N/A, TBD, or unknown." in text
    assert "Task text values must not use empty stand-ins such as None, N/A, TBD, or unknown." in text
    assert "Path values must not contain embedded whitespace." in text
    assert "Path values must not target VCS, dependency, or cache directories." in text
    assert "Allowed files must not include workflow control files" in text
    assert "Allowed files must not use broad top-level directory scopes" in text
    assert "Allowed and forbidden files must not contain overlapping scope entries" in text
    assert "changed-file evidence must not list workflow control files" in text


def test_render_task_keeps_required_reading_sections_in_sync() -> None:
    """Rendered task text keeps both required-reading sections aligned."""

    base_spec = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base_spec.message_id,
        task=base_spec.task,
        objective=base_spec.objective,
        allowed_files=base_spec.allowed_files,
        forbidden_files=base_spec.forbidden_files,
        requirements=base_spec.requirements,
        acceptance_criteria=base_spec.acceptance_criteria,
        verification_commands=base_spec.verification_commands,
        required_reading=(*module.DEFAULT_REQUIRED_READING, "docs/handoff/deepseek_task_template.md"),
    )

    text = module.render_task(spec)

    before_editing = validate_handoff_docs._normalized_required_reading_paths(
        text,
        "## Required Reading Before Editing",
    )
    required_reading = validate_handoff_docs._normalized_required_reading_paths(text, "## Required Reading")
    assert before_editing == required_reading
    assert validate_handoff_docs._validate_ready_inbox(text) == []


def test_render_task_records_worktree_baseline_paths() -> None:
    """Rendered task text records pre-assignment worktree paths."""

    text = module.render_task(_valid_spec(), worktree_baseline=("README.md", "docs/notes.md"))

    assert "## Worktree Baseline" in text
    assert "- `README.md`" in text
    assert "- `docs/notes.md`" in text


def test_render_task_rejects_worktree_baseline_overlapping_allowed_files() -> None:
    """Rendered task text rejects baseline paths that overlap assigned files."""

    with pytest.raises(ValueError) as exc_info:
        module.render_task(_valid_spec(), worktree_baseline=("src/example.py",))

    assert "worktree baseline path must not overlap allowed file: src/example.py vs src/example.py" in str(
        exc_info.value
    )


def test_render_task_rejects_unsafe_worktree_baseline_paths() -> None:
    """Rendered task text rejects unsafe or duplicate baseline paths."""

    with pytest.raises(ValueError) as exc_info:
        module.render_task(
            _valid_spec(),
            worktree_baseline=("src`bad.py", "src/example.py", "src/example.py"),
        )

    message = str(exc_info.value)
    assert "unsafe worktree baseline path: src`bad.py" in message
    assert "duplicate worktree baseline path: src/example.py" in message


def test_render_task_rejects_non_none_worktree_baseline_stand_in() -> None:
    """Rendered task text rejects loose clean-baseline stand-ins."""

    with pytest.raises(ValueError) as exc_info:
        module.render_task(_valid_spec(), worktree_baseline=("Clean.",))

    assert "worktree baseline path must use explicit None or a path, not stand-in: Clean." in str(exc_info.value)


def test_validate_spec_rejects_unbounded_input() -> None:
    """Task input must include scope and verification evidence."""

    spec = module.DeepSeekTaskSpec(
        message_id="unassigned",
        task="TASK_1",
        objective="Do the work.",
        allowed_files=("src/a.py", "src/b.py", "src/c.py", "src/d.py", "src/e.py", "src/f.py"),
        forbidden_files=(),
        requirements=("Keep behavior deterministic.",),
        acceptance_criteria=("Happy path verified.",),
        verification_commands=("python -m pytest tests/example.py -q",),
    )

    issues = module.validate_spec(spec)

    assert "message id must be concrete" in issues
    assert "allowed files must be limited to 5 or fewer" in issues
    assert "at least one forbidden file is required" in issues
    assert "at least 3 requirements are required" in issues
    assert "at least 3 acceptance criteria are required" in issues
    assert "verification commands must include: ruff" in issues
    assert "verification commands must include: git diff --check" in issues


def test_validate_spec_rejects_empty_input_and_output_contracts() -> None:
    """Task preparation requires explicit input and output boundaries."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=base.verification_commands,
        input_contracts=(),
        output_contracts=(),
    )

    issues = module.validate_spec(spec)

    assert "at least one input contract is required" in issues
    assert "at least one output contract is required" in issues
    assert any("ready inbox must include at least one input contract item" in issue for issue in issues)
    assert any("ready inbox must include at least one output contract item" in issue for issue in issues)


def test_validate_spec_rejects_contract_stand_ins() -> None:
    """Task preparation rejects contract fields that carry no usable boundary."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=base.verification_commands,
        input_contracts=("N/A",),
        output_contracts=("unknown",),
    )

    issues = module.validate_spec(spec)

    assert any("ready inbox input contract is an empty stand-in: N/A" in issue for issue in issues)
    assert any("ready inbox output contract is an empty stand-in: unknown" in issue for issue in issues)


def test_validate_spec_rejects_duplicate_requirements() -> None:
    """Task preparation rejects repeated requirements before writing."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=("Preserve public interfaces.", "Preserve public interfaces.", "Keep error paths visible."),
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=base.verification_commands,
        stop_conditions=base.stop_conditions,
    )

    issues = module.validate_spec(spec)

    assert "duplicate requirement: Preserve public interfaces." in issues
    assert "docs/handoff/deepseek_inbox.md ready inbox requirement is duplicated: Preserve public interfaces." in issues


def test_validate_spec_rejects_verification_command_family_substrings() -> None:
    """Task preparation must reject verification command lookalikes."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytester tests/example.py -q",
            "python -m ruffian check src/example.py tests/example.py",
            "git diff --checked -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification commands must include: pytest" in issues
    assert "verification commands must include: ruff" in issues
    assert "verification commands must include: git diff --check" in issues


def test_validate_spec_rejects_verification_commands_missing_allowed_file_coverage() -> None:
    """Task preparation requires verification commands to cover allowed files."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/other.py -q",
            "python -m ruff check tests/example.py",
            "git diff --check -- tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert (
        "docs/handoff/deepseek_inbox.md ready inbox git diff --check must mention allowed path: "
        "src/example.py"
    ) in issues
    assert (
        "docs/handoff/deepseek_inbox.md ready inbox ruff check must mention allowed Python file: "
        "src/example.py"
    ) in issues
    assert (
        "docs/handoff/deepseek_inbox.md ready inbox pytest must mention allowed test file: "
        "tests/example.py"
    ) in issues


def test_validate_spec_rejects_diff_check_without_pathspec_delimiter() -> None:
    """Task preparation requires diff-check pathspec separation."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert (
        "docs/handoff/deepseek_inbox.md ready inbox git diff --check command must use -- before pathspecs: "
        "git diff --check src/example.py tests/example.py"
    ) in issues
    assert "verification commands must include: git diff --check" in issues


def test_validate_spec_rejects_diff_check_missing_allowed_directory() -> None:
    """Task preparation requires diff-check commands to cover directory scope."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=("src/example_pkg",),
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example_pkg",
            "git diff --check -- tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert (
        "docs/handoff/deepseek_inbox.md ready inbox git diff --check must mention allowed path: "
        "src/example_pkg"
    ) in issues


def test_validate_spec_rejects_broad_top_level_allowed_scope() -> None:
    """Task preparation rejects overbroad top-level directory scopes."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=("tests",),
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check tests",
            "git diff --check -- tests",
        ),
    )

    issues = module.validate_spec(spec)

    assert (
        "docs/handoff/deepseek_inbox.md ready inbox allowed scope must not use "
        "broad top-level directory: tests"
    ) in issues


def test_validate_spec_rejects_duplicate_acceptance_criteria() -> None:
    """Task preparation rejects repeated acceptance criteria before writing."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=("Happy path verified.", "Happy path verified.", "Scope verified."),
        verification_commands=base.verification_commands,
        stop_conditions=base.stop_conditions,
    )

    issues = module.validate_spec(spec)

    assert "duplicate acceptance criterion: Happy path verified." in issues
    assert (
        "docs/handoff/deepseek_inbox.md ready inbox acceptance criterion is duplicated: Happy path verified."
        in issues
    )


def test_validate_spec_rejects_angle_bracket_markers() -> None:
    """Task preparation rejects unfilled angle-bracket markers before writing."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=("Implement the assigned behavior.", "<Fill requirement.>"),
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=base.verification_commands,
        stop_conditions=base.stop_conditions,
    )

    issues = module.validate_spec(spec)

    assert "requirement 2 must not contain angle-bracket markers" in issues


def test_validate_spec_rejects_duplicate_stop_conditions() -> None:
    """Task preparation rejects repeated stop conditions before writing."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=base.verification_commands,
        stop_conditions=(
            "Stop if scope expands.",
            "Stop if scope expands.",
            "Stop if tests require weaker assertions.",
        ),
    )

    issues = module.validate_spec(spec)

    assert "duplicate stop condition: Stop if scope expands." in issues
    assert "docs/handoff/deepseek_inbox.md ready inbox stop condition is duplicated: Stop if scope expands." in issues


def test_validate_spec_rejects_too_few_stop_conditions() -> None:
    """Task preparation requires enough stop conditions before writing."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=base.verification_commands,
        stop_conditions=("Stop if scope expands.",),
    )

    issues = module.validate_spec(spec)

    assert "at least 3 stop conditions are required" in issues
    assert "docs/handoff/deepseek_inbox.md ready inbox must include at least 3 stop conditions" in issues


def test_validate_spec_rejects_chained_verification_commands() -> None:
    """Task preparation must require standalone verification commands."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py && echo ok",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 2 must not contain shell control operators" in issues
    assert "verification commands must include: ruff" in issues


def test_validate_spec_rejects_wrapped_verification_commands() -> None:
    """Task preparation rejects verification commands hidden behind shell wrappers."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "powershell -Command python -m pytest tests/example.py -q",
            "cmd /c python -m ruff check src/example.py tests/example.py",
            "bash -lc git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 1 must start with a direct verification command" in issues
    assert "verification command 2 must start with a direct verification command" in issues
    assert "verification command 3 must start with a direct verification command" in issues
    assert "verification commands must include: pytest" in issues
    assert "verification commands must include: ruff" in issues
    assert "verification commands must include: git diff --check" in issues


def test_validate_spec_rejects_commented_verification_commands() -> None:
    """Task preparation rejects verification commands with inline comments."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check tests/example.py # src/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 2 must not contain shell control operators" in issues
    assert "verification commands must include: ruff" in issues


def test_validate_spec_rejects_redirected_verification_commands() -> None:
    """Task preparation rejects verification commands with redirection."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q > result.txt",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 1 must not contain shell control operators" in issues
    assert "verification commands must include: pytest" in issues


def test_validate_spec_rejects_shell_command_substitution() -> None:
    """Task preparation rejects verification commands with shell command substitution."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q $(python -c print(1))",
            "python -m ruff check src/example.py tests/example.py `python -c print(1)`",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 1 must not contain shell control operators" in issues
    assert "verification command 2 must not contain shell control operators" in issues
    assert "verification commands must include: pytest" in issues
    assert "verification commands must include: ruff" in issues


def test_validate_spec_rejects_shell_variable_expansion() -> None:
    """Task preparation rejects verification commands with shell variable expansion."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q $env:PYTEST_ADDOPTS",
            "python -m ruff check src/example.py tests/example.py ${RUFF_FLAGS}",
            "git diff --check -- src/example.py tests/example.py %DIFF_PATHS%",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 1 must not contain shell control operators" in issues
    assert "verification command 2 must not contain shell control operators" in issues
    assert "verification command 3 must not contain shell control operators" in issues
    assert "verification commands must include: pytest" in issues
    assert "verification commands must include: ruff" in issues
    assert "verification commands must include: git diff --check" in issues


def test_validate_spec_rejects_response_file_verification_arguments() -> None:
    """Task preparation rejects verification commands with hidden argument files."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q @pytest.args",
            "python -m ruff check src/example.py tests/example.py @ruff.args",
            "git diff --check -- src/example.py tests/example.py @diff.args",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 1 must not contain response-file arguments" in issues
    assert "verification command 2 must not contain response-file arguments" in issues
    assert "verification command 3 must not contain response-file arguments" in issues
    assert "verification commands must include: pytest" in issues
    assert "verification commands must include: ruff" in issues
    assert "verification commands must include: git diff --check" in issues


def test_validate_spec_rejects_unsafe_verification_flags() -> None:
    """Task preparation rejects verification commands that avoid real checks."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q -khappy_path",
            "python -m pytest tests/example.py -q -mslow",
            "python -m ruff check src/example.py tests/example.py --ignore=tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 1 must not contain unsafe verification flags" in issues
    assert "verification command 2 must not contain unsafe verification flags" in issues
    assert "verification command 3 must not contain unsafe verification flags" in issues
    assert "verification commands must include: pytest" in issues
    assert "verification commands must include: ruff" in issues


def test_validate_spec_rejects_no_run_or_mutating_verification_flags() -> None:
    """Task preparation rejects commands that enumerate or mutate instead of verifying."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q --co",
            "python -m pytest tests/example.py --setup-only",
            "python -m ruff check src/example.py tests/example.py --fix-only",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 1 must not contain unsafe verification flags" in issues
    assert "verification command 2 must not contain unsafe verification flags" in issues
    assert "verification command 3 must not contain unsafe verification flags" in issues
    assert "verification commands must include: pytest" in issues
    assert "verification commands must include: ruff" in issues


def test_validate_spec_rejects_rerun_only_or_early_stop_verification_flags() -> None:
    """Task preparation rejects commands that rerun subsets or stop early."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q --lf",
            "python -m pytest tests/example.py --maxfail=1",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 1 must not contain unsafe verification flags" in issues
    assert "verification command 2 must not contain unsafe verification flags" in issues
    assert "verification commands must include: pytest" in issues


def test_validate_spec_rejects_rule_selection_or_config_override_verification_flags() -> None:
    """Task preparation rejects ruff commands that override lint policy."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py --select F401",
            "python -m ruff check src/example.py tests/example.py --lint.ignore E501",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 2 must not contain unsafe verification flags" in issues
    assert "verification command 3 must not contain unsafe verification flags" in issues
    assert "verification commands must include: ruff" in issues


def test_validate_spec_rejects_pytest_config_or_import_override_verification_flags() -> None:
    """Task preparation rejects pytest commands that override config or import scope."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q --override-ini addopts=",
            "python -m pytest tests/example.py --pyargs",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 1 must not contain unsafe verification flags" in issues
    assert "verification command 2 must not contain unsafe verification flags" in issues
    assert "verification commands must include: pytest" in issues


def test_validate_spec_rejects_pytest_node_selection_verification_targets() -> None:
    """Task preparation rejects pytest commands narrowed to individual test nodes."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py::test_happy_path -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 1 must not contain unsafe verification flags" in issues
    assert "verification commands must include: pytest" in issues


def test_validate_spec_rejects_mutating_verification_flags() -> None:
    """Task preparation rejects verification commands that mutate files."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py --fix",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 2 must not contain unsafe verification flags" in issues
    assert "verification commands must include: ruff" in issues


def test_validate_spec_rejects_unsafe_scope_paths() -> None:
    """Task preparation rejects unsafe or contradictory file scopes."""

    spec = module.DeepSeekTaskSpec(
        message_id="codex-task-1",
        task="TASK_1",
        objective="Add one deterministic example behavior.",
        allowed_files=(
            "/tmp/example.py",
            "../outside.py",
            "src`bad.py",
            "src/injected.py\n## Forbidden Files",
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
            "src/example.py",
            "src/example.py",
        ),
        forbidden_files=(
            "src",
            "private/*",
            "private/generated#note.py",
            "private/generated file.py",
            "node_modules/pkg/index.js",
            "TBD",
        ),
        requirements=(
            "Preserve public interfaces.",
            "Add focused tests.",
            "Keep error paths visible.",
        ),
        acceptance_criteria=(
            "Happy path verified.",
            "Error path verified.",
            "Scope verified.",
        ),
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert any("unsafe allowed path: /tmp/example.py" in issue for issue in issues)
    assert any("unsafe allowed path: ../outside.py" in issue for issue in issues)
    assert any("unsafe allowed path: src`bad.py" in issue for issue in issues)
    assert any("unsafe allowed path: src/injected.py\\n## Forbidden Files" in issue for issue in issues)
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
    assert any("empty forbidden path stand-in: TBD" in issue for issue in issues)
    assert any("duplicate allowed path: src/example.py" in issue for issue in issues)
    assert any("overlapping allowed and forbidden scope: src/example.py vs src" in issue for issue in issues)


def test_validate_spec_rejects_overlapping_scope_entries_in_same_list() -> None:
    """Task preparation rejects ambiguous scope lists before assignment."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=("src/example_pkg", "src/example_pkg/module.py"),
        forbidden_files=("private", "private/generated"),
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example_pkg src/example_pkg/module.py",
            "git diff --check -- src/example_pkg src/example_pkg/module.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert (
        "docs/handoff/deepseek_inbox.md ready inbox has overlapping allowed scope: "
        "src/example_pkg vs src/example_pkg/module.py"
    ) in issues
    assert (
        "docs/handoff/deepseek_inbox.md ready inbox has overlapping forbidden scope: "
        "private vs private/generated"
    ) in issues


def test_validate_spec_rejects_handoff_control_allowed_scope() -> None:
    """Task preparation rejects worker scope over handoff control files."""

    spec = module.DeepSeekTaskSpec(
        message_id="codex-task-1",
        task="TASK_1",
        objective="Add one deterministic example behavior.",
        allowed_files=("docs/handoff/deepseek_inbox.md", "tests/example.py"),
        forbidden_files=("src/other.py",),
        requirements=(
            "Preserve public interfaces.",
            "Add focused tests.",
            "Keep error paths visible.",
        ),
        acceptance_criteria=(
            "Happy path verified.",
            "Error path verified.",
            "Scope verified.",
        ),
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert any("handoff control file: docs/handoff/deepseek_inbox.md" in issue for issue in issues)


def test_validate_spec_rejects_workflow_control_allowed_scope() -> None:
    """Task preparation rejects worker scope over workflow governance files."""

    spec = module.DeepSeekTaskSpec(
        message_id="codex-task-1",
        task="TASK_1",
        objective="Add one deterministic example behavior.",
        allowed_files=(
            "progress.md",
            "test_plan.md",
            "docs/handoff/deepseek_task_template.md",
            "utils/validate_handoff_docs.py",
        ),
        forbidden_files=("src/other.py",),
        requirements=(
            "Preserve public interfaces.",
            "Add focused tests.",
            "Keep error paths visible.",
        ),
        acceptance_criteria=(
            "Happy path verified.",
            "Error path verified.",
            "Scope verified.",
        ),
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check progress.md test_plan.md docs/handoff/deepseek_task_template.md utils/validate_handoff_docs.py",
            "git diff --check -- progress.md test_plan.md docs/handoff/deepseek_task_template.md utils/validate_handoff_docs.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert any("workflow control file: progress.md" in issue for issue in issues)
    assert any("workflow control file: test_plan.md" in issue for issue in issues)
    assert any("workflow control file: docs/handoff/deepseek_task_template.md" in issue for issue in issues)
    assert any("workflow control file: utils/validate_handoff_docs.py" in issue for issue in issues)


def test_validate_spec_rejects_unsafe_required_reading_paths() -> None:
    """Task preparation rejects unsafe or duplicate required-reading paths."""

    spec = module.DeepSeekTaskSpec(
        message_id="codex-task-1",
        task="TASK_1",
        objective="Add one deterministic example behavior.",
        allowed_files=("src/example.py", "tests/example.py"),
        forbidden_files=("src/other.py",),
        requirements=(
            "Preserve public interfaces.",
            "Add focused tests.",
            "Keep error paths visible.",
        ),
        acceptance_criteria=(
            "Happy path verified.",
            "Error path verified.",
            "Scope verified.",
        ),
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
        required_reading=(
            *module.DEFAULT_REQUIRED_READING,
            "../secret.md",
            "docs/with space.md",
            ".venv/pyvenv.cfg",
            "N/A",
            "spec.md",
        ),
    )

    issues = module.validate_spec(spec)

    assert "unsafe required reading path: ../secret.md" in issues
    assert "unsafe required reading path: docs/with space.md" in issues
    assert "unsafe required reading path: .venv/pyvenv.cfg" in issues
    assert "empty required reading path stand-in: N/A" in issues
    assert "duplicate required reading path: spec.md" in issues


def test_validate_spec_rejects_control_file_required_reading_paths() -> None:
    """Task preparation keeps mutable handoff controls out of required reading."""

    spec = module.DeepSeekTaskSpec(
        message_id="codex-task-1",
        task="TASK_1",
        objective="Add one deterministic example behavior.",
        allowed_files=("src/example.py", "tests/example.py"),
        forbidden_files=("src/other.py",),
        requirements=(
            "Preserve public interfaces.",
            "Add focused tests.",
            "Keep error paths visible.",
        ),
        acceptance_criteria=(
            "Happy path verified.",
            "Error path verified.",
            "Scope verified.",
        ),
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
        required_reading=(
            *module.DEFAULT_REQUIRED_READING,
            "docs/handoff/deepseek_outbox.md",
            "DEEPSEEK_INBOX.md",
            "CODEX_REVIEW.md",
        ),
    )

    issues = module.validate_spec(spec)

    assert "required reading path must not list handoff control file: docs/handoff/deepseek_outbox.md" in issues
    assert "required reading path must not list handoff control file: DEEPSEEK_INBOX.md" in issues
    assert "required reading path must not list handoff control file: CODEX_REVIEW.md" in issues


def test_validate_spec_rejects_multiline_verification_commands() -> None:
    """Task preparation rejects verification commands that can break the rendered block."""

    spec = module.DeepSeekTaskSpec(
        message_id="codex-task-1",
        task="TASK_1",
        objective="Add one deterministic example behavior.",
        allowed_files=("src/example.py", "tests/example.py"),
        forbidden_files=("src/other.py",),
        requirements=(
            "Preserve public interfaces.",
            "Add focused tests.",
            "Keep error paths visible.",
        ),
        acceptance_criteria=(
            "Happy path verified.",
            "Error path verified.",
            "Scope verified.",
        ),
        verification_commands=(
            "python -m pytest tests/example.py -q\n```",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "verification command 1 must be single line" in issues
    assert "verification command 1 must not contain markdown fences" in issues


def test_validate_spec_rejects_multiline_task_text_fields() -> None:
    """Task preparation rejects narrative fields that can inject markdown sections."""

    spec = module.DeepSeekTaskSpec(
        message_id="codex-task-1",
        task="TASK_1",
        objective="Add one deterministic example behavior.\n## Forbidden Files",
        allowed_files=("src/example.py", "tests/example.py"),
        forbidden_files=("src/other.py",),
        requirements=(
            "Preserve public interfaces.\n- extra item",
            "Add focused tests.",
            "Keep error paths visible.",
        ),
        acceptance_criteria=(
            "Happy path verified.",
            "Error path verified. ```",
            "Scope verified.",
        ),
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
        stop_conditions=(*module.DEFAULT_STOP_CONDITIONS, "Stop on uncertainty.\n## Required Outbox"),
    )

    issues = module.validate_spec(spec)

    assert "objective 1 must be single line" in issues
    assert "requirement 1 must be single line" in issues
    assert "acceptance criterion 2 must not contain markdown fences" in issues
    assert "stop condition 4 must be single line" in issues


def test_validate_spec_rejects_empty_stand_in_task_text_fields() -> None:
    """Task preparation rejects stand-ins where concrete task text is required."""

    spec = module.DeepSeekTaskSpec(
        message_id="unknown",
        task="TBD",
        objective="N/A",
        allowed_files=("src/example.py", "tests/example.py"),
        forbidden_files=("src/other.py",),
        requirements=(
            "None",
            "Add focused tests.",
            "Keep error paths visible.",
        ),
        acceptance_criteria=(
            "unknown",
            "Error path verified.",
            "Scope verified.",
        ),
        verification_commands=(
            "pending",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
        stop_conditions=(
            "TBD",
            "Stop if implementation needs files outside Allowed Files.",
            "Stop if tests can only succeed by weakening assertions.",
        ),
    )

    issues = module.validate_spec(spec)

    assert "message id 1 must not be empty stand-in: unknown" in issues
    assert "task 1 must not be empty stand-in: TBD" in issues
    assert "objective 1 must not be empty stand-in: N/A" in issues
    assert "requirement 1 must not be empty stand-in: None" in issues
    assert "acceptance criterion 1 must not be empty stand-in: unknown" in issues
    assert "verification command 1 must not be empty stand-in: pending" in issues
    assert "stop condition 1 must not be empty stand-in: TBD" in issues


def test_validate_spec_rejects_multiline_metadata_fields() -> None:
    """Task preparation rejects metadata fields that can inject top-level values."""

    spec = module.DeepSeekTaskSpec(
        message_id="codex-task-1\nStatus: READY_FOR_CODEX_REVIEW",
        task="TASK_1\nMessage ID: other",
        objective="Add one deterministic example behavior.",
        allowed_files=("src/example.py", "tests/example.py"),
        forbidden_files=("src/other.py",),
        requirements=(
            "Preserve public interfaces.",
            "Add focused tests.",
            "Keep error paths visible.",
        ),
        acceptance_criteria=(
            "Happy path verified.",
            "Error path verified.",
            "Scope verified.",
        ),
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )

    issues = module.validate_spec(spec)

    assert "message id 1 must be single line" in issues
    assert "task 1 must be single line" in issues


def test_render_waiting_outbox_uses_task_metadata() -> None:
    """Waiting outbox text keeps the assigned task identity."""

    text = module.render_waiting_outbox(_valid_spec())

    assert "Status: WAITING_FOR_DEEPSEEK" in text
    assert "Message ID: codex-task-1" in text
    assert "Task: TASK_1" in text
    assert "READY_FOR_CODEX_REVIEW" not in text


def test_render_waiting_outbox_rejects_invalid_spec() -> None:
    """Waiting outbox rendering must not expose invalid task metadata."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task="unassigned",
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=base.verification_commands,
    )

    with pytest.raises(ValueError) as exc_info:
        module.render_waiting_outbox(spec)

    assert "task spec validation failed" in str(exc_info.value)
    assert "task must be concrete" in str(exc_info.value)


def test_main_dry_run_prints_task_without_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run mode prints the task and leaves the inbox untouched."""

    result = module.main([*(_valid_args(tmp_path)), "--dry-run"])

    captured = capsys.readouterr()
    assert result == 0
    assert "Status: READY_FOR_DEEPSEEK" in captured.out
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()
    assert not (tmp_path / validate_handoff_docs.OUTBOX_PATH).exists()


def test_main_dry_run_includes_git_worktree_baseline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run mode records current git worktree paths in the rendered task."""

    _write(tmp_path / "src" / "example.py", "VALUE = 1\n")
    _write(tmp_path / "docs" / "notes.md", "before\n")
    _init_git_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    _write(tmp_path / "docs" / "notes.md", "after\n")

    result = module.main([*(_valid_args(tmp_path)), "--dry-run"])

    captured = capsys.readouterr()
    assert result == 0
    assert "## Worktree Baseline" in captured.out
    assert "- `docs/notes.md`" in captured.out


def test_main_dry_run_rejects_allowed_scope_git_worktree_baseline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run mode rejects dirty baseline paths that overlap assigned files."""

    _write(tmp_path / "src" / "example.py", "VALUE = 1\n")
    _init_git_repo(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    _write(tmp_path / "src" / "example.py", "VALUE = 2\n")

    result = module.main([*(_valid_args(tmp_path)), "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task validation failed" in captured.err
    assert "worktree baseline path must not overlap allowed file: src/example.py vs src/example.py" in captured.err
    assert captured.out == ""


def test_main_dry_run_rejects_unsafe_git_worktree_baseline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry-run mode reports invalid git baseline paths without writing files."""

    monkeypatch.setattr(module, "_load_worktree_baseline", lambda root: ("src`bad.py",))

    result = module.main([*(_valid_args(tmp_path)), "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task validation failed" in captured.err
    assert "unsafe worktree baseline path: src`bad.py" in captured.err
    assert captured.out == ""


def test_main_dry_run_can_read_spec_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run mode can render a task from a JSON spec file."""

    spec_path = tmp_path / "task-spec.json"
    spec_path.write_text(json.dumps(_valid_spec_document()), encoding="utf-8")

    result = module.main(["--root", str(tmp_path), "--spec-file", "task-spec.json", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 0
    assert "Status: READY_FOR_DEEPSEEK" in captured.out
    assert "Task: TASK_1" in captured.out
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def test_main_rejects_invalid_spec_file_shape(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file input must use the expected field types."""

    spec_path = tmp_path / "task-spec.json"
    spec_path.write_text(json.dumps({"message_id": 123}), encoding="utf-8")

    result = module.main(["--root", str(tmp_path), "--spec-file", "task-spec.json", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task spec invalid" in captured.err
    assert "spec field must be a string: message_id" in captured.err


def test_main_reports_invalid_spec_file_list_item_index(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file list type errors should identify the bad item."""

    spec_path = tmp_path / "task-spec.json"
    data = _valid_spec_document()
    data["allowed_files"] = ["src/example.py", 123]
    spec_path.write_text(json.dumps(data), encoding="utf-8")

    result = module.main(["--root", str(tmp_path), "--spec-file", "task-spec.json", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task spec invalid" in captured.err
    assert "spec field item must be a string: allowed_files[2]" in captured.err
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def test_main_rejects_parent_spec_file_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file path must stay inside the repository root."""

    result = module.main(["--root", str(tmp_path), "--spec-file", "../task-spec.json", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task spec invalid" in captured.err
    assert "unsafe spec file path" in captured.err


def test_main_rejects_url_spec_file_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file path rejects URL-shaped input before reading."""

    result = module.main(["--root", str(tmp_path), "--spec-file", "https://example.com/task.json", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task spec invalid" in captured.err
    assert "unsafe spec file path" in captured.err


def test_main_rejects_directory_spec_file_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file input must point at a file, not a directory."""

    (tmp_path / "docs").mkdir()

    result = module.main(["--root", str(tmp_path), "--spec-file", "docs", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task spec invalid" in captured.err
    assert "spec file must be a readable file" in captured.err
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def test_main_rejects_non_utf8_spec_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file input must be UTF-8 JSON text."""

    spec_path = tmp_path / "task-spec.json"
    spec_path.write_bytes(b"{\xff")

    result = module.main(["--root", str(tmp_path), "--spec-file", "task-spec.json", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task spec invalid" in captured.err
    assert "spec file must be UTF-8 JSON text" in captured.err
    assert "'utf-8' codec" not in captured.err
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def test_main_rejects_unknown_spec_file_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file input should fail on misspelled or unsupported fields."""

    spec_path = tmp_path / "task-spec.json"
    data = _valid_spec_document()
    data["allowed_file"] = ["src/wrong.py"]
    spec_path.write_text(json.dumps(data), encoding="utf-8")

    result = module.main(["--root", str(tmp_path), "--spec-file", "task-spec.json", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task spec invalid" in captured.err
    assert "spec file contains unknown fields: allowed_file" in captured.err


def test_main_rejects_url_scope_from_spec_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file input rejects URL-shaped file scopes before writing."""

    spec_path = tmp_path / "task-spec.json"
    data = _valid_spec_document()
    data["allowed_files"] = ["https://example.com/file.py"]
    spec_path.write_text(json.dumps(data), encoding="utf-8")

    result = module.main(["--root", str(tmp_path), "--spec-file", "task-spec.json", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task validation failed" in captured.err
    assert "unsafe allowed path: https://example.com/file.py" in captured.err
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def test_main_rejects_url_required_reading_from_spec_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file input rejects URL-shaped required-reading paths before writing."""

    spec_path = tmp_path / "task-spec.json"
    data = _valid_spec_document()
    data["required_reading"] = ["https://example.com/rules.md"]
    spec_path.write_text(json.dumps(data), encoding="utf-8")

    result = module.main(["--root", str(tmp_path), "--spec-file", "task-spec.json", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task validation failed" in captured.err
    assert "unsafe required reading path: https://example.com/rules.md" in captured.err
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def test_main_rejects_control_file_required_reading_from_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI input rejects handoff control files before writing."""

    result = module.main(
        [
            *(_valid_args(tmp_path)),
            "--required-reading",
            "docs/handoff/deepseek_outbox.md",
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task validation failed" in captured.err
    assert "required reading path must not list handoff control file: docs/handoff/deepseek_outbox.md" in captured.err
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def test_main_rejects_control_file_required_reading_from_spec_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file input rejects root shortcut required-reading paths before writing."""

    spec_path = tmp_path / "task-spec.json"
    data = _valid_spec_document()
    data["required_reading"] = ["DEEPSEEK_INBOX.md"]
    spec_path.write_text(json.dumps(data), encoding="utf-8")

    result = module.main(["--root", str(tmp_path), "--spec-file", "task-spec.json", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task validation failed" in captured.err
    assert "required reading path must not list handoff control file: DEEPSEEK_INBOX.md" in captured.err
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def test_main_rejects_empty_verification_command_from_spec_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file input rejects empty verification commands before writing."""

    spec_path = tmp_path / "task-spec.json"
    data = _valid_spec_document()
    verification_commands = cast(list[str], data["verification_commands"])
    data["verification_commands"] = ["", *verification_commands]
    spec_path.write_text(json.dumps(data), encoding="utf-8")

    result = module.main(["--root", str(tmp_path), "--spec-file", "task-spec.json", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task validation failed" in captured.err
    assert "verification command 1 must not be empty" in captured.err
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def test_main_rejects_multiline_requirement_from_spec_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file input rejects multiline requirement text before writing."""

    spec_path = tmp_path / "task-spec.json"
    data = _valid_spec_document()
    data["requirements"] = [
        "Preserve public interfaces.\n## Forbidden Files",
        "Add focused tests.",
        "Keep error paths visible.",
    ]
    spec_path.write_text(json.dumps(data), encoding="utf-8")

    result = module.main(["--root", str(tmp_path), "--spec-file", "task-spec.json", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task validation failed" in captured.err
    assert "requirement 1 must be single line" in captured.err
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def test_main_rejects_multiline_message_id_from_spec_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file input rejects multiline message ids before writing."""

    spec_path = tmp_path / "task-spec.json"
    data = _valid_spec_document()
    data["message_id"] = "codex-task-1\nStatus: READY_FOR_CODEX_REVIEW"
    spec_path.write_text(json.dumps(data), encoding="utf-8")

    result = module.main(["--root", str(tmp_path), "--spec-file", "task-spec.json", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task validation failed" in captured.err
    assert "message id 1 must be single line" in captured.err
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def test_main_rejects_parent_scope_from_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI input rejects parent-directory file scopes before writing."""

    result = module.main([*(_valid_args(tmp_path)), "--allowed-file", "../outside.py", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task validation failed" in captured.err
    assert "unsafe allowed path: ../outside.py" in captured.err
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def test_main_writes_canonical_inbox(tmp_path: Path) -> None:
    """Write mode updates the canonical DeepSeek inbox path."""

    result = module.main(_valid_args(tmp_path))

    inbox_path = tmp_path / validate_handoff_docs.INBOX_PATH
    assert result == 0
    assert inbox_path.is_file()
    assert validate_handoff_docs._validate_ready_inbox(inbox_path.read_text(encoding="utf-8")) == []


def test_write_task_rejects_invalid_spec_before_writing(tmp_path: Path) -> None:
    """Programmatic writes must use the same task-spec gate as the CLI."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id=base.message_id,
        task=base.task,
        objective=base.objective,
        allowed_files=(),
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=base.verification_commands,
    )

    with pytest.raises(ValueError) as exc_info:
        module.write_task(tmp_path, spec, worktree_baseline=())

    assert "task spec validation failed" in str(exc_info.value)
    assert "at least one allowed file is required" in str(exc_info.value)
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def test_write_waiting_outbox_rejects_invalid_spec_before_writing(tmp_path: Path) -> None:
    """Programmatic waiting outbox writes must not publish invalid task metadata."""

    base = _valid_spec()
    spec = module.DeepSeekTaskSpec(
        message_id="unassigned",
        task=base.task,
        objective=base.objective,
        allowed_files=base.allowed_files,
        forbidden_files=base.forbidden_files,
        requirements=base.requirements,
        acceptance_criteria=base.acceptance_criteria,
        verification_commands=base.verification_commands,
    )

    with pytest.raises(ValueError) as exc_info:
        module.write_waiting_outbox(tmp_path, spec)

    assert "task spec validation failed" in str(exc_info.value)
    assert "message id must be concrete" in str(exc_info.value)
    assert not (tmp_path / validate_handoff_docs.OUTBOX_PATH).exists()


def test_main_can_reset_outbox_when_writing_task(tmp_path: Path) -> None:
    """The reset flag clears stale review-ready outbox state."""

    result = module.main([*(_valid_args(tmp_path)), "--reset-outbox"])

    outbox_path = tmp_path / validate_handoff_docs.OUTBOX_PATH
    assert result == 0
    assert outbox_path.is_file()
    outbox_text = outbox_path.read_text(encoding="utf-8")
    assert "Status: WAITING_FOR_DEEPSEEK" in outbox_text
    assert "READY_FOR_CODEX_REVIEW" not in outbox_text


def test_validate_repository_rejects_unreset_outbox(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Full repository validation catches a missing outbox reset."""

    _write_minimal_repository_docs(tmp_path)

    result = module.main([*(_valid_args(tmp_path)), "--validate-repository"])

    captured = capsys.readouterr()
    assert result == 1
    assert "repository handoff validation failed after write" in captured.err
    assert "restored previous handoff files" in captured.err
    assert "ready task requires docs/handoff/deepseek_outbox.md Status" in captured.err
    inbox_text = (tmp_path / validate_handoff_docs.INBOX_PATH).read_text(encoding="utf-8")
    assert "Status: WAITING_FOR_TASK" in inbox_text


def test_validate_repository_accepts_reset_outbox(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Full repository validation succeeds when the assignment lifecycle is reset."""

    _write_minimal_repository_docs(tmp_path)

    result = module.main([*(_valid_args(tmp_path)), "--reset-outbox", "--validate-repository"])

    captured = capsys.readouterr()
    assert result == 0
    assert "repository handoff validation ok" in captured.out


def test_validate_repository_rejects_non_file_required_reading(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Repository validation rejects assigned readings that cannot be opened."""

    _write_minimal_repository_docs(tmp_path)

    result = module.main(
        [
            *(_valid_args(tmp_path)),
            "--required-reading",
            "docs/missing.md",
            "--reset-outbox",
            "--validate-repository",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "repository handoff validation failed after write" in captured.err
    assert "restored previous handoff files" in captured.err
    assert "ready inbox required reading before editing path must point to a file: docs/missing.md" in captured.err
    assert "ready inbox required reading path must point to a file: docs/missing.md" in captured.err
    inbox_text = (tmp_path / validate_handoff_docs.INBOX_PATH).read_text(encoding="utf-8")
    outbox_text = (tmp_path / validate_handoff_docs.OUTBOX_PATH).read_text(encoding="utf-8")
    assert "Status: WAITING_FOR_TASK" in inbox_text
    assert "Status: WAITING_FOR_TASK" in outbox_text


def test_validate_repository_rejects_non_file_required_reading_from_spec_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec-file assignments inherit repository required-reading file checks."""

    _write_minimal_repository_docs(tmp_path)
    spec_path = tmp_path / "task-spec.json"
    data = _valid_spec_document()
    data["required_reading"] = ["docs/missing.md"]
    spec_path.write_text(json.dumps(data), encoding="utf-8")

    result = module.main(
        [
            "--root",
            str(tmp_path),
            "--spec-file",
            "task-spec.json",
            "--reset-outbox",
            "--validate-repository",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "repository handoff validation failed after write" in captured.err
    assert "restored previous handoff files" in captured.err
    assert "ready inbox required reading path must point to a file: docs/missing.md" in captured.err
    inbox_text = (tmp_path / validate_handoff_docs.INBOX_PATH).read_text(encoding="utf-8")
    outbox_text = (tmp_path / validate_handoff_docs.OUTBOX_PATH).read_text(encoding="utf-8")
    assert "Status: WAITING_FOR_TASK" in inbox_text
    assert "Status: WAITING_FOR_TASK" in outbox_text


def test_main_returns_nonzero_for_invalid_task(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI validation failures are reported before writing."""

    result = module.main(
        [
            "--root",
            str(tmp_path),
            "--message-id",
            "unassigned",
            "--task",
            "TASK_1",
            "--objective",
            "Do the work.",
            "--allowed-file",
            "src/example.py",
            "--forbidden-file",
            "src/forbidden.py",
            "--acceptance",
            "Only one criterion.",
            "--verification-command",
            "python -m pytest tests/example.py -q",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "deepseek task validation failed" in captured.err
    assert not (tmp_path / validate_handoff_docs.INBOX_PATH).exists()


def _valid_spec() -> module.DeepSeekTaskSpec:
    return module.DeepSeekTaskSpec(
        message_id="codex-task-1",
        task="TASK_1",
        objective="Add one deterministic example behavior.",
        allowed_files=("src/example.py", "tests/example.py"),
        forbidden_files=("src/other.py",),
        requirements=(
            "Preserve public interfaces.",
            "Add focused tests.",
            "Keep error paths visible.",
        ),
        acceptance_criteria=(
            "Happy path verified.",
            "Error path verified.",
            "Scope verified.",
        ),
        verification_commands=(
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ),
    )


def _valid_args(root: Path) -> list[str]:
    return [
        "--root",
        str(root),
        "--message-id",
        "codex-task-1",
        "--task",
        "TASK_1",
        "--objective",
        "Add one deterministic example behavior.",
        "--allowed-file",
        "src/example.py",
        "--allowed-file",
        "tests/example.py",
        "--forbidden-file",
        "src/other.py",
        "--requirement",
        "Preserve public interfaces.",
        "--requirement",
        "Add focused tests.",
        "--requirement",
        "Keep error paths visible.",
        "--acceptance",
        "Happy path verified.",
        "--acceptance",
        "Error path verified.",
        "--acceptance",
        "Scope verified.",
        "--verification-command",
        "python -m pytest tests/example.py -q",
        "--verification-command",
        "python -m ruff check src/example.py tests/example.py",
        "--verification-command",
        "git diff --check -- src/example.py tests/example.py",
    ]


def _valid_spec_document() -> dict[str, object]:
    return {
        "message_id": "codex-task-1",
        "task": "TASK_1",
        "objective": "Add one deterministic example behavior.",
        "allowed_files": ["src/example.py", "tests/example.py"],
        "forbidden_files": ["src/other.py"],
        "requirements": [
            "Preserve public interfaces.",
            "Add focused tests.",
            "Keep error paths visible.",
        ],
        "acceptance_criteria": [
            "Happy path verified.",
            "Error path verified.",
            "Scope verified.",
        ],
        "verification_commands": [
            "python -m pytest tests/example.py -q",
            "python -m ruff check src/example.py tests/example.py",
            "git diff --check -- src/example.py tests/example.py",
        ],
    }


def _write_minimal_repository_docs(root: Path) -> None:
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
    _write(handoff_dir / "deepseek_inbox.md", _waiting_inbox())
    _write(handoff_dir / "deepseek_outbox.md", _waiting_outbox())
    _write(handoff_dir / "codex_review_checklist.md", _codex_checklist())
    _write(handoff_dir / "dual_model_development_workflow.md", _workflow())
    _write(handoff_dir / "cross_platform_continuation.md", _cross_platform_continuation())
    _write(handoff_dir / "deepseek_task_template.md", _task_template())
    _write(handoff_dir / "deepseek_task_spec_schema.md", _task_spec_schema())
    _write(handoff_dir / "deepseek_assignment_examples.md", _assignment_examples())
    _write(handoff_dir / "codex_review_template.md", _review_template())


def _waiting_inbox() -> str:
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
            "- Run scoped scan.",
            "## Required Outbox Evidence",
            "- READY_FOR_CODEX_REVIEW",
        ]
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
            "- Keep tasks small.",
            "## Required DeepSeek Task Template",
            "- Use the template.",
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
            "- every assigned verification command result includes a clean marker such as `exited 0`",
            "- clean result markers inside the backticked command text do not count as verification evidence",
            "- verification evidence must not say dry-run, manual-only, simulated, synthetic, or fabricated",
            "- checked `- [x] ...` evidence items",
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


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
