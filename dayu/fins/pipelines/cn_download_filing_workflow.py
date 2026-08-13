"""CN/HK 单份财报下载阶段机。

阶段机负责单个 :class:`CnReportCandidate` 的 skip、PDF 下载 / 复用、Docling
转换 / 复用以及 source commit。所有持久化动作都经 ``dayu.fins.storage`` 的
窄仓储协议完成；本模块不直接拼 workspace 路径。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TypeVar

from dayu.contracts.cancellation import CancelledError
from dayu.fins.domain.document_models import BatchToken, FileObjectMeta, SourceHandle
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_download_models import (
    CN_PIPELINE_DOWNLOAD_VERSION,
    CnCompanyProfile,
    CnReportCandidate,
    DownloadedReportAsset,
)
from dayu.fins.pipelines.cn_download_pdf_gate import CnDownloadPdfGateProtocol
from dayu.fins.pipelines.cn_download_protocols import (
    CnPreparationGate,
    CnReportDiscoveryClientProtocol,
)
from dayu.fins.pipelines.cn_download_source_upsert import (
    JsonObject,
    JsonValue,
    build_cn_file_entry,
    build_content_fingerprint,
    build_remote_fingerprint,
    commit_cn_filing_source_document,
    update_cn_staging_source_document,
)
from dayu.fins.pipelines.cn_download_staging import has_blob_file, inspect_staged_blobs
from dayu.fins.pipelines.docling_upload_service import build_cn_filing_ids
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    DocumentBlobRepositoryProtocol,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.log import Log

_PDF_CONTENT_TYPE = "application/pdf"
_JSON_CONTENT_TYPE = "application/json"
_SOURCE_LABEL_ORIGINAL = "original"
_SOURCE_LABEL_DOCLING = "docling"
_DEFAULT_PROVIDER_DOWNLOAD_TIMEOUT_SECONDS = 300.0
"""CN/HK 阶段 A（provider download/request）默认 hard timeout 秒数。"""
_CN_TEMP_PDF_STALE_SECONDS = 24 * 3600
"""startup stale-temp sweep 的有限 stale 阈值（owned 临时 PDF mtime 早于此时长才删）。"""

_InnerTaskT = TypeVar("_InnerTaskT")
"""阶段 A/B 实际 inner future 的结果类型参数（provider/read/Docling 各异）。"""


class CnDownloadFilingError(RuntimeError):
    """CN/HK 单 filing 下载失败。"""


def _rollback_batch_preserving_primary(
    batching_repository: BatchingRepositoryProtocol,
    token: BatchToken,
    *,
    primary: BaseException,
    ticker: str,
    document_id: str,
    module: str,
) -> None:
    """在已有主异常时尽力回滚且不让清理失败遮蔽主异常。

    Args:
        batching_repository: 当前 batch 仓储。
        token: 必须回滚的原始 batch token。
        primary: 必须保留并继续传播的主异常。
        ticker: 当前股票代码。
        document_id: 当前 filing 文档标识。
        module: 日志模块名。

    Returns:
        无。

    Raises:
        无；回滚或日志异常均由调用方保留的主异常覆盖。
    """

    try:
        batching_repository.rollback_batch(token)
    except BaseException as rollback_error:
        try:
            primary.add_note(
                f"rollback_batch failed: {type(rollback_error).__name__}: {rollback_error}"
            )
        except BaseException:
            pass
        try:
            Log.warn(
                f"CN per-filing rollback 失败: ticker={ticker} document_id={document_id} error={rollback_error}",
                module=module,
            )
        except BaseException:
            pass


def _read_and_unlink_temp_pdf(path: Path, *, module: str) -> bytes:
    """读取临时 PDF 并在 finally 中幂等删除（阶段 B 唯一清理 owner）。

    Args:
        path: downloader 暂存 PDF 路径。
        module: 日志模块名。

    Returns:
        PDF 字节内容。

    Raises:
        OSError: 读取失败时抛出。
    """

    try:
        return path.read_bytes()
    finally:
        _unlink_temp_pdf(path, module=module)


def _download_report_pdf_with_gate(
    *,
    discovery_client: CnReportDiscoveryClientProtocol,
    pdf_download_gate: CnDownloadPdfGateProtocol,
    candidate: CnReportCandidate,
    cancel_checker: Callable[[], bool] | None,
) -> DownloadedReportAsset:
    """在 PDF 下载 gate 内访问远端 PDF。

    Args:
        discovery_client: 当前市场 downloader。
        pdf_download_gate: PDF 下载段 gate。
        candidate: 待下载候选。
        cancel_checker: 可选取消检查函数。

    Returns:
        已下载 PDF 资产。

    Raises:
        Exception: gate 获取、取消、主源下载或 PDF 校验失败时原样抛出。
    """

    with pdf_download_gate.lease_for_provider(candidate.provider, cancel_checker=cancel_checker):
        return discovery_client.download_report_pdf(candidate)


async def run_cn_download_single_filing_stream(
    *,
    source_repository: SourceDocumentRepositoryProtocol,
    blob_repository: DocumentBlobRepositoryProtocol,
    processed_repository: ProcessedDocumentRepositoryProtocol,
    discovery_client: CnReportDiscoveryClientProtocol,
    pdf_download_gate: CnDownloadPdfGateProtocol,
    convert_pdf_to_docling_json: Callable[[bytes, str], bytes],
    ticker: str,
    profile: CnCompanyProfile,
    candidate: CnReportCandidate,
    overwrite: bool,
    cancel_checker: Callable[[], bool] | None,
    module: str,
    batching_repository: BatchingRepositoryProtocol | None = None,
    preparation_gate: CnPreparationGate | None = None,
    provider_download_timeout_seconds: float = _DEFAULT_PROVIDER_DOWNLOAD_TIMEOUT_SECONDS,
) -> AsyncGenerator[DownloadEvent, None]:
    """执行单个 CN/HK filing 下载阶段机（S14-CTRL-12 三段边界）。

    阶段 A（provider download/request）：唯一 hard bounded，由
    ``provider_download_timeout_seconds`` 包裹 outer 等待（``asyncio.timeout``
    只取消 outer task，不取消 ``to_thread`` worker）；超时/outer cancel 时
    late result 禁止进入 B/C/repo。inner task / temp asset owner 与可选的
    容量 slot owner 分离（S14-RR-02）：无论是否注入 ``preparation_gate``，
    每个阶段 A/B 实际 inner future 都注册 late completion cleanup，outer
    提前放弃后由最后一个真实 inner 的 done callback 回收 exact 临时 PDF；
    有 gate 时该 callback 再额外在最后一个 inner 完成后恰好 release 一次
    slot，绝不提前释放；无 batch/token。

    阶段 B（preparation：``pdf_path.read_bytes`` 与默认/注入 Docling
    converter）：不纳入 hard timeout、不承诺 interruptible/最终有限结束；worker
    只接收 immutable/path input、零 repo/batch/token 句柄；临时 PDF 由
    ``_read_and_unlink_temp_pdf`` 唯一清理；outer cancel 不提前 release slot。

    阶段 C（repository transaction）：阶段 A/B 成功且 cancellation fence 通过
    后才 begin 同-core explicit batch，blob/meta 写在短事务窗口内；commit 前再查
    cancel_checker；commit-start 前失败/取消 rollback、commit-start 后只按
    S14-CTRL-04 journal/recovery 收敛。

    Args:
        source_repository: source 文档仓储。
        blob_repository: 文件对象仓储。
        processed_repository: processed 文档仓储。
        discovery_client: 当前市场 downloader。
        pdf_download_gate: PDF 下载段 gate。
        convert_pdf_to_docling_json: PDF -> Docling JSON 转换函数。
        ticker: 已归一化 ticker。
        profile: 公司基础元数据。
        candidate: 远端候选报告。
        overwrite: 是否强制覆盖；为 ``True`` 时禁止复用和 skip。
        cancel_checker: 可选取消检查函数。
        module: 日志模块名。
        batching_repository: 可选同-core 共享 batch 仓储（阶段 C 使用）。
        preparation_gate: 可选共享 CN/HK preparation gate（slot 先于阶段 A；
            无 gate 时 inner task / temp asset owner 仍生效，只回收 late 临时
            PDF，不持有容量 slot）。
        provider_download_timeout_seconds: 阶段 A 唯一 hard timeout。

    Yields:
        单 filing 的文件级与终态下载事件。``FILING_STARTED`` 由上层 workflow
        统一发出，本函数只发后续事件。

    Raises:
        CnDownloadFilingError: 仓储、下载或转换失败时抛出。
        CancelledError: 取消检查命中时抛出。
    """

    _raise_if_cancelled(module=module, ticker=ticker, document_id="", cancel_checker=cancel_checker)
    document_id, internal_document_id = build_cn_filing_ids(
        ticker=ticker,
        form_type=candidate.fiscal_period,
        fiscal_year=candidate.fiscal_year,
        fiscal_period=candidate.fiscal_period,
        amended=candidate.amended,
    )
    pdf_filename = f"{document_id}.pdf"
    docling_filename = f"{document_id}_docling.json"
    previous_meta = _safe_get_source_meta(
        source_repository=source_repository,
        ticker=ticker,
        document_id=document_id,
    )
    previous_completed_meta = _resolve_previous_completed_meta(
        previous_meta=previous_meta,
        overwrite=overwrite,
    )
    source_meta_exists = previous_meta is not None
    remote_fingerprint = build_remote_fingerprint(candidate)
    skip_result = _resolve_fast_skip_result(
        previous_meta=previous_meta,
        remote_fingerprint=remote_fingerprint,
        overwrite=overwrite,
        candidate=candidate,
    )
    if skip_result is not None:
        yield DownloadEvent(
            event_type=DownloadEventType.FILING_COMPLETED,
            ticker=ticker,
            document_id=document_id,
            payload={"filing_result": skip_result, **skip_result},
        )
        return

    # 只读解析阶段（阶段 A/B 前不写 repository；S3 读路径无需 token）。
    handle = None
    if previous_meta is not None:
        try:
            handle = source_repository.get_source_handle(ticker, document_id, SourceKind.FILING)
        except FileNotFoundError:
            handle = None
    reusable_pdf = None
    if handle is not None:
        reusable_pdf = _resolve_reusable_pdf(
            blob_repository=blob_repository,
            handle=handle,
            pdf_filename=pdf_filename,
            docling_filename=docling_filename,
            previous_meta=previous_meta,
            remote_fingerprint=remote_fingerprint,
            overwrite=overwrite,
        )

    # ========== 阶段 A：provider download（唯一 hard bounded；slot 先于 provider） ==========
    active_gate = preparation_gate
    slot_held = False
    if active_gate is not None:
        await active_gate.acquire()
        slot_held = True
    # slot 与阶段 A/B 各实际 inner future 绑定：outer 提前放弃（timeout/cancel/
    # 生成器关闭）时绝不提前 release，最后一个真实 inner 完成后才收敛释放。
    # inner task / temp asset owner 与可选的容量 slot owner 分离（S14-RR-02）：
    # 无论是否注入 gate，owner 都始终存在并承担 late inner 的 temp PDF cleanup。
    ownership = _PreparationInnerOwner(gate=active_gate)
    pdf_path: Path | None = None
    pdf_bytes: bytes | None = None
    try:
        # ========== 阶段 A：provider download（唯一 hard bounded） ==========
        try:
            if reusable_pdf is None:
                provider_inner = asyncio.create_task(
                    asyncio.to_thread(
                        _download_report_pdf_with_gate,
                        discovery_client=discovery_client,
                        pdf_download_gate=pdf_download_gate,
                        candidate=candidate,
                        cancel_checker=cancel_checker,
                    )
                )
                _bind_preparation_inner(
                    provider_inner,
                    ownership=ownership,
                    late_cleanup=_cleanup_late_provider_asset,
                    module=module,
                    ticker=ticker,
                    document_id=document_id,
                )
                try:
                    # shield 保护实际 inner future：outer timeout/cancel 只取消
                    # shield 包装与 outer 等待，绝不取消 provider worker
                    # （``Task.cancel`` 会级联取消 ``_fut_waiter``）。
                    async with asyncio.timeout(provider_download_timeout_seconds):
                        asset = await asyncio.shield(provider_inner)
                except asyncio.TimeoutError:
                    # 阶段 A hard timeout：只放弃 outer 等待，provider worker 继续
                    # 在后台运行；late result 禁止进入 B/C/repo，slot 由 inner
                    # 真正完成时的 done callback 收敛释放（无 gate 时只回收
                    # late temp PDF，S14-RR-02）。
                    ownership.abandoned = True
                    failed = _build_filing_result(
                        document_id=document_id,
                        status="failed",
                        candidate=candidate,
                        reason_code="pdf_download_failed",
                        reason_message="provider download timeout",
                        downloaded_files=0,
                        skipped_files=0,
                    )
                    yield DownloadEvent(
                        event_type=DownloadEventType.FILING_FAILED,
                        ticker=ticker,
                        document_id=document_id,
                        payload={"filing_result": failed, **failed},
                    )
                    return
                except asyncio.CancelledError:
                    # outer cancellation：不取消 provider worker、不提前释放 slot，
                    # 由最后一个真实 inner 完成后的 done callback 收敛。
                    ownership.abandoned = True
                    raise
                pdf_path = asset.pdf_path
                pdf_sha256 = asset.sha256
                reused_pdf = False
            else:
                pdf_bytes = reusable_pdf
                pdf_sha256 = _read_required_text(previous_meta, "staging_pdf_sha256")
                reused_pdf = True
        except CancelledError:
            # 自定义取消只可能来自已真实完成的 inner（cancel_checker 命中）。
            if slot_held:
                _release_preparation_slot(ownership)
                slot_held = False
            raise
        except Exception as exc:
            # provider inner 已真实完成（异常），此时释放 slot 是安全的。
            if slot_held:
                _release_preparation_slot(ownership)
                slot_held = False
            failed = _build_filing_result(
                document_id=document_id,
                status="failed",
                candidate=candidate,
                reason_code="pdf_download_failed",
                reason_message=str(exc),
                downloaded_files=0,
                skipped_files=0,
            )
            yield DownloadEvent(
                event_type=DownloadEventType.FILING_FAILED,
                ticker=ticker,
                document_id=document_id,
                payload={"filing_result": failed, **failed},
            )
            return

        # ========== 阶段 B：preparation（read_bytes + Docling，无 token，不纳入 hard timeout） ==========
        try:
            if not reused_pdf and pdf_path is not None:
                read_inner = asyncio.create_task(
                    asyncio.to_thread(_read_and_unlink_temp_pdf, pdf_path, module=module)
                )
                _bind_preparation_inner(
                    read_inner,
                    ownership=ownership,
                    late_cleanup=_noop_late_cleanup,
                    module=module,
                    ticker=ticker,
                    document_id=document_id,
                )
                try:
                    pdf_bytes = await asyncio.shield(read_inner)
                except asyncio.CancelledError:
                    ownership.abandoned = True
                    raise
                except Exception as read_error:
                    # read worker 已真实完成（异常），释放 slot 是安全的。
                    if slot_held:
                        _release_preparation_slot(ownership)
                        slot_held = False
                    failed = _build_filing_result(
                        document_id=document_id,
                        status="failed",
                        candidate=candidate,
                        reason_code="pdf_read_failed",
                        reason_message=str(read_error),
                        downloaded_files=0,
                        skipped_files=0,
                    )
                    yield DownloadEvent(
                        event_type=DownloadEventType.FILING_FAILED,
                        ticker=ticker,
                        document_id=document_id,
                        payload={"filing_result": failed, **failed},
                    )
                    return
            else:
                pdf_path = None
            assert pdf_bytes is not None
            # 阶段 B 复用判定只在存在 previous_meta 时进行（fresh doc 无 staging
            # meta 必然无复用对象，handle 由阶段 C 创建 staging meta 后取得）。
            if previous_meta is not None:
                if handle is None:
                    handle = source_repository.get_source_handle(ticker, document_id, SourceKind.FILING)
                if handle is not None and _can_skip_by_pdf_sha(
                    previous_meta=previous_meta,
                    overwrite=overwrite,
                    pdf_sha256=pdf_sha256,
                    blob_repository=blob_repository,
                    handle=handle,
                    docling_filename=docling_filename,
                ):
                    if slot_held:
                        _release_preparation_slot(ownership)
                        slot_held = False
                    if batching_repository is None:
                        _commit_skipped_cn_filing_source(
                            source_repository=source_repository,
                            processed_repository=processed_repository,
                            ticker=ticker,
                            document_id=document_id,
                            internal_document_id=internal_document_id,
                            form_type=candidate.fiscal_period,
                            candidate=candidate,
                            profile=profile,
                            pdf_sha256=pdf_sha256,
                            remote_fingerprint=remote_fingerprint,
                            previous_meta=previous_meta,
                            previous_completed_meta=previous_completed_meta,
                        )
                        skipped = _build_skipped_by_pdf_sha_result(document_id=document_id, candidate=candidate)
                        yield DownloadEvent(
                            event_type=DownloadEventType.FILING_COMPLETED,
                            ticker=ticker,
                            document_id=document_id,
                            payload={"filing_result": skipped, **skipped},
                        )
                        return
                    token = batching_repository.begin_batch(ticker)
                    finalization_started = False
                    try:
                        _commit_skipped_cn_filing_source(
                            source_repository=source_repository,
                            processed_repository=processed_repository,
                            ticker=ticker,
                            document_id=document_id,
                            internal_document_id=internal_document_id,
                            form_type=candidate.fiscal_period,
                            candidate=candidate,
                            profile=profile,
                            pdf_sha256=pdf_sha256,
                            remote_fingerprint=remote_fingerprint,
                            previous_meta=previous_meta,
                            previous_completed_meta=previous_completed_meta,
                        )
                        _raise_if_cancelled(
                            module=module,
                            ticker=ticker,
                            document_id=document_id,
                            cancel_checker=cancel_checker,
                        )
                        finalization_started = True
                        batching_repository.commit_batch(token)
                    except BaseException as exc:
                        if not finalization_started:
                            _rollback_batch_preserving_primary(
                                batching_repository,
                                token,
                                primary=exc,
                                ticker=ticker,
                                document_id=document_id,
                                module=module,
                            )
                        raise
                    skipped = _build_skipped_by_pdf_sha_result(document_id=document_id, candidate=candidate)
                    yield DownloadEvent(
                        event_type=DownloadEventType.FILING_COMPLETED,
                        ticker=ticker,
                        document_id=document_id,
                        payload={"filing_result": skipped, **skipped},
                    )
                    return
                reusable_docling = _resolve_reusable_docling(
                    blob_repository=blob_repository,
                    handle=handle,
                    docling_filename=docling_filename,
                    previous_meta=previous_meta,
                    remote_fingerprint=remote_fingerprint,
                    pdf_sha256=pdf_sha256,
                    overwrite=overwrite,
                )
            else:
                reusable_docling = None
            if reusable_docling is None:
                Log.info(
                    f"开始 Docling 转换: ticker={ticker} document_id={document_id} "
                    f"form={candidate.fiscal_period} filing_date={candidate.filing_date} "
                    f"source_file={pdf_filename} reused_pdf={reused_pdf}",
                    module=module,
                )
                docling_inner = asyncio.create_task(
                    asyncio.to_thread(
                        convert_pdf_to_docling_json,
                        pdf_bytes,
                        pdf_filename,
                    )
                )
                _bind_preparation_inner(
                    docling_inner,
                    ownership=ownership,
                    late_cleanup=_noop_late_cleanup,
                    module=module,
                    ticker=ticker,
                    document_id=document_id,
                )
                try:
                    docling_json_bytes = await asyncio.shield(docling_inner)
                except asyncio.CancelledError:
                    # outer cancellation：不取消 Docling worker、不提前释放 slot。
                    ownership.abandoned = True
                    raise
                except Exception as exc:
                    # Docling worker 已真实完成（异常），释放 slot 是安全的。
                    if slot_held:
                        _release_preparation_slot(ownership)
                        slot_held = False
                    failed = _build_filing_result(
                        document_id=document_id,
                        status="failed",
                        candidate=candidate,
                        reason_code="docling_convert_failed",
                        reason_message=str(exc),
                        downloaded_files=0 if reused_pdf else 1,
                        skipped_files=1 if reused_pdf else 0,
                    )
                    yield DownloadEvent(
                        event_type=DownloadEventType.FILING_FAILED,
                        ticker=ticker,
                        document_id=document_id,
                        payload={"filing_result": failed, **failed},
                    )
                    return
                reused_docling = False
                converted = True
            else:
                docling_json_bytes = reusable_docling
                reused_docling = True
                converted = False
            if slot_held:
                _release_preparation_slot(ownership)
                slot_held = False
        except CancelledError:
            if slot_held:
                _release_preparation_slot(ownership)
                slot_held = False
            raise
        except Exception as exc:
            if slot_held:
                _release_preparation_slot(ownership)
                slot_held = False
            failed = _build_filing_result(
                document_id=document_id,
                status="failed",
                candidate=candidate,
                reason_code="docling_convert_failed",
                reason_message=str(exc),
                downloaded_files=0 if reused_pdf else 1,
                skipped_files=1 if reused_pdf else 0,
            )
            yield DownloadEvent(
                event_type=DownloadEventType.FILING_FAILED,
                ticker=ticker,
                document_id=document_id,
                payload={"filing_result": failed, **failed},
            )
            return
    finally:
        # outer 提前放弃（timeout/cancel/生成器关闭/未捕获异常）且 slot 尚未
        # 释放时，标记 abandoned；由最后一个真实 inner 的 done callback 收敛
        # release，绝不提前释放、不泄漏 slot（无 gate 时只回收 late temp PDF）。
        if not ownership.released:
            ownership.abandoned = True

    # ========== 阶段 C：repository transaction（blob+meta 写在同一同-core explicit batch） ==========
    if batching_repository is None:
        # FS/local 模式：保留现有 auto-batch 语义，逐写走仓储自动 batch。
        yield DownloadEvent(
            event_type=DownloadEventType.FILE_DOWNLOADED,
            ticker=ticker,
            document_id=document_id,
            payload={
                "name": pdf_filename,
                "stage": "pdf_downloaded",
                "status": "skipped" if reused_pdf else "downloaded",
                "reused": reused_pdf,
                "reason_code": "local_pdf_reused" if reused_pdf else None,
            },
        )
        terminal = await _commit_cn_filing_fs_mode(
            source_repository=source_repository,
            blob_repository=blob_repository,
            processed_repository=processed_repository,
            ticker=ticker,
            document_id=document_id,
            internal_document_id=internal_document_id,
            pdf_filename=pdf_filename,
            docling_filename=docling_filename,
            pdf_bytes=pdf_bytes,
            pdf_sha256=pdf_sha256,
            docling_json_bytes=docling_json_bytes,
            reused_pdf=reused_pdf,
            reused_docling=reused_docling,
            candidate=candidate,
            profile=profile,
            remote_fingerprint=remote_fingerprint,
            previous_meta=previous_meta,
            previous_completed_meta=previous_completed_meta,
            source_meta_exists=source_meta_exists,
            overwrite=overwrite,
            module=module,
            cancel_checker=cancel_checker,
        )
        if terminal is None:
            return
        yield terminal
        return

    token = batching_repository.begin_batch(ticker)
    finalization_started = False
    try:
        if _should_reset_before_download(previous_meta=previous_meta, remote_fingerprint=remote_fingerprint, overwrite=overwrite):
            source_repository.reset_source_document(ticker, document_id, SourceKind.FILING)
            previous_meta = None
            previous_completed_meta = None
            source_meta_exists = False
        initial_file_entries = _read_file_entries(previous_meta) if previous_meta is not None else []
        update_cn_staging_source_document(
            source_repository=source_repository,
            ticker=ticker,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=candidate.fiscal_period,
            primary_document=pdf_filename,
            file_entries=initial_file_entries,
            candidate=candidate,
            profile=profile,
            pdf_sha256=pdf_sha256,
            remote_fingerprint=remote_fingerprint,
            previous_meta_exists=source_meta_exists,
        )
        handle = source_repository.get_source_handle(ticker, document_id, SourceKind.FILING)
        if reused_pdf:
            pdf_entry_meta = _find_file_meta(blob_repository=blob_repository, handle=handle, filename=pdf_filename)
        else:
            pdf_entry_meta = blob_repository.store_file(
                handle,
                pdf_filename,
                BytesIO(pdf_bytes),
                content_type=_PDF_CONTENT_TYPE,
                metadata={"source": _SOURCE_LABEL_ORIGINAL},
            )
        pdf_entry = build_cn_file_entry(
            filename=pdf_filename,
            file_meta=pdf_entry_meta,
            source_label=_SOURCE_LABEL_ORIGINAL,
        )
        docling_entry = build_cn_file_entry(
            filename=docling_filename,
            file_meta=_resolve_docling_file_meta(
                blob_repository=blob_repository,
                handle=handle,
                docling_filename=docling_filename,
                docling_json_bytes=docling_json_bytes,
                pdf_sha256=pdf_sha256,
                reused_docling=reused_docling,
            ),
            source_label=_SOURCE_LABEL_DOCLING,
        )
        update_cn_staging_source_document(
            source_repository=source_repository,
            ticker=ticker,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=candidate.fiscal_period,
            primary_document=pdf_filename,
            file_entries=[pdf_entry, docling_entry],
            candidate=candidate,
            profile=profile,
            pdf_sha256=pdf_sha256,
            remote_fingerprint=remote_fingerprint,
            previous_meta_exists=True,
        )
        yield DownloadEvent(
            event_type=DownloadEventType.FILE_DOWNLOADED,
            ticker=ticker,
            document_id=document_id,
            payload={
                "name": pdf_filename,
                "stage": "pdf_downloaded",
                "status": "skipped" if reused_pdf else "downloaded",
                "reused": reused_pdf,
                "reason_code": "local_pdf_reused" if reused_pdf else None,
            },
        )
        _raise_if_cancelled(module=module, ticker=ticker, document_id=document_id, cancel_checker=cancel_checker)
        source_fingerprint = build_content_fingerprint(
            pdf_bytes=pdf_bytes,
            docling_json_bytes=docling_json_bytes,
        )
        commit_cn_filing_source_document(
            source_repository=source_repository,
            processed_repository=processed_repository,
            ticker=ticker,
            document_id=document_id,
            internal_document_id=internal_document_id,
            form_type=candidate.fiscal_period,
            primary_document=docling_filename,
            file_entries=[pdf_entry, docling_entry],
            candidate=candidate,
            profile=profile,
            pdf_sha256=pdf_sha256,
            remote_fingerprint=remote_fingerprint,
            source_fingerprint=source_fingerprint,
            previous_completed_meta=previous_completed_meta,
            source_meta_exists=True,
        )
        _raise_if_cancelled(module=module, ticker=ticker, document_id=document_id, cancel_checker=cancel_checker)
        finalization_started = True
        batching_repository.commit_batch(token)
    except BaseException as exc:
        if not finalization_started:
            _rollback_batch_preserving_primary(
                batching_repository,
                token,
                primary=exc,
                ticker=ticker,
                document_id=document_id,
                module=module,
            )
        raise
    downloaded = _build_filing_result(
        document_id=document_id,
        status="downloaded",
        candidate=candidate,
        reason_code="download_committed",
        reason_message="PDF 与 Docling JSON 已完成落盘并提交 source meta",
        downloaded_files=(0 if reused_pdf else 1) + (0 if reused_docling else 1),
        skipped_files=(1 if reused_pdf else 0) + (1 if reused_docling else 0),
    )
    downloaded["reused_pdf"] = reused_pdf
    downloaded["reused_docling"] = reused_docling
    downloaded["converted"] = converted
    yield DownloadEvent(
        event_type=DownloadEventType.FILING_COMPLETED,
        ticker=ticker,
        document_id=document_id,
        payload={"filing_result": downloaded, **downloaded},
    )

async def _commit_cn_filing_fs_mode(
    *,
    source_repository: SourceDocumentRepositoryProtocol,
    blob_repository: DocumentBlobRepositoryProtocol,
    processed_repository: ProcessedDocumentRepositoryProtocol,
    ticker: str,
    document_id: str,
    internal_document_id: str,
    pdf_filename: str,
    docling_filename: str,
    pdf_bytes: bytes,
    pdf_sha256: str,
    docling_json_bytes: bytes,
    reused_pdf: bool,
    reused_docling: bool,
    candidate: CnReportCandidate,
    profile: CnCompanyProfile,
    remote_fingerprint: str,
    previous_meta: JsonObject | None,
    previous_completed_meta: JsonObject | None,
    source_meta_exists: bool,
    overwrite: bool,
    module: str,
    cancel_checker: Callable[[], bool] | None,
) -> DownloadEvent | None:
    """FS/local 模式提交 CN 单 filing（保留现有 auto-batch 语义）。

    Args:
        source_repository: source 文档仓储。
        blob_repository: 文件对象仓储。
        processed_repository: processed 文档仓储。
        handle: source document 句柄。
        ticker: 已归一化 ticker。
        document_id: 文档 ID。
        internal_document_id: 内部文档 ID。
        pdf_filename: PDF 文件名。
        docling_filename: Docling JSON 文件名。
        pdf_bytes: PDF 字节。
        pdf_sha256: PDF SHA-256。
        docling_json_bytes: Docling JSON 字节。
        reused_pdf: PDF 是否复用。
        reused_docling: Docling JSON 是否复用。
        candidate: 远端候选。
        profile: 公司基础元数据。
        remote_fingerprint: 远端 fingerprint。
        previous_meta: 既有 meta。
        previous_completed_meta: 上一版完成态 meta。
        source_meta_exists: source meta 是否已存在。
        overwrite: 是否强制覆盖。
        module: 日志模块名。
        cancel_checker: 取消检查函数。

    Returns:
        FILING_COMPLETED 事件；写入失败/取消时返回 ``None``（调用方终止）。

    Raises:
        CancelledError: 取消检查命中时抛出。
    """

    if _should_reset_before_download(previous_meta=previous_meta, remote_fingerprint=remote_fingerprint, overwrite=overwrite):
        source_repository.reset_source_document(ticker, document_id, SourceKind.FILING)
        previous_meta = None
        previous_completed_meta = None
        source_meta_exists = False
    initial_file_entries = _read_file_entries(previous_meta) if previous_meta is not None else []
    update_cn_staging_source_document(
        source_repository=source_repository,
        ticker=ticker,
        document_id=document_id,
        internal_document_id=internal_document_id,
        form_type=candidate.fiscal_period,
        primary_document=pdf_filename,
        file_entries=initial_file_entries,
        candidate=candidate,
        profile=profile,
        pdf_sha256=pdf_sha256,
        remote_fingerprint=remote_fingerprint,
        previous_meta_exists=source_meta_exists,
    )
    handle = source_repository.get_source_handle(ticker, document_id, SourceKind.FILING)
    if reused_pdf:
        pdf_entry_meta = _find_file_meta(blob_repository=blob_repository, handle=handle, filename=pdf_filename)
    else:
        pdf_entry_meta = blob_repository.store_file(
            handle,
            pdf_filename,
            BytesIO(pdf_bytes),
            content_type=_PDF_CONTENT_TYPE,
            metadata={"source": _SOURCE_LABEL_ORIGINAL},
        )
    pdf_entry = build_cn_file_entry(
        filename=pdf_filename,
        file_meta=pdf_entry_meta,
        source_label=_SOURCE_LABEL_ORIGINAL,
    )
    docling_entry = build_cn_file_entry(
        filename=docling_filename,
        file_meta=_resolve_docling_file_meta(
            blob_repository=blob_repository,
            handle=handle,
            docling_filename=docling_filename,
            docling_json_bytes=docling_json_bytes,
            pdf_sha256=pdf_sha256,
            reused_docling=reused_docling,
        ),
        source_label=_SOURCE_LABEL_DOCLING,
    )
    update_cn_staging_source_document(
        source_repository=source_repository,
        ticker=ticker,
        document_id=document_id,
        internal_document_id=internal_document_id,
        form_type=candidate.fiscal_period,
        primary_document=pdf_filename,
        file_entries=[pdf_entry, docling_entry],
        candidate=candidate,
        profile=profile,
        pdf_sha256=pdf_sha256,
        remote_fingerprint=remote_fingerprint,
        previous_meta_exists=True,
    )
    _raise_if_cancelled(module=module, ticker=ticker, document_id=document_id, cancel_checker=cancel_checker)
    source_fingerprint = build_content_fingerprint(
        pdf_bytes=pdf_bytes,
        docling_json_bytes=docling_json_bytes,
    )
    commit_cn_filing_source_document(
        source_repository=source_repository,
        processed_repository=processed_repository,
        ticker=ticker,
        document_id=document_id,
        internal_document_id=internal_document_id,
        form_type=candidate.fiscal_period,
        primary_document=docling_filename,
        file_entries=[pdf_entry, docling_entry],
        candidate=candidate,
        profile=profile,
        pdf_sha256=pdf_sha256,
        remote_fingerprint=remote_fingerprint,
        source_fingerprint=source_fingerprint,
        previous_completed_meta=previous_completed_meta,
        source_meta_exists=True,
    )
    downloaded = _build_filing_result(
        document_id=document_id,
        status="downloaded",
        candidate=candidate,
        reason_code="download_committed",
        reason_message="PDF 与 Docling JSON 已完成落盘并提交 source meta",
        downloaded_files=(0 if reused_pdf else 1) + (0 if reused_docling else 1),
        skipped_files=(1 if reused_pdf else 0) + (1 if reused_docling else 0),
    )
    downloaded["reused_pdf"] = reused_pdf
    downloaded["reused_docling"] = reused_docling
    downloaded["converted"] = not reused_docling
    return DownloadEvent(
        event_type=DownloadEventType.FILING_COMPLETED,
        ticker=ticker,
        document_id=document_id,
        payload={"filing_result": downloaded, **downloaded},
    )


def _resolve_docling_file_meta(
    *,
    blob_repository: DocumentBlobRepositoryProtocol,
    handle: SourceHandle,
    docling_filename: str,
    docling_json_bytes: bytes,
    pdf_sha256: str,
    reused_docling: bool,
) -> FileObjectMeta:
    """解析 Docling JSON 文件元数据（复用或新写入）。

    Args:
        blob_repository: blob 仓储。
        handle: source document 句柄。
        docling_filename: Docling JSON 文件名。
        docling_json_bytes: Docling JSON 字节。
        pdf_sha256: PDF SHA-256。
        reused_docling: 是否复用已存在对象。

    Returns:
        文件对象元数据。

    Raises:
        OSError: 底层 blob 读取或写入失败时抛出。
    """

    if reused_docling:
        try:
            return _find_file_meta(
                blob_repository=blob_repository,
                handle=handle,
                filename=docling_filename,
            )
        except FileNotFoundError:
            # Docling blob 已落盘但 meta.files 未列出（crash 恢复场景）：
            # 用复用 bytes 幂等重写，补回 meta 条目。
            pass
    return blob_repository.store_file(
        handle,
        docling_filename,
        BytesIO(docling_json_bytes),
        content_type=_JSON_CONTENT_TYPE,
        metadata={"source": _SOURCE_LABEL_DOCLING, "pdf_sha256": pdf_sha256},
    )


def _release_preparation_slot(ownership: _PreparationInnerOwner) -> None:
    """释放 preparation gate slot（无 gate 时为空操作；恰好释放一次）。

    Args:
        ownership: 共享所有权状态（无 gate 时 release 为空操作）。

    Returns:
        无。

    Raises:
        RuntimeError: gate 无 active slot 可释放时抛出。
    """

    ownership.release()


@dataclass
class _PreparationInnerOwner:
    """CN/HK 阶段 A/B 实际 inner future 的共享所有权状态（与可选容量 slot 分离）。

    inner task / temp asset owner 与可选的容量 slot owner 分离（S14-RR-02）：
    无论是否注入 ``preparation_gate``，每个阶段 A/B 实际 inner future 都绑定
    本 owner；``pending_inner`` 统计尚未完成（含异常）的 inner future 数，
    ``abandoned`` 表示 outer 已提前放弃（阶段 A timeout / outer cancel /
    生成器提前关闭），``released`` 保证容量 slot（存在时）恰好释放一次。
    无 gate 时本对象仍承担 late inner 的 temp asset cleanup owner，但不持有
    任何容量 slot。正常路径由阶段 B 结束时显式 ``release()``（无 gate 时为
    空操作），提前放弃路径由最后一个 inner 的 done callback 收敛。
    """

    gate: CnPreparationGate | None = None
    pending_inner: int = 0
    abandoned: bool = False
    released: bool = False

    def release(self) -> None:
        """释放容量 slot（幂等恰好一次；无 gate 时为空操作）。

        Args:
            无。

        Returns:
            无。

        Raises:
            RuntimeError: gate 无 active slot 可释放时抛出。
        """

        if self.released or self.gate is None:
            return
        self.released = True
        self.gate.release()


def _bind_preparation_inner(
    inner: asyncio.Task[_InnerTaskT],
    *,
    ownership: _PreparationInnerOwner,
    late_cleanup: Callable[[asyncio.Task[_InnerTaskT], str], None],
    module: str,
    ticker: str,
    document_id: str,
) -> None:
    """把阶段 A/B 实际 inner future 与 late cleanup 及可选容量 slot 绑定。

    inner task / temp asset owner 与可选的容量 slot owner 分离（S14-RR-02）：
    无论是否注入 ``preparation_gate``，每个阶段 A/B 实际 inner future 都注册
    done callback；outer 提前放弃（阶段 A timeout / outer cancel）时绝不提前
    释放 slot，也不取消 inner，最后一个真实 inner 完成（含异常）时由 done
    callback 执行 late 清理（如 unlink 临时 PDF）；有 gate 时再额外恰好
    release 一次（S14-CR-02）。正常路径（``abandoned=False``）不触发
    release，由阶段 B 结束后显式释放。

    Args:
        inner: 阶段 A/B 的实际 inner task。
        ownership: 共享所有权状态。
        late_cleanup: inner 完成时执行的 late 清理（如 unlink 临时 PDF）。
        module: 日志模块名。
        ticker: 股票代码。
        document_id: 文档 ID。

    Returns:
        无。

    Raises:
        无。
    """

    ownership.pending_inner += 1

    def _on_inner_done(task: asyncio.Task[_InnerTaskT]) -> None:
        ownership.pending_inner -= 1
        if not ownership.abandoned or ownership.released:
            return
        if ownership.pending_inner > 0:
            return
        try:
            late_cleanup(task, module)
        finally:
            _release_preparation_slot(ownership)
            Log.warn(
                f"CN/HK preparation 后台 inner 已收敛 slot: "
                f"ticker={ticker} document_id={document_id}",
                module=module,
            )

    inner.add_done_callback(_on_inner_done)


def _cleanup_late_provider_asset(task: asyncio.Task[_InnerTaskT], module: str) -> None:
    """late provider 完成时只做 exact 临时 PDF 清理（禁止进入 B/C/repo）。

    Args:
        task: 已完成的阶段 A inner task。
        module: 日志模块名。

    Returns:
        无。

    Raises:
        无。
    """

    if task.cancelled() or task.exception() is not None:
        return
    asset = task.result()
    if isinstance(asset, DownloadedReportAsset):
        _unlink_temp_pdf(asset.pdf_path, module=module)


def _noop_late_cleanup(task: asyncio.Task[_InnerTaskT], module: str) -> None:
    """late inner 完成时无需额外清理的 no-op。

    Args:
        task: 已完成的 inner task。
        module: 日志模块名。

    Returns:
        无。

    Raises:
        无。
    """

    del task, module


def _commit_skipped_cn_filing_source(
    *,
    source_repository: SourceDocumentRepositoryProtocol,
    processed_repository: ProcessedDocumentRepositoryProtocol,
    ticker: str,
    document_id: str,
    internal_document_id: str,
    form_type: str,
    candidate: CnReportCandidate,
    profile: CnCompanyProfile,
    pdf_sha256: str,
    remote_fingerprint: str,
    previous_meta: JsonObject | None,
    previous_completed_meta: JsonObject | None,
) -> None:
    """pdf_sha 命中 skip 时提交既有完成态 meta（S14-CTRL-12 skip 语义）。

    Args:
        source_repository: source 文档仓储。
        processed_repository: processed 文档仓储。
        ticker: 已归一化 ticker。
        document_id: 文档 ID。
        internal_document_id: 内部文档 ID。
        form_type: 文档 form_type。
        candidate: 远端候选。
        profile: 公司基础元数据。
        pdf_sha256: PDF SHA-256。
        remote_fingerprint: 远端 fingerprint。
        previous_meta: 既有 meta。
        previous_completed_meta: 上一版完成态 meta。

    Returns:
        无。

    Raises:
        CnDownloadFilingError: 既有 meta 缺字段时抛出。
        OSError: 仓储写入失败时抛出。
    """

    commit_cn_filing_source_document(
        source_repository=source_repository,
        processed_repository=processed_repository,
        ticker=ticker,
        document_id=document_id,
        internal_document_id=internal_document_id,
        form_type=form_type,
        primary_document=_read_required_text(previous_meta, "primary_document"),
        file_entries=_read_file_entries(previous_meta),
        candidate=candidate,
        profile=profile,
        pdf_sha256=pdf_sha256,
        remote_fingerprint=remote_fingerprint,
        source_fingerprint=_read_required_text(previous_meta, "source_fingerprint"),
        previous_completed_meta=previous_completed_meta,
        source_meta_exists=True,
    )


def _build_skipped_by_pdf_sha_result(*, document_id: str, candidate: CnReportCandidate) -> JsonObject:
    """构建 pdf_sha256 匹配的 skipped 结果。

    Args:
        document_id: 文档 ID。
        candidate: 远端候选。

    Returns:
        skipped filing 结果。

    Raises:
        无。
    """

    skipped = _build_filing_result(
        document_id=document_id,
        status="skipped",
        candidate=candidate,
        reason_code="pdf_sha256_matched",
        reason_message="PDF 内容与完成态一致且 Docling JSON 存在，跳过重新处理",
        downloaded_files=0,
        skipped_files=2,
    )
    return skipped


def _safe_get_source_meta(
    *,
    source_repository: SourceDocumentRepositoryProtocol,
    ticker: str,
    document_id: str,
) -> JsonObject | None:
    """安全读取 source meta。"""

    try:
        meta = source_repository.get_source_meta(ticker, document_id, SourceKind.FILING)
    except FileNotFoundError:
        return None
    return {str(key): _coerce_json_value(value) for key, value in meta.items()}


def _resolve_fast_skip_result(
    *,
    previous_meta: JsonObject | None,
    remote_fingerprint: str,
    overwrite: bool,
    candidate: CnReportCandidate,
) -> JsonObject | None:
    """判断是否可在下载 PDF 前 fast skip。"""

    if overwrite or previous_meta is None:
        return None
    if previous_meta.get("ingest_complete") is not True:
        return None
    if previous_meta.get("download_version") != CN_PIPELINE_DOWNLOAD_VERSION:
        return None
    if previous_meta.get("remote_fingerprint") != remote_fingerprint:
        return None
    return {
        "document_id": str(previous_meta.get("document_id") or ""),
        "status": "skipped",
        "form_type": str(previous_meta.get("form_type") or ""),
        "filing_date": str(previous_meta.get("filing_date") or ""),
        "report_date": None,
        "fiscal_year": candidate.fiscal_year,
        "fiscal_period": candidate.fiscal_period,
        "source_id": candidate.source_id,
        "downloaded_files": 0,
        "skipped_files": 2,
        "reason_code": "remote_fingerprint_matched",
        "reason_message": "远端 fingerprint 与本地完成态一致，跳过下载",
        "skip_reason": "remote_fingerprint_matched",
    }


def _resolve_previous_completed_meta(
    *,
    previous_meta: JsonObject | None,
    overwrite: bool,
) -> JsonObject | None:
    """解析可用于版本计算的上一版完成态 meta。

    Args:
        previous_meta: 当前 source meta。
        overwrite: 是否强制覆盖。

    Returns:
        可用于版本计算和审计字段保留的完成态 meta；不存在时返回 ``None``。

    Raises:
        无。
    """

    if overwrite or previous_meta is None:
        return None
    if previous_meta.get("ingest_complete") is not True:
        return None
    return previous_meta


def _should_reset_before_download(
    *,
    previous_meta: JsonObject | None,
    remote_fingerprint: str,
    overwrite: bool,
) -> bool:
    """判断进入下载分支前是否应 reset 单个 source document。"""

    if overwrite or previous_meta is None:
        return False
    if previous_meta.get("ingest_complete") is True:
        return False
    return previous_meta.get("staging_remote_fingerprint") != remote_fingerprint


def _resolve_reusable_pdf(
    *,
    blob_repository: DocumentBlobRepositoryProtocol,
    handle: SourceHandle,
    pdf_filename: str,
    docling_filename: str,
    previous_meta: JsonObject | None,
    remote_fingerprint: str,
    overwrite: bool,
) -> bytes | None:
    """判断中间态 PDF 是否可复用。"""

    if overwrite or previous_meta is None:
        return None
    if previous_meta.get("ingest_complete") is not False:
        return None
    if previous_meta.get("staging_remote_fingerprint") != remote_fingerprint:
        return None
    expected_sha = _optional_text(previous_meta.get("staging_pdf_sha256"))
    staged = inspect_staged_blobs(
        blob_repository=blob_repository,
        handle=handle,
        pdf_filename=pdf_filename,
        docling_filename=docling_filename,
        expected_pdf_sha256=expected_sha,
    )
    return staged.pdf_bytes if staged.pdf_sha256_matched else None


def _resolve_reusable_docling(
    *,
    blob_repository: DocumentBlobRepositoryProtocol,
    handle: SourceHandle,
    docling_filename: str,
    previous_meta: JsonObject | None,
    remote_fingerprint: str,
    pdf_sha256: str,
    overwrite: bool,
) -> bytes | None:
    """判断中间态 Docling JSON 是否可复用。

    Args:
        blob_repository: blob 仓储。
        handle: source document 句柄。
        docling_filename: Docling JSON 文件名。
        previous_meta: 当前 source meta。
        remote_fingerprint: 当前候选远端 fingerprint。
        pdf_sha256: 当前 PDF 字节 SHA-256。
        overwrite: 是否强制覆盖。

    Returns:
        可复用 Docling JSON 字节；不可复用时返回 ``None``。

    Raises:
        OSError: 底层 blob 读取失败时抛出。
    """

    if overwrite or previous_meta is None:
        return None
    if previous_meta.get("ingest_complete") is not False:
        return None
    if previous_meta.get("staging_remote_fingerprint") != remote_fingerprint:
        return None
    if previous_meta.get("staging_pdf_sha256") != pdf_sha256:
        return None
    try:
        return blob_repository.read_file_bytes(handle, docling_filename)
    except FileNotFoundError:
        return None


def _can_skip_by_pdf_sha(
    *,
    previous_meta: JsonObject | None,
    overwrite: bool,
    pdf_sha256: str,
    blob_repository: DocumentBlobRepositoryProtocol,
    handle: SourceHandle,
    docling_filename: str,
) -> bool:
    """判断完成态 PDF 内容未变时是否可跳过。"""

    if overwrite or previous_meta is None:
        return False
    if previous_meta.get("ingest_complete") is not True:
        return False
    if previous_meta.get("download_version") != CN_PIPELINE_DOWNLOAD_VERSION:
        return False
    if previous_meta.get("pdf_sha256") != pdf_sha256:
        return False
    return has_blob_file(blob_repository=blob_repository, handle=handle, filename=docling_filename)


def _find_file_meta(
    *,
    blob_repository: DocumentBlobRepositoryProtocol,
    handle: SourceHandle,
    filename: str,
) -> FileObjectMeta:
    """从 blob 仓储中查找指定文件元数据。"""

    for item in blob_repository.list_files(handle):
        if item.uri.rsplit("/", 1)[-1] == filename:
            return item
    raise FileNotFoundError(f"文件不存在: {filename}")


def _read_file_entries(meta: JsonObject | None) -> list[JsonObject]:
    """读取完成态 meta 中的文件条目。

    Args:
        meta: source meta。

    Returns:
        可传给 source upsert 的文件条目列表。

    Raises:
        CnDownloadFilingError: meta 缺失或 ``files`` 字段不是对象列表时抛出。
    """

    if meta is None:
        raise CnDownloadFilingError("缺少 source meta，无法读取 files")
    raw_files = meta.get("files")
    if not isinstance(raw_files, list):
        raise CnDownloadFilingError("source meta.files 必须为 list")
    entries: list[JsonObject] = []
    for raw_item in raw_files:
        if not isinstance(raw_item, dict):
            raise CnDownloadFilingError("source meta.files 条目必须为 object")
        entries.append({str(key): _coerce_json_value(value) for key, value in raw_item.items()})
    return entries


def _build_filing_result(
    *,
    document_id: str,
    status: str,
    candidate: CnReportCandidate,
    reason_code: str,
    reason_message: str,
    downloaded_files: int,
    skipped_files: int,
) -> JsonObject:
    """构建单 filing 结果 payload。"""

    payload: JsonObject = {
        "document_id": document_id,
        "status": status,
        "form_type": candidate.fiscal_period,
        "filing_date": candidate.filing_date,
        "report_date": None,
        "fiscal_year": candidate.fiscal_year,
        "fiscal_period": candidate.fiscal_period,
        "source_id": candidate.source_id,
        "downloaded_files": downloaded_files,
        "skipped_files": skipped_files,
        "failed_files": [],
        "has_xbrl": False,
        "reason_code": reason_code,
        "reason_message": reason_message,
    }
    if status == "skipped":
        payload["skip_reason"] = reason_code
    return payload


def _read_required_text(meta: JsonObject | None, key: str) -> str:
    """读取必填文本 meta 字段。"""

    if meta is None:
        raise CnDownloadFilingError(f"缺少 source meta，无法读取 {key}")
    value = _optional_text(meta.get(key))
    if value is None:
        raise CnDownloadFilingError(f"source meta 缺少 {key}")
    return value


def _optional_text(value: JsonValue) -> str | None:
    """把值收窄为非空字符串。"""

    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _coerce_json_value(value: JsonValue) -> JsonValue:
    """把仓储 meta 值收窄到 JSON 值。

    Args:
        value: 仓储 meta 中的单个值。

    Returns:
        JSON 值；非 JSON 类型按字符串保存。

    Raises:
        无。
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_coerce_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _coerce_json_value(item) for key, item in value.items()}
    return str(value)


def _unlink_temp_pdf(path: Path, *, module: str) -> None:
    """删除 downloader 暂存 PDF。"""

    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        Log.warn(f"删除临时 PDF 失败: path={path} error={exc}", module=module)


def _raise_if_cancelled(
    *,
    module: str,
    ticker: str,
    document_id: str,
    cancel_checker: Callable[[], bool] | None,
) -> None:
    """在阶段边界检查取消请求。"""

    if cancel_checker is None or not cancel_checker():
        return
    Log.info(
        f"CN/HK 下载收到取消请求: ticker={ticker} document_id={document_id}",
        module=module,
    )
    raise CancelledError("操作已被取消")


def sweep_stale_temp_pdfs(*, module: str) -> int:
    """启动期清理 owned stale 临时 PDF（bounded startup sweep）。

    只限 ``{tempdir}/dayu_cn_downloads/cninfo_*.pdf`` 与
    ``{tempdir}/dayu_hk_downloads/hkexnews_*.pdf``，只删 regular 非 symlink 且
    mtime 早于模块级有限 stale 阈值的文件；unknown/symlink/lock busy
    fail-safe 不删并记 metrics；禁止广泛 temp sweep。sweep 不触碰
    repository/batch/token。

    Args:
        module: 日志模块名。

    Returns:
        实际删除的 owned stale 文件数量。

    Raises:
        无（删除失败只记录日志）。
    """

    import tempfile
    import time

    removed = 0
    for temp_dir_name, prefix in (
        ("dayu_cn_downloads", "cninfo_"),
        ("dayu_hk_downloads", "hkexnews_"),
    ):
        temp_dir = Path(tempfile.gettempdir()) / temp_dir_name
        if not temp_dir.is_dir():
            continue
        for candidate in temp_dir.iterdir():
            try:
                if not candidate.is_file() or candidate.is_symlink():
                    Log.debug(
                        f"skip temp sweep non-regular: path={candidate}",
                        module=module,
                    )
                    continue
                if not candidate.name.endswith(".pdf") or not candidate.name.startswith(prefix):
                    continue
                if time.time() - candidate.stat().st_mtime < _CN_TEMP_PDF_STALE_SECONDS:
                    continue
                candidate.unlink()
                removed += 1
            except OSError as exc:
                Log.warn(
                    f"temp sweep skip lock busy/unknown: path={candidate} error={exc}",
                    module=module,
                )
                continue
    if removed:
        Log.info(f"startup stale-temp sweep 清理: removed={removed}", module=module)
    return removed


__all__ = [
    "CnDownloadFilingError",
    "run_cn_download_single_filing_stream",
    "sweep_stale_temp_pdfs",
]
