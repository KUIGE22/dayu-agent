"""CN 单 filing 阶段机三段边界测试（S14-CTRL-12）。

直调 ``run_cn_download_single_filing_stream``，注入 fake staged store（S3
模式）与记录型 batching/gate，验证：

- 阶段 A（provider download）与阶段 B（read_bytes + Docling）期间无 active
  token；``begin_batch`` 只在 Docling 转换完成后才调用；
- 阶段 A / 阶段 B（read_bytes）失败 => batching 零 begin/commit/rollback，
  事件流含 ``FILING_FAILED``，gate slot 释放；
- 阶段 C begin 后 repository failure => rollback 同一 token；
- 阶段 A 参数 ``provider_download_timeout_seconds`` 真实生效：超时即失败终态、
  late result 不进入 B/C、slot 绑定实际 inner future 在 inner 完成后才释放；
- outer cancel during A/B：CancelledError 传播、不取消 worker、不提前释放
  slot，容量 1 下第二 filing 在 inner 真正结束前不能开始。
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import pytest

from dayu.fins.domain.document_models import (
    BatchToken,
    FileObjectMeta,
)
from dayu.fins.pipelines.cn_download_filing_workflow import (
    run_cn_download_single_filing_stream,
)
from dayu.fins.pipelines.cn_download_models import (
    CnCompanyProfile,
    CnReportCandidate,
    CnReportQuery,
    DownloadedReportAsset,
)
from dayu.fins.pipelines.cn_download_pdf_gate import NoopCnDownloadPdfGate
from dayu.fins.pipelines.cn_download_protocols import CnPreparationGate
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    FsBatchingRepository,
    FsDocumentBlobRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet
from dayu.fins.storage._fs_storage_core import FsStorageCore
from dayu.fins.storage.s3_file_store import StagedFileStoreProtocol
from tests.fins.storage_testkit import build_fs_storage_test_context

_PDF_BYTES = b"%PDF-1.7\n" + b"0" * 2048
_DOCLING_BYTES = b'{"document": "ok"}'
_SHA256_HEX = "0" * 64
_TIMESTAMP = "2026-05-02T00:00:00+00:00"
_MODULE = "test_cn_to_thread_boundary"
_SHORT_TIMEOUT_SECONDS = 0.1
_DEFAULT_TIMEOUT_SECONDS = 300.0


class _FakeStagedStore(StagedFileStoreProtocol):
    """记录远端写入/删除的 staged fake（S3 模式开关）。

    实现 ``StagedFileStoreProtocol`` 全部方法；``stat_object`` 供 stage-delete
    head 校验使用。``fail_publish`` 注入阶段 C blob 写入失败。
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
        self.fail_publish: bool = False

    def stage_publish(self, *, operation_id: str, data: BinaryIO) -> FileObjectMeta:
        """把字节写入 staging key 并返回元数据。

        Args:
            operation_id: 当前 operation id。
            data: caller 二进制流。

        Returns:
            staging key 对应元数据。

        Raises:
            OSError: ``fail_publish`` 为真时抛出（注入写入失败）。
        """

        if self.fail_publish:
            raise OSError("staged publish failed")
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
        """幂等删除（记录调用）。

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


@dataclass
class _FakeDiscoveryClient:
    """CN discovery / 下载 fake（写临时 PDF，支持失败与阻塞注入）。"""

    temp_dir: Path
    pdf_bytes: bytes = _PDF_BYTES
    download_calls: int = 0
    fail_download: bool = False
    fail_after_block: bool = False
    delete_pdf_before_return: bool = False
    block_after_write: bool = False
    entered_blocker: threading.Event | None = None
    blocker: threading.Event | None = None

    def resolve_company(self, query: CnReportQuery) -> CnCompanyProfile:
        """返回固定公司元数据。

        Args:
            query: 单次 download 的查询参数。

        Returns:
             固定公司元数据。

        Raises:
            无。
        """

        return CnCompanyProfile(
            provider="cninfo",
            company_id="CNINFO:9900000600",
            company_name="贵州茅台",
            ticker=query.normalized_ticker,
        )

    def list_report_candidates(
        self,
        query: CnReportQuery,
        profile: CnCompanyProfile,
    ) -> tuple[CnReportCandidate, ...]:
        """返回空候选（本 harness 直调阶段机，只走 download）。

        Args:
            query: 单次 download 的查询参数。
            profile: 公司元数据。

        Returns:
             空候选 tuple。

        Raises:
            无。
        """

        del query, profile
        return ()

    def download_report_pdf(self, candidate: CnReportCandidate) -> DownloadedReportAsset:
        """写入临时 PDF 并返回资产；可注入失败/阻塞。

        Args:
            candidate: 待下载候选。

        Returns:
             已下载 PDF 资产。

        Raises:
            RuntimeError: ``fail_download`` 或 ``fail_after_block`` 为真时抛出。
        """

        self.download_calls += 1
        if self.fail_download:
            raise RuntimeError("download failed")
        path = self.temp_dir / f"{candidate.source_id}_{self.download_calls}.pdf"
        if self.block_after_write:
            # 先写临时 PDF 再阻塞：模拟 provider 已产出 late asset 后被 outer
            # 超时/取消放弃（S14-RR-02 无 gate 路径的可观测清理对象）。
            path.write_bytes(self.pdf_bytes)
            entered = self.entered_blocker
            if entered is not None:
                entered.set()
            blocker = self.blocker
            if blocker is not None:
                blocker.wait()
        else:
            blocker = self.blocker
            if blocker is not None:
                blocker.wait()
            if self.fail_after_block:
                raise RuntimeError("download failed after block")
            path.write_bytes(self.pdf_bytes)
        if self.delete_pdf_before_return:
            path.unlink()
        return DownloadedReportAsset(
            candidate=candidate,
            pdf_path=path,
            sha256=hashlib.sha256(self.pdf_bytes).hexdigest(),
            content_length=len(self.pdf_bytes),
            downloaded_at=_TIMESTAMP,
        )


@dataclass
class _RecordingConverter:
    """记录 Docling 转换调用并断言阶段 A/B 无 active token；支持阻塞注入。"""

    batching: _RecordingBatching
    core: FsStorageCore
    calls: int = 0
    fail_once: bool = False
    blocker: threading.Event | None = None

    def __call__(self, raw_data: bytes, stream_name: str) -> bytes:
        """转换并断言转换期间无已 begin 的 batch；可注入阻塞。

        Args:
            raw_data: PDF 字节。
            stream_name: 文件名。

        Returns:
            固定 Docling JSON 字节。

        Raises:
            RuntimeError: ``fail_once`` 为真时抛出。
        """

        assert self.batching.begin_batch_calls == 0
        assert self.core._active_batches == {}
        self.calls += 1
        blocker = self.blocker
        if blocker is not None:
            blocker.wait()
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("docling failed")
        return _DOCLING_BYTES


class _RecordingBatching(BatchingRepositoryProtocol):
    """记录 begin/commit/rollback 调用并委托真实同-core 批处理仓储。"""

    def __init__(self, delegate: FsBatchingRepository) -> None:
        """包装真实批处理仓储。

        Args:
            delegate: 同-core 真实批处理仓储。

        Returns:
            无。

        Raises:
            无。
        """

        self._delegate = delegate
        self.begin_tokens: list[BatchToken] = []
        self.commit_tokens: list[BatchToken] = []
        self.rollback_tokens: list[BatchToken] = []

    @property
    def begin_batch_calls(self) -> int:
        """返回 begin 调用次数。

        Args:
            无。

        Returns:
            begin 调用次数。

        Raises:
            无。
        """

        return len(self.begin_tokens)

    def begin_batch(self, ticker: str) -> BatchToken:
        """记录并委托 begin。

        Args:
            ticker: 股票代码。

        Returns:
            批处理 token。

        Raises:
            RuntimeError: 同 ticker 已存在活动事务时抛出。
        """

        token = self._delegate.begin_batch(ticker)
        self.begin_tokens.append(token)
        return token

    def commit_batch(self, token: BatchToken) -> None:
        """记录并委托 commit。

        Args:
            token: 批处理 token。

        Returns:
            无。

        Raises:
            ValueError: token 非当前活动事务时抛出。
        """

        self.commit_tokens.append(token)
        self._delegate.commit_batch(token)

    def rollback_batch(self, token: BatchToken) -> None:
        """记录并委托 rollback。

        Args:
            token: 批处理 token。

        Returns:
            无。

        Raises:
            ValueError: token 非当前活动事务时抛出。
        """

        self.rollback_tokens.append(token)
        self._delegate.rollback_batch(token)

    def recover_orphan_batches(self, *, dry_run: bool = False) -> tuple[str, ...]:
        """委托恢复孤儿 batch。

        Args:
            dry_run: 是否仅返回动作。

        Returns:
            动作摘要。

        Raises:
            OSError: 恢复过程访问文件系统失败时抛出。
        """

        return self._delegate.recover_orphan_batches(dry_run=dry_run)


@dataclass
class _RunHarness:
    """单 filing 阶段机测试装配（同 core 仓储 + 注入 fake）。"""

    core: FsStorageCore
    fake_store: _FakeStagedStore
    source_repository: FsSourceDocumentRepository
    blob_repository: FsDocumentBlobRepository
    processed_repository: FsProcessedDocumentRepository
    batching: _RecordingBatching
    gate: CnPreparationGate
    discovery: _FakeDiscoveryClient
    converter: _RecordingConverter


def _build_harness(tmp_path: Path) -> _RunHarness:
    """构造注入 fake staged store / batching / gate 的测试装配。

    Args:
        tmp_path: 工作区根目录。

    Returns:
        可直调阶段机的 harness。

    Raises:
        OSError: 仓储初始化失败时抛出。
    """

    context = build_fs_storage_test_context(tmp_path)
    fake_store = _FakeStagedStore()
    context.core._file_store = fake_store
    batching = _RecordingBatching(
        FsBatchingRepository(
            tmp_path,
            repository_set=_FsRepositorySet(core=context.core),
        )
    )
    gate = CnPreparationGate(capacity=1)
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path)
    converter = _RecordingConverter(batching=batching, core=context.core)
    return _RunHarness(
        core=context.core,
        fake_store=fake_store,
        source_repository=context.source_repository,
        blob_repository=context.blob_repository,
        processed_repository=context.processed_repository,
        batching=batching,
        gate=gate,
        discovery=discovery,
        converter=converter,
    )


def _candidate(*, source_id: str = "A1") -> CnReportCandidate:
    """构造 CN 候选。

    Args:
        source_id: provider 内部唯一 ID。

    Returns:
        单份候选报告。

    Raises:
        无。
    """

    return CnReportCandidate(
        provider="cninfo",
        source_id=source_id,
        source_url=f"https://static.cninfo.test/{source_id}.pdf",
        title="贵州茅台：2024年年度报告",
        language="zh",
        filing_date="2025-04-01",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
        content_length=len(_PDF_BYTES),
        etag='"v1"',
        last_modified="Wed, 01 Apr 2026 00:00:00 GMT",
    )


def _profile(ticker: str) -> CnCompanyProfile:
    """构造公司基础元数据。

    Args:
        ticker: 已归一化 ticker。

    Returns:
        公司元数据。

    Raises:
        无。
    """

    return CnCompanyProfile(
        provider="cninfo",
        company_id="CNINFO:9900000600",
        company_name="贵州茅台",
        ticker=ticker,
    )


async def _collect_events(harness: _RunHarness, *, candidate: CnReportCandidate) -> list[DownloadEvent]:
    """收集单 filing 事件流。

    Args:
        harness: 测试装配。
        candidate: 待下载候选。

    Returns:
        完整事件列表。

    Raises:
        Exception: 阶段机内部仓储/下载失败时透传。
    """

    events: list[DownloadEvent] = []
    async for event in run_cn_download_single_filing_stream(
        source_repository=harness.source_repository,
        blob_repository=harness.blob_repository,
        processed_repository=harness.processed_repository,
        discovery_client=harness.discovery,
        pdf_download_gate=NoopCnDownloadPdfGate(),
        convert_pdf_to_docling_json=harness.converter,
        ticker="600519",
        profile=_profile("600519"),
        candidate=candidate,
        overwrite=False,
        cancel_checker=None,
        module=_MODULE,
        batching_repository=harness.batching,
        preparation_gate=harness.gate,
    ):
        events.append(event)
    return events


async def _drain_events_with_timeout(
    harness: _RunHarness,
    *,
    candidate: CnReportCandidate,
    provider_download_timeout_seconds: float,
) -> list[DownloadEvent]:
    """收集单 filing 事件流（显式传阶段 A 参数 timeout）。

    Args:
        harness: 测试装配。
        candidate: 待下载候选。
        provider_download_timeout_seconds: 阶段 A hard timeout。

    Returns:
        完整事件列表。

    Raises:
        Exception: 阶段机内部仓储/下载失败时透传。
    """

    events: list[DownloadEvent] = []
    async for event in run_cn_download_single_filing_stream(
        source_repository=harness.source_repository,
        blob_repository=harness.blob_repository,
        processed_repository=harness.processed_repository,
        discovery_client=harness.discovery,
        pdf_download_gate=NoopCnDownloadPdfGate(),
        convert_pdf_to_docling_json=harness.converter,
        ticker="600519",
        profile=_profile("600519"),
        candidate=candidate,
        overwrite=False,
        cancel_checker=None,
        module=_MODULE,
        batching_repository=harness.batching,
        preparation_gate=harness.gate,
        provider_download_timeout_seconds=provider_download_timeout_seconds,
    ):
        events.append(event)
    return events


async def _run_single_filing_stream(
    harness: _RunHarness,
    *,
    candidate: CnReportCandidate,
    preparation_gate: CnPreparationGate | None,
    provider_download_timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> list[DownloadEvent]:
    """直调阶段机并收集事件（显式 gate 与阶段 A timeout；gate 可为 None）。

    Args:
        harness: 测试装配。
        candidate: 待下载候选。
        preparation_gate: 可选 preparation gate；``None`` 覆盖
            standalone/FS ``CnPipeline`` 的允许路径（S14-RR-02）。
        provider_download_timeout_seconds: 阶段 A hard timeout。

    Returns:
        完整事件列表。

    Raises:
        Exception: 阶段机内部仓储/下载失败时透传。
    """

    events: list[DownloadEvent] = []
    async for event in run_cn_download_single_filing_stream(
        source_repository=harness.source_repository,
        blob_repository=harness.blob_repository,
        processed_repository=harness.processed_repository,
        discovery_client=harness.discovery,
        pdf_download_gate=NoopCnDownloadPdfGate(),
        convert_pdf_to_docling_json=harness.converter,
        ticker="600519",
        profile=_profile("600519"),
        candidate=candidate,
        overwrite=False,
        cancel_checker=None,
        module=_MODULE,
        batching_repository=harness.batching,
        preparation_gate=preparation_gate,
        provider_download_timeout_seconds=provider_download_timeout_seconds,
    ):
        events.append(event)
    return events


async def _wait_for_gate_release(gate: CnPreparationGate, *, timeout_seconds: float = 5.0) -> None:
    """有界等待 gate slot 收敛释放（poll 事件循环处理 done callback）。

    Args:
        gate: 共享 preparation gate。
        timeout_seconds: 最大等待秒数。

    Returns:
        无。

    Raises:
        AssertionError: 超时仍占用时抛出。
    """

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while gate.has_admitted_work():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(f"gate slot 未在 {timeout_seconds} 秒内释放")
        await asyncio.sleep(0.01)


async def _wait_for_no_pdf(tmp_path: Path, *, timeout_seconds: float = 5.0) -> None:
    """有界等待 late provider 的临时 PDF 被 done callback 精确回收（S14-RR-02）。

    Args:
        tmp_path: 工作区根目录（临时 PDF 所在目录）。
        timeout_seconds: 最大等待秒数。

    Returns:
        无。

    Raises:
        AssertionError: 超时仍存在临时 PDF 时抛出。
    """

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while list(tmp_path.glob("*.pdf")):
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(f"late provider 临时 PDF 未在 {timeout_seconds} 秒内被回收")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_begin_batch_only_after_docling_conversion(tmp_path: Path) -> None:
    """阶段 A/B 期间无 active token，begin 只在 Docling 转换完成后发生。

    记录型 converter 在转换瞬间断言 batching 零 begin 且 core 无活动 batch；
    全部事件消费完成后 begin/commit 各一次、rollback 零次，gate slot 已释放。
    """

    harness = _build_harness(tmp_path)

    events = await _collect_events(harness, candidate=_candidate())

    assert [item.event_type for item in events] == [
        DownloadEventType.FILE_DOWNLOADED,
        DownloadEventType.FILING_COMPLETED,
    ]
    assert harness.converter.calls == 1
    assert harness.batching.begin_batch_calls == 1
    assert len(harness.batching.commit_tokens) == 1
    assert harness.batching.rollback_tokens == []
    assert harness.gate.has_admitted_work() is False
    assert harness.core._active_batches == {}


@pytest.mark.asyncio
async def test_stage_a_failure_yields_filing_failed_with_zero_begin(tmp_path: Path) -> None:
    """阶段 A provider 抛错 => FILING_FAILED，batching 零 begin/commit/rollback。

    provider 失败发生在 begin 之前，阶段 C 永不进入；gate slot 释放。
    """

    harness = _build_harness(tmp_path)
    harness.discovery.fail_download = True

    events = await _collect_events(harness, candidate=_candidate())

    failed = [item for item in events if item.event_type == DownloadEventType.FILING_FAILED]
    assert len(failed) == 1
    assert failed[0].payload["reason_code"] == "pdf_download_failed"
    assert harness.batching.begin_batch_calls == 0
    assert harness.batching.commit_tokens == []
    assert harness.batching.rollback_tokens == []
    assert harness.gate.has_admitted_work() is False
    assert harness.core._active_batches == {}


@pytest.mark.asyncio
async def test_stage_b_read_failure_yields_filing_failed_with_zero_begin(tmp_path: Path) -> None:
    """阶段 B read_bytes 失败 => FILING_FAILED，batching 零 begin/commit/rollback。

    downloader 返回前删除暂存 PDF，``_read_and_unlink_temp_pdf`` 读取抛
    ``FileNotFoundError``；事件流含 ``pdf_read_failed``。
    """

    harness = _build_harness(tmp_path)
    harness.discovery.delete_pdf_before_return = True

    events = await _collect_events(harness, candidate=_candidate())

    failed = [item for item in events if item.event_type == DownloadEventType.FILING_FAILED]
    assert len(failed) == 1
    assert failed[0].payload["reason_code"] == "pdf_read_failed"
    assert harness.batching.begin_batch_calls == 0
    assert harness.batching.commit_tokens == []
    assert harness.batching.rollback_tokens == []
    assert harness.gate.has_admitted_work() is False


@pytest.mark.asyncio
async def test_stage_c_repository_failure_rolls_back_same_token(tmp_path: Path) -> None:
    """阶段 C begin 后 repository failure => rollback 同一 token。

    fake staged store 在阶段 C blob 写入（``stage_publish``）抛
    ``OSError``；阶段机 begin 一次、rollback 同一 token、commit 零次，
    异常透传，core 无残留活动 batch。
    """

    harness = _build_harness(tmp_path)
    harness.fake_store.fail_publish = True

    with pytest.raises(OSError):
        await _collect_events(harness, candidate=_candidate())

    assert harness.batching.begin_batch_calls == 1
    assert harness.batching.commit_tokens == []
    assert [item.token_id for item in harness.batching.rollback_tokens] == [
        harness.batching.begin_tokens[0].token_id
    ]
    assert harness.gate.has_admitted_work() is False
    assert harness.core._active_batches == {}


@pytest.mark.asyncio
async def test_stage_a_param_timeout_yields_failed_then_slot_released(tmp_path: Path) -> None:
    """阶段 A 参数 timeout 真实生效：FILING_FAILED、零 begin、slot 随 late inner 释放。

    ``provider_download_timeout_seconds`` 只包裹 outer 等待：provider 在线程内
    阻塞，参数超时后产出失败终态；late success 禁止进入 B/C（converter 零
    调用）；slot 在 inner 真正完成后才 release，绝不提前释放。
    """

    harness = _build_harness(tmp_path)
    blocker = threading.Event()
    harness.discovery.blocker = blocker

    events: list[DownloadEvent] = []
    async for event in run_cn_download_single_filing_stream(
        source_repository=harness.source_repository,
        blob_repository=harness.blob_repository,
        processed_repository=harness.processed_repository,
        discovery_client=harness.discovery,
        pdf_download_gate=NoopCnDownloadPdfGate(),
        convert_pdf_to_docling_json=harness.converter,
        ticker="600519",
        profile=_profile("600519"),
        candidate=_candidate(),
        overwrite=False,
        cancel_checker=None,
        module=_MODULE,
        batching_repository=harness.batching,
        preparation_gate=harness.gate,
        provider_download_timeout_seconds=_SHORT_TIMEOUT_SECONDS,
    ):
        events.append(event)

    failed = [item for item in events if item.event_type == DownloadEventType.FILING_FAILED]
    assert len(failed) == 1
    assert failed[0].payload["reason_code"] == "pdf_download_failed"
    assert failed[0].payload["reason_message"] == "provider download timeout"
    assert harness.batching.begin_batch_calls == 0
    assert harness.batching.commit_tokens == []
    assert harness.batching.rollback_tokens == []
    assert harness.converter.calls == 0
    # 超时瞬间 slot 仍被持有（provider worker 尚未完成）。
    assert harness.gate.has_admitted_work() is True
    # late success 完成后 slot 才收敛释放；临时 PDF 被 late cleanup 删除。
    blocker.set()
    await _wait_for_gate_release(harness.gate)
    assert harness.discovery.download_calls == 1
    assert list(tmp_path.glob("*.pdf")) == []
    assert harness.core._active_batches == {}


@pytest.mark.asyncio
async def test_stage_a_param_timeout_second_filing_blocks_until_inner_done(tmp_path: Path) -> None:
    """容量 1 gate：阶段 A timeout 后第二 filing 在 inner 真正完成前不能开始。

    第一 filing 超时产失败终态但 slot 仍被 late provider worker 持有；第二
    filing 停在 ``gate.acquire()``，provider 零调用；late worker 完成后 slot
    释放，第二 filing 才能继续并正常完成。
    """

    harness = _build_harness(tmp_path)
    blocker = threading.Event()
    harness.discovery.blocker = blocker

    first_task = asyncio.create_task(
        _drain_events_with_timeout(
            harness,
            candidate=_candidate(source_id="A1"),
            provider_download_timeout_seconds=_SHORT_TIMEOUT_SECONDS,
        )
    )
    await asyncio.sleep(_SHORT_TIMEOUT_SECONDS + 0.1)
    second_task = asyncio.create_task(
        _drain_events_with_timeout(
            harness,
            candidate=_candidate(source_id="A2"),
            provider_download_timeout_seconds=_DEFAULT_TIMEOUT_SECONDS,
        )
    )
    await asyncio.sleep(0.1)

    assert harness.discovery.download_calls == 1
    assert harness.gate.has_admitted_work() is True
    first_events = await first_task
    failed = [item for item in first_events if item.event_type == DownloadEventType.FILING_FAILED]
    assert len(failed) == 1

    blocker.set()
    await _wait_for_gate_release(harness.gate)
    second_events = await second_task
    assert harness.discovery.download_calls == 2
    assert [item.event_type for item in second_events] == [
        DownloadEventType.FILE_DOWNLOADED,
        DownloadEventType.FILING_COMPLETED,
    ]
    assert harness.batching.begin_batch_calls == 1
    assert len(harness.batching.commit_tokens) == 1
    assert harness.gate.has_admitted_work() is False


@pytest.mark.asyncio
async def test_stage_a_param_timeout_late_exception_releases_slot(tmp_path: Path) -> None:
    """阶段 A 参数 timeout 后 provider late exception：slot 随 inner 完成释放。"""

    harness = _build_harness(tmp_path)
    blocker = threading.Event()
    harness.discovery.blocker = blocker
    harness.discovery.fail_after_block = True

    events: list[DownloadEvent] = []
    async for event in run_cn_download_single_filing_stream(
        source_repository=harness.source_repository,
        blob_repository=harness.blob_repository,
        processed_repository=harness.processed_repository,
        discovery_client=harness.discovery,
        pdf_download_gate=NoopCnDownloadPdfGate(),
        convert_pdf_to_docling_json=harness.converter,
        ticker="600519",
        profile=_profile("600519"),
        candidate=_candidate(),
        overwrite=False,
        cancel_checker=None,
        module=_MODULE,
        batching_repository=harness.batching,
        preparation_gate=harness.gate,
        provider_download_timeout_seconds=_SHORT_TIMEOUT_SECONDS,
    ):
        events.append(event)

    assert harness.gate.has_admitted_work() is True
    blocker.set()
    await _wait_for_gate_release(harness.gate)
    assert harness.converter.calls == 0
    assert harness.batching.begin_batch_calls == 0
    assert harness.gate.has_admitted_work() is False


@pytest.mark.asyncio
async def test_outer_cancel_during_stage_a_eventually_releases_slot(tmp_path: Path) -> None:
    """outer cancel during A：CancelledError 传播、不取消 worker、slot 随 inner 释放。

    provider 在线程内阻塞，外层 ``asyncio.timeout`` 取消消费端；阶段 A 的取消
    以 ``asyncio.CancelledError`` 形式进入生成器（绕过节流处理），late result
    不进入 B/C；blocker 释放后 inner 完成，slot 收敛 release，零 publish。
    """

    harness = _build_harness(tmp_path)
    blocker = threading.Event()
    harness.discovery.blocker = blocker
    candidate = _candidate()

    async def drain() -> list[DownloadEvent]:
        events: list[DownloadEvent] = []
        async with asyncio.timeout(_SHORT_TIMEOUT_SECONDS):
            async for event in run_cn_download_single_filing_stream(
                source_repository=harness.source_repository,
                blob_repository=harness.blob_repository,
                processed_repository=harness.processed_repository,
                discovery_client=harness.discovery,
                pdf_download_gate=NoopCnDownloadPdfGate(),
                convert_pdf_to_docling_json=harness.converter,
                ticker="600519",
                profile=_profile("600519"),
                candidate=candidate,
                overwrite=False,
                cancel_checker=None,
                module=_MODULE,
                batching_repository=harness.batching,
                preparation_gate=harness.gate,
            ):
                events.append(event)
        return events

    try:
        with pytest.raises(TimeoutError):
            await drain()
    finally:
        blocker.set()

    assert harness.batching.begin_batch_calls == 0
    assert harness.batching.commit_tokens == []
    assert harness.batching.rollback_tokens == []
    assert harness.converter.calls == 0
    await _wait_for_gate_release(harness.gate)
    assert harness.core._active_batches == {}


@pytest.mark.asyncio
async def test_outer_cancel_during_stage_b_docling_eventually_releases_slot(tmp_path: Path) -> None:
    """outer cancel during B（Docling worker 阻塞）：slot 随真实 inner 完成释放。

    阶段 A 正常成功持有 slot；Docling worker 在线程内阻塞时 outer 取消；late
    转换结果不进入阶段 C（零 begin/commit/rollback/零 publish）；worker 完成后
    slot 收敛 release。
    """

    harness = _build_harness(tmp_path)
    converter_blocker = threading.Event()
    harness.converter.blocker = converter_blocker
    candidate = _candidate()

    async def drain() -> list[DownloadEvent]:
        events: list[DownloadEvent] = []
        async with asyncio.timeout(_SHORT_TIMEOUT_SECONDS):
            async for event in run_cn_download_single_filing_stream(
                source_repository=harness.source_repository,
                blob_repository=harness.blob_repository,
                processed_repository=harness.processed_repository,
                discovery_client=harness.discovery,
                pdf_download_gate=NoopCnDownloadPdfGate(),
                convert_pdf_to_docling_json=harness.converter,
                ticker="600519",
                profile=_profile("600519"),
                candidate=candidate,
                overwrite=False,
                cancel_checker=None,
                module=_MODULE,
                batching_repository=harness.batching,
                preparation_gate=harness.gate,
            ):
                events.append(event)
        return events

    try:
        with pytest.raises(TimeoutError):
            await drain()
    finally:
        converter_blocker.set()

    assert harness.batching.begin_batch_calls == 0
    assert harness.batching.commit_tokens == []
    assert harness.batching.rollback_tokens == []
    await _wait_for_gate_release(harness.gate)
    assert harness.gate.has_admitted_work() is False
    assert harness.core._active_batches == {}


@pytest.mark.asyncio
async def test_stage_a_param_timeout_no_gate_late_success_cleans_pdf(tmp_path: Path) -> None:
    """无 gate 阶段 A 参数 timeout：late success 的临时 PDF 被精确回收（S14-RR-02）。

    ``preparation_gate=None`` 是公开协议与 standalone/FS ``CnPipeline`` 的允许
    路径：超时产出 ``FILING_FAILED``、零 begin/commit/rollback、converter 零
    调用；provider 已写出临时 PDF 后在后台阻塞，late success 完成时 done
    callback 回收 exact 临时 PDF，不进入 B/C/repo。
    """

    harness = _build_harness(tmp_path)
    blocker = threading.Event()
    harness.discovery.block_after_write = True
    harness.discovery.blocker = blocker

    events = await _run_single_filing_stream(
        harness,
        candidate=_candidate(),
        preparation_gate=None,
        provider_download_timeout_seconds=_SHORT_TIMEOUT_SECONDS,
    )

    failed = [item for item in events if item.event_type == DownloadEventType.FILING_FAILED]
    assert len(failed) == 1
    assert failed[0].payload["reason_code"] == "pdf_download_failed"
    assert failed[0].payload["reason_message"] == "provider download timeout"
    assert harness.batching.begin_batch_calls == 0
    assert harness.batching.commit_tokens == []
    assert harness.batching.rollback_tokens == []
    assert harness.converter.calls == 0
    # 超时瞬间 provider 已写出临时 PDF（block_after_write），尚未被回收。
    assert harness.discovery.download_calls == 1
    assert len(list(tmp_path.glob("*.pdf"))) == 1
    # late success 完成后 done callback 回收临时 PDF；零 repository 写入。
    blocker.set()
    await _wait_for_no_pdf(tmp_path)
    assert harness.core._active_batches == {}


@pytest.mark.asyncio
async def test_stage_a_param_timeout_no_gate_late_exception_stays_closed(tmp_path: Path) -> None:
    """无 gate 阶段 A 参数 timeout：late exception 不进入 B/C，零 PDF 残留（S14-RR-02）。

    provider 阻塞后抛异常（未产出 asset，无临时 PDF）；超时后零
    begin/commit/rollback、converter 零调用，late exception 收敛后最终零
    临时 PDF、零 repository 写入。
    """

    harness = _build_harness(tmp_path)
    blocker = threading.Event()
    harness.discovery.blocker = blocker
    harness.discovery.fail_after_block = True

    events = await _run_single_filing_stream(
        harness,
        candidate=_candidate(),
        preparation_gate=None,
        provider_download_timeout_seconds=_SHORT_TIMEOUT_SECONDS,
    )

    failed = [item for item in events if item.event_type == DownloadEventType.FILING_FAILED]
    assert len(failed) == 1
    assert harness.batching.begin_batch_calls == 0
    assert harness.batching.commit_tokens == []
    assert harness.batching.rollback_tokens == []
    assert harness.converter.calls == 0
    blocker.set()
    # 让 late exception 线程收敛后再断言：零临时 PDF、零 repository 写入。
    await asyncio.sleep(0.05)
    assert list(tmp_path.glob("*.pdf")) == []
    assert harness.core._active_batches == {}


@pytest.mark.asyncio
async def test_outer_cancel_during_stage_a_no_gate_cleans_late_pdf(tmp_path: Path) -> None:
    """无 gate outer cancel during A：late PDF 被回收、零 repository 写入（S14-RR-02）。

    无 ``preparation_gate`` 时 outer 取消消费端；provider 已写出临时 PDF 并在
    后台阻塞；outer 取消传播 ``TimeoutError``，late result 不进入 B/C；释放
    blocker 后 inner 完成，done callback 回收临时 PDF，零 begin/commit/rollback。
    """

    harness = _build_harness(tmp_path)
    blocker = threading.Event()
    harness.discovery.block_after_write = True
    harness.discovery.blocker = blocker
    candidate = _candidate()

    async def drain() -> list[DownloadEvent]:
        events: list[DownloadEvent] = []
        async with asyncio.timeout(_SHORT_TIMEOUT_SECONDS):
            async for event in run_cn_download_single_filing_stream(
                source_repository=harness.source_repository,
                blob_repository=harness.blob_repository,
                processed_repository=harness.processed_repository,
                discovery_client=harness.discovery,
                pdf_download_gate=NoopCnDownloadPdfGate(),
                convert_pdf_to_docling_json=harness.converter,
                ticker="600519",
                profile=_profile("600519"),
                candidate=candidate,
                overwrite=False,
                cancel_checker=None,
                module=_MODULE,
                batching_repository=harness.batching,
                preparation_gate=None,
            ):
                events.append(event)
        return events

    try:
        with pytest.raises(TimeoutError):
            await drain()
    finally:
        blocker.set()

    assert harness.batching.begin_batch_calls == 0
    assert harness.batching.commit_tokens == []
    assert harness.batching.rollback_tokens == []
    assert harness.converter.calls == 0
    await _wait_for_no_pdf(tmp_path)
    assert harness.core._active_batches == {}
