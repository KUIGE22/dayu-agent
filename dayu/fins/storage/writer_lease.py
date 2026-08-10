"""单 writer 排他 lease。

本模块实现 S3 模式下的单 writer 拓扑（S14-CTRL-09）：

- 以 ``.dayu/fins_writer.lock`` 为锁文件获取**非阻塞 exclusive flock**；
  锁文件旁 ``.dayu/fins_writer.json`` 记录 pid/hostname 仅作诊断；
- 已有人持有 => fail-fast 抛稳定错误（不含候选值），拒绝第二 writer，
  绝不 last-writer-wins；
- lease 由 ``PreparedHostRuntimeDependencies`` 私有持有，进程存活期持有，
  ``close()`` 释放（幂等）；进程崩溃时 OS 自动释放 flock；
- 现有 per-ticker batch lock 继续作为单进程内 batch 串行化，不替代本 lease。
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

import dayu.file_lock as file_lock_module

_FINS_WRITER_LOCK_FILENAME = "fins_writer.lock"
_FINS_WRITER_INFO_FILENAME = "fins_writer.json"
_LOCK_NAME = "Fins 单 writer lease"


class WriterLeaseError(RuntimeError):
    """writer lease 获取或释放失败时抛出的错误。"""


@dataclass
class WriterLease:
    """已持有的单 writer lease。

    Args:
        lock_stream: 已持锁的文件流（close 时释放）。
        info_path: 诊断信息文件路径。
        pid: 持有者进程 PID。
        hostname: 持有者主机名。
    """

    lock_stream: TextIO
    info_path: Path
    pid: int
    hostname: str
    _released: bool = field(default=False, init=False, repr=False)

    def release(self) -> None:
        """释放 lease（幂等）。

        Args:
            无。

        Returns:
            无。

        Raises:
            WriterLeaseError: 解锁失败时抛出。
        """

        if self._released:
            return
        try:
            file_lock_module.release_text_file_lock(
                self.lock_stream,
                lock_name=_LOCK_NAME,
            )
        except OSError as exc:
            raise WriterLeaseError("writer lease 释放失败") from exc
        finally:
            self.lock_stream.close()
            self._released = True


def acquire_writer_lease(workspace_root: Path) -> WriterLease:
    """获取工作区的单 writer lease。

    Args:
        workspace_root: 工作区根目录。

    Returns:
        已持有的 lease。

    Raises:
        WriterLeaseError: 已有持有者（锁竞争）、锁文件不可用或加锁失败时抛出；
            错误消息不含候选持有者信息。
    """

    dayu_root = workspace_root / ".dayu"
    dayu_root.mkdir(parents=True, exist_ok=True)
    lock_path = dayu_root / _FINS_WRITER_LOCK_FILENAME
    stream = lock_path.open("a+", encoding="utf-8")
    try:
        file_lock_module.acquire_text_file_lock(
            stream,
            blocking=False,
            lock_name=_LOCK_NAME,
        )
    except OSError as exc:
        stream.close()
        if file_lock_module.is_lock_contention_error(exc):
            raise WriterLeaseError("已有其他 writer 进程持有工作区") from exc
        raise WriterLeaseError("writer lease 获取失败") from exc

    pid = os.getpid()
    hostname = socket.gethostname()
    info_path = dayu_root / _FINS_WRITER_INFO_FILENAME
    try:
        info_path.write_text(
            json.dumps({"pid": pid, "hostname": hostname}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        # 诊断信息写入失败不影响锁本身；记录后继续返回 lease。
        pass
    return WriterLease(
        lock_stream=stream,
        info_path=info_path,
        pid=pid,
        hostname=hostname,
    )
