"""文件系统仓储 — Blob / 文件条目操作 mixin。

S3 模式（注入 ``StagedFileStoreProtocol``）下：

- ``list_entries`` / ``read_file_bytes`` 经 ``FileStore.list_objects`` /
  ``get_object`` 访问远端 bytes（S14-CTRL-03 byte-path matrix）；
- ``store_file`` 必须已有该 ticker 的 active explicit BatchToken，否则稳定抛
  ``s3_write_requires_batch``；有 active batch 时只执行 remote staging（put 到
  ``.dayu-staging/{operation_id}/{sha256}``）并追加 ``action=publish``
  per-target journal 条目（``publish_state=staged``），final 发布只发生在
  ``commit_batch``（S14-CTRL-04）；
- ``delete_entry`` 分类 ``EXPLICIT_REQUIRED``，S3 模式绝不直接远端删除：经
  私有同-core stage-delete helper 对每个要删 key 记录 ``action=delete``/
  ``delete_state=pending`` 并只改 staging local，remote delete 只在 commit 的
  post-swap cleanup 或 recovery 收敛（S14-CTRL-13）。

FS/local 模式行为逐字节不变。
"""

from __future__ import annotations

import shutil
from typing import BinaryIO, Optional

from dayu.fins.domain.document_models import (
    DocumentEntry,
    FileObjectMeta,
    ProcessedHandle,
    SourceHandle,
)

from ._fs_storage_infra import BatchAdmission, _FsStorageInfra
from ._fs_storage_utils import (
    _file_object_meta_from_dict,
    _normalize_entry_name,
    _normalize_ticker,
)
from .file_store import FileStore
from .s3_file_store import StagedFileStoreProtocol


def _key_from_stored_uri(file_store: FileStore, uri: str) -> str:
    """从对象 URI 提取 key（S3 模式）。

    Args:
        file_store: 注入的文件存储。
        uri: 对象 URI。

    Returns:
        key 部分。

    Raises:
        ValueError: URI 形态非法时抛出。
    """

    assert isinstance(file_store, StagedFileStoreProtocol)
    return file_store.key_from_uri(uri)


def _get_object(file_store: FileStore, key: str) -> BinaryIO:
    """经 FileStore 读取对象（S3 模式）。

    Args:
        file_store: 注入的文件存储。
        key: 对象 key。

    Returns:
        caller-owned 二进制流。

    Raises:
        FileNotFoundError: 对象缺失时抛出。
        OSError: 读取或校验失败时抛出。
    """

    return file_store.get_object(key)


class _FsBlobMixin(_FsStorageInfra):
    """Blob / 文件条目操作 mixin。"""

    def list_entries(self, handle: SourceHandle | ProcessedHandle) -> list[DocumentEntry]:
        """列出文档目录下的直系条目。

        Args:
            handle: 源文档/解析产物句柄。

        Returns:
            直系条目列表；目录不存在时返回空列表。

        Raises:
            OSError: 读取目录失败时抛出。
        """

        if self._is_s3_mode():
            return self._list_entries_s3(handle)
        directory = self._handle_dir_path(handle)
        if not directory.exists() or not directory.is_dir():
            return []
        return [
            DocumentEntry(name=child.name, is_file=child.is_file())
            for child in sorted(directory.iterdir(), key=lambda item: item.name)
        ]

    def _list_entries_s3(self, handle: SourceHandle | ProcessedHandle) -> list[DocumentEntry]:
        """经 FileStore 列出文档目录直系条目。

        Args:
            handle: 源文档/解析产物句柄。

        Returns:
            直系条目列表；远端无对象时返回空列表。

        Raises:
            OSError: 列出失败时抛出。
        """

        file_store = self._file_store
        assert file_store is not None
        prefix = self._build_store_key_prefix(handle)
        entries: dict[str, bool] = {}
        for meta in file_store.list_objects(prefix):
            if meta.uri is None:
                continue
            key = _key_from_stored_uri(file_store, meta.uri)
            if not key.startswith(prefix):
                continue
            relative = key[len(prefix):]
            if not relative:
                continue
            head, _, _ = relative.partition("/")
            if not head:
                continue
            entries[head] = "/" not in relative
        return [
            DocumentEntry(name=name, is_file=is_file)
            for name, is_file in sorted(entries.items())
        ]

    def read_file_bytes(self, handle: SourceHandle | ProcessedHandle, filename: str) -> bytes:
        """读取文档目录下的单个文件内容。

        Args:
            handle: 源文档/解析产物句柄。
            filename: 直系文件名。

        Returns:
            文件二进制内容。

        Raises:
            FileNotFoundError: 文件不存在时抛出。
            IsADirectoryError: 目标为目录时抛出。
            OSError: 读取失败时抛出。
        """

        if self._is_s3_mode():
            return self._read_file_bytes_s3(handle, filename)
        path = self._resolve_handle_child_path(handle, filename)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        if path.is_dir():
            raise IsADirectoryError(f"目标是目录，无法按文件读取: {path}")
        return path.read_bytes()

    def _read_file_bytes_s3(self, handle: SourceHandle | ProcessedHandle, filename: str) -> bytes:
        """经 FileStore 读取单个文件字节。

        Args:
            handle: 源文档/解析产物句柄。
            filename: 直系文件名。

        Returns:
            文件二进制内容。

        Raises:
            FileNotFoundError: 对象缺失时抛出。
            OSError: 读取或校验失败时抛出。
        """

        normalized_filename = _normalize_entry_name(filename)
        key = self._build_store_key(handle, normalized_filename)
        file_store = self._file_store
        assert file_store is not None
        stream = _get_object(file_store, key)
        try:
            return stream.read()
        finally:
            stream.close()

    def delete_entry(self, handle: SourceHandle | ProcessedHandle, name: str) -> None:
        """删除文档目录下的单个直系条目。

        Args:
            handle: 源文档/解析产物句柄。
            name: 直系条目名称。

        Returns:
            无。

        Raises:
            FileNotFoundError: 条目不存在时抛出。
            OSError: 删除失败时抛出。
            RuntimeError: S3 模式无 active batch 时抛出
                ``s3_write_requires_batch``。
        """

        self._execute_with_auto_batch(
            handle.ticker,
            self._delete_entry_impl,
            handle,
            name,
            admission=BatchAdmission.EXPLICIT_REQUIRED,
        )

    def _delete_entry_impl(self, handle: SourceHandle | ProcessedHandle, name: str) -> None:
        """执行单个直系条目删除（内部实现）。

        Args:
            handle: 源文档/解析产物句柄。
            name: 直系条目名称。

        Returns:
            无。

        Raises:
            FileNotFoundError: 条目不存在时抛出。
            OSError: 删除失败时抛出。
        """

        if self._is_s3_mode():
            self._delete_entry_impl_s3(handle, name)
            return
        path = self._resolve_handle_child_path(handle, name)
        if not path.exists():
            raise FileNotFoundError(f"条目不存在: {path}")
        if path.is_dir():
            shutil.rmtree(path)
            return
        path.unlink()

    def _delete_entry_impl_s3(self, handle: SourceHandle | ProcessedHandle, name: str) -> None:
        """S3 模式删除条目：stage-delete intent 后只改 staging local。

        Args:
            handle: 源文档/解析产物句柄。
            name: 直系条目名称。

        Returns:
            无。

        Raises:
            FileNotFoundError: 条目不存在时抛出。
            OSError: 删除失败时抛出。
        """

        key = self._build_store_key(handle, _normalize_entry_name(name))
        token = self._active_batches.get(_normalize_ticker(handle.ticker))
        if token is None:
            raise RuntimeError("s3_write_requires_batch")
        self._stage_delete_one_key(token, key)
        path = self._resolve_handle_child_path(handle, name)
        if path.is_dir():
            shutil.rmtree(path)
            return
        path.unlink(missing_ok=True)

    def store_file(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
        data: BinaryIO,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """存储文件并返回文件元数据。

        Args:
            handle: 源文档/解析产物句柄。
            filename: 文件名。
            data: 文件二进制流。
            content_type: 可选内容类型。
            metadata: 可选扩展元数据。

        Returns:
            文件对象元数据。

        Raises:
            FileNotFoundError: 句柄对应文档不存在时抛出。
            ValueError: filename 为空、为 ``.`` / ``..``、或包含路径分隔符时抛出。
            RuntimeError: S3 模式无 active batch 时抛出 ``s3_write_requires_batch``。
            OSError: 写入失败时抛出。
        """

        normalized_filename = _normalize_entry_name(filename)
        normalized_ticker = _normalize_ticker(handle.ticker)
        key = self._build_store_key(handle, normalized_filename)
        if self._is_s3_mode():
            return self._store_file_s3(
                normalized_ticker,
                key,
                data,
                content_type=content_type,
                metadata=metadata,
            )
        file_store = self._build_file_store(normalized_ticker)
        return file_store.put_object(
            key,
            data,
            content_type=content_type,
            metadata=metadata,
        )

    def _store_file_s3(
        self,
        ticker: str,
        key: str,
        data: BinaryIO,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """S3 模式存储：stage + journal（不发布）。

        Args:
            ticker: 股票代码。
            key: 最终对象 key。
            data: 文件二进制流。
            content_type: 可选内容类型。
            metadata: 可选扩展元数据。

        Returns:
            最终 key 对应的文件对象元数据（bytes 尚未发布，final 发布在
            ``commit_batch``）。

        Raises:
            RuntimeError: 无 active batch 时抛出 ``s3_write_requires_batch``。
            OSError: staging 写入或 journal 追加失败时抛出。
        """

        token = self._active_batches.get(ticker)
        if token is None:
            raise RuntimeError("s3_write_requires_batch")
        return self._stage_publish(
            token,
            final_key=key,
            data=data,
            content_type=content_type,
            metadata=metadata,
        )

    def _build_store_key_prefix(self, handle: SourceHandle | ProcessedHandle) -> str:
        """构造文档目录的 key 前缀。

        Args:
            handle: 源文档/解析产物句柄。

        Returns:
            文档目录前缀（含尾部斜杠）。

        Raises:
            无。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        if isinstance(handle, ProcessedHandle):
            return f"{normalized_ticker}/processed/{handle.document_id}/"
        from dayu.fins.domain.enums import SourceKind

        if handle.source_kind == SourceKind.FILING:
            return f"{normalized_ticker}/filings/{handle.document_id}/"
        return f"{normalized_ticker}/materials/{handle.document_id}/"

    def list_files(self, handle: SourceHandle | ProcessedHandle) -> list[FileObjectMeta]:
        """列出文档关联的文件元数据列表。

        Args:
            handle: 源文档/解析产物句柄。

        Returns:
            文件元数据列表。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
            ValueError: 元数据格式非法时抛出。
        """

        meta = self._get_handle_meta(handle)
        files = meta.get("files", [])
        if not isinstance(files, list):
            raise ValueError("meta.files 必须为 list")
        result: list[FileObjectMeta] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            result.append(_file_object_meta_from_dict(item))
        return result
