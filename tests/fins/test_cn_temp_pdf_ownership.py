"""CN 临时 PDF 所有权与共享 preparation gate 测试（S14-CTRL-12）。

覆盖：

- ``_read_and_unlink_temp_pdf``：正常读完即删除（finally 幂等 unlink）；
  worker 读取抛错时 finally 仍执行 unlink；
- 共享 ``CnPreparationGate``（容量 1）：同 runtime 多并发 filing 时第二条在
  provider 前等待 slot，不启动 provider、不创建临时 PDF；临时 PDF 数不超过
  gate 容量；
- slot 先于 provider：等待 slot 期间 provider 未被调用，slot 跨阶段 A provider
  future 与阶段 B read+Docling inner futures 持有；
- 启动期 ``sweep_stale_temp_pdfs``：只删 owned 且 mtime 早于阈值的 regular
  非 symlink；fresh/unknown/symlink 不删。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from dayu.fins.pipelines.cn_download_filing_workflow import (
    _read_and_unlink_temp_pdf,
    _unlink_temp_pdf,
    run_cn_download_single_filing_stream,
    sweep_stale_temp_pdfs,
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
from tests.fins.storage_testkit import FsStorageTestContext, build_fs_storage_test_context

_PDF_BYTES = b"%PDF-1.7\n" + b"0" * 2048
_DOCLING_BYTES = b'{"document": "ok"}'
_TIMESTAMP = "2026-05-02T00:00:00+00:00"
_MODULE = "test_cn_temp_pdf_ownership"
_STALE_SECONDS = 2 * 24 * 3600


@dataclass
class _FakeDiscoveryClient:
    """CN discovery / 下载 fake（支持 provider 内阻塞与 gate 观测）。"""

    temp_dir: Path
    pdf_bytes: bytes = _PDF_BYTES
    download_calls: int = 0
    fail_download: bool = False
    gate: CnPreparationGate | None = None
    gate_active_at_provider: bool | None = None
    block_after_write: bool = False
    blocker: threading.Event | None = None
    entered_blocker: threading.Event | None = None

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
        """返回空候选（本测试直调阶段机，只走 download）。

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
        """写入临时 PDF 并返回资产；可记录 provider 期间 gate 持有状态。

        Args:
            candidate: 待下载候选。

        Returns:
            已下载 PDF 资产。

        Raises:
            RuntimeError: ``fail_download`` 为真时抛出。
        """

        self.download_calls += 1
        gate = self.gate
        if gate is not None:
            self.gate_active_at_provider = gate.has_admitted_work()
        if self.fail_download:
            raise RuntimeError("download failed")
        path = self.temp_dir / f"{candidate.source_id}_{self.download_calls}.pdf"
        if self.block_after_write:
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
            path.write_bytes(self.pdf_bytes)
        return DownloadedReportAsset(
            candidate=candidate,
            pdf_path=path,
            sha256=hashlib.sha256(self.pdf_bytes).hexdigest(),
            content_length=len(self.pdf_bytes),
            downloaded_at=_TIMESTAMP,
        )


@dataclass
class _GateAwareConverter:
    """记录 Docling 转换期间 gate 是否仍持有 slot。"""

    gate: CnPreparationGate
    calls: int = 0
    gate_active_during_conversion: bool | None = None

    def __call__(self, raw_data: bytes, stream_name: str) -> bytes:
        """记录转换期间 slot 状态并返回固定 Docling JSON。

        Args:
            raw_data: PDF 字节。
            stream_name: 文件名。

        Returns:
            固定 Docling JSON 字节。

        Raises:
            无。
        """

        del raw_data, stream_name
        self.calls += 1
        self.gate_active_during_conversion = self.gate.has_admitted_work()
        return _DOCLING_BYTES


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


async def _collect_events(
    context: FsStorageTestContext,
    *,
    discovery: _FakeDiscoveryClient,
    converter: _GateAwareConverter,
    gate: CnPreparationGate,
    ticker: str,
) -> list[DownloadEvent]:
    """收集单 filing 事件流。

    Args:
        context: 测试仓储上下文。
        discovery: fake discovery。
        converter: gate-aware converter。
        gate: preparation gate。
        ticker: 已归一化 ticker。

    Returns:
        完整事件列表。

    Raises:
        Exception: 阶段机内部仓储/下载失败时透传。
    """

    events: list[DownloadEvent] = []
    async for event in run_cn_download_single_filing_stream(
        source_repository=context.source_repository,
        blob_repository=context.blob_repository,
        processed_repository=context.processed_repository,
        discovery_client=discovery,
        pdf_download_gate=NoopCnDownloadPdfGate(),
        convert_pdf_to_docling_json=converter,
        ticker=ticker,
        profile=_profile(ticker),
        candidate=_candidate(),
        overwrite=False,
        cancel_checker=None,
        module=_MODULE,
        batching_repository=None,
        preparation_gate=gate,
    ):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_slot_held_before_provider_and_through_conversion(tmp_path: Path) -> None:
    """slot 先于 provider，且跨阶段 A provider 与阶段 B 转换持有。

    单 filing 成功流：provider 执行瞬间 gate 已有 active slot；Docling 转换
    瞬间 slot 仍被持有；完成后 slot 释放、事件流为
    FILE_DOWNLOADED + FILING_COMPLETED。
    """

    context = build_fs_storage_test_context(tmp_path)
    gate = CnPreparationGate(capacity=1)
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, gate=gate)
    converter = _GateAwareConverter(gate=gate)

    events = await _collect_events(
        context,
        discovery=discovery,
        converter=converter,
        gate=gate,
        ticker="600519",
    )

    assert discovery.gate_active_at_provider is True
    assert converter.gate_active_during_conversion is True
    assert gate.has_admitted_work() is False
    assert [item.event_type for item in events] == [
        DownloadEventType.FILE_DOWNLOADED,
        DownloadEventType.FILING_COMPLETED,
    ]
    assert list(tmp_path.glob("*.pdf")) == []


@pytest.mark.asyncio
async def test_shared_gate_capacity_one_serializes_provider_and_temp_pdf(tmp_path: Path) -> None:
    """共享容量 1 gate：第二条在 provider 前等待 slot，不创建临时 PDF。

    第一条取得 slot 并在 provider 内阻塞（已写临时 PDF）；第二条并发时停在
    gate acquire，其 provider 零调用、临时 PDF 数保持 1；释放后两条都完成，
    临时 PDF 全部清理。
    """

    context = build_fs_storage_test_context(tmp_path)
    gate = CnPreparationGate(capacity=1)
    entered = threading.Event()
    release = threading.Event()
    first_discovery = _FakeDiscoveryClient(
        temp_dir=tmp_path,
        gate=gate,
        block_after_write=True,
        entered_blocker=entered,
        blocker=release,
    )
    second_discovery = _FakeDiscoveryClient(temp_dir=tmp_path, gate=gate)
    converter = _GateAwareConverter(gate=gate)

    first_task = asyncio.create_task(
        _collect_events(
            context,
            discovery=first_discovery,
            converter=converter,
            gate=gate,
            ticker="600519",
        )
    )
    assert await asyncio.to_thread(entered.wait, 5)
    await asyncio.sleep(0.05)
    second_task = asyncio.create_task(
        _collect_events(
            context,
            discovery=second_discovery,
            converter=converter,
            gate=gate,
            ticker="000001",
        )
    )
    await asyncio.sleep(0.1)

    assert first_discovery.download_calls == 1
    assert second_discovery.download_calls == 0
    assert len(list(tmp_path.glob("*.pdf"))) == 1
    assert gate.has_admitted_work() is True

    release.set()
    await asyncio.gather(first_task, second_task)

    assert first_discovery.download_calls == 1
    assert second_discovery.download_calls == 1
    assert converter.calls == 2
    assert converter.gate_active_during_conversion is True
    assert gate.has_admitted_work() is False
    assert list(tmp_path.glob("*.pdf")) == []


def test_read_and_unlink_temp_pdf_unlinks_after_success(tmp_path: Path) -> None:
    """正常读完即删除，finally 幂等 unlink 无副作用。

    读取返回字节后文件被删除；路径已不存在时再次 unlink 不抛错。
    """

    path = tmp_path / "cninfo_A1.pdf"
    path.write_bytes(_PDF_BYTES)

    content = _read_and_unlink_temp_pdf(path, module=_MODULE)

    assert content == _PDF_BYTES
    assert not path.exists()
    _unlink_temp_pdf(path, module=_MODULE)


def test_read_and_unlink_temp_pdf_still_unlinks_on_read_error(tmp_path: Path) -> None:
    """读取抛错时 finally 仍执行 unlink。

    临时 PDF 为指向缺失目标的 symlink：``read_bytes`` 抛
    ``FileNotFoundError``，finally 幂等 unlink 把 symlink 本体删除。
    """

    path = tmp_path / "cninfo_A2.pdf"
    path.symlink_to(tmp_path / "missing_target.pdf")

    with pytest.raises(FileNotFoundError):
        _read_and_unlink_temp_pdf(path, module=_MODULE)

    assert not path.exists()


def test_sweep_stale_temp_pdfs_deletes_only_owned_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """启动期 sweep 只删 owned 且 mtime 早于阈值的 regular 非 symlink。

    老化的 ``cninfo_*.pdf`` 被删；fresh、非 owned 前缀、非 pdf、symlink 均
    保留。
    """

    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    downloads_dir = tmp_path / "dayu_cn_downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    stale = downloads_dir / "cninfo_stale.pdf"
    stale.write_bytes(_PDF_BYTES)
    old_mtime = time.time() - _STALE_SECONDS
    os.utime(stale, (old_mtime, old_mtime))
    fresh = downloads_dir / "cninfo_fresh.pdf"
    fresh.write_bytes(_PDF_BYTES)
    unknown_prefix = downloads_dir / "other.pdf"
    unknown_prefix.write_bytes(_PDF_BYTES)
    non_pdf = downloads_dir / "cninfo_note.txt"
    non_pdf.write_text("note")
    symlink = downloads_dir / "cninfo_link.pdf"
    symlink.symlink_to(stale)

    removed = sweep_stale_temp_pdfs(module=_MODULE)

    assert removed == 1
    assert not stale.exists()
    assert fresh.exists()
    assert unknown_prefix.exists()
    assert non_pdf.exists()
    assert symlink.is_symlink()
