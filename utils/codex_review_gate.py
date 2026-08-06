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
    inbox_value, inbox_read_issue = validate_handoff_docs.read_required_repository_text(
        root=root,
        relative_path=INBOX_PATH,
    )
    outbox_value, outbox_read_issue = validate_handoff_docs.read_required_repository_text(
        root=root,
        relative_path=OUTBOX_PATH,
    )
    for read_issue in (inbox_read_issue, outbox_read_issue):
        if read_issue is not None and read_issue not in issues:
            issues.append(read_issue)
    inbox_text = inbox_value if inbox_value is not None else ""
    outbox_text = outbox_value if outbox_value is not None else ""
    metadata = validate_handoff_docs.extract_handoff_metadata(outbox_text)
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
        pattern=validate_handoff_docs.SECRET_KEY_PATTERN,
        root=root,
        paths=scan_paths + HANDOFF_SECRET_SCAN_PATHS,
        redact=True,
    )

    return _redact_review_result(
        ReviewGateResult(
            ready_for_review=ready_for_review,
            status=metadata.get("Status"),
            message_id=metadata.get("Message ID"),
            task=metadata.get("Task"),
            changed_files=changed_files,
            issues=tuple(issues),
            blocked_term_hits=tuple(blocked_term_hits),
            secret_key_hits=tuple(secret_key_hits),
        )
    )


def to_jsonable_result(result: ReviewGateResult) -> dict[str, object]:
    """Return a JSON-serializable review gate result."""

    safe_result = _redact_review_result(result)
    return {
        "ok": not safe_result.issues
        and not safe_result.blocked_term_hits
        and not safe_result.secret_key_hits,
        "ready_for_review": safe_result.ready_for_review,
        "status": safe_result.status,
        "message_id": safe_result.message_id,
        "task": safe_result.task,
        "changed_files": [path.as_posix() for path in safe_result.changed_files],
        "issues": list(safe_result.issues),
        "blocked_term_hits": [_scan_hit_to_dict(hit) for hit in safe_result.blocked_term_hits],
        "secret_key_hits": [_scan_hit_to_dict(hit) for hit in safe_result.secret_key_hits],
    }


def _scan_hit_to_dict(hit: ScanHit) -> dict[str, object]:
    return {
        "path": hit.path.as_posix(),
        "line_number": hit.line_number,
        "preview": hit.preview,
    }


def _redact_review_result(result: ReviewGateResult) -> ReviewGateResult:
    """净化完整 Codex review report 的所有用户可见文本字段。

    参数:
        result: 可能包含 metadata、路径、issue 或 scan hit 敏感形状的报告。

    返回值:
        保留布尔与行号语义、替换全部 secret-shaped 文本的报告。

    异常:
        无。
    """

    return ReviewGateResult(
        ready_for_review=result.ready_for_review,
        status=_redact_optional_text(result.status),
        message_id=_redact_optional_text(result.message_id),
        task=_redact_optional_text(result.task),
        changed_files=tuple(
            Path(validate_handoff_docs.redact_secret_shapes(path.as_posix()))
            for path in result.changed_files
        ),
        issues=tuple(
            validate_handoff_docs.redact_secret_shapes(issue)
            for issue in result.issues
        ),
        blocked_term_hits=_redact_scan_hits(result.blocked_term_hits),
        secret_key_hits=_redact_scan_hits(result.secret_key_hits),
    )


def _redact_optional_text(value: str | None) -> str | None:
    """净化可选报告文本。

    参数:
        value: 可选 metadata 文本。

    返回值:
        ``None`` 原样返回；字符串中的敏感形状被替换。

    异常:
        无。
    """

    if value is None:
        return None
    return validate_handoff_docs.redact_secret_shapes(value)


def _redact_scan_hits(hits: Sequence[ScanHit]) -> tuple[ScanHit, ...]:
    """净化 scan hit 的路径与预览文本。

    参数:
        hits: 待输出的 scan hit 序列。

    返回值:
        路径和 preview 均完成敏感形状替换的不可变序列。

    异常:
        无。
    """

    return tuple(
        ScanHit(
            path=Path(validate_handoff_docs.redact_secret_shapes(hit.path.as_posix())),
            line_number=hit.line_number,
            preview=validate_handoff_docs.redact_secret_shapes(hit.preview),
        )
        for hit in hits
    )


def format_scan_preview(*, line: str, redact: bool) -> str:
    """生成不会旁路 secret-shape 脱敏的扫描预览。

    参数:
        line: 当前模式命中的原始文本行。
        redact: 调用方是否要求无条件脱敏。

    返回值:
        当调用方要求脱敏或文本行包含 secret-shaped 值时返回
        ``<redacted>``，否则返回去除首尾空白的原始行。

    异常:
        无。
    """

    if redact or validate_handoff_docs.contains_secret_shape(line):
        return validate_handoff_docs.REDACTED_SECRET
    return line.strip()


def _is_ready_for_review(text: str) -> bool:
    return validate_handoff_docs.extract_handoff_metadata(text).get("Status") == validate_handoff_docs.READY_FOR_REVIEW


def _extract_changed_files(outbox_text: str) -> tuple[Path, ...]:
    body = _section_body(outbox_text, "## Changed Files")
    return tuple(
        Path(value)
        for value in validate_handoff_docs.extract_outbox_changed_file_entries(body)
    )


def _resolve_scan_paths(*, root: Path, changed_files: Sequence[Path]) -> tuple[tuple[Path, ...], list[str]]:
    """解析可安全扫描的仓库内 changed-file 路径。

    参数:
        root: 仓库根目录。
        changed_files: outbox 声明的变更文件路径。

    返回值:
        可扫描的仓库相对路径元组与路径问题列表。

    异常:
        无。
    """

    scan_paths: list[Path] = []
    issues: list[str] = []
    seen_paths: set[str] = set()
    for path in changed_files:
        raw_path = path.as_posix()
        normalized_path = validate_handoff_docs.normalize_repository_path(raw_path)
        if not normalized_path:
            issues.append("changed file path must not be empty")
            continue
        if validate_handoff_docs.is_unsafe_repository_path(
            raw_path=raw_path,
            normalized_path=normalized_path,
        ):
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
        if not validate_handoff_docs.is_path_within_repository_root(root=root, path=resolved):
            issues.append(f"changed file path must stay within repository root: {normalized_path}")
            continue
        if not resolved.exists():
            issues.append(f"changed file listed in outbox does not exist: {normalized_path}")
            continue
        if not resolved.is_file():
            issues.append(f"changed file listed in outbox must be a file: {normalized_path}")
            continue
        scan_paths.append(relative_path)
    return tuple(scan_paths), issues


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
    outbox_results = validate_handoff_docs.extract_outbox_verification_results(outbox_body)
    inbox_body = _section_body(inbox_text, "## Verification Commands")
    issues: list[str] = []
    for command in validate_handoff_docs.extract_verification_commands(inbox_body):
        matching_lines = [line for result_command, line in outbox_results if result_command == command]
        if not matching_lines:
            issues.append(f"{OUTBOX_PATH.as_posix()} missing assigned verification command result: {command}")
            continue
        if any(validate_handoff_docs.has_failing_verification_result(line) for line in matching_lines):
            issues.append(f"{OUTBOX_PATH.as_posix()} assigned verification command has failing result: {command}")
        if not any(validate_handoff_docs.has_clean_verification_result(line) for line in matching_lines):
            issues.append(f"{OUTBOX_PATH.as_posix()} assigned verification command lacks clean result: {command}")
    return issues


def _validate_acceptance_criteria(*, inbox_text: str, outbox_text: str) -> list[str]:
    if not _is_ready_for_deepseek(inbox_text):
        return []

    inbox_criteria = _extract_inbox_acceptance_criteria(inbox_text)
    outbox_items = _extract_outbox_checked_acceptance_items(outbox_text)
    issues: list[str] = []
    for item in outbox_items:
        if validate_handoff_docs.has_negative_acceptance_evidence(item):
            issues.append(f"{OUTBOX_PATH.as_posix()} checked acceptance evidence is negative: {item}")
    for criterion in inbox_criteria:
        if not any(
            validate_handoff_docs.acceptance_item_covers_criterion(item=item, criterion=criterion)
            for item in outbox_items
        ):
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


def _validate_changed_files_have_worktree_changes(*, root: Path, changed_files: Sequence[Path]) -> list[str]:
    changed_git_paths, issues = _load_git_changed_paths(root)
    if changed_git_paths is None:
        return issues

    for changed_file in changed_files:
        raw_path = changed_file.as_posix()
        normalized_path = validate_handoff_docs.normalize_repository_path(raw_path)
        if validate_handoff_docs.is_unsafe_repository_path(
            raw_path=raw_path,
            normalized_path=normalized_path,
        ):
            continue
        if normalized_path and normalized_path not in changed_git_paths:
            issues.append(f"changed file is not dirty in git status: {normalized_path}")
    return issues


def _validate_worktree_baseline_paths_are_dirty(*, root: Path, inbox_text: str) -> list[str]:
    if not _is_ready_for_deepseek(inbox_text):
        return []

    changed_git_paths, issues = _load_git_changed_paths(root)
    if changed_git_paths is None:
        return issues

    baseline_body = _section_body(inbox_text, "## Worktree Baseline")
    baseline_paths = set(validate_handoff_docs.extract_worktree_baseline_paths(baseline_body))
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
    reported_paths: set[str] = set()
    for changed_file in changed_files:
        raw_path = changed_file.as_posix()
        normalized_path = validate_handoff_docs.normalize_repository_path(raw_path)
        if not validate_handoff_docs.is_unsafe_repository_path(
            raw_path=raw_path,
            normalized_path=normalized_path,
        ):
            reported_paths.add(normalized_path)
    baseline_body = _section_body(inbox_text, "## Worktree Baseline")
    baseline_paths = set(validate_handoff_docs.extract_worktree_baseline_paths(baseline_body))
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
    return validate_handoff_docs.extract_handoff_metadata(text).get("Status") == validate_handoff_docs.READY_FOR_DEEPSEEK


def _extract_section_paths(text: str, heading: str) -> tuple[Path, ...]:
    paths: list[Path] = []
    for raw_path in validate_handoff_docs.extract_repository_path_entries(_section_body(text, heading)):
        normalized_path = validate_handoff_docs.normalize_repository_path(raw_path)
        if not normalized_path:
            continue
        if validate_handoff_docs.is_unsafe_repository_path(
            raw_path=raw_path,
            normalized_path=normalized_path,
        ):
            continue
        paths.append(Path(normalized_path))
    return tuple(paths)


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
    """扫描仓库内文本文件并返回匹配位置。

    参数:
        pattern: 待匹配的正则表达式。
        root: 仓库根目录。
        paths: 待扫描的仓库相对路径。
        redact: 是否隐藏命中行正文。

    返回值:
        仓库内文件的有序扫描命中元组。

    异常:
        无；非 UTF-8 或不可读文件以受控命中表示，越界或非文件路径被跳过。
    """

    hits: list[ScanHit] = []
    for relative_path in paths:
        path = root / relative_path
        if not validate_handoff_docs.is_path_within_repository_root(root=root, path=path):
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            hits.append(ScanHit(path=relative_path, line_number=0, preview="<non-utf8 file skipped>"))
            continue
        except OSError:
            hits.append(ScanHit(path=relative_path, line_number=0, preview="<unreadable file skipped>"))
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                preview = format_scan_preview(line=line, redact=redact)
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
