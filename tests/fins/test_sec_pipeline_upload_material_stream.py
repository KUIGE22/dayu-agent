"""SecPipeline upload_material_stream 测试。"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Callable, Optional

import pytest

from dayu.fins.domain.document_models import (
    BatchToken,
    FileObjectMeta,
    ProcessedHandle,
    SourceHandle,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.sec_pipeline import SecPipeline
from dayu.fins.pipelines.upload_material_events import UploadMaterialEvent, UploadMaterialEventType
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet
from dayu.fins.storage.fs_batching_repository import FsBatchingRepository
from tests.fins.storage_testkit import FsStorageTestContext, build_fs_storage_test_context


@pytest.mark.asyncio
async def test_upload_material_stream_uploads_docling_files(tmp_path: Path) -> None:
    """验证 `upload_material_stream` 可完成上传并生成 docling 主文件。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
    )
    pipeline._upload_service._convert_with_docling = lambda raw_data, stream_name: {  # type: ignore[attr-defined]
        "name": stream_name,
        "format": "docling",
    }
    material_file = tmp_path / "material.pdf"
    material_file.write_text("demo material", encoding="utf-8")

    events = [
        event
        async for event in pipeline.upload_material_stream(
            ticker="AAPL",
            action="create",
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            files=[material_file],
            filing_date="2025-05-01",
            report_date="2025-03-31",
            company_id="320193",
            company_name="Apple Inc.",
            ticker_aliases=["AAPL", "APC"],
            overwrite=False,
        )
    ]

    assert len(events) == 5
    assert events[0].event_type == UploadMaterialEventType.UPLOAD_STARTED
    assert events[1].event_type == UploadMaterialEventType.CONVERSION_STARTED
    assert events[1].payload["name"] == "material.pdf"
    assert events[1].payload["message"] == "正在 convert"
    assert events[2].event_type == UploadMaterialEventType.FILE_UPLOADED
    assert events[2].payload["name"] == "material.pdf"
    assert events[2].payload["source"] == "original"
    assert events[3].event_type == UploadMaterialEventType.FILE_UPLOADED
    assert events[3].payload["name"] == "material_docling.json"
    assert events[3].payload["source"] == "docling"
    assert events[4].event_type == UploadMaterialEventType.UPLOAD_COMPLETED
    result = events[4].payload["result"]
    assert result["action"] == "upload_material"
    assert result["ticker"] == "AAPL"
    assert result["status"] == "ok"
    assert str(result["document_id"]).startswith("mat_")
    company_meta = pipeline._company_repository.get_company_meta("AAPL")  # type: ignore[attr-defined]
    assert company_meta.company_id == "AAPL_US"
    assert company_meta.company_name == "Apple Inc."
    assert company_meta.ticker_aliases == ["AAPL", "APC"]
    meta = pipeline._source_repository.get_source_meta("AAPL", result["document_id"], SourceKind.MATERIAL)  # type: ignore[attr-defined]
    assert str(meta["primary_document"]).endswith("_docling.json")


@pytest.mark.asyncio
async def test_upload_material_stream_auto_action_and_overwrite_reset(tmp_path: Path) -> None:
    """验证 SecPipeline material 上传会自动解析动作并在 overwrite 时重置单文档。"""

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
    )
    pipeline._upload_service._convert_with_docling = lambda raw_data, stream_name: {  # type: ignore[attr-defined]
        "name": stream_name,
        "format": "docling",
    }
    old_file = tmp_path / "deck_old.pdf"
    new_file = tmp_path / "deck_new.pdf"
    old_file.write_text("old material", encoding="utf-8")
    new_file.write_text("new material", encoding="utf-8")

    create_events = [
        event
        async for event in pipeline.upload_material_stream(
            ticker="AAPL",
            action=None,
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            files=[old_file],
            company_id="320193",
            company_name="Apple Inc.",
            overwrite=False,
        )
    ]
    create_result = create_events[-1].payload["result"]
    assert create_result["material_action"] == "create"

    overwrite_events = [
        event
        async for event in pipeline.upload_material_stream(
            ticker="AAPL",
            action=None,
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            files=[new_file],
            company_id="320193",
            company_name="Apple Inc.",
            overwrite=True,
        )
    ]
    overwrite_result = overwrite_events[-1].payload["result"]
    assert overwrite_result["status"] == "ok"
    assert overwrite_result["material_action"] == "update"
    assert overwrite_result["document_id"] == create_result["document_id"]

    handle = pipeline._source_repository.get_source_handle("AAPL", overwrite_result["document_id"], SourceKind.MATERIAL)  # type: ignore[attr-defined]
    file_names = sorted(meta.uri.split("/")[-1] for meta in pipeline._blob_repository.list_files(handle))  # type: ignore[attr-defined]
    assert file_names == ["deck_new.pdf", "deck_new_docling.json"]

# ---------- overwrite 真实 workflow batch 边界（S14-CTRL-12 upload-overwrite） ----------


class _RecordingBatching:
    """记录 service explicit batch 的 begin/commit/rollback（转发同 core 真实现）。"""

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


class _FailStoreToggle:
    """按开关在 store_file 注入失败的包装（同 core 观察，不进入生产路径）。"""

    def __init__(self, original: Callable[..., FileObjectMeta]) -> None:
        self._original = original
        self.fail = False

    def __call__(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
        data: BinaryIO,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """按开关转发或抛错。"""

        if self.fail:
            raise OSError("injected store failure")
        return self._original(
            handle,
            filename,
            data,
            content_type=content_type,
            metadata=metadata,
        )


def _build_observed_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[SecPipeline, FsStorageTestContext, _RecordingBatching]:
    """构造同-core recording batching 的 SecPipeline（窄仓储共享同一 core）。"""

    context = build_fs_storage_test_context(tmp_path)
    recording = _RecordingBatching(
        FsBatchingRepository(
            tmp_path,
            repository_set=_FsRepositorySet(core=context.core),
        )
    )
    monkeypatch.setattr(
        "dayu.fins.pipelines.docling_upload_service._convert_bytes_with_docling",
        lambda raw_data, stream_name: {"name": stream_name, "format": "docling"},
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        company_repository=context.company_repository,
        source_repository=context.source_repository,
        processed_repository=context.processed_repository,
        blob_repository=context.blob_repository,
        filing_maintenance_repository=context.filing_maintenance_repository,
        batching_repository=recording,
    )
    return pipeline, context, recording


async def _upload_material(
    pipeline: SecPipeline,
    *,
    file_path: Path,
    overwrite: bool,
    action: str | None = None,
) -> list[UploadMaterialEvent]:
    """驱动一次 material 上传并收集事件。"""

    return [
        event
        async for event in pipeline.upload_material_stream(
            ticker="AAPL",
            action=action,
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            files=[file_path],
            company_id="320193",
            company_name="Apple Inc.",
            overwrite=overwrite,
        )
    ]


@pytest.mark.asyncio
async def test_upload_material_stream_overwrite_single_service_batch_with_reset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """overwrite 真实 workflow：service explicit batch 恰好一次 begin/commit，reset 在 active token 内。"""

    pipeline, context, recording = _build_observed_pipeline(tmp_path, monkeypatch)
    core = context.core
    reset_observations: list[str] = []
    original_reset = core.reset_source_document

    def observed_reset(ticker: str, document_id: str, source_kind: SourceKind) -> None:
        assert ticker in core._active_batches, f"reset 时同-core token 必须已 active: {ticker}"
        reset_observations.append(ticker)
        original_reset(ticker, document_id, source_kind)

    core.reset_source_document = observed_reset
    old_file = tmp_path / "deck_old.pdf"
    new_file = tmp_path / "deck_new.pdf"
    old_file.write_text("old material", encoding="utf-8")
    new_file.write_text("new material", encoding="utf-8")

    create_events = await _upload_material(pipeline, file_path=old_file, overwrite=False)
    create_result = create_events[-1].payload["result"]
    assert create_result["status"] == "ok"
    assert create_result["material_action"] == "create"
    assert [event.event_type.value for event in create_events] == [
        "upload_started",
        "conversion_started",
        "file_uploaded",
        "file_uploaded",
        "upload_completed",
    ]
    assert recording.begin_calls == ["AAPL"]
    assert recording.commit_calls == ["AAPL"]
    assert recording.rollback_calls == []
    assert reset_observations == []

    overwrite_events = await _upload_material(pipeline, file_path=new_file, overwrite=True)
    overwrite_result = overwrite_events[-1].payload["result"]
    assert overwrite_result["status"] == "ok"
    assert overwrite_result["material_action"] == "update"
    assert overwrite_result["document_id"] == create_result["document_id"]
    assert recording.begin_calls == ["AAPL", "AAPL"]
    assert recording.commit_calls == ["AAPL", "AAPL"]
    assert recording.rollback_calls == []
    assert reset_observations == ["AAPL"]


@pytest.mark.asyncio
async def test_upload_material_stream_overwrite_failure_rolls_back_keeps_old(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """overwrite reset 后/commit 前失败：一次 rollback、零 commit、旧 source/meta/blob bytes 可读。"""

    pipeline, context, recording = _build_observed_pipeline(tmp_path, monkeypatch)
    core = context.core
    reset_observations: list[str] = []
    original_reset = core.reset_source_document

    def observed_reset(ticker: str, document_id: str, source_kind: SourceKind) -> None:
        assert ticker in core._active_batches, f"reset 时同-core token 必须已 active: {ticker}"
        reset_observations.append(ticker)
        original_reset(ticker, document_id, source_kind)

    core.reset_source_document = observed_reset
    store_toggle = _FailStoreToggle(core.store_file)
    core.store_file = store_toggle
    old_file = tmp_path / "deck_old.pdf"
    new_file = tmp_path / "deck_new.pdf"
    old_file.write_text("old material", encoding="utf-8")
    new_file.write_text("new material", encoding="utf-8")

    create_events = await _upload_material(pipeline, file_path=old_file, overwrite=False)
    create_result = create_events[-1].payload["result"]
    assert create_result["status"] == "ok"
    document_id = create_result["document_id"]
    assert recording.begin_calls == ["AAPL"]
    assert recording.commit_calls == ["AAPL"]

    store_toggle.fail = True
    failed_events = await _upload_material(pipeline, file_path=new_file, overwrite=True)
    assert failed_events[-1].event_type == UploadMaterialEventType.UPLOAD_FAILED
    failed_result = failed_events[-1].payload["result"]
    assert failed_result["status"] == "failed"
    assert failed_result["material_action"] == "update"
    assert failed_result["ticker"] == "AAPL"
    assert recording.begin_calls == ["AAPL", "AAPL"]
    assert recording.rollback_calls == ["AAPL"]
    assert recording.commit_calls == ["AAPL"]
    assert reset_observations == ["AAPL"]

    handle = context.source_repository.get_source_handle("AAPL", document_id, SourceKind.MATERIAL)
    meta = context.source_repository.get_source_meta("AAPL", document_id, SourceKind.MATERIAL)
    assert str(meta["primary_document"]).endswith("_docling.json")
    file_names = sorted(meta.uri.split("/")[-1] for meta in context.blob_repository.list_files(handle))
    assert file_names == ["deck_old.pdf", "deck_old_docling.json"]
    assert context.blob_repository.read_file_bytes(handle, "deck_old.pdf") == b"old material"
    docling_bytes = context.blob_repository.read_file_bytes(handle, "deck_old_docling.json")
    assert b'"docling"' in docling_bytes
