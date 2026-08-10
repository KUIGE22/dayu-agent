"""StoreFileSource 单元测试（S14-CTRL-03/06 FileStore-backed Source）。"""

from __future__ import annotations

import io
from pathlib import Path
from typing import BinaryIO

import pytest

from dayu.fins.domain.document_models import FileObjectMeta
from dayu.fins.storage.file_store import FileStore
from dayu.fins.storage.store_source import StoreFileSource


class _FakeFileStore(FileStore):
    """实现 FileStore 的窄 fake。"""

    def __init__(self, content: bytes) -> None:
        self._content = content

    def get_object(self, key: str) -> BinaryIO:
        """返回内容流。"""

        return io.BytesIO(self._content)

    def put_object(
        self,
        key: str,
        data: BinaryIO,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> FileObjectMeta:
        """未使用。"""

        del key, data, content_type, metadata
        raise NotImplementedError

    def stat_object(self, key: str) -> FileObjectMeta:
        """未使用。"""

        del key
        raise NotImplementedError

    def delete_object(self, key: str) -> None:
        """未使用。"""

        del key
        raise NotImplementedError

    def get_presigned_url(self, key: str, expires_in: int) -> str:
        """未使用。"""

        del key, expires_in
        raise NotImplementedError

    def list_objects(self, prefix: str) -> list[FileObjectMeta]:
        """未使用。"""

        del prefix
        raise NotImplementedError


def _build_source() -> StoreFileSource:
    """构造测试用 StoreFileSource。"""

    return StoreFileSource(
        file_store=_FakeFileStore(b"%PDF-1.7 fake"),
        file_meta=FileObjectMeta(
            uri="s3://bucket/AAPL/filings/fil_1/primary.pdf",
            content_type="application/pdf",
            size=14,
            sha256="a" * 64,
        ),
        key="AAPL/filings/fil_1/primary.pdf",
    )


def test_source_properties() -> None:
    """uri/media_type/content_length/etag 透传 file_meta。"""

    source = _build_source()
    assert source.uri == "s3://bucket/AAPL/filings/fil_1/primary.pdf"
    assert source.media_type == "application/pdf"
    assert source.content_length == 14
    assert source.etag is None


def test_open_returns_seekable_reusable_stream() -> None:
    """open() 返回 seekable、可顺序重读的 caller-owned 流。"""

    source = _build_source()
    stream = source.open()
    try:
        assert stream.read() == b"%PDF-1.7 fake"
        stream.seek(0)
        assert stream.read() == b"%PDF-1.7 fake"
    finally:
        stream.close()


def test_materialize_returns_caller_owned_path(tmp_path: Path) -> None:
    """materialize() 生成 caller-owned 临时文件路径。"""

    source = _build_source()
    path = source.materialize(suffix=".pdf")
    try:
        assert path.suffix == ".pdf"
        assert path.read_bytes() == b"%PDF-1.7 fake"
    finally:
        path.unlink(missing_ok=True)


def test_materialize_without_suffix(tmp_path: Path) -> None:
    """materialize() 无后缀时仍可读取。"""

    source = _build_source()
    path = source.materialize()
    try:
        assert path.read_bytes() == b"%PDF-1.7 fake"
    finally:
        path.unlink(missing_ok=True)


def test_open_missing_raises() -> None:
    """get_object 抛 FileNotFoundError 时 open() 透传。"""

    class _MissingStore(_FakeFileStore):
        """缺失 store。"""

        def __init__(self) -> None:
            """初始化。"""

            super().__init__(b"")

        def get_object(self, key: str) -> BinaryIO:
            """抛缺失。"""

            del key
            raise FileNotFoundError("对象不存在")

    source = StoreFileSource(
        file_store=_MissingStore(),
        file_meta=FileObjectMeta(uri="s3://bucket/x.pdf"),
        key="x.pdf",
    )
    with pytest.raises(FileNotFoundError):
        source.open()


def test_materialize_closes_stream_after_write(tmp_path: Path) -> None:
    """materialize() 完成后关闭底层流。"""

    class _TrackingStore(_FakeFileStore):
        """记录 close 的 store。"""

        closed = False

        def __init__(self) -> None:
            """初始化。"""

            super().__init__(b"data")

        def get_object(self, key: str) -> BinaryIO:
            """返回记录型流。"""

            del key

            class _TrackingStream(io.BytesIO):
                """记录 close 的流。"""

                def close(self) -> None:
                    _TrackingStore.closed = True
                    super().close()

            return _TrackingStream(b"data")

    source = StoreFileSource(
        file_store=_TrackingStore(),
        file_meta=FileObjectMeta(uri="s3://bucket/x.pdf"),
        key="x.pdf",
    )
    path = source.materialize()
    try:
        assert path.read_bytes() == b"data"
        assert _TrackingStore.closed is True
    finally:
        path.unlink(missing_ok=True)
