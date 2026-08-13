"""面向 worker 的 Fins 源同步严格 ``DownloadEvent`` owner。

本模块独占有界事件关联、终态身份校验、仓储证据读取和 locator 回读验证，
并把内部异常按固定优先级收敛为纯领域结果。
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncGenerator, Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, TypeAlias

from dayu.contracts.cancellation import CancelledError as DomainCancelledError
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.evidence_locator import (
    REPOSITORY_ID,
    SCHEMA_VERSION,
    ArtifactKind,
    DocumentLocatorPayload,
    EvidenceLocatorProjection,
    EvidenceLocatorRequest,
    LocatorKind,
    canonical_json_bytes,
    is_lower_hex_sha256,
    sha256_hex,
)
from dayu.fins.domain.source_sync import (
    FinsWorkerSourceDocument,
    FinsWorkerSyncOutcome,
    FinsWorkerSyncRequest,
    FinsWorkerSyncResult,
)
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.storage import SourceDocumentRepositoryProtocol
from dayu.fins.ticker_normalization import normalize_ticker

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

_US_FORMS = frozenset(
    {
        "10-K",
        "10-Q",
        "20-F",
        "6-K",
        "8-K",
        "8-K/A",
        "DEF 14A",
        "SC 13D",
        "SC 13D/A",
        "SC 13G",
        "SC 13G/A",
    }
)
_ASIA_FORMS = frozenset({"FY", "H1", "Q1", "Q2", "Q3", "Q4"})
_ASIA_FORM_ORDER = ("FY", "H1", "Q1", "Q2", "Q3", "Q4")
_MIC_MARKET = {
    "XNAS": ("US", None),
    "XNYS": ("US", None),
    "XHKG": ("HK", "HKEX"),
    "XSHG": ("CN", "SSE"),
    "XSHE": ("CN", "SZSE"),
}
_REUSED_REASONS = frozenset(
    {
        "already_downloaded_complete",
        "source_fingerprint_matched",
        "remote_files_equivalent",
        "not_modified",
        "remote_fingerprint_matched",
        "pdf_sha256_matched",
    }
)
_IGNORED_REASONS = frozenset({"rejection_registry", "6k_filtered"})
_SOURCE_SYNC_CLOSE_TASK_NAME = "fins-source-sync-inner-close"


class FinsSourceSyncDownloadPipelineProtocol(Protocol):
    """源同步 owner 消费的可关闭下载事件流窄协议。"""

    def download_stream(
        self,
        ticker: str,
        form_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        overwrite: bool = False,
        rebuild: bool = False,
        ticker_aliases: list[str] | None = None,
        *,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> AsyncGenerator[DownloadEvent, None]:
        """创建一次可关闭的下载事件流。

        Args:
            ticker: 规范股票代码。
            form_type: 逗号连接的目标 form，或 ``None``。
            start_date: ISO 日期窗口起点，或 ``None``。
            end_date: ISO 日期窗口终点，或 ``None``。
            overwrite: 是否覆盖现有下载。
            rebuild: 是否只重建既有下载产物。
            ticker_aliases: 可选 ticker 别名。
            cancel_checker: 可选取消检查器。

        Yields:
            按生产顺序生成的下载事件。

        Raises:
            BaseException: pipeline 创建或迭代失败时原样抛出。
        """

        ...


class FinsDownloadPipelineFactoryProtocol(Protocol):
    """既有市场下载 pipeline 的窄工厂边界。"""

    def build_source_sync_pipeline(self, ticker: str) -> FinsSourceSyncDownloadPipelineProtocol:
        """为规范 ticker 构建源同步下载 pipeline。

        Args:
            ticker: 规范股票代码。

        Returns:
            对应市场的下载 pipeline。

        Raises:
            Exception: 市场路由或 pipeline 构建失败时抛出。
        """

        ...


class FinsEvidenceLocatorOwnerProtocol(Protocol):
    """源同步调用的既有 locator 解析与回读验证 owner。"""

    def resolve_evidence_locator(self, request: EvidenceLocatorRequest) -> EvidenceLocatorProjection:
        """解析证据 locator 并执行 owner 侧事实读取。

        Args:
            request: 已闭合的 locator 请求。

        Returns:
            无路径 locator 投影。

        Raises:
            Exception: 仓储事实、哈希或 locator 不变量不成立时抛出。
        """

        ...

    def validate_evidence_locator(self, locator: EvidenceLocatorProjection) -> None:
        """回读并验证 locator 投影仍与仓储事实一致。

        Args:
            locator: 待验证 locator 投影。

        Returns:
            无。

        Raises:
            Exception: locator 回读或事实验证失败时抛出。
        """

        ...


class _InvariantError(Exception):
    """已证明 wire 或关联不变量失败的私有标记。"""


class _DocumentFailure(Exception):
    """单文档无法生成已验证证据的私有标记。"""


@dataclass(frozen=True, slots=True)
class _StartedFiling:
    """已接收 ``FILING_STARTED`` 的市场身份快照。"""

    document_id: str
    form_type: str
    filing_date: date
    report_date: str | None
    accession_number: str | None
    fiscal_year: int | None
    fiscal_period: str | None
    source_id: str | None


@dataclass(frozen=True, slots=True)
class _TerminalFiling:
    """已收窄且保持 canonical nested payload 的 filing 终态。"""

    nested: JsonObject
    document_id: str
    status: str
    form_type: str
    filing_date: date | None
    reason_code: str | None
    skip_reason: str | None


@dataclass(slots=True)
class _CollectionState:
    """单次下载事件消费过程的有界可变关联状态。"""

    started: dict[str, _StartedFiling] = field(default_factory=dict)
    terminals: list[_TerminalFiling] = field(default_factory=list)
    terminal_ids: set[str] = field(default_factory=set)
    candidate_forms: set[str] = field(default_factory=set)
    documents: list[FinsWorkerSourceDocument] = field(default_factory=list)
    downloaded_count: int = 0
    reused_count: int = 0
    ignored_count: int = 0
    failed_count: int = 0
    pipeline_started: bool = False
    pipeline_result: JsonObject | None = None


def _empty_result(outcome: FinsWorkerSyncOutcome) -> FinsWorkerSyncResult:
    """构造指定 outcome 的全空闭合结果。

    Args:
        outcome: 目标闭集结果。

    Returns:
        文档与所有计数均为空的同步结果。

    Raises:
        ValueError: outcome 不允许全空结果时抛出。
    """

    return FinsWorkerSyncResult(
        outcome=outcome,
        documents=(),
        latest_source_observed_date=None,
        discovered_count=0,
        downloaded_count=0,
        reused_count=0,
        ignored_count=0,
        failed_count=0,
    )


def _copy_json_value(value: JsonValue) -> JsonValue:
    """递归复制 owner 管辖的严格 JSON 值。

    Args:
        value: 待复制 JSON 值。

    Returns:
        与输入等价且不共享 list/dict 容器的 JSON 值。

    Raises:
        _InvariantError: 数字非有限、对象 key 非字符串或值不属于 JSON 时抛出。
    """

    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise _InvariantError("non-finite JSON number")
        return value
    if type(value) is list:
        return [_copy_json_value(item) for item in value]
    if type(value) is dict:
        copied: JsonObject = {}
        for key, item in value.items():
            if type(key) is not str:
                raise _InvariantError("JSON object key is not a string")
            copied[key] = _copy_json_value(item)
        return copied
    raise _InvariantError("owned event subtree is not JSON")


def _copy_json_object(value: JsonValue) -> JsonObject:
    """复制并要求输入为严格 JSON object。

    Args:
        value: 待复制 JSON 值。

    Returns:
        独立 JSON object。

    Raises:
        _InvariantError: 输入或其子树不符合严格 JSON object 时抛出。
    """

    copied = _copy_json_value(value)
    if type(copied) is not dict:
        raise _InvariantError("owned event subtree must be an object")
    return copied


def _require_text(value: JsonValue, label: str, *, allow_empty: bool = False) -> str:
    """收窄规范文本并按需允许空字符串。

    Args:
        value: 待收窄 JSON 值。
        label: 错误消息中的字段名。
        allow_empty: 是否允许空字符串。

    Returns:
        已验证字符串。

    Raises:
        _InvariantError: 值不是规范字符串时抛出。
    """

    if type(value) is not str or value != value.strip() or (not allow_empty and not value):
        raise _InvariantError(f"{label} must be canonical text")
    return value


def _optional_text(value: JsonValue, label: str) -> str | None:
    """收窄可空规范文本。

    Args:
        value: 待收窄 JSON 值。
        label: 错误消息中的字段名。

    Returns:
        ``None`` 或已验证字符串。

    Raises:
        _InvariantError: 非空值不是规范字符串时抛出。
    """

    if value is None:
        return None
    return _require_text(value, label)


def _require_int(value: JsonValue, label: str) -> int:
    """收窄非负精确整数。

    Args:
        value: 待收窄 JSON 值。
        label: 错误消息中的字段名。

    Returns:
        已验证非负整数。

    Raises:
        _InvariantError: 值不是非负精确整数时抛出。
    """

    if type(value) is not int or value < 0:
        raise _InvariantError(f"{label} must be a non-negative integer")
    return value


def _require_date(value: JsonValue, label: str) -> date:
    """收窄 canonical ISO 日历日期。

    Args:
        value: 待收窄 JSON 值。
        label: 错误消息中的字段名。

    Returns:
        已解析日期。

    Raises:
        _InvariantError: 值不是 canonical ISO 日历日期时抛出。
    """

    text = _require_text(value, label)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise _InvariantError(f"{label} must be an ISO calendar date") from exc
    if parsed.isoformat() != text:
        raise _InvariantError(f"{label} must be a canonical ISO calendar date")
    return parsed


def _same_json(left: JsonValue, right: JsonValue) -> bool:
    """按 canonical JSON bytes 比较两个 JSON 值。

    Args:
        left: 左侧 JSON 值。
        right: 右侧 JSON 值。

    Returns:
        canonical bytes 相等时返回 ``True``。

    Raises:
        无。
    """

    return canonical_json_bytes({"value": left}) == canonical_json_bytes({"value": right})


async def _capture_inner_close_error(
    inner: AsyncGenerator[DownloadEvent, None],
) -> BaseException | None:
    """在独立 owner task 内关闭 direct inner 并把异常作为值返回。

    Args:
        inner: 当前 runtime 直接拥有的下载事件流。

    Returns:
        关闭成功时返回 ``None``，否则返回原始 ``BaseException``。

    Raises:
        无；包括进程级异常在内的关闭结果均由外层统一仲裁。
    """

    try:
        await inner.aclose()
    except BaseException as exc:
        return exc
    return None


async def _await_owned_inner_close(
    inner: AsyncGenerator[DownloadEvent, None],
) -> tuple[BaseException | None, asyncio.CancelledError | None]:
    """用唯一独立 task 关闭 direct inner，并在重复取消下完整 reap。

    Args:
        inner: 当前 runtime 直接拥有的下载事件流。

    Returns:
        ``(关闭自身异常, 等待期首个外层取消)``；两者都可为 ``None``。

    Raises:
        无；外层 task 的重复取消被记录，关闭 task 的所有终态被转为值。
    """

    close_task = asyncio.create_task(
        _capture_inner_close_error(inner),
        name=_SOURCE_SYNC_CLOSE_TASK_NAME,
    )
    cleanup_wait_cancel: asyncio.CancelledError | None = None
    while not close_task.done():
        try:
            await asyncio.shield(close_task)
        except asyncio.CancelledError as exc:
            if cleanup_wait_cancel is None:
                cleanup_wait_cancel = exc
    return close_task.result(), cleanup_wait_cancel


def _error_priority(error: BaseException) -> int:
    """返回源同步终态异常的固定仲裁优先级。

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
    if isinstance(error, DomainCancelledError):
        return 3
    if isinstance(error, _InvariantError):
        return 4
    return 5


def _arbitrate_stream_errors(
    body_error: BaseException | None,
    close_error: BaseException | None,
    cleanup_wait_cancel: asyncio.CancelledError | None,
) -> BaseException | None:
    """按全局优先级选择唯一 winner，其余异常只作为 note。

    Args:
        body_error: 事件流迭代或消费的主异常。
        close_error: direct inner 关闭协程的终态异常。
        cleanup_wait_cancel: 等待关闭期间观察到的第一份外层取消。

    Returns:
        优先级最高的原始异常对象，或全部为空时的 ``None``。

    Raises:
        无；附加 secondary note 失败也不得遮蔽 winner。
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
        key=lambda indexed: (_error_priority(indexed[1][1]), indexed[0]),
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


def _parse_started(event: DownloadEvent, *, market: str) -> _StartedFiling:
    """解析并冻结市场专属 ``FILING_STARTED`` 身份。

    Args:
        event: 待解析 started 事件。
        market: 已归一化市场代码。

    Returns:
        已收窄 started filing 身份。

    Raises:
        _InvariantError: 文档、日期或市场专属身份缺失或非法时抛出。
    """

    if event.document_id is None or not event.document_id:
        raise _InvariantError("filing_started requires document_id")
    payload = _copy_json_object(event.payload)
    form_type = _require_text(payload.get("form_type"), "started.form_type")
    filing_date = _require_date(payload.get("filing_date"), "started.filing_date")
    if market == "US":
        if "report_date" not in payload:
            raise _InvariantError("SEC filing_started requires report_date identity")
        report_date = _optional_text(payload["report_date"], "started.report_date")
        accession_number = _require_text(payload.get("accession_number"), "started.accession_number")
        fiscal_year = None
        fiscal_period = None
        source_id = None
    else:
        report_date = _optional_text(payload.get("report_date"), "started.report_date")
        accession_number = None
        fiscal_year = _require_int(payload.get("fiscal_year"), "started.fiscal_year")
        fiscal_period = _require_text(payload.get("fiscal_period"), "started.fiscal_period")
        source_id = _require_text(payload.get("source_id"), "started.source_id")
    return _StartedFiling(
        document_id=event.document_id,
        form_type=form_type,
        filing_date=filing_date,
        report_date=report_date,
        accession_number=accession_number,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        source_id=source_id,
    )


def _parse_terminal(event: DownloadEvent) -> _TerminalFiling:
    """解析 filing 终态并验证 nested/flat mirror 完全闭合。

    Args:
        event: 待解析终态事件。

    Returns:
        已收窄 filing 终态。

    Raises:
        _InvariantError: payload、mirror、身份或状态不合法时抛出。
    """

    payload = _copy_json_object(event.payload)
    if "filing_result" not in payload:
        raise _InvariantError("filing terminal lacks nested filing_result")
    nested = _copy_json_object(payload["filing_result"])
    for key, value in payload.items():
        if key == "filing_result":
            continue
        if key not in nested or not _same_json(value, nested[key]):
            raise _InvariantError("filing terminal flat mirror drift")
    document_id = _require_text(nested.get("document_id"), "terminal.document_id", allow_empty=True)
    status = _require_text(nested.get("status"), "terminal.status")
    form_type = _require_text(nested.get("form_type"), "terminal.form_type")
    filing_value = nested.get("filing_date")
    filing_date = None if filing_value is None else _require_date(filing_value, "terminal.filing_date")
    reason_code = _optional_text(nested.get("reason_code"), "terminal.reason_code")
    skip_reason = _optional_text(nested.get("skip_reason"), "terminal.skip_reason")
    if event.event_type is DownloadEventType.FILING_COMPLETED and status not in {"downloaded", "skipped"}:
        raise _InvariantError("filing_completed has invalid nested status")
    if event.event_type is DownloadEventType.FILING_FAILED and status != "failed":
        raise _InvariantError("filing_failed has invalid nested status")
    return _TerminalFiling(
        nested=nested,
        document_id=document_id,
        status=status,
        form_type=form_type,
        filing_date=filing_date,
        reason_code=reason_code,
        skip_reason=skip_reason,
    )


def _correlate_terminal(
    event: DownloadEvent,
    terminal: _TerminalFiling,
    state: _CollectionState,
    request: FinsWorkerSyncRequest,
    *,
    market: str,
) -> bool:
    """把 ordinary 或 ``candidate_not_found`` 终态关联到唯一 started。

    Args:
        event: 原始终态事件。
        terminal: 已收窄终态。
        state: 当前关联状态。
        request: 当前同步请求。
        market: 已归一化市场代码。

    Returns:
        终态属于合法 ``candidate_not_found`` 例外时返回 ``True``。

    Raises:
        _InvariantError: 终态身份缺失、漂移、重复或无 started owner 时抛出。
    """

    candidate_not_found = terminal.reason_code == "candidate_not_found" or terminal.skip_reason == "candidate_not_found"
    if candidate_not_found:
        if (
            market == "US"
            or event.event_type is not DownloadEventType.FILING_COMPLETED
            or event.document_id is not None
            or terminal.document_id != ""
            or terminal.status != "skipped"
            or terminal.filing_date is not None
            or terminal.reason_code != "candidate_not_found"
            or terminal.skip_reason != "candidate_not_found"
            or terminal.form_type not in request.forms
            or terminal.form_type in state.candidate_forms
            or terminal.nested.get("report_date") is not None
            or any(
                started.form_type == terminal.form_type
                for started in state.started.values()
            )
        ):
            raise _InvariantError("invalid candidate_not_found terminal")
        state.candidate_forms.add(terminal.form_type)
        return True
    if event.document_id is None or event.document_id != terminal.document_id or not terminal.document_id:
        raise _InvariantError("terminal document identity drift")
    if terminal.document_id in state.terminal_ids:
        raise _InvariantError("duplicate filing terminal")
    started = state.started.get(terminal.document_id)
    if started is None:
        raise _InvariantError("terminal without filing_started")
    if terminal.form_type != started.form_type or terminal.filing_date != started.filing_date:
        raise _InvariantError("terminal identity does not match filing_started")
    if market == "US":
        if "report_date" not in terminal.nested or "internal_document_id" not in terminal.nested:
            raise _InvariantError("SEC terminal lacks required identity")
        report_date = _optional_text(terminal.nested["report_date"], "terminal.report_date")
        if report_date != started.report_date:
            raise _InvariantError("terminal report_date does not match filing_started")
        internal = _require_text(terminal.nested["internal_document_id"], "terminal.internal_document_id")
        accession = terminal.nested.get("accession_number")
        if internal != started.accession_number:
            raise _InvariantError("terminal accession identity drift")
        if accession is not None and _require_text(accession, "terminal.accession_number") != started.accession_number:
            raise _InvariantError("terminal accession identity drift")
    else:
        required = {"fiscal_year", "fiscal_period", "source_id"}
        if not required.issubset(terminal.nested):
            raise _InvariantError("CN/HK terminal lacks required identity")
        fiscal_year = _require_int(terminal.nested["fiscal_year"], "terminal.fiscal_year")
        fiscal_period = _require_text(terminal.nested["fiscal_period"], "terminal.fiscal_period")
        source_id = _require_text(terminal.nested["source_id"], "terminal.source_id")
        if fiscal_year != started.fiscal_year:
            raise _InvariantError("terminal fiscal_year identity drift")
        if fiscal_period != started.fiscal_period:
            raise _InvariantError("terminal fiscal_period identity drift")
        if source_id != started.source_id:
            raise _InvariantError("terminal source_id identity drift")
    state.terminal_ids.add(terminal.document_id)
    return False


def _validate_filters(result: Mapping[str, JsonValue], request: FinsWorkerSyncRequest, *, market: str) -> None:
    """验证 pipeline terminal 的窗口与 form filters。

    Args:
        result: pipeline terminal result。
        request: 当前同步请求。
        market: 已归一化市场代码。

    Returns:
        无。

    Raises:
        _InvariantError: filters 形态或值与请求不一致时抛出。
    """

    filters = result.get("filters")
    status = result.get("status")
    if status == "failed" and type(filters) is dict and not filters:
        return
    if type(filters) is not dict or set(filters) != {"forms", "start_dates", "end_date", "overwrite"}:
        raise _InvariantError("pipeline filters shape drift")
    expected_forms = list(request.forms) if market == "US" else [form for form in _ASIA_FORM_ORDER if form in request.forms]
    forms = filters["forms"]
    if type(forms) is not list or forms != expected_forms:
        raise _InvariantError("pipeline filters forms drift")
    start_dates = filters["start_dates"]
    if type(start_dates) is not dict or set(start_dates) != set(request.forms):
        raise _InvariantError("pipeline filters start_dates drift")
    if any(value != request.start_date.isoformat() for value in start_dates.values()):
        raise _InvariantError("pipeline filters start date drift")
    if filters["end_date"] != request.end_date.isoformat() or filters["overwrite"] is not False:
        raise _InvariantError("pipeline filters window drift")


def _validate_pipeline_result(
    result: JsonObject,
    state: _CollectionState,
    request: FinsWorkerSyncRequest,
    *,
    market: str,
) -> str:
    """验证 pipeline terminal 与已消费 filing 序列完全一致。

    Args:
        result: pipeline terminal result。
        state: 已消费关联状态。
        request: 当前同步请求。
        market: 已归一化市场代码。

    Returns:
        已验证 pipeline 状态文本。

    Raises:
        _InvariantError: owner、filters、filings、顺序或 summary 漂移时抛出。
    """

    status = _require_text(result.get("status"), "result.status")
    if status not in {"ok", "cancelled", "failed"}:
        raise _InvariantError("unknown pipeline status")
    if result.get("ticker") != request.ticker or result.get("action") != "download":
        raise _InvariantError("pipeline terminal identity drift")
    expected_pipeline = "sec" if market == "US" else "cn"
    if result.get("pipeline") != expected_pipeline:
        raise _InvariantError("pipeline terminal owner drift")
    _validate_filters(result, request, market=market)
    if status != "ok":
        return status
    filings = result.get("filings")
    if type(filings) is not list or len(filings) != len(state.terminals):
        raise _InvariantError("pipeline filings correlation drift")
    for raw, terminal in zip(filings, state.terminals, strict=True):
        item = _copy_json_object(raw)
        if canonical_json_bytes(item) != canonical_json_bytes(terminal.nested):
            raise _InvariantError("pipeline filing order/content drift")
    summary = result.get("summary")
    if type(summary) is not dict:
        raise _InvariantError("pipeline summary must be an object")
    expected = {
        "total": len(state.terminals),
        "downloaded": sum(item.status == "downloaded" for item in state.terminals),
        "skipped": sum(item.status == "skipped" for item in state.terminals),
        "failed": sum(item.status == "failed" for item in state.terminals),
    }
    for key, value in expected.items():
        if summary.get(key) != value or type(summary.get(key)) is not int:
            raise _InvariantError("pipeline summary drift")
    return status


@dataclass(frozen=True, slots=True)
class DefaultFinsWorkerSourceSyncRuntime:
    """有界 ``DownloadEvent`` 关联状态机及其直接 inner 的唯一 owner。"""

    pipeline_factory: FinsDownloadPipelineFactoryProtocol = field(repr=False, compare=False)
    source_repository: SourceDocumentRepositoryProtocol = field(repr=False, compare=False)
    evidence_locator_owner: FinsEvidenceLocatorOwnerProtocol = field(repr=False, compare=False)

    async def sync_worker_source(
        self,
        request: FinsWorkerSyncRequest,
        *,
        cancel_checker: Callable[[], bool],
    ) -> FinsWorkerSyncResult:
        """执行一次严格有界的源同步并按固定优先级收敛结果。

        Args:
            request: 已校验 worker 源同步请求。
            cancel_checker: 外部或领域取消检查器。

        Returns:
            无内部 wire、异常文本或路径泄漏的闭合结果。

        Raises:
            asyncio.CancelledError: task 被取消时在直接 inner 关闭后原样抛出。
            KeyboardInterrupt: 迭代或关闭收到进程中断时原样抛出。
            SystemExit: 迭代或关闭收到进程退出时原样抛出。
        """

        preflight = self._preflight(request)
        if preflight is not None:
            return _empty_result(preflight)
        if cancel_checker():
            return _empty_result(FinsWorkerSyncOutcome.CANCELLED)
        market = normalize_ticker(request.ticker).market
        try:
            pipeline = self.pipeline_factory.build_source_sync_pipeline(request.ticker)
            inner = pipeline.download_stream(
                ticker=request.ticker,
                form_type=",".join(request.forms),
                start_date=request.start_date.isoformat(),
                end_date=request.end_date.isoformat(),
                overwrite=False,
                rebuild=False,
                ticker_aliases=[request.ticker],
                cancel_checker=cancel_checker,
            )
        except asyncio.CancelledError:
            raise
        except DomainCancelledError:
            return _empty_result(FinsWorkerSyncOutcome.CANCELLED)
        except Exception:
            return _empty_result(FinsWorkerSyncOutcome.UNAVAILABLE)

        state = _CollectionState()
        event_count = 0
        primary_error: BaseException | None = None
        try:
            async for event in inner:
                event_count += 1
                if cancel_checker():
                    raise DomainCancelledError("source sync cancelled")
                if event_count > request.max_events:
                    raise _InvariantError("download event cap exceeded")
                self._consume_event(event, state, request, market=market)
                if len(state.documents) > request.max_documents:
                    raise _InvariantError("verified document cap exceeded")
        except BaseException as exc:
            primary_error = exc
        close_error, cleanup_wait_cancel = await _await_owned_inner_close(inner)
        primary_error = _arbitrate_stream_errors(
            primary_error,
            close_error,
            cleanup_wait_cancel,
        )
        if isinstance(primary_error, asyncio.CancelledError):
            raise primary_error.with_traceback(primary_error.__traceback__)
        if isinstance(primary_error, DomainCancelledError):
            return _empty_result(FinsWorkerSyncOutcome.CANCELLED)
        if isinstance(primary_error, _InvariantError):
            return _empty_result(FinsWorkerSyncOutcome.INVARIANT_FAILED)
        if isinstance(primary_error, Exception):
            return _empty_result(FinsWorkerSyncOutcome.UNAVAILABLE)
        if primary_error is not None:
            raise primary_error.with_traceback(primary_error.__traceback__)

        if cancel_checker():
            return _empty_result(FinsWorkerSyncOutcome.CANCELLED)
        try:
            if state.pipeline_result is None or not state.pipeline_started:
                raise _InvariantError("missing pipeline terminal")
            if set(state.started) != state.terminal_ids:
                raise _InvariantError("filing_started/terminal mismatch")
            status = _validate_pipeline_result(state.pipeline_result, state, request, market=market)
        except _InvariantError:
            return _empty_result(FinsWorkerSyncOutcome.INVARIANT_FAILED)
        if status == "failed":
            return _empty_result(FinsWorkerSyncOutcome.UNAVAILABLE)
        if status == "cancelled":
            return _empty_result(FinsWorkerSyncOutcome.CANCELLED)
        documents = tuple(sorted(state.documents, key=lambda item: (item.document_id, item.form_type, item.source_observed_date)))
        discovered = state.downloaded_count + state.reused_count + state.ignored_count + state.failed_count
        if documents and state.failed_count:
            outcome = FinsWorkerSyncOutcome.PARTIAL
        elif not documents and state.failed_count:
            outcome = FinsWorkerSyncOutcome.UNAVAILABLE
        else:
            outcome = FinsWorkerSyncOutcome.COMPLETE
        return FinsWorkerSyncResult(
            outcome=outcome,
            documents=documents,
            latest_source_observed_date=max((item.source_observed_date for item in documents), default=None),
            discovered_count=discovered,
            downloaded_count=state.downloaded_count,
            reused_count=state.reused_count,
            ignored_count=state.ignored_count,
            failed_count=state.failed_count,
        )

    def _preflight(self, request: FinsWorkerSyncRequest) -> FinsWorkerSyncOutcome | None:
        """在创建 pipeline 前验证 ticker、MIC 与 form 市场边界。

        Args:
            request: 当前同步请求。

        Returns:
            不支持时返回对应 outcome，通过时返回 ``None``。

        Raises:
            无。
        """

        try:
            normalized = normalize_ticker(request.ticker)
        except (TypeError, ValueError):
            return FinsWorkerSyncOutcome.UNSUPPORTED_MARKET
        expected = _MIC_MARKET.get(request.exchange_mic)
        if expected is None or request.ticker != normalized.canonical or expected != (normalized.market, normalized.exchange):
            return FinsWorkerSyncOutcome.UNSUPPORTED_MARKET
        allowed = _US_FORMS if normalized.market == "US" else _ASIA_FORMS
        if any(form not in allowed for form in request.forms):
            return FinsWorkerSyncOutcome.UNSUPPORTED_FORM
        return None

    def _consume_event(
        self,
        event: DownloadEvent,
        state: _CollectionState,
        request: FinsWorkerSyncRequest,
        *,
        market: str,
    ) -> None:
        """消费单个下载事件并推进严格关联状态机。

        Args:
            event: 当前下载事件。
            state: 当前有界关联状态。
            request: 当前同步请求。
            market: 已归一化市场代码。

        Returns:
            无。

        Raises:
            _InvariantError: 事件类型、顺序、身份、payload 或容量不变量失败时抛出。
        """

        if type(event.event_type) is not DownloadEventType or event.ticker != request.ticker:
            raise _InvariantError("event type/ticker drift")
        if state.pipeline_result is not None:
            raise _InvariantError("event after pipeline terminal")
        if event.event_type is DownloadEventType.PIPELINE_STARTED:
            if state.pipeline_started or state.started or state.terminals:
                raise _InvariantError("duplicate or late pipeline_started")
            state.pipeline_started = True
            return
        if not state.pipeline_started:
            raise _InvariantError("event before pipeline_started")
        if event.event_type is DownloadEventType.FILING_STARTED:
            started = _parse_started(event, market=market)
            if started.document_id in state.started or started.document_id in state.terminal_ids:
                raise _InvariantError("duplicate filing_started")
            if started.form_type in state.candidate_forms:
                raise _InvariantError("filing_started conflicts with candidate_not_found")
            if started.form_type not in request.forms or not request.start_date <= started.filing_date <= request.end_date:
                raise _InvariantError("filing_started outside request")
            state.started[started.document_id] = started
            return
        if event.event_type in {
            DownloadEventType.FILE_DOWNLOADED,
            DownloadEventType.FILE_SKIPPED,
            DownloadEventType.FILE_FAILED,
        }:
            if event.document_id is None or event.document_id not in state.started or event.document_id in state.terminal_ids:
                raise _InvariantError("file event is not owned by an active filing")
            return
        if event.event_type in {DownloadEventType.FILING_COMPLETED, DownloadEventType.FILING_FAILED}:
            terminal = _parse_terminal(event)
            candidate = _correlate_terminal(event, terminal, state, request, market=market)
            state.terminals.append(terminal)
            if candidate:
                state.ignored_count += 1
                return
            self._classify_terminal(terminal, state, request)
            return
        if event.event_type is DownloadEventType.PIPELINE_COMPLETED:
            payload = _copy_json_object(event.payload)
            if set(payload) != {"result"}:
                raise _InvariantError("pipeline terminal payload drift")
            state.pipeline_result = _copy_json_object(payload["result"])
            return
        if event.event_type is DownloadEventType.COMPANY_RESOLVED:
            return
        raise _InvariantError("unsupported download event")

    def _classify_terminal(
        self,
        terminal: _TerminalFiling,
        state: _CollectionState,
        request: FinsWorkerSyncRequest,
    ) -> None:
        """把已关联终态分类为下载、复用、忽略或失败。

        Args:
            terminal: 已关联 filing 终态。
            state: 当前有界关联状态。
            request: 当前同步请求。

        Returns:
            无。

        Raises:
            _InvariantError: skip reason、仓储存在性或复用证据不闭合时抛出。
        """

        if terminal.status == "failed":
            state.failed_count += 1
            return
        if terminal.filing_date is None:
            raise _InvariantError("materialized terminal lacks filing date")
        if terminal.status == "downloaded":
            try:
                document = self._verify_document(terminal, request)
            except _DocumentFailure:
                state.failed_count += 1
                return
            state.documents.append(document)
            state.downloaded_count += 1
            return
        reason = terminal.reason_code or terminal.skip_reason
        meta_missing = False
        try:
            self.source_repository.get_source_meta(request.ticker, terminal.document_id, SourceKind.FILING)
        except FileNotFoundError:
            meta_missing = True
        except Exception as exc:
            raise _InvariantError("skipped document meta lookup failed") from exc
        if reason in _IGNORED_REASONS and meta_missing:
            state.ignored_count += 1
            return
        if reason not in _REUSED_REASONS or meta_missing:
            raise _InvariantError("skipped document reason/meta state is not closed")
        try:
            document = self._verify_document(terminal, request)
        except _DocumentFailure as exc:
            raise _InvariantError("reused document verification drift") from exc
        state.documents.append(document)
        state.reused_count += 1

    def _verify_document(
        self,
        terminal: _TerminalFiling,
        request: FinsWorkerSyncRequest,
    ) -> FinsWorkerSourceDocument:
        """读取文档事实并完成 locator 解析与回读验证。

        Args:
            terminal: 已关联且可物化的 filing 终态。
            request: 当前同步请求。

        Returns:
            已验证、无路径的源文档 DTO。

        Raises:
            _DocumentFailure: meta、主源 bytes、locator 或回读事实不闭合时抛出。
        """

        try:
            observed_date = terminal.filing_date
            if observed_date is None:
                raise _DocumentFailure("source document lacks filing date")
            meta = self.source_repository.get_source_meta(request.ticker, terminal.document_id, SourceKind.FILING)
            if type(meta) is not dict:
                raise _DocumentFailure("source meta is not an object")
            if meta.get("ingest_complete") is not True or meta.get("is_deleted") is not False:
                raise _DocumentFailure("source meta is incomplete or deleted")
            if meta.get("ticker") not in {None, request.ticker} or meta.get("document_id") not in {None, terminal.document_id}:
                raise _DocumentFailure("source meta identity drift")
            if meta.get("form_type") != terminal.form_type or meta.get("filing_date") != observed_date.isoformat():
                raise _DocumentFailure("source meta form/date drift")
            if not request.start_date <= observed_date <= request.end_date:
                raise _DocumentFailure("source document is outside request window")
            document_version = meta.get("document_version")
            source_fingerprint = meta.get("source_fingerprint")
            if type(document_version) is not str or not document_version or document_version != document_version.strip():
                raise _DocumentFailure("invalid document_version")
            if type(source_fingerprint) is not str or not is_lower_hex_sha256(source_fingerprint):
                raise _DocumentFailure("invalid source_fingerprint")
            source = self.source_repository.get_primary_source(
                request.ticker,
                terminal.document_id,
                SourceKind.FILING,
            )
            with source.open() as stream:
                content = stream.read()
            if type(content) is not bytes:
                raise _DocumentFailure("primary source did not return bytes")
            content_sha256 = sha256_hex(content)
            locator_request = EvidenceLocatorRequest(
                schema_version=SCHEMA_VERSION,
                repository_id=REPOSITORY_ID,
                ticker=request.ticker,
                document_id=terminal.document_id,
                source_kind=SourceKind.FILING,
                artifact_kind=ArtifactKind.SOURCE,
                document_version=document_version,
                source_fingerprint=source_fingerprint,
                primary_content_sha256=content_sha256,
                locator_kind=LocatorKind.DOCUMENT,
                locator_payload=DocumentLocatorPayload(),
                locator_content_sha256=content_sha256,
            )
            locator = self.evidence_locator_owner.resolve_evidence_locator(locator_request)
            self.evidence_locator_owner.validate_evidence_locator(locator)
            return FinsWorkerSourceDocument(
                document_id=terminal.document_id,
                form_type=terminal.form_type,
                source_observed_date=observed_date,
                locator=locator,
                locator_sha256=sha256_hex(locator.to_json()),
            )
        except _DocumentFailure:
            raise
        except Exception as exc:
            raise _DocumentFailure("document evidence verification failed") from exc


__all__ = [
    "DefaultFinsWorkerSourceSyncRuntime",
    "FinsDownloadPipelineFactoryProtocol",
    "FinsEvidenceLocatorOwnerProtocol",
    "FinsSourceSyncDownloadPipelineProtocol",
]
