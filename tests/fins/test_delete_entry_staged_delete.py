"""S3 模式 delete_entry staged-delete 单元测试（S14-CTRL-13）。

验证 S3 模式 ``delete_entry`` 绝不直接远端删除：记录 ``action=delete``/
``delete_state=pending`` 到 remote journal、只改 staging local；remote
delete 只在 commit 的 post-swap cleanup 阶段；FS/local 模式保留本地删除。
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import BinaryIO

import pytest

from dayu.fins.domain.document_models import FileObjectMeta, ProcessedHandle
from dayu.fins.storage._fs_storage_core import FsStorageCore
from tests.fins.storage_testkit import build_fs_storage_test_context


class _FakeStagedStore:
    """记录远端删除/写入的 staged fake。"""

    def __init__(self) -> None:
        self.deleted_keys: list[str] = []
        self.staged_objects: dict[str, bytes] = {}

    def stage_publish(self, *, operation_id: str, data: BinaryIO) -> FileObjectMeta:
        """写入 staging。"""

        content = data.read()
        key = f".dayu-staging/{operation_id}/x"
        self.staged_objects[key] = content
        return FileObjectMeta(uri=f"s3://bucket/{key}", sha256="0" * 64, size=len(content))

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
        self.staged_objects[final_key] = self.staged_objects[staging_key]

    def object_uri(self, key: str) -> str:
        """构造 URI。"""

        return f"s3://bucket/{key}"

    def get_object(self, key: str) -> io.BytesIO:
        """读取对象。"""

        if key not in self.staged_objects:
            raise FileNotFoundError(f"对象不存在: {key}")
        return io.BytesIO(self.staged_objects[key])

    def key_from_uri(self, uri: str) -> str:
        """从 URI 提取 key。"""

        return uri.split("s3://bucket/", 1)[1]

    def delete_object_idempotent(self, key: str) -> None:
        """幂等删除（记录调用）。"""

        self.deleted_keys.append(key)
        self.staged_objects.pop(key, None)

    def stat_object(self, key: str) -> FileObjectMeta:
        """HEAD 返回元数据。"""

        return FileObjectMeta(uri=f"s3://bucket/{key}", sha256="0" * 64, size=1)


def _staged_context(tmp_path: Path) -> tuple[FsStorageCore, _FakeStagedStore]:
    """构造注入 fake 的 core。"""

    context = build_fs_storage_test_context(tmp_path)
    fake = _FakeStagedStore()
    context.core._file_store = fake
    return context.core, fake


def test_s3_delete_entry_records_intent_without_remote_delete(tmp_path: Path) -> None:
    """S3 模式 delete_entry 记录 delete intent，不直接远端删除。"""

    core, fake = _staged_context(tmp_path)
    handle = ProcessedHandle(ticker="AAPL", document_id="d1")
    token = core.begin_batch("AAPL")
    core.store_file(handle, "a.json", io.BytesIO(b"{}"))
    core.delete_entry(handle, "a.json")
    journal = core._remote_journal(token)
    assert fake.deleted_keys == []
    assert journal.delete_targets[0].final_key == "AAPL/processed/d1/a.json"
    assert journal.delete_targets[0].delete_state == "pending"
    core.rollback_batch(token)


def test_s3_repeated_delete_intent_same_key_is_deduplicated(tmp_path: Path) -> None:
    """同一 operation 内同一 key 的重复 delete intent 幂等收敛为一条。

    ``delete_entry`` 与 inventory diff（如 ``update_filing`` 移除文件）可能对
    同一 key 各自记录 delete intent；journal 必须保持 delete final_key 唯一
    （S14-CR-04 target 唯一性真源），重复调用不产生重复 target。
    """

    core, _ = _staged_context(tmp_path)
    handle = ProcessedHandle(ticker="AAPL", document_id="d1")
    token = core.begin_batch("AAPL")
    core.delete_entry(handle, "a.json")
    core.delete_entry(handle, "a.json")
    journal = core._remote_journal(token)
    matches = [
        target
        for target in journal.delete_targets
        if target.final_key == "AAPL/processed/d1/a.json"
    ]
    assert len(matches) == 1
    assert matches[0].delete_state == "pending"
    core.rollback_batch(token)


def test_s3_commit_publishes_and_deletes_post_swap(tmp_path: Path) -> None:
    """commit 先发布 final，post-swap cleanup 再删 staging + final。"""

    core, fake = _staged_context(tmp_path)
    handle = ProcessedHandle(ticker="AAPL", document_id="d1")
    token = core.begin_batch("AAPL")
    core.store_file(handle, "a.json", io.BytesIO(b"{}"))
    core.delete_entry(handle, "a.json")
    assert fake.deleted_keys == []
    core.commit_batch(token)
    assert "AAPL/processed/d1/a.json" in fake.deleted_keys
    assert any(".dayu-staging" in key for key in fake.deleted_keys)


def test_s3_delete_entry_without_batch_fails_loud(tmp_path: Path) -> None:
    """S3 模式 delete_entry 无 active batch 抛 s3_write_requires_batch。"""

    core, _ = _staged_context(tmp_path)
    handle = ProcessedHandle(ticker="AAPL", document_id="d1")
    with pytest.raises(RuntimeError, match="s3_write_requires_batch"):
        core.delete_entry(handle, "a.json")


def test_fs_mode_delete_entry_removes_local(tmp_path: Path) -> None:
    """FS/local 模式 delete_entry 保留本地删除（无 remote journal）。"""

    from dayu.fins.storage.remote_op_journal import list_journal_ids

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    handle = ProcessedHandle(ticker="AAPL", document_id="d1")
    core.store_file(handle, "a.json", io.BytesIO(b"{}"))
    core.delete_entry(handle, "a.json")
    assert list_journal_ids(core.dayu_root) == []
    assert core._active_batches == {}


def test_s3_no_prefix_sweep(tmp_path: Path) -> None:
    """S3 模式 delete 只删 journal 内 operation-owned key，无 prefix sweep。"""

    core, fake = _staged_context(tmp_path)
    handle = ProcessedHandle(ticker="AAPL", document_id="d1")
    token = core.begin_batch("AAPL")
    core.store_file(handle, "a.json", io.BytesIO(b"{}"))
    core.delete_entry(handle, "a.json")
    core.commit_batch(token)
    assert all("AAPL/processed/d1" in key or ".dayu-staging" in key for key in fake.deleted_keys)


# ---------- S3 模式 maintenance 清理与 rejected 路径（S14-CTRL-13） ----------


def test_s3_store_rejected_file_requires_batch(tmp_path: Path) -> None:
    """S3 模式 store_rejected_filing_file 无 active batch 抛 s3_write_requires_batch。"""

    core, _ = _staged_context(tmp_path)
    with pytest.raises(RuntimeError, match="s3_write_requires_batch"):
        core.store_rejected_filing_file("AAPL", "rej_1", "a.pdf", io.BytesIO(b"r"))


def test_store_rejected_file_empty_filename_raises(tmp_path: Path) -> None:
    """rejected filing filename 为空 => ValueError。"""

    core, _ = _staged_context(tmp_path)
    with pytest.raises(ValueError, match="filename 不能为空"):
        core.store_rejected_filing_file("AAPL", "rej_1", "  ", io.BytesIO(b"r"))


def test_s3_store_and_read_rejected_file(tmp_path: Path) -> None:
    """S3 模式 rejected 文件 store -> commit -> 经 FileStore 读回。"""

    core, fake = _staged_context(tmp_path)
    token = core.begin_batch("AAPL")
    meta = core.store_rejected_filing_file(
        "AAPL",
        "rej_1",
        "a.pdf",
        io.BytesIO(b"%PDF-rejected"),
        content_type="application/pdf",
    )
    assert meta.uri.endswith("AAPL/filings/.rejections/rej_1/a.pdf")
    core.commit_batch(token)
    assert fake.staged_objects.get("AAPL/filings/.rejections/rej_1/a.pdf") == b"%PDF-rejected"
    assert (
        core.read_rejected_filing_file_bytes("AAPL", "rej_1", "a.pdf")
        == b"%PDF-rejected"
    )
    with pytest.raises(FileNotFoundError):
        core.read_rejected_filing_file_bytes("AAPL", "rej_1", "missing.pdf")


def test_s3_clear_filing_documents_records_intents(tmp_path: Path) -> None:
    """S3 模式 clear_filing_documents 逐 key 记 delete intents，commit 后远端删除。"""

    from dayu.fins.domain.document_models import FilingCreateRequest, SourceHandle

    core, fake = _staged_context(tmp_path)
    handle = SourceHandle(ticker="AAPL", document_id="fil_1", source_kind="filing")
    token = core.begin_batch("AAPL")
    meta_a = core.store_file(handle, "a.pdf", io.BytesIO(b"a"))
    core.create_filing(
        FilingCreateRequest(
            ticker="AAPL",
            document_id="fil_1",
            internal_document_id="int_1",
            form_type="10-K",
            primary_document="a.pdf",
            file_entries=[
                {"name": "a.pdf", "uri": meta_a.uri, "size": meta_a.size, "sha256": meta_a.sha256},
            ],
        )
    )
    core.commit_batch(token)

    core.clear_filing_documents("AAPL")
    assert "AAPL/filings/fil_1/a.pdf" in fake.deleted_keys


def test_s3_cleanup_stale_filing_documents_records_intents(tmp_path: Path) -> None:
    """S3 模式 cleanup_stale_filing_documents 记 delete intents，commit 后远端删除。"""

    from dayu.fins.domain.document_models import FilingCreateRequest, SourceHandle

    core, fake = _staged_context(tmp_path)
    handle = SourceHandle(ticker="AAPL", document_id="fil_1", source_kind="filing")
    token = core.begin_batch("AAPL")
    meta_a = core.store_file(handle, "a.pdf", io.BytesIO(b"a"))
    core.create_filing(
        FilingCreateRequest(
            ticker="AAPL",
            document_id="fil_1",
            internal_document_id="int_1",
            form_type="10-K",
            primary_document="a.pdf",
            file_entries=[
                {"name": "a.pdf", "uri": meta_a.uri, "size": meta_a.size, "sha256": meta_a.sha256},
            ],
        )
    )
    core.commit_batch(token)

    cleared = core.cleanup_stale_filing_documents(
        "AAPL",
        active_form_types={"10-K"},
        valid_document_ids=set(),
    )
    assert cleared == 1
    assert "AAPL/filings/fil_1/a.pdf" in fake.deleted_keys


def test_s3_clear_filing_documents_missing_dir_returns(tmp_path: Path) -> None:
    """S3 模式 clear_filing_documents 目标目录缺失 => 无副作用 no-op。"""

    core, fake = _staged_context(tmp_path)
    core.clear_filing_documents("AAPL")
    assert fake.deleted_keys == []


def test_load_rejection_registry_normalizes_mixed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """load_download_rejection_registry 跳过非法 document_id/payload/key。"""

    import json

    from dayu.fins.storage import _fs_maintenance_core as maintenance_module

    core, _ = _staged_context(tmp_path)
    path = core._download_rejections_path_for_read("AAPL")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "doc_ok": {"reason": "x"},
                "bad_payload": "not-a-dict",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        maintenance_module,
        "_read_json_object",
        lambda _path: {
            "doc_ok": {"reason": "x"},
            "bad_payload": "not-a-dict",
            123: "ignored",
        },
    )
    registry = core.load_download_rejection_registry("AAPL")
    assert registry == {"doc_ok": {"reason": "x"}}


def test_fs_read_rejected_file_missing_and_directory(tmp_path: Path) -> None:
    """FS 模式 read_rejected_filing_file_bytes 缺失 => FileNotFoundError。"""

    context = build_fs_storage_test_context(tmp_path)
    core = context.core
    with pytest.raises(FileNotFoundError):
        core.read_rejected_filing_file_bytes("AAPL", "rej_1", "missing.pdf")
