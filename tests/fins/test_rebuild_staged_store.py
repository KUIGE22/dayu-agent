"""S3 模式 source meta rebuild staged 语义测试（S14-CTRL-12/13）。

验证 ``replace_source_meta``（SEC / CN rebuild 共同使用的 storage-owner
``AUTO_ATOMIC_ALLOWED`` 写入口）在 S3 staged 模式下的三条事实：

- 在 owner 显式同-core batch 内完成 old/new files diff，被移除文件只记
  ``action=delete`` delete intent（``delete_state=pending``），绝不直接远端删除；
- commit 后经 post-swap cleanup 幂等执行 remote delete（fake 收到
  ``delete_object_idempotent``），且未被移除文件不误删；
- 无 active token 时 ``AUTO_ATOMIC_ALLOWED`` 自建短内部 batch 并提交，
  meta swap 生效：``meta.files`` 收缩、新字段生效。
"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from dayu.fins.domain.document_models import DocumentMeta, FileObjectMeta, FilingCreateRequest
from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage.s3_file_store import StagedFileStoreProtocol
from tests.fins.storage_testkit import FsStorageTestContext, build_fs_storage_test_context

_TICKER = "600519"
_DOCUMENT_ID = "fil_cn_rebuild"
_INTERNAL_DOCUMENT_ID = "internal_cn_rebuild"
_REBUILD_VERSION = "cn_pipeline_download_v1.0.0"
_SHA256_HEX = "0" * 64
_TIMESTAMP = "2026-01-01T00:00:00+00:00"


class _FakeStagedStore(StagedFileStoreProtocol):
    """记录远端写入/删除调用的 staged fake。

    实现 ``StagedFileStoreProtocol`` 全部方法；``stat_object`` 供
    ``_stage_delete_one_key`` head 校验使用，恒返回固定 sha/size，保证
    stage-delete 记录与 commit 时 head 验证一致。
    """

    def __init__(self) -> None:
        """初始化空 fake。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.deleted_keys: list[str] = []
        self.staged_objects: dict[str, bytes] = {}

    def stage_publish(self, *, operation_id: str, data: BinaryIO) -> FileObjectMeta:
        """把字节写入 staging key 并返回元数据。

        Args:
            operation_id: 当前 operation id。
            data: caller 二进制流。

        Returns:
            staging key 对应元数据。

        Raises:
            无。
        """

        content = data.read()
        key = f".dayu-staging/{operation_id}/x"
        self.staged_objects[key] = content
        return FileObjectMeta(
            uri=f"s3://bucket/{key}",
            etag=_SHA256_HEX,
            last_modified=_TIMESTAMP,
            size=len(content),
            content_type=None,
            sha256=_SHA256_HEX,
        )

    def publish_staged(
        self,
        *,
        staging_key: str,
        final_key: str,
        content_type: str | None,
        metadata: dict[str, str],
    ) -> None:
        """发布 staging 到 final key。

        Args:
            staging_key: staging key。
            final_key: final key。
            content_type: 可选内容类型。
            metadata: 扩展元数据。

        Returns:
            无。

        Raises:
            无。
        """

        del content_type, metadata
        self.staged_objects[final_key] = self.staged_objects[staging_key]

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
        """幂等删除（记录调用并移除本地 staged 内容）。

        Args:
            key: 对象 key。

        Returns:
            无。

        Raises:
            无。
        """

        self.deleted_keys.append(key)
        self.staged_objects.pop(key, None)

    def stat_object(self, key: str) -> FileObjectMeta:
        """HEAD 返回固定元数据。

        Args:
            key: 对象 key。

        Returns:
            固定 sha/size 的元数据。

        Raises:
            无。
        """

        return FileObjectMeta(
            uri=f"s3://bucket/{key}",
            etag=_SHA256_HEX,
            last_modified=_TIMESTAMP,
            size=1,
            content_type=None,
            sha256=_SHA256_HEX,
        )


def _staged_context(tmp_path: Path) -> tuple[FsStorageTestContext, _FakeStagedStore]:
    """构造注入 fake staged store 的测试仓储上下文。

    Args:
        tmp_path: 工作区根目录。

    Returns:
        ``(context, fake)`` 元组；``fake`` 已注入 core，仓储进入 S3 模式。

    Raises:
        OSError: 仓储初始化失败时抛出。
    """

    context = build_fs_storage_test_context(tmp_path)
    fake = _FakeStagedStore()
    context.core._file_store = fake
    return context, fake


def _file_entry(name: str) -> dict[str, str | int | None]:
    """构造 source meta ``files[]`` 条目。

    Args:
        name: 文件名。

    Returns:
        含 name/uri/etag/size/sha256 等字段的文件条目。

    Raises:
        无。
    """

    return {
        "name": name,
        "uri": f"s3://bucket/{_TICKER}/filings/{_DOCUMENT_ID}/{name}",
        "etag": f"etag-{name}",
        "last_modified": _TIMESTAMP,
        "size": 1024,
        "content_type": "application/pdf",
        "sha256": _SHA256_HEX,
    }


def _store_key(name: str) -> str:
    """构造文档对象 key。

    Args:
        name: 文件名。

    Returns:
        ``ticker/filings/document_id/name`` 形式的 key。

    Raises:
        无。
    """

    return f"{_TICKER}/filings/{_DOCUMENT_ID}/{name}"


def _create_two_file_document(context: FsStorageTestContext) -> None:
    """创建含 a.pdf + b.pdf 两个文件条目的源文档。

    Args:
        context: 测试仓储上下文。

    Returns:
        无。

    Raises:
        OSError: 仓储写入失败时抛出。
    """

    context.source_repository.create_source_document(
        FilingCreateRequest(
            ticker=_TICKER,
            document_id=_DOCUMENT_ID,
            internal_document_id=_INTERNAL_DOCUMENT_ID,
            form_type="FY",
            primary_document="a.pdf",
            file_entries=[_file_entry("a.pdf"), _file_entry("b.pdf")],
            meta={"ingest_complete": False},
        ),
        source_kind=SourceKind.FILING,
    )


def _single_file_meta(context: FsStorageTestContext) -> DocumentMeta:
    """读取当前 meta 并收缩为只含 a.pdf 的版本。

    Args:
        context: 测试仓储上下文。

    Returns:
        只含 a.pdf 文件条目的新 meta，并写入 rebuild 版本号。

    Raises:
        无。
    """

    meta: DocumentMeta = dict(context.source_repository.get_source_meta(_TICKER, _DOCUMENT_ID, SourceKind.FILING))
    meta["files"] = [_file_entry("a.pdf")]
    meta["primary_document"] = "a.pdf"
    meta["ingest_complete"] = True
    meta["download_version"] = _REBUILD_VERSION
    return meta


def test_replace_source_meta_owner_batch_records_delete_intent(tmp_path: Path) -> None:
    """owner batch 内 replace_source_meta 只记 delete intent，不直接远端删除。

    SEC/CN rebuild 在 storage-owner ``AUTO_ATOMIC_ALLOWED`` batch 内执行
    ``replace_source_meta``：old/new files diff 出被移除的 b.pdf，journal 追加
    ``action=delete`` delete target（``delete_state=pending``），此时 fake 零
    remote delete；commit 后 post-swap cleanup 幂等删除 b.pdf。
    """

    context, fake = _staged_context(tmp_path)
    _create_two_file_document(context)
    core = context.core
    token = core.begin_batch(_TICKER)
    try:
        context.source_repository.replace_source_meta(
            _TICKER,
            _DOCUMENT_ID,
            SourceKind.FILING,
            _single_file_meta(context),
        )
        journal = core._remote_journal(token)
        assert [item.final_key for item in journal.delete_targets] == [_store_key("b.pdf")]
        assert journal.delete_targets[0].delete_state == "pending"
        assert fake.deleted_keys == []
        core.commit_batch(token)
    except Exception:
        core.rollback_batch(token)
        raise

    assert _store_key("b.pdf") in fake.deleted_keys
    assert _store_key("a.pdf") not in fake.deleted_keys


def test_replace_source_meta_auto_batch_commits_remote_delete(tmp_path: Path) -> None:
    """无 active token 时 replace_source_meta 自建 batch，commit 后 meta 生效。

    ``AUTO_ATOMIC_ALLOWED`` 在无 active token 时自建短内部 batch：b.pdf 的
    delete intent 随 commit 的 post-swap cleanup 幂等删除，a.pdf 不误删；
    替换后 ``meta.files`` 收缩、rebuild 版本字段生效。
    """

    context, fake = _staged_context(tmp_path)
    _create_two_file_document(context)

    context.source_repository.replace_source_meta(
        _TICKER,
        _DOCUMENT_ID,
        SourceKind.FILING,
        _single_file_meta(context),
    )

    assert _store_key("b.pdf") in fake.deleted_keys
    assert _store_key("a.pdf") not in fake.deleted_keys
    assert context.core._active_batches == {}
    meta = context.source_repository.get_source_meta(_TICKER, _DOCUMENT_ID, SourceKind.FILING)
    files = meta.get("files")
    assert isinstance(files, list)
    assert [item.get("name") for item in files] == ["a.pdf"]
    assert meta.get("download_version") == _REBUILD_VERSION
    assert meta.get("primary_document") == "a.pdf"
