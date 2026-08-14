"""InvestmentSourcesService recovery、ordering 与 closed error application tests。

本 owner 只使用 pure DTO 与三个同步 recording fake；不导入 execution owner、
connector/Fins concrete、Session、engine 或 PostgreSQL。精确十二个 named tests
分别固定 public protocol/export、manual/schedule recovery、preflight ordering 与
穷尽 typed error mapping。
"""

from __future__ import annotations

import inspect
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TypeAlias, get_type_hints
from uuid import UUID

import pytest

import dayu.services as services_package
from dayu.investment.composition import PlatformSourceSyncServiceProtocol
from dayu.investment.domain.identifiers import (
    CompanyId,
    Principal,
    SecurityId,
    TenantId,
    TenantScope,
)
from dayu.investment.domain.jobs import (
    JobCorrelationInvariantError,
    JobDeadlineExceededError,
    JobEnqueueReceipt,
    JobEnqueueRequest,
    JobGovernanceRequiredError,
    JobHandlerDescriptor,
    JobIdempotencyConflictError,
    JobIdempotencyRecord,
    JobInputError,
    JobLeaseLostError,
    JobNotFoundError,
    JobRepositoryFailureError,
    JobState,
    JobStateConflictError,
    build_canonical_document,
    job_enqueue_request_fingerprint,
)
from dayu.investment.domain.schedules import (
    ScheduleDefinition,
    ScheduleExecutionUnavailableError,
    ScheduleInputError,
    ScheduleInvariantError,
    ScheduleMisfirePolicy,
    ScheduleRegistrationRequest,
    ScheduleRepositoryError,
    ScheduleState,
    ScheduleVersionConflictError,
)
from dayu.investment.domain.source import (
    SourceDefinitionId,
    SourceKind,
    SourceSubscriptionId,
    SubscriptionStatus,
)
from dayu.investment.domain.source_evidence import SourceSyncAttemptReceipt
from dayu.investment.domain.source_health import (
    SourceHealthProjection,
    SourceHealthReenableRequest,
    SourceHealthSnapshotCursor,
    SourceHealthSnapshotPage,
    SourceHealthStatus,
)
from dayu.investment.domain.source_operation import (
    SourceOperationAcquireDecision,
    SourceOperationAcquireRequest,
    SourceTerminalRecordDecision,
    SourceTerminalRecordRequest,
)
from dayu.investment.domain.source_payload import (
    ManualSourceSyncPayload,
    ScheduledSourceSyncPayload,
    SourceExecutionBinding,
    build_manual_source_request_fingerprint,
    build_manual_source_sync_payload_document,
    build_scheduled_source_request_fingerprint,
    build_scheduled_source_sync_payload_document,
    build_source_execution_snapshot,
)
from dayu.investment.domain.source_sync import (
    FINS_SOURCE_DEFINITION_KEY,
    SOURCE_SYNC_JOB_DESCRIPTOR,
    SOURCE_SYNC_PAYLOAD_SCHEMA_NAME,
    FinsDisclosureSubscriptionConfig,
    SourceConnectorKey,
    SourcePollingScheduleRequest,
    SourceServiceInputError,
    SourceServiceUnavailableError,
    SourceSyncEnqueueRequest,
    SourceSyncErrorCode,
    SourceSyncRepositoryFailure,
    SourceSyncRepositoryFailureCode,
    SourceSyncRequestRejected,
    SourceSyncRequestRejectionCode,
)
from dayu.services.investment_sources import (
    InvestmentSourcesService,
    SourceManualJobGatewayProtocol,
    SourceScheduleGatewayProtocol,
)
from dayu.services.protocols import (
    PlatformSourceSyncServiceProtocol as ReExportedPlatformSourceSyncServiceProtocol,
)

NOW = datetime(2026, 8, 14, 9, 30, tzinfo=timezone.utc)
"""稳定测试业务时刻。"""

_DEFAULT_SCHEDULE_KEY_PREFIX = "investment.source-sync.v1"
"""独立断言 production schedule key 公式的固定前缀。"""


class _LostResponseError(RuntimeError):
    """模拟 durable commit 后 caller 未收到 response。"""


class _UnlistedSignal(BaseException):
    """模拟不属于 public closed surface 的控制流信号。"""


class _ForeignRequestCode(str, Enum):
    """模拟值相同但 owner 不同的 request code。"""

    INVALID_INPUT = "invalid_input"


class _ForeignRepositoryCode(str, Enum):
    """模拟值相同但 owner 不同的 repository code。"""

    UNAVAILABLE = "unavailable"


JobGatewayError: TypeAlias = (
    JobIdempotencyConflictError
    | JobInputError
    | JobRepositoryFailureError
    | JobNotFoundError
    | JobStateConflictError
    | JobCorrelationInvariantError
    | JobGovernanceRequiredError
    | JobLeaseLostError
    | JobDeadlineExceededError
)
"""Facade 实际调用集合允许观察到的 closed Job errors。"""

ScheduleGatewayError: TypeAlias = (
    ScheduleVersionConflictError
    | ScheduleInputError
    | ScheduleRepositoryError
    | ScheduleInvariantError
    | ScheduleExecutionUnavailableError
)
"""Facade 实际调用集合允许观察到的 closed Schedule errors。"""

SourceRepositoryError: TypeAlias = (
    SourceSyncRequestRejected | SourceSyncRepositoryFailure
)
"""Public facade 可映射的 Source repository errors。"""


def _scope(seed: int = 1) -> TenantScope:
    """构造 canonical tenant scope。

    Args:
        seed: Tenant UUID 的尾部整数。

    Returns:
        Trusted test scope。

    Raises:
        无。
    """

    return Principal(
        tenant_id=TenantId(f"00000000-0000-0000-0000-{seed:012d}"),
        user_id=f"source-user-{seed}",
    ).to_scope()


def _subscription_id(seed: int = 101) -> SourceSubscriptionId:
    """构造 canonical subscription identity。

    Args:
        seed: UUID 整数种子。

    Returns:
        Source subscription identity。

    Raises:
        无。
    """

    return SourceSubscriptionId(str(UUID(int=seed)))


def _config(
    *,
    lookback_days: int = 3,
    max_documents_per_sync: int = 20,
) -> FinsDisclosureSubscriptionConfig:
    """构造 strict Fins subscription config。

    Args:
        lookback_days: Query window 天数。
        max_documents_per_sync: 单次最大文档数。

    Returns:
        Strict config。

    Raises:
        无。
    """

    return FinsDisclosureSubscriptionConfig(
        forms=("10-K", "10-Q"),
        lookback_days=lookback_days,
        freshness_max_age_days=2,
        failing_after=2,
        disable_after=4,
        max_documents_per_sync=max_documents_per_sync,
    )


def _binding(
    scope: TenantScope,
    subscription_id: SourceSubscriptionId,
    *,
    subscription_version: int = 3,
    subscription_status: SubscriptionStatus = SubscriptionStatus.ENABLED,
    source_definition_seed: int = 201,
    source_definition_version: int = 5,
    security_seed: int = 301,
    security_version: int = 7,
    config: FinsDisclosureSubscriptionConfig | None = None,
) -> SourceExecutionBinding:
    """构造完整 executable Source binding。

    Args:
        scope: Tenant scope。
        subscription_id: Subscription identity。
        subscription_version: Subscription version。
        subscription_status: Enabled 或 disabled 状态。
        source_definition_seed: Source definition UUID seed。
        source_definition_version: Source definition version。
        security_seed: Security identity seed。
        security_version: Security version。
        config: 可空 strict config。

    Returns:
        Strict execution binding。

    Raises:
        无。
    """

    return SourceExecutionBinding(
        tenant_id=scope.tenant_id,
        source_definition_id=SourceDefinitionId(
            str(UUID(int=source_definition_seed))
        ),
        source_definition_version=source_definition_version,
        source_key=FINS_SOURCE_DEFINITION_KEY,
        source_kind=SourceKind.FILING,
        subscription_id=subscription_id,
        subscription_version=subscription_version,
        subscription_status=subscription_status,
        security_company_id=CompanyId(f"company-{security_seed}"),
        security_id=SecurityId(f"security-{security_seed}"),
        security_version=security_version,
        security_ticker="AAPL",
        exchange_mic="XNAS",
        security_is_active=True,
        connector_key=SourceConnectorKey.FINS_MARKET_DISCLOSURE_V1,
        config=config if config is not None else _config(),
    )


def _manual_request(
    subscription_id: SourceSubscriptionId,
    *,
    expected_subscription_version: int = 3,
    trigger_seed: int = 401,
    available_at: datetime = NOW,
    deadline_at: datetime = NOW + timedelta(hours=2),
) -> SourceSyncEnqueueRequest:
    """构造 manual caller intent。

    Args:
        subscription_id: Subscription identity。
        expected_subscription_version: Expected subscription version。
        trigger_seed: Trigger UUID seed。
        available_at: Immutable original availability。
        deadline_at: Immutable deadline。

    Returns:
        Strict manual request。

    Raises:
        无。
    """

    return SourceSyncEnqueueRequest(
        subscription_id=subscription_id,
        expected_subscription_version=expected_subscription_version,
        trigger_id=UUID(int=trigger_seed),
        available_at=available_at,
        deadline_at=deadline_at,
    )


def _polling_request(
    subscription_id: SourceSubscriptionId,
    *,
    expected_subscription_version: int = 3,
    cron_expression: str = "0 * * * *",
    timezone_name: str = "UTC",
    misfire_grace_seconds: int = 120,
    job_deadline_seconds: int = 600,
    schedule_key: str | None = None,
) -> SourcePollingScheduleRequest:
    """构造 polling schedule caller intent。

    Args:
        subscription_id: Subscription identity。
        expected_subscription_version: Expected subscription version。
        cron_expression: 五字段 cron caller text。
        timezone_name: IANA timezone。
        misfire_grace_seconds: Misfire grace。
        job_deadline_seconds: Occurrence deadline。
        schedule_key: 可空 caller key。

    Returns:
        Strict polling request。

    Raises:
        无。
    """

    return SourcePollingScheduleRequest(
        subscription_id=subscription_id,
        expected_subscription_version=expected_subscription_version,
        cron_expression=cron_expression,
        timezone_name=timezone_name,
        misfire_policy=ScheduleMisfirePolicy.COALESCE_ONE,
        misfire_grace_seconds=misfire_grace_seconds,
        job_deadline_seconds=job_deadline_seconds,
        schedule_key=schedule_key,
    )


def _normalized_polling_request(
    request: SourcePollingScheduleRequest,
) -> SourcePollingScheduleRequest:
    """独立应用 accepted default schedule key 公式。

    Args:
        request: Caller polling intent。

    Returns:
        带非空 schedule key 的等价 request。

    Raises:
        无。
    """

    if request.schedule_key is not None:
        return request
    return replace(
        request,
        schedule_key=(
            f"{_DEFAULT_SCHEDULE_KEY_PREFIX}:{request.subscription_id}"
        ),
    )


def _healthy_health(
    scope: TenantScope,
    subscription_id: SourceSubscriptionId,
) -> SourceHealthProjection:
    """构造 virtual healthy head。

    Args:
        scope: Tenant scope。
        subscription_id: Subscription identity。

    Returns:
        Version-zero healthy projection。

    Raises:
        无。
    """

    return SourceHealthProjection(
        tenant_id=scope.tenant_id,
        subscription_id=subscription_id,
        status=SourceHealthStatus.HEALTHY,
        consecutive_failures=0,
        safe_error_code=None,
        version=0,
        last_source_sync_run_id=None,
        observed_at=None,
    )


def _disabled_health(
    scope: TenantScope,
    subscription_id: SourceSubscriptionId,
) -> SourceHealthProjection:
    """构造 persisted disabled head。

    Args:
        scope: Tenant scope。
        subscription_id: Subscription identity。

    Returns:
        Disabled projection。

    Raises:
        无。
    """

    return SourceHealthProjection(
        tenant_id=scope.tenant_id,
        subscription_id=subscription_id,
        status=SourceHealthStatus.DISABLED,
        consecutive_failures=4,
        safe_error_code=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
        version=4,
        last_source_sync_run_id=UUID(int=501),
        observed_at=NOW - timedelta(minutes=1),
    )


def _reenabled_health(
    scope: TenantScope,
    subscription_id: SourceSubscriptionId,
) -> SourceHealthProjection:
    """构造 operator re-enable 后的 healthy head。

    Args:
        scope: Tenant scope。
        subscription_id: Subscription identity。

    Returns:
        Persisted healthy projection。

    Raises:
        无。
    """

    return SourceHealthProjection(
        tenant_id=scope.tenant_id,
        subscription_id=subscription_id,
        status=SourceHealthStatus.HEALTHY,
        consecutive_failures=0,
        safe_error_code=None,
        version=5,
        last_source_sync_run_id=UUID(int=501),
        observed_at=NOW,
    )


def _record_from_enqueue(
    scope: TenantScope,
    request: JobEnqueueRequest,
    *,
    definition_id: UUID = UUID(int=601),
    job_id: UUID = UUID(int=602),
) -> JobIdempotencyRecord:
    """从 ordinary enqueue request 重建 immutable lookup record。

    Args:
        scope: Tenant scope。
        request: Captured enqueue request。
        definition_id: Durable definition identity。
        job_id: Durable job identity。

    Returns:
        Generic strict idempotency record。

    Raises:
        无。
    """

    return JobIdempotencyRecord(
        tenant_id=scope.tenant_id,
        definition_id=definition_id,
        job_id=job_id,
        descriptor=request.descriptor,
        idempotency_key=request.idempotency_key,
        payload=request.payload,
        payload_sha256=request.payload.sha256,
        request_fingerprint=job_enqueue_request_fingerprint(request),
        original_available_at=request.available_at,
        deadline_at=request.deadline_at,
    )


def _manual_record(
    scope: TenantScope,
    request: SourceSyncEnqueueRequest,
    binding: SourceExecutionBinding,
) -> JobIdempotencyRecord:
    """构造 Source-valid manual Job lookup record。

    Args:
        scope: Tenant scope。
        request: Original manual intent。
        binding: Original frozen binding。

    Returns:
        Strict generic record containing strict Source payload。

    Raises:
        无。
    """

    payload = ManualSourceSyncPayload(
        subscription_id=request.subscription_id,
        expected_subscription_version=request.expected_subscription_version,
        trigger_id=request.trigger_id,
        execution_snapshot=build_source_execution_snapshot(
            binding,
            request.available_at,
        ),
        request_fingerprint=build_manual_source_request_fingerprint(request),
    )
    enqueue = JobEnqueueRequest(
        descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
        idempotency_key=(
            "source-sync-trigger:v1:"
            f"{request.subscription_id}:{request.trigger_id}"
        ),
        payload=build_manual_source_sync_payload_document(payload),
        available_at=request.available_at,
        deadline_at=request.deadline_at,
    )
    return _record_from_enqueue(scope, enqueue)


def _definition_from_registration(
    scope: TenantScope,
    request: ScheduleRegistrationRequest,
    *,
    schedule_id: UUID = UUID(int=701),
) -> ScheduleDefinition:
    """从 registration intent 构造首次 disabled definition。

    Args:
        scope: Tenant scope。
        request: Registration request。
        schedule_id: Durable schedule identity。

    Returns:
        Version-one disabled definition。

    Raises:
        无。
    """

    return ScheduleDefinition(
        id=schedule_id,
        tenant_id=scope.tenant_id,
        schedule_key=request.schedule_key,
        descriptor=request.descriptor,
        payload=request.payload,
        cron_expression=request.cron_expression,
        timezone_name=request.timezone_name,
        misfire_policy=request.misfire_policy,
        misfire_grace_seconds=request.misfire_grace_seconds,
        job_deadline_seconds=request.job_deadline_seconds,
        state=ScheduleState.DISABLED,
        next_fire_at=None,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )


def _schedule_definition(
    scope: TenantScope,
    request: SourcePollingScheduleRequest,
    binding: SourceExecutionBinding,
) -> ScheduleDefinition:
    """构造 Source-valid polling schedule definition。

    Args:
        scope: Tenant scope。
        request: Original polling intent。
        binding: Original source binding。

    Returns:
        Strict disabled definition。

    Raises:
        无。
    """

    normalized = _normalized_polling_request(request)
    if normalized.schedule_key is None:
        raise AssertionError("normalized schedule key missing")
    payload = ScheduledSourceSyncPayload(
        subscription_id=normalized.subscription_id,
        source_definition_id=binding.source_definition_id,
        expected_subscription_version=normalized.expected_subscription_version,
        schedule_key=normalized.schedule_key,
        source_request_fingerprint=build_scheduled_source_request_fingerprint(
            normalized,
            normalized.schedule_key,
        ),
    )
    registration = ScheduleRegistrationRequest(
        schedule_key=normalized.schedule_key,
        descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
        payload=build_scheduled_source_sync_payload_document(payload),
        cron_expression=normalized.cron_expression,
        timezone_name=normalized.timezone_name,
        misfire_policy=normalized.misfire_policy,
        misfire_grace_seconds=normalized.misfire_grace_seconds,
        job_deadline_seconds=normalized.job_deadline_seconds,
    )
    return _definition_from_registration(scope, registration)


class _FakeJobGateway:
    """Recording Job gateway with durable response-loss simulation。"""

    def __init__(self, record: JobIdempotencyRecord | None = None) -> None:
        """初始化可空 lookup record 与零调用计数。

        Args:
            record: 可空 persisted record。

        Returns:
            无。

        Raises:
            无。
        """

        self.record = record
        self.lookup_error: JobGatewayError | None = None
        self.enqueue_error: JobGatewayError | None = None
        self.lookup_unlisted_error: BaseException | None = None
        self.enqueue_unlisted_error: BaseException | None = None
        self.enforce_tenant_visibility = False
        self.lose_enqueue_response = False
        self.events: list[str] = []
        self.lookup_calls: list[
            tuple[TenantScope, JobHandlerDescriptor, str]
        ] = []
        self.enqueue_calls: list[tuple[TenantScope, JobEnqueueRequest]] = []
        self.publish_calls = 0
        self.current_job_state = JobState.READY
        self.definition_active = True

    def get_by_idempotency_key(
        self,
        scope: TenantScope,
        *,
        descriptor: JobHandlerDescriptor,
        idempotency_key: str,
    ) -> JobIdempotencyRecord | None:
        """记录 lookup 并原样返回配置 record供Facade strict校验。

        Args:
            scope: Tenant scope。
            descriptor: Exact descriptor。
            idempotency_key: Stable key。

        Returns:
            配置的 record 或 ``None``。

        Raises:
            JobGatewayError: 配置的 closed failure。
        """

        self.events.append("job.lookup")
        self.lookup_calls.append((scope, descriptor, idempotency_key))
        if self.lookup_unlisted_error is not None:
            raise self.lookup_unlisted_error
        if self.lookup_error is not None:
            raise self.lookup_error
        if (
            self.enforce_tenant_visibility
            and self.record is not None
            and self.record.tenant_id != scope.tenant_id
        ):
            return None
        return self.record

    def enqueue(
        self,
        scope: TenantScope,
        request: JobEnqueueRequest,
    ) -> JobEnqueueReceipt:
        """记录 ordinary enqueue，按配置 commit、失败或丢 response。

        Args:
            scope: Tenant scope。
            request: Enqueue request。

        Returns:
            Durable READY receipt。

        Raises:
            JobGatewayError: 配置的 pre-commit closed failure。
            _LostResponseError: Durable record 已保存但 response 丢失。
        """

        self.events.append("job.enqueue")
        self.enqueue_calls.append((scope, request))
        if self.enqueue_unlisted_error is not None:
            raise self.enqueue_unlisted_error
        if self.enqueue_error is not None:
            raise self.enqueue_error
        record = _record_from_enqueue(scope, request)
        self.record = record
        receipt = JobEnqueueReceipt(
            tenant_id=record.tenant_id,
            definition_id=record.definition_id,
            job_id=record.job_id,
            state=JobState.READY,
            idempotency_reused=False,
        )
        if self.lose_enqueue_response:
            raise _LostResponseError()
        self.publish_calls += 1
        return receipt


class _FakeScheduleGateway:
    """Recording Schedule validation/lookup/ensure gateway。"""

    def __init__(self, definition: ScheduleDefinition | None = None) -> None:
        """初始化可空 persisted definition。

        Args:
            definition: 可空 current definition。

        Returns:
            无。

        Raises:
            无。
        """

        self.definition = definition
        self.validation_error: ScheduleGatewayError | None = None
        self.lookup_error: ScheduleGatewayError | None = None
        self.ensure_error: ScheduleGatewayError | None = None
        self.validation_unlisted_error: BaseException | None = None
        self.lookup_unlisted_error: BaseException | None = None
        self.ensure_unlisted_error: BaseException | None = None
        self.enforce_tenant_visibility = False
        self.lose_ensure_response = False
        self.events: list[str] = []
        self.validation_calls: list[str] = []
        self.lookup_calls: list[tuple[TenantScope, str]] = []
        self.ensure_calls: list[
            tuple[TenantScope, ScheduleRegistrationRequest]
        ] = []

    def validate_cron_expression(self, expression: str) -> None:
        """记录 semantic cron validation。

        Args:
            expression: Structural-valid cron。

        Returns:
            无。

        Raises:
            ScheduleGatewayError: 配置的 closed failure。
        """

        self.events.append("schedule.validate")
        self.validation_calls.append(expression)
        if self.validation_unlisted_error is not None:
            raise self.validation_unlisted_error
        if self.validation_error is not None:
            raise self.validation_error

    def get_by_key(
        self,
        scope: TenantScope,
        *,
        schedule_key: str,
    ) -> ScheduleDefinition | None:
        """记录 tenant/key lookup并原样返回配置definition供Facade校验。

        Args:
            scope: Tenant scope。
            schedule_key: Stable key。

        Returns:
            配置的 current definition 或 ``None``。

        Raises:
            ScheduleGatewayError: 配置的 closed failure。
        """

        self.events.append("schedule.lookup")
        self.lookup_calls.append((scope, schedule_key))
        if self.lookup_unlisted_error is not None:
            raise self.lookup_unlisted_error
        if self.lookup_error is not None:
            raise self.lookup_error
        if (
            self.enforce_tenant_visibility
            and self.definition is not None
            and self.definition.tenant_id != scope.tenant_id
        ):
            return None
        return self.definition

    def ensure_registered(
        self,
        scope: TenantScope,
        request: ScheduleRegistrationRequest,
    ) -> ScheduleDefinition:
        """记录 ensure，按配置创建、失败或丢 response。

        Args:
            scope: Tenant scope。
            request: Registration intent。

        Returns:
            First disabled definition。

        Raises:
            ScheduleGatewayError: 配置的 pre-commit closed failure。
            _LostResponseError: Definition 已保存但 response 丢失。
        """

        self.events.append("schedule.ensure")
        self.ensure_calls.append((scope, request))
        if self.ensure_unlisted_error is not None:
            raise self.ensure_unlisted_error
        if self.ensure_error is not None:
            raise self.ensure_error
        definition = _definition_from_registration(scope, request)
        self.definition = definition
        if self.lose_ensure_response:
            raise _LostResponseError()
        return definition


class _FakeSourceRepository:
    """Facade 三个 Source preflight/read dependencies 的 recording fake。"""

    def __init__(
        self,
        *,
        binding: SourceExecutionBinding,
        health: SourceHealthProjection,
    ) -> None:
        """保存 strict default projections 与零调用记录。

        Args:
            binding: Default executable binding。
            health: Default health projection。

        Returns:
            无。

        Raises:
            无。
        """

        self.binding = binding
        self.health = health
        self.receipt: SourceSyncAttemptReceipt | None = None
        self.page = SourceHealthSnapshotPage(snapshots=(), next_cursor=None)
        self.reenabled_health = _reenabled_health(
            Principal(
                tenant_id=health.tenant_id,
                user_id="source-reenable",
            ).to_scope(),
            health.subscription_id,
        )
        self.binding_error: SourceRepositoryError | None = None
        self.receipt_error: SourceRepositoryError | None = None
        self.health_error: SourceRepositoryError | None = None
        self.list_error: SourceRepositoryError | None = None
        self.reenable_error: SourceRepositoryError | None = None
        self.calls: list[str] = []
        self.events: list[str] = []

    def get_executable_binding(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
    ) -> SourceExecutionBinding:
        """记录 binding preflight。

        Args:
            scope: Tenant scope。
            subscription_id: Subscription identity。

        Returns:
            Configured binding。

        Raises:
            SourceRepositoryError: Configured closed error。
        """

        self.events.append("source.binding")
        self.calls.append("get_executable_binding")
        if self.binding_error is not None:
            raise self.binding_error
        return self.binding

    def acquire_operation(
        self,
        scope: TenantScope,
        request: SourceOperationAcquireRequest,
    ) -> SourceOperationAcquireDecision:
        """拒绝 facade 越界调用 execution acquire。

        Args:
            scope: Tenant scope。
            request: Execution acquire request。

        Returns:
            永不返回。

        Raises:
            AssertionError: 恒抛。
        """

        raise AssertionError("facade must not acquire source operation")

    def record_terminal(
        self,
        scope: TenantScope,
        request: SourceTerminalRecordRequest,
    ) -> SourceTerminalRecordDecision:
        """拒绝 facade 越界调用 execution terminal。

        Args:
            scope: Tenant scope。
            request: Execution terminal request。

        Returns:
            永不返回。

        Raises:
            AssertionError: 恒抛。
        """

        raise AssertionError("facade must not record source terminal")

    def get_source_receipt(
        self,
        scope: TenantScope,
        source_sync_run_id: UUID,
    ) -> SourceSyncAttemptReceipt | None:
        """记录 receipt read。

        Args:
            scope: Tenant scope。
            source_sync_run_id: Source run UUID。

        Returns:
            Configured receipt 或 ``None``。

        Raises:
            SourceRepositoryError: Configured closed error。
        """

        self.events.append("source.receipt")
        self.calls.append("get_source_receipt")
        if self.receipt_error is not None:
            raise self.receipt_error
        return self.receipt

    def get_health(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
    ) -> SourceHealthProjection:
        """记录 health head read。

        Args:
            scope: Tenant scope。
            subscription_id: Subscription identity。

        Returns:
            Configured health projection。

        Raises:
            SourceRepositoryError: Configured closed error。
        """

        self.events.append("source.health")
        self.calls.append("get_health")
        if self.health_error is not None:
            raise self.health_error
        return self.health

    def list_health_snapshots(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
        cursor: SourceHealthSnapshotCursor | None,
        *,
        limit: int,
    ) -> SourceHealthSnapshotPage:
        """记录 health keyset read。

        Args:
            scope: Tenant scope。
            subscription_id: Subscription identity。
            cursor: 可空 cursor。
            limit: Page size。

        Returns:
            Configured page。

        Raises:
            SourceRepositoryError: Configured closed error。
        """

        self.events.append("source.list")
        self.calls.append("list_health_snapshots")
        if self.list_error is not None:
            raise self.list_error
        return self.page

    def reenable_health(
        self,
        scope: TenantScope,
        request: SourceHealthReenableRequest,
    ) -> SourceHealthProjection:
        """记录 re-enable CAS。

        Args:
            scope: Tenant scope。
            request: Re-enable request。

        Returns:
            Configured re-enabled projection。

        Raises:
            SourceRepositoryError: Configured closed error。
        """

        self.events.append("source.reenable")
        self.calls.append("reenable_health")
        if self.reenable_error is not None:
            raise self.reenable_error
        return self.reenabled_health


def _facade(
    scope: TenantScope,
    subscription_id: SourceSubscriptionId,
    *,
    job_gateway: _FakeJobGateway | None = None,
    schedule_gateway: _FakeScheduleGateway | None = None,
    source_repository: _FakeSourceRepository | None = None,
) -> tuple[
    InvestmentSourcesService,
    _FakeJobGateway,
    _FakeScheduleGateway,
    _FakeSourceRepository,
]:
    """构造 facade 与三个 typed fakes。

    Args:
        scope: Tenant scope。
        subscription_id: Subscription identity。
        job_gateway: 可空 custom Job fake。
        schedule_gateway: 可空 custom Schedule fake。
        source_repository: 可空 custom Source fake。

    Returns:
        Facade 与三个实际注入 fake。

    Raises:
        无。
    """

    selected_job = job_gateway if job_gateway is not None else _FakeJobGateway()
    selected_schedule = (
        schedule_gateway
        if schedule_gateway is not None
        else _FakeScheduleGateway()
    )
    selected_source = (
        source_repository
        if source_repository is not None
        else _FakeSourceRepository(
            binding=_binding(scope, subscription_id),
            health=_healthy_health(scope, subscription_id),
        )
    )
    shared_events: list[str] = []
    selected_job.events = shared_events
    selected_schedule.events = shared_events
    selected_source.events = shared_events
    return (
        InvestmentSourcesService(
            job_gateway=selected_job,
            schedule_gateway=selected_schedule,
            source_repository=selected_source,
        ),
        selected_job,
        selected_schedule,
        selected_source,
    )


def test_schedule_recovery_lookup_precedes_source_binding_read_and_survives_version_status_config_security_drift() -> None:
    """Schedule response-loss recovery只依赖 persisted immutable intent。"""

    scope = _scope()
    subscription_id = _subscription_id()
    request = _polling_request(subscription_id)
    service, _, schedules, sources = _facade(scope, subscription_id)
    schedules.lose_ensure_response = True

    with pytest.raises(_LostResponseError):
        service.ensure_polling_schedule(scope, request)

    original_definition = schedules.definition
    assert original_definition is not None
    assert sources.calls == ["get_executable_binding"]
    assert schedules.events == [
        "schedule.validate",
        "schedule.lookup",
        "source.binding",
        "schedule.ensure",
    ]
    assert len(schedules.lookup_calls) == 1
    assert len(schedules.ensure_calls) == 1

    schedules.lose_ensure_response = False
    schedules.definition = replace(
        original_definition,
        state=ScheduleState.ACTIVE,
        next_fire_at=NOW + timedelta(hours=1),
        version=4,
        updated_at=NOW + timedelta(minutes=1),
    )
    sources.binding = _binding(
        scope,
        subscription_id,
        subscription_version=9,
        subscription_status=SubscriptionStatus.DISABLED,
        source_definition_seed=202,
        source_definition_version=8,
        security_seed=302,
        security_version=11,
        config=_config(lookback_days=9, max_documents_per_sync=40),
    )
    source_calls_before = tuple(sources.calls)
    events_before = tuple(schedules.events)
    recovered = service.ensure_polling_schedule(scope, request)

    assert recovered is schedules.definition
    assert recovered.id == original_definition.id
    assert recovered.state is ScheduleState.ACTIVE
    assert recovered.version == 4
    assert tuple(sources.calls) == source_calls_before
    assert tuple(schedules.events) == events_before + (
        "schedule.validate",
        "schedule.lookup",
    )
    assert len(schedules.lookup_calls) == 2
    assert len(schedules.ensure_calls) == 1


def test_schedule_recovery_rejects_caller_intent_or_persisted_identity_drift_and_cross_tenant_is_missing() -> None:
    """Schedule hit区分合法caller drift、persisted tamper与cross-tenant miss。"""

    scope = _scope()
    other_scope = _scope(2)
    subscription_id = _subscription_id()
    binding = _binding(scope, subscription_id)
    request = _polling_request(subscription_id)
    definition = _schedule_definition(scope, request, binding)
    service, _, schedules, sources = _facade(
        scope,
        subscription_id,
        schedule_gateway=_FakeScheduleGateway(definition),
    )

    for caller_drift in (
        replace(request, cron_expression="30 * * * *"),
        replace(request, timezone_name="Asia/Shanghai"),
        replace(request, expected_subscription_version=4),
        replace(request, misfire_grace_seconds=180),
        replace(request, job_deadline_seconds=900),
    ):
        with pytest.raises(ScheduleVersionConflictError):
            service.ensure_polling_schedule(scope, caller_drift)
        assert sources.calls == []

    normalized = _normalized_polling_request(request)
    if normalized.schedule_key is None:
        raise AssertionError("normalized schedule key missing")
    expected_key = normalized.schedule_key
    persisted_payload = ScheduledSourceSyncPayload(
        subscription_id=normalized.subscription_id,
        source_definition_id=binding.source_definition_id,
        expected_subscription_version=normalized.expected_subscription_version,
        schedule_key=expected_key,
        source_request_fingerprint=build_scheduled_source_request_fingerprint(
            normalized,
            expected_key,
        ),
    )
    wrong_key_request = replace(normalized, schedule_key="other-source-key")
    wrong_key_payload = ScheduledSourceSyncPayload(
        subscription_id=wrong_key_request.subscription_id,
        source_definition_id=binding.source_definition_id,
        expected_subscription_version=(
            wrong_key_request.expected_subscription_version
        ),
        schedule_key="other-source-key",
        source_request_fingerprint=build_scheduled_source_request_fingerprint(
            wrong_key_request,
            "other-source-key",
        ),
    )
    persisted_invariant_definitions = (
        replace(definition, tenant_id=other_scope.tenant_id),
        replace(
            definition,
            descriptor=replace(SOURCE_SYNC_JOB_DESCRIPTOR, max_attempts=4),
        ),
        replace(definition, schedule_key="other-source-key"),
        replace(
            definition,
            payload=build_scheduled_source_sync_payload_document(
                wrong_key_payload
            ),
        ),
        replace(
            definition,
            payload=build_scheduled_source_sync_payload_document(
                replace(
                    persisted_payload,
                    source_request_fingerprint="0" * 64,
                )
            ),
        ),
        replace(
            definition,
            payload=build_canonical_document(
                {"schema_version": 1, "unexpected": "source-shape"},
                schema_name=SOURCE_SYNC_PAYLOAD_SCHEMA_NAME,
                schema_version=1,
            ),
        ),
    )
    for drifted_definition in persisted_invariant_definitions:
        schedules.definition = drifted_definition
        with pytest.raises(SourceServiceUnavailableError) as unavailable:
            service.ensure_polling_schedule(scope, request)
        assert (
            unavailable.value.code
            is SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT
        )
        assert sources.calls == []

    schedules_for_other_tenant = _FakeScheduleGateway(definition)
    schedules_for_other_tenant.enforce_tenant_visibility = True
    cross_tenant_service, _, _, cross_tenant_sources = _facade(
        other_scope,
        subscription_id,
        schedule_gateway=schedules_for_other_tenant,
        source_repository=_FakeSourceRepository(
            binding=_binding(other_scope, subscription_id),
            health=_healthy_health(other_scope, subscription_id),
        ),
    )
    cross_tenant_sources.binding_error = SourceSyncRequestRejected(
        SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND
    )
    with pytest.raises(SourceServiceInputError) as missing:
        cross_tenant_service.ensure_polling_schedule(other_scope, request)
    assert (
        missing.value.code
        is SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND
    )
    assert schedules_for_other_tenant.definition is definition
    assert schedules_for_other_tenant.lookup_calls[-1][0] is other_scope
    assert schedules_for_other_tenant.ensure_calls == []


def test_polling_schedule_cron_validation_precedes_lookup_and_source_reads_for_hit_and_miss() -> None:
    """Schedule结构、IANA、关系与semantic cron失败均早于lookup/source。"""

    scope = _scope()
    subscription_id = _subscription_id()
    valid_request = _polling_request(subscription_id)
    valid_definition = _schedule_definition(
        scope,
        valid_request,
        _binding(scope, subscription_id),
    )
    hostile_requests = (
        _polling_request(subscription_id, cron_expression="@daily"),
        _polling_request(subscription_id, timezone_name="Mars/Olympus"),
        _polling_request(
            subscription_id,
            misfire_grace_seconds=120,
            job_deadline_seconds=120,
        ),
        _polling_request(subscription_id, cron_expression="60 * * * *"),
    )

    for definition in (None, valid_definition):
        for index, hostile in enumerate(hostile_requests):
            schedules = _FakeScheduleGateway(definition)
            if index == 3:
                schedules.validation_error = ScheduleInputError()
            service, _, _, sources = _facade(
                scope,
                subscription_id,
                schedule_gateway=schedules,
            )
            with pytest.raises(SourceServiceInputError) as rejected:
                service.ensure_polling_schedule(scope, hostile)
            assert (
                rejected.value.code
                is SourceSyncRequestRejectionCode.INVALID_INPUT
            )
            assert schedules.lookup_calls == []
            assert schedules.ensure_calls == []
            assert sources.calls == []
            expected_validation_calls = (
                [hostile.cron_expression] if index == 3 else []
            )
            assert schedules.validation_calls == expected_validation_calls

    for definition, expected_events in (
        (
            valid_definition,
            ["schedule.validate", "schedule.lookup"],
        ),
        (
            None,
            [
                "schedule.validate",
                "schedule.lookup",
                "source.binding",
                "schedule.ensure",
            ],
        ),
    ):
        schedules = _FakeScheduleGateway(definition)
        service, _, _, sources = _facade(
            scope,
            subscription_id,
            schedule_gateway=schedules,
        )
        result = service.ensure_polling_schedule(scope, valid_request)
        assert schedules.validation_calls == [valid_request.cron_expression]
        assert schedules.events == expected_events
        if definition is not None:
            assert result is definition
            assert sources.calls == []
        else:
            assert sources.calls == ["get_executable_binding"]


def test_source_service_propagates_schedule_version_conflict_without_message_mapping_or_source_error_wrapping() -> None:
    """Schedule ensure immutable conflict保持原异常identity。"""

    scope = _scope()
    subscription_id = _subscription_id()
    for use_ensure in (False, True):
        conflict = ScheduleVersionConflictError(
            "unavailable persisted_invariant invalid_input"
        )
        schedules = _FakeScheduleGateway()
        if use_ensure:
            schedules.ensure_error = conflict
        else:
            schedules.lookup_error = conflict
        service, _, _, sources = _facade(
            scope,
            subscription_id,
            schedule_gateway=schedules,
        )

        with pytest.raises(ScheduleVersionConflictError) as raised:
            service.ensure_polling_schedule(
                scope,
                _polling_request(subscription_id),
            )

        assert raised.value is conflict
        if use_ensure:
            assert sources.calls == ["get_executable_binding"]
            assert len(schedules.ensure_calls) == 1
        else:
            assert sources.calls == []
            assert schedules.ensure_calls == []


def test_manual_response_loss_strictly_validates_persisted_intent_then_source_facade_alone_rebuilds_ready_reused_receipt_after_job_progress_definition_disable_and_source_drift_without_publish() -> None:
    """Manual response-loss recovery忽略全部current mutable drift且不publish。"""

    scope = _scope()
    subscription_id = _subscription_id()
    request = _manual_request(subscription_id)
    jobs = _FakeJobGateway()
    jobs.lose_enqueue_response = True
    service, _, _, sources = _facade(
        scope,
        subscription_id,
        job_gateway=jobs,
    )

    with pytest.raises(_LostResponseError):
        service.enqueue_manual_sync(scope, request)

    record = jobs.record
    assert record is not None
    assert sources.calls == ["get_executable_binding", "get_health"]
    assert jobs.events == [
        "job.lookup",
        "source.binding",
        "source.health",
        "job.enqueue",
    ]
    assert len(jobs.enqueue_calls) == 1
    assert jobs.publish_calls == 0

    jobs.lose_enqueue_response = False
    jobs.current_job_state = JobState.SUCCEEDED
    jobs.definition_active = False
    sources.binding = _binding(
        scope,
        subscription_id,
        subscription_version=8,
        subscription_status=SubscriptionStatus.DISABLED,
        source_definition_seed=205,
        security_seed=305,
        config=_config(lookback_days=8, max_documents_per_sync=50),
    )
    sources.health = _disabled_health(scope, subscription_id)
    source_calls_before = tuple(sources.calls)
    events_before = tuple(jobs.events)
    receipt = service.enqueue_manual_sync(scope, request)

    assert receipt == JobEnqueueReceipt(
        tenant_id=record.tenant_id,
        definition_id=record.definition_id,
        job_id=record.job_id,
        state=JobState.READY,
        idempotency_reused=True,
    )
    assert tuple(sources.calls) == source_calls_before
    assert tuple(jobs.events) == events_before + ("job.lookup",)
    assert len(jobs.enqueue_calls) == 1
    assert jobs.publish_calls == 0
    assert len(jobs.lookup_calls) == 2


def test_manual_recovery_rejects_caller_intent_or_persisted_payload_drift_and_cross_tenant_is_missing() -> None:
    """Manual hit区分caller drift、Source-invalid payload与cross-tenant miss。"""

    scope = _scope()
    other_scope = _scope(2)
    subscription_id = _subscription_id()
    binding = _binding(scope, subscription_id)
    request = _manual_request(subscription_id)
    jobs = _FakeJobGateway(_manual_record(scope, request, binding))
    service, _, _, sources = _facade(
        scope,
        subscription_id,
        job_gateway=jobs,
    )

    for caller_drift in (
        replace(request, expected_subscription_version=4),
        replace(
            request,
            available_at=request.available_at + timedelta(minutes=1),
        ),
        replace(
            request,
            deadline_at=request.deadline_at + timedelta(hours=1),
        ),
    ):
        with pytest.raises(JobIdempotencyConflictError):
            service.enqueue_manual_sync(scope, caller_drift)
        assert sources.calls == []

    invalid_source_payload = build_canonical_document(
        {"schema_version": 1, "unexpected": "manual-source-shape"},
        schema_name=SOURCE_SYNC_PAYLOAD_SCHEMA_NAME,
        schema_version=1,
    )
    generic_request = JobEnqueueRequest(
        descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
        idempotency_key=jobs.record.idempotency_key if jobs.record is not None else "missing",
        payload=invalid_source_payload,
        available_at=request.available_at,
        deadline_at=request.deadline_at,
    )
    source_valid_record = _manual_record(scope, request, binding)
    source_payload = ManualSourceSyncPayload(
        subscription_id=request.subscription_id,
        expected_subscription_version=request.expected_subscription_version,
        trigger_id=request.trigger_id,
        execution_snapshot=build_source_execution_snapshot(
            binding,
            request.available_at,
        ),
        request_fingerprint=build_manual_source_request_fingerprint(request),
    )
    wrong_descriptor = replace(SOURCE_SYNC_JOB_DESCRIPTOR, max_attempts=4)
    wrong_descriptor_request = JobEnqueueRequest(
        descriptor=wrong_descriptor,
        idempotency_key=source_valid_record.idempotency_key,
        payload=source_valid_record.payload,
        available_at=request.available_at,
        deadline_at=request.deadline_at,
    )
    wrong_key_request = JobEnqueueRequest(
        descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
        idempotency_key="source-sync-trigger:v1:wrong-key",
        payload=source_valid_record.payload,
        available_at=request.available_at,
        deadline_at=request.deadline_at,
    )
    wrong_tenant_binding = _binding(
        other_scope,
        subscription_id,
        subscription_version=request.expected_subscription_version,
    )
    wrong_tenant_payload = replace(
        source_payload,
        execution_snapshot=build_source_execution_snapshot(
            wrong_tenant_binding,
            request.available_at,
        ),
    )
    disabled_binding = _binding(
        scope,
        subscription_id,
        subscription_version=request.expected_subscription_version,
        subscription_status=SubscriptionStatus.DISABLED,
    )
    disabled_payload = replace(
        source_payload,
        execution_snapshot=build_source_execution_snapshot(
            disabled_binding,
            request.available_at,
        ),
    )
    persisted_invariant_records = (
        replace(source_valid_record, tenant_id=other_scope.tenant_id),
        _record_from_enqueue(scope, wrong_descriptor_request),
        _record_from_enqueue(scope, wrong_key_request),
        _record_from_enqueue(scope, generic_request),
        _record_from_enqueue(
            scope,
            replace(
                generic_request,
                payload=build_manual_source_sync_payload_document(
                    replace(source_payload, request_fingerprint="0" * 64)
                ),
            ),
        ),
        _record_from_enqueue(
            scope,
            replace(
                generic_request,
                payload=build_manual_source_sync_payload_document(
                    wrong_tenant_payload
                ),
            ),
        ),
        _record_from_enqueue(
            scope,
            replace(
                generic_request,
                payload=build_manual_source_sync_payload_document(
                    disabled_payload
                ),
            ),
        ),
    )
    for drifted_record in persisted_invariant_records:
        jobs.record = drifted_record
        with pytest.raises(SourceServiceUnavailableError) as unavailable:
            service.enqueue_manual_sync(scope, request)
        assert (
            unavailable.value.code
            is SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT
        )
        assert sources.calls == []

    different_trigger = replace(request, trigger_id=UUID(int=402))
    different_trigger_payload = replace(
        source_payload,
        trigger_id=different_trigger.trigger_id,
        request_fingerprint=build_manual_source_request_fingerprint(
            different_trigger
        ),
    )
    different_subscription_id = _subscription_id(102)
    different_subscription_request = replace(
        request,
        subscription_id=different_subscription_id,
    )
    different_subscription_binding = _binding(
        scope,
        different_subscription_id,
        subscription_version=request.expected_subscription_version,
    )
    different_subscription_payload = ManualSourceSyncPayload(
        subscription_id=different_subscription_id,
        expected_subscription_version=request.expected_subscription_version,
        trigger_id=request.trigger_id,
        execution_snapshot=build_source_execution_snapshot(
            different_subscription_binding,
            request.available_at,
        ),
        request_fingerprint=build_manual_source_request_fingerprint(
            different_subscription_request
        ),
    )
    for key_inconsistent_payload in (
        different_trigger_payload,
        different_subscription_payload,
    ):
        jobs.record = _record_from_enqueue(
            scope,
            replace(
                generic_request,
                payload=build_manual_source_sync_payload_document(
                    key_inconsistent_payload
                ),
            ),
        )
        with pytest.raises(SourceServiceUnavailableError) as unavailable:
            service.enqueue_manual_sync(scope, request)
        assert (
            unavailable.value.code
            is SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT
        )

    cross_tenant_jobs = _FakeJobGateway(source_valid_record)
    cross_tenant_jobs.enforce_tenant_visibility = True
    cross_tenant_service, _, _, cross_tenant_sources = _facade(
        other_scope,
        subscription_id,
        job_gateway=cross_tenant_jobs,
        source_repository=_FakeSourceRepository(
            binding=_binding(other_scope, subscription_id),
            health=_healthy_health(other_scope, subscription_id),
        ),
    )
    cross_tenant_sources.binding_error = SourceSyncRequestRejected(
        SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND
    )
    with pytest.raises(SourceServiceInputError) as missing:
        cross_tenant_service.enqueue_manual_sync(other_scope, request)
    assert (
        missing.value.code
        is SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND
    )
    assert cross_tenant_jobs.record is source_valid_record
    assert cross_tenant_jobs.lookup_calls[-1][0] is other_scope
    assert cross_tenant_jobs.enqueue_calls == []


def test_source_service_propagates_job_idempotency_conflict_without_message_mapping_or_source_error_wrapping() -> None:
    """Ordinary Job enqueue conflict保持原异常identity。"""

    scope = _scope()
    subscription_id = _subscription_id()
    for use_enqueue in (False, True):
        conflict = JobIdempotencyConflictError(
            "unavailable persisted_invariant invalid_input"
        )
        jobs = _FakeJobGateway()
        if use_enqueue:
            jobs.enqueue_error = conflict
        else:
            jobs.lookup_error = conflict
        service, _, _, sources = _facade(
            scope,
            subscription_id,
            job_gateway=jobs,
        )

        with pytest.raises(JobIdempotencyConflictError) as raised:
            service.enqueue_manual_sync(
                scope,
                _manual_request(subscription_id),
            )

        assert raised.value is conflict
        if use_enqueue:
            assert sources.calls == ["get_executable_binding", "get_health"]
            assert len(jobs.enqueue_calls) == 1
        else:
            assert sources.calls == []
            assert jobs.enqueue_calls == []


def test_platform_source_sync_service_protocol_has_exact_synchronous_signatures_and_parameter_annotations() -> None:
    """Platform Source protocol精确固定六同步方法与annotation。"""

    expected_names = (
        "platform_service_name",
        "enqueue_manual_sync",
        "ensure_polling_schedule",
        "get_source_receipt",
        "get_source_health",
        "list_source_health_snapshots",
        "reenable_source_health",
    )
    protocol_members = tuple(
        name
        for name in PlatformSourceSyncServiceProtocol.__dict__
        if not name.startswith("_")
    )
    assert protocol_members == expected_names
    assert ReExportedPlatformSourceSyncServiceProtocol is PlatformSourceSyncServiceProtocol
    assert isinstance(
        PlatformSourceSyncServiceProtocol.__dict__["platform_service_name"],
        property,
    )
    service_name_property = PlatformSourceSyncServiceProtocol.__dict__[
        "platform_service_name"
    ]
    if not isinstance(service_name_property, property):
        raise AssertionError("platform_service_name must be property")
    service_name_getter = service_name_property.fget
    if service_name_getter is None:
        raise AssertionError("platform_service_name getter missing")
    assert service_name_getter.__module__ == "dayu.investment.composition"
    assert get_type_hints(service_name_getter) == {"return": str}
    getter_signature = inspect.signature(service_name_getter)
    assert tuple(getter_signature.parameters) == ("self",)
    assert (
        getter_signature.parameters["self"].kind
        is inspect.Parameter.POSITIONAL_OR_KEYWORD
    )
    assert (
        getter_signature.parameters["self"].default
        is inspect.Parameter.empty
    )
    method_expectations = (
        (
            "enqueue_manual_sync",
            ("self", "scope", "request"),
            {"scope": TenantScope, "request": SourceSyncEnqueueRequest, "return": JobEnqueueReceipt},
        ),
        (
            "ensure_polling_schedule",
            ("self", "scope", "request"),
            {"scope": TenantScope, "request": SourcePollingScheduleRequest, "return": ScheduleDefinition},
        ),
        (
            "get_source_receipt",
            ("self", "scope", "source_sync_run_id"),
            {"scope": TenantScope, "source_sync_run_id": UUID, "return": SourceSyncAttemptReceipt | None},
        ),
        (
            "get_source_health",
            ("self", "scope", "subscription_id"),
            {"scope": TenantScope, "subscription_id": SourceSubscriptionId, "return": SourceHealthProjection},
        ),
        (
            "list_source_health_snapshots",
            ("self", "scope", "subscription_id", "cursor", "limit"),
            {
                "scope": TenantScope,
                "subscription_id": SourceSubscriptionId,
                "cursor": SourceHealthSnapshotCursor | None,
                "limit": int,
                "return": SourceHealthSnapshotPage,
            },
        ),
        (
            "reenable_source_health",
            ("self", "scope", "request"),
            {"scope": TenantScope, "request": SourceHealthReenableRequest, "return": SourceHealthProjection},
        ),
    )
    for name, parameter_names, expected_hints in method_expectations:
        method = PlatformSourceSyncServiceProtocol.__dict__[name]
        assert inspect.isfunction(method)
        assert not inspect.iscoroutinefunction(method)
        assert method.__module__ == "dayu.investment.composition"
        signature = inspect.signature(method)
        assert tuple(signature.parameters) == parameter_names
        assert get_type_hints(method) == expected_hints
        for parameter in signature.parameters.values():
            expected_kind = (
                inspect.Parameter.KEYWORD_ONLY
                if parameter.name == "limit"
                else inspect.Parameter.POSITIONAL_OR_KEYWORD
            )
            assert parameter.kind is expected_kind
            assert parameter.default is inspect.Parameter.empty
    list_signature = inspect.signature(
        PlatformSourceSyncServiceProtocol.list_source_health_snapshots
    )
    assert (
        list_signature.parameters["limit"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )
    assert tuple(field.name for field in fields(SourceSyncEnqueueRequest)) == (
        "subscription_id",
        "expected_subscription_version",
        "trigger_id",
        "available_at",
        "deadline_at",
    )


def test_services_package_exports_public_investment_sources_only_and_not_private_execution_types() -> None:
    """Services root只新增public facade，不导出private gateways/execution。"""

    assert services_package.InvestmentSourcesService is InvestmentSourcesService
    assert services_package.__all__.count("InvestmentSourcesService") == 1
    forbidden_exports = (
        "SourceManualJobGatewayProtocol",
        "SourceScheduleGatewayProtocol",
        "SourceSyncExecutionServiceProtocol",
        "SourceSyncExecutionService",
        "SourceSyncExecutionHandler",
    )
    for name in forbidden_exports:
        assert name not in services_package.__all__
        assert name not in vars(services_package)
    assert SourceManualJobGatewayProtocol.__module__ == (
        "dayu.services.investment_sources"
    )
    assert SourceScheduleGatewayProtocol.__module__ == (
        "dayu.services.investment_sources"
    )


def test_source_sync_closed_error_enums_and_service_errors_preserve_exact_codes_without_free_text() -> None:
    """Source public/repository errors只携带closed enum code。"""

    assert {item.value for item in SourceSyncRequestRejectionCode} == {
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
    assert {item.value for item in SourceSyncRepositoryFailureCode} == {
        "unavailable",
        "transaction_aborted",
        "persisted_invariant",
    }
    for request_code in SourceSyncRequestRejectionCode:
        request_errors = (
            SourceSyncRequestRejected(request_code),
            SourceServiceInputError(request_code),
        )
        for error in request_errors:
            assert error.code is request_code
            assert error.args == (request_code.value,)
            assert vars(error) == {"code": request_code}
            assert "retryable" not in vars(error)
    for repository_code in SourceSyncRepositoryFailureCode:
        repository_errors = (
            SourceSyncRepositoryFailure(repository_code),
            SourceServiceUnavailableError(repository_code),
        )
        for error in repository_errors:
            assert error.code is repository_code
            assert error.args == (repository_code.value,)
            assert vars(error) == {"code": repository_code}
            assert "retryable" not in vars(error)
    for error_type in (
        SourceSyncRequestRejected,
        SourceServiceInputError,
        SourceSyncRepositoryFailure,
        SourceServiceUnavailableError,
    ):
        signature = inspect.signature(error_type)
        assert tuple(signature.parameters) == ("code",)
        with pytest.raises(TypeError):
            signature.bind("code", "free text")
    foreign_request_code = _ForeignRequestCode.INVALID_INPUT
    foreign_repository_code = _ForeignRepositoryCode.UNAVAILABLE
    assert foreign_request_code.value == (
        SourceSyncRequestRejectionCode.INVALID_INPUT.value
    )
    assert foreign_repository_code.value == (
        SourceSyncRepositoryFailureCode.UNAVAILABLE.value
    )
    assert not isinstance(
        foreign_request_code,
        SourceSyncRequestRejectionCode,
    )
    assert not isinstance(
        foreign_repository_code,
        SourceSyncRepositoryFailureCode,
    )
    assert issubclass(SourceSyncRequestRejectionCode, Enum)
    assert issubclass(SourceSyncRepositoryFailureCode, Enum)


def test_source_public_service_maps_invalid_missing_subscription_version_subscription_state_health_cas_and_unavailable_branches_exactly() -> None:
    """Public Source methods精确映射自己的input/repository closed codes。"""

    scope = _scope()
    subscription_id = _subscription_id()
    manual = _manual_request(subscription_id)
    polling = _polling_request(subscription_id)

    service, jobs, schedules, sources = _facade(scope, subscription_id)
    for limit in (-1, 0, 201, True):
        with pytest.raises(SourceServiceInputError) as invalid:
            service.list_source_health_snapshots(
                scope,
                subscription_id,
                None,
                limit=limit,
            )
        assert invalid.value.code is SourceSyncRequestRejectionCode.INVALID_INPUT
    assert sources.calls == []
    assert jobs.lookup_calls == []
    assert jobs.enqueue_calls == []
    assert schedules.lookup_calls == []
    assert schedules.ensure_calls == []

    for code in (
        SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND,
        SourceSyncRequestRejectionCode.BINDING_NON_EXECUTABLE,
    ):
        for use_manual in (True, False):
            service, jobs, schedules, sources = _facade(
                scope,
                subscription_id,
            )
            sources.binding_error = SourceSyncRequestRejected(code)
            with pytest.raises(SourceServiceInputError) as rejected:
                if use_manual:
                    service.enqueue_manual_sync(scope, manual)
                else:
                    service.ensure_polling_schedule(scope, polling)
            assert rejected.value.code is code
            assert jobs.enqueue_calls == []
            assert schedules.ensure_calls == []

    for use_manual in (True, False):
        service, jobs, schedules, sources = _facade(
            scope,
            subscription_id,
        )
        sources.binding = _binding(
            scope,
            subscription_id,
            subscription_version=4,
        )
        with pytest.raises(SourceServiceInputError) as version_conflict:
            if use_manual:
                service.enqueue_manual_sync(scope, manual)
            else:
                service.ensure_polling_schedule(scope, polling)
        assert (
            version_conflict.value.code
            is SourceSyncRequestRejectionCode.SUBSCRIPTION_VERSION_CONFLICT
        )
        assert jobs.enqueue_calls == []
        assert schedules.ensure_calls == []

    service, jobs, schedules, sources = _facade(scope, subscription_id)
    sources.binding = _binding(
        scope,
        subscription_id,
        subscription_status=SubscriptionStatus.DISABLED,
    )
    with pytest.raises(SourceServiceInputError) as state_conflict:
        service.enqueue_manual_sync(scope, manual)
    assert (
        state_conflict.value.code
        is SourceSyncRequestRejectionCode.SUBSCRIPTION_STATE_CONFLICT
    )
    assert jobs.enqueue_calls == []
    assert schedules.ensure_calls == []

    service, jobs, schedules, sources = _facade(scope, subscription_id)
    sources.health = _disabled_health(scope, subscription_id)
    with pytest.raises(SourceServiceInputError) as health_disabled:
        service.enqueue_manual_sync(scope, manual)
    assert (
        health_disabled.value.code
        is SourceSyncRequestRejectionCode.BINDING_NON_EXECUTABLE
    )
    assert jobs.enqueue_calls == []
    assert schedules.ensure_calls == []

    reenable = SourceHealthReenableRequest(
        subscription_id=subscription_id,
        expected_health_version=4,
    )
    for code in (
        SourceSyncRequestRejectionCode.HEALTH_VERSION_CONFLICT,
        SourceSyncRequestRejectionCode.HEALTH_STATE_CONFLICT,
    ):
        service, _, _, sources = _facade(scope, subscription_id)
        sources.reenable_error = SourceSyncRequestRejected(code)
        with pytest.raises(SourceServiceInputError) as cas_error:
            service.reenable_source_health(scope, reenable)
        assert cas_error.value.code is code

    for code in SourceSyncRepositoryFailureCode:
        service, _, _, sources = _facade(scope, subscription_id)
        sources.health_error = SourceSyncRepositoryFailure(code)
        with pytest.raises(SourceServiceUnavailableError) as unavailable:
            service.get_source_health(scope, subscription_id)
        assert unavailable.value.code is code

    service, _, _, sources = _facade(scope, subscription_id)
    assert service.get_source_receipt(scope, UUID(int=801)) is None
    assert service.get_source_health(scope, subscription_id) is sources.health
    assert (
        service.list_source_health_snapshots(
            scope,
            subscription_id,
            None,
            limit=20,
        )
        is sources.page
    )
    assert service.reenable_source_health(scope, reenable) is sources.reenabled_health


def test_source_service_exhaustively_maps_job_and_schedule_input_repository_state_invariant_and_conflict_errors() -> None:
    """Facade调用集合穷尽映射每个typed Job/Schedule error。"""

    scope = _scope()
    subscription_id = _subscription_id()
    manual = _manual_request(subscription_id)
    polling = _polling_request(subscription_id)

    for use_enqueue in (False, True):
        job_conflict = JobIdempotencyConflictError(
            "invalid_input unavailable persisted_invariant"
        )
        jobs = _FakeJobGateway()
        if use_enqueue:
            jobs.enqueue_error = job_conflict
        else:
            jobs.lookup_error = job_conflict
        service, _, _, sources = _facade(
            scope,
            subscription_id,
            job_gateway=jobs,
        )
        with pytest.raises(JobIdempotencyConflictError) as propagated_job:
            service.enqueue_manual_sync(scope, manual)
        assert propagated_job.value is job_conflict
        expected_source_calls = (
            ["get_executable_binding", "get_health"]
            if use_enqueue
            else []
        )
        assert sources.calls == expected_source_calls

        job_input = JobInputError(
            "repository persisted invariant unavailable conflict"
        )
        jobs = _FakeJobGateway()
        if use_enqueue:
            jobs.enqueue_error = job_input
        else:
            jobs.lookup_error = job_input
        service, _, _, _ = _facade(
            scope,
            subscription_id,
            job_gateway=jobs,
        )
        with pytest.raises(SourceServiceInputError) as mapped_input:
            service.enqueue_manual_sync(scope, manual)
        assert (
            mapped_input.value.code
            is SourceSyncRequestRejectionCode.INVALID_INPUT
        )

        job_repository = JobRepositoryFailureError(
            "invalid_input persisted_invariant conflict"
        )
        jobs = _FakeJobGateway()
        if use_enqueue:
            jobs.enqueue_error = job_repository
        else:
            jobs.lookup_error = job_repository
        service, _, _, _ = _facade(
            scope,
            subscription_id,
            job_gateway=jobs,
        )
        with pytest.raises(SourceServiceUnavailableError) as mapped_repository:
            service.enqueue_manual_sync(scope, manual)
        assert (
            mapped_repository.value.code
            is SourceSyncRepositoryFailureCode.UNAVAILABLE
        )

        job_invariant_cases = (
            JobNotFoundError("unavailable invalid_input"),
            JobStateConflictError("unavailable invalid_input"),
            JobCorrelationInvariantError("unavailable invalid_input"),
            JobGovernanceRequiredError("unavailable invalid_input"),
            JobLeaseLostError("unavailable invalid_input"),
            JobDeadlineExceededError("unavailable invalid_input"),
        )
        for error in job_invariant_cases:
            jobs = _FakeJobGateway()
            if use_enqueue:
                jobs.enqueue_error = error
            else:
                jobs.lookup_error = error
            service, _, _, _ = _facade(
                scope,
                subscription_id,
                job_gateway=jobs,
            )
            with pytest.raises(
                SourceServiceUnavailableError
            ) as mapped_invariant:
                service.enqueue_manual_sync(scope, manual)
            assert (
                mapped_invariant.value.code
                is SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT
            )

        unlisted_job_error = RuntimeError(
            "job repository unavailable invalid_input"
        )
        jobs = _FakeJobGateway()
        if use_enqueue:
            jobs.enqueue_unlisted_error = unlisted_job_error
        else:
            jobs.lookup_unlisted_error = unlisted_job_error
        service, _, _, _ = _facade(
            scope,
            subscription_id,
            job_gateway=jobs,
        )
        with pytest.raises(RuntimeError) as propagated_unlisted_job:
            service.enqueue_manual_sync(scope, manual)
        assert propagated_unlisted_job.value is unlisted_job_error

    for use_ensure in (False, True):
        schedule_conflict = ScheduleVersionConflictError(
            "invalid_input unavailable persisted_invariant"
        )
        schedules = _FakeScheduleGateway()
        if use_ensure:
            schedules.ensure_error = schedule_conflict
        else:
            schedules.lookup_error = schedule_conflict
        service, _, _, sources = _facade(
            scope,
            subscription_id,
            schedule_gateway=schedules,
        )
        with pytest.raises(
            ScheduleVersionConflictError
        ) as propagated_schedule:
            service.ensure_polling_schedule(scope, polling)
        assert propagated_schedule.value is schedule_conflict
        expected_source_calls = (
            ["get_executable_binding"] if use_ensure else []
        )
        assert sources.calls == expected_source_calls

        schedule_input = ScheduleInputError(
            "repository persisted invariant unavailable conflict"
        )
        schedules = _FakeScheduleGateway()
        if use_ensure:
            schedules.ensure_error = schedule_input
        else:
            schedules.lookup_error = schedule_input
        service, _, _, _ = _facade(
            scope,
            subscription_id,
            schedule_gateway=schedules,
        )
        with pytest.raises(SourceServiceInputError) as mapped_input:
            service.ensure_polling_schedule(scope, polling)
        assert (
            mapped_input.value.code
            is SourceSyncRequestRejectionCode.INVALID_INPUT
        )

        schedule_repository = ScheduleRepositoryError(
            "invalid_input persisted_invariant conflict"
        )
        schedules = _FakeScheduleGateway()
        if use_ensure:
            schedules.ensure_error = schedule_repository
        else:
            schedules.lookup_error = schedule_repository
        service, _, _, _ = _facade(
            scope,
            subscription_id,
            schedule_gateway=schedules,
        )
        with pytest.raises(SourceServiceUnavailableError) as mapped_repository:
            service.ensure_polling_schedule(scope, polling)
        assert (
            mapped_repository.value.code
            is SourceSyncRepositoryFailureCode.UNAVAILABLE
        )

        schedule_invariant_cases = (
            ScheduleInvariantError("unavailable invalid_input"),
            ScheduleExecutionUnavailableError("unavailable invalid_input"),
        )
        for error in schedule_invariant_cases:
            schedules = _FakeScheduleGateway()
            if use_ensure:
                schedules.ensure_error = error
            else:
                schedules.lookup_error = error
            service, _, _, _ = _facade(
                scope,
                subscription_id,
                schedule_gateway=schedules,
            )
            with pytest.raises(
                SourceServiceUnavailableError
            ) as mapped_invariant:
                service.ensure_polling_schedule(scope, polling)
            assert (
                mapped_invariant.value.code
                is SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT
            )

        unlisted_schedule_error = RuntimeError(
            "schedule repository unavailable invalid_input"
        )
        schedules = _FakeScheduleGateway()
        if use_ensure:
            schedules.ensure_unlisted_error = unlisted_schedule_error
        else:
            schedules.lookup_unlisted_error = unlisted_schedule_error
        service, _, _, _ = _facade(
            scope,
            subscription_id,
            schedule_gateway=schedules,
        )
        with pytest.raises(RuntimeError) as propagated_unlisted_schedule:
            service.ensure_polling_schedule(scope, polling)
        assert propagated_unlisted_schedule.value is unlisted_schedule_error

    job_signal = _UnlistedSignal()
    jobs = _FakeJobGateway()
    jobs.lookup_unlisted_error = job_signal
    service, _, _, _ = _facade(
        scope,
        subscription_id,
        job_gateway=jobs,
    )
    with pytest.raises(_UnlistedSignal) as propagated_job_signal:
        service.enqueue_manual_sync(scope, manual)
    assert propagated_job_signal.value is job_signal

    schedule_signal = _UnlistedSignal()
    schedules = _FakeScheduleGateway()
    schedules.lookup_unlisted_error = schedule_signal
    service, _, _, _ = _facade(
        scope,
        subscription_id,
        schedule_gateway=schedules,
    )
    with pytest.raises(_UnlistedSignal) as propagated_schedule_signal:
        service.ensure_polling_schedule(scope, polling)
    assert propagated_schedule_signal.value is schedule_signal
