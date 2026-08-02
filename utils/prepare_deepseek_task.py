"""Prepare a bounded READY_FOR_DEEPSEEK inbox task."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from utils import validate_handoff_docs

DEFAULT_REQUIRED_READING: tuple[str, ...] = (
    "AGENTS.md",
    "spec.md",
    "architecture.md",
    "task.md",
    "docs/handoff/deepseek_inbox.md",
)
DEFAULT_STOP_CONDITIONS: tuple[str, ...] = (
    "Stop if an interface, schema, or expected behavior is missing.",
    "Stop if implementation needs files outside Allowed Files.",
    "Stop if tests can only succeed by weakening assertions.",
)
DEFAULT_INPUT_CONTRACTS: tuple[str, ...] = (
    "Preserve existing function, CLI, schema, and file inputs for the allowed files unless a requirement explicitly narrows them.",
)
DEFAULT_OUTPUT_CONTRACTS: tuple[str, ...] = (
    "Preserve existing return values, artifacts, logs, schemas, and user-visible behavior unless a requirement explicitly narrows them.",
)
SPEC_FILE_FIELDS: frozenset[str] = frozenset(
    {
        "message_id",
        "task",
        "objective",
        "input_contracts",
        "output_contracts",
        "allowed_files",
        "forbidden_files",
        "requirements",
        "acceptance_criteria",
        "verification_commands",
        "required_reading",
        "stop_conditions",
    }
)


@dataclass(frozen=True)
class DeepSeekTaskSpec:
    """Structured input for a DeepSeek implementation task."""

    message_id: str
    task: str
    objective: str
    allowed_files: tuple[str, ...]
    forbidden_files: tuple[str, ...]
    requirements: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    verification_commands: tuple[str, ...]
    input_contracts: tuple[str, ...] = DEFAULT_INPUT_CONTRACTS
    output_contracts: tuple[str, ...] = DEFAULT_OUTPUT_CONTRACTS
    required_reading: tuple[str, ...] = DEFAULT_REQUIRED_READING
    stop_conditions: tuple[str, ...] = DEFAULT_STOP_CONDITIONS


def render_task(spec: DeepSeekTaskSpec, *, worktree_baseline: Sequence[str] = ()) -> str:
    """Render a DeepSeek task inbox from structured input."""

    baseline_paths = _normalize_worktree_baseline_values(worktree_baseline)
    baseline_scope_issues = _validate_worktree_baseline_scope(
        baseline_paths=baseline_paths,
        allowed_files=spec.allowed_files,
    )
    if baseline_scope_issues:
        raise ValueError("; ".join(baseline_scope_issues))
    lines = [
        "# DeepSeek Inbox",
        "",
        f"Status: {validate_handoff_docs.READY_FOR_DEEPSEEK}",
        f"Message ID: {spec.message_id}",
        f"Task: {spec.task}",
        "",
        "CODEX_GATE: PASS",
        "",
        "## Operating Role",
        "",
        "- Implement exactly one bounded task as the DeepSeek worker.",
        "- Stop after writing `docs/handoff/deepseek_outbox.md`.",
        "",
        "## Required Reading Before Editing",
        "",
        *[f"- `{item}`" for item in spec.required_reading],
        "",
        "## Current Task",
        "",
        f"- {spec.objective}",
        "",
        "## Global Implementation Rules",
        "",
        "- Modify only files listed under `## Allowed Files`.",
        "- Do not edit files listed under `## Forbidden Files`.",
        "- Do not delete, weaken, skip, or replace existing tests to make a task look complete.",
        "- Record exact verification commands and results in the outbox.",
        "",
        "## Objective",
        "",
        spec.objective,
        "",
        "## Input Contracts",
        "",
        *[f"- {item}" for item in spec.input_contracts],
        "",
        "## Output Contracts",
        "",
        *[f"- {item}" for item in spec.output_contracts],
        "",
        "## Required Reading",
        "",
        *[f"- `{item}`" for item in spec.required_reading],
        "",
        "## Allowed Files",
        "",
        *[f"- `{item}`" for item in spec.allowed_files],
        "",
        "## Forbidden Files",
        "",
        *[f"- `{item}`" for item in spec.forbidden_files],
        "",
        "## Worktree Baseline",
        "",
        *_render_worktree_baseline(baseline_paths),
        "Worktree baseline entries must not overlap allowed files.",
        "",
        "## Requirements",
        "",
        *[f"{index}. {item}" for index, item in enumerate(spec.requirements, start=1)],
        "",
        "## Acceptance Criteria",
        "",
        *[f"- [ ] {item}" for item in spec.acceptance_criteria],
        "",
        "## Verification Commands",
        "",
        "```powershell",
        *spec.verification_commands,
        "```",
        "",
        "Verification commands must mention each concrete allowed file as a path token.",
        "Verification commands must start with direct command families, not shell wrappers.",
        "Verification commands must not use shell redirection.",
        "Verification commands must not use command substitution such as `$(...)` or backticks.",
        "Verification commands must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "Verification commands must not include unsafe verification flags such as "
        "`--collect-only`, `--exit-zero`, `--fix`, or `--unsafe-fixes`.",
        "No-run or mutating verification flags such as `--co`, `--fixtures`, "
        "`--setup-only`, `--fix-only`, or `--add-noqa` are unsafe.",
        "Rerun-only or early-stop verification flags such as `--lf`, "
        "`--last-failed`, `-x`, `--exitfirst`, `--maxfail`, or `--stepwise` are unsafe.",
        "Rule-selection or config-override verification flags such as `--select`, "
        "`--extend-ignore`, `--lint.select`, `--config`, or `--isolated` are unsafe.",
        "Pytest config or import override flags such as `-o`, `--override-ini`, `--rootdir`, "
        "`--confcutdir`, `--import-mode`, or `--pyargs` are unsafe.",
        "Pytest node selection targets such as `tests/test_example.py::test_name` are unsafe.",
        "Filtering or exclusion verification flags such as `-k`, `-m`, `--deselect`, `--ignore`, or `--exclude` are unsafe.",
        "Attached short filter forms such as `-kslow` or `-mslow` are unsafe too.",
        "Git diff-check commands must mention every allowed file or directory scope as a path token.",
        "Git diff-check commands with pathspecs must use `--` before the path list.",
        "Verification commands must not use response-file or splatting arguments such as `@args.txt`.",
        "Path values must not use wildcards or glob metacharacters.",
        "Path values must not contain shell metacharacters such as hash signs, ampersands, semicolons, pipes, dollar signs, less-than or greater-than signs, or quotes.",
        "Path values must not use empty stand-ins such as None, N/A, TBD, or unknown.",
        "Path values must not contain embedded whitespace.",
        "Path values must not target VCS, dependency, or cache directories.",
        "Allowed files must not include workflow control files such as handoff docs, root task plans, gate utilities, or CI gates.",
        "Allowed files must not use broad top-level directory scopes such as `dayu`, `docs`, `src`, `tests`, `utils`, `.github`, or `workspace`.",
        "Allowed and forbidden files must not contain overlapping scope entries within the same list.",
        "",
        "## Anti-Placeholder Scan",
        "",
        "- Run a scoped scan over changed implementation and test files.",
        "```powershell",
        _render_anti_placeholder_scan_command(spec.allowed_files),
        "```",
        "- Report the exact command and result in the outbox.",
        "- Anti-Placeholder scan command must start with `rg` or `rg.exe`.",
        "- Anti-Placeholder scan command must include every configured scanner pattern.",
        "- Anti-Placeholder scan command must use `--` before the path list.",
        "- Anti-Placeholder scan command must not use shell variable expansion such as `$env:...`, `$NAME`, `${NAME}`, or `%NAME%`.",
        "- Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`.",
        "- Anti-Placeholder scan command must mention every allowed file as a path token.",
        "- Do not report empty stand-ins such as None, N/A, or no scan as completed scanner evidence.",
        "",
        "## Stop Conditions",
        "",
        *[f"- {item}" for item in spec.stop_conditions],
        "",
        "## Required Outbox",
        "",
        f"- `{validate_handoff_docs.READY_FOR_REVIEW}`",
        "- concrete summary with at least two bullet items",
        "- changed files",
        "- changed-file evidence must not list workflow control files",
        "- verification commands and exact results",
        "- every assigned verification command result includes a clean marker such as `exited 0`",
        "- checked acceptance criteria evidence",
        "- checked acceptance evidence must not say skipped, unverified, untested, pending, deferred, or not applicable",
        "- Anti-Placeholder scan command and clean result",
        "- Anti-Placeholder scan command must be exact and must not use shell control operators",
        "- Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`",
        "- Anti-Placeholder scan command must not include unresolved angle-bracket markers",
        "- Anti-Placeholder evidence must not say skipped, not executed, not scanned, or no scan",
        "- scope deviations",
        "- explicit None when no unresolved questions or blockers remain",
        "",
        "## Required Outbox Evidence",
        "",
        f"- `{validate_handoff_docs.READY_FOR_REVIEW}`",
        "- concrete summary with at least two bullet items",
        "- changed files",
        "- changed-file evidence must not list workflow control files",
        "- verification commands and exact results",
        "- every assigned verification command result includes a clean marker such as `exited 0`",
        "- checked acceptance criteria evidence",
        "- checked acceptance evidence must not say skipped, unverified, untested, pending, deferred, or not applicable",
        "- Anti-Placeholder scan command and clean result",
        "- Anti-Placeholder scan command must be exact and must not use shell control operators",
        "- Anti-Placeholder scan command must not use response-file or splatting arguments such as `@args.txt`",
        "- Anti-Placeholder scan command must not include unresolved angle-bracket markers",
        "- Anti-Placeholder evidence must not say skipped, not executed, not scanned, or no scan",
        "- scope deviations",
        "- explicit None when no unresolved questions or blockers remain",
        "",
    ]
    return "\n".join(lines)


def _render_worktree_baseline(paths: Sequence[str]) -> tuple[str, ...]:
    if not paths:
        return ("- None.",)
    return tuple(f"- `{path}`" for path in sorted(paths))


def _normalize_worktree_baseline_values(paths: Sequence[str]) -> tuple[str, ...]:
    issues: list[str] = []
    normalized_paths: list[str] = []
    seen: set[str] = set()

    for raw_path in paths:
        normalized_path = validate_handoff_docs._normalize_scope_path(raw_path)
        display_path = validate_handoff_docs._display_scope_path(raw_path)

        if not normalized_path:
            issues.append("worktree baseline path must not be empty")
            continue
        if validate_handoff_docs._is_unsafe_scope_path(raw_path=raw_path, normalized_path=normalized_path):
            issues.append(f"unsafe worktree baseline path: {display_path}")
        if normalized_path in seen:
            issues.append(f"duplicate worktree baseline path: {normalized_path}")
        seen.add(normalized_path)
        normalized_paths.append(normalized_path)

    if issues:
        raise ValueError("; ".join(issues))

    return tuple(normalized_paths)


def _render_anti_placeholder_scan_command(allowed_files: Sequence[str]) -> str:
    normalized_paths: list[str] = []
    for path in allowed_files:
        normalized_path = validate_handoff_docs._normalize_scope_path(path)
        if normalized_path:
            normalized_paths.append(normalized_path)
    pattern_args = " ".join(f'-e "{pattern}"' for pattern in validate_handoff_docs.ANTI_PLACEHOLDER_SCANNER_PATTERNS)
    path_args = " ".join(normalized_paths)
    return f"rg -n --pcre2 {pattern_args} -- {path_args}"


def _validate_worktree_baseline_scope(*, baseline_paths: Sequence[str], allowed_files: Sequence[str]) -> list[str]:
    """Reject baseline paths that could mask assigned-file changes."""

    normalized_allowed_paths = [validate_handoff_docs._normalize_scope_path(path) for path in allowed_files]
    issues: list[str] = []
    for baseline_path in baseline_paths:
        for allowed_path in normalized_allowed_paths:
            if allowed_path and validate_handoff_docs._scope_paths_overlap(baseline_path, allowed_path):
                issues.append(f"worktree baseline path must not overlap allowed file: {baseline_path} vs {allowed_path}")
    return issues


def validate_spec(spec: DeepSeekTaskSpec) -> list[str]:
    """Return validation issues for task input before writing it."""

    issues: list[str] = []
    if not spec.message_id or spec.message_id == "unassigned" or spec.message_id.startswith("<"):
        issues.append("message id must be concrete")
    if not spec.task or spec.task == "unassigned" or spec.task.startswith("<"):
        issues.append("task must be concrete")
    issues.extend(_validate_single_line_text("message id", (spec.message_id,)))
    issues.extend(_validate_single_line_text("task", (spec.task,)))
    if not spec.objective.strip() or spec.objective.strip().startswith("<"):
        issues.append("objective must be concrete")
    if not spec.allowed_files:
        issues.append("at least one allowed file is required")
    if len(spec.allowed_files) > 5:
        issues.append("allowed files must be limited to 5 or fewer")
    if not spec.forbidden_files:
        issues.append("at least one forbidden file is required")
    if not spec.requirements:
        issues.append("at least one requirement is required")
    if len(spec.requirements) < 3:
        issues.append("at least 3 requirements are required")
    issues.extend(
        validate_handoff_docs._validate_scope_paths(
            allowed_files=spec.allowed_files,
            forbidden_files=spec.forbidden_files,
        )
    )
    issues.extend(_validate_required_reading_paths(spec.required_reading))
    issues.extend(_validate_single_line_text("objective", (spec.objective,)))
    issues.extend(_validate_single_line_text("input contract", spec.input_contracts))
    issues.extend(_validate_unique_text("input contract", spec.input_contracts))
    issues.extend(_validate_single_line_text("output contract", spec.output_contracts))
    issues.extend(_validate_unique_text("output contract", spec.output_contracts))
    issues.extend(_validate_single_line_text("requirement", spec.requirements))
    issues.extend(_validate_unique_text("requirement", spec.requirements))
    issues.extend(_validate_single_line_text("acceptance criterion", spec.acceptance_criteria))
    issues.extend(_validate_unique_text("acceptance criterion", spec.acceptance_criteria))
    issues.extend(_validate_single_line_text("stop condition", spec.stop_conditions))
    issues.extend(_validate_unique_text("stop condition", spec.stop_conditions))
    if len(spec.acceptance_criteria) < 3:
        issues.append("at least 3 acceptance criteria are required")
    if len(spec.stop_conditions) < 3:
        issues.append("at least 3 stop conditions are required")
    if not spec.input_contracts:
        issues.append("at least one input contract is required")
    if not spec.output_contracts:
        issues.append("at least one output contract is required")
    issues.extend(_validate_verification_command_text(spec.verification_commands))
    usable_verification_commands = [
        command
        for command in spec.verification_commands
        if not validate_handoff_docs._has_shell_control_operator(command)
        and not validate_handoff_docs._has_response_file_argument(command)
        and not validate_handoff_docs._has_unsafe_verification_flag(command)
        and not validate_handoff_docs._git_diff_check_uses_paths_without_delimiter(command)
    ]
    for required_command in validate_handoff_docs.REQUIRED_VERIFICATION_COMMANDS:
        if not any(
            validate_handoff_docs._matches_required_verification_command(command, required_command)
            for command in usable_verification_commands
        ):
            issues.append(f"verification commands must include: {required_command}")
    issues.extend(validate_handoff_docs._validate_ready_inbox(render_task(spec)))
    return issues


def _validate_single_line_text(label: str, items: Sequence[str]) -> list[str]:
    """Validate task text before rendering it into markdown sections."""

    issues: list[str] = []

    for index, raw_item in enumerate(items, start=1):
        item = raw_item.strip()
        if not item:
            issues.append(f"{label} {index} must not be empty")
            continue
        if "\n" in raw_item or "\r" in raw_item:
            issues.append(f"{label} {index} must be single line")
        if "```" in raw_item:
            issues.append(f"{label} {index} must not contain markdown fences")
        if validate_handoff_docs._has_unresolved_angle_marker(raw_item):
            issues.append(f"{label} {index} must not contain angle-bracket markers")

    return issues


def _validate_unique_text(label: str, items: Sequence[str]) -> list[str]:
    """Validate text items are unique after whitespace and case normalization."""

    issues: list[str] = []
    seen: set[str] = set()

    for raw_item in items:
        item = raw_item.strip()
        if not item:
            continue
        normalized_item = " ".join(item.casefold().split())
        if normalized_item in seen:
            issues.append(f"duplicate {label}: {item}")
        seen.add(normalized_item)

    return issues


def _validate_required_reading_paths(paths: Sequence[str]) -> list[str]:
    """Validate required-reading path safety."""

    issues: list[str] = []
    seen: set[str] = set()

    for raw_path in paths:
        normalized_path = validate_handoff_docs._normalize_scope_path(raw_path)
        display_path = validate_handoff_docs._display_scope_path(raw_path)

        if not normalized_path:
            issues.append("required reading path must not be empty")
            continue
        if validate_handoff_docs._is_path_stand_in(raw_path):
            issues.append(f"empty required reading path stand-in: {display_path}")
            continue
        if validate_handoff_docs._is_unsafe_scope_path(raw_path=raw_path, normalized_path=normalized_path):
            issues.append(f"unsafe required reading path: {display_path}")
        if normalized_path in validate_handoff_docs.REQUIRED_READING_CONTROL_FILE_PATHS:
            issues.append(f"required reading path must not list handoff control file: {normalized_path}")
        if normalized_path in seen:
            issues.append(f"duplicate required reading path: {normalized_path}")
        seen.add(normalized_path)

    return issues


def _validate_verification_command_text(commands: Sequence[str]) -> list[str]:
    """Validate verification command text before rendering it into a fenced block."""

    issues: list[str] = []
    seen: set[str] = set()

    for index, raw_command in enumerate(commands, start=1):
        command = raw_command.strip()
        if not command:
            issues.append(f"verification command {index} must not be empty")
            continue
        if "\n" in raw_command or "\r" in raw_command:
            issues.append(f"verification command {index} must be single line")
        if "```" in raw_command:
            issues.append(f"verification command {index} must not contain markdown fences")
        if validate_handoff_docs._has_shell_control_operator(command):
            issues.append(f"verification command {index} must not contain shell control operators")
        if validate_handoff_docs._has_response_file_argument(command):
            issues.append(f"verification command {index} must not contain response-file arguments")
        if validate_handoff_docs._has_unsafe_verification_flag(command):
            issues.append(f"verification command {index} must not contain unsafe verification flags")
        if validate_handoff_docs._has_wrapped_required_verification_command(command):
            issues.append(f"verification command {index} must start with a direct verification command")
        if command in seen:
            issues.append(f"duplicate verification command: {command}")
        seen.add(command)

    return issues


def write_task(root: Path, spec: DeepSeekTaskSpec, *, worktree_baseline: Sequence[str] | None = None) -> Path:
    """Write the rendered task to the canonical DeepSeek inbox."""

    path = root / validate_handoff_docs.INBOX_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    baseline = tuple(worktree_baseline) if worktree_baseline is not None else _load_worktree_baseline(root)
    path.write_text(render_task(spec, worktree_baseline=baseline), encoding="utf-8")
    return path


def render_waiting_outbox(spec: DeepSeekTaskSpec) -> str:
    """Render an outbox that is waiting for DeepSeek implementation."""

    lines = [
        "# DeepSeek Outbox",
        "",
        "Status: WAITING_FOR_DEEPSEEK",
        f"Message ID: {spec.message_id}",
        f"Task: {spec.task}",
        "",
        "## Summary",
        "",
        "Codex assigned a bounded task. DeepSeek has not submitted implementation evidence yet.",
        "",
        "## Changed Files",
        "",
        "- None",
        "",
        "## Verification Commands and Results",
        "",
        "- Not run",
        "",
        "## Acceptance Criteria",
        "",
        "- Not applicable until DeepSeek submits implementation evidence.",
        "",
        "## Scope Deviations",
        "",
        "- None",
        "",
        "## Anti-Placeholder Scan",
        "",
        "- Not run",
        "",
        "## Unresolved Questions or Blockers",
        "",
        "- Waiting for DeepSeek implementation.",
        "",
    ]
    return "\n".join(lines)


def write_waiting_outbox(root: Path, spec: DeepSeekTaskSpec) -> Path:
    """Reset the canonical DeepSeek outbox to an implementation-waiting state."""

    path = root / validate_handoff_docs.OUTBOX_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_waiting_outbox(spec), encoding="utf-8")
    return path


def _load_worktree_baseline(root: Path) -> tuple[str, ...]:
    try:
        probe = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            check=False,
            text=True,
        )
    except FileNotFoundError:
        return ()

    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return ()

    status = subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        check=False,
        text=True,
    )
    if status.returncode != 0:
        return ()

    return tuple(sorted(_parse_git_status_paths(status.stdout)))


def _parse_git_status_paths(text: str) -> set[str]:
    paths: set[str] = set()
    for line in text.splitlines():
        if len(line) < 4:
            continue
        value = line[3:].strip()
        if " -> " in value:
            old_path, new_path = value.split(" -> ", 1)
            paths.add(_normalize_git_status_path(old_path))
            paths.add(_normalize_git_status_path(new_path))
        else:
            paths.add(_normalize_git_status_path(value))
    return {path for path in paths if path}


def _normalize_git_status_path(value: str) -> str:
    return value.strip().strip('"').replace("\\", "/").strip("/")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a bounded READY_FOR_DEEPSEEK inbox task.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root. Defaults to current directory.")
    parser.add_argument("--spec-file", type=Path, help="JSON task specification file, resolved from repository root.")
    parser.add_argument("--message-id", default="", help="Concrete Codex-generated message id.")
    parser.add_argument("--task", default="", help="Concrete task code.")
    parser.add_argument("--objective", default="", help="One bounded implementation objective.")
    parser.add_argument("--input-contract", action="append", default=[], help="Input contract to preserve or satisfy.")
    parser.add_argument("--output-contract", action="append", default=[], help="Output contract to preserve or satisfy.")
    parser.add_argument("--allowed-file", action="append", default=[], help="Allowed file or directory scope.")
    parser.add_argument("--forbidden-file", action="append", default=[], help="Forbidden file or directory scope.")
    parser.add_argument("--requirement", action="append", default=[], help="Concrete implementation requirement.")
    parser.add_argument("--acceptance", action="append", default=[], help="Unchecked acceptance criterion.")
    parser.add_argument("--verification-command", action="append", default=[], help="Exact verification command.")
    parser.add_argument("--required-reading", action="append", default=[], help="Extra required reading path.")
    parser.add_argument("--stop-condition", action="append", default=[], help="Extra stop condition.")
    parser.add_argument("--dry-run", action="store_true", help="Print the rendered task instead of writing it.")
    parser.add_argument("--reset-outbox", action="store_true", help="Reset the DeepSeek outbox after writing the task.")
    parser.add_argument("--validate-repository", action="store_true", help="Run full handoff validation after writing.")
    return parser.parse_args(argv)


def _spec_from_args(args: argparse.Namespace) -> DeepSeekTaskSpec:
    if args.spec_file is not None:
        return _spec_from_json_file(root=args.root, spec_file=args.spec_file)

    required_reading = (*DEFAULT_REQUIRED_READING, *tuple(args.required_reading))
    stop_conditions = (*DEFAULT_STOP_CONDITIONS, *tuple(args.stop_condition))
    input_contracts = (*DEFAULT_INPUT_CONTRACTS, *tuple(args.input_contract))
    output_contracts = (*DEFAULT_OUTPUT_CONTRACTS, *tuple(args.output_contract))
    return DeepSeekTaskSpec(
        message_id=args.message_id,
        task=args.task,
        objective=args.objective,
        input_contracts=input_contracts,
        output_contracts=output_contracts,
        allowed_files=tuple(args.allowed_file),
        forbidden_files=tuple(args.forbidden_file),
        requirements=tuple(args.requirement),
        acceptance_criteria=tuple(args.acceptance),
        verification_commands=tuple(args.verification_command),
        required_reading=required_reading,
        stop_conditions=stop_conditions,
    )


def _spec_from_json_file(*, root: Path, spec_file: Path) -> DeepSeekTaskSpec:
    path = _resolve_spec_file(root=root, spec_file=spec_file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"spec file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"spec file is not valid JSON: {path}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("spec file must contain a JSON object")
    unknown_fields = sorted(str(key) for key in data if key not in SPEC_FILE_FIELDS)
    if unknown_fields:
        raise ValueError(f"spec file contains unknown fields: {', '.join(unknown_fields)}")

    required_reading = (*DEFAULT_REQUIRED_READING, *_string_tuple(data, "required_reading"))
    stop_conditions = (*DEFAULT_STOP_CONDITIONS, *_string_tuple(data, "stop_conditions"))
    input_contracts = (*DEFAULT_INPUT_CONTRACTS, *_string_tuple(data, "input_contracts"))
    output_contracts = (*DEFAULT_OUTPUT_CONTRACTS, *_string_tuple(data, "output_contracts"))
    return DeepSeekTaskSpec(
        message_id=_string_value(data, "message_id"),
        task=_string_value(data, "task"),
        objective=_string_value(data, "objective"),
        input_contracts=input_contracts,
        output_contracts=output_contracts,
        allowed_files=_string_tuple(data, "allowed_files"),
        forbidden_files=_string_tuple(data, "forbidden_files"),
        requirements=_string_tuple(data, "requirements"),
        acceptance_criteria=_string_tuple(data, "acceptance_criteria"),
        verification_commands=_string_tuple(data, "verification_commands"),
        required_reading=required_reading,
        stop_conditions=stop_conditions,
    )


def _resolve_spec_file(*, root: Path, spec_file: Path) -> Path:
    raw_path = str(spec_file)
    normalized_path = validate_handoff_docs._normalize_scope_path(raw_path)
    if (
        not normalized_path
        or validate_handoff_docs._is_unsafe_scope_path(raw_path=raw_path, normalized_path=normalized_path)
    ):
        raise ValueError(f"unsafe spec file path: {validate_handoff_docs._display_scope_path(raw_path)}")
    return root / normalized_path


def _string_value(data: dict[object, object], key: str) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"spec field must be a string: {key}")
    return value


def _string_tuple(data: dict[object, object], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"spec field must be a list of strings: {key}")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"spec field must be a list of strings: {key}")
        result.append(item)
    return tuple(result)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        spec = _spec_from_args(args)
    except ValueError as exc:
        print(f"deepseek task spec invalid: {exc}", file=sys.stderr)
        return 1

    issues = validate_spec(spec)
    if issues:
        print("deepseek task validation failed:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1

    baseline = _load_worktree_baseline(args.root)
    try:
        rendered_task = render_task(spec, worktree_baseline=baseline)
    except ValueError as exc:
        print("deepseek task validation failed:", file=sys.stderr)
        print(f"- {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(rendered_task, end="")
        return 0

    managed_paths = [args.root / validate_handoff_docs.INBOX_PATH]
    if args.reset_outbox:
        managed_paths.append(args.root / validate_handoff_docs.OUTBOX_PATH)
    original_contents = _capture_files(managed_paths) if args.validate_repository else {}

    written_paths = [write_task(args.root, spec, worktree_baseline=baseline)]
    if args.reset_outbox:
        written_paths.append(write_waiting_outbox(args.root, spec))
    for path in written_paths:
        print(f"wrote {path}")

    if args.validate_repository:
        repository_issues = validate_handoff_docs.validate_handoff_docs(args.root)
        if repository_issues:
            _restore_files(original_contents)
            print("repository handoff validation failed after write:", file=sys.stderr)
            print("restored previous handoff files", file=sys.stderr)
            for issue in repository_issues:
                print(f"- {issue}", file=sys.stderr)
            return 1
        print("repository handoff validation ok")
    return 0


def _capture_files(paths: Sequence[Path]) -> dict[Path, str | None]:
    return {path: path.read_text(encoding="utf-8") if path.is_file() else None for path in paths}


def _restore_files(contents: dict[Path, str | None]) -> None:
    for path, text in contents.items():
        if text is None:
            if path.exists():
                path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
