"""Source Sync evidence、terminal candidate 与 receipt/result 契约。

本模块从冻结的 Slice 2.3 WIP 机械拆出 evidence 责任闭包，并唯一拥有
Investment-owned pathless locator、document evidence、provider/no-provider
candidate、connector request/decision 与 durable receipt/result canonical 文档。
模块不导入 Fins，公开边界只暴露纯领域 DTO。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import TypeAlias
from uuid import UUID

from dayu.investment.domain.identifiers import TenantId
from dayu.investment.domain.jobs import CanonicalJobDocument, JsonValue, build_canonical_document
from dayu.investment.domain.source import SourceSubscriptionId
from dayu.investment.domain.source_payload import (
    SourceExecutionSnapshot,
    build_source_execution_snapshot_document,
)
from dayu.investment.domain.source_sync import (
    _CANONICAL_FORM,
    _CANONICAL_TICKER,
    MAX_SOURCE_DOCUMENT_BYTES,
    MAX_SOURCE_DOCUMENTS,
    SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME,
    SOURCE_SYNC_RECEIPT_SCHEMA_NAME,
    SOURCE_SYNC_RESULT_SCHEMA_NAME,
    SourceSyncErrorCode,
    SourceSyncOutcome,
    _decode_source_document,
    _parse_date_text,
    _parse_datetime_text,
    _parse_uuid_text,
    _require_aware_utc,
    _require_canonical_document_size,
    _require_exact_keys,
    _require_exact_type,
    _require_json_nonnegative_int,
    _require_json_object,
    _require_json_schema_version,
    _require_json_text,
    _require_nonblank,
    _require_nonnegative_int,
    _require_sha256,
)

_SENSITIVE_LOCATOR_KEYS = frozenset(
    {
        "path",
        "pathname",
        "file_path",
        "uri",
        "url",
        "bucket",
        "key",
        "handle",
        "credential",
        "secret",
        "token",
    }
)


class SourceNoProviderReason(str, Enum):
    """不调用 provider 的闭合原因。"""

    DISABLED = "disabled"
    BINDING_DRIFT = "binding_drift"


class SourceConnectorSyncAction(str, Enum):
    """Connector 调用的闭合决策。"""

    COMPLETED = "completed"
    CANCELLED = "cancelled"


def build_source_evidence_locator_document(
    *,
    repository_id: str,
    ticker: str,
    document_id: str,
    source_kind: str,
    artifact_kind: str,
    document_version: str,
    source_fingerprint: str,
    primary_content_sha256: str,
    locator_kind: str,
    locator_content_sha256: str,
) -> SourceEvidenceLocatorDocument:
    """构建 Investment-owned pathless locator wrapper。

    Args:
        repository_id: Fins 公共 repository identity。
        ticker: Canonical ticker。
        document_id: Fins 文档 identity。
        source_kind: 必须为 filing。
        artifact_kind: 必须为 source。
        document_version: 文档版本。
        source_fingerprint: Source fingerprint。
        primary_content_sha256: Primary bytes hash。
        locator_kind: 必须为 document。
        locator_content_sha256: Locator content hash。

    Returns:
        已二次校验的 pathless locator document。

    Raises:
        ValueError: 任一字段不满足 closed schema 时抛出。
    """

    document = build_canonical_document(
        {
            "artifact_kind": artifact_kind,
            "document_id": document_id,
            "document_version": document_version,
            "locator_content_sha256": locator_content_sha256,
            "locator_kind": locator_kind,
            "locator_payload": {},
            "primary_content_sha256": primary_content_sha256,
            "repository_id": repository_id,
            "schema_version": 1,
            "source_fingerprint": source_fingerprint,
            "source_kind": source_kind,
            "ticker": ticker,
        },
        schema_name=SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME,
        schema_version=1,
    )
    _require_canonical_document_size(document, max_bytes=MAX_SOURCE_DOCUMENT_BYTES)
    return SourceEvidenceLocatorDocument(document=document)


@dataclass(frozen=True, slots=True)
class SourceEvidenceLocatorDocument:
    """Investment 持有的无路径 Fins evidence locator document。"""

    document: CanonicalJobDocument

    def __post_init__(self) -> None:
        """重算 hash 并 strict parse exact pathless schema。

        Raises:
            TypeError: document 类型非法时抛出。
            ValueError: schema、hash、key 或 identity 漂移时抛出。
        """

        raw = _decode_source_document(
            self.document,
            schema_name=SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME,
            schema_version=1,
            max_bytes=MAX_SOURCE_DOCUMENT_BYTES,
        )
        _validate_source_evidence_locator_value(raw)


def _validate_source_evidence_locator_value(raw: dict[str, JsonValue]) -> None:
    """验证 pathless locator 的 exact JSON shape。

    Args:
        raw: Locator JSON 根对象。

    Raises:
        ValueError: key、固定值或 hash 形态漂移时抛出。
    """

    expected = frozenset(
        {
            "schema_version",
            "repository_id",
            "ticker",
            "document_id",
            "source_kind",
            "artifact_kind",
            "document_version",
            "source_fingerprint",
            "primary_content_sha256",
            "locator_kind",
            "locator_payload",
            "locator_content_sha256",
        }
    )
    _require_exact_keys(raw, expected, "evidence locator")
    _reject_sensitive_locator_keys(raw)
    _require_json_schema_version(raw["schema_version"], "locator schema_version")
    if raw["repository_id"] != "dayu.fins.public.v1":
        raise ValueError("locator repository_id 漂移")
    if raw["source_kind"] != "filing" or raw["artifact_kind"] != "source":
        raise ValueError("locator source/artifact kind 漂移")
    if raw["locator_kind"] != "document":
        raise ValueError("locator kind 必须为 document")
    ticker = _require_json_text(raw["ticker"], "ticker")
    if _CANONICAL_TICKER.fullmatch(ticker) is None:
        raise ValueError("locator ticker 非 canonical")
    _require_json_text(raw["document_id"], "document_id")
    _require_json_text(raw["document_version"], "document_version")
    _require_sha256(_require_json_text(raw["source_fingerprint"], "source_fingerprint"), "source_fingerprint")
    _require_sha256(
        _require_json_text(raw["primary_content_sha256"], "primary_content_sha256"),
        "primary_content_sha256",
    )
    _require_sha256(
        _require_json_text(raw["locator_content_sha256"], "locator_content_sha256"),
        "locator_content_sha256",
    )
    payload = _require_json_object(raw["locator_payload"], "locator_payload")
    if payload:
        raise ValueError("document locator payload 必须是空对象")


def _reject_sensitive_locator_keys(value: JsonValue) -> None:
    """递归拒绝 path/URI/credential 等敏感 key。

    Args:
        value: 待扫描 JSON 值。

    Raises:
        ValueError: 命中敏感 key 时抛出。
    """

    if type(value) is dict:
        for key, nested in value.items():
            if key.lower() in _SENSITIVE_LOCATOR_KEYS:
                raise ValueError("locator 含敏感位置或凭据 key")
            _reject_sensitive_locator_keys(nested)
    elif type(value) is list:
        for nested in value:
            _reject_sensitive_locator_keys(nested)


def _locator_identity(locator: SourceEvidenceLocatorDocument) -> tuple[str, str]:
    """读取已校验 locator 的 ticker/document identity。

    Args:
        locator: Pathless locator document。

    Returns:
        ``(ticker, document_id)``。

    Raises:
        ValueError: locator 文档漂移时抛出。
    """

    raw = _decode_source_document(
        locator.document,
        schema_name=SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME,
        schema_version=1,
        max_bytes=MAX_SOURCE_DOCUMENT_BYTES,
    )
    _validate_source_evidence_locator_value(raw)
    return (
        _require_json_text(raw["ticker"], "ticker"),
        _require_json_text(raw["document_id"], "document_id"),
    )


@dataclass(frozen=True, slots=True)
class SourceDocumentEvidence:
    """一次 Source observation 的单文档 pathless evidence。"""

    document_id: str
    form_type: str
    source_observed_date: date
    locator: SourceEvidenceLocatorDocument
    locator_sha256: str

    def __post_init__(self) -> None:
        """校验 document identity、form/date 与 locator hash。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: identity、hash 或 canonical 形态漂移时抛出。
        """

        _require_nonblank(self.document_id, "document_id")
        if not isinstance(self.form_type, str) or _CANONICAL_FORM.fullmatch(self.form_type) is None:
            raise ValueError("form_type 必须是 canonical uppercase form")
        if type(self.source_observed_date) is not date:
            raise TypeError("source_observed_date 必须是 date")
        if not isinstance(self.locator, SourceEvidenceLocatorDocument):
            raise TypeError("locator 必须是 SourceEvidenceLocatorDocument")
        _require_sha256(self.locator_sha256, "locator_sha256")
        if self.locator_sha256 != self.locator.document.sha256:
            raise ValueError("locator_sha256 必须等于 wrapper document hash")
        _, locator_document_id = _locator_identity(self.locator)
        if locator_document_id != self.document_id:
            raise ValueError("evidence document_id 与 locator 不一致")


def validate_evidence_against_snapshot(
    evidence: SourceDocumentEvidence,
    snapshot: SourceExecutionSnapshot,
) -> None:
    """校验 evidence 与 execution snapshot 的 ticker/form/date identity。

    Args:
        evidence: 单文档 evidence。
        snapshot: 冻结 execution snapshot。

    Raises:
        TypeError: 参数类型非法时抛出。
        ValueError: ticker、form 或日期越界时抛出。
    """

    if not isinstance(evidence, SourceDocumentEvidence):
        raise TypeError("evidence 必须是 SourceDocumentEvidence")
    if not isinstance(snapshot, SourceExecutionSnapshot):
        raise TypeError("snapshot 必须是 SourceExecutionSnapshot")
    ticker, _ = _locator_identity(evidence.locator)
    if ticker != snapshot.canonical_ticker:
        raise ValueError("evidence locator ticker 与 snapshot 不一致")
    if evidence.form_type not in snapshot.binding.config.forms:
        raise ValueError("evidence form 不在 request forms")
    if not snapshot.query_start_date <= evidence.source_observed_date <= snapshot.query_end_date:
        raise ValueError("evidence source date 超出 query window")


def _validate_documents(documents: tuple[SourceDocumentEvidence, ...]) -> None:
    """校验文档 tuple 的排序、唯一性与上限。

    Args:
        documents: Evidence tuple。

    Raises:
        TypeError: item 类型非法时抛出。
        ValueError: 排序、唯一性或数量非法时抛出。
    """

    if len(documents) > MAX_SOURCE_DOCUMENTS:
        raise ValueError("documents 不得超过 500")
    keys: list[tuple[str, str, date]] = []
    ids: list[str] = []
    for document in documents:
        if not isinstance(document, SourceDocumentEvidence):
            raise TypeError("documents item 必须是 SourceDocumentEvidence")
        keys.append((document.document_id, document.form_type, document.source_observed_date))
        ids.append(document.document_id)
    if keys != sorted(keys) or len(set(keys)) != len(keys):
        raise ValueError("documents 必须按 identity 严格排序")
    if len(set(ids)) != len(ids):
        raise ValueError("document_id 必须唯一")


@dataclass(frozen=True, slots=True)
class SourceFinsTerminalCandidate:
    """Connector 可提交给 repository 的 closed Fins terminal candidate。"""

    proposed_outcome: SourceSyncOutcome
    proposed_safe_error_code: SourceSyncErrorCode | None
    documents: tuple[SourceDocumentEvidence, ...]
    records_discovered: int
    records_downloaded: int
    records_reused: int
    records_ignored: int
    records_failed: int
    latest_source_observed_date: date | None

    def __post_init__(self) -> None:
        """校验 outcome/error/count/documents 的 exact matrix。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: 任一跨字段组合不闭合时抛出。
        """

        if not isinstance(self.proposed_outcome, SourceSyncOutcome):
            raise TypeError("proposed_outcome 必须是 SourceSyncOutcome")
        if self.proposed_safe_error_code is not None and not isinstance(
            self.proposed_safe_error_code,
            SourceSyncErrorCode,
        ):
            raise TypeError("proposed_safe_error_code 类型非法")
        documents = tuple(self.documents)
        object.__setattr__(self, "documents", documents)
        _validate_documents(documents)
        for name, count in (
            ("records_discovered", self.records_discovered),
            ("records_downloaded", self.records_downloaded),
            ("records_reused", self.records_reused),
            ("records_ignored", self.records_ignored),
            ("records_failed", self.records_failed),
        ):
            _require_nonnegative_int(count, name)
        if self.records_discovered != (
            self.records_downloaded + self.records_reused + self.records_ignored + self.records_failed
        ):
            raise ValueError("records_discovered 必须等于分类计数之和")
        if len(documents) != self.records_downloaded + self.records_reused:
            raise ValueError("documents 数量必须等于 downloaded+reused")
        expected_latest = max((item.source_observed_date for item in documents), default=None)
        if self.latest_source_observed_date != expected_latest:
            raise ValueError("latest_source_observed_date 必须精确等于 documents 最大日期")
        _validate_fins_candidate_shape(self)


def _validate_fins_candidate_shape(candidate: SourceFinsTerminalCandidate) -> None:
    """验证 Fins candidate 的 outcome-specific closed shape。

    Args:
        candidate: 待校验 candidate。

    Raises:
        ValueError: outcome/error/count/documents 组合非法时抛出。
    """

    outcome = candidate.proposed_outcome
    error = candidate.proposed_safe_error_code
    if outcome is SourceSyncOutcome.SUCCEEDED:
        if not candidate.documents or error is not None or candidate.records_failed != 0:
            raise ValueError("succeeded candidate shape 非法")
        return
    if outcome is SourceSyncOutcome.NO_CHANGE:
        if (
            candidate.documents
            or error is not None
            or candidate.records_downloaded != 0
            or candidate.records_reused != 0
            or candidate.records_failed != 0
        ):
            raise ValueError("no_change candidate shape 非法")
        return
    if outcome is SourceSyncOutcome.PARTIAL:
        if not candidate.documents or error is not SourceSyncErrorCode.PARTIAL_BATCH or candidate.records_failed <= 0:
            raise ValueError("partial candidate shape 非法")
        return
    if outcome is not SourceSyncOutcome.FAILED:
        raise ValueError("connector candidate 不得提出 disabled/stale outcome")
    allowed = frozenset(
        {
            SourceSyncErrorCode.UNSUPPORTED_MARKET,
            SourceSyncErrorCode.UNSUPPORTED_FORM,
            SourceSyncErrorCode.PROVIDER_RATE_LIMITED,
            SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
            SourceSyncErrorCode.FINS_INVARIANT,
        }
    )
    if error not in allowed or candidate.documents:
        raise ValueError("failed candidate error/documents shape 非法")
    if error is SourceSyncErrorCode.PROVIDER_UNAVAILABLE:
        if candidate.records_downloaded != 0 or candidate.records_reused != 0:
            raise ValueError("provider_unavailable 不得有 verified documents")
        return
    if candidate.records_discovered != 0:
        raise ValueError("该 failed candidate 必须全计数为零")


@dataclass(frozen=True, slots=True)
class SourceNoProviderTerminalCandidate:
    """不进入 Fins 的 closed terminal candidate。"""

    reason: SourceNoProviderReason

    def __post_init__(self) -> None:
        """校验 no-provider reason 属于闭合集合。

        Raises:
            TypeError: reason 类型非法时抛出。
        """

        if not isinstance(self.reason, SourceNoProviderReason):
            raise TypeError("reason 必须是 SourceNoProviderReason")


SourceTerminalCandidate: TypeAlias = SourceFinsTerminalCandidate | SourceNoProviderTerminalCandidate
"""Repository terminal candidate 的 closed union。"""


@dataclass(frozen=True, slots=True)
class SourceConnectorSyncRequest:
    """Investment connector 的 strict execution 请求。"""

    operation_id: UUID
    execution_snapshot: SourceExecutionSnapshot
    execution_snapshot_sha256: str

    def __post_init__(self) -> None:
        """校验 operation identity 与 snapshot canonical hash。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: snapshot hash 漂移时抛出。
        """

        _require_exact_type(self.operation_id, UUID, "operation_id")
        if not isinstance(self.execution_snapshot, SourceExecutionSnapshot):
            raise TypeError("execution_snapshot 必须是 SourceExecutionSnapshot")
        _require_sha256(self.execution_snapshot_sha256, "execution_snapshot_sha256")
        expected = build_source_execution_snapshot_document(self.execution_snapshot).sha256
        if self.execution_snapshot_sha256 != expected:
            raise ValueError("execution_snapshot_sha256 漂移")


@dataclass(frozen=True, slots=True)
class SourceConnectorSyncDecision:
    """Investment connector 的 completed/cancelled closed 决策。"""

    action: SourceConnectorSyncAction
    candidate: SourceFinsTerminalCandidate | None

    def __post_init__(self) -> None:
        """校验 action 与 candidate presence matrix。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: presence matrix 非法时抛出。
        """

        if not isinstance(self.action, SourceConnectorSyncAction):
            raise TypeError("action 必须是 SourceConnectorSyncAction")
        if self.action is SourceConnectorSyncAction.COMPLETED:
            if not isinstance(self.candidate, SourceFinsTerminalCandidate):
                raise ValueError("completed 必须携带 Fins candidate")
        elif self.candidate is not None:
            raise ValueError("cancelled candidate 必须为 None")


@dataclass(frozen=True, slots=True)
class SourceSyncAttemptReceipt:
    """一次 producer attempt 的 immutable Source Sync 收据。"""

    tenant_id: TenantId
    source_sync_run_id: UUID
    subscription_id: SourceSubscriptionId
    job_id: UUID
    producer_attempt_id: UUID
    payload_sha256: str
    execution_snapshot_sha256: str
    outcome: SourceSyncOutcome
    retry_recommended: bool
    documents: tuple[SourceDocumentEvidence, ...]
    records_discovered: int
    records_ingested: int
    records_downloaded: int
    records_reused: int
    records_ignored: int
    records_failed: int
    latest_source_observed_date: date | None
    safe_error_code: SourceSyncErrorCode | None
    started_at: datetime
    finished_at: datetime
    latency_ms: int
    receipt: CanonicalJobDocument

    def __post_init__(self) -> None:
        """校验收据字段、outcome matrix 与 canonical bytes。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: identity、计数、时间或 canonical 文档漂移时抛出。
        """

        documents = tuple(self.documents)
        object.__setattr__(self, "documents", documents)
        _validate_source_sync_attempt_receipt_fields(self)
        raw = _decode_source_document(
            self.receipt,
            schema_name=SOURCE_SYNC_RECEIPT_SCHEMA_NAME,
            schema_version=1,
            max_bytes=MAX_SOURCE_DOCUMENT_BYTES,
        )
        _require_json_schema_version(raw.get("schema_version"), "receipt schema_version")
        if raw != _source_sync_attempt_receipt_value(self):
            raise ValueError("receipt canonical bytes 与 outer fields 不一致")


@dataclass(frozen=True, slots=True)
class SourceSyncResult:
    """Durable Job 使用的最小 Source Sync canonical result。"""

    outcome: SourceSyncOutcome
    source_sync_run_id: UUID
    producer_attempt_id: UUID
    source_receipt_sha256: str
    retry_recommended: bool
    result: CanonicalJobDocument

    def __post_init__(self) -> None:
        """校验 result identity、hash 与 canonical body。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: hash、bool 或 canonical 文档漂移时抛出。
        """

        if not isinstance(self.outcome, SourceSyncOutcome):
            raise TypeError("outcome 必须是 SourceSyncOutcome")
        _require_exact_type(self.source_sync_run_id, UUID, "source_sync_run_id")
        _require_exact_type(self.producer_attempt_id, UUID, "producer_attempt_id")
        _require_sha256(self.source_receipt_sha256, "source_receipt_sha256")
        if type(self.retry_recommended) is not bool:
            raise TypeError("retry_recommended 必须是 bool")
        raw = _decode_source_document(
            self.result,
            schema_name=SOURCE_SYNC_RESULT_SCHEMA_NAME,
            schema_version=1,
            max_bytes=MAX_SOURCE_DOCUMENT_BYTES,
        )
        _require_json_schema_version(raw.get("schema_version"), "result schema_version")
        if raw != _source_sync_result_value(self):
            raise ValueError("result canonical bytes 与 outer fields 不一致")


def _validate_source_sync_attempt_receipt_fields(receipt: SourceSyncAttemptReceipt) -> None:
    """验证 receipt 的 identity、count、time 与 outcome matrix。

    Args:
        receipt: 待验证收据。

    Raises:
        TypeError: 字段类型非法时抛出。
        ValueError: 跨字段矩阵非法时抛出。
    """

    if not isinstance(receipt.tenant_id, TenantId):
        raise TypeError("tenant_id 必须是 TenantId")
    for label, value in (
        ("source_sync_run_id", receipt.source_sync_run_id),
        ("job_id", receipt.job_id),
        ("producer_attempt_id", receipt.producer_attempt_id),
    ):
        _require_exact_type(value, UUID, label)
    if not isinstance(receipt.subscription_id, SourceSubscriptionId):
        raise TypeError("subscription_id 必须是 SourceSubscriptionId")
    _require_sha256(receipt.payload_sha256, "payload_sha256")
    _require_sha256(receipt.execution_snapshot_sha256, "execution_snapshot_sha256")
    if not isinstance(receipt.outcome, SourceSyncOutcome):
        raise TypeError("outcome 必须是 SourceSyncOutcome")
    if type(receipt.retry_recommended) is not bool:
        raise TypeError("retry_recommended 必须是 bool")
    documents = receipt.documents
    _validate_documents(documents)
    for label, value in (
        ("records_discovered", receipt.records_discovered),
        ("records_ingested", receipt.records_ingested),
        ("records_downloaded", receipt.records_downloaded),
        ("records_reused", receipt.records_reused),
        ("records_ignored", receipt.records_ignored),
        ("records_failed", receipt.records_failed),
        ("latency_ms", receipt.latency_ms),
    ):
        _require_nonnegative_int(value, label)
    if receipt.records_discovered != (
        receipt.records_downloaded + receipt.records_reused + receipt.records_ignored + receipt.records_failed
    ):
        raise ValueError("records_discovered 必须等于分类计数之和")
    if receipt.records_ingested != receipt.records_downloaded + receipt.records_reused:
        raise ValueError("records_ingested 必须等于 downloaded+reused")
    if len(documents) != receipt.records_ingested:
        raise ValueError("documents 数量必须等于 records_ingested")
    expected_latest = max((item.source_observed_date for item in documents), default=None)
    if receipt.latest_source_observed_date != expected_latest:
        raise ValueError("latest_source_observed_date 必须精确等于 evidence 最大日期")
    if receipt.safe_error_code is not None and not isinstance(receipt.safe_error_code, SourceSyncErrorCode):
        raise TypeError("safe_error_code 类型非法")
    _require_aware_utc(receipt.started_at, "started_at")
    _require_aware_utc(receipt.finished_at, "finished_at")
    if receipt.finished_at < receipt.started_at:
        raise ValueError("finished_at 不得早于 started_at")
    expected_latency = int((receipt.finished_at - receipt.started_at) / timedelta(milliseconds=1))
    if receipt.latency_ms != expected_latency:
        raise ValueError("latency_ms 必须等于执行区间截断毫秒")
    _validate_receipt_outcome_shape(receipt)


def _validate_receipt_outcome_shape(receipt: SourceSyncAttemptReceipt) -> None:
    """验证 receipt 的 outcome/error/retry/count 闭合矩阵。

    Args:
        receipt: 已通过基础校验的收据。

    Raises:
        ValueError: outcome shape 非法时抛出。
    """

    outcome = receipt.outcome
    error = receipt.safe_error_code
    if outcome is SourceSyncOutcome.SUCCEEDED:
        valid = (
            error is None
            and not receipt.retry_recommended
            and receipt.records_ingested > 0
            and receipt.records_failed == 0
        )
    elif outcome is SourceSyncOutcome.NO_CHANGE:
        valid = (
            error is None
            and not receipt.retry_recommended
            and receipt.records_ingested == 0
            and receipt.records_failed == 0
        )
    elif outcome is SourceSyncOutcome.PARTIAL:
        valid = (
            error is SourceSyncErrorCode.PARTIAL_BATCH
            and receipt.retry_recommended
            and receipt.records_ingested > 0
            and receipt.records_failed > 0
        )
    elif outcome is SourceSyncOutcome.SKIPPED_DISABLED:
        valid = error is None and not receipt.retry_recommended and receipt.records_discovered == 0
    elif outcome is SourceSyncOutcome.STALE_SUBSCRIPTION:
        valid = (
            error is SourceSyncErrorCode.STALE_SUBSCRIPTION
            and not receipt.retry_recommended
            and receipt.records_discovered == 0
        )
    else:
        valid = _validate_failed_receipt_shape(receipt)
    if not valid:
        raise ValueError("receipt outcome/error/retry/count shape 非法")


def _validate_failed_receipt_shape(receipt: SourceSyncAttemptReceipt) -> bool:
    """判断 failed receipt 是否属于闭合矩阵。

    Args:
        receipt: Failed outcome 收据。

    Returns:
        组合合法时返回 ``True``。

    Raises:
        无。
    """

    error = receipt.safe_error_code
    allowed = frozenset(
        {
            SourceSyncErrorCode.UNSUPPORTED_MARKET,
            SourceSyncErrorCode.UNSUPPORTED_FORM,
            SourceSyncErrorCode.STALE_DATA,
            SourceSyncErrorCode.PROVIDER_RATE_LIMITED,
            SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
            SourceSyncErrorCode.FINS_INVARIANT,
        }
    )
    if error not in allowed:
        return False
    if receipt.retry_recommended != (
        error in {SourceSyncErrorCode.PROVIDER_RATE_LIMITED, SourceSyncErrorCode.PROVIDER_UNAVAILABLE}
    ):
        return False
    if error is SourceSyncErrorCode.STALE_DATA:
        return receipt.records_ingested > 0
    if receipt.records_ingested != 0:
        return False
    if error is SourceSyncErrorCode.PROVIDER_UNAVAILABLE:
        return True
    return receipt.records_discovered == 0


def _evidence_value(evidence: SourceDocumentEvidence) -> dict[str, JsonValue]:
    """把 document evidence 投影为 receipt JSON 对象。

    Args:
        evidence: Strict evidence DTO。

    Returns:
        Closed JSON 对象。

    Raises:
        ValueError: Locator canonical 文档漂移时抛出。
    """

    locator = _decode_source_document(
        evidence.locator.document,
        schema_name=SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME,
        schema_version=1,
        max_bytes=MAX_SOURCE_DOCUMENT_BYTES,
    )
    return {
        "document_id": evidence.document_id,
        "form_type": evidence.form_type,
        "locator": locator,
        "locator_sha256": evidence.locator_sha256,
        "source_observed_date": evidence.source_observed_date.isoformat(),
    }


def _source_sync_attempt_receipt_value(receipt: SourceSyncAttemptReceipt) -> dict[str, JsonValue]:
    """把完整 receipt DTO 投影为 canonical JSON body。

    Args:
        receipt: Strict receipt DTO。

    Returns:
        不含 tenant 与自身 wrapper 的 closed JSON body。

    Raises:
        ValueError: Nested evidence 漂移时抛出。
    """

    return {
        "documents": [_evidence_value(item) for item in receipt.documents],
        "execution_snapshot_sha256": receipt.execution_snapshot_sha256,
        "finished_at": receipt.finished_at.isoformat(),
        "job_id": str(receipt.job_id),
        "latest_source_observed_date": (
            receipt.latest_source_observed_date.isoformat() if receipt.latest_source_observed_date is not None else None
        ),
        "latency_ms": receipt.latency_ms,
        "outcome": receipt.outcome.value,
        "payload_sha256": receipt.payload_sha256,
        "producer_attempt_id": str(receipt.producer_attempt_id),
        "records_discovered": receipt.records_discovered,
        "records_downloaded": receipt.records_downloaded,
        "records_ignored": receipt.records_ignored,
        "records_ingested": receipt.records_ingested,
        "records_reused": receipt.records_reused,
        "records_failed": receipt.records_failed,
        "retry_recommended": receipt.retry_recommended,
        "safe_error_code": receipt.safe_error_code.value if receipt.safe_error_code is not None else None,
        "schema_version": 1,
        "source_sync_run_id": str(receipt.source_sync_run_id),
        "started_at": receipt.started_at.isoformat(),
        "subscription_id": str(receipt.subscription_id),
    }


def _source_sync_result_value(result: SourceSyncResult) -> dict[str, JsonValue]:
    """把 result DTO 投影为 canonical JSON body。

    Args:
        result: Strict result DTO。

    Returns:
        六字段 closed JSON body。

    Raises:
        无。
    """

    return {
        "outcome": result.outcome.value,
        "producer_attempt_id": str(result.producer_attempt_id),
        "retry_recommended": result.retry_recommended,
        "schema_version": 1,
        "source_receipt_sha256": result.source_receipt_sha256,
        "source_sync_run_id": str(result.source_sync_run_id),
    }


def build_source_sync_attempt_receipt(
    *,
    tenant_id: TenantId,
    source_sync_run_id: UUID,
    subscription_id: SourceSubscriptionId,
    job_id: UUID,
    producer_attempt_id: UUID,
    payload_sha256: str,
    execution_snapshot_sha256: str,
    outcome: SourceSyncOutcome,
    retry_recommended: bool,
    documents: tuple[SourceDocumentEvidence, ...],
    records_discovered: int,
    records_ingested: int,
    records_downloaded: int,
    records_reused: int,
    records_ignored: int,
    records_failed: int,
    latest_source_observed_date: date | None,
    safe_error_code: SourceSyncErrorCode | None,
    started_at: datetime,
    finished_at: datetime,
    latency_ms: int,
) -> SourceSyncAttemptReceipt:
    """构建 Source Sync receipt 的唯一 canonical representation。

    Args:
        tenant_id: 租户标识。
        source_sync_run_id: Source run UUID。
        subscription_id: Subscription 强标识。
        job_id: Producer Job UUID。
        producer_attempt_id: Producer attempt UUID。
        payload_sha256: Durable payload hash。
        execution_snapshot_sha256: Frozen snapshot hash。
        outcome: Source observation outcome。
        retry_recommended: 运营重试建议。
        documents: Verified pathless evidence tuple。
        records_discovered: 总发现数。
        records_ingested: 下载与复用总数。
        records_downloaded: 下载数。
        records_reused: 复用数。
        records_ignored: 忽略数。
        records_failed: 失败数。
        latest_source_observed_date: 最新 source calendar date。
        safe_error_code: 可空 closed error。
        started_at: Producer generation 开始时刻。
        finished_at: Authoritative terminal 时刻。
        latency_ms: 截断非负毫秒延迟。

    Returns:
        完整 immutable receipt。

    Raises:
        TypeError: 字段类型非法时抛出。
        ValueError: 字段或 outcome matrix 非法时抛出。
    """

    if not isinstance(outcome, SourceSyncOutcome):
        raise TypeError("outcome 必须是 SourceSyncOutcome")
    if safe_error_code is not None and not isinstance(safe_error_code, SourceSyncErrorCode):
        raise TypeError("safe_error_code 类型非法")
    documents = tuple(documents)
    _validate_documents(documents)
    if latest_source_observed_date is not None and type(latest_source_observed_date) is not date:
        raise TypeError("latest_source_observed_date 必须是 date 或 None")
    _require_aware_utc(started_at, "started_at")
    _require_aware_utc(finished_at, "finished_at")
    value: dict[str, JsonValue] = {
        "documents": [_evidence_value(item) for item in documents],
        "execution_snapshot_sha256": execution_snapshot_sha256,
        "finished_at": finished_at.isoformat(),
        "job_id": str(job_id),
        "latest_source_observed_date": (
            latest_source_observed_date.isoformat() if latest_source_observed_date is not None else None
        ),
        "latency_ms": latency_ms,
        "outcome": outcome.value,
        "payload_sha256": payload_sha256,
        "producer_attempt_id": str(producer_attempt_id),
        "records_discovered": records_discovered,
        "records_downloaded": records_downloaded,
        "records_failed": records_failed,
        "records_ignored": records_ignored,
        "records_ingested": records_ingested,
        "records_reused": records_reused,
        "retry_recommended": retry_recommended,
        "safe_error_code": safe_error_code.value if safe_error_code is not None else None,
        "schema_version": 1,
        "source_sync_run_id": str(source_sync_run_id),
        "started_at": started_at.isoformat(),
        "subscription_id": str(subscription_id),
    }
    canonical = build_canonical_document(
        value,
        schema_name=SOURCE_SYNC_RECEIPT_SCHEMA_NAME,
        schema_version=1,
    )
    _require_canonical_document_size(canonical, max_bytes=MAX_SOURCE_DOCUMENT_BYTES)
    return SourceSyncAttemptReceipt(
        tenant_id=tenant_id,
        source_sync_run_id=source_sync_run_id,
        subscription_id=subscription_id,
        job_id=job_id,
        producer_attempt_id=producer_attempt_id,
        payload_sha256=payload_sha256,
        execution_snapshot_sha256=execution_snapshot_sha256,
        outcome=outcome,
        retry_recommended=retry_recommended,
        documents=documents,
        records_discovered=records_discovered,
        records_ingested=records_ingested,
        records_downloaded=records_downloaded,
        records_reused=records_reused,
        records_ignored=records_ignored,
        records_failed=records_failed,
        latest_source_observed_date=latest_source_observed_date,
        safe_error_code=safe_error_code,
        started_at=started_at,
        finished_at=finished_at,
        latency_ms=latency_ms,
        receipt=canonical,
    )


def parse_source_sync_attempt_receipt(
    *,
    tenant_id: TenantId,
    receipt: CanonicalJobDocument,
) -> SourceSyncAttemptReceipt:
    """严格解析持久化 Source Sync receipt。

    Args:
        tenant_id: Repository outer tenant identity。
        receipt: 持久化 canonical receipt document。

    Returns:
        完整 immutable receipt DTO。

    Raises:
        TypeError: tenant 或 document 类型非法时抛出。
        ValueError: canonical shape 或字段矩阵漂移时抛出。
    """

    if not isinstance(tenant_id, TenantId):
        raise TypeError("tenant_id 必须是 TenantId")
    raw = _decode_source_document(
        receipt,
        schema_name=SOURCE_SYNC_RECEIPT_SCHEMA_NAME,
        schema_version=1,
        max_bytes=MAX_SOURCE_DOCUMENT_BYTES,
    )
    _require_exact_keys(raw, _RECEIPT_KEYS, "source sync receipt")
    documents = _parse_evidence_list(raw["documents"])
    latest_raw = raw["latest_source_observed_date"]
    latest = None if latest_raw is None else _parse_date_text(latest_raw, "latest_source_observed_date")
    error_raw = raw["safe_error_code"]
    try:
        error = None if error_raw is None else SourceSyncErrorCode(_require_json_text(error_raw, "safe_error_code"))
        outcome = SourceSyncOutcome(_require_json_text(raw["outcome"], "outcome"))
    except ValueError:
        raise ValueError("receipt closed enum 非法") from None
    retry = raw["retry_recommended"]
    if type(retry) is not bool:
        raise ValueError("retry_recommended 必须是 bool")
    return SourceSyncAttemptReceipt(
        tenant_id=tenant_id,
        source_sync_run_id=_parse_uuid_text(raw["source_sync_run_id"], "source_sync_run_id"),
        subscription_id=SourceSubscriptionId(_require_json_text(raw["subscription_id"], "subscription_id")),
        job_id=_parse_uuid_text(raw["job_id"], "job_id"),
        producer_attempt_id=_parse_uuid_text(raw["producer_attempt_id"], "producer_attempt_id"),
        payload_sha256=_require_json_text(raw["payload_sha256"], "payload_sha256"),
        execution_snapshot_sha256=_require_json_text(
            raw["execution_snapshot_sha256"],
            "execution_snapshot_sha256",
        ),
        outcome=outcome,
        retry_recommended=retry,
        documents=documents,
        records_discovered=_require_json_nonnegative_int(raw["records_discovered"], "records_discovered"),
        records_ingested=_require_json_nonnegative_int(raw["records_ingested"], "records_ingested"),
        records_downloaded=_require_json_nonnegative_int(raw["records_downloaded"], "records_downloaded"),
        records_reused=_require_json_nonnegative_int(raw["records_reused"], "records_reused"),
        records_ignored=_require_json_nonnegative_int(raw["records_ignored"], "records_ignored"),
        records_failed=_require_json_nonnegative_int(raw["records_failed"], "records_failed"),
        latest_source_observed_date=latest,
        safe_error_code=error,
        started_at=_parse_datetime_text(raw["started_at"], "started_at"),
        finished_at=_parse_datetime_text(raw["finished_at"], "finished_at"),
        latency_ms=_require_json_nonnegative_int(raw["latency_ms"], "latency_ms"),
        receipt=receipt,
    )


def build_source_sync_result(receipt: SourceSyncAttemptReceipt) -> SourceSyncResult:
    """从完整 receipt 唯一派生 durable Job result。

    Args:
        receipt: 已验证 Source receipt。

    Returns:
        六字段 canonical Source result。

    Raises:
        TypeError: receipt 类型非法时抛出。
    """

    if not isinstance(receipt, SourceSyncAttemptReceipt):
        raise TypeError("receipt 必须是 SourceSyncAttemptReceipt")
    value: dict[str, JsonValue] = {
        "outcome": receipt.outcome.value,
        "producer_attempt_id": str(receipt.producer_attempt_id),
        "retry_recommended": receipt.retry_recommended,
        "schema_version": 1,
        "source_receipt_sha256": receipt.receipt.sha256,
        "source_sync_run_id": str(receipt.source_sync_run_id),
    }
    document = build_canonical_document(
        value,
        schema_name=SOURCE_SYNC_RESULT_SCHEMA_NAME,
        schema_version=1,
    )
    _require_canonical_document_size(document, max_bytes=MAX_SOURCE_DOCUMENT_BYTES)
    return SourceSyncResult(
        outcome=receipt.outcome,
        source_sync_run_id=receipt.source_sync_run_id,
        producer_attempt_id=receipt.producer_attempt_id,
        source_receipt_sha256=receipt.receipt.sha256,
        retry_recommended=receipt.retry_recommended,
        result=document,
    )


def parse_source_sync_result(result: CanonicalJobDocument) -> SourceSyncResult:
    """严格解析持久化 Source Sync Job result。

    Args:
        result: 持久化 canonical result document。

    Returns:
        Strict Source result DTO。

    Raises:
        ValueError: schema、hash、keys 或字段形态非法时抛出。
    """

    raw = _decode_source_document(
        result,
        schema_name=SOURCE_SYNC_RESULT_SCHEMA_NAME,
        schema_version=1,
        max_bytes=MAX_SOURCE_DOCUMENT_BYTES,
    )
    _require_exact_keys(
        raw,
        frozenset(
            {
                "schema_version",
                "outcome",
                "source_sync_run_id",
                "producer_attempt_id",
                "source_receipt_sha256",
                "retry_recommended",
            }
        ),
        "source sync result",
    )
    _require_json_schema_version(raw["schema_version"], "result schema_version")
    try:
        outcome = SourceSyncOutcome(_require_json_text(raw["outcome"], "outcome"))
    except ValueError:
        raise ValueError("result outcome 非法") from None
    retry = raw["retry_recommended"]
    if type(retry) is not bool:
        raise ValueError("retry_recommended 必须是 bool")
    return SourceSyncResult(
        outcome=outcome,
        source_sync_run_id=_parse_uuid_text(raw["source_sync_run_id"], "source_sync_run_id"),
        producer_attempt_id=_parse_uuid_text(raw["producer_attempt_id"], "producer_attempt_id"),
        source_receipt_sha256=_require_json_text(raw["source_receipt_sha256"], "source_receipt_sha256"),
        retry_recommended=retry,
        result=result,
    )


def _parse_evidence_list(value: JsonValue) -> tuple[SourceDocumentEvidence, ...]:
    """解析 receipt 内的 evidence JSON array。

    Args:
        value: Receipt documents 字段。

    Returns:
        Strict evidence tuple。

    Raises:
        ValueError: array、item 或 locator shape 非法时抛出。
    """

    if type(value) is not list:
        raise ValueError("documents 必须是 JSON array")
    parsed: list[SourceDocumentEvidence] = []
    for item in value:
        raw = _require_json_object(item, "document evidence")
        _require_exact_keys(
            raw,
            frozenset({"document_id", "form_type", "source_observed_date", "locator", "locator_sha256"}),
            "document evidence",
        )
        locator_value = _require_json_object(raw["locator"], "locator")
        locator_document = build_canonical_document(
            locator_value,
            schema_name=SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME,
            schema_version=1,
        )
        parsed.append(
            SourceDocumentEvidence(
                document_id=_require_json_text(raw["document_id"], "document_id"),
                form_type=_require_json_text(raw["form_type"], "form_type"),
                source_observed_date=_parse_date_text(raw["source_observed_date"], "source_observed_date"),
                locator=SourceEvidenceLocatorDocument(document=locator_document),
                locator_sha256=_require_json_text(raw["locator_sha256"], "locator_sha256"),
            )
        )
    return tuple(parsed)


_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "source_sync_run_id",
        "subscription_id",
        "job_id",
        "producer_attempt_id",
        "payload_sha256",
        "execution_snapshot_sha256",
        "outcome",
        "retry_recommended",
        "documents",
        "records_discovered",
        "records_ingested",
        "records_downloaded",
        "records_reused",
        "records_ignored",
        "records_failed",
        "latest_source_observed_date",
        "safe_error_code",
        "started_at",
        "finished_at",
        "latency_ms",
    }
)


__all__ = [
    "SourceConnectorSyncAction",
    "SourceConnectorSyncDecision",
    "SourceConnectorSyncRequest",
    "SourceDocumentEvidence",
    "SourceEvidenceLocatorDocument",
    "SourceFinsTerminalCandidate",
    "SourceNoProviderReason",
    "SourceNoProviderTerminalCandidate",
    "SourceSyncAttemptReceipt",
    "SourceSyncResult",
    "SourceTerminalCandidate",
    "build_source_evidence_locator_document",
    "build_source_sync_attempt_receipt",
    "build_source_sync_result",
    "parse_source_sync_attempt_receipt",
    "parse_source_sync_result",
    "validate_evidence_against_snapshot",
]
