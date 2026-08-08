"""Run the local DeepSeek/Codex workflow health checks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from dayu.redaction import (
    SECRET_KEY_PATTERN,
    RedactingArgumentParser,
    has_secret_shapes,
    redact_secret_shapes,
)
from utils import codex_review_gate, validate_handoff_docs

TEXT_HEALTH_PATHS: tuple[Path, ...] = (
    Path(".github/workflows/dual-model-gates.yml"),
    *validate_handoff_docs.REQUIRED_FILES,
    Path("utils/validate_handoff_docs.py"),
    Path("utils/codex_review_gate.py"),
    Path("utils/dual_model_pipeline_check.py"),
    Path("utils/prepare_deepseek_task.py"),
    Path("tests/test_validate_handoff_docs.py"),
    Path("tests/test_codex_review_gate.py"),
    Path("tests/test_dual_model_pipeline_check.py"),
    Path("tests/test_dual_model_gates_workflow.py"),
    Path("tests/test_prepare_deepseek_task.py"),
)

BLOCKED_TERM_HEALTH_PATHS: tuple[Path, ...] = (
    Path("utils/codex_review_gate.py"),
    Path("utils/validate_handoff_docs.py"),
    Path("utils/prepare_deepseek_task.py"),
    Path("utils/dual_model_pipeline_check.py"),
    Path("tests/test_codex_review_gate.py"),
    Path("tests/test_validate_handoff_docs.py"),
    Path("tests/test_prepare_deepseek_task.py"),
    Path("tests/test_dual_model_pipeline_check.py"),
    Path("tests/test_dual_model_gates_workflow.py"),
    Path("docs/handoff/codex_review_checklist.md"),
    Path("docs/handoff/deepseek_task_template.md"),
    Path("docs/handoff/deepseek_task_spec_schema.md"),
    Path("docs/handoff/dual_model_development_workflow.md"),
    Path("docs/handoff/deepseek_assignment_examples.md"),
    Path("test_plan.md"),
    Path("progress.md"),
)


@dataclass(frozen=True)
class CheckResult:
    """One pipeline health check result."""

    name: str
    ok: bool
    details: tuple[str, ...] = ()


def run_pipeline_check(root: Path, *, require_ready: bool = False) -> tuple[CheckResult, ...]:
    """Run the local dual-model workflow checks."""

    handoff_issues = validate_handoff_docs.validate_handoff_docs(root)
    review_result = codex_review_gate.run_review_gate(root, allow_waiting=not require_ready)
    review_details = _review_details(review_result)
    whitespace_details = _scan_whitespace(root=root, paths=TEXT_HEALTH_PATHS)
    blocked_term_details = _scan_text_files(
        root=root,
        paths=BLOCKED_TERM_HEALTH_PATHS,
        pattern=codex_review_gate.BLOCKED_TERM_PATTERN,
        redact=False,
    )
    key_details = _scan_text_files(
        root=root,
        paths=TEXT_HEALTH_PATHS,
        pattern=SECRET_KEY_PATTERN,
        redact=True,
        include_environment_secrets=True,
    )

    results = (
        CheckResult(name="handoff docs", ok=not handoff_issues, details=tuple(handoff_issues)),
        CheckResult(name="codex review gate", ok=not review_details, details=tuple(review_details)),
        CheckResult(name="text whitespace", ok=not whitespace_details, details=tuple(whitespace_details)),
        CheckResult(name="blocked term scan", ok=not blocked_term_details, details=tuple(blocked_term_details)),
        CheckResult(name="secret key shape scan", ok=not key_details, details=tuple(key_details)),
    )
    return tuple(_redact_check_result(result) for result in results)


def to_jsonable_results(results: Sequence[CheckResult]) -> dict[str, object]:
    """Return a JSON-serializable pipeline check report."""

    safe_results = tuple(_redact_check_result(result) for result in results)
    return {
        "ok": all(result.ok for result in safe_results),
        "checks": [
            {
                "name": result.name,
                "ok": result.ok,
                "details": list(result.details),
            }
            for result in safe_results
        ],
    }


def _redact_check_result(result: CheckResult) -> CheckResult:
    """净化 aggregate check 的名称与全部 detail 文本。

    参数:
        result: 可能包含敏感形状的聚合检查结果。

    返回值:
        保留检查状态、替换名称与 details 中所有敏感形状的结果。

    异常:
        无。
    """

    return CheckResult(
        name=redact_secret_shapes(result.name),
        ok=result.ok,
        details=tuple(
            redact_secret_shapes(detail)
            for detail in result.details
        ),
    )


def _review_details(result: codex_review_gate.ReviewGateResult) -> list[str]:
    details = list(result.issues)
    details.extend(_format_scan_hits("blocked term", result.blocked_term_hits))
    details.extend(_format_scan_hits("secret key", result.secret_key_hits))
    return details


def _format_scan_hits(label: str, hits: Sequence[codex_review_gate.ScanHit]) -> list[str]:
    return [f"{label}: {hit.path.as_posix()}:{hit.line_number}: {hit.preview}" for hit in hits]


def _resolve_scan_path(*, root: Path, relative_path: Path) -> tuple[Path, str | None]:
    """解析聚合文本扫描路径并拒绝真实目标越界。

    参数:
        root: 仓库根目录。
        relative_path: 待扫描的仓库相对路径。

    返回值:
        目标路径与可选 containment 诊断；诊断非空时调用方不得读取目标。

    异常:
        无；解析错误与仓库外真实目标均转换为稳定诊断。
    """

    path = root / relative_path
    if not validate_handoff_docs.is_path_within_repository_root(root=root, path=path):
        return path, f"{relative_path.as_posix()}: path must stay within repository root"
    return path, None


def _scan_whitespace(*, root: Path, paths: Sequence[Path]) -> list[str]:
    """扫描仓库文本的空白、换行与可读性问题。

    参数:
        root: 仓库根目录。
        paths: 待扫描的仓库相对路径。

    返回值:
        尾随空白、缺失末尾换行、非 UTF-8 或不可读文件的诊断列表。

    异常:
        无；文件解码与读取错误均转换为失败诊断。
    """

    details: list[str] = []
    for relative_path in paths:
        path, path_issue = _resolve_scan_path(root=root, relative_path=relative_path)
        if path_issue is not None:
            details.append(path_issue)
            continue
        if not path.is_file():
            continue
        try:
            raw_text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            details.append(f"{relative_path.as_posix()}: non-utf8 text")
            continue
        except OSError:
            details.append(f"{relative_path.as_posix()}: unreadable text")
            continue
        for line_number, line in enumerate(raw_text.splitlines(), start=1):
            if line.rstrip(" \t") != line:
                details.append(f"{relative_path.as_posix()}:{line_number}: trailing whitespace")
        if raw_text and not raw_text.endswith("\n"):
            details.append(f"{relative_path.as_posix()}: missing final newline")
    return details


def _scan_text_files(
    *,
    root: Path,
    paths: Sequence[Path],
    pattern: re.Pattern[str],
    redact: bool,
    include_environment_secrets: bool = False,
) -> list[str]:
    """扫描文本模式并将无法扫描的文件按 fail-closed 诊断返回。

    参数:
        root: 仓库根目录。
        paths: 待扫描的仓库相对路径。
        pattern: blocked-term 或 secret-key 正则表达式。
        redact: 命中时是否隐藏原始行文本。
        include_environment_secrets: 是否在静态模式之外检测当前环境凭据精确值。

    返回值:
        模式命中以及非 UTF-8、不可读文件的诊断列表。

    异常:
        无；文件解码与读取错误均转换为失败诊断。
    """

    details: list[str] = []
    for relative_path in paths:
        path, path_issue = _resolve_scan_path(root=root, relative_path=relative_path)
        if path_issue is not None:
            details.append(path_issue)
            continue
        if not path.is_file():
            continue
        try:
            raw_text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            details.append(f"{relative_path.as_posix()}: non-utf8 text")
            continue
        except OSError:
            details.append(f"{relative_path.as_posix()}: unreadable text")
            continue
        for line_number, line in enumerate(raw_text.splitlines(), start=1):
            matched = pattern.search(line) is not None
            if include_environment_secrets and not matched:
                matched = has_secret_shapes(line)
            if matched:
                preview = codex_review_gate.format_scan_preview(line=line, redact=redact)
                details.append(f"{relative_path.as_posix()}:{line_number}: {preview}")
    return details


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析 aggregate pipeline 命令行参数。

    参数:
        argv: 可选参数序列；省略时读取进程参数。

    返回值:
        已解析的 argparse namespace。

    异常:
        SystemExit: 请求帮助或参数无效时由 argparse 抛出。
    """

    parser = RedactingArgumentParser(
        description="Run local DeepSeek/Codex workflow health checks."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Require the DeepSeek outbox to be marked READY_FOR_CODEX_REVIEW.",
    )
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON report.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    results = run_pipeline_check(args.root, require_ready=args.require_ready)
    if args.json:
        print(json.dumps(to_jsonable_results(results), ensure_ascii=False, indent=2))
    else:
        _print_results(results)
    return 0 if all(result.ok for result in results) else 1


def _print_results(results: Sequence[CheckResult]) -> None:
    """安全输出 aggregate pipeline 的纯文本检查结果。

    参数:
        results: 可能由调用方直接构造、尚未净化的检查结果。

    返回值:
        无。

    异常:
        无。
    """

    safe_results = tuple(_redact_check_result(result) for result in results)
    print("# Dual-Model Pipeline Check")
    for result in safe_results:
        marker = "ok" if result.ok else "fail"
        print(f"[{marker}] {result.name}")
        for detail in result.details:
            print(f"  - {detail}")
    if all(result.ok for result in safe_results):
        print()
        print("dual-model pipeline check ok")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
