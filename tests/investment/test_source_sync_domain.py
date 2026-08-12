"""Source Sync foundation 纯领域契约的直接测试。"""

from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple
from uuid import UUID

import pytest

from dayu.investment.domain.jobs import CanonicalJobDocument, JsonValue, build_canonical_document
from dayu.investment.domain.schedules import ScheduleMisfirePolicy
from dayu.investment.domain.source import SourceSubscriptionId
from dayu.investment.domain.source_sync import (
    FINS_SOURCE_DEFINITION_KEY,
    MAX_SOURCE_DOCUMENT_BYTES,
    MAX_SOURCE_DOCUMENTS,
    SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME,
    SOURCE_EXECUTION_SNAPSHOT_SCHEMA_NAME,
    SOURCE_SYNC_JOB_DESCRIPTOR,
    SOURCE_SYNC_JOB_TYPE,
    SOURCE_SYNC_PAYLOAD_SCHEMA_NAME,
    SOURCE_SYNC_PAYLOAD_SCHEMA_VERSION,
    SOURCE_SYNC_RECEIPT_SCHEMA_NAME,
    SOURCE_SYNC_RESULT_SCHEMA_NAME,
    FinsDisclosureSubscriptionConfig,
    SourceBindingDisposition,
    SourceConnectorKey,
    SourcePollingScheduleRequest,
    SourceServiceInputError,
    SourceServiceUnavailableError,
    SourceSyncEnqueueRequest,
    SourceSyncErrorCode,
    SourceSyncExecutionRejected,
    SourceSyncExecutionRejectionCode,
    SourceSyncOrigin,
    SourceSyncOutcome,
    SourceSyncRepositoryFailure,
    SourceSyncRepositoryFailureCode,
    SourceSyncRequestRejected,
    SourceSyncRequestRejectionCode,
    _decode_source_document,
    _parse_date_text,
    _parse_datetime_text,
    _parse_uuid_text,
    _require_aware_utc,
    _require_canonical_document_size,
    _require_date,
    _require_json_nonnegative_int,
    _require_json_object,
    _require_json_positive_int,
    _require_json_schema_version,
    _require_json_text,
    _require_nonblank,
    _require_nonnegative_int,
    _require_positive_int,
    _require_sha256,
    parse_fins_disclosure_subscription_config,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_NOW = datetime(2026, 8, 12, 9, 30, tzinfo=_UTC)
_SUBSCRIPTION_ID = SourceSubscriptionId("00000000-0000-4000-8000-000000000001")


class _FormsTupleSubclass(NamedTuple):
    """构造必须被 strict config 拒绝的 tuple subclass。"""

    form: str


def _config() -> FinsDisclosureSubscriptionConfig:
    """返回稳定的合法 Fins 配置。"""

    return FinsDisclosureSubscriptionConfig(
        forms=("10-K", "10-Q"),
        lookback_days=30,
        freshness_max_age_days=7,
        failing_after=2,
        disable_after=4,
    )


def _config_json() -> dict[str, JsonValue]:
    """返回配置的 closed JSON shape。"""

    return {
        "forms": ["10-K", "10-Q"],
        "lookback_days": 30,
        "freshness_max_age_days": 7,
        "failing_after": 2,
        "disable_after": 4,
        "max_documents_per_sync": 500,
    }


def _document(*, canonical_bytes: bytes, sha256: str | None = None) -> CanonicalJobDocument:
    """按给定 bytes 构造 decoder 测试文档。"""

    return CanonicalJobDocument(
        schema_name="investment.decoder-test",
        schema_version=1,
        canonical_bytes=canonical_bytes,
        sha256=sha256 or hashlib.sha256(canonical_bytes).hexdigest(),
    )


def test_source_sync_foundation_constants_enums_and_descriptor_are_exact() -> None:
    """Foundation 常量、closed enum 与 handler descriptor 必须精确。"""

    assert SOURCE_SYNC_JOB_TYPE == "investment.source-sync.v1"
    assert SOURCE_SYNC_PAYLOAD_SCHEMA_NAME == "investment.source-sync"
    assert SOURCE_SYNC_PAYLOAD_SCHEMA_VERSION == 1
    assert SOURCE_EXECUTION_SNAPSHOT_SCHEMA_NAME == "investment.source-execution-snapshot"
    assert SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME == "investment.fins-evidence-locator"
    assert SOURCE_SYNC_RECEIPT_SCHEMA_NAME == "investment.source-sync-receipt"
    assert SOURCE_SYNC_RESULT_SCHEMA_NAME == "investment.source-sync-result"
    assert FINS_SOURCE_DEFINITION_KEY == "fins.market-disclosure.v1"
    assert MAX_SOURCE_DOCUMENTS == 500
    assert MAX_SOURCE_DOCUMENT_BYTES == 8_388_608
    assert SOURCE_SYNC_JOB_DESCRIPTOR.job_type == SOURCE_SYNC_JOB_TYPE
    assert SOURCE_SYNC_JOB_DESCRIPTOR.payload_schema_name == SOURCE_SYNC_PAYLOAD_SCHEMA_NAME
    assert SOURCE_SYNC_JOB_DESCRIPTOR.payload_schema_version == 1
    assert SOURCE_SYNC_JOB_DESCRIPTOR.max_attempts == 3
    assert SOURCE_SYNC_JOB_DESCRIPTOR.retry_base_seconds == 30
    assert SOURCE_SYNC_JOB_DESCRIPTOR.retry_max_seconds == 300
    assert SOURCE_SYNC_JOB_DESCRIPTOR.lease_duration_seconds == 900
    assert {member.value for member in SourceConnectorKey} == {
        "fins.market-disclosure.v1",
        "rss.v1",
        "industry-metric.v1",
        "manual.v1",
    }
    assert {member.value for member in SourceSyncOrigin} == {"manual", "scheduled"}
    assert {member.value for member in SourceBindingDisposition} == {"ready", "disabled", "stale"}
    assert {member.value for member in SourceSyncOutcome} == {
        "succeeded",
        "no_change",
        "partial",
        "failed",
        "skipped_disabled",
        "stale_subscription",
    }
    assert {member.value for member in SourceSyncErrorCode} == {
        "unsupported_market",
        "unsupported_form",
        "stale_data",
        "partial_batch",
        "provider_rate_limited",
        "provider_unavailable",
        "fins_invariant",
        "stale_subscription",
    }
    assert {member.value for member in SourceSyncRequestRejectionCode} == {
        "tenant_identity_mismatch",
        "job_lineage_mismatch",
        "payload_hash_mismatch",
        "binding_non_executable",
        "snapshot_mismatch",
        "invalid_input",
        "subscription_not_found",
        "subscription_version_conflict",
        "subscription_state_conflict",
        "health_version_conflict",
        "health_state_conflict",
    }
    assert {member.value for member in SourceSyncExecutionRejectionCode} == {
        "job_not_live",
        "lease_lost",
    }
    assert {member.value for member in SourceSyncRepositoryFailureCode} == {
        "unavailable",
        "transaction_aborted",
        "persisted_invariant",
    }


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (
            SourceSyncRequestRejected(SourceSyncRequestRejectionCode.INVALID_INPUT),
            SourceSyncRequestRejectionCode.INVALID_INPUT,
        ),
        (
            SourceSyncExecutionRejected(SourceSyncExecutionRejectionCode.LEASE_LOST),
            SourceSyncExecutionRejectionCode.LEASE_LOST,
        ),
        (
            SourceSyncRepositoryFailure(SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED),
            SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED,
        ),
        (
            SourceServiceInputError(SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND),
            SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND,
        ),
        (
            SourceServiceUnavailableError(SourceSyncRepositoryFailureCode.UNAVAILABLE),
            SourceSyncRepositoryFailureCode.UNAVAILABLE,
        ),
    ],
)
def test_source_closed_errors_expose_only_the_typed_code(
    error: Exception,
    code: SourceSyncRequestRejectionCode | SourceSyncExecutionRejectionCode | SourceSyncRepositoryFailureCode,
) -> None:
    """Closed error 只能把稳定 code 放入异常正文。"""

    assert vars(error) == {"code": code}
    assert error.args == (code.value,)


def test_fins_config_is_frozen_slots_and_normalizes_forms_to_tuple() -> None:
    """Config 必须 frozen、slots，并只接受精确 typed tuple。"""

    forms = ("10-K", "10-Q")
    config = FinsDisclosureSubscriptionConfig(
        forms=forms,
        lookback_days=30,
        freshness_max_age_days=7,
        failing_after=2,
        disable_after=4,
    )
    assert config.forms == ("10-K", "10-Q")
    assert tuple(field.name for field in fields(config)) == (
        "forms",
        "lookback_days",
        "freshness_max_age_days",
        "failing_after",
        "disable_after",
        "max_documents_per_sync",
    )
    with pytest.raises(FrozenInstanceError):
        setattr(config, "lookback_days", 1)
    invalid_forms = (
        "10-K",
        ["10-K"],
        (form for form in ("10-K",)),
        _FormsTupleSubclass("10-K"),
    )
    for invalid in invalid_forms:
        with pytest.raises(TypeError):
            replace(config, **{"forms": invalid})


@pytest.mark.parametrize(
    "invalid",
    [
        {"forms": ()},
        {"forms": tuple(f"FORM-{index}" for index in range(17))},
        {"forms": ("10-k",)},
        {"forms": ("10-K", "10-K")},
        {"lookback_days": 0},
        {"lookback_days": True},
        {"lookback_days": 3661},
        {"freshness_max_age_days": 3661},
        {"failing_after": 0},
        {"disable_after": 2, "failing_after": 2},
        {"max_documents_per_sync": 0},
        {"max_documents_per_sync": 501},
    ],
)
def test_fins_config_rejects_noncanonical_or_out_of_range_values(
    invalid: dict[str, int | bool | tuple[str, ...]],
) -> None:
    """Config 对数量、form、整数和阈值漂移全部 fail closed。"""

    with pytest.raises((TypeError, ValueError)):
        replace(_config(), **invalid)


def test_config_parser_accepts_only_the_exact_json_shape() -> None:
    """Config parser 接受五必需键与可选 max，并拒绝其它 shape 漂移。"""

    expected = _config()
    assert parse_fins_disclosure_subscription_config(_config_json()) == expected
    omitted = _config_json()
    omitted.pop("max_documents_per_sync")
    assert parse_fins_disclosure_subscription_config(omitted).max_documents_per_sync == 500
    for explicit in (1, 500):
        value = _config_json()
        value["max_documents_per_sync"] = explicit
        assert parse_fins_disclosure_subscription_config(value).max_documents_per_sync == explicit
    for invalid_max in (True, 0, 501):
        value = _config_json()
        value["max_documents_per_sync"] = invalid_max
        with pytest.raises((TypeError, ValueError)):
            parse_fins_disclosure_subscription_config(value)
    for key in (
        "forms",
        "lookback_days",
        "freshness_max_age_days",
        "failing_after",
        "disable_after",
    ):
        missing = _config_json()
        missing.pop(key)
        with pytest.raises(ValueError):
            parse_fins_disclosure_subscription_config(missing)
    unknown = _config_json()
    unknown["ticker"] = "AAPL"
    with pytest.raises(ValueError):
        parse_fins_disclosure_subscription_config(unknown)
    wrong_forms = _config_json()
    wrong_forms["forms"] = "10-K"
    with pytest.raises(ValueError):
        parse_fins_disclosure_subscription_config(wrong_forms)
    wrong_item = _config_json()
    wrong_item["forms"] = ["10-K", " 10-Q"]
    with pytest.raises(ValueError):
        parse_fins_disclosure_subscription_config(wrong_item)
    with pytest.raises(ValueError):
        parse_fins_disclosure_subscription_config(["10-K"])


def test_canonical_document_size_validator_accepts_exact_and_rejects_one_over() -> None:
    """共享 builder size validator 必须接受 exact cap 并拒绝 one-over。"""

    document = build_canonical_document(
        {"schema_version": 1},
        schema_name="investment.source-size-test",
        schema_version=1,
    )
    _require_canonical_document_size(document, max_bytes=len(document.canonical_bytes))
    with pytest.raises(ValueError):
        _require_canonical_document_size(document, max_bytes=len(document.canonical_bytes) - 1)
    with pytest.raises((TypeError, ValueError)):
        _require_canonical_document_size(document, max_bytes=True)


def test_manual_and_schedule_inputs_enforce_versions_times_and_closed_shapes() -> None:
    """Public manual/schedule 输入必须闭合版本、时间与 schedule 字段。"""

    enqueue = SourceSyncEnqueueRequest(
        subscription_id=_SUBSCRIPTION_ID,
        expected_subscription_version=3,
        trigger_id=UUID("00000000-0000-4000-8000-000000000002"),
        available_at=_NOW,
        deadline_at=_NOW + timedelta(minutes=30),
    )
    assert enqueue.expected_subscription_version == 3
    for invalid in (
        {"expected_subscription_version": 0},
        {"expected_subscription_version": True},
        {"available_at": _NOW.replace(tzinfo=None)},
        {"deadline_at": _NOW},
        {"deadline_at": _NOW - timedelta(seconds=1)},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(enqueue, **invalid)

    schedule = SourcePollingScheduleRequest(
        subscription_id=_SUBSCRIPTION_ID,
        expected_subscription_version=3,
        cron_expression="0 6 * * *",
        timezone_name="Asia/Shanghai",
        misfire_policy=ScheduleMisfirePolicy.COALESCE_ONE,
        misfire_grace_seconds=60,
        job_deadline_seconds=600,
    )
    assert schedule.schedule_key is None
    assert replace(schedule, schedule_key="source:daily").schedule_key == "source:daily"
    for invalid in (
        {"expected_subscription_version": 0},
        {"cron_expression": " "},
        {"timezone_name": " UTC"},
        {"misfire_grace_seconds": 0},
        {"job_deadline_seconds": True},
        {"schedule_key": ""},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(schedule, **invalid)


def test_decoder_rejects_schema_cap_encoding_hash_canonical_and_root_drift() -> None:
    """共享 decoder 必须先闭合 schema、cap、UTF-8、hash、canonical 与根类型。"""

    valid = build_canonical_document(
        {"schema_version": 1, "value": "ok"},
        schema_name="investment.decoder-test",
        schema_version=1,
    )
    assert _decode_source_document(
        valid,
        schema_name="investment.decoder-test",
        schema_version=1,
        max_bytes=1024,
    ) == {"schema_version": 1, "value": "ok"}
    with pytest.raises(ValueError):
        _decode_source_document(valid, schema_name="investment.other", schema_version=1, max_bytes=1024)
    with pytest.raises(ValueError):
        _decode_source_document(valid, schema_name="investment.decoder-test", schema_version=2, max_bytes=1024)
    with pytest.raises(ValueError):
        _decode_source_document(
            valid,
            schema_name="investment.decoder-test",
            schema_version=1,
            max_bytes=len(valid.canonical_bytes) - 1,
        )
    with pytest.raises(ValueError):
        _decode_source_document(
            _document(canonical_bytes=b"\xff"),
            schema_name="investment.decoder-test",
            schema_version=1,
            max_bytes=1024,
        )
    with pytest.raises(ValueError):
        _decode_source_document(
            replace(valid, sha256="a" * 64),
            schema_name="investment.decoder-test",
            schema_version=1,
            max_bytes=1024,
        )
    noncanonical = b'{"value": "space"}'
    with pytest.raises(ValueError):
        _decode_source_document(
            _document(canonical_bytes=noncanonical),
            schema_name="investment.decoder-test",
            schema_version=1,
            max_bytes=1024,
        )
    array_document = build_canonical_document(
        ["not-an-object"],
        schema_name="investment.decoder-test",
        schema_version=1,
    )
    with pytest.raises(ValueError):
        _decode_source_document(
            array_document,
            schema_name="investment.decoder-test",
            schema_version=1,
            max_bytes=1024,
        )


def test_shared_scalar_parsers_reject_bool_blank_noncanonical_and_non_utc_values() -> None:
    """Shared typed helpers 必须拒绝 bool、空白、非 canonical 与非 UTC 值。"""

    assert _require_json_object({"key": "value"}, "value") == {"key": "value"}
    assert _require_json_text("value", "value") == "value"
    assert _require_json_positive_int(1, "value") == 1
    assert _require_json_nonnegative_int(0, "value") == 0
    assert _parse_uuid_text("00000000-0000-4000-8000-000000000003", "uuid") == UUID(
        "00000000-0000-4000-8000-000000000003"
    )
    assert _parse_date_text("2026-08-12", "date") == date(2026, 8, 12)
    assert _parse_datetime_text("2026-08-12T09:30:00+00:00", "datetime") == _NOW
    _require_nonblank("value", "value")
    _require_nonnegative_int(0, "value")
    _require_positive_int(1, "value")
    _require_sha256("a" * 64, "hash")
    _require_aware_utc(_NOW, "datetime")
    _require_date(date(2026, 8, 12), "date")
    _require_json_schema_version(1, "schema_version")

    invalid_calls = (
        lambda: _require_json_object([], "value"),
        lambda: _require_json_text(" value", "value"),
        lambda: _require_json_positive_int(True, "value"),
        lambda: _require_json_nonnegative_int(-1, "value"),
        lambda: _require_json_schema_version(True, "schema_version"),
        lambda: _require_json_schema_version(2, "schema_version"),
        lambda: _parse_uuid_text("NOT-A-UUID", "uuid"),
        lambda: _parse_uuid_text("00000000000040008000000000000003", "uuid"),
        lambda: _parse_date_text("2026-8-2", "date"),
        lambda: _parse_datetime_text("2026-08-12T09:30:00", "datetime"),
        lambda: _require_nonblank(" ", "value"),
        lambda: _require_nonnegative_int(True, "value"),
        lambda: _require_positive_int(0, "value"),
        lambda: _require_sha256("A" * 64, "hash"),
        lambda: _require_aware_utc(_NOW.replace(tzinfo=None), "datetime"),
        lambda: _require_date(_NOW, "date"),
    )
    for invalid_call in invalid_calls:
        with pytest.raises((TypeError, ValueError)):
            invalid_call()
