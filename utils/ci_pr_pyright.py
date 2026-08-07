"""CI PR pyright 诊断 ratchet。

在 pull_request CI 中仅检测 PR 引入的 pyright 类型错误，
允许基线上既有的诊断静默通过。

ratchet 策略（全仓 pyright + diff 行映射 + Counter 多重集）:
1. 始终对 HEAD 与 BASE（临时 git worktree）分别执行全仓
   ``pyright --outputjson``，即使没有 .py 文件变更也不跳过。
2. 使用 ``git diff --name-status --diff-filter=ACMRTD base head``
   （双点直接比较，不依赖 merge-base）计算变更文件并分类。
3. 按文件状态分别判定每条 HEAD 诊断：
   - 新增(A/C) → 全部诊断是 PR 引入。
   - 删除(D) → HEAD 中不应有诊断；若有则忽略。
   - 修改(M/T) → difflib 行映射；equal 块对齐 BASE 行后查 Counter。
   - 重命名(R) → old→new 路径映射 + 内容 diff 行映射。
   - 未变更 → identity 行映射 + Counter 消耗匹配。
4. BASE 诊断使用 ``collections.Counter`` 多重集，每条 BASE
   诊断最多消耗一次，防止一条既存诊断放行多条 HEAD 重复。
5. 诊断指纹为五元组 ``(文件, 1-indexed行, severity, rule, message)``。
   pyright JSON 中 ``range.start.line`` 为 0-indexed，统一转为 1-indexed。
6. Fail-closed：--head 与工作树 commit 不一致、pyright 异常退出、
   JSON 结构不合法时立即非零退出。

用法:
  python -m utils.ci_pr_pyright --base origin/main --head "$(git rev-parse HEAD)"

严格类型约束：
  本模块不引入 Any/object 签名。pyright JSON 结构通过 TypedDict
  精确定义并在 json.loads 后校验。
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import difflib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NotRequired, TypeAlias, TypedDict

# ── 递归 JSON 类型别名（零 Any/object）──────────────────────────

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
"""递归 JSON 值类型，替代宽泛的 object/Any。"""

JsonObject: TypeAlias = dict[str, JsonValue]
"""JSON 对象类型别名。"""

# ══════════════════════════════════════════════════════════════════
# pyright JSON schema（TypedDict，零宽类型）
# ══════════════════════════════════════════════════════════════════


class _PyrightPosition(TypedDict):
    """pyright JSON 中的行列位置。"""

    line: int  # 0-indexed
    character: int


class _PyrightRange(TypedDict):
    """pyright JSON 中的起止区间。"""

    start: _PyrightPosition
    end: _PyrightPosition


class _PyrightDiagnostic(TypedDict):
    """pyright JSON 中的单条诊断。"""

    file: str
    severity: str
    message: str
    range: _PyrightRange
    rule: NotRequired[str]


# 诊断五元组：(文件相对路径, 1-indexed 行号, severity, rule, message)
DiagnosticTuple = tuple[str, int, str, str, str]


# ══════════════════════════════════════════════════════════════════
# 变更集数据类
# ══════════════════════════════════════════════════════════════════


@dataclasses.dataclass
class _ChangeSet:
    """base→head 间的 Python 文件变更分类。

    属性:
        new_files: 新增或复制文件（status A/C）的相对路径集合。
        modified_files: 修改文件（status M/T）的相对路径列表。
        deleted_files: 删除文件（status D）的相对路径集合。
        rename_new_to_old: 重命名文件 new_path → old_path 映射。
        has_any_py_changes: 是否有任何 .py 文件变更。
    """

    new_files: set[str] = dataclasses.field(default_factory=set)
    modified_files: list[str] = dataclasses.field(default_factory=list)
    deleted_files: set[str] = dataclasses.field(default_factory=set)
    rename_new_to_old: dict[str, str] = dataclasses.field(default_factory=dict)
    has_any_py_changes: bool = False


@dataclasses.dataclass
class _FileDiffInfo:
    """单个修改文件的 diff 行映射信息。

    属性:
        changed_lines: HEAD 中被 insert/replace 的行号集合（1-indexed）。
        line_map: HEAD 行号 → BASE 行号的映射（1-indexed）；
            equal 块有映射，insert/replace 块为 None。
        base_exists: BASE 是否包含此文件。
    """

    changed_lines: set[int]
    line_map: dict[int, int | None]
    base_exists: bool


# ══════════════════════════════════════════════════════════════════
# git 辅助
# ══════════════════════════════════════════════════════════════════


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """在仓库中运行 git 命令并捕获文本输出。

    参数:
        *args: git 命令行参数。
        cwd: 工作目录；为 ``None`` 时使用当前目录。

    返回值:
        已完成的子进程结果（check=True, capture_output=True, text=True）。

    异常:
        subprocess.CalledProcessError: git 命令失败时抛出。
    """
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
    )


def _ensure_ref_available(ref: str) -> None:
    """确保 git ref 在本地可用；若浅克隆缺失则自动 fetch。

    参数:
        ref: git 提交 SHA。

    异常:
        subprocess.CalledProcessError: ref 无法 fetch 时抛出。
    """
    result = subprocess.run(
        ["git", "cat-file", "-e", ref],
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return
    subprocess.run(
        ["git", "fetch", "--no-tags", "--depth=1", "origin", ref],
        check=True,
        capture_output=True,
    )


def _verify_and_resolve_head(head: str) -> str:
    """验证工作树 commit 与 --head 一致并返回 resolved SHA。

    Fail-closed：不一致时退出码 2；无法 resolve 时退出码 2。

    参数:
        head: 预期的 git ref（可以是 SHA、分支名或 HEAD）。

    返回值:
        解析后的完整 head SHA。

    异常:
        SystemExit: 不一致或解析失败时退出。
    """
    actual = _git("rev-parse", "HEAD").stdout.strip()
    resolved = _git("rev-parse", "--verify", head).stdout.strip()

    if actual != resolved:
        print(
            f"FATAL: 工作树 commit ({actual[:12]}) 与 --head ({resolved[:12]}) 不一致。"
            "\n请确保 CI checkout 的 commit 与 --head 参数匹配。",
            file=sys.stderr,
        )
        sys.exit(2)

    return resolved


def _get_file_content_at_ref(ref: str, path: str) -> str | None:
    """获取指定 git ref 上的文件内容。

    参数:
        ref: git 提交 SHA。
        path: 仓库相对文件路径。

    返回值:
        UTF-8 文本内容；文件不存在时返回 ``None``。
    """
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


# ══════════════════════════════════════════════════════════════════
# diff 解析与行映射
# ══════════════════════════════════════════════════════════════════


def _parse_changed_entries(base: str, head: str) -> _ChangeSet:
    """解析 base→head（双点直接比较）间的 Python 文件变更。

    使用双点 ``base head`` 而非三点 ``base...head``，避免在
    浅克隆中因缺少 merge-base 导致失败。

    参数:
        base: 基线 ref。
        head: PR 分支 ref。

    返回值:
        ``_ChangeSet`` 分类结果。

    异常:
        subprocess.CalledProcessError: git diff 失败时抛出。
    """
    result = _git(
        "diff", "--name-status", "--diff-filter=ACMRTD", base, head,
    )

    change = _ChangeSet()
    for line_num, line in enumerate(result.stdout.strip().splitlines(), start=1):
        if not line:
            continue
        parts = line.split("\t")
        status_field = parts[0]
        status_letter = status_field[0]

        if status_letter == "R":
            if len(parts) < 3:
                print(
                    f"FATAL: git diff name-status 行 {line_num} 格式异常（R 需三列）: {line!r}",
                    file=sys.stderr,
                )
                sys.exit(2)
            new_path = Path(parts[2])
            old_path = Path(parts[1])
        elif status_letter == "C":
            if len(parts) < 3:
                print(
                    f"FATAL: git diff name-status 行 {line_num} 格式异常（C 需三列）: {line!r}",
                    file=sys.stderr,
                )
                sys.exit(2)
            new_path = Path(parts[2])
            old_path = None  # 复制源不参与比较；新文件全部诊断是新增
        elif status_letter in ("A", "M", "T", "D"):
            if len(parts) < 2:
                print(
                    f"FATAL: git diff name-status 行 {line_num} 格式异常（需至少两列）: {line!r}",
                    file=sys.stderr,
                )
                sys.exit(2)
            new_path = Path(parts[1])
            old_path = None
        else:
            print(
                f"FATAL: git diff name-status 行 {line_num} 未知状态 {status_letter!r}: {line!r}",
                file=sys.stderr,
            )
            sys.exit(2)

        if new_path.suffix != ".py":
            continue

        head_rel = new_path.as_posix()
        change.has_any_py_changes = True

        if status_letter in ("A", "C"):
            change.new_files.add(head_rel)
        elif status_letter == "D":
            change.deleted_files.add(head_rel)
        elif status_letter == "R" and old_path is not None:
            change.modified_files.append(head_rel)
            change.rename_new_to_old[head_rel] = old_path.as_posix()
        else:
            change.modified_files.append(head_rel)

    return change


def _build_diff_opcodes(
    base_content: str,
    head_content: str,
) -> list[tuple[str, int, int, int, int]]:
    """返回 base 与 head 文本之间的 difflib opcode 列表。

    所有索引均为 0-indexed 行号。
    opcode 标签: ``'equal'`` / ``'replace'`` / ``'insert'`` / ``'delete'``。

    参数:
        base_content: BASE 文件内容。
        head_content: HEAD 文件内容。

    返回值:
        ``(tag, i1, i2, j1, j2)`` 列表。
    """
    base_lines = base_content.splitlines(keepends=True)
    head_lines = head_content.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(None, base_lines, head_lines)
    raw = matcher.get_opcodes()
    return [(str(tag), i1, i2, j1, j2) for tag, i1, i2, j1, j2 in raw]


def _compute_changed_head_lines(
    opcodes: list[tuple[str, int, int, int, int]],
) -> set[int]:
    """从 opcode 列表计算被修改或新增的 HEAD 行号（1-indexed）。

    参数:
        opcodes: ``_build_diff_opcodes`` 返回值。

    返回值:
        insert 或 replace 覆盖的 HEAD 行号集合（1-indexed）。
    """
    changed: set[int] = set()
    for tag, _i1, _i2, j1, j2 in opcodes:
        if tag in ("insert", "replace"):
            for j in range(j1, j2):
                changed.add(j + 1)  # 0-indexed → 1-indexed
    return changed


def _build_head_to_base_line_map(
    opcodes: list[tuple[str, int, int, int, int]],
) -> dict[int, int | None]:
    """建立 HEAD 行号 → BASe 行号的 1-indexed 映射。

    equal 块中的行保留对应关系；insert/replace 块中的 HEAD 行映射为 ``None``。

    参数:
        opcodes: ``_build_diff_opcodes`` 返回值。

    返回值:
        ``{head_line_1i: base_line_1i | None}``。
    """
    mapping: dict[int, int | None] = {}
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            for offset in range(j2 - j1):
                mapping[j1 + offset + 1] = i1 + offset + 1
        elif tag in ("insert", "replace"):
            for j in range(j1, j2):
                mapping[j + 1] = None
    return mapping


def _build_file_diff_infos(
    change: _ChangeSet,
    base: str,
    repo_root: Path,
) -> dict[str, _FileDiffInfo]:
    """为所有修改文件构建 diff 行映射信息。

    参数:
        change: 变更集。
        base: 基线 ref。
        repo_root: 仓库根目录。

    返回值:
        ``{head_rel_path: _FileDiffInfo}``。
    """
    infos: dict[str, _FileDiffInfo] = {}

    for head_rel in change.modified_files:
        base_old = change.rename_new_to_old.get(head_rel)
        base_path = base_old if base_old is not None else head_rel
        base_text = _get_file_content_at_ref(base, base_path)

        if base_text is None:
            infos[head_rel] = _FileDiffInfo(
                changed_lines=set(),
                line_map={},
                base_exists=False,
            )
            continue

        head_text = (repo_root / head_rel).read_text(encoding="utf-8")
        opcodes = _build_diff_opcodes(base_text, head_text)
        infos[head_rel] = _FileDiffInfo(
            changed_lines=_compute_changed_head_lines(opcodes),
            line_map=_build_head_to_base_line_map(opcodes),
            base_exists=True,
        )

    return infos


# ══════════════════════════════════════════════════════════════════
# pyright 运行与诊断索引
# ══════════════════════════════════════════════════════════════════


def _run_pyright_json() -> list[_PyrightDiagnostic]:
    """运行全仓 pyright 并返回经过字段级结构校验的诊断列表（fail-closed）。

    返回值:
        经过 ``_validate_and_build_diagnostics`` 校验的诊断列表。

    异常:
        SystemExit: pyright 进程异常、非 JSON、结构非法→退出 3。
    """
    result = subprocess.run(
        ["pyright", "--outputjson"],
        capture_output=True, text=True, check=False,
    )

    if result.returncode not in (0, 1):
        print(
            f"FATAL: pyright 进程异常退出 (code={result.returncode})",
            file=sys.stderr,
        )
        if result.stderr:
            print(result.stderr[:2000], file=sys.stderr)
        sys.exit(3)

    try:
        raw: JsonValue = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(
            "FATAL: pyright 输出无法解析为 JSON",
            f"\n--- stdout ---\n{result.stdout[:800]}",
            f"\n--- stderr ---\n{result.stderr[:800]}",
            file=sys.stderr,
        )
        sys.exit(3)

    return _validate_and_build_diagnostics(raw)


def _validate_and_build_diagnostics(raw: JsonValue) -> list[_PyrightDiagnostic]:
    """校验 pyright JSON 结构并逐字段验证后返回诊断列表。

    从 ``json.loads`` 的 ``JsonValue`` 出发，经 isinstance 逐层
    收窄至 ``list[_PyrightDiagnostic]``。任何字段缺失或类型错误
    均 fail-closed 退出 3。

    参数:
        raw: ``json.loads`` 解析结果（JsonValue）。

    返回值:
        经过完全字段校验的 ``list[_PyrightDiagnostic]``。

    异常:
        SystemExit: 结构非法→退出 3。
    """
    if not isinstance(raw, dict):
        print("FATAL: pyright JSON 根对象不是 dict", file=sys.stderr)
        sys.exit(3)
    if "generalDiagnostics" not in raw:
        print("FATAL: pyright JSON 缺少 generalDiagnostics", file=sys.stderr)
        sys.exit(3)

    diags_raw = raw["generalDiagnostics"]
    if not isinstance(diags_raw, list):
        print("FATAL: pyright JSON generalDiagnostics 不是 list", file=sys.stderr)
        sys.exit(3)

    validated: list[_PyrightDiagnostic] = []
    for i, item in enumerate(diags_raw):
        if not isinstance(item, dict):
            print(f"FATAL: 诊断 [{i}] 不是 dict", file=sys.stderr)
            sys.exit(3)
        for key in ("file", "severity", "message"):
            if key not in item or not isinstance(item[key], str):
                print(f"FATAL: 诊断 [{i}] 字段 {key} 缺失或不是 str", file=sys.stderr)
                sys.exit(3)
        if "rule" in item and not isinstance(item["rule"], str):
            print(f"FATAL: 诊断 [{i}] rule 不是 str", file=sys.stderr)
            sys.exit(3)

        rng = item.get("range")
        if not isinstance(rng, dict):
            print(f"FATAL: 诊断 [{i}] range 不是 dict", file=sys.stderr)
            sys.exit(3)
        for pos_key in ("start", "end"):
            pos = rng.get(pos_key)
            if not isinstance(pos, dict):
                print(f"FATAL: 诊断 [{i}] range.{pos_key} 不是 dict", file=sys.stderr)
                sys.exit(3)
            for int_key in ("line", "character"):
                val = pos.get(int_key)
                if not isinstance(val, int) or isinstance(val, bool):
                    print(f"FATAL: 诊断 [{i}] range.{pos_key}.{int_key} 不是 int（或为 bool）", file=sys.stderr)
                    sys.exit(3)
                if val < 0:
                    print(f"FATAL: 诊断 [{i}] range.{pos_key}.{int_key} 为负数", file=sys.stderr)
                    sys.exit(3)

        # 逐字段 extract + isinstance 收窄（避免对 JsonValue 链式下标）
        file_val = item["file"]
        sev_val = item["severity"]
        msg_val = item["message"]
        assert isinstance(file_val, str)
        assert isinstance(sev_val, str)
        assert isinstance(msg_val, str)

        start_pos = rng["start"]
        end_pos = rng["end"]
        assert isinstance(start_pos, dict)
        assert isinstance(end_pos, dict)

        start_line = start_pos["line"]
        start_char = start_pos["character"]
        end_line = end_pos["line"]
        end_char = end_pos["character"]
        assert isinstance(start_line, int) and not isinstance(start_line, bool)
        assert isinstance(start_char, int) and not isinstance(start_char, bool)
        assert isinstance(end_line, int) and not isinstance(end_line, bool)
        assert isinstance(end_char, int) and not isinstance(end_char, bool)
        assert start_line >= 0
        assert start_char >= 0
        assert end_line >= 0
        assert end_char >= 0

        diag: _PyrightDiagnostic = {
            "file": file_val,
            "severity": sev_val,
            "message": msg_val,
            "range": {
                "start": {"line": start_line, "character": start_char},
                "end": {"line": end_line, "character": end_char},
            },
        }
        if "rule" in item:
            rule_val = item["rule"]
            assert isinstance(rule_val, str)
            diag["rule"] = rule_val
        validated.append(diag)

    return validated


def _normalize_diagnostic_tuple(
    diag: _PyrightDiagnostic,
    *,
    worktree_root: Path | None = None,
    repo_root: Path,
) -> DiagnosticTuple:
    """将单条 pyright 诊断归一化为可比五元组。

    pyright JSON 中 ``range.start.line`` 为 **0-indexed**，
    本函数统一转为 **1-indexed** 以与 diff 行映射对齐。

    参数:
        diag: pyright 诊断。
        worktree_root: 临时工作树根目录；提供时移除该前缀。
        repo_root: 仓库根目录；用于从绝对路径提取相对路径。

    返回值:
        ``(relative_file, line_1i, severity, rule, message)``。
    """
    file_path = Path(diag["file"]).resolve()
    if worktree_root is not None:
        _resolved_wt = worktree_root.resolve()
        try:
            file_path = file_path.relative_to(_resolved_wt)
        except ValueError:
            pass
    try:
        rel = file_path.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        rel = file_path.as_posix()

    line_1i = diag["range"]["start"]["line"] + 1  # 0-indexed → 1-indexed
    return (
        rel,
        line_1i,
        diag.get("severity", "error"),
        diag.get("rule", ""),
        diag["message"].strip(),
    )


def _build_diagnostic_counter(
    diagnostics: list[_PyrightDiagnostic],
    *,
    worktree_root: Path | None = None,
    repo_root: Path,
) -> collections.Counter[DiagnosticTuple]:
    """将诊断列表转化为 ``Counter`` 多重集，每条诊断可消耗一次。

    参数:
        diagnostics: pyright 诊断列表。
        worktree_root: 临时工作树根目录；提供时移除该前缀。
        repo_root: 仓库根目录。

    返回值:
        ``Counter[DiagnosticTuple]``，total() 为诊断总数。
    """
    counter: collections.Counter[DiagnosticTuple] = collections.Counter()
    for d in diagnostics:
        counter[_normalize_diagnostic_tuple(
            d,
            worktree_root=worktree_root,
            repo_root=repo_root,
        )] += 1
    return counter


def _run_base_pyright_and_build_counter(
    base: str,
    repo_root: Path,
    old_to_new: dict[str, str],
) -> collections.Counter[DiagnosticTuple]:
    """在 BASE 临时工作树上运行全仓 pyright 并返回 Counter。

    参数:
        base: 基线 git ref。
        repo_root: 仓库根目录。
        old_to_new: 重命名映射 old_name → new_name。

    返回值:
        BASE 诊断 Counter。

    异常:
        SystemExit: pyright 失败时退出码 3。
    """
    base_counter: collections.Counter[DiagnosticTuple] = collections.Counter()

    with tempfile.TemporaryDirectory(prefix="ci_pyright_base_") as tmpdir:
        worktree = Path(tmpdir) / "base"
        _git("worktree", "add", "--detach", str(worktree), base)
        try:
            _old_cwd = os.getcwd()
            try:
                os.chdir(str(worktree))
                base_raw = _run_pyright_json()
            finally:
                os.chdir(_old_cwd)

            _resolved_wt = worktree.resolve()
            _resolved_repo = repo_root.resolve()
            remapped: list[_PyrightDiagnostic] = []
            for d in base_raw:
                d_file = Path(d["file"]).resolve()
                try:
                    rel = d_file.relative_to(_resolved_wt).as_posix()
                except ValueError:
                    try:
                        rel = d_file.relative_to(_resolved_repo).as_posix()
                    except ValueError:
                        rel = d_file.as_posix()
                rel = old_to_new.get(rel, rel)
                # 构造新诊断字典以避免 TypedDict 键赋值问题
                new_diag: _PyrightDiagnostic = {
                    "file": rel,
                    "severity": d["severity"],
                    "message": d["message"],
                    "range": d["range"],
                }
                if "rule" in d:
                    new_diag["rule"] = d["rule"]
                remapped.append(new_diag)

            base_counter = _build_diagnostic_counter(
                remapped,
                repo_root=repo_root,
            )
        finally:
            _git("worktree", "remove", "--force", str(worktree))

    return base_counter


# ══════════════════════════════════════════════════════════════════
# ratchet 判定
# ══════════════════════════════════════════════════════════════════


def _classify_head_diagnostics(
    head_diags: list[_PyrightDiagnostic],
    *,
    change: _ChangeSet,
    file_diff_infos: dict[str, _FileDiffInfo],
    base_counter: collections.Counter[DiagnosticTuple],
    repo_root: Path,
) -> tuple[list[_PyrightDiagnostic], int]:
    """将 HEAD 诊断分类为 PR 新增与既存。

    参数:
        head_diags: HEAD 全仓 pyright 诊断。
        change: 变更集。
        file_diff_infos: 修改文件的 diff 行映射。
        base_counter: BASE 诊断 Counter（会被消耗）。
        repo_root: 仓库根目录。

    返回值:
        ``(new_errors, preexisting_count)``。
    """
    all_changed = (
        change.new_files
        | set(change.modified_files)
        | change.deleted_files
    )
    remaining = collections.Counter(base_counter)
    new_errors: list[_PyrightDiagnostic] = []
    preexisting = 0

    for d in head_diags:
        head_tuple = _normalize_diagnostic_tuple(d, repo_root=repo_root)
        head_rel, head_line, severity, rule, message = head_tuple

        # 删除文件不应出现在 HEAD 中
        if head_rel in change.deleted_files:
            continue

        # 新增文件 → 全部诊断是 PR 引入
        if head_rel in change.new_files:
            new_errors.append(d)
            continue

        # 未变更文件 → identity 行映射 + Counter 消耗
        if head_rel not in all_changed:
            if remaining[head_tuple] > 0:
                remaining[head_tuple] -= 1
                preexisting += 1
                continue
            new_errors.append(d)
            continue

        # 修改/重命名文件 → 行映射判定
        diff_info = file_diff_infos.get(head_rel)
        if diff_info is None or not diff_info.base_exists:
            new_errors.append(d)
            continue

        if head_line in diff_info.changed_lines:
            # insert/replace 块 → PR 引入（零漏报）
            new_errors.append(d)
            continue

        base_line = diff_info.line_map.get(head_line)
        if base_line is None:
            new_errors.append(d)
            continue

        # equal 块 → 映射到 BASE 行并消耗 Counter
        base_tuple = (head_rel, base_line, severity, rule, message)
        if remaining[base_tuple] > 0:
            remaining[base_tuple] -= 1
            preexisting += 1
            continue
        new_errors.append(d)

    return new_errors, preexisting


def _format_new_errors(
    new_errors: list[_PyrightDiagnostic],
    repo_root: Path,
) -> str:
    """格式化新增诊断列表为可读文本。

    参数:
        new_errors: PR 新增诊断列表。
        repo_root: 仓库根目录。

    返回值:
        按文件分组的格式化文本。
    """
    new_by_file: dict[str, list[_PyrightDiagnostic]] = {}
    for d in new_errors:
        fp = Path(d["file"]).resolve()
        try:
            rel = fp.relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            rel = fp.as_posix()
        new_by_file.setdefault(rel, []).append(d)

    lines: list[str] = []
    for file_name in sorted(new_by_file):
        lines.append(f"  {file_name}:")
        for d in sorted(new_by_file[file_name], key=lambda x: x["range"]["start"]["line"]):
            line_1i = d["range"]["start"]["line"] + 1
            rule = d.get("rule", "")
            message = d["message"].split("\n")[0]
            lines.append(f"    L{line_1i} [{rule}] {message}")
        lines.append("")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> None:
    """CI PR pyright 诊断 ratchet 入口。

    编排：解析参数 → 验证 checkout → 分类变更 → 构建行映射 →
    运行 HEAD/BASE pyright → 分类诊断 → 输出结果。

    参数:
        argv: 命令行参数列表；为 ``None`` 时使用 ``sys.argv[1:]``。

    异常:
        无；通过 ``sys.exit`` 返回状态码。
    """
    parser = argparse.ArgumentParser(
        description="CI PR pyright 诊断 ratchet — 仅报告 PR 新增类型错误"
    )
    parser.add_argument("--base", required=True, help="基线 git ref")
    parser.add_argument("--head", required=True, help="当前 checkout 的 git ref")
    args = parser.parse_args(argv)

    base: str = args.base
    head: str = args.head
    repo_root = Path.cwd()

    # 1. 验证 checkout 一致性
    head = _verify_and_resolve_head(head)
    _ensure_ref_available(base)

    # 2. 解析变更
    change = _parse_changed_entries(base, head)
    _print_change_summary(change)

    # 3. 构建行映射（仅修改文件）
    file_diff_infos = _build_file_diff_infos(change, base, repo_root)

    old_to_new: dict[str, str] = {
        old: new for new, old in change.rename_new_to_old.items()
    }

    # 4. HEAD 全仓 pyright
    print("\n[1/2] 全仓 pyright on HEAD ...")
    head_diags = _run_pyright_json()
    head_counter = _build_diagnostic_counter(head_diags, repo_root=repo_root)
    print(f"  HEAD 诊断: {head_counter.total()} 条")

    # 5. BASE 全仓 pyright
    print("\n[2/2] 全仓 pyright on BASE（临时工作树）...")
    base_counter = _run_base_pyright_and_build_counter(base, repo_root, old_to_new)
    print(f"  BASE 诊断: {base_counter.total()} 条")

    # 6. ratchet 判定
    new_errors, preexisting = _classify_head_diagnostics(
        head_diags,
        change=change,
        file_diff_infos=file_diff_infos,
        base_counter=base_counter,
        repo_root=repo_root,
    )

    # 7. 输出
    if not new_errors:
        print("\n✅ 无 PR 新增 pyright 诊断。")
        print(f"   HEAD 共 {head_counter.total()} 条，BASE 共 {base_counter.total()} 条")
        print(f"   经行映射/Counter 确认为既存 {preexisting} 条")
        sys.exit(0)

    print(f"\n❌ PR 引入 {len(new_errors)} 条新 pyright 诊断:\n")
    print(_format_new_errors(new_errors, repo_root))
    print(
        f"共 {len(new_errors)} 条新增诊断 "
        f"（HEAD {head_counter.total()}，"
        f"经行映射/Counter 确认为既存 {preexisting}，"
        f"BASE {base_counter.total()}）"
    )
    sys.exit(1)


def _print_change_summary(change: _ChangeSet) -> None:
    """打印变更文件摘要。

    参数:
        change: 变更集。
    """
    total = len(change.new_files) + len(change.modified_files) + len(change.deleted_files)
    if total == 0:
        print("仓库无 .py 文件差异；仍将运行全仓 pyright 比较。")
        return

    print(f"变更 Python 文件 ({total}):")
    for f in sorted(change.new_files):
        print(f"  A {f}")
    for f in sorted(change.modified_files):
        print(f"  M {f}")
    for f in sorted(change.deleted_files):
        print(f"  D {f}")

    if change.new_files:
        print(f"\n新增文件 ({len(change.new_files)})，全部诊断视为 PR 引入。")
    if change.deleted_files:
        print(f"删除文件 ({len(change.deleted_files)})，不参与诊断比较。")


if __name__ == "__main__":
    main()
