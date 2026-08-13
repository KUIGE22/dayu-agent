"""SecPipeline 下载工作流模块。"""

from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import time
from collections.abc import AsyncGenerator
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Protocol, TypeVar

from dayu.fins.domain.document_models import BatchToken
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    FilingMaintenanceRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.log import Log

_DEFAULT_PROVIDER_DOWNLOAD_TIMEOUT_SECONDS = 300.0
"""SEC/CN 阶段 A（provider download/request）的默认 hard timeout 秒数。"""
_SEC_FILING_CLOSE_TASK_NAME = "fins-sec-filing-inner-close"


class _FilingTerminalState(Enum):
    """单个 filing 的 terminal outcome（S14-CTRL-12 per-filing terminal 状态机）。"""

    PENDING = "pending"
    FILING_COMPLETED = "filing_completed"
    FILING_FAILED = "filing_failed"


class _DownloadWorkflowDownloader(Protocol):
    """下载工作流所需的最小下载器边界。"""

    def configure(self, user_agent: Optional[str], sleep_seconds: float, max_retries: int) -> None:
        """配置下载器。"""

        ...

    def normalize_ticker(self, ticker: str) -> str:
        """标准化 ticker。"""

        ...

    def resolve_company(self, ticker: str) -> Awaitable[tuple[str, str, str]] | tuple[str, str, str]:
        """解析公司信息。"""

        ...

    def fetch_submissions(self, cik10: str) -> Awaitable[dict[str, Any]] | dict[str, Any]:
        """拉取 submissions。"""

        ...


class SecDownloadWorkflowHost(Protocol):
    """Sec download 工作流所需的最小宿主边界。"""

    @property
    def MODULE(self) -> str:
        """返回日志模块名。"""

        ...

    @property
    def _downloader(self) -> _DownloadWorkflowDownloader:
        """返回下载器实例。"""

        ...

    @property
    def _user_agent(self) -> Optional[str]:
        """返回 User-Agent。"""

        ...

    @property
    def _sleep_seconds(self) -> float:
        """返回下载间隔秒数。"""

        ...

    @property
    def _max_retries(self) -> int:
        """返回最大重试次数。"""

        ...

    @property
    def _filing_maintenance_repository(self) -> FilingMaintenanceRepositoryProtocol:
        """返回 filing 维护仓储。"""

        ...

    @property
    def _source_repository(self) -> SourceDocumentRepositoryProtocol:
        """返回 source 仓储。"""

        ...

    @property
    def batching_repository(self) -> BatchingRepositoryProtocol | None:
        """返回同-core 共享 batch 仓储（可能为 None）。

        Args:
            无。

        Returns:
            runtime 注入的 batch 仓储实例；standalone/FS 路径下为 ``None``。

        Raises:
            无。
        """

        ...

    def _rebuild_download_artifacts(
        self,
        *,
        ticker: str,
        form_type: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        overwrite: bool,
    ) -> dict[str, Any]:
        """基于本地已下载 filings 重建 meta/manifest。"""

        ...

    def _resolve_form_windows(
        self,
        form_type: Optional[str],
        start_date: Optional[str],
        end_date: dt.date,
    ) -> dict[str, dt.date]:
        """计算 form 到起始日期映射。"""

        ...

    def _upsert_company_meta(
        self,
        ticker: str,
        company_id: str,
        company_name: str,
        ticker_aliases: Optional[list[str]],
    ) -> None:
        """写入公司元数据。"""

        ...

    def _build_result(self, action: str, **payload: Any) -> dict[str, Any]:
        """构建统一结果。"""

        ...

    def _log_filing_download_result(self, ticker: str, filing_result: dict[str, Any]) -> None:
        """记录单个 filing 下载结果。"""

        ...

    def _download_single_filing_stream(
        self,
        *,
        ticker: str,
        cik: str,
        filing: Any,
        overwrite: bool,
        rejection_registry: dict[str, dict[str, str]],
    ) -> AsyncGenerator[DownloadEvent, None]:
        """执行单 filing 下载流。"""

        ...

    def _filter_filings(
        self,
        *,
        ticker: str,
        submissions: dict[str, Any],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        sc13_direction_cache: Optional[dict[str, Optional[bool]]] = None,
        rejection_registry: Optional[dict[str, dict[str, str]]] = None,
        overwrite: bool = False,
    ) -> Awaitable[tuple[list[Any], set[str]]]:
        """过滤 filings 并收集 filenum。"""

        ...

    def _extend_with_browse_edgar_sc13(
        self,
        *,
        ticker: str,
        filings: list[Any],
        filenums: set[str],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        sc13_direction_cache: Optional[dict[str, Optional[bool]]] = None,
        rejection_registry: Optional[dict[str, dict[str, str]]] = None,
        overwrite: bool = False,
    ) -> Awaitable[list[Any]]:
        """补充 browse-edgar SC13 filings。"""

        ...

    def _retry_sc13_if_empty(
        self,
        *,
        ticker: str,
        filings: list[Any],
        filenums: set[str],
        submissions: dict[str, Any],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        sc13_direction_cache: Optional[dict[str, Optional[bool]]] = None,
        rejection_registry: Optional[dict[str, dict[str, str]]] = None,
        overwrite: bool = False,
    ) -> Awaitable[list[Any]]:
        """在 SC13 为空时执行渐进式回溯。"""

        ...


_AwaitableResult = TypeVar("_AwaitableResult")


async def _maybe_await(value: Awaitable[_AwaitableResult] | _AwaitableResult) -> _AwaitableResult:
    """按需等待可等待对象。"""

    if inspect.isawaitable(value):
        return await value
    return value


def _rollback_batch_preserving_primary(
    batching: BatchingRepositoryProtocol,
    token: BatchToken,
    *,
    primary: BaseException,
    ticker: str,
    document_id: str,
    module: str,
) -> None:
    """在已有主异常时尽力回滚且不让清理失败遮蔽主异常。

    Args:
        batching: 当前 batch 仓储。
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
        batching.rollback_batch(token)
    except BaseException as rollback_error:
        try:
            primary.add_note(
                f"rollback_batch failed: {type(rollback_error).__name__}: {rollback_error}"
            )
        except BaseException:
            pass
        try:
            Log.warn(
                f"SEC per-filing rollback 失败: ticker={ticker} document_id={document_id} error={rollback_error}",
                module=module,
            )
        except BaseException:
            pass


async def _capture_filing_close_error(
    inner: AsyncGenerator[DownloadEvent, None],
) -> BaseException | None:
    """在独立 owner task 内关闭 SEC filing inner 并把异常作为值返回。

    Args:
        inner: SEC market owner 直接拥有的 filing 事件流。

    Returns:
        关闭成功时返回 ``None``，否则返回原始 ``BaseException``。

    Raises:
        无；所有关闭终态均交由 market owner 统一仲裁。
    """

    try:
        await inner.aclose()
    except BaseException as exc:
        return exc
    return None


async def _await_owned_filing_close(
    inner: AsyncGenerator[DownloadEvent, None],
) -> tuple[BaseException | None, asyncio.CancelledError | None]:
    """以唯一独立 task 关闭 filing inner，并在重复取消下完整 reap。

    Args:
        inner: SEC market owner 直接拥有的 filing 事件流。

    Returns:
        ``(关闭自身异常, 等待期首个外层取消)``。

    Raises:
        无；关闭 task 必须终止并读取结果后才返回。
    """

    close_task = asyncio.create_task(
        _capture_filing_close_error(inner),
        name=_SEC_FILING_CLOSE_TASK_NAME,
    )
    cleanup_wait_cancel: asyncio.CancelledError | None = None
    while not close_task.done():
        try:
            await asyncio.shield(close_task)
        except asyncio.CancelledError as exc:
            if cleanup_wait_cancel is None:
                cleanup_wait_cancel = exc
    return close_task.result(), cleanup_wait_cancel


def _filing_error_priority(error: BaseException) -> int:
    """返回 SEC filing stream 异常的固定仲裁优先级。

    Args:
        error: body、close 或 cleanup-wait 观察到的异常。

    Returns:
        数值越小优先级越高的闭合等级。

    Raises:
        无。
    """

    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        return 0
    if isinstance(error, asyncio.CancelledError):
        return 1
    if not isinstance(error, Exception):
        return 2
    return 3


def _arbitrate_filing_stream_errors(
    body_error: BaseException | None,
    close_error: BaseException | None,
    cleanup_wait_cancel: asyncio.CancelledError | None,
) -> BaseException | None:
    """选择 SEC filing stream 唯一 winner 并把secondary只作为note。

    Args:
        body_error: filing 迭代或事件消费的主异常。
        close_error: filing inner 关闭自身的终态异常。
        cleanup_wait_cancel: 等待关闭期间观察到的第一份外层取消。

    Returns:
        process-exit、asyncio cancel、其它 body/close 顺序中优先级最高的异常。

    Raises:
        无；附加 note 失败不得遮蔽 winner。
    """

    candidates = tuple(
        (label, error)
        for label, error in (
            ("body", body_error),
            ("cleanup-wait", cleanup_wait_cancel),
            ("close", close_error),
        )
        if error is not None
    )
    if not candidates:
        return None
    _, winner = min(
        enumerate(candidates),
        key=lambda indexed: (_filing_error_priority(indexed[1][1]), indexed[0]),
    )[1]
    for label, secondary in candidates:
        if secondary is winner:
            continue
        try:
            winner.add_note(
                f"secondary {label} error: {type(secondary).__name__}: {secondary}"
            )
        except BaseException:
            pass
    return winner


async def run_download_stream_impl(
    host: SecDownloadWorkflowHost,
    *,
    ticker: str,
    form_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    overwrite: bool = False,
    rebuild: bool = False,
    ticker_aliases: Optional[list[str]] = None,
    cancel_checker: Optional[Callable[[], bool]] = None,
    parse_date: Callable[[str, bool], dt.date],
    extract_sec_ticker_aliases: Callable[..., list[str]],
    merge_ticker_aliases: Callable[..., list[str]],
    clear_filings_dir: Callable[[FilingMaintenanceRepositoryProtocol, str], None],
    load_rejection_registry: Callable[
        [FilingMaintenanceRepositoryProtocol, str],
        dict[str, dict[str, str]],
    ],
    save_rejection_registry: Callable[
        [FilingMaintenanceRepositoryProtocol, str, dict[str, dict[str, str]]],
        None,
    ],
    should_warn_missing_sc13: Callable[[dict[str, dt.date], list[Any]], bool],
    warn_insufficient_filings: Callable[
        [dict[str, Any], list[dict[str, Any]], dict[str, dict[str, str]]],
        list[str],
    ],
    warn_xbrl_missing_filings: Callable[[list[dict[str, Any]]], list[str]],
    cleanup_stale_filing_dirs: Callable[..., int],
    build_download_filing_event_payload: Callable[[dict[str, Any]], dict[str, Any]],
    provider_download_timeout_seconds: float = _DEFAULT_PROVIDER_DOWNLOAD_TIMEOUT_SECONDS,
) -> AsyncGenerator[DownloadEvent, None]:
    """执行 SecPipeline 下载主工作流。

    Args:
        host: `SecPipeline` facade 暴露出的最小宿主边界。
        ticker: 股票代码。
        form_type: 可选文档类型。
        start_date: 可选开始日期。
        end_date: 可选结束日期。
        overwrite: 是否强制覆盖。
        rebuild: 是否仅基于本地已下载数据重建 `meta/manifest`。
        ticker_aliases: CLI 侧传入的 alias 列表。
        cancel_checker: 可选取消检查函数，仅在文档边界生效。
        parse_date: 日期解析 helper。
        extract_sec_ticker_aliases: SEC alias 提取 helper。
        merge_ticker_aliases: alias 合并 helper。
        clear_filings_dir: 清空 filings 目录 helper。
        load_rejection_registry: 加载拒绝注册表 helper。
        save_rejection_registry: 保存拒绝注册表 helper。
        should_warn_missing_sc13: SC13 缺失 warning helper。
        warn_insufficient_filings: form 数量检查 helper。
        warn_xbrl_missing_filings: XBRL 缺失检查 helper。
        cleanup_stale_filing_dirs: 清理过期 filing 目录 helper。
        build_download_filing_event_payload: 构建 filing 事件 payload helper。

    Yields:
        下载流程事件流。

    Raises:
        ValueError: ticker 不合法或市场不匹配时抛出。
        RuntimeError: 下载执行失败时抛出。
    """

    normalized = normalize_ticker(ticker)
    if normalized.market != "US":
        raise ValueError(f"SecPipeline 仅支持 US，当前 market={normalized.market}")
    normalized_ticker = host._downloader.normalize_ticker(ticker)
    if rebuild:
        yield DownloadEvent(
            event_type=DownloadEventType.PIPELINE_STARTED,
            ticker=normalized_ticker,
            payload={
                "form_type": form_type,
                "start_date": start_date,
                "end_date": end_date,
                "overwrite": overwrite,
                "rebuild": True,
            },
        )
        rebuild_result = host._rebuild_download_artifacts(
            ticker=normalized_ticker,
            form_type=form_type,
            start_date=start_date,
            end_date=end_date,
            overwrite=overwrite,
        )
        for filing_result in rebuild_result.get("filings", []):
            if not isinstance(filing_result, dict):
                continue
            status = str(filing_result.get("status", "failed"))
            event_type = (
                DownloadEventType.FILING_FAILED
                if status == "failed"
                else DownloadEventType.FILING_COMPLETED
            )
            document_id = str(filing_result.get("document_id", ""))
            yield DownloadEvent(
                event_type=event_type,
                ticker=normalized_ticker,
                document_id=document_id,
                payload=build_download_filing_event_payload(filing_result),
            )
        yield DownloadEvent(
            event_type=DownloadEventType.PIPELINE_COMPLETED,
            ticker=normalized_ticker,
            payload={"result": rebuild_result},
        )
        return

    download_end_date = parse_date(end_date, True) if end_date else dt.date.today()
    host._downloader.configure(
        user_agent=host._user_agent,
        sleep_seconds=host._sleep_seconds,
        max_retries=host._max_retries,
    )
    yield DownloadEvent(
        event_type=DownloadEventType.PIPELINE_STARTED,
        ticker=normalized_ticker,
        payload={
            "form_type": form_type,
            "start_date": start_date,
            "end_date": end_date,
            "overwrite": overwrite,
            "rebuild": False,
        },
    )

    cik, company_name, cik10 = await _maybe_await(host._downloader.resolve_company(normalized_ticker))
    submissions = await _maybe_await(host._downloader.fetch_submissions(cik10))
    sec_ticker_aliases = extract_sec_ticker_aliases(
        submissions=submissions,
        primary_ticker=normalized_ticker,
    )
    merged_ticker_aliases = merge_ticker_aliases(
        primary_ticker=normalized_ticker,
        alias_groups=[sec_ticker_aliases, ticker_aliases],
    )
    yield DownloadEvent(
        event_type=DownloadEventType.COMPANY_RESOLVED,
        ticker=normalized_ticker,
        payload={
            "cik": cik,
            "company_name": company_name,
            "cik10": cik10,
        },
    )
    form_windows = host._resolve_form_windows(
        form_type=form_type,
        start_date=start_date,
        end_date=download_end_date,
    )
    Log.verbose(
        f"下载窗口详情: { {key: value.isoformat() for key, value in form_windows.items()} }",
        module=host.MODULE,
    )
    Log.info(
        (
            "进入美股下载流程: "
            f"ticker={normalized_ticker} form_type={form_type} start={start_date} end={end_date} "
            f"overwrite={overwrite}"
        ),
        module=host.MODULE,
    )
    host._upsert_company_meta(
        ticker=normalized_ticker,
        company_id=cik,
        company_name=company_name,
        ticker_aliases=merged_ticker_aliases,
    )
    sc13_direction_cache: dict[str, Optional[bool]] = {}
    if overwrite:
        clear_filings_dir(host._filing_maintenance_repository, normalized_ticker)
    rejection_registry = load_rejection_registry(host._filing_maintenance_repository, normalized_ticker)
    filings, filenums = await host._filter_filings(
        ticker=normalized_ticker,
        submissions=submissions,
        form_windows=form_windows,
        end_date=download_end_date,
        target_cik=cik,
        sc13_direction_cache=sc13_direction_cache,
        rejection_registry=rejection_registry,
        overwrite=overwrite,
    )
    filings = await host._extend_with_browse_edgar_sc13(
        ticker=normalized_ticker,
        filings=filings,
        filenums=filenums,
        form_windows=form_windows,
        end_date=download_end_date,
        target_cik=cik,
        sc13_direction_cache=sc13_direction_cache,
        rejection_registry=rejection_registry,
        overwrite=overwrite,
    )
    filings = await host._retry_sc13_if_empty(
        ticker=normalized_ticker,
        filings=filings,
        filenums=filenums,
        submissions=submissions,
        form_windows=form_windows,
        end_date=download_end_date,
        target_cik=cik,
        sc13_direction_cache=sc13_direction_cache,
        rejection_registry=rejection_registry,
        overwrite=overwrite,
    )
    warnings: list[str] = []
    if should_warn_missing_sc13(form_windows, filings):
        warning = (
            "未在 issuer 的 submissions/browse-edgar 中发现 SC 13D/G；"
            "13D/G 往往由申报人提交，需要申报人 CIK 维度或反查补齐。"
        )
        warnings.append(warning)
        Log.warn(warning, module=host.MODULE)

    filing_results: list[dict[str, Any]] = []
    started_at = time.perf_counter()
    batching = host.batching_repository
    for filing in filings:
        if cancel_checker is not None and cancel_checker():
            Log.info(
                f"下载任务收到取消请求，文档边界停止: ticker={normalized_ticker}",
                module=host.MODULE,
            )
            break
        document_id = f"fil_{filing.accession_number}"
        yield DownloadEvent(
            event_type=DownloadEventType.FILING_STARTED,
            ticker=normalized_ticker,
            document_id=document_id,
            payload={
                "form_type": filing.form_type,
                "filing_date": filing.filing_date,
                "report_date": filing.report_date,
                "accession_number": filing.accession_number,
                "total_filings": len(filings),
            },
        )
        if batching is None:
            inner = host._download_single_filing_stream(
                ticker=normalized_ticker,
                cik=cik,
                filing=filing,
                overwrite=overwrite,
                rejection_registry=rejection_registry,
            )
            stream_error: BaseException | None = None
            try:
                async for event in inner:
                    event_result = event.payload.get("filing_result")
                    if event.event_type in {
                        DownloadEventType.FILING_COMPLETED,
                        DownloadEventType.FILING_FAILED,
                    } and isinstance(event_result, dict):
                        filing_results.append(event_result)
                        host._log_filing_download_result(
                            ticker=normalized_ticker,
                            filing_result=event_result,
                        )
                    yield event
            except BaseException as exc:
                stream_error = exc
            close_error, cleanup_wait_cancel = await _await_owned_filing_close(inner)
            stream_error = _arbitrate_filing_stream_errors(
                stream_error,
                close_error,
                cleanup_wait_cancel,
            )
            if stream_error is not None:
                raise stream_error.with_traceback(stream_error.__traceback__)
            continue
        token = batching.begin_batch(normalized_ticker)
        terminal = _FilingTerminalState.PENDING
        finalization_started = False
        try:
            async with asyncio.timeout(provider_download_timeout_seconds):
                inner = host._download_single_filing_stream(
                    ticker=normalized_ticker,
                    cik=cik,
                    filing=filing,
                    overwrite=overwrite,
                    rejection_registry=rejection_registry,
                )
                stream_error: BaseException | None = None
                try:
                    async for event in inner:
                        event_result = event.payload.get("filing_result")
                        if event.event_type in {
                            DownloadEventType.FILING_COMPLETED,
                            DownloadEventType.FILING_FAILED,
                        } and isinstance(event_result, dict):
                            filing_results.append(event_result)
                            host._log_filing_download_result(
                                ticker=normalized_ticker,
                                filing_result=event_result,
                            )
                            # 恰好一个 terminal event 才允许成功判定：重复/矛盾
                            # terminal（COMPLETED 后 FAILED、FAILED 后 COMPLETED、
                            # 两个 COMPLETED）一律视为非法终态 => rollback
                            # （S14-CTRL-12 per-filing terminal 状态机）。
                            if terminal is _FilingTerminalState.PENDING:
                                terminal = _FilingTerminalState.FILING_COMPLETED if (
                                    event.event_type == DownloadEventType.FILING_COMPLETED
                                ) else _FilingTerminalState.FILING_FAILED
                            else:
                                terminal = _FilingTerminalState.FILING_FAILED
                        yield event
                except BaseException as exc:
                    stream_error = exc
                close_error, cleanup_wait_cancel = await _await_owned_filing_close(inner)
                stream_error = _arbitrate_filing_stream_errors(
                    stream_error,
                    close_error,
                    cleanup_wait_cancel,
                )
                if stream_error is not None:
                    raise stream_error.with_traceback(stream_error.__traceback__)
            if terminal is _FilingTerminalState.FILING_COMPLETED and (
                cancel_checker is None or not cancel_checker()
            ):
                finalization_started = True
                batching.commit_batch(token)
            else:
                finalization_started = True
                batching.rollback_batch(token)
        except BaseException as exc:
            # commit PONR 前任意退出都回滚同一 token；commit/rollback 一旦开始则不二次回滚。
            if not finalization_started:
                _rollback_batch_preserving_primary(
                    batching,
                    token,
                    primary=exc,
                    ticker=normalized_ticker,
                    document_id=document_id,
                    module=host.MODULE,
                )
            try:
                if isinstance(exc, asyncio.TimeoutError):
                    Log.warn(
                        f"SEC per-filing provider timeout，rollback: ticker={normalized_ticker} document_id={document_id}",
                        module=host.MODULE,
                    )
                else:
                    Log.warn(
                        f"SEC per-filing 下载失败，rollback: ticker={normalized_ticker} document_id={document_id} error={exc}",
                        module=host.MODULE,
                    )
            except BaseException:
                pass
            raise

    save_rejection_registry(host._filing_maintenance_repository, normalized_ticker, rejection_registry)
    for warning in warn_insufficient_filings(
        form_windows,
        filing_results,
        rejection_registry,
    ):
        warnings.append(warning)
        Log.warn(warning, module=host.MODULE)
    for warning in warn_xbrl_missing_filings(filing_results):
        warnings.append(warning)
        Log.warn(warning, module=host.MODULE)
    cleaned = cleanup_stale_filing_dirs(
        repository=host._filing_maintenance_repository,
        ticker=normalized_ticker,
        form_windows=form_windows,
        filing_results=filing_results,
    )
    if cleaned:
        Log.info(
            f"清理过期 filing 目录: ticker={normalized_ticker} cleaned={cleaned}",
            module=host.MODULE,
        )
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    summary = {
        "total": len(filing_results),
        "downloaded": sum(1 for item in filing_results if item["status"] == "downloaded"),
        "skipped": sum(1 for item in filing_results if item["status"] == "skipped"),
        "failed": sum(1 for item in filing_results if item["status"] == "failed"),
        "elapsed_ms": elapsed_ms,
        "reused_downloads": 0,
        "converted": 0,
    }
    Log.info(
        (
            "美股下载完成: "
            f"ticker={normalized_ticker} total={summary['total']} downloaded={summary['downloaded']} "
            f"skipped={summary['skipped']} failed={summary['failed']} elapsed_ms={summary['elapsed_ms']}"
        ),
        module=host.MODULE,
    )
    final_result = host._build_result(
        action="download",
        ticker=normalized_ticker,
        market_profile={
            "market": normalized.market,
        },
        filters={
            "forms": sorted(form_windows.keys()),
            "start_dates": {key: value.isoformat() for key, value in sorted(form_windows.items())},
            "end_date": download_end_date.isoformat(),
            "overwrite": overwrite,
        },
        warnings=warnings,
        filings=filing_results,
        summary=summary,
        status="cancelled" if cancel_checker is not None and cancel_checker() else "ok",
    )
    yield DownloadEvent(
        event_type=DownloadEventType.PIPELINE_COMPLETED,
        ticker=normalized_ticker,
        payload={"result": final_result},
    )
