"""utils.ci_pr_pyright 单元测试。

覆盖：双点 diff 解析、diff 行映射（equal/insert/replace/delete）、
诊断 0→1 索引转换、行偏移不误报、同位置同 rule 不同 message 不漏报、
修改行一律报新、rename、delete、空变更、Counter 多重集消耗、
未变更文件 identity 匹配、changed-producer→unchanged-consumer 新增诊断、
fail-closed（--head 不匹配、pyright 异常退出、JSON 缺失字段）、
浅克隆直接比较、无 .py 变更时仍全仓比较。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import NotRequired, TypedDict

import pytest

from utils import ci_pr_pyright as module

pytestmark = pytest.mark.unit


# ── 类型辅助（零 Any）──────────────────────────────────────────


class _TD(TypedDict):
    """测试用诊断 TypedDict，与 _PyrightDiagnostic 结构一致。"""

    file: str
    severity: str
    message: str
    range: _TDRange
    rule: NotRequired[str]


class _TDPos(TypedDict):
    line: int
    character: int


class _TDRange(TypedDict):
    start: _TDPos
    end: _TDPos


def _diag(
    file: str,
    line_0i: int,
    rule: str = "r",
    message: str = "m",
    severity: str = "error",
) -> _TD:
    """构造一条 pyright 格式诊断。line_0i 为 0-indexed（匹配真实 pyright JSON）。

    参数:
        file: 诊断文件路径。
        line_0i: 0-indexed 行号。
        rule: pyright 规则名。
        message: 诊断消息。
        severity: 严重级别。

    返回值:
        符合 _TD 结构的诊断字典。

    异常:
        无。
    """
    d: _TD = {
        "file": file,
        "severity": severity,
        "message": message,
        "range": {
            "start": {"line": line_0i, "character": 0},
            "end": {"line": line_0i, "character": 10},
        },
    }
    if rule:
        d["rule"] = rule
    return d


def _fake_pyright_output(diagnostics: list[_TD]) -> str:
    """将诊断列表序列化为 pyright JSON 格式字符串。

    参数:
        diagnostics: 诊断列表。

    返回值:
        pyright --outputjson 格式的 JSON 字符串。

    异常:
        无。
    """
    return json.dumps({
        "version": "1.1.408",
        "time": "0",
        "generalDiagnostics": diagnostics,
        "summary": {},
    })


# ── _parse_changed_entries（双点 diff）─────────────────────────


class TestParseChangedEntries:
    """git 临时仓库中 _parse_changed_entries 的边界测试。"""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """在临时 git 仓库中准备 base→head 变更。

        参数:
            tmp_path: pytest 临时目录夹具。
            monkeypatch: pytest monkeypatch 夹具。
        """
        self.repo = tmp_path / "repo"
        self.repo.mkdir()
        monkeypatch.chdir(self.repo)
        _git(self.repo, "init", "-b", "main")
        _git(self.repo, "config", "user.email", "test@ci.local")
        _git(self.repo, "config", "user.name", "CI Test")

        (self.repo / "keep.py").write_text("# unchanged\n")
        (self.repo / "mod.py").write_text("x: int = 1\n")
        (self.repo / "old_name.py").write_text("y = 2\n")
        (self.repo / "del_me.py").write_text("z = 3\n")
        (self.repo / "my file.py").write_text("a = 1\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-m", "base")

        self.base = _git_rev_parse(self.repo, "HEAD")

        (self.repo / "mod.py").write_text("x: str = 'a'\n")
        (self.repo / "new_file.py").write_text("w = 4\n")
        (self.repo / "old_name.py").rename(self.repo / "new_name.py")
        (self.repo / "del_me.py").unlink()
        (self.repo / "README.md").write_text("# hi\n")
        (self.repo / "my file.py").write_text("b = 2\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-m", "changes")

        self.head = _git_rev_parse(self.repo, "HEAD")

    def test_includes_added_modified_renamed_and_deleted(self) -> None:
        """验证新增、修改、重命名、删除文件均被识别。"""
        change = module._parse_changed_entries(self.base, self.head)
        assert "new_file.py" in change.new_files
        assert "mod.py" in change.modified_files
        assert "del_me.py" in change.deleted_files
        # 重命名
        assert change.rename_new_to_old.get("new_name.py") == "old_name.py"
        assert "new_name.py" in change.modified_files

    def test_has_any_py_changes_true(self) -> None:
        """验证存在 .py 变更时 has_any_py_changes 为 True。"""
        change = module._parse_changed_entries(self.base, self.head)
        assert change.has_any_py_changes is True

    def test_excludes_non_python(self) -> None:
        """验证非 Python 文件不出现在变更集中。"""
        change = module._parse_changed_entries(self.base, self.head)
        all_files = (change.new_files | set(change.modified_files) | change.deleted_files)
        assert "README.md" not in all_files

    def test_no_changes_returns_empty(self) -> None:
        """验证相同 ref 无变更时 has_any_py_changes 为 False。"""
        change = module._parse_changed_entries(self.head, self.head)
        assert change.has_any_py_changes is False

    def test_space_in_filename(self) -> None:
        """验证包含空格的文件名可被正确识别。"""
        change = module._parse_changed_entries(self.base, self.head)
        all_files = (change.new_files | set(change.modified_files) | change.deleted_files)
        assert "my file.py" in all_files


# ── 模块级 stub（替代 lambda 与嵌套类）─────────────────────────


class _StaticSubprocessRunStub:
    """替换 subprocess.run 的静态 callable stub。

    属性:
        returncode: 固定退出码。
        stdout: 固定标准输出。
        stderr: 固定标准错误。
    """

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        """创建固定返回值 stub。

        参数:
            returncode: 进程退出码。
            stdout: 标准输出文本。
            stderr: 标准错误文本。
        """
        self.returncode: int = returncode
        self.stdout: str = stdout
        self.stderr: str = stderr

    def __call__(
        self,
        cmd: list[str],
        capture_output: bool = False,
        text: bool = False,
        check: bool = True,
        cwd: str | Path | None = None,
    ) -> _StaticSubprocessRunStub:
        """返回自身，使 ``subprocess.run(...)`` 调用有效。

        参数:
            cmd: 命令行参数列表（忽略）。
            capture_output: 忽略。
            text: 忽略。
            check: 忽略。
            cwd: 忽略。

        返回值:
            自身实例。
        """
        return self


class _FakeCompletedProcess:
    """模拟 subprocess.CompletedProcess，供 _StaticGitStub 使用。

    属性:
        stdout: 标准输出文本。
        stderr: 标准错误文本。
        returncode: 进程退出码。
    """

    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0) -> None:
        """创建模拟进程结果。

        参数:
            stdout: 标准输出。
            stderr: 标准错误。
            returncode: 退出码。
        """
        self.stdout: str = stdout
        self.stderr: str = stderr
        self.returncode: int = returncode


class _StaticGitStub:
    """替换 _git 的静态 stub，返回固定 diff 输出。

    属性:
        _stdout: 预设的标准输出。
    """

    def __init__(self, stdout: str) -> None:
        """创建固定输出 stub。

        参数:
            stdout: 预设的标准输出文本。
        """
        self._stdout: str = stdout

    def __call__(self, *args: str, cwd: Path | None = None) -> _FakeCompletedProcess:
        """返回预设 stdout 的 _FakeCompletedProcess。

        参数:
            *args: git 参数（忽略）。
            cwd: 工作目录（忽略）。

        返回值:
            预设 stdout 的模拟进程结果。
        """
        return _FakeCompletedProcess(stdout=self._stdout)


# ══════════════════════════════════════════════════════════════════
# JSON 结构校验 fail-closed
# ══════════════════════════════════════════════════════════════════


class TestValidateAndBuildDiagnosticsFailClosed:
    """_validate_and_build_diagnostics 对非法 JSON 结构的 fail-closed 测试。"""

    def test_root_not_dict_exits_3(self) -> None:
        """根对象不是 dict → exit 3。"""
        with pytest.raises(SystemExit) as exc:
            module._validate_and_build_diagnostics(42)
        assert exc.value.code == 3

    @pytest.mark.parametrize("invalid_json", [
        {"no_diags": 1},
        {"generalDiagnostics": "not_list"},
        {"generalDiagnostics": [{"file": 1, "severity": "e", "message": "m", "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}}]},
        {"generalDiagnostics": [{"file": "f", "severity": "e", "message": "m", "range": "not_dict"}]},
        {"generalDiagnostics": [{"file": "f", "severity": "e", "message": "m", "range": {"start": "not_dict", "end": {"line": 0, "character": 0}}}]},
        {"generalDiagnostics": [{"file": "f", "severity": "e", "message": "m", "range": {"start": {"line": "not_int", "character": 0}, "end": {"line": 0, "character": 0}}}]},
        {"generalDiagnostics": [{"file": "f", "severity": "e", "message": "m", "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}, "rule": 1}]},
    ])
    def test_invalid_json_exits_3(self, invalid_json: module.JsonValue) -> None:
        """多种非法 JSON 结构均 exit 3。

        参数:
            invalid_json: 故意非法的 pyright JSON 结构。
        """
        with pytest.raises(SystemExit) as exc:
            module._validate_and_build_diagnostics(invalid_json)
        assert exc.value.code == 3

    def test_bool_rejected_as_int_exits_3(self) -> None:
        """bool 值（JSON true）被 line/character 校验拒绝 → exit 3。"""
        data = json.loads(
            '{"generalDiagnostics":[{"file":"f","severity":"e","message":"m",'
            '"range":{"start":{"line":true,"character":0},"end":{"line":0,"character":0}}}]}'
        )
        with pytest.raises(SystemExit) as exc:
            module._validate_and_build_diagnostics(data)
        assert exc.value.code == 3

    def test_negative_line_exits_3(self) -> None:
        """负数行号被拒绝 → exit 3。"""
        data = json.loads(
            '{"generalDiagnostics":[{"file":"f","severity":"e","message":"m",'
            '"range":{"start":{"line":-1,"character":0},"end":{"line":0,"character":0}}}]}'
        )
        with pytest.raises(SystemExit) as exc:
            module._validate_and_build_diagnostics(data)
        assert exc.value.code == 3

    def test_valid_json_constructs_correctly(self) -> None:
        """有效 JSON 正确构造 list[_PyrightDiagnostic]。"""
        valid: module.JsonValue = {
            "generalDiagnostics": [{
                "file": "a.py", "severity": "error", "message": "msg",
                "range": {"start": {"line": 3, "character": 0}, "end": {"line": 3, "character": 10}},
                "rule": "reportGeneralTypeIssues",
            }],
        }
        result = module._validate_and_build_diagnostics(valid)
        assert len(result) == 1
        assert result[0]["file"] == "a.py"
        assert result[0]["range"]["start"]["line"] == 3


class TestRunPyrightFailClosed:
    """_run_pyright_json 对 pyright 异常输出的 fail-closed 测试。"""

    def test_abnormal_exit_exits_3(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """pyright 进程异常退出码 → exit 3。"""
        monkeypatch.setattr(
            subprocess, "run",
            _StaticSubprocessRunStub(returncode=2, stdout="", stderr="crash"),
        )
        with pytest.raises(SystemExit) as exc:
            module._run_pyright_json()
        assert exc.value.code == 3

    def test_invalid_json_output_exits_3(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """pyright stdout 非合法 JSON → exit 3。"""
        monkeypatch.setattr(
            subprocess, "run",
            _StaticSubprocessRunStub(returncode=0, stdout="not json{{{", stderr=""),
        )
        with pytest.raises(SystemExit) as exc:
            module._run_pyright_json()
        assert exc.value.code == 3


# ══════════════════════════════════════════════════════════════════
# Copy 状态 / malformed 行 fail-closed
# ══════════════════════════════════════════════════════════════════


class TestParseChangedEntriesCopyAndMalformed:
    """_parse_changed_entries 的 Copy 处理和 malformed 行 fail-closed 测试。"""

    def test_copy_status_new_path_is_parts2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Copy 状态使用 parts[2] 作为新文件路径，归入 new_files。"""
        monkeypatch.setattr(module, "_git", _StaticGitStub("C100\tsrc.py\tcopied.py\n"))
        change = module._parse_changed_entries("b", "h")
        assert "copied.py" in change.new_files
        assert "src.py" not in change.new_files

    def test_copy_status_ignores_non_python(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Copy 非 Python 文件不出现在变更集中。"""
        monkeypatch.setattr(module, "_git", _StaticGitStub("C100\tsrc.md\tdst.md\n"))
        change = module._parse_changed_entries("b", "h")
        assert not change.new_files
        assert not change.modified_files

    def test_malformed_c_line_exits_2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """C 行缺少第三列 → exit 2。"""
        monkeypatch.setattr(module, "_git", _StaticGitStub("C100\told.py\n"))
        with pytest.raises(SystemExit) as exc:
            module._parse_changed_entries("a", "b")
        assert exc.value.code == 2

    def test_malformed_r_line_exits_2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """R 行缺少第三列 → exit 2。"""
        monkeypatch.setattr(module, "_git", _StaticGitStub("R100\told.py\n"))
        with pytest.raises(SystemExit) as exc:
            module._parse_changed_entries("a", "b")
        assert exc.value.code == 2

    def test_malformed_plain_line_exits_2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """普通状态行缺少路径 → exit 2。"""
        monkeypatch.setattr(module, "_git", _StaticGitStub("M\n"))
        with pytest.raises(SystemExit) as exc:
            module._parse_changed_entries("a", "b")
        assert exc.value.code == 2

    def test_unknown_status_exits_2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """未知 status letter → exit 2。"""
        monkeypatch.setattr(module, "_git", _StaticGitStub("X\tfile.py\n"))
        with pytest.raises(SystemExit) as exc:
            module._parse_changed_entries("a", "b")
        assert exc.value.code == 2


# ── 浅克隆双点直接比较回归 ─────────────────────────────────────


def test_shallow_clone_direct_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实浅克隆中双点直接比较不依赖 merge-base。

    用 file:// origin 做 --depth=1 clone，仅 HEAD 可见，
    再 depth=1 fetch base SHA 到独立 tag。
    验证 git merge-base 失败而双树 diff 成功。

    参数:
        tmp_path: pytest 临时目录夹具。
        monkeypatch: pytest monkeypatch 夹具。
    """
    # 1. 创建 bare origin repo
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "--bare", "-b", "main")

    # 2. 在临时工作区创建两个 commit 并 push
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-b", "main")
    _git(work, "config", "user.email", "x@y")
    _git(work, "config", "user.name", "X")
    (work / "a.py").write_text("x=1\n")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "base")
    base_sha = _git_rev_parse(work, "HEAD")

    (work / "a.py").write_text("x=2\n")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "change")
    head_sha = _git_rev_parse(work, "HEAD")

    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "origin", "main")

    # 3. 浅克隆（--depth=1）到独立目录
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "--depth=1", "--branch", "main", f"file://{origin}", str(shallow)],
        check=True, capture_output=True,
    )
    monkeypatch.chdir(shallow)

    # 4. 单独 depth=1 fetch base SHA（此时两个 commit 对象均存在）
    subprocess.run(
        ["git", "fetch", "--no-tags", "--depth=1", "origin", base_sha],
        check=True, capture_output=True,
    )

    # 5. 验证两个对象存在但 merge-base 仍不可用（浅克隆无历史）
    mb_result = subprocess.run(
        ["git", "merge-base", base_sha, head_sha],
        check=False, capture_output=True,
    )
    assert mb_result.returncode != 0, "浅克隆 fetch 后仍不应能计算 merge-base"

    # 6. 双点 diff 不依赖 merge-base，应成功
    change = module._parse_changed_entries(base_sha, head_sha)
    assert change.has_any_py_changes is True


# ── _build_diff_opcodes / 行映射 ────────────────────────────────


class TestBuildDiffOpcodes:
    """_build_diff_opcodes 行差异解析测试。"""

    def test_equal_content_yields_equal_opcode(self) -> None:
        """验证相同内容产生 equal 操作码。"""
        ops = module._build_diff_opcodes("a\nb\nc\n", "a\nb\nc\n")
        assert ops == [("equal", 0, 3, 0, 3)]

    def test_insert_lines(self) -> None:
        """验证插入行产生 insert 操作码。"""
        ops = module._build_diff_opcodes("a\nc\n", "a\nx\ny\nc\n")
        assert "insert" in [t for t, *_ in ops]

    def test_replace_lines(self) -> None:
        """验证替换行产生 replace 操作码。"""
        ops = module._build_diff_opcodes("a\nb\nc\n", "a\nx\nc\n")
        assert "replace" in [t for t, *_ in ops]

    def test_delete_lines(self) -> None:
        """验证删除行产生 delete 操作码。"""
        ops = module._build_diff_opcodes("a\nb\nc\n", "a\nc\n")
        assert "delete" in [t for t, *_ in ops]


class TestComputeChangedHeadLines:
    """_compute_changed_head_lines 变更行计算测试。"""

    def test_equal_block_has_no_changed_lines(self) -> None:
        """验证 equal 块不产生变更行。"""
        assert module._compute_changed_head_lines([("equal", 0, 3, 0, 3)]) == set()

    def test_insert_marks_head_lines_1indexed(self) -> None:
        """验证 insert 块标记为 1-indexed 变更行。"""
        ops = [("insert", 0, 0, 0, 2), ("equal", 0, 2, 2, 4)]
        assert module._compute_changed_head_lines(ops) == {1, 2}

    def test_replace_marks_head_lines_1indexed(self) -> None:
        """验证 replace 块标记为 1-indexed 变更行。"""
        ops = [("replace", 0, 2, 0, 2), ("equal", 2, 3, 2, 3)]
        assert module._compute_changed_head_lines(ops) == {1, 2}


class TestBuildHeadToBaseLineMap:
    """_build_head_to_base_line_map 行映射构建测试。"""

    def test_equal_maps_directly(self) -> None:
        """验证 equal 块 HEAD 行直接映射到 BASE 同行。"""
        m = module._build_head_to_base_line_map([("equal", 0, 3, 0, 3)])
        assert m == {1: 1, 2: 2, 3: 3}

    def test_insert_shifts_equal_lines(self) -> None:
        """验证 insert 块之后的 equal 行正确偏移映射。"""
        ops = [("insert", 0, 0, 0, 2), ("equal", 0, 2, 2, 4)]
        m = module._build_head_to_base_line_map(ops)
        assert m[1] is None
        assert m[2] is None
        assert m[3] == 1
        assert m[4] == 2

    def test_replace_yields_none(self) -> None:
        """验证 replace 块 HEAD 行映射为 None。"""
        ops = [("replace", 0, 2, 0, 2), ("equal", 2, 3, 2, 3)]
        m = module._build_head_to_base_line_map(ops)
        assert m[1] is None
        assert m[2] is None
        assert m[3] == 3


# ── 诊断归一化（0→1 索引转换）─────────────────────────────────


def test_line_index_converts_0based_to_1based() -> None:
    """pyright JSON 中 range.start.line 是 0-indexed → 转为 1-indexed。"""
    diag = _diag("/abs/repo/dayu/a.py", line_0i=0, rule="r", message="m")
    tup = module._normalize_diagnostic_tuple(diag, repo_root=Path("/abs/repo"))
    assert tup[1] == 1  # 0→1


def test_line_index_pyright_realistic() -> None:
    """真实 pyright JSON：文件第 19 行 → line=18 (0-indexed) → 归一化 19。"""
    diag = _diag("/abs/repo/x.py", line_0i=18, rule="reportPrivateImportUsage", message="...")
    tup = module._normalize_diagnostic_tuple(diag, repo_root=Path("/abs/repo"))
    assert tup[1] == 19


def test_normalize_basic() -> None:
    """验证诊断归一化将绝对路径转为相对路径。"""
    diag = _diag("/abs/repo/dayu/a.py", line_0i=41, rule="r", message="m")
    tup = module._normalize_diagnostic_tuple(diag, repo_root=Path("/abs/repo"))
    assert tup == ("dayu/a.py", 42, "error", "r", "m")


def test_normalize_with_worktree_prefix() -> None:
    """验证 worktree 前缀被移除后归一化结果正确。"""
    diag = _diag("/tmp/wt/dayu/b.py", line_0i=6, rule="reportUnknownVariableType",
                  message="Type unknown", severity="warning")
    tup = module._normalize_diagnostic_tuple(
        diag, worktree_root=Path("/tmp/wt"), repo_root=Path("/real/repo"),
    )
    assert tup[0] == "dayu/b.py"
    assert tup[1] == 7


# ── Counter 多重集 ──────────────────────────────────────────────


def test_counter_consumes_one_match_per_diagnostic() -> None:
    """一条 BASE 诊断只能消耗一次。"""
    diags = [_diag("/repo/a.py", 0, "r", "m")]
    c = module._build_diagnostic_counter(diags, repo_root=Path("/repo"))
    assert c.total() == 1
    assert c[("a.py", 1, "error", "r", "m")] == 1


# ── fail-closed ────────────────────────────────────────────────


def test_head_mismatch_exits_2(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """工作树 commit 与 --head 不一致 → 退出码 2。

    参数:
        monkeypatch: pytest monkeypatch 夹具。
        tmp_path: pytest 临时目录夹具。
    """
    repo = tmp_path / "r"
    repo.mkdir()
    monkeypatch.chdir(repo)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "x@y")
    _git(repo, "config", "user.name", "X")
    (repo / "a.py").write_text("x=1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "only")
    real_sha = _git_rev_parse(repo, "HEAD")

    (repo / "b.py").write_text("y=2\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "head")
    fake_sha = _git_rev_parse(repo, "HEAD")
    _git(repo, "checkout", real_sha)

    with pytest.raises(SystemExit) as exc:
        module.main(["--base", real_sha, "--head", fake_sha])
    assert exc.value.code == 2


# ── 集成级 main() 测试 ─────────────────────────────────────────


class TestMainRatchet:
    """main() ratchet 流程集成测试。"""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """在临时 git 仓库中准备 base→head 变更供集成测试使用。

        参数:
            tmp_path: pytest 临时目录夹具。
            monkeypatch: pytest monkeypatch 夹具。
        """
        self.repo = tmp_path / "repo"
        self.repo.mkdir()
        monkeypatch.chdir(self.repo)

        _git(self.repo, "init", "-b", "main")
        _git(self.repo, "config", "user.email", "ci@test")
        _git(self.repo, "config", "user.name", "CI")

        (self.repo / "mod.py").write_text(
            "x: int = 1\n\ny = unknown_var\nz: str = 'a'\n"
        )
        (self.repo / "unchanged.py").write_text("u = 1\n")
        (self.repo / "del_me.py").write_text("d = 1\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-m", "base")
        self.base_sha = _git_rev_parse(self.repo, "HEAD")

        (self.repo / "mod.py").write_text(
            "x: int = 1\n\n# NEW\nNEW_VAR = 42\n\ny = unknown_var\nz: int = 1\n"
        )
        (self.repo / "new_file.py").write_text("w = None\n")
        (self.repo / "del_me.py").unlink()
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-m", "changes")
        self.head_sha = _git_rev_parse(self.repo, "HEAD")

        self._modified_head_paths = [Path("mod.py")]

    def _mock_all(
        self,
        monkeypatch: pytest.MonkeyPatch,
        head_diags: list[_TD],
        base_diags: list[_TD],
        base_file_content: str | None = None,
    ) -> None:
        """Mock _run_pyright_json 与 git 外围命令。

        将 pyright 运行替换为预设诊断列表，将 subprocess.run 替换为
        拦截器，对 git 命令返回预设结果，其余透传到真实实现。

        参数:
            monkeypatch: pytest monkeypatch 夹具。
            head_diags: HEAD 全仓 pyright 诊断列表。
            base_diags: BASE 全仓 pyright 诊断列表。
            base_file_content: BASE 上修改文件的内容；为 None 时
                git show 返回错误。

        返回值:
            无。

        异常:
            无。
        """
        call_count: list[int] = [0]

        def fake_pyright() -> list[_TD]:
            """Mock _run_pyright_json。

            第一次调用返回 HEAD 诊断，第二次调用返回 BASE 诊断。

            返回值:
                当前调用对应的诊断列表。

            异常:
                无。
            """
            call_count[0] += 1
            if call_count[0] == 1:
                return head_diags
            return base_diags

        monkeypatch.setattr(module, "_run_pyright_json", fake_pyright)

        real = subprocess.run

        class _FakeRunResult:
            """模拟 subprocess.run 返回值的轻量类。

            提供与 subprocess.CompletedProcess 兼容的 stdout、stderr、
            returncode 属性，供 fake_run 在拦截 git 命令时返回。

            属性:
                stdout: 标准输出文本。
                stderr: 标准错误文本。
                returncode: 进程退出码。
            """

            def __init__(self, s: str = "", e: str = "", rc: int = 0) -> None:
                """创建模拟的 subprocess 运行结果。

                参数:
                    s: 标准输出文本，对应 stdout 属性。
                    e: 标准错误文本，对应 stderr 属性。
                    rc: 退出码，对应 returncode 属性。

                返回值:
                    无。

                异常:
                    无。
                """
                self.stdout = s
                self.stderr = e
                self.returncode = rc

        def fake_run(
            cmd: list[str],
            capture_output: bool = False,
            text: bool = False,
            check: bool = True,
            cwd: str | Path | None = None,
        ) -> _FakeRunResult:
            """Mock subprocess.run，拦截 git 命令返回预设结果。

            参数:
                cmd: 命令行参数列表。
                capture_output: 是否捕获输出。
                text: 是否以文本模式返回。
                check: 是否检查返回码。
                cwd: 工作目录。

            返回值:
                _FakeRunResult 模拟结果。

            异常:
                无；未拦截的命令透传到真实 subprocess.run 后包装。
            """
            cs = " ".join(str(c) for c in cmd)
            if "rev-parse" in cs and "HEAD" in cs and "--verify" not in cs:
                return _FakeRunResult(s=self.head_sha)
            if "rev-parse" in cs and "--verify" in cs:
                ref = cmd[-1]
                if ref == self.head_sha:
                    return _FakeRunResult(s=self.head_sha)
                return _FakeRunResult(s=ref)
            if "show" in cs:
                if base_file_content is not None:
                    return _FakeRunResult(s=base_file_content)
                return _FakeRunResult(e="not found", rc=128)
            if "cat-file" in cs and "-e" in cs:
                ref = cmd[-1]
                if ref in (self.base_sha, self.head_sha):
                    return _FakeRunResult()
                return _FakeRunResult(rc=128)
            if "fetch" in cs:
                return _FakeRunResult()
            if "worktree add" in cs:
                for i, arg in enumerate(cmd):
                    if arg == "--detach" and i + 1 < len(cmd):
                        wt = Path(cmd[i + 1])
                        wt.mkdir(parents=True, exist_ok=True)
                        for hf in self._modified_head_paths:
                            (wt / hf).parent.mkdir(parents=True, exist_ok=True)
                            (wt / hf).write_text(base_file_content or "#\n")
                        (wt / "unchanged.py").parent.mkdir(parents=True, exist_ok=True)
                        (wt / "unchanged.py").write_text("u = 1\n")
                        break
                return _FakeRunResult()
            if "worktree remove" in cs:
                return _FakeRunResult()
            if "diff --name-status" in cs:
                return _FakeRunResult(
                    s=real(cmd, capture_output=capture_output, text=text, check=check, cwd=cwd).stdout,
                )
            wrapped = real(cmd, capture_output=capture_output, text=text, check=check, cwd=cwd)
            return _FakeRunResult(
                s=wrapped.stdout if wrapped.stdout else "",
                e=wrapped.stderr if wrapped.stderr else "",
                rc=wrapped.returncode,
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

    # ── 核心 ratchet ──

    def test_line_offset_preserves_diagnostic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """插入行导致位移：HEAD L6 映射回 BASE L3，既存放行。"""
        base_diags = [_diag(str(self.repo / "mod.py"), 2, "r1", "unknown")]
        head_diags = [_diag(str(self.repo / "mod.py"), 5, "r1", "unknown")]
        self._mock_all(monkeypatch, head_diags, base_diags,
                       "x: int = 1\n\ny = unknown_var\nz: str = 'a'\n")

        with pytest.raises(SystemExit) as exc:
            module.main(["--base", self.base_sha, "--head", self.head_sha])
        assert exc.value.code == 0

    def test_same_line_diff_message_is_new(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """同 equal 行同一 rule 不同 message → 新增。"""
        base = [_diag(str(self.repo / "mod.py"), 0, "r1", "Type A")]
        head = [_diag(str(self.repo / "mod.py"), 0, "r1", "Type C")]
        self._mock_all(monkeypatch, head, base,
                       "x: int = 1\n\ny = unknown_var\nz: str = 'a'\n")

        with pytest.raises(SystemExit) as exc:
            module.main(["--base", self.base_sha, "--head", self.head_sha])
        assert exc.value.code == 1

    def test_replaced_line_always_new(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """replace 块中诊断一律视为新增（零漏报）。"""
        base = [_diag(str(self.repo / "mod.py"), 3, "r1", "L4 err")]
        head = [_diag(str(self.repo / "mod.py"), 6, "r1", "L4 err")]
        self._mock_all(monkeypatch, head, base,
                       "x: int = 1\n\ny = unknown_var\nz: str = 'a'\n")

        with pytest.raises(SystemExit) as exc:
            module.main(["--base", self.base_sha, "--head", self.head_sha])
        assert exc.value.code == 1

    def test_new_file_all_diags_are_new(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """新增文件全部诊断视为 PR 引入。"""
        head = [_diag(str(self.repo / "new_file.py"), 0, "r1", "err")]
        self._mock_all(monkeypatch, head, [])

        with pytest.raises(SystemExit) as exc:
            module.main(["--base", self.base_sha, "--head", self.head_sha])
        assert exc.value.code == 1

    def test_mixed_preexisting_and_new(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """既存诊断与新增诊断混合时正确分类。"""
        base = [_diag(str(self.repo / "mod.py"), 2, "r1", "unknown")]
        head = [
            _diag(str(self.repo / "mod.py"), 5, "r1", "unknown"),  # 位移→既存
            _diag(str(self.repo / "mod.py"), 6, "r2", "replaced"),  # replace→新增
        ]
        self._mock_all(monkeypatch, head, base,
                       "x: int = 1\n\ny = unknown_var\nz: str = 'a'\n")

        with pytest.raises(SystemExit) as exc:
            module.main(["--base", self.base_sha, "--head", self.head_sha])
        assert exc.value.code == 1

    # ── unchanged consumer ──

    def test_unchanged_file_new_diagnostic_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """未变更文件出现 HEAD 新增诊断 → 必须失败。"""
        head = [_diag(str(self.repo / "unchanged.py"), 0, "r1", "new err")]
        self._mock_all(monkeypatch, head, [])

        with pytest.raises(SystemExit) as exc:
            module.main(["--base", self.base_sha, "--head", self.head_sha])
        assert exc.value.code == 1

    def test_unchanged_file_matching_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """未变更文件诊断与 BASE 完全匹配 → 放行。"""
        base = [_diag(str(self.repo / "unchanged.py"), 0, "r1", "old")]
        head = [_diag(str(self.repo / "unchanged.py"), 0, "r1", "old")]
        self._mock_all(monkeypatch, head, base)

        with pytest.raises(SystemExit) as exc:
            module.main(["--base", self.base_sha, "--head", self.head_sha])
        assert exc.value.code == 0

    # ── Counter 多重集 ──

    def test_one_base_diag_cannot_match_two_head(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """BASE 一条诊断不能消耗两次。"""
        base = [_diag(str(self.repo / "unchanged.py"), 4, "r1", "dup")]
        head = [
            _diag(str(self.repo / "unchanged.py"), 4, "r1", "dup"),
            _diag(str(self.repo / "unchanged.py"), 4, "r1", "dup"),
        ]
        self._mock_all(monkeypatch, head, base)

        with pytest.raises(SystemExit) as exc:
            module.main(["--base", self.base_sha, "--head", self.head_sha])
        assert exc.value.code == 1

    # ── 删除文件 ──

    def test_deleted_file_not_in_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """删除文件的诊断不出现在新增错误中。"""
        self._mock_all(monkeypatch, [], [_diag(str(self.repo / "del_me.py"), 0, "r1", "old")])

        with pytest.raises(SystemExit) as exc:
            module.main(["--base", self.base_sha, "--head", self.head_sha])
        assert exc.value.code == 0

    # ── 无 .py 变更仍全仓比较 ──

    def test_no_py_changes_still_runs_full_compare(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 .py 变更不跳过 ratchet（pyrightconfig 等变化可能引发新诊断）。"""
        head = [_diag(str(self.repo / "unchanged.py"), 0, "r1", "persist")]
        base = [_diag(str(self.repo / "unchanged.py"), 0, "r1", "persist")]
        self._mock_all(monkeypatch, head, base)

        with pytest.raises(SystemExit) as exc:
            module.main(["--base", self.head_sha, "--head", self.head_sha])
        # 相同 ref → 无 .py diff，但全仓比较仍运行；diagnostics 匹配→0
        assert exc.value.code == 0


# ── helpers ────────────────────────────────────────────────────


def _git(repo: Path, *args: str, check: bool = True) -> None:
    """在指定仓库中运行 git 命令（非交互，捕获输出）。

    参数:
        repo: 仓库路径。
        *args: git 子命令及参数。
        check: 是否在非零退出码时抛出 CalledProcessError。

    返回值:
        无。

    异常:
        subprocess.CalledProcessError: check=True 且 git 命令失败时抛出。
    """
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
    )


def _git_rev_parse(repo: Path, ref: str) -> str:
    """解析 git ref 为完整 SHA。

    参数:
        repo: 仓库路径。
        ref: git ref 名称（分支、标签、提交 SHA）。

    返回值:
        解析后的完整提交 SHA 字符串。

    异常:
        subprocess.CalledProcessError: ref 无法解析时抛出。
    """
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", ref],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
