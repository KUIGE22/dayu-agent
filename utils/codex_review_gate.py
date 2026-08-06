"""Build a local Codex review gate report for a DeepSeek handoff."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from utils import validate_handoff_docs

SECRET_KEY_PATTERN = re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,}")
BLOCKED_TERMS = (
    "TO" + "DO",
    "FIX" + "ME",
    "pa" + "ss",
    "Not" + "Implemented",
    "mo" + "ck",
    "place" + "holder",
    "fa" + "ke",
    "du" + "mmy",
)
BLOCKED_TERM_PATTERN = re.compile(r"\b(" + "|".join(re.escape(term) for term in BLOCKED_TERMS) + r")\b")
OUTBOX_PATH = Path("docs/handoff/deepseek_outbox.md")
INBOX_PATH = validate_handoff_docs.INBOX_PATH
NO_SCOPE_DEVIATION_VALUES = {
    "none",
}
NO_WORKTREE_BASELINE_VALUES = {
    "none",
    "not applicable",
    "n/a",
    "clean",
    "empty",
}
HANDOFF_CONTROL_PATHS = frozenset(
    {
        INBOX_PATH.as_posix(),
        OUTBOX_PATH.as_posix(),
        "CODEX_REVIEW.md",
        "DEEPSEEK_INBOX.md",
    }
)
HANDOFF_SECRET_SCAN_PATHS = (
    Path("CODEX_REVIEW.md"),
    Path("DEEPSEEK_INBOX.md"),
    INBOX_PATH,
    OUTBOX_PATH,
)
WORKFLOW_CONTROL_PATHS = validate_handoff_docs.ASSIGNMENT_CONTROL_FILE_PATHS
COMMAND_SUCCESS_MARKERS = (
    "exited 0",
    "exit 0",
    "-> ok",
    "succeeded",
)
COMMAND_FAILURE_MARKERS = (
    "exited 1",
    "exit 1",
    "nonzero",
    "failed",
    "failure",
    "not successful",
    "not succeeded",
    "not executed",
    "not actually executed",
    "not actually run",
    "skipped",
    "skip",
    "unsuccessful",
    "dry run",
    "dry-run",
    "manual only",
    "manual-only",
    "manual verification",
    "manually verified",
    "simulated run",
    "simulated result",
    "synthetic result",
    "fabricated result",
    "invented result",
    "estimated result",
)
ACCEPTANCE_FAILURE_MARKERS = (
    "not implemented",
    "not done",
    "not verified",
    "not covered",
    "not executed",
    "unverified",
    "untested",
    "pending",
    "deferred",
    "not applicable",
    "n/a",
    "incomplete",
    "missing",
    "omitted",
    "skipped",
    "skip",
    "unable to verify",
)


@dataclass(frozen=True)
class ScanHit:
    """One text scan hit."""

    path: Path
    line_number: int
    preview: str


@dataclass(frozen=True)
class ReviewGateResult:
    """Codex review gate status."""

    ready_for_review: bool
    status: str | None
    message_id: str | None
    task: str | None
    changed_files: tuple[Path, ...]
    issues: tuple[str, ...]
    blocked_term_hits: tuple[ScanHit, ...]
    secret_key_hits: tuple[ScanHit, ...]


def run_review_gate(root: Path, *, allow_waiting: bool = False) -> ReviewGateResult:
    """Run handoff validation and scoped scans for a Codex review."""

    issues = validate_handoff_docs.validate_handoff_docs(root)
    inbox_text = _read_optional_text(root / INBOX_PATH)
    outbox_text = _read_optional_text(root / OUTBOX_PATH)
    metadata = _extract_metadata(outbox_text)
    ready_for_review = _is_ready_for_review(outbox_text)

    if not ready_for_review and not allow_waiting:
        issues.append(f"{OUTBOX_PATH.as_posix()} is not marked {validate_handoff_docs.READY_FOR_REVIEW}")

    changed_files = _extract_changed_files(outbox_text)
    if ready_for_review and not changed_files:
        issues.append(f"{OUTBOX_PATH.as_posix()} ready outbox must list at least one changed file")

    scan_paths, scan_issues = _resolve_scan_paths(root=root, changed_files=changed_files)
    issues.extend(scan_issues)
    if ready_for_review:
        issues.extend(_validate_scope(inbox_text=inbox_text, changed_files=changed_files))
        issues.extend(_validate_scope_deviations(outbox_text))
        issues.extend(_validate_verification_commands(inbox_text=inbox_text, outbox_text=outbox_text))
        issues.extend(_validate_acceptance_criteria(inbox_text=inbox_text, outbox_text=outbox_text))
        issues.extend(_validate_changed_files_have_worktree_changes(root=root, changed_files=changed_files))
        issues.extend(_validate_worktree_baseline_paths_are_dirty(root=root, inbox_text=inbox_text))
        issues.extend(
            _validate_scoped_worktree_changes_are_reported(
                root=root,
                inbox_text=inbox_text,
                changed_files=changed_files,
            )
        )

    blocked_term_hits = _scan_files(
        pattern=BLOCKED_TERM_PATTERN,
        root=root,
        paths=scan_paths + (OUTBOX_PATH,),
        redact=False,
    )
    secret_key_hits = _scan_files(
        pattern=SECRET_KEY_PATTERN,
        root=root,
        paths=scan_paths + HANDOFF_SECRET_SCAN_PATHS,
        redact=True,
    )

    return ReviewGateResult(
        ready_for_review=ready_for_review,
        status=metadata.get("Status"),
        message_id=metadata.get("Message ID"),
        task=metadata.get("Task"),
        changed_files=changed_files,
        issues=tuple(issues),
        blocked_term_hits=tuple(blocked_term_hits),
        secret_key_hits=tuple(secret_key_hits),
    )


def to_jsonable_result(result: ReviewGateResult) -> dict[str, object]:
    """Return a JSON-serializable review gate result."""

    return {
        "ok": not result.issues and not result.blocked_term_hits and not result.secret_key_hits,
        "ready_for_review": result.ready_for_review,
        "status": result.status,
        "message_id": result.message_id,
        "task": result.task,
        "changed_files": [path.as_posix() for path in result.changed_files],
        "issues": list(result.issues),
        "blocked_term_hits": [_scan_hit_to_dict(hit) for hit in result.blocked_term_hits],
        "secret_key_hits": [_scan_hit_to_dict(hit) for hit in result.secret_key_hits],
    }


def _scan_hit_to_dict(hit: ScanHit) -> dict[str, object]:
    return {
        "path": hit.path.as_posix(),
        "line_number": hit.line_number,
        "preview": hit.preview,
    }


def _read_optional_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _extract_metadata(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key in {"Status", "Message ID", "Task"}:
            if key not in metadata:
                metadata[key] = value.strip()
    return metadata


def _is_ready_for_review(text: str) -> bool:
    return _extract_metadata(text).get("Status") == validate_handoff_docs.READY_FOR_REVIEW


def _extract_changed_files(outbox_text: str) -> tuple[Path, ...]:
    body = _section_body(outbox_text, "## Changed Files")
    paths: list[Path] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith("-"):
            continue
        value = line[1:].strip()
        if value in {"None", "No changes", "Not applicable"}:
            continue
        match = re.fullmatch(r"`([^`]+)`(?:\s+-\s+.*)?", value)
        if match:
            value = match.group(1)
        paths.append(Path(value))
    return tuple(paths)


def _resolve_scan_paths(*, root: Path, changed_files: Sequence[Path]) -> tuple[tuple[Path, ...], list[str]]:
    scan_paths: list[Path] = []
    issues: list[str] = []
    seen_paths: set[str] = set()
    for path in changed_files:
        normalized_path = _normalize_outbox_path(path)
        if not normalized_path:
            issues.append("changed file path must not be empty")
            continue
        if _is_unsafe_outbox_path(path):
            issues.append(f"changed file path must be a safe repository-relative path: {path.as_posix()}")
            continue
        if normalized_path in seen_paths:
            issues.append(f"changed file path is duplicated in outbox: {normalized_path}")
            continue
        seen_paths.add(normalized_path)
        if normalized_path in HANDOFF_CONTROL_PATHS:
            issues.append(f"changed file is a handoff control file, not an implementation file: {normalized_path}")
            continue
        if normalized_path in WORKFLOW_CONTROL_PATHS:
            issues.append(f"changed file is a workflow control file, not an implementation file: {normalized_path}")
            continue

        relative_path = Path(normalized_path)
        resolved = root / relative_path
        if not resolved.exists():
            issues.append(f"changed file listed in outbox does not exist: {normalized_path}")
            continue
        if not resolved.is_file():
            issues.append(f"changed file listed in outbox must be a file: {normalized_path}")
            continue
        scan_paths.append(relative_path)
    return tuple(scan_paths), issues


def _normalize_outbox_path(path: Path) -> str:
    value = path.as_posix().replace("\\", "/")
    while "//" in value:
        value = value.replace("//", "/")
    return value.strip().strip("/").rstrip("/")


def _is_unsafe_outbox_path(path: Path) -> bool:
    value = path.as_posix().replace("\\", "/")
    if "`" in value:
        return True
    if "\n" in value or "\r" in value:
        return True
    if path.is_absolute() or value.startswith(("/", "\\")):
        return True
    if "://" in value:
        return True
    if ":" in value:
        return True
    return any(part in {"..", "."} for part in value.split("/"))


def _validate_scope(*, inbox_text: str, changed_files: Sequence[Path]) -> list[str]:
    issues: list[str] = []
    if not _is_ready_for_deepseek(inbox_text):
        issues.append(f"{OUTBOX_PATH.as_posix()} ready review requires {INBOX_PATH.as_posix()} to be READY_FOR_DEEPSEEK")
        return issues

    allowed_paths = _extract_section_paths(inbox_text, "## Allowed Files")
    forbidden_paths = _extract_section_paths(inbox_text, "## Forbidden Files")
    for changed_file in changed_files:
        if not _path_matches_any(changed_file, allowed_paths):
            issues.append(f"changed file is outside allowed scope: {changed_file.as_posix()}")
        if _path_matches_any(changed_file, forbidden_paths):
            issues.append(f"changed file touches forbidden scope: {changed_file.as_posix()}")
    return issues


def _validate_scope_deviations(outbox_text: str) -> list[str]:
    lines = _scope_deviation_lines(outbox_text)
    if not lines:
        return [f"{OUTBOX_PATH.as_posix()} ready outbox must explicitly state scope deviations or None"]

    deviations = [line for line in lines if _normalize_scope_deviation(line) not in NO_SCOPE_DEVIATION_VALUES]
    return [f"{OUTBOX_PATH.as_posix()} lists scope deviations requiring Codex review: {line}" for line in deviations]


def _validate_verification_commands(*, inbox_text: str, outbox_text: str) -> list[str]:
    if not _is_ready_for_deepseek(inbox_text):
        return []

    outbox_body = _section_body(outbox_text, "## Verification Commands and Results")
    outbox_results = _extract_outbox_verification_results(outbox_body)
    issues: list[str] = []
    for command in _extract_verification_commands(inbox_text):
        matching_lines = [line for result_command, line in outbox_results if result_command == command]
        if not matching_lines:
            issues.append(f"{OUTBOX_PATH.as_posix()} missing assigned verification command result: {command}")
            continue
        if any(_has_failing_command_result(line) for line in matching_lines):
            issues.append(f"{OUTBOX_PATH.as_posix()} assigned verification command has failing result: {command}")
        if not any(_has_clean_command_result(line) for line in matching_lines):
            issues.append(f"{OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: {command}")
    return issues


def _validate_acceptance_criteria(*, inbox_text: str, outbox_text: str) -> list[str]:
    if not _is_ready_for_deepseek(inbox_text):
        return []

    inbox_criteria = _extract_inbox_acceptance_criteria(inbox_text)
    outbox_items = _extract_outbox_checked_acceptance_items(outbox_text)
    issues: list[str] = []
    for item in outbox_items:
        if _has_negative_acceptance_evidence(item):
            issues.append(f"{OUTBOX_PATH.as_posix()} checked acceptance evidence is negative: {item}")
    for criterion in inbox_criteria:
        normalized_criterion = _normalize_acceptance_text(criterion)
        if not normalized_criterion:
            continue
        if not any(_acceptance_item_covers_criterion(item=item, criterion=criterion) for item in outbox_items):
            issues.append(f"{OUTBOX_PATH.as_posix()} missing checked acceptance evidence: {criterion}")
    return issues


def _extract_inbox_acceptance_criteria(inbox_text: str) -> tuple[str, ...]:
    body = _section_body(inbox_text, "## Acceptance Criteria")
    criteria: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("- [ ] "):
            criteria.append(line[6:].strip())
    return tuple(criteria)


def _extract_outbox_checked_acceptance_items(outbox_text: str) -> tuple[str, ...]:
    body = _section_body(outbox_text, "## Acceptance Criteria")
    items: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("- [x] ") or line.startswith("- [X] "):
            items.append(line[6:].strip())
    return tuple(items)


def _normalize_acceptance_text(value: str) -> str:
    normalized = " ".join(value.strip().lower().split())
    return normalized.rstrip(".:")


def _acceptance_item_covers_criterion(*, item: str, criterion: str) -> bool:
    normalized_item = _normalize_acceptance_text(item)
    normalized_criterion = _normalize_acceptance_text(criterion)
    if not normalized_item.startswith(normalized_criterion):
        return False
    if len(normalized_item) == len(normalized_criterion):
        return True
    next_character = normalized_item[len(normalized_criterion)]
    return not next_character.isalnum()


def _has_negative_acceptance_evidence(value: str) -> bool:
    normalized = _normalize_acceptance_text(value)
    return any(marker in normalized for marker in ACCEPTANCE_FAILURE_MARKERS)


def _extract_outbox_verification_results(outbox_body: str) -> tuple[tuple[str, str], ...]:
    results: list[tuple[str, str]] = []
    for raw_line in outbox_body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.search(r"`([^`]+)`", line)
        if match:
            results.append((match.group(1).strip(), line))
    return tuple(results)


def _has_clean_command_result(line: str) -> bool:
    normalized = _command_result_evidence_text(line)
    if any(marker in normalized for marker in COMMAND_FAILURE_MARKERS):
        return False
    return any(marker in normalized for marker in COMMAND_SUCCESS_MARKERS)


def _has_failing_command_result(line: str) -> bool:
    normalized = _command_result_evidence_text(line)
    return any(marker in normalized for marker in COMMAND_FAILURE_MARKERS)


def _command_result_evidence_text(line: str) -> str:
    """Return command-result prose outside backticked command spans."""

    return re.sub(r"`[^`\r\n]*`", " ", line).lower()


def _extract_verification_commands(inbox_text: str) -> tuple[str, ...]:
    body = _section_body(inbox_text, "## Verification Commands")
    commands: list[str] = []
    in_fence = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            commands.append(line)
            continue
        if line.startswith("- "):
            match = re.search(r"`([^`]+)`", line[2:].strip())
            if match:
                commands.append(match.group(1).strip())
    return tuple(commands)


def _validate_changed_files_have_worktree_changes(*, root: Path, changed_files: Sequence[Path]) -> list[str]:
    changed_git_paths, issues = _load_git_changed_paths(root)
    if changed_git_paths is None:
        return issues

    for changed_file in changed_files:
        if _is_unsafe_outbox_path(changed_file):
            continue
        normalized_path = _normalize_outbox_path(changed_file)
        if normalized_path and normalized_path not in changed_git_paths:
            issues.append(f"changed file is not dirty in git status: {normalized_path}")
    return issues


def _validate_worktree_baseline_paths_are_dirty(*, root: Path, inbox_text: str) -> list[str]:
    if not _is_ready_for_deepseek(inbox_text):
        return []

    changed_git_paths, issues = _load_git_changed_paths(root)
    if changed_git_paths is None:
        return issues

    baseline_paths = set(_extract_worktree_baseline_paths(inbox_text))
    return [
        f"worktree baseline path is not dirty in git status: {baseline_path}"
        for baseline_path in sorted(baseline_paths)
        if baseline_path not in changed_git_paths
    ]


def _validate_scoped_worktree_changes_are_reported(
    *,
    root: Path,
    inbox_text: str,
    changed_files: Sequence[Path],
) -> list[str]:
    if not _is_ready_for_deepseek(inbox_text):
        return []

    changed_git_paths, issues = _load_git_changed_paths(root)
    if changed_git_paths is None:
        return issues

    allowed_paths = _extract_section_paths(inbox_text, "## Allowed Files")
    forbidden_paths = _extract_section_paths(inbox_text, "## Forbidden Files")
    reported_paths = {_normalize_outbox_path(path) for path in changed_files if not _is_unsafe_outbox_path(path)}
    baseline_paths = set(_extract_worktree_baseline_paths(inbox_text))
    for git_path_text in sorted(changed_git_paths):
        if git_path_text == OUTBOX_PATH.as_posix():
            continue
        if git_path_text in baseline_paths:
            continue
        if git_path_text in HANDOFF_CONTROL_PATHS or git_path_text in WORKFLOW_CONTROL_PATHS:
            issues.append(f"workflow control file changed after assignment: {git_path_text}")
            continue
        git_path = Path(git_path_text)
        if _path_matches_any(git_path, forbidden_paths):
            issues.append(f"worktree change touches forbidden scope: {git_path_text}")
            continue
        if _path_matches_any(git_path, allowed_paths) and git_path_text not in reported_paths:
            issues.append(f"worktree change inside allowed scope is missing from outbox: {git_path_text}")
            continue
        if git_path_text not in reported_paths:
            issues.append(f"post-assignment worktree change is missing from outbox: {git_path_text}")
    return issues


def _extract_worktree_baseline_paths(inbox_text: str) -> tuple[str, ...]:
    body = _section_body(inbox_text, "## Worktree Baseline")
    paths: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        value = line[2:].strip()
        match = re.search(r"`([^`]+)`", value)
        if match:
            value = match.group(1)
        normalized_value = _normalize_outbox_path(Path(value))
        if not normalized_value or normalized_value.lower().rstrip(".") in NO_WORKTREE_BASELINE_VALUES:
            continue
        if _is_unsafe_outbox_path(Path(value)):
            continue
        paths.append(normalized_value)
    return tuple(paths)


def _load_git_changed_paths(root: Path) -> tuple[frozenset[str] | None, list[str]]:
    try:
        probe = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            check=False,
            text=True,
        )
    except FileNotFoundError:
        return None, ["git executable is unavailable for changed-file evidence"]

    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return None, []

    status = subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        check=False,
        text=True,
    )
    if status.returncode != 0:
        details = (status.stderr or status.stdout).strip()
        return None, [f"git status check failed for changed-file evidence: {details}"]

    changed_paths: set[str] = set()
    for line in status.stdout.splitlines():
        if len(line) < 4:
            continue
        value = line[3:].strip()
        if " -> " in value:
            old_path, new_path = value.split(" -> ", 1)
            changed_paths.add(_normalize_git_status_path(old_path))
            changed_paths.add(_normalize_git_status_path(new_path))
        else:
            changed_paths.add(_normalize_git_status_path(value))
    return frozenset(path for path in changed_paths if path), []


def _normalize_git_status_path(value: str) -> str:
    return value.strip().strip('"').replace("\\", "/").strip("/")


def _scope_deviation_lines(outbox_text: str) -> tuple[str, ...]:
    body = _section_body(outbox_text, "## Scope Deviations")
    lines: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("-"):
            line = line[1:].strip()
        if line:
            lines.append(line)
    return tuple(lines)


def _normalize_scope_deviation(value: str) -> str:
    return value.strip().strip("`").strip().lower().rstrip(".")


def _is_ready_for_deepseek(text: str) -> bool:
    return _extract_metadata(text).get("Status") == validate_handoff_docs.READY_FOR_DEEPSEEK


def _extract_section_paths(text: str, heading: str) -> tuple[Path, ...]:
    paths: list[Path] = []
    for value in _section_items(_section_body(text, heading)):
        paths.append(Path(value))
    return tuple(paths)


def _section_items(text: str) -> list[str]:
    items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        value = line[2:].strip()
        match = re.search(r"`([^`]+)`", value)
        if match:
            value = match.group(1)
        if not value or value in {"None", "Not applicable"} or value.startswith("<"):
            continue
        items.append(value)
    return items


def _path_matches_any(path: Path, scopes: Sequence[Path]) -> bool:
    return any(_path_matches_scope(path, scope) for scope in scopes)


def _path_matches_scope(path: Path, scope: Path) -> bool:
    normalized_path = _normalize_relative_path(path)
    normalized_scope = _normalize_relative_path(scope)
    if not normalized_scope:
        return False
    if normalized_path == normalized_scope:
        return True
    return normalized_path.startswith(f"{normalized_scope}/")


def _normalize_relative_path(path: Path) -> str:
    return path.as_posix().strip().strip("/").rstrip("/")


def _scan_files(*, pattern: re.Pattern[str], root: Path, paths: Sequence[Path], redact: bool) -> tuple[ScanHit, ...]:
    hits: list[ScanHit] = []
    for relative_path in paths:
        path = root / relative_path
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            hits.append(ScanHit(path=relative_path, line_number=0, preview="<non-utf8 file skipped>"))
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                preview = "<redacted>" if redact else line.strip()
                hits.append(ScanHit(path=relative_path, line_number=line_number, preview=preview))
    return tuple(hits)


def _section_body(text: str, heading: str) -> str:
    target_level = _heading_level(heading)
    if target_level is None:
        return ""

    body_lines: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if not in_section:
            if stripped == heading:
                in_section = True
            continue

        level = _heading_level(stripped)
        if level is not None and level <= target_level:
            break
        body_lines.append(line)

    return "\n".join(body_lines).strip()


def _heading_level(line: str) -> int | None:
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None

    level = len(stripped) - len(stripped.lstrip("#"))
    if len(stripped) == level or stripped[level] != " ":
        return None

    return level


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local Codex review gate for a DeepSeek handoff.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--allow-waiting",
        action="store_true",
        help="Allow an outbox that is still waiting for an assigned DeepSeek task.",
    )
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON report.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_review_gate(args.root, allow_waiting=args.allow_waiting)
    if args.json:
        print(json.dumps(to_jsonable_result(result), ensure_ascii=False, indent=2))
    else:
        _print_report(result)
    if result.issues or result.blocked_term_hits or result.secret_key_hits:
        return 1
    return 0


def _print_report(result: ReviewGateResult) -> None:
    print("# Codex Review Gate")
    print(f"Status: {result.status or 'unknown'}")
    print(f"Message ID: {result.message_id or 'unknown'}")
    print(f"Task: {result.task or 'unknown'}")
    print(f"Ready for review: {'yes' if result.ready_for_review else 'no'}")
    print()
    print("Changed files:")
    if result.changed_files:
        for path in result.changed_files:
            print(f"- {path.as_posix()}")
    else:
        print("- None")

    _print_issue_group("Issues", result.issues)
    _print_hit_group("Blocked term hits", result.blocked_term_hits)
    _print_hit_group("Secret key hits", result.secret_key_hits)

    if not result.issues and not result.blocked_term_hits and not result.secret_key_hits:
        print()
        print("codex review gate ok")


def _print_issue_group(title: str, issues: Sequence[str]) -> None:
    if not issues:
        return
    print()
    print(f"{title}:")
    for issue in issues:
        print(f"- {issue}")


def _print_hit_group(title: str, hits: Sequence[ScanHit]) -> None:
    if not hits:
        return
    print()
    print(f"{title}:")
    for hit in hits:
        print(f"- {hit.path.as_posix()}:{hit.line_number}: {hit.preview}")


if __name__ == "__main__":
    raise SystemExit(main())
