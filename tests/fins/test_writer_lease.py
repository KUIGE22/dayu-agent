"""writer lease 单元测试（S14-CTRL-09 单 writer 拓扑）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from dayu.fins.storage.writer_lease import WriterLeaseError, acquire_writer_lease


def test_acquire_and_release(tmp_path: Path) -> None:
    """获取后可释放，释放后可重获。"""

    lease = acquire_writer_lease(tmp_path)
    assert lease.pid > 0
    assert lease.info_path.parent == tmp_path / ".dayu"
    lease.release()
    lease.release()  # 幂等
    lease2 = acquire_writer_lease(tmp_path)
    lease2.release()


def test_second_holder_rejected(tmp_path: Path) -> None:
    """第二持有者 fail-fast，拒绝第二 writer。"""

    first = acquire_writer_lease(tmp_path)
    try:
        with pytest.raises(WriterLeaseError):
            acquire_writer_lease(tmp_path)
    finally:
        first.release()


def test_release_allows_reacquire(tmp_path: Path) -> None:
    """release 后可重新获取。"""

    first = acquire_writer_lease(tmp_path)
    first.release()
    second = acquire_writer_lease(tmp_path)
    second.release()


def test_lock_file_created(tmp_path: Path) -> None:
    """锁文件与诊断 json 生成。"""

    acquire_writer_lease(tmp_path).release()
    assert (tmp_path / ".dayu" / "fins_writer.lock").exists()
    assert (tmp_path / ".dayu" / "fins_writer.json").exists()


def test_diagnostic_json_content(tmp_path: Path) -> None:
    """诊断 json 记录 pid/hostname。"""

    import json

    acquire_writer_lease(tmp_path).release()
    info = json.loads((tmp_path / ".dayu" / "fins_writer.json").read_text(encoding="utf-8"))
    assert isinstance(info["pid"], int)
    assert isinstance(info["hostname"], str)
