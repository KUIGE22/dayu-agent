"""destructive inventory contraction 单元测试（S14-CTRL-13）。

验证会改变 blob inventory 的 metadata mutation 比较 old/new authoritative
inventory 并在 local metadata swap 前把 removed targets journal 为
``action=delete`` delete intents；processed financials present->None 与
source files shrink 均如此；全程禁 prefix sweep。

processed 的计数/是否含 financials 从请求与 previous meta 计算（S3 模式下
新写字节只存在于 staging、尚未发布到 final key，绝不读未发布对象）。
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import BinaryIO

from dayu.fins.domain.document_models import (
    FileObjectMeta,
    ProcessedCreateRequest,
    ProcessedUpdateRequest,
    SourceHandle,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage._fs_storage_core import FsStorageCore
from tests.fins.storage_testkit import build_fs_storage_test_context

_STAGING_PREFIX = ".dayu-staging/"


class _FakeStagedStore:
    """记录远端删除的 staged fake（staging key 按 sha 唯一，stat 真实）。"""

    def __init__(self) -> None:
        self.deleted_keys: list[str] = []
        self.objects: dict[str, bytes] = {}

    def stage_publish(self, *, operation_id: str, data: BinaryIO) -> FileObjectMeta:
        """写入 staging（key 为 ``.dayu-staging/{operation_id}/{sha256}``）。"""

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
        """发布 final（staging -> final 拷贝）。"""

        del content_type, metadata
        self.objects[final_key] = self.objects[staging_key]

    def object_uri(self, key: str) -> str:
        """构造 URI。"""

        return f"s3://bucket/{key}"

    def key_from_uri(self, uri: str) -> str:
        """从 URI 提取 key。"""

        return uri.split("s3://bucket/", 1)[1]

    def delete_object_idempotent(self, key: str) -> None:
        """幂等删除。"""

        self.deleted_keys.append(key)
        self.objects.pop(key, None)

    def get_object(self, key: str) -> io.BytesIO:
        """读取对象。"""

        if key not in self.objects:
            raise FileNotFoundError(f"对象不存在: {key}")
        return io.BytesIO(self.objects[key])

    def list_objects(self, prefix: str) -> list[FileObjectMeta]:
        """列出对象。"""

        return [
            FileObjectMeta(uri=self.object_uri(key))
            for key in sorted(self.objects)
            if key.startswith(prefix)
        ]

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


def _staged_core(tmp_path: Path) -> tuple[FsStorageCore, _FakeStagedStore]:
    """构造注入 fake 的 core。"""

    context = build_fs_storage_test_context(tmp_path)
    fake = _FakeStagedStore()
    context.core._file_store = fake
    return context.core, fake


def _final_deleted_keys(fake: _FakeStagedStore) -> list[str]:
    """过滤出 final key 的远端删除（排除 staging 清理）。"""

    return [key for key in fake.deleted_keys if not key.startswith(_STAGING_PREFIX)]


def _create_processed(core: FsStorageCore, ticker: str, doc_id: str) -> None:
    """创建含 financials 的 processed 文档。"""

    core.create_processed(
        ProcessedCreateRequest(
            ticker=ticker,
            document_id=doc_id,
            internal_document_id=f"int_{doc_id}",
            source_kind=SourceKind.FILING,
            form_type="10-K",
            sections=[{"title": "s"}],
            financials={"revenue": 1},
            meta={"fiscal_year": 2024},
        )
    )


def test_processed_financials_present_to_none_records_delete_intent(tmp_path: Path) -> None:
    """financials present->None：journal 记 delete target，commit 后远端删除。"""

    core, fake = _staged_core(tmp_path)
    _create_processed(core, "AAPL", "p1")
    token = core.begin_batch("AAPL")
    core.update_processed(
        ProcessedUpdateRequest(
            ticker="AAPL",
            document_id="p1",
            internal_document_id="int_p1",
            source_kind=SourceKind.FILING,
            form_type="10-K",
            sections=[{"title": "s"}],
            financials=None,
            meta={},
        )
    )
    journal = core._remote_journal(token)
    assert any(
        t.final_key == "AAPL/processed/p1/financials.json"
        and t.delete_state == "pending"
        for t in journal.delete_targets
    )
    assert _final_deleted_keys(fake) == []
    core.commit_batch(token)
    assert "AAPL/processed/p1/financials.json" in _final_deleted_keys(fake)


def test_processed_files_inventory_persisted(tmp_path: Path) -> None:
    """processed meta 显式持久化 authoritative files inventory。"""

    core, _ = _staged_core(tmp_path)
    _create_processed(core, "AAPL", "p2")
    meta = core.get_processed_meta("AAPL", "p2")
    files = meta.get("files")
    assert isinstance(files, list)
    assert "financials.json" in files
    assert "sections.json" in files


def test_processed_remove_financials_updates_files_inventory(tmp_path: Path) -> None:
    """移除 financials 后 files inventory 不含 financials.json。"""

    core, _ = _staged_core(tmp_path)
    _create_processed(core, "AAPL", "p3")
    core.update_processed(
        ProcessedUpdateRequest(
            ticker="AAPL",
            document_id="p3",
            internal_document_id="int_p3",
            source_kind=SourceKind.FILING,
            form_type="10-K",
            sections=[{"title": "s"}],
            financials=None,
            meta={},
        )
    )
    meta = core.get_processed_meta("AAPL", "p3")
    files = meta.get("files")
    assert isinstance(files, list)
    assert "financials.json" not in files


def test_processed_delete_records_delete_intent(tmp_path: Path) -> None:
    """processed delete：从 authoritative files 逐 key 记 delete intent。"""

    from dayu.fins.domain.document_models import ProcessedDeleteRequest

    core, fake = _staged_core(tmp_path)
    _create_processed(core, "AAPL", "p4")
    token = core.begin_batch("AAPL")
    core.delete_processed(
        ProcessedDeleteRequest(ticker="AAPL", document_id="p4")
    )
    journal = core._remote_journal(token)
    assert any(
        t.final_key.startswith("AAPL/processed/p4/") for t in journal.delete_targets
    )
    assert _final_deleted_keys(fake) == []
    core.commit_batch(token)
    assert any(
        key.startswith("AAPL/processed/p4/") for key in _final_deleted_keys(fake)
    )


def test_source_file_list_shrink_records_delete_intent(tmp_path: Path) -> None:
    """source files shrink：removed 文件记 delete intent，未移除不误删。"""

    from dayu.fins.domain.document_models import FilingCreateRequest, FilingUpdateRequest

    core, fake = _staged_core(tmp_path)
    handle = SourceHandle(ticker="AAPL", document_id="fil_1", source_kind="filing")
    token = core.begin_batch("AAPL")
    meta_a = core.store_file(handle, "a.pdf", io.BytesIO(b"a"))
    meta_b = core.store_file(handle, "b.pdf", io.BytesIO(b"b"))
    core.create_filing(
        FilingCreateRequest(
            ticker="AAPL",
            document_id="fil_1",
            internal_document_id="int_fil_1",
            form_type="10-K",
            primary_document="a.pdf",
            file_entries=[
                {"name": "a.pdf", "uri": meta_a.uri, "size": meta_a.size, "sha256": meta_a.sha256},
                {"name": "b.pdf", "uri": meta_b.uri, "size": meta_b.size, "sha256": meta_b.sha256},
            ],
        )
    )
    core.commit_batch(token)

    token = core.begin_batch("AAPL")
    core.update_filing(
        FilingUpdateRequest(
            ticker="AAPL",
            document_id="fil_1",
            internal_document_id="int_fil_1",
            form_type="10-K",
            primary_document="a.pdf",
            file_entries=[
                {"name": "a.pdf", "uri": meta_a.uri, "size": meta_a.size, "sha256": meta_a.sha256},
            ],
        )
    )
    journal = core._remote_journal(token)
    assert any(
        t.final_key == "AAPL/filings/fil_1/b.pdf" and t.delete_state == "pending"
        for t in journal.delete_targets
    )
    assert not any(
        t.final_key == "AAPL/filings/fil_1/a.pdf" for t in journal.delete_targets
    )
    assert _final_deleted_keys(fake) == []
    core.commit_batch(token)
    assert "AAPL/filings/fil_1/b.pdf" in _final_deleted_keys(fake)
    assert "AAPL/filings/fil_1/a.pdf" not in _final_deleted_keys(fake)


def test_processed_create_records_counts_and_has_xbrl(tmp_path: Path) -> None:
    """创建时计数与 has_xbrl 从请求计算并持久化。"""

    core, _ = _staged_core(tmp_path)
    core.create_processed(
        ProcessedCreateRequest(
            ticker="AAPL",
            document_id="p5",
            internal_document_id="int_p5",
            source_kind=SourceKind.FILING,
            form_type="10-K",
            sections=[{"title": "a"}, {"title": "b"}],
            tables=[{"t": "1"}],
            financials={"revenue": 1},
        )
    )
    meta = core.get_processed_meta("AAPL", "p5")
    assert meta["section_count"] == 2
    assert meta["table_count"] == 1
    assert meta["has_xbrl"] is True
    files = meta.get("files")
    assert isinstance(files, list)
    assert files == ["sections.json", "tables.json", "financials.json"]


def test_processed_update_sections_replaces_count(tmp_path: Path) -> None:
    """更新 sections 后计数取新值，financials 保留时 has_xbrl 不变。"""

    core, _ = _staged_core(tmp_path)
    _create_processed(core, "AAPL", "p6")
    core.update_processed(
        ProcessedUpdateRequest(
            ticker="AAPL",
            document_id="p6",
            internal_document_id="int_p6",
            source_kind=SourceKind.FILING,
            form_type="10-K",
            sections=[{"title": "a"}, {"title": "b"}, {"title": "c"}],
            financials={"revenue": 2},
            meta={},
        )
    )
    meta = core.get_processed_meta("AAPL", "p6")
    assert meta["section_count"] == 3
    assert meta["has_xbrl"] is True
    files = meta.get("files")
    assert isinstance(files, list)
    assert "financials.json" in files


def test_processed_update_sections_none_preserves_count(tmp_path: Path) -> None:
    """更新时不提供 sections 保留 previous 计数。"""

    core, _ = _staged_core(tmp_path)
    _create_processed(core, "AAPL", "p7")
    core.update_processed(
        ProcessedUpdateRequest(
            ticker="AAPL",
            document_id="p7",
            internal_document_id="int_p7",
            source_kind=SourceKind.FILING,
            form_type="10-K",
            sections=None,
            financials={"revenue": 3},
            meta={},
        )
    )
    meta = core.get_processed_meta("AAPL", "p7")
    assert meta["section_count"] == 1
    assert meta["has_xbrl"] is True


def test_processed_financials_none_has_xbrl_false(tmp_path: Path) -> None:
    """移除 financials 后 has_xbrl 置 False。"""

    core, _ = _staged_core(tmp_path)
    _create_processed(core, "AAPL", "p8")
    core.update_processed(
        ProcessedUpdateRequest(
            ticker="AAPL",
            document_id="p8",
            internal_document_id="int_p8",
            source_kind=SourceKind.FILING,
            form_type="10-K",
            sections=[{"title": "s"}],
            financials=None,
            meta={},
        )
    )
    meta = core.get_processed_meta("AAPL", "p8")
    assert meta["has_xbrl"] is False


def test_processed_commit_publishes_new_sections_bytes(tmp_path: Path) -> None:
    """commit 后新 sections bytes 可从 final key 读取（S3 发布）。"""

    core, fake = _staged_core(tmp_path)
    _create_processed(core, "AAPL", "p9")
    token = core.begin_batch("AAPL")
    core.update_processed(
        ProcessedUpdateRequest(
            ticker="AAPL",
            document_id="p9",
            internal_document_id="int_p9",
            source_kind=SourceKind.FILING,
            form_type="10-K",
            sections=[{"title": "x"}, {"title": "y"}],
            financials=None,
            meta={},
        )
    )
    core.commit_batch(token)
    stream = fake.get_object("AAPL/processed/p9/sections.json")
    try:
        payload = stream.read().decode("utf-8")
    finally:
        stream.close()
    assert '"x"' in payload and '"y"' in payload


def test_processed_update_rollback_preserves_old_meta_and_bytes(tmp_path: Path) -> None:
    """rollback 保留旧 meta/远端 bytes，零 final-key 删除。"""

    core, fake = _staged_core(tmp_path)
    _create_processed(core, "AAPL", "p10")
    token = core.begin_batch("AAPL")
    core.update_processed(
        ProcessedUpdateRequest(
            ticker="AAPL",
            document_id="p10",
            internal_document_id="int_p10",
            source_kind=SourceKind.FILING,
            form_type="10-K",
            sections=[{"title": "a"}, {"title": "b"}],
            financials=None,
            meta={},
        )
    )
    core.rollback_batch(token)
    meta = core.get_processed_meta("AAPL", "p10")
    assert meta["section_count"] == 1
    assert meta["has_xbrl"] is True
    files = meta.get("files")
    assert isinstance(files, list)
    assert "financials.json" in files
    assert _final_deleted_keys(fake) == []
    assert "AAPL/processed/p10/financials.json" in fake.objects
    assert "AAPL/processed/p10/sections.json" in fake.objects
