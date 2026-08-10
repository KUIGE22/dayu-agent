"""Fins 文件系统 batch recovery 真源测试。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, TypedDict

import pytest

import dayu.fins.storage._fs_storage_infra as fs_storage_infra_module
from dayu.fins.domain.document_models import BatchToken, FileObjectMeta, SourceHandle
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.storage._fs_storage_core import FsStorageCore
from dayu.fins.storage._fs_storage_infra import BatchAdmission
from dayu.fins.storage.fs_company_meta_repository import FsCompanyMetaRepository
from tests.conftest import requires_symlink
from tests.fins.storage_testkit import build_fs_storage_test_context

_LOCK_HOLDER_POLL_INTERVAL_SEC = 0.05
_LOCK_HOLDER_READY_TIMEOUT_SEC = 15.0
_LOCK_HOLDER_STOP_TIMEOUT_SEC = 15.0


class _LockHolderState(TypedDict):
    """跨进程持锁子进程回传的状态。"""

    ticker: str
    staging_root_dir: str
    ticker_lock_path: str


def _write_text(path: Path, content: str) -> None:
    """向测试路径写入文本文件。

    Args:
        path: 目标文件路径。
        content: 文件内容。

    Returns:
        无。

    Raises:
        OSError: 写入失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _repo_root() -> Path:
    """返回仓库根目录。

    Args:
        无。

    Returns:
        当前测试所在仓库根目录。

    Raises:
        无。
    """

    return Path(__file__).resolve().parents[2]


def _build_lock_holder_script() -> str:
    """构造跨进程持锁子脚本文本。

    Args:
        无。

    Returns:
        供 `python -c` 执行的脚本文本。

    Raises:
        无。
    """

    return textwrap.dedent(
        """
        import json
        import sys
        import time
        from pathlib import Path

        from dayu.fins.storage._fs_repository_factory import build_fs_repository_set

        workspace_root = Path(sys.argv[1])
        ticker = sys.argv[2]
        ready_path = Path(sys.argv[3])
        release_path = Path(sys.argv[4])

        repository_set = build_fs_repository_set(workspace_root=workspace_root)
        core = repository_set.core
        token = core.begin_batch(ticker)
        ready_path.write_text(
            json.dumps(
                {
                    "ticker": token.ticker,
                    "staging_root_dir": str(token.staging_root_dir),
                    "ticker_lock_path": str(token.ticker_lock_path),
                }
            ),
            encoding="utf-8",
        )
        try:
            while not release_path.exists():
                time.sleep(0.05)
        finally:
            core.rollback_batch(token)
        """
    )


def _spawn_lock_holder(
    workspace_root: Path,
    ticker: str,
    ready_path: Path,
    release_path: Path,
) -> subprocess.Popen[str]:
    """启动一个持有指定 ticker batch 锁的子进程。

    Args:
        workspace_root: 测试工作区根目录。
        ticker: 需要持有的股票代码。
        ready_path: 子进程回传状态文件路径。
        release_path: 主进程发出释放信号的文件路径。

    Returns:
        已启动的子进程句柄。

    Raises:
        OSError: 子进程启动失败时抛出。
    """

    environment = dict(os.environ)
    python_path_parts = [str(_repo_root())]
    existing_python_path = environment.get("PYTHONPATH")
    if existing_python_path:
        python_path_parts.append(existing_python_path)
    environment["PYTHONPATH"] = os.pathsep.join(python_path_parts)
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            _build_lock_holder_script(),
            str(workspace_root),
            ticker,
            str(ready_path),
            str(release_path),
        ],
        cwd=_repo_root(),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for_lock_holder_state(process: subprocess.Popen[str], ready_path: Path) -> _LockHolderState:
    """等待持锁子进程写出状态文件。

    Args:
        process: 持锁子进程。
        ready_path: 子进程状态文件路径。

    Returns:
        子进程回传的持锁状态。

    Raises:
        AssertionError: 子进程提前退出或超时未就绪时抛出。
    """

    deadline = time.monotonic() + _LOCK_HOLDER_READY_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if ready_path.exists():
            raw_payload = json.loads(ready_path.read_text(encoding="utf-8"))
            assert isinstance(raw_payload, dict)
            ticker = raw_payload.get("ticker")
            staging_root_dir = raw_payload.get("staging_root_dir")
            ticker_lock_path = raw_payload.get("ticker_lock_path")
            assert isinstance(ticker, str)
            assert isinstance(staging_root_dir, str)
            assert isinstance(ticker_lock_path, str)
            return {
                "ticker": ticker,
                "staging_root_dir": staging_root_dir,
                "ticker_lock_path": ticker_lock_path,
            }
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                "持锁子进程在写出状态前提前退出:\n"
                f"stdout={stdout}\n"
                f"stderr={stderr}"
            )
        time.sleep(_LOCK_HOLDER_POLL_INTERVAL_SEC)
    _stop_lock_holder(process, ready_path.parent / "holder-release-on-timeout")
    raise AssertionError(f"等待持锁子进程状态超时: timeout={_LOCK_HOLDER_READY_TIMEOUT_SEC} 秒")


def _stop_lock_holder(process: subprocess.Popen[str], release_path: Path) -> None:
    """通知持锁子进程退出并等待收口。

    Args:
        process: 持锁子进程。
        release_path: 释放信号文件路径。

    Returns:
        无。

    Raises:
        AssertionError: 子进程异常退出时抛出。
    """

    if process.poll() is None:
        release_path.touch()
        try:
            stdout, stderr = process.communicate(timeout=_LOCK_HOLDER_STOP_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"持锁子进程未能在超时内退出: timeout={_LOCK_HOLDER_STOP_TIMEOUT_SEC} 秒\n"
                f"stdout={stdout}\n"
                f"stderr={stderr}"
            )
        if process.returncode != 0:
            raise AssertionError(
                "持锁子进程异常退出:\n"
                f"stdout={stdout}\n"
                f"stderr={stderr}"
            )


@pytest.mark.unit
def test_batch_paths_move_under_dayu_root(tmp_path: Path) -> None:
    """验证 batch 与 backup 目录已迁移到 `.dayu/` 下。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    assert core.dayu_root == tmp_path / ".dayu"
    assert core.batch_root == tmp_path / ".dayu" / "repo_batches"
    assert core.backup_root == tmp_path / ".dayu" / "repo_backups"


@pytest.mark.unit
def test_recover_started_batch_cleans_orphan_staging(tmp_path: Path) -> None:
    """验证 started 阶段遗留的 staging 会在下次构造仓储时自动清理。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    token = core.begin_batch("AAPL")
    staged_marker = token.staging_ticker_dir / "filings" / "marker.txt"
    _write_text(staged_marker, "staged")

    core._active_batches.clear()
    core._release_ticker_lock(token.ticker)

    assert token.staging_root_dir.exists()

    FsCompanyMetaRepository(tmp_path)

    assert not token.staging_root_dir.exists()


@pytest.mark.unit
def test_recover_backed_up_target_restores_backup(tmp_path: Path) -> None:
    """验证 backed_up_target 阶段会把 backup 恢复回正式目录。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    target_marker = core._target_ticker_dir("AAPL") / "filings" / "before.txt"
    _write_text(target_marker, "before")

    token = core.begin_batch("AAPL")
    core._write_batch_journal(token, "backed_up_target")
    token.target_ticker_dir.parent.mkdir(parents=True, exist_ok=True)
    target_dir = token.target_ticker_dir
    backup_dir = token.backup_dir
    target_dir.rename(backup_dir)

    core._active_batches.clear()
    core._release_ticker_lock(token.ticker)

    actions = core.recover_orphan_batches()

    assert any("restore backup ticker=AAPL" in action for action in actions)
    assert target_dir.exists()
    assert not backup_dir.exists()
    assert not token.staging_root_dir.exists()
    assert (target_dir / "filings" / "before.txt").read_text(encoding="utf-8") == "before"


@pytest.mark.unit
def test_recover_swapped_target_deletes_leftover_backup(tmp_path: Path) -> None:
    """验证 swapped_target 阶段会保留新 target 并清理遗留 backup。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    old_marker = core._target_ticker_dir("AAPL") / "filings" / "version.txt"
    _write_text(old_marker, "old")

    token = core.begin_batch("AAPL")
    _write_text(token.staging_ticker_dir / "filings" / "version.txt", "new")
    core._write_batch_journal(token, "backed_up_target")
    token.target_ticker_dir.rename(token.backup_dir)
    token.staging_ticker_dir.rename(token.target_ticker_dir)
    core._write_batch_journal(token, "swapped_target")

    core._active_batches.clear()
    core._release_ticker_lock(token.ticker)

    actions = core.recover_orphan_batches()

    assert any("delete backup ticker=AAPL" in action for action in actions)
    assert token.target_ticker_dir.exists()
    assert not token.backup_dir.exists()
    assert not token.staging_root_dir.exists()
    assert (token.target_ticker_dir / "filings" / "version.txt").read_text(encoding="utf-8") == "new"


@pytest.mark.unit
def test_recover_orphan_batches_dry_run_is_non_destructive(tmp_path: Path) -> None:
    """验证 dry-run 只返回动作，不修改文件系统。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    token = core.begin_batch("AAPL")
    _write_text(token.staging_ticker_dir / "filings" / "marker.txt", "staged")

    core._active_batches.clear()
    core._release_ticker_lock(token.ticker)

    actions = core.recover_orphan_batches(dry_run=True)

    assert any("cleanup batch ticker=AAPL" in action for action in actions)
    assert token.staging_root_dir.exists()


@pytest.mark.unit
def test_recover_missing_journal_without_ticker_keeps_unknown_token_dir(tmp_path: Path) -> None:
    """验证缺少 journal 且无法推断 ticker 的 token 目录会保守跳过。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    token_dir = core.batch_root / "token-without-journal"
    token_dir.mkdir(parents=True, exist_ok=True)

    actions = core.recover_orphan_batches()

    assert actions == (
        "skip batch token=token-without-journal phase=unknown reason=missing journal",
    )
    assert token_dir.exists()


@pytest.mark.unit
def test_recover_orphan_batches_cleans_live_owner_without_lock(tmp_path: Path) -> None:
    """验证 recovery 在 ticker 锁已释放时会清理 orphan，即使 owner 进程仍存活。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    token = core.begin_batch("AAPL")
    _write_text(token.staging_ticker_dir / "filings" / "marker.txt", "staged")

    core._active_batches.clear()
    core._release_ticker_lock(token.ticker)

    actions = core.recover_orphan_batches()

    assert any("cleanup batch ticker=AAPL" in action for action in actions)
    assert not token.staging_root_dir.exists()


@pytest.mark.unit
def test_recover_orphan_batches_tolerates_token_dir_disappearing_during_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 recovery 扫描 live batch 时，token 目录中途消失不会中断整批恢复。

    复现场景：
    - recovery 进程先枚举到 `repo_batches/<token>`。
    - owner 进程随后完成提交并删掉该 token 根目录。
    - 当前恢复流程继续进入 `_infer_batch_ticker()` 时，`token_dir.iterdir()`
      可能直接抛出 `FileNotFoundError`。

    期望行为：
    - recovery 把该 token 视为已消失的 live batch，安静跳过。
    - 不因单个竞态样本中断整个 `recover_orphan_batches()`。
    """

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    token = core.begin_batch("AAPL")
    _write_text(token.staging_ticker_dir / "filings" / "marker.txt", "staged")

    core._active_batches.clear()
    core._release_ticker_lock(token.ticker)
    token.journal_path.unlink()

    original_infer_batch_ticker = core._infer_batch_ticker

    def _delete_token_dir_before_infer(token_dir: Path) -> str:
        """在推断 ticker 前模拟 owner 进程已删除 token 根目录。"""

        if token_dir == token.staging_root_dir:
            shutil.rmtree(token_dir, ignore_errors=True)
        return original_infer_batch_ticker(token_dir)

    monkeypatch.setattr(core, "_infer_batch_ticker", _delete_token_dir_before_infer)

    actions = core.recover_orphan_batches()

    assert actions == (
        f"skip batch token={token.token_id} phase=unknown reason=missing journal",
    )
    assert not token.staging_root_dir.exists()


@pytest.mark.unit
def test_commit_batch_keeps_new_target_when_swapped_target_journal_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证新 ticker 在换入目标后 journal 写失败时仍保留已落盘目标。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    token = core.begin_batch("AAPL")
    _write_text(token.staging_ticker_dir / "filings" / "version.txt", "new")
    original_write_batch_journal = core._write_batch_journal

    def _failing_write_batch_journal(batch_token: object, phase: str) -> None:
        """在 swapped_target 阶段模拟 journal 写入失败。"""

        if phase == "swapped_target":
            raise OSError("disk full")
        original_write_batch_journal(batch_token, phase)  # type: ignore[arg-type]

    monkeypatch.setattr(core, "_write_batch_journal", _failing_write_batch_journal)

    with pytest.raises(OSError, match="disk full"):
        core.commit_batch(token)

    assert token.target_ticker_dir.exists()
    assert not token.backup_dir.exists()
    assert not token.staging_root_dir.exists()
    assert token.ticker not in core._active_batches
    assert (token.target_ticker_dir / "filings" / "version.txt").read_text(encoding="utf-8") == "new"


@pytest.mark.unit
def test_rollback_batch_cleans_and_unlocks_when_rolled_back_journal_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 rollback journal 写失败时仍会清理 staging 并释放 ticker 锁。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    token = core.begin_batch("AAPL")
    _write_text(token.staging_ticker_dir / "filings" / "version.txt", "draft")
    original_write_batch_journal = core._write_batch_journal

    def _failing_write_batch_journal(batch_token: object, phase: str) -> None:
        """在 rolled_back 阶段模拟 journal 写入失败。"""

        if phase == "rolled_back":
            raise OSError("disk full")
        original_write_batch_journal(batch_token, phase)  # type: ignore[arg-type]

    monkeypatch.setattr(core, "_write_batch_journal", _failing_write_batch_journal)

    with pytest.raises(OSError, match="disk full"):
        core.rollback_batch(token)

    assert not token.staging_root_dir.exists()
    assert token.ticker not in core._active_batches

    monkeypatch.setattr(core, "_write_batch_journal", original_write_batch_journal)
    next_token = core.begin_batch("AAPL")
    try:
        assert next_token.ticker == "AAPL"
    finally:
        core.rollback_batch(next_token)


@pytest.mark.unit
def test_execute_with_auto_batch_preserves_original_error_when_rollback_journal_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 auto batch 回滚失败时仍优先抛出原始写路径异常。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    original_write_batch_journal = core._write_batch_journal

    def _failing_write_batch_journal(batch_token: object, phase: str) -> None:
        """在 rolled_back 阶段模拟 journal 写入失败。"""

        if phase == "rolled_back":
            raise OSError("disk full")
        original_write_batch_journal(batch_token, phase)  # type: ignore[arg-type]

    def _failing_operation() -> None:
        """模拟原始写路径失败。"""

        raise ValueError("write failed")

    monkeypatch.setattr(core, "_write_batch_journal", _failing_write_batch_journal)

    with pytest.raises(ValueError, match="write failed") as exc_info:
        core._execute_with_auto_batch(
            "AAPL",
            _failing_operation,
            admission=BatchAdmission.AUTO_ATOMIC_ALLOWED,
        )

    notes = getattr(exc_info.value, "__notes__", [])
    assert any("rollback_batch failed: disk full" in note for note in notes)

    monkeypatch.setattr(core, "_write_batch_journal", original_write_batch_journal)
    next_token = core.begin_batch("AAPL")
    try:
        assert next_token.ticker == "AAPL"
    finally:
        core.rollback_batch(next_token)


@pytest.mark.unit
def test_begin_batch_rejects_cross_process_same_ticker(tmp_path: Path) -> None:
    """验证同一 ticker 的 batch 锁不会被两个进程同时拿到。"""

    ready_path = tmp_path / "holder-ready.json"
    release_path = tmp_path / "holder-release"
    process = _spawn_lock_holder(tmp_path, "AAPL", ready_path, release_path)
    try:
        holder_state = _wait_for_lock_holder_state(process, ready_path)
        assert holder_state["ticker"] == "AAPL"
        assert Path(holder_state["ticker_lock_path"]).exists()

        contender_core = build_fs_storage_test_context(tmp_path).core
        with pytest.raises(RuntimeError, match="跨进程活动 batch"):
            contender_core.begin_batch("AAPL")
    finally:
        _stop_lock_holder(process, release_path)


@pytest.mark.unit
def test_recover_orphan_batches_skips_live_locked_batch(tmp_path: Path) -> None:
    """验证 recovery 遇到活跃 ticker 锁时会跳过，而不会误删 staging。"""

    ready_path = tmp_path / "holder-ready.json"
    release_path = tmp_path / "holder-release"
    process = _spawn_lock_holder(tmp_path, "AAPL", ready_path, release_path)
    try:
        holder_state = _wait_for_lock_holder_state(process, ready_path)
        assert holder_state["ticker"] == "AAPL"
        staging_root_dir = Path(holder_state["staging_root_dir"])
        assert staging_root_dir.exists()

        recovery_core = build_fs_storage_test_context(tmp_path).core
        actions = recovery_core.recover_orphan_batches()

        assert actions == ()
        assert staging_root_dir.exists()
    finally:
        _stop_lock_holder(process, release_path)


@pytest.mark.unit
def test_begin_batch_allows_different_ticker_while_other_process_holds_lock(tmp_path: Path) -> None:
    """验证 batch 锁按 ticker 粒度隔离，不同 ticker 可并发开启。"""

    ready_path = tmp_path / "holder-ready.json"
    release_path = tmp_path / "holder-release"
    process = _spawn_lock_holder(tmp_path, "AAPL", ready_path, release_path)
    try:
        holder_state = _wait_for_lock_holder_state(process, ready_path)
        assert holder_state["ticker"] == "AAPL"

        contender_core = build_fs_storage_test_context(tmp_path).core
        token = contender_core.begin_batch("MSFT")
        try:
            assert token.ticker == "MSFT"
            assert token.staging_root_dir.exists()
            assert token.ticker_lock_path.name == "MSFT.lock"
        finally:
            contender_core.rollback_batch(token)
    finally:
        _stop_lock_holder(process, release_path)


@pytest.mark.unit
def test_fins_batch_lock_uses_msvcrt_when_fcntl_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Windows 分支应改用 msvcrt 提供真正的非阻塞 batch 锁。"""

    class _FakeMsvcrt:
        """记录 locking 调用的 Windows 锁实现桩。"""

        LK_NBLCK = 2
        LK_UNLCK = 3

        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []

        def locking(self, fd: int, mode: int, size: int) -> None:
            del fd
            self.calls.append((mode, size))

    core = build_fs_storage_test_context(tmp_path).core
    fake_msvcrt = _FakeMsvcrt()
    monkeypatch.setattr(fs_storage_infra_module.file_lock_module, "_FCNTL", None)
    monkeypatch.setattr(fs_storage_infra_module.file_lock_module, "_MSVCRT", fake_msvcrt)
    fake_msvcrt.calls.clear()
    stream = core._open_and_lock_stream(tmp_path / ".dayu" / "batch_locks" / "AAPL.lock", blocking=False)
    try:
        assert fake_msvcrt.calls == [(fake_msvcrt.LK_NBLCK, 1)]
    finally:
        core._release_lock_stream(stream)

    assert fake_msvcrt.calls == [
        (fake_msvcrt.LK_NBLCK, 1),
        (fake_msvcrt.LK_UNLCK, 1),
    ]


@pytest.mark.unit
def test_recovery_lock_retries_until_windows_lock_is_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """验证 recovery 阻塞锁在 Windows 上会持续重试直到成功。"""

    class _RetryingMsvcrt:
        """前两次竞争失败、随后成功的 Windows 锁实现桩。"""

        LK_NBLCK = 2
        LK_UNLCK = 3

        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []
            self._remaining_contention_failures = 2

        def locking(self, fd: int, mode: int, size: int) -> None:
            del fd
            self.calls.append((mode, size))
            if mode == self.LK_NBLCK and self._remaining_contention_failures > 0:
                self._remaining_contention_failures -= 1
                raise BlockingIOError(
                    fs_storage_infra_module.file_lock_module.errno.EAGAIN,
                    "locked",
                )

    core = build_fs_storage_test_context(tmp_path).core
    fake_msvcrt = _RetryingMsvcrt()
    sleep_calls: list[float] = []
    monkeypatch.setattr(fs_storage_infra_module.file_lock_module, "_FCNTL", None)
    monkeypatch.setattr(fs_storage_infra_module.file_lock_module, "_MSVCRT", fake_msvcrt)
    monkeypatch.setattr(fs_storage_infra_module.file_lock_module.time, "sleep", sleep_calls.append)

    stream = core._acquire_recovery_lock()
    try:
        assert fake_msvcrt.calls == [
            (fake_msvcrt.LK_NBLCK, 1),
            (fake_msvcrt.LK_NBLCK, 1),
            (fake_msvcrt.LK_NBLCK, 1),
        ]
        assert sleep_calls == [
            fs_storage_infra_module.file_lock_module._WINDOWS_LOCK_RETRY_INTERVAL_SEC,
            fs_storage_infra_module.file_lock_module._WINDOWS_LOCK_RETRY_INTERVAL_SEC,
        ]
    finally:
        core._release_lock_stream(stream)

    assert fake_msvcrt.calls == [
        (fake_msvcrt.LK_NBLCK, 1),
        (fake_msvcrt.LK_NBLCK, 1),
        (fake_msvcrt.LK_NBLCK, 1),
        (fake_msvcrt.LK_UNLCK, 1),
    ]


@pytest.mark.unit
def test_parse_backup_directory_name_rejects_invalid_names() -> None:
    """验证 _parse_backup_directory_name 对不合法名称返回 None。"""

    from dayu.fins.storage._fs_storage_infra import _parse_backup_directory_name

    # 无分隔符
    assert _parse_backup_directory_name("no_separator") is None
    # 只有 token_id 部分
    assert _parse_backup_directory_name(".bak.abc123") is None
    # ticker 为空
    assert _parse_backup_directory_name(".bak.") is None
    # 正确格式
    assert _parse_backup_directory_name("AAPL.bak.abc123") == ("AAPL", "abc123")


@pytest.mark.unit
def test_begin_batch_rejects_same_ticker_in_same_process(tmp_path: Path) -> None:
    """验证同一进程内对同一 ticker 重复 begin_batch 抛出 RuntimeError。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    token = core.begin_batch("AAPL")
    try:
        with pytest.raises(RuntimeError, match="已存在活动 batch"):
            core.begin_batch("AAPL")
    finally:
        core.rollback_batch(token)


@pytest.mark.unit
def test_commit_batch_rejects_invalid_token(tmp_path: Path) -> None:
    """验证 commit_batch 对无效 token 抛出 ValueError。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    # 未开启任何 batch 时提交
    from dayu.fins.domain.document_models import BatchToken, now_iso8601

    fake_token = BatchToken(
        token_id="fake-id",
        ticker="AAPL",
        target_ticker_dir=tmp_path / "portfolio" / "AAPL",
        staging_root_dir=tmp_path / ".dayu" / "repo_batches" / "fake-id",
        staging_ticker_dir=tmp_path / ".dayu" / "repo_batches" / "fake-id" / "AAPL",
        backup_dir=tmp_path / ".dayu" / "repo_backups" / "AAPL.bak.fake-id",
        journal_path=tmp_path / ".dayu" / "repo_batches" / "fake-id" / "transaction.json",
        ticker_lock_path=tmp_path / ".dayu" / "batch_locks" / "AAPL.lock",
        created_at=now_iso8601(),
    )
    with pytest.raises(ValueError, match="无效的 batch token"):
        core.commit_batch(fake_token)

    # 不同 ticker 的活动 batch 也不能提交假 token
    real_token = core.begin_batch("MSFT")
    try:
        with pytest.raises(ValueError, match="无效的 batch token"):
            core.commit_batch(fake_token)
    finally:
        core.rollback_batch(real_token)


@pytest.mark.unit
def test_rollback_batch_rejects_invalid_token(tmp_path: Path) -> None:
    """验证 rollback_batch 对无效 token 抛出 ValueError。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    from dayu.fins.domain.document_models import BatchToken, now_iso8601

    fake_token = BatchToken(
        token_id="fake-id",
        ticker="AAPL",
        target_ticker_dir=tmp_path / "portfolio" / "AAPL",
        staging_root_dir=tmp_path / ".dayu" / "repo_batches" / "fake-id",
        staging_ticker_dir=tmp_path / ".dayu" / "repo_batches" / "fake-id" / "AAPL",
        backup_dir=tmp_path / ".dayu" / "repo_backups" / "AAPL.bak.fake-id",
        journal_path=tmp_path / ".dayu" / "repo_batches" / "fake-id" / "transaction.json",
        ticker_lock_path=tmp_path / ".dayu" / "batch_locks" / "AAPL.lock",
        created_at=now_iso8601(),
    )
    with pytest.raises(ValueError, match="无效的 batch token"):
        core.rollback_batch(fake_token)


@pytest.mark.unit
def test_select_primary_document_fallback_branches(tmp_path: Path) -> None:
    """验证 _select_primary_document 的各个回退分支。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    # 显式指定优先
    assert core._select_primary_document("explicit.htm", "old.htm", ["a.txt"], ["b.txt"]) == "explicit.htm"
    # 显式为空字符串时回退到 previous_primary
    assert core._select_primary_document("", "old.htm", ["a.txt"], ["b.txt"]) == "old.htm"
    # 显式为 None，previous_primary 为空字符串时回退到 current_file_names
    assert core._select_primary_document(None, "", ["a.txt"], ["b.txt"]) == "a.txt"
    # 显式为 None，previous_primary 非字符串时也回退到 current_file_names
    assert core._select_primary_document(None, 123, ["a.txt"], ["b.txt"]) == "a.txt"
    # 显式为 None，previous_primary 非字符串，current 为空时回退到 previous_file_names
    assert core._select_primary_document(None, 123, [], ["b.txt"]) == "b.txt"
    # 全部为空
    assert core._select_primary_document(None, None, [], []) is None
    # 显式为空格字符串时回退到 previous_primary
    assert core._select_primary_document("   ", "old.htm", ["a.txt"], []) == "old.htm"


@pytest.mark.unit
def test_handle_dir_path_with_processed_handle(tmp_path: Path) -> None:
    """验证 _handle_dir_path 对 ProcessedHandle 返回 processed 目录路径。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    from dayu.fins.domain.document_models import ProcessedHandle

    handle = ProcessedHandle(ticker="AAPL", document_id="doc_1")
    path = core._handle_dir_path(handle)
    assert path == core._processed_dir_for_read("AAPL", "doc_1")


@pytest.mark.unit
def test_build_store_key_with_processed_handle(tmp_path: Path) -> None:
    """验证 _build_store_key 对 ProcessedHandle 返回 processed key 格式。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    from dayu.fins.domain.document_models import ProcessedHandle

    handle = ProcessedHandle(ticker="AAPL", document_id="doc_1")
    key = core._build_store_key(handle, "output.json")
    assert key == "AAPL/processed/doc_1/output.json"


@pytest.mark.unit
def test_build_store_key_with_source_handle(tmp_path: Path) -> None:
    """验证 _build_store_key 对 SourceHandle 返回对应 source_dir key 格式。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    from dayu.fins.domain.document_models import SourceHandle

    handle = SourceHandle(ticker="AAPL", document_id="fil_1", source_kind="filing")
    key = core._build_store_key(handle, "main.html")
    assert key == "AAPL/filings/fil_1/main.html"


@pytest.mark.unit
def test_get_handle_meta_raises_when_meta_missing(tmp_path: Path) -> None:
    """验证 _get_handle_meta 在 meta.json 不存在时抛出 FileNotFoundError。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    from dayu.fins.domain.document_models import SourceHandle

    handle = SourceHandle(ticker="AAPL", document_id="nonexistent", source_kind="filing")
    with pytest.raises(FileNotFoundError, match="meta.json 不存在"):
        core._get_handle_meta(handle)


@pytest.mark.unit
def test_get_handle_meta_with_processed_handle(tmp_path: Path) -> None:
    """验证 _get_handle_meta 对 ProcessedHandle 使用 processed meta 路径。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    from dayu.fins.domain.document_models import ProcessedHandle

    handle = ProcessedHandle(ticker="AAPL", document_id="nonexistent_proc")
    with pytest.raises(FileNotFoundError, match="meta.json 不存在"):
        core._get_handle_meta(handle)


@pytest.mark.unit
def test_resolve_handle_child_path_rejects_dotdot(tmp_path: Path) -> None:
    """验证 _resolve_handle_child_path 对 `..` 名称抛出 ValueError。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    from dayu.fins.domain.document_models import ProcessedHandle

    handle = ProcessedHandle(ticker="AAPL", document_id="doc_1")
    with pytest.raises(ValueError, match="条目名称非法"):
        core._resolve_handle_child_path(handle, "..")


@pytest.mark.unit
@requires_symlink
def test_resolve_handle_child_path_boundary_check_via_symlink(tmp_path: Path) -> None:
    """验证 _resolve_handle_child_path 通过 symlink 越界时抛出 ValueError。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    from dayu.fins.domain.document_models import ProcessedHandle

    # 先确保 handle 目录存在
    handle = ProcessedHandle(ticker="AAPL", document_id="doc_1")
    handle_dir = core._handle_dir_path(handle)
    handle_dir.mkdir(parents=True, exist_ok=True)

    # 创建一个指向目录外部的 symlink
    external_target = tmp_path / "external_secret"
    external_target.write_text("secret", encoding="utf-8")
    symlink_path = handle_dir / "escape"
    symlink_path.symlink_to(external_target)

    with pytest.raises(ValueError, match="越界"):
        core._resolve_handle_child_path(handle, "escape")


@pytest.mark.unit
def test_ticker_dir_for_read_with_active_batch(tmp_path: Path) -> None:
    """验证 _ticker_dir_for_read 在有活动 batch 时返回 staging 目录。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    token = core.begin_batch("AAPL")
    try:
        read_dir = core._ticker_dir_for_read("AAPL")
        assert read_dir == token.staging_ticker_dir
    finally:
        core.rollback_batch(token)


@pytest.mark.unit
def test_ticker_dir_for_read_without_active_batch(tmp_path: Path) -> None:
    """验证 _ticker_dir_for_read 在无活动 batch 时返回正式目录。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    read_dir = core._ticker_dir_for_read("AAPL")
    assert read_dir == core._target_ticker_dir("AAPL")


@pytest.mark.unit
def test_should_manage_batch_state_returns_false_when_nothing_exists(tmp_path: Path) -> None:
    """验证 _should_manage_batch_state 在无 .dayu 目录且 create_directories=False 时返回 False。"""

    from dayu.fins.storage._fs_storage_infra import _FsStorageInfra

    infra = _FsStorageInfra(tmp_path, create_directories=False)
    assert infra._should_manage_batch_state() is False


@pytest.mark.unit
def test_build_file_store_uses_provided_store(tmp_path: Path) -> None:
    """验证 _build_file_store 在已注入 file_store 时直接返回。"""

    from dayu.fins.storage.local_file_store import LocalFileStore

    store = LocalFileStore(root=tmp_path, scheme="local")
    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    core._file_store = store

    assert core._build_file_store("AAPL") is store


@pytest.mark.unit
def test_recover_orphan_batch_dirs_skips_non_directory_files(tmp_path: Path) -> None:
    """验证 _recover_orphan_batch_dirs 跳过 batch_root 下的非目录文件。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    (core.batch_root / "not-a-dir.txt").write_text("noise", encoding="utf-8")

    actions = core._recover_orphan_batch_dirs(dry_run=True)
    assert actions == []


@pytest.mark.unit
def test_release_ticker_lock_with_no_cached_stream(tmp_path: Path) -> None:
    """验证 _release_ticker_lock 在无缓存流时安全返回。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    # 无异常即通过
    core._release_ticker_lock("NONEXISTENT")


@pytest.mark.unit
def test_filing_manifest_path_for_read(tmp_path: Path) -> None:
    """验证 _filing_manifest_path_for_read 返回正确路径。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    path = core._filing_manifest_path_for_read("AAPL")
    assert path.name == "filing_manifest.json"
    assert "filings" in path.parts


@pytest.mark.unit
def test_material_manifest_path_for_read(tmp_path: Path) -> None:
    """验证 _material_manifest_path_for_read 返回正确路径。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    path = core._material_manifest_path_for_read("AAPL")
    assert path.name == "material_manifest.json"
    assert "materials" in path.parts


@pytest.mark.unit
def test_company_meta_path(tmp_path: Path) -> None:
    """验证 _company_meta_path 返回正确路径。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    path = core._company_meta_path("AAPL")
    assert path.name == "meta.json"
    assert path.parent == core._ticker_dir_for_write("AAPL")


@pytest.mark.unit
def test_rejected_filing_file_path_for_read_rejects_dotdot(tmp_path: Path) -> None:
    """验证 _rejected_filing_file_path_for_read 对 `..` 名称抛出 ValueError。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    with pytest.raises(ValueError, match="条目名称非法"):
        core._rejected_filing_file_path_for_read("AAPL", "doc_1", "..")


@pytest.mark.unit
@requires_symlink
def test_rejected_filing_file_path_for_read_boundary_check_via_symlink(tmp_path: Path) -> None:
    """验证 _rejected_filing_file_path_for_read 通过 symlink 越界时抛出 ValueError。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    # 创建 rejected filing 目录
    rejected_dir = core._rejected_filing_dir_for_read("AAPL", "doc_1")
    rejected_dir.mkdir(parents=True, exist_ok=True)

    # 创建指向目录外部的 symlink
    external_target = tmp_path / "external_secret"
    external_target.write_text("secret", encoding="utf-8")
    symlink_path = rejected_dir / "escape"
    symlink_path.symlink_to(external_target)

    with pytest.raises(ValueError, match="越界"):
        core._rejected_filing_file_path_for_read("AAPL", "doc_1", "escape")


@pytest.mark.unit
def test_file_store_root_for_ticker_with_active_batch(tmp_path: Path) -> None:
    """验证 _file_store_root_for_ticker 在有活动 batch 时返回 staging 的父目录。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    token = core.begin_batch("AAPL")
    try:
        root = core._file_store_root_for_ticker("AAPL")
        assert root == token.staging_ticker_dir.parent
    finally:
        core.rollback_batch(token)


@pytest.mark.unit
def test_file_store_root_for_ticker_without_active_batch(tmp_path: Path) -> None:
    """验证 _file_store_root_for_ticker 在无活动 batch 时返回 portfolio_root。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    root = core._file_store_root_for_ticker("AAPL")
    assert root == core.portfolio_root


@pytest.mark.unit
def test_processed_manifest_path(tmp_path: Path) -> None:
    """验证 _processed_manifest_path 返回正确路径。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    path = core._processed_manifest_path("AAPL")
    assert path.name == "manifest.json"
    assert "processed" in path.parts


@pytest.mark.unit
def test_processed_manifest_path_for_read(tmp_path: Path) -> None:
    """验证 _processed_manifest_path_for_read 返回正确路径。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    path = core._processed_manifest_path_for_read("AAPL")
    assert path.name == "manifest.json"
    assert "processed" in path.parts


@pytest.mark.unit
def test_remove_manifest_item(tmp_path: Path) -> None:
    """验证 _remove_manifest_item 从 manifest 中移除指定文档。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    # 先创建一个 manifest
    manifest_path = core._filing_manifest_path("AAPL")
    from dayu.fins.storage._fs_storage_utils import _write_json
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(manifest_path, {
        "ticker": "AAPL",
        "updated_at": "2024-01-01",
        "documents": [
            {"document_id": "fil_1", "name": "one"},
            {"document_id": "fil_2", "name": "two"},
        ],
    })

    core._remove_manifest_item(manifest_path, "AAPL", "fil_1")
    from dayu.fins.storage._fs_storage_utils import _read_json_object
    result = _read_json_object(manifest_path)
    assert [d["document_id"] for d in result["documents"]] == ["fil_2"]


@pytest.mark.unit
def test_remove_manifest_items(tmp_path: Path) -> None:
    """验证 _remove_manifest_items 批量移除文档。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    manifest_path = core._filing_manifest_path("AAPL")
    from dayu.fins.storage._fs_storage_utils import _write_json
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(manifest_path, {
        "ticker": "AAPL",
        "updated_at": "2024-01-01",
        "documents": [
            {"document_id": "fil_1", "name": "one"},
            {"document_id": "fil_2", "name": "two"},
            {"document_id": "fil_3", "name": "three"},
        ],
    })

    core._remove_manifest_items(manifest_path, "AAPL", ["fil_1", "fil_3"])
    from dayu.fins.storage._fs_storage_utils import _read_json_object
    result = _read_json_object(manifest_path)
    assert [d["document_id"] for d in result["documents"]] == ["fil_2"]


@pytest.mark.unit
def test_recover_orphan_backup_dirs_skips_non_directory(tmp_path: Path) -> None:
    """验证 _recover_orphan_backup_dirs 跳过 backup_root 下的非目录文件。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    (core.backup_root / "not-a-dir.txt").write_text("noise", encoding="utf-8")

    actions = core._recover_orphan_backup_dirs(dry_run=True)
    assert actions == []


@pytest.mark.unit
def test_recover_orphan_backup_dirs_skips_unparseable_name(tmp_path: Path) -> None:
    """验证 _recover_orphan_backup_dirs 跳过无法解析的目录名。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    (core.backup_root / "invalid-backup-name").mkdir(parents=True, exist_ok=True)

    actions = core._recover_orphan_backup_dirs(dry_run=True)
    assert actions == []


@pytest.mark.unit
def test_recover_orphan_backup_dirs_restores_when_no_target(tmp_path: Path) -> None:
    """验证孤儿 backup 在目标不存在时恢复为正式目录。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    # 创建一个 orphan backup 目录
    backup_dir = core.backup_root / "ORPHAN.bak.deadbeef"
    (backup_dir / "filings").mkdir(parents=True, exist_ok=True)
    (backup_dir / "filings" / "data.txt").write_text("restored", encoding="utf-8")

    actions = core._recover_orphan_backup_dirs(dry_run=False)
    assert any("restore backup ticker=ORPHAN" in a for a in actions)
    target_dir = core._target_ticker_dir("ORPHAN")
    assert (target_dir / "filings" / "data.txt").read_text(encoding="utf-8") == "restored"
    assert not backup_dir.exists()


@pytest.mark.unit
def test_recover_orphan_backup_dirs_deletes_when_target_exists(tmp_path: Path) -> None:
    """验证孤儿 backup 在目标已存在时被清理。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    # 创建正式目录
    target_dir = core._target_ticker_dir("ORPHAN")
    (target_dir / "filings").mkdir(parents=True, exist_ok=True)

    # 创建同名 orphan backup
    backup_dir = core.backup_root / "ORPHAN.bak.deadbeef"
    (backup_dir / "filings").mkdir(parents=True, exist_ok=True)

    actions = core._recover_orphan_backup_dirs(dry_run=False)
    assert any("delete backup ticker=ORPHAN" in a for a in actions)
    assert not backup_dir.exists()
    assert target_dir.exists()


@pytest.mark.unit
def test_recover_orphan_backup_dirs_skips_when_corresponding_batch_exists(tmp_path: Path) -> None:
    """验证孤儿 backup 在对应 batch token 目录仍存在时跳过（由 batch recovery 处理）。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    backup_dir = core.backup_root / "AAPL.bak.abc123"
    backup_dir.mkdir(parents=True, exist_ok=True)
    token_dir = core.batch_root / "abc123"
    token_dir.mkdir(parents=True, exist_ok=True)

    actions = core._recover_orphan_backup_dirs(dry_run=True)
    assert actions == []


@pytest.mark.unit
def test_recover_orphan_backup_dirs_dry_run(tmp_path: Path) -> None:
    """验证 _recover_orphan_backup_dirs dry-run 不修改文件系统。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    backup_dir = core.backup_root / "DRYRUN.bak.abc123"
    (backup_dir / "filings").mkdir(parents=True, exist_ok=True)

    actions = core._recover_orphan_backup_dirs(dry_run=True)
    assert any("restore backup ticker=DRYRUN" in a for a in actions)
    assert backup_dir.exists()


@pytest.mark.unit
def test_recover_single_batch_dir_skips_missing_journal_and_ticker(tmp_path: Path) -> None:
    """验证 recovery 跳过无 journal 且无 ticker 推断依据的 batch token 目录。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    token_dir = core.batch_root / "empty-token"
    token_dir.mkdir(parents=True, exist_ok=True)

    actions = core._recover_single_batch_dir(token_dir, dry_run=True)
    assert len(actions) == 1
    assert "missing journal" in actions[0]


@pytest.mark.unit
def test_recover_single_batch_dir_with_backed_up_target_phase(tmp_path: Path) -> None:
    """验证 recovery 对 backed_up_target 阶段恢复 backup。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    # 先创建 target 目录（模拟已有数据的 ticker）
    target_dir = core._target_ticker_dir("AAPL")
    (target_dir / "filings").mkdir(parents=True, exist_ok=True)
    (target_dir / "filings" / "data.txt").write_text("original", encoding="utf-8")

    token = core.begin_batch("AAPL")
    core._write_batch_journal(token, "backed_up_target")

    # 模拟 backed_up_target 状态：target 已移到 backup
    backup_dir = token.backup_dir
    target_dir.rename(backup_dir)

    core._active_batches.clear()
    core._release_ticker_lock(token.ticker)

    actions = core.recover_orphan_batches()
    assert any("restore backup ticker=AAPL" in a for a in actions)
    assert target_dir.exists()
    assert not backup_dir.exists()


@pytest.mark.unit
def test_begin_batch_cleans_up_staging_on_journal_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 begin_batch 在 journal 写入失败时清理 staging 并释放锁。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    original_write = core._write_batch_journal
    call_count = 0

    def _failing_once_write(token: object, phase: str) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError("disk full")
        original_write(token, phase)  # type: ignore[arg-type]

    monkeypatch.setattr(core, "_write_batch_journal", _failing_once_write)

    with pytest.raises(OSError, match="disk full"):
        core.begin_batch("AAPL")

    # 锁已释放，可以重新开启
    token = core.begin_batch("AAPL")
    try:
        assert token.ticker == "AAPL"
    finally:
        core.rollback_batch(token)


@pytest.mark.unit
def test_processed_dir_for_read(tmp_path: Path) -> None:
    """验证 _processed_dir_for_read 返回正确路径。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    path = core._processed_dir_for_read("AAPL", "doc_1")
    assert path == core.portfolio_root / "AAPL" / "processed" / "doc_1"


@pytest.mark.unit
def test_ensure_batch_recovery_is_idempotent(tmp_path: Path) -> None:
    """验证 ensure_batch_recovery 只执行一次恢复。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core

    actions_first = core.ensure_batch_recovery()
    actions_second = core.ensure_batch_recovery()
    assert actions_first == ()
    assert actions_second == ()


# ---------- S14-CR-03/04：publish 匹配真源与 startup fail-closed ----------


class _FakeStagedStore:
    """S3 staged 模式记录型 fake（真实 sha；可注入 publish 失败次数）。

    实现 ``StagedFileStoreProtocol`` 与 ``FileStore`` 读写面：``stat_object``
    真实计算 digest/size；``fail_publish_remaining`` 控制前 N 次 CopyObject
    抛 ``OSError``（模拟模糊响应）；``forced_stat`` 可伪造远端 HEAD 元数据
    （构造 same-SHA/different-size 等现实中需要注入的对手样本）。
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.publish_calls: list[tuple[str, str]] = []
        self.fail_publish_remaining: int = 0
        self.forced_stat: dict[str, tuple[str, int]] = {}

    def _sha256_of(self, content: bytes) -> str:
        """计算内容 SHA-256。

        Args:
            content: 字节内容。

        Returns:
            SHA-256 hex。

        Raises:
            无。
        """

        return hashlib.sha256(content).hexdigest()

    def stage_publish(self, *, operation_id: str, data: BinaryIO) -> FileObjectMeta:
        """写入 staging key 并返回真实元数据。

        Args:
            operation_id: 当前 operation id。
            data: caller 二进制流。

        Returns:
            staging key 对应元数据。

        Raises:
            无。
        """

        content = data.read()
        digest = self._sha256_of(content)
        key = f".dayu-staging/{operation_id}/{digest}"
        self.objects[key] = content
        return FileObjectMeta(uri=self.object_uri(key), sha256=digest, size=len(content))

    def publish_staged(
        self,
        *,
        staging_key: str,
        final_key: str,
        content_type: str | None,
        metadata: dict[str, str],
    ) -> None:
        """单次 CopyObject；前 N 次可注入失败。

        Args:
            staging_key: staging key。
            final_key: final key。
            content_type: 可选内容类型。
            metadata: 扩展元数据。

        Returns:
            无。

        Raises:
            OSError: ``fail_publish_remaining`` 大于 0 时抛出。
        """

        del content_type, metadata
        self.publish_calls.append((staging_key, final_key))
        if self.fail_publish_remaining > 0:
            self.fail_publish_remaining -= 1
            raise OSError("publish failed")
        self.objects[final_key] = self.objects[staging_key]

    def object_uri(self, key: str) -> str:
        """构造对象 URI。

        Args:
            key: 对象 key。

        Returns:
            ``s3://bucket/{key}`` URI。

        Raises:
            无。
        """

        return f"s3://bucket/{key}"

    def key_from_uri(self, uri: str) -> str:
        """从 URI 提取 key。

        Args:
            uri: ``s3://bucket/{key}`` URI。

        Returns:
            key 部分。

        Raises:
            无。
        """

        return uri.split("s3://bucket/", 1)[1]

    def delete_object_idempotent(self, key: str) -> None:
        """幂等删除对象。

        Args:
            key: 对象 key。

        Returns:
            无。

        Raises:
            无。
        """

        self.objects.pop(key, None)

    def stat_object(self, key: str) -> FileObjectMeta:
        """HEAD 返回真实或伪造的 digest/size。

        Args:
            key: 对象 key。

        Returns:
            对象元数据。

        Raises:
            FileNotFoundError: 对象缺失时抛出。
        """

        if key not in self.objects:
            raise FileNotFoundError(f"对象不存在: {key}")
        forced = self.forced_stat.get(key)
        if forced is not None:
            forced_sha, forced_size = forced
            return FileObjectMeta(uri=self.object_uri(key), sha256=forced_sha, size=forced_size)
        content = self.objects[key]
        return FileObjectMeta(
            uri=self.object_uri(key),
            sha256=self._sha256_of(content),
            size=len(content),
        )

    def list_objects(self, prefix: str) -> list[FileObjectMeta]:
        """列出对象。

        Args:
            prefix: key 前缀。

        Returns:
            匹配对象元数据列表。

        Raises:
            无。
        """

        return [
            FileObjectMeta(uri=self.object_uri(key))
            for key in sorted(self.objects)
            if key.startswith(prefix)
        ]

    def get_object(self, key: str) -> BytesIO:
        """读取对象字节。

        Args:
            key: 对象 key。

        Returns:
            对象字节流。

        Raises:
            FileNotFoundError: 对象缺失时抛出。
        """

        if key not in self.objects:
            raise FileNotFoundError(f"对象不存在: {key}")
        return BytesIO(self.objects[key])

    def put_object(
        self,
        key: str,
        data: BinaryIO,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> FileObjectMeta:
        """写入对象（FileStore 协议面）。

        Args:
            key: 对象 key。
            data: 二进制流。
            content_type: 可选内容类型。
            metadata: 扩展元数据。

        Returns:
            对象元数据。

        Raises:
            无。
        """

        del content_type, metadata
        content = data.read()
        self.objects[key] = content
        return FileObjectMeta(
            uri=self.object_uri(key),
            sha256=self._sha256_of(content),
            size=len(content),
        )

    def delete_object(self, key: str) -> None:
        """删除对象（FileStore 协议面）。

        Args:
            key: 对象 key。

        Returns:
            无。

        Raises:
            FileNotFoundError: 对象缺失时抛出。
        """

        if key not in self.objects:
            raise FileNotFoundError(f"对象不存在: {key}")
        self.objects.pop(key, None)

    def get_presigned_url(self, key: str, expires_in: int) -> str:
        """构造预签名 URL（FileStore 协议面）。

        Args:
            key: 对象 key。
            expires_in: 有效秒数。

        Returns:
            预签名 URL。

        Raises:
            无。
        """

        del key, expires_in
        return "https://presigned.example/presigned"


def _s3_staged_core(
    tmp_path: Path,
    fake: _FakeStagedStore,
    *,
    create_directories: bool = True,
) -> FsStorageCore:
    """构造注入 fake staged store 的 core。

    Args:
        tmp_path: 工作区根目录。
        fake: fake staged store。
        create_directories: 是否在构造时创建目录并立即执行 startup recovery；
            ``False`` 时由调用方显式调用 ``ensure_batch_recovery``。

    Returns:
        S3 模式 core。

    Raises:
        OSError: 仓储初始化失败时抛出。
    """

    repository_set = build_fs_repository_set(
        workspace_root=tmp_path,
        file_store=fake,
        create_directories=create_directories,
    )
    return repository_set.core


def _simulate_crash(core: FsStorageCore, token: BatchToken) -> None:
    """模拟 owner 进程崩溃：清空活动 batch 并释放 ticker 锁。

    Args:
        core: S3 模式 core。
        token: 待遗留的 batch token。

    Returns:
        无。

    Raises:
        无。
    """

    core._active_batches.clear()
    core._release_ticker_lock(token.ticker)


def _staged_filing_batch(
    core: FsStorageCore,
    fake: _FakeStagedStore,
    *,
    content: bytes = b"a",
) -> BatchToken:
    """begin batch 并 stage 一个 source filing 文件（commit 前崩溃点）。

    Args:
        core: S3 模式 core。
        fake: fake staged store。
        content: 待 stage 的文件内容。

    Returns:
        遗留的 batch token。

    Raises:
        OSError: 仓储写入失败时抛出。
    """

    handle = SourceHandle(ticker="AAPL", document_id="fil_1", source_kind="filing")
    token = core.begin_batch("AAPL")
    core.store_file(handle, "a.pdf", BytesIO(content))
    return token


def _final_key() -> str:
    """返回测试 final key。

    Args:
        无。

    Returns:
        AAPL source filing 的 PDF final key。

    Raises:
        无。
    """

    return "AAPL/filings/fil_1/a.pdf"


def _stage_key_of(fake: _FakeStagedStore) -> str:
    """返回 journal 中唯一 staging key。

    Args:
        fake: fake staged store。

    Returns:
        唯一 staging key。

    Raises:
        AssertionError: staging 对象数量不为 1 时抛出。
    """

    staging_keys = [key for key in fake.objects if key.startswith(".dayu-staging/")]
    assert len(staging_keys) == 1
    return staging_keys[0]


@pytest.mark.unit
def test_publish_one_target_same_size_diff_sha_republishes(tmp_path: Path) -> None:
    """commit 模糊 Copy 判定：同-size/different-SHA final 不得被当作已完成。

    预置同 size 不同 SHA 的错误对象；首次 CopyObject 抛 OSError（响应模糊），
    head 判定必须同时匹配 SHA 与 size 才返回——不匹配则 staging 存在时重试发布，
    最终 final bytes 为 staging 真值（S14-CR-03）。
    """

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    key = _final_key()
    wrong = b"b"
    fake.put_object(key, BytesIO(wrong))
    fake.fail_publish_remaining = 1

    core.commit_batch(token)

    assert fake.get_object(key).read() == b"a"
    assert len(fake.publish_calls) == 2


@pytest.mark.unit
def test_publish_one_target_same_sha_diff_size_not_accepted(tmp_path: Path) -> None:
    """commit 模糊 Copy 判定：same-SHA/different-size final 不得被当作已完成。

    伪造远端 HEAD 返回与 target 相同 SHA 但不同 size；首次 CopyObject 抛
    OSError，head 判定 SHA 与 size 任一不匹配 => staging 存在时重试发布
    （S14-CR-03）。
    """

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    key = _final_key()
    wrong = b"b"
    fake.put_object(key, BytesIO(wrong))
    fake.forced_stat[key] = (hashlib.sha256(b"a").hexdigest(), len(wrong) + 1)
    fake.fail_publish_remaining = 1

    core.commit_batch(token)

    assert fake.get_object(key).read() == b"a"
    assert len(fake.publish_calls) == 2


@pytest.mark.unit
def test_publish_one_target_exact_match_skips_retry(tmp_path: Path) -> None:
    """commit 模糊 Copy 判定：SHA 与 size 同时匹配 => 幂等视为完成，不再重试。"""

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    key = _final_key()
    fake.put_object(key, BytesIO(b"a"))
    fake.fail_publish_remaining = 1

    core.commit_batch(token)

    assert fake.get_object(key).read() == b"a"
    assert len(fake.publish_calls) == 1


@pytest.mark.unit
def test_publish_one_target_staging_missing_fails_closed(tmp_path: Path) -> None:
    """commit 模糊 Copy 判定：不匹配且 staging 缺失 => fail closed，不置 verified。"""

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    key = _final_key()
    wrong = b"b"
    fake.put_object(key, BytesIO(wrong))
    fake.delete_object_idempotent(_stage_key_of(fake))
    fake.fail_publish_remaining = 1

    with pytest.raises(RuntimeError, match="fail closed"):
        core.commit_batch(token)

    assert fake.get_object(key).read() == b"b"
    from dayu.fins.storage.remote_op_journal import list_journal_ids

    assert list_journal_ids(core.dayu_root) == [token.token_id]


@pytest.mark.unit
def test_recovery_publish_same_size_diff_sha_republishes_from_staging(tmp_path: Path) -> None:
    """startup recovery：同-size/different-SHA final 必须从 staging 重发布。"""

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    _simulate_crash(core, token)
    key = _final_key()
    fake.put_object(key, BytesIO(b"b"))

    restarted = _s3_staged_core(tmp_path, fake, create_directories=False)
    restarted.ensure_batch_recovery()

    assert fake.get_object(key).read() == b"a"
    from dayu.fins.storage.remote_op_journal import list_journal_ids

    assert list_journal_ids(tmp_path / ".dayu") == []


@pytest.mark.unit
def test_recovery_publish_same_sha_diff_size_republishes_from_staging(tmp_path: Path) -> None:
    """startup recovery：same-SHA/different-size final 必须从 staging 重发布。"""

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    _simulate_crash(core, token)
    key = _final_key()
    wrong = b"b"
    fake.put_object(key, BytesIO(wrong))
    fake.forced_stat[key] = (hashlib.sha256(b"a").hexdigest(), len(wrong) + 1)

    restarted = _s3_staged_core(tmp_path, fake, create_directories=False)
    restarted.ensure_batch_recovery()

    assert fake.get_object(key).read() == b"a"
    from dayu.fins.storage.remote_op_journal import list_journal_ids

    assert list_journal_ids(tmp_path / ".dayu") == []


@pytest.mark.unit
def test_recovery_publish_exact_match_verifies_without_republish(tmp_path: Path) -> None:
    """startup recovery：SHA 与 size 同时匹配 => 只幂等 verify，不重复发布。"""

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    _simulate_crash(core, token)
    fake.put_object(_final_key(), BytesIO(b"a"))

    restarted = _s3_staged_core(tmp_path, fake, create_directories=False)
    restarted.ensure_batch_recovery()

    assert fake.publish_calls == []
    assert fake.get_object(_final_key()).read() == b"a"
    from dayu.fins.storage.remote_op_journal import list_journal_ids

    assert list_journal_ids(tmp_path / ".dayu") == []


@pytest.mark.unit
def test_recovery_publish_staging_missing_fails_closed_preserves_remote(tmp_path: Path) -> None:
    """startup recovery：不匹配且 staging 缺失 => fail closed，保留 journal 与远端。"""

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    _simulate_crash(core, token)
    key = _final_key()
    fake.put_object(key, BytesIO(b"b"))
    fake.delete_object_idempotent(_stage_key_of(fake))

    restarted = _s3_staged_core(tmp_path, fake, create_directories=False)
    with pytest.raises(RuntimeError, match="fail closed"):
        restarted.ensure_batch_recovery()

    from dayu.fins.storage.remote_op_journal import journal_path, list_journal_ids

    assert journal_path(tmp_path / ".dayu", token.token_id).exists()
    assert list_journal_ids(tmp_path / ".dayu") == [token.token_id]
    assert fake.get_object(key).read() == b"b"


def _corrupt_journal_and_assert_preserved(
    tmp_path: Path,
    token: BatchToken,
    payload: str,
    fake: _FakeStagedStore,
) -> None:
    """写入损坏/非法 journal，断言 startup fail closed 且全部保留。

    Args:
        tmp_path: 工作区根目录。
        token: 已遗留的 batch token。
        payload: 损坏/非法 journal 内容。
        fake: 同一 fake staged store（远端对象必须仍可读）。

    Returns:
        无。

    Raises:
        RemoteOpJournalError: ensure_batch_recovery 稳定抛出（测试通过条件）。
    """

    from dayu.fins.storage.remote_op_journal import RemoteOpJournalError, journal_path

    journal_file = journal_path(tmp_path / ".dayu", token.token_id)
    journal_file.parent.mkdir(parents=True, exist_ok=True)
    journal_file.write_text(payload, encoding="utf-8")
    restarted = _s3_staged_core(tmp_path, _FakeStagedStore(), create_directories=False)
    with pytest.raises(RemoteOpJournalError):
        restarted.ensure_batch_recovery()
    assert journal_file.exists()
    assert token.staging_root_dir.exists()
    assert fake.get_object(_final_key()).read() == b"a"


@pytest.mark.unit
def test_startup_corrupt_json_journal_fails_closed_preserves_all(tmp_path: Path) -> None:
    """first-copy 后 corrupt JSON journal：startup fail closed，一切保留。"""

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    fake.put_object(_final_key(), BytesIO(b"a"))
    _simulate_crash(core, token)

    _corrupt_journal_and_assert_preserved(tmp_path, token, "{not-json", fake)


@pytest.mark.unit
def test_startup_partial_invalid_target_journal_fails_closed_preserves_all(tmp_path: Path) -> None:
    """partial/unknown action target journal：startup fail closed，一切保留。"""

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    fake.put_object(_final_key(), BytesIO(b"a"))
    _simulate_crash(core, token)
    journal_file = Path(str(tmp_path / ".dayu" / "remote_ops" / f"{token.token_id}.json"))
    raw = json.loads(journal_file.read_text(encoding="utf-8"))
    raw["targets"].append({"action": "explode", "final_key": "x"})

    _corrupt_journal_and_assert_preserved(tmp_path, token, json.dumps(raw), fake)


@pytest.mark.unit
def test_startup_unknown_phase_journal_fails_closed_preserves_all(tmp_path: Path) -> None:
    """unknown phase journal：startup fail closed，一切保留。"""

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    fake.put_object(_final_key(), BytesIO(b"a"))
    _simulate_crash(core, token)
    journal_file = Path(str(tmp_path / ".dayu" / "remote_ops" / f"{token.token_id}.json"))
    raw = json.loads(journal_file.read_text(encoding="utf-8"))
    raw["phase"] = "not-a-phase"

    _corrupt_journal_and_assert_preserved(tmp_path, token, json.dumps(raw), fake)


@pytest.mark.unit
def test_startup_duplicate_key_journal_fails_closed_preserves_all(tmp_path: Path) -> None:
    """duplicate publish key journal：startup fail closed，一切保留。"""

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    fake.put_object(_final_key(), BytesIO(b"a"))
    _simulate_crash(core, token)
    journal_file = Path(str(tmp_path / ".dayu" / "remote_ops" / f"{token.token_id}.json"))
    raw = json.loads(journal_file.read_text(encoding="utf-8"))
    raw["targets"].append(dict(raw["targets"][0]))

    _corrupt_journal_and_assert_preserved(tmp_path, token, json.dumps(raw), fake)


@pytest.mark.unit
def test_startup_operation_id_mismatch_fails_closed_preserves_all(tmp_path: Path) -> None:
    """body operation_id 与文件名身份不一致：startup fail closed 且零副作用（S14-RR-01）。

    崩溃后 journal body 的 ``operation_id`` 被损坏为另一合法非空值；startup
    必须在任何远端 publish/delete 与 FS swap 之前稳定抛
    ``RemoteOpJournalError``，保留原 journal、batch staging 目录与远端
    staging/final bytes，绝不先发布 final 再因 token 目录缺失失败。
    """

    from dayu.fins.storage.remote_op_journal import RemoteOpJournalError, journal_path, list_journal_ids

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    fake.put_object(_final_key(), BytesIO(b"a"))
    _simulate_crash(core, token)
    journal_file = journal_path(tmp_path / ".dayu", token.token_id)
    raw = json.loads(journal_file.read_text(encoding="utf-8"))
    raw["operation_id"] = "other-valid-operation-id"
    journal_file.write_text(json.dumps(raw), encoding="utf-8")
    objects_before = dict(fake.objects)

    restarted = _s3_staged_core(tmp_path, fake, create_directories=False)
    with pytest.raises(RemoteOpJournalError):
        restarted.ensure_batch_recovery()

    # 零远端 publish/delete、零 FS swap：journal 与 batch staging 目录保留，
    # 远端 staging/final bytes 逐字不变。
    assert journal_file.exists()
    assert token.staging_root_dir.exists()
    assert list_journal_ids(tmp_path / ".dayu") == [token.token_id]
    assert fake.publish_calls == []
    assert fake.objects == objects_before


@pytest.mark.unit
def test_startup_staging_namespace_mismatch_fails_closed_preserves_all(tmp_path: Path) -> None:
    """publish staging_key 命名空间不属于本 operation：startup fail closed 全保留。

    staging key 引用其它 operation 的命名空间视为结构性损坏（S14-RR-01），
    startup 在发布/删除/FS swap 前 fail closed，证据全保留。
    """

    from dayu.fins.storage.remote_op_journal import RemoteOpJournalError, journal_path, list_journal_ids

    fake = _FakeStagedStore()
    core = _s3_staged_core(tmp_path, fake)
    token = _staged_filing_batch(core, fake, content=b"a")
    fake.put_object(_final_key(), BytesIO(b"a"))
    _simulate_crash(core, token)
    journal_file = journal_path(tmp_path / ".dayu", token.token_id)
    raw = json.loads(journal_file.read_text(encoding="utf-8"))
    raw["targets"][0]["staging_key"] = ".dayu-staging/other-valid-operation-id/deadbeef"
    journal_file.write_text(json.dumps(raw), encoding="utf-8")
    objects_before = dict(fake.objects)

    restarted = _s3_staged_core(tmp_path, fake, create_directories=False)
    with pytest.raises(RemoteOpJournalError):
        restarted.ensure_batch_recovery()

    assert journal_file.exists()
    assert token.staging_root_dir.exists()
    assert list_journal_ids(tmp_path / ".dayu") == [token.token_id]
    assert fake.publish_calls == []
    assert fake.objects == objects_before
