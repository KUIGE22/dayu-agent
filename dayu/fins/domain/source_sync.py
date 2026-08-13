"""面向 worker 的 Fins 源同步纯领域契约。

本模块只暴露规范化且不含路径的 DTO；下载事件 wire 与仓储实现细节始终由
runtime owner 私有持有。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum

from ..ticker_normalization import normalize_ticker
from .evidence_locator import (
    EvidenceLocatorError,
    EvidenceLocatorProjection,
    is_lower_hex_sha256,
    sha256_hex,
    validate_evidence_locator_projection,
)

_MIC = re.compile(r"^[A-Z]{4}$")


def _require_exact_date(value: date, label: str) -> None:
    """要求输入为精确的 ``date`` 实例而非其子类。

    Args:
        value: 待校验日期。
        label: 错误消息中的字段名。

    Returns:
        无。

    Raises:
        TypeError: 输入不是精确 ``date`` 类型时抛出。
    """

    if type(value) is not date:
        raise TypeError(f"{label} must be a date")


def _require_bounded_int(value: int, label: str, *, minimum: int, maximum: int) -> None:
    """要求输入为给定闭区间内的精确整数。

    Args:
        value: 待校验整数。
        label: 错误消息中的字段名。
        minimum: 允许的最小值。
        maximum: 允许的最大值。

    Returns:
        无。

    Raises:
        TypeError: 输入不是精确 ``int`` 类型时抛出。
        ValueError: 输入超出闭区间时抛出。
    """

    if type(value) is not int:
        raise TypeError(f"{label} must be an int")
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")


class FinsWorkerSyncOutcome(str, Enum):
    """Fins gateway 向 worker 暴露的闭集同步结果。"""

    COMPLETE = "complete"
    PARTIAL = "partial"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED_MARKET = "unsupported_market"
    UNSUPPORTED_FORM = "unsupported_form"
    CANCELLED = "cancelled"
    INVARIANT_FAILED = "invariant_failed"


@dataclass(frozen=True, slots=True)
class FinsWorkerSyncRequest:
    """一次有界 worker 源同步的规范请求。"""

    ticker: str
    exchange_mic: str
    forms: tuple[str, ...]
    start_date: date
    end_date: date
    max_documents: int
    max_events: int

    def __post_init__(self) -> None:
        """校验请求字段的类型、规范形态与容量边界。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: ticker、日期或容量字段类型错误时抛出。
            ValueError: ticker、MIC、form、日期窗口或容量边界非法时抛出。
        """

        if type(self.ticker) is not str:
            raise TypeError("ticker must be a string")
        try:
            normalized_ticker = normalize_ticker(self.ticker)
        except ValueError as exc:
            raise ValueError("ticker must be canonical") from exc
        if normalized_ticker.canonical != self.ticker:
            raise ValueError("ticker must be canonical")
        if type(self.exchange_mic) is not str or _MIC.fullmatch(self.exchange_mic) is None:
            raise ValueError("exchange_mic must be a four-character uppercase MIC")
        if type(self.forms) is not tuple or not 1 <= len(self.forms) <= 16:
            raise ValueError("forms must contain between 1 and 16 values")
        if any(type(form) is not str or not form or form != form.strip() for form in self.forms):
            raise ValueError("forms must contain non-empty canonical strings")
        if self.forms != tuple(sorted(set(self.forms))):
            raise ValueError("forms must be strictly sorted and unique")
        _require_exact_date(self.start_date, "start_date")
        _require_exact_date(self.end_date, "end_date")
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        _require_bounded_int(self.max_documents, "max_documents", minimum=1, maximum=500)
        _require_bounded_int(self.max_events, "max_events", minimum=1, maximum=16_064)


@dataclass(frozen=True, slots=True)
class FinsWorkerSourceDocument:
    """返回 Investment adapter 的已验证无路径源文档。"""

    document_id: str
    form_type: str
    source_observed_date: date
    locator: EvidenceLocatorProjection
    locator_sha256: str

    def __post_init__(self) -> None:
        """校验文档身份、日期和证据 locator 的闭合关系。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: locator 或日期类型错误时抛出。
            ValueError:文档字段、locator 或摘要不满足闭合约束时抛出。
        """

        if type(self.document_id) is not str or not self.document_id or self.document_id != self.document_id.strip():
            raise ValueError("document_id must be non-empty and canonical")
        if type(self.form_type) is not str or not self.form_type or self.form_type != self.form_type.strip():
            raise ValueError("form_type must be non-empty and canonical")
        _require_exact_date(self.source_observed_date, "source_observed_date")
        if type(self.locator) is not EvidenceLocatorProjection:
            raise TypeError("locator must be an EvidenceLocatorProjection")
        try:
            validate_evidence_locator_projection(self.locator)
        except EvidenceLocatorError as exc:
            raise ValueError("locator must be a valid EvidenceLocatorProjection") from exc
        if not is_lower_hex_sha256(self.locator_sha256):
            raise ValueError("locator_sha256 must be a lowercase SHA-256")
        if self.locator_sha256 != sha256_hex(self.locator.to_json()):
            raise ValueError("locator_sha256 does not match locator canonical bytes")
        if self.locator.document_id != self.document_id:
            raise ValueError("locator document_id does not match document")


@dataclass(frozen=True, slots=True)
class FinsWorkerSyncResult:
    """一次 worker 源同步的闭合集合结果。"""

    outcome: FinsWorkerSyncOutcome
    documents: tuple[FinsWorkerSourceDocument, ...]
    latest_source_observed_date: date | None
    discovered_count: int
    downloaded_count: int
    reused_count: int
    ignored_count: int
    failed_count: int

    def __post_init__(self) -> None:
        """校验结果文档、计数、日期与 outcome 的整体不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: outcome、documents 或文档成员类型错误时抛出。
            ValueError: 排序、唯一性、计数、日期或 outcome 形态不闭合时抛出。
        """

        if type(self.outcome) is not FinsWorkerSyncOutcome:
            raise TypeError("outcome must be FinsWorkerSyncOutcome")
        if type(self.documents) is not tuple:
            raise TypeError("documents must be a tuple")
        for document in self.documents:
            if type(document) is not FinsWorkerSourceDocument:
                raise TypeError("documents must contain FinsWorkerSourceDocument values")
            document.__post_init__()
        ordered = tuple(sorted(self.documents, key=lambda item: (item.document_id, item.form_type, item.source_observed_date)))
        if self.documents != ordered:
            raise ValueError("documents must be strictly sorted")
        document_ids = tuple(document.document_id for document in self.documents)
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document_id must be unique")
        counts = (
            self.discovered_count,
            self.downloaded_count,
            self.reused_count,
            self.ignored_count,
            self.failed_count,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            raise ValueError("result counts must be non-negative integers")
        if self.discovered_count != sum(counts[1:]):
            raise ValueError("discovered_count must equal classified counts")
        if len(self.documents) != self.downloaded_count + self.reused_count:
            raise ValueError("document count must equal downloaded plus reused")
        latest = max((document.source_observed_date for document in self.documents), default=None)
        if self.latest_source_observed_date != latest:
            raise ValueError("latest_source_observed_date must match documents")
        self._validate_outcome_shape()

    def _validate_outcome_shape(self) -> None:
        """按闭集 outcome 校验允许的文档与计数组合。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: outcome 与文档或计数组合不兼容时抛出。
        """

        all_zero = self.discovered_count == 0
        if self.outcome is FinsWorkerSyncOutcome.COMPLETE:
            if self.failed_count != 0:
                raise ValueError("complete result cannot contain failures")
            return
        if self.outcome is FinsWorkerSyncOutcome.PARTIAL:
            if not self.documents or self.downloaded_count + self.reused_count == 0 or self.failed_count == 0:
                raise ValueError("partial result requires verified documents and failures")
            return
        if self.outcome is FinsWorkerSyncOutcome.UNAVAILABLE:
            if self.documents or self.downloaded_count or self.reused_count:
                raise ValueError("unavailable result cannot contain documents")
            if not all_zero and self.failed_count == 0:
                raise ValueError("correlated unavailable result requires failures")
            return
        if self.outcome in {
            FinsWorkerSyncOutcome.RATE_LIMITED,
            FinsWorkerSyncOutcome.UNSUPPORTED_MARKET,
            FinsWorkerSyncOutcome.UNSUPPORTED_FORM,
            FinsWorkerSyncOutcome.CANCELLED,
            FinsWorkerSyncOutcome.INVARIANT_FAILED,
        } and (self.documents or not all_zero):
            raise ValueError(f"{self.outcome.value} result must be empty")


__all__ = [
    "FinsWorkerSourceDocument",
    "FinsWorkerSyncOutcome",
    "FinsWorkerSyncRequest",
    "FinsWorkerSyncResult",
]
