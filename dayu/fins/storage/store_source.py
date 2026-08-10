"""FileStore-backed Source adapter。

在 S3 模式（注入 ``S3FileStore``）下把 ``FileObjectMeta`` 转换为满足
engine ``Source`` 公共协议的 seekable、caller-owned 流（S14-CTRL-03/06）：

- ``open()`` 经 ``FileStore.get_object(key)`` 返回已验证（SHA-256 相等）、
  seekable、顺序可重读的二进制流；
- ``materialize()`` 生成 caller-owned 临时文件路径并返回；
- 该 adapter 只接收注入的 FileStore 与文件元数据，不接触仓库/batch/token。
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

from dayu.fins.domain.document_models import FileObjectMeta

from .file_store import FileStore


@dataclass(frozen=True)
class StoreFileSource:
    """基于 ``FileStore`` 的对象存储 Source 实现。"""

    file_store: FileStore
    file_meta: FileObjectMeta
    key: str

    @property
    def uri(self) -> str:
        """返回源文件 URI。

        Args:
            无。

        Returns:
            文件元数据 URI。

        Raises:
            无。
        """

        return self.file_meta.uri

    @property
    def media_type(self) -> Optional[str]:
        """返回源文件 media type。

        Args:
            无。

        Returns:
            文件内容类型。

        Raises:
            无。
        """

        return self.file_meta.content_type

    @property
    def content_length(self) -> Optional[int]:
        """返回源文件内容长度。

        Args:
            无。

        Returns:
            文件大小。

        Raises:
            无。
        """

        return self.file_meta.size

    @property
    def etag(self) -> Optional[str]:
        """返回源文件 etag。

        Args:
            无。

        Returns:
            文件 etag。

        Raises:
            无。
        """

        return self.file_meta.etag

    def open(self) -> BinaryIO:
        """打开只读流（caller-owned、已验证、seekable）。

        Args:
            无。

        Returns:
            二进制只读流；caller 负责 close。

        Raises:
            FileNotFoundError: 对象缺失时抛出。
            OSError: 读取或校验失败时抛出。
        """

        return self.file_store.get_object(self.key)

    def materialize(self, suffix: Optional[str] = None) -> Path:
        """物化为 caller-owned 临时文件路径。

        Args:
            suffix: 可选文件后缀。

        Returns:
            可读取的临时文件路径（caller 负责清理）。

        Raises:
            OSError: 临时文件写入失败时抛出。
        """

        stream = self.file_store.get_object(self.key)
        try:
            descriptor, temp_path = tempfile.mkstemp(suffix=suffix or "")
            try:
                with os.fdopen(descriptor, "wb") as target:
                    while True:
                        chunk = stream.read(1024 * 64)
                        if not chunk:
                            break
                        target.write(chunk)
            except Exception:
                Path(temp_path).unlink(missing_ok=True)
                raise
            return Path(temp_path)
        finally:
            stream.close()
