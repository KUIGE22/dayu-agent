"""upload overwrite 的 per-document batch 单元测试（S14-CTRL-12 producer #4）。

验证 ``DoclingUploadService.execute_upload`` 在 per-document 显式 batch 内
完成 begin -> overwrite 时 reset 复用 token -> store_file + source meta ->
commit；失败 rollback 保留旧 source/bytes 可读；无外层 wrapper、无嵌套
batch、零第二 batch/auto-begin。
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pytest

from dayu.fins.domain.document_models import BatchToken, FileObjectMeta, SourceHandle
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.docling_upload_service import DoclingUploadService
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet
from dayu.fins.storage.fs_batching_repository import FsBatchingRepository
from tests.fins.storage_testkit import build_fs_storage_test_context


class _FakeStagedStore:
    """实现 StagedFileStoreProtocol 的记录型 fake（staging key 按 sha 唯一，
    stat 真实、缺失抛 FileNotFoundError，遵循 FileStore 契约）。"""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.published: list[str] = []
        self.fail_stage: bool = False
        self.fail_publish: bool = False

    def stage_publish(self, *, operation_id: str, data: BytesIO) -> FileObjectMeta:
        """写入 staging（key 为 ``.dayu-staging/{operation_id}/{sha256}``）。"""

        if self.fail_stage:
            raise OSError("stage failed")
        content = data.read()
        digest = hashlib.sha256(content).hexdigest()
        key = f".dayu-staging/{operation_id}/{digest}"
        self.objects[key] = content
        return FileObjectMeta(
            uri=self.object_uri(key),
            sha256=digest,
            size=len(content),
        )

    def publish_staged(
        self,
        *,
        staging_key: str,
        final_key: str,
        content_type: str | None,
        metadata: dict[str, str],
    ) -> None:
        """发布 final。"""

        del content_type, metadata
        if self.fail_publish:
            raise OSError("publish failed")
        self.objects[final_key] = self.objects[staging_key]
        self.published.append(final_key)

    def object_uri(self, key: str) -> str:
        """构造 URI。"""

        return f"s3://bucket/{key}"

    def key_from_uri(self, uri: str) -> str:
        """从 URI 提取 key。"""

        return uri.split("s3://bucket/", 1)[1]

    def delete_object_idempotent(self, key: str) -> None:
        """幂等删除。"""

        self.objects.pop(key, None)

    def stat_object(self, key: str) -> FileObjectMeta:
        """HEAD 返回真实 digest/size；缺失抛 FileNotFoundError。"""

        if key not in self.objects:
            raise FileNotFoundError(f"对象不存在: {key}")
        content = self.objects[key]
        return FileObjectMeta(
            uri=self.object_uri(key),
            sha256=hashlib.sha256(content).hexdigest(),
            size=len(content),
        )

    def list_objects(self, prefix: str) -> list[FileObjectMeta]:
        """列出对象。"""

        return [
            FileObjectMeta(uri=self.object_uri(key))
            for key in sorted(self.objects)
            if key.startswith(prefix)
        ]

    def get_object(self, key: str) -> BytesIO:
        """读取对象。"""

        if key not in self.objects:
            raise FileNotFoundError(f"对象不存在: {key}")
        return BytesIO(self.objects[key])


class _RecordingBatching:
    """记录 begin/commit/rollback 调用的 batching fake。"""

    def __init__(self, real: FsBatchingRepository) -> None:
        self._real = real
        self.begin_calls: list[str] = []
        self.commit_calls: list[str] = []
        self.rollback_calls: list[str] = []

    def begin_batch(self, ticker: str) -> BatchToken:
        """记录并转发 begin。"""

        self.begin_calls.append(ticker)
        return self._real.begin_batch(ticker)

    def commit_batch(self, token: BatchToken) -> None:
        """记录并转发 commit。"""

        self.commit_calls.append(token.ticker)
        self._real.commit_batch(token)

    def rollback_batch(self, token: BatchToken) -> None:
        """记录并转发 rollback。"""

        self.rollback_calls.append(token.ticker)
        self._real.rollback_batch(token)

    def recover_orphan_batches(self, *, dry_run: bool = False) -> tuple[str, ...]:
        """转发 recovery。"""

        return self._real.recover_orphan_batches(dry_run=dry_run)

    def clear(self) -> None:
        """清空记录，便于分段断言。"""

        self.begin_calls.clear()
        self.commit_calls.clear()
        self.rollback_calls.clear()


def _convert_docling_stub(raw_data: bytes, stream_name: str) -> dict[str, str | int]:
    """返回固定 Docling 转换结果，避免在 fake PDF bytes 上运行真实 Docling。"""

    return {"name": stream_name, "source": "docling", "size": len(raw_data)}


def _upload_service(tmp_path: Path) -> tuple[DoclingUploadService, _FakeStagedStore, _RecordingBatching]:
    """构造同 core 的 upload service + fake store + recording batching。"""

    context = build_fs_storage_test_context(tmp_path)
    fake = _FakeStagedStore()
    context.core._file_store = fake
    real_batching = FsBatchingRepository(
        tmp_path,
        repository_set=_FsRepositorySet(core=context.core),
    )
    recording = _RecordingBatching(real_batching)
    service = DoclingUploadService(
        source_repository=context.source_repository,
        blob_repository=context.blob_repository,
        batching_repository=recording,
        convert_with_docling=_convert_docling_stub,
    )
    return service, fake, recording


def _write_temp_file(tmp_path: Path, name: str, content: bytes) -> Path:
    """写入临时上传文件。"""

    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_execute_upload_create_single_batch(tmp_path: Path) -> None:
    """create 成功：恰好一个显式 batch，commit 被调用。"""

    service, fake, recording = _upload_service(tmp_path)
    upload_file = _write_temp_file(tmp_path, "a.pdf", b"%PDF-1.7")
    result = service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="fil_1",
        internal_document_id="int_1",
        form_type="10-K",
        files=[upload_file],
        overwrite=False,
        meta={},
    )
    assert result.status == "uploaded"
    assert recording.begin_calls == ["AAPL"]
    assert recording.commit_calls == ["AAPL"]
    assert recording.rollback_calls == []
    assert fake.published


def test_execute_upload_overwrite_reset_inside_batch(tmp_path: Path) -> None:
    """overwrite：reset_source_document 在显式 batch 内复用 token。"""

    service, fake, recording = _upload_service(tmp_path)
    upload_file = _write_temp_file(tmp_path, "a.pdf", b"%PDF-1.7")
    service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="fil_1",
        internal_document_id="int_1",
        form_type="10-K",
        files=[upload_file],
        overwrite=False,
        meta={},
    )
    result = service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="update",
        document_id="fil_1",
        internal_document_id="int_1",
        form_type="10-K",
        files=[upload_file],
        overwrite=True,
        meta={},
    )
    assert result.status == "uploaded"
    # 每个 upload 恰好一个 batch：create 1 次 + overwrite 1 次。
    assert recording.begin_calls == ["AAPL", "AAPL"]
    assert recording.commit_calls == ["AAPL", "AAPL"]
    assert recording.rollback_calls == []


def test_execute_upload_failure_rolls_back_keeps_old(tmp_path: Path) -> None:
    """commit 前 store 失败：rollback 同一 token，旧 source/bytes 可读。"""

    service, fake, recording = _upload_service(tmp_path)
    upload_file = _write_temp_file(tmp_path, "a.pdf", b"%PDF-1.7")
    service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="fil_1",
        internal_document_id="int_1",
        form_type="10-K",
        files=[upload_file],
        overwrite=False,
        meta={},
    )
    old_meta = service._source_repository.get_source_meta(
        "AAPL", "fil_1", SourceKind.FILING
    )
    old_files = old_meta.get("files")
    # commit-start 前的 staging 失败 => 显式 rollback 同一 token。
    fake.fail_stage = True
    with pytest.raises(OSError, match="stage failed"):
        service.execute_upload(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            action="update",
            document_id="fil_1",
            internal_document_id="int_1",
            form_type="10-K",
            files=[upload_file],
            overwrite=True,
            meta={},
        )
    assert recording.rollback_calls == ["AAPL"]
    # rollback 后旧 meta 与旧远端 bytes 均保留。
    after_meta = service._source_repository.get_source_meta(
        "AAPL", "fil_1", SourceKind.FILING
    )
    assert after_meta.get("files") == old_files
    assert "AAPL/filings/fil_1/a.pdf" in fake.objects
    assert "AAPL/filings/fil_1/a_docling.json" in fake.objects


def test_execute_upload_commit_failure_propagates_recovery(tmp_path: Path) -> None:
    """commit-start 后 publish 失败：错误传播、不 rollback、journal/recovery 收敛。"""

    service, fake, recording = _upload_service(tmp_path)
    upload_file = _write_temp_file(tmp_path, "a.pdf", b"%PDF-1.7")
    service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="fil_1",
        internal_document_id="int_1",
        form_type="10-K",
        files=[upload_file],
        overwrite=False,
        meta={},
    )
    old_meta = service._source_repository.get_source_meta(
        "AAPL", "fil_1", SourceKind.FILING
    )
    old_files = old_meta.get("files")
    # commit-start 后 publish 失败：head final 与目标 digest 不符且重试失败
    # => RuntimeError 传播，绝不调用 rollback（commit 已开始）。
    changed_file = _write_temp_file(tmp_path, "a.pdf", b"%PDF-1.7-new")
    fake.fail_publish = True
    with pytest.raises(RuntimeError):
        service.execute_upload(
            ticker="AAPL",
            source_kind=SourceKind.FILING,
            action="update",
            document_id="fil_1",
            internal_document_id="int_1",
            form_type="10-K",
            files=[changed_file],
            overwrite=True,
            meta={},
        )
    assert recording.rollback_calls == []
    after_meta = service._source_repository.get_source_meta(
        "AAPL", "fil_1", SourceKind.FILING
    )
    assert after_meta.get("files") == old_files
    # 模拟重启：fault 消失后重放 remote journal —— staging keys 仍存在则完成
    # 发布，但 FS batch staging 目录已被 in-process commit 清理 => fail closed
    # （保留 journal 与远端 objects，不伪造恢复、不删 finals）。
    fake.fail_publish = False
    restarted = build_fs_storage_test_context(tmp_path)
    restarted.core._file_store = fake
    restarted.core._batch_recovery_completed = False
    with pytest.raises(RuntimeError, match="fail closed"):
        restarted.core.ensure_batch_recovery()
    assert "AAPL/filings/fil_1/a.pdf" in fake.objects
    assert "AAPL/filings/fil_1/a_docling.json" in fake.objects
    journal_dir = tmp_path / ".dayu" / "remote_ops"
    assert any(journal_dir.glob("*.json"))


def test_execute_upload_overwrite_replacement_survives_old_only_deleted(tmp_path: Path) -> None:
    """overwrite：同 key 新发布取代旧 delete intent，旧-only 附件被删除。"""

    service, fake, _ = _upload_service(tmp_path)
    a_file = _write_temp_file(tmp_path, "a.pdf", b"%PDF-1.7")
    b_file = _write_temp_file(tmp_path, "b.pdf", b"%PDF-1.8")
    service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="fil_1",
        internal_document_id="int_1",
        form_type="10-K",
        files=[a_file, b_file],
        overwrite=False,
        meta={},
    )
    assert "AAPL/filings/fil_1/a.pdf" in fake.objects
    assert "AAPL/filings/fil_1/b.pdf" in fake.objects
    # overwrite 只重新上传 a.pdf（内容变更）：a.pdf 的 delete intent 被同 key
    # 新发布取代，b.pdf/b_docling.json 为 old-only 附件被 post-commit 删除。
    a_new = _write_temp_file(tmp_path, "a.pdf", b"%PDF-1.7-new")
    result = service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="update",
        document_id="fil_1",
        internal_document_id="int_1",
        form_type="10-K",
        files=[a_new],
        overwrite=True,
        meta={},
    )
    assert result.status == "uploaded"
    assert "AAPL/filings/fil_1/a.pdf" in fake.objects
    stream = fake.get_object("AAPL/filings/fil_1/a.pdf")
    try:
        assert stream.read() == b"%PDF-1.7-new"
    finally:
        stream.close()
    assert "AAPL/filings/fil_1/a_docling.json" in fake.objects
    assert "AAPL/filings/fil_1/b.pdf" not in fake.objects
    assert "AAPL/filings/fil_1/b_docling.json" not in fake.objects


def test_store_file_duplicate_publish_key_rejected(tmp_path: Path) -> None:
    """同一 operation 内重复 publish 同一 final key 被拒绝。"""

    context = build_fs_storage_test_context(tmp_path)
    fake = _FakeStagedStore()
    context.core._file_store = fake
    handle = SourceHandle(ticker="AAPL", document_id="fil_1", source_kind="filing")
    token = context.core.begin_batch("AAPL")
    context.core.store_file(handle, "a.pdf", BytesIO(b"x"))
    with pytest.raises(RuntimeError, match="publish final_key 重复"):
        context.core.store_file(handle, "a.pdf", BytesIO(b"y"))
    context.core.rollback_batch(token)


def test_execute_upload_delete_no_batch(tmp_path: Path) -> None:
    """delete 动作不进入写 batch。"""

    service, _, recording = _upload_service(tmp_path)
    upload_file = _write_temp_file(tmp_path, "a.pdf", b"%PDF-1.7")
    service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="create",
        document_id="fil_1",
        internal_document_id="int_1",
        form_type="10-K",
        files=[upload_file],
        overwrite=False,
        meta={},
    )
    recording.clear()
    result = service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        action="delete",
        document_id="fil_1",
        internal_document_id="int_1",
        form_type="10-K",
        files=[],
        overwrite=False,
        meta={},
    )
    assert result.status == "deleted"
    assert recording.begin_calls == []
