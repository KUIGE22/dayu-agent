"""Investment Sources 的同步 public facade。

本模块只拥有六个 public Source 方法、两个窄同步 gateway 与 closed
error mapping。它不导入 execution owner、connector/Fins concrete、Session、
engine 或 PostgreSQL 实现；manual/schedule recovery 始终先读 durable
identity，再决定是否读取 mutable source binding。
"""

from __future__ import annotations

from typing import NoReturn, Protocol
from uuid import UUID

from dayu.investment.composition import PlatformSourceSyncServiceProtocol
from dayu.investment.domain.identifiers import TenantScope
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
)
from dayu.investment.domain.schedules import (
    ScheduleDefinition,
    ScheduleExecutionUnavailableError,
    ScheduleInputError,
    ScheduleInvariantError,
    ScheduleRegistrationRequest,
    ScheduleRepositoryError,
    ScheduleVersionConflictError,
    validate_timezone_name,
)
from dayu.investment.domain.schedules import (
    validate_cron_expression as validate_schedule_cron_expression,
)
from dayu.investment.domain.source import SourceSubscriptionId, SubscriptionStatus
from dayu.investment.domain.source_evidence import SourceSyncAttemptReceipt
from dayu.investment.domain.source_health import (
    SourceHealthProjection,
    SourceHealthReenableRequest,
    SourceHealthSnapshotCursor,
    SourceHealthSnapshotPage,
    SourceHealthStatus,
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
    parse_source_sync_payload,
)
from dayu.investment.domain.source_sync import (
    SOURCE_SYNC_JOB_DESCRIPTOR,
    SourcePollingScheduleRequest,
    SourceServiceInputError,
    SourceServiceUnavailableError,
    SourceSyncEnqueueRequest,
    SourceSyncRepositoryFailure,
    SourceSyncRepositoryFailureCode,
    SourceSyncRequestRejected,
    SourceSyncRequestRejectionCode,
)
from dayu.investment.storage.source_sync_protocols import SourceSyncRepositoryProtocol

_INVESTMENT_SOURCES_SERVICE_NAME = "investment_sources"
"""平台组合根中的稳定 public service 名。"""

_MANUAL_KEY_PREFIX = "source-sync-trigger:v1"
"""Manual Job idempotency key 的固定 namespace。"""

_SCHEDULE_KEY_PREFIX = "investment.source-sync.v1"
"""Polling schedule 缺省 key 的固定 namespace。"""

_MAX_HEALTH_PAGE_SIZE = 200
"""Public health snapshot page 的固定上限。"""


class SourceManualJobGatewayProtocol(Protocol):
    """Facade 消费的 JobService 同步窄协议。"""

    def get_by_idempotency_key(
        self,
        scope: TenantScope,
        *,
        descriptor: JobHandlerDescriptor,
        idempotency_key: str,
    ) -> JobIdempotencyRecord | None:
        """读取 immutable Job request identity。

        Args:
            scope: 可信租户范围。
            descriptor: exact Job handler descriptor。
            idempotency_key: 稳定幂等键。

        Returns:
            命中 record 或 ``None``。

        Raises:
            JobInputError: descriptor 或 key 非法。
            JobRepositoryFailureError: Repository 或 persisted identity 失败。
            JobNotFoundError: Gateway 违反 lookup missing 合同。
            JobStateConflictError: Gateway 观察到非法 durable state。
            JobCorrelationInvariantError: Gateway 观察到 correlation drift。
            JobGovernanceRequiredError: Gateway 错误要求治理动作。
            JobLeaseLostError: Gateway 错误泄漏 lease failure。
            JobDeadlineExceededError: Gateway 错误泄漏 deadline failure。
            JobIdempotencyConflictError: Gateway 报告 durable identity conflict。
        """
        ...

    def enqueue(
        self,
        scope: TenantScope,
        request: JobEnqueueRequest,
    ) -> JobEnqueueReceipt:
        """提交 ordinary durable Job enqueue。

        Args:
            scope: 可信租户范围。
            request: 完整 Job enqueue request。

        Returns:
            Durable enqueue receipt。

        Raises:
            JobInputError: Enqueue request 非法。
            JobRepositoryFailureError: Repository 或 persisted identity 失败。
            JobNotFoundError: Definition 不存在。
            JobStateConflictError: Durable state 冲突。
            JobCorrelationInvariantError: Correlation identity 漂移。
            JobGovernanceRequiredError: Enqueue 被治理规则拒绝。
            JobLeaseLostError: Gateway 错误泄漏 lease failure。
            JobDeadlineExceededError: Gateway 错误泄漏 deadline failure。
            JobIdempotencyConflictError: 同 key immutable intent 漂移。
        """
        ...


class SourceScheduleGatewayProtocol(Protocol):
    """Facade 消费的 ScheduleService 同步窄协议。"""

    def validate_cron_expression(self, expression: str) -> None:
        """复用 Schedule owner 的 validation-only cron seam。

        Args:
            expression: 已通过 domain 结构校验的五字段 cron。

        Returns:
            无。

        Raises:
            ScheduleInputError: croniter 语义非法或无候选。
        """
        ...

    def get_by_key(
        self,
        scope: TenantScope,
        *,
        schedule_key: str,
    ) -> ScheduleDefinition | None:
        """按 tenant 与 stable key 读取当前 definition。

        Args:
            scope: 可信租户范围。
            schedule_key: 稳定 schedule key。

        Returns:
            当前 definition，missing 或 cross-tenant 时为 ``None``。

        Raises:
            ScheduleInputError: scope 或 key 非法。
            ScheduleRepositoryError: Repository 或 persisted definition 失败。
            ScheduleInvariantError: Gateway 观察到 durable invariant drift。
            ScheduleExecutionUnavailableError: Gateway 错误执行了 runtime seam。
            ScheduleVersionConflictError: Gateway 错误报告 immutable conflict。
        """
        ...

    def ensure_registered(
        self,
        scope: TenantScope,
        request: ScheduleRegistrationRequest,
    ) -> ScheduleDefinition:
        """创建或恢复 immutable intent 相同的 schedule。

        Args:
            scope: 可信租户范围。
            request: 已完整校验的 registration intent。

        Returns:
            首次 disabled draft 或 exact current definition。

        Raises:
            ScheduleInputError: Request 非法。
            ScheduleRepositoryError: Repository 或 persisted definition 失败。
            ScheduleInvariantError: Durable invariant 漂移。
            ScheduleExecutionUnavailableError: Gateway 错误执行了 runtime seam。
            ScheduleVersionConflictError: 同 key immutable intent 漂移。
        """
        ...


def _raise_invalid_input() -> NoReturn:
    """抛出 public invalid-input closed error。

    Raises:
        SourceServiceInputError: 恒抛。
    """

    raise SourceServiceInputError(SourceSyncRequestRejectionCode.INVALID_INPUT)


def _raise_persisted_invariant() -> NoReturn:
    """抛出 public persisted-invariant unavailable error。

    Raises:
        SourceServiceUnavailableError: 恒抛。
    """

    raise SourceServiceUnavailableError(
        SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT
    )


def _raise_source_repository_error(
    error: SourceSyncRequestRejected | SourceSyncRepositoryFailure,
) -> NoReturn:
    """把 Source repository closed error 映射到 public Service error。

    Args:
        error: Repository request rejection 或 failure。

    Raises:
        SourceServiceInputError: Request rejection 时保留原 code 抛出。
        SourceServiceUnavailableError: Repository failure 时保留原 code 抛出。
    """

    if isinstance(error, SourceSyncRequestRejected):
        raise SourceServiceInputError(error.code) from None
    raise SourceServiceUnavailableError(error.code) from None


def _raise_downstream_error(
    error: JobIdempotencyConflictError
    | ScheduleVersionConflictError
    | JobInputError
    | ScheduleInputError
    | JobRepositoryFailureError
    | ScheduleRepositoryError
    | JobNotFoundError
    | JobStateConflictError
    | JobCorrelationInvariantError
    | JobGovernanceRequiredError
    | JobLeaseLostError
    | JobDeadlineExceededError
    | ScheduleInvariantError
    | ScheduleExecutionUnavailableError,
) -> NoReturn:
    """穷尽映射 Facade 实际调用集合的 Job/Schedule closed errors。

    Args:
        error: Downstream typed error。

    Raises:
        JobIdempotencyConflictError: Job durable conflict 原样传播。
        ScheduleVersionConflictError: Schedule immutable conflict 原样传播。
        SourceServiceInputError: Downstream input error 收窄为 invalid input。
        SourceServiceUnavailableError: Repository/state/invariant error 收窄为
            unavailable 或 persisted invariant。
    """

    if isinstance(
        error,
        (JobIdempotencyConflictError, ScheduleVersionConflictError),
    ):
        raise error
    if isinstance(error, (JobInputError, ScheduleInputError)):
        raise SourceServiceInputError(
            SourceSyncRequestRejectionCode.INVALID_INPUT
        ) from None
    if isinstance(error, (JobRepositoryFailureError, ScheduleRepositoryError)):
        raise SourceServiceUnavailableError(
            SourceSyncRepositoryFailureCode.UNAVAILABLE
        ) from None
    raise SourceServiceUnavailableError(
        SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT
    ) from None


def _validate_scope(scope: TenantScope) -> None:
    """校验 public 方法收到真实 TenantScope。

    Args:
        scope: 待校验租户范围。

    Raises:
        SourceServiceInputError: scope 类型非法时抛出。
    """

    if not isinstance(scope, TenantScope):
        _raise_invalid_input()


def _manual_key(request: SourceSyncEnqueueRequest) -> str:
    """构造 manual Job 的唯一稳定幂等键。

    Args:
        request: 已校验 manual caller intent。

    Returns:
        ``subscription + trigger`` 固定公式 key。

    Raises:
        无。
    """

    return f"{_MANUAL_KEY_PREFIX}:{request.subscription_id}:{request.trigger_id}"


def _normalized_schedule_request(
    request: SourcePollingScheduleRequest,
) -> SourcePollingScheduleRequest:
    """把可空 schedule key 归一为唯一稳定 key。

    Args:
        request: 已校验 polling caller intent。

    Returns:
        ``schedule_key`` 必为非空的等价 request。

    Raises:
        无。
    """

    schedule_key = (
        request.schedule_key
        if request.schedule_key is not None
        else f"{_SCHEDULE_KEY_PREFIX}:{request.subscription_id}"
    )
    return SourcePollingScheduleRequest(
        subscription_id=request.subscription_id,
        expected_subscription_version=request.expected_subscription_version,
        cron_expression=request.cron_expression,
        timezone_name=request.timezone_name,
        misfire_policy=request.misfire_policy,
        misfire_grace_seconds=request.misfire_grace_seconds,
        job_deadline_seconds=request.job_deadline_seconds,
        schedule_key=schedule_key,
    )


def _recover_manual_receipt(
    scope: TenantScope,
    request: SourceSyncEnqueueRequest,
    idempotency_key: str,
    record: JobIdempotencyRecord,
) -> JobEnqueueReceipt:
    """strict 验证 persisted manual intent 后重建 reused READY receipt。

    Args:
        scope: 可信租户范围。
        request: 当前 caller intent。
        idempotency_key: 当前 caller 派生的 exact key。
        record: Job lookup 返回的 immutable request identity。

    Returns:
        同一 Job identity 的 reused READY receipt。

    Raises:
        JobIdempotencyConflictError: Persisted intent 合法但与 caller 不同。
        SourceServiceUnavailableError: Persisted Source identity 非法。
    """

    if (
        record.tenant_id != scope.tenant_id
        or record.descriptor != SOURCE_SYNC_JOB_DESCRIPTOR
        or record.idempotency_key != idempotency_key
    ):
        _raise_persisted_invariant()
    try:
        payload = parse_source_sync_payload(record.payload)
        if not isinstance(payload, ManualSourceSyncPayload):
            _raise_persisted_invariant()
        persisted_request = SourceSyncEnqueueRequest(
            subscription_id=payload.subscription_id,
            expected_subscription_version=payload.expected_subscription_version,
            trigger_id=payload.trigger_id,
            available_at=record.original_available_at,
            deadline_at=record.deadline_at,
        )
        expected_snapshot = build_source_execution_snapshot(
            payload.execution_snapshot.binding,
            record.original_available_at,
        )
    except (TypeError, ValueError):
        _raise_persisted_invariant()
    if (
        _manual_key(persisted_request) != record.idempotency_key
        or payload.execution_snapshot != expected_snapshot
        or payload.execution_snapshot.binding.tenant_id != record.tenant_id
        or payload.execution_snapshot.binding.subscription_status
        is not SubscriptionStatus.ENABLED
        or payload.request_fingerprint
        != build_manual_source_request_fingerprint(persisted_request)
    ):
        _raise_persisted_invariant()
    if persisted_request != request:
        raise JobIdempotencyConflictError()
    return JobEnqueueReceipt(
        tenant_id=record.tenant_id,
        definition_id=record.definition_id,
        job_id=record.job_id,
        state=JobState.READY,
        idempotency_reused=True,
    )


def _recover_schedule_definition(
    scope: TenantScope,
    request: SourcePollingScheduleRequest,
    definition: ScheduleDefinition,
) -> ScheduleDefinition:
    """strict 验证 persisted scheduled intent 并区分 drift/tamper。

    Args:
        scope: 可信租户范围。
        request: 已归一 schedule key 的 caller intent。
        definition: Schedule lookup 返回的当前 projection。

    Returns:
        Exact persisted current definition。

    Raises:
        ScheduleVersionConflictError: Persisted intent 合法但与 caller 不同。
        SourceServiceUnavailableError: Persisted Source identity 非法。
    """

    if request.schedule_key is None:
        _raise_persisted_invariant()
    if (
        definition.tenant_id != scope.tenant_id
        or definition.schedule_key != request.schedule_key
        or definition.descriptor != SOURCE_SYNC_JOB_DESCRIPTOR
    ):
        _raise_persisted_invariant()
    try:
        payload = parse_source_sync_payload(definition.payload)
        if not isinstance(payload, ScheduledSourceSyncPayload):
            _raise_persisted_invariant()
        persisted_request = SourcePollingScheduleRequest(
            subscription_id=payload.subscription_id,
            expected_subscription_version=payload.expected_subscription_version,
            cron_expression=definition.cron_expression,
            timezone_name=definition.timezone_name,
            misfire_policy=definition.misfire_policy,
            misfire_grace_seconds=definition.misfire_grace_seconds,
            job_deadline_seconds=definition.job_deadline_seconds,
            schedule_key=definition.schedule_key,
        )
    except (TypeError, ValueError):
        _raise_persisted_invariant()
    if (
        payload.schedule_key != definition.schedule_key
        or payload.source_request_fingerprint
        != build_scheduled_source_request_fingerprint(
            persisted_request,
            definition.schedule_key,
        )
    ):
        _raise_persisted_invariant()
    if persisted_request != request:
        raise ScheduleVersionConflictError()
    return definition


class InvestmentSourcesService(PlatformSourceSyncServiceProtocol):
    """Source manual/schedule recovery 与 receipt/health 的同步 facade。

    Args:
        job_gateway: Job lookup/enqueue 窄 gateway。
        schedule_gateway: Schedule validate/lookup/ensure 窄 gateway。
        source_repository: Source binding/receipt/health 七方法 repository。
    """

    def __init__(
        self,
        *,
        job_gateway: SourceManualJobGatewayProtocol,
        schedule_gateway: SourceScheduleGatewayProtocol,
        source_repository: SourceSyncRepositoryProtocol,
    ) -> None:
        """保存三个 closed dependencies，不执行读取或 mutation。

        Args:
            job_gateway: Job lookup/enqueue 窄 gateway。
            schedule_gateway: Schedule validate/lookup/ensure 窄 gateway。
            source_repository: Source binding/receipt/health repository。

        Returns:
            无。

        Raises:
            无。
        """

        self._job_gateway = job_gateway
        self._schedule_gateway = schedule_gateway
        self._source_repository = source_repository

    @property
    def platform_service_name(self) -> str:
        """返回稳定 platform mapping 名。

        Returns:
            精确 ``investment_sources``。

        Raises:
            无。
        """

        return _INVESTMENT_SOURCES_SERVICE_NAME

    def enqueue_manual_sync(
        self,
        scope: TenantScope,
        request: SourceSyncEnqueueRequest,
    ) -> JobEnqueueReceipt:
        """恢复或创建一次 manual Source Sync durable Job。

        Args:
            scope: 可信租户范围。
            request: Manual caller intent。

        Returns:
            首次或 reused durable enqueue receipt。

        Raises:
            SourceServiceInputError: 输入、subscription 或 binding 不可用。
            SourceServiceUnavailableError: Repository 或 persisted identity 失败。
            JobIdempotencyConflictError: 同 key caller intent 漂移。
        """

        _validate_scope(scope)
        if type(request) is not SourceSyncEnqueueRequest:
            _raise_invalid_input()
        idempotency_key = _manual_key(request)
        caller_fingerprint = build_manual_source_request_fingerprint(request)
        try:
            record = self._job_gateway.get_by_idempotency_key(
                scope,
                descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
                idempotency_key=idempotency_key,
            )
        except (
            JobIdempotencyConflictError,
            JobInputError,
            JobRepositoryFailureError,
            JobNotFoundError,
            JobStateConflictError,
            JobCorrelationInvariantError,
            JobGovernanceRequiredError,
            JobLeaseLostError,
            JobDeadlineExceededError,
        ) as error:
            _raise_downstream_error(error)
        if record is not None:
            if not isinstance(record, JobIdempotencyRecord):
                _raise_persisted_invariant()
            return _recover_manual_receipt(
                scope,
                request,
                idempotency_key,
                record,
            )

        try:
            binding = self._source_repository.get_executable_binding(
                scope,
                request.subscription_id,
            )
        except (SourceSyncRequestRejected, SourceSyncRepositoryFailure) as error:
            _raise_source_repository_error(error)
        if not isinstance(binding, SourceExecutionBinding):
            _raise_persisted_invariant()
        if (
            binding.tenant_id != scope.tenant_id
            or binding.subscription_id != request.subscription_id
        ):
            _raise_persisted_invariant()
        if binding.subscription_version != request.expected_subscription_version:
            raise SourceServiceInputError(
                SourceSyncRequestRejectionCode.SUBSCRIPTION_VERSION_CONFLICT
            )
        if binding.subscription_status is not SubscriptionStatus.ENABLED:
            raise SourceServiceInputError(
                SourceSyncRequestRejectionCode.SUBSCRIPTION_STATE_CONFLICT
            )
        try:
            health = self._source_repository.get_health(
                scope,
                request.subscription_id,
            )
        except (SourceSyncRequestRejected, SourceSyncRepositoryFailure) as error:
            _raise_source_repository_error(error)
        if (
            not isinstance(health, SourceHealthProjection)
            or health.tenant_id != scope.tenant_id
            or health.subscription_id != request.subscription_id
        ):
            _raise_persisted_invariant()
        if health.status is SourceHealthStatus.DISABLED:
            raise SourceServiceInputError(
                SourceSyncRequestRejectionCode.BINDING_NON_EXECUTABLE
            )

        snapshot = build_source_execution_snapshot(binding, request.available_at)
        payload = ManualSourceSyncPayload(
            subscription_id=request.subscription_id,
            expected_subscription_version=request.expected_subscription_version,
            trigger_id=request.trigger_id,
            execution_snapshot=snapshot,
            request_fingerprint=caller_fingerprint,
        )
        enqueue_request = JobEnqueueRequest(
            descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
            idempotency_key=idempotency_key,
            payload=build_manual_source_sync_payload_document(payload),
            available_at=request.available_at,
            deadline_at=request.deadline_at,
        )
        try:
            return self._job_gateway.enqueue(scope, enqueue_request)
        except (
            JobIdempotencyConflictError,
            JobInputError,
            JobRepositoryFailureError,
            JobNotFoundError,
            JobStateConflictError,
            JobCorrelationInvariantError,
            JobGovernanceRequiredError,
            JobLeaseLostError,
            JobDeadlineExceededError,
        ) as error:
            _raise_downstream_error(error)

    def ensure_polling_schedule(
        self,
        scope: TenantScope,
        request: SourcePollingScheduleRequest,
    ) -> ScheduleDefinition:
        """恢复或创建一个 Source polling disabled schedule draft。

        Args:
            scope: 可信租户范围。
            request: Polling schedule caller intent。

        Returns:
            首次 disabled draft 或 exact current definition。

        Raises:
            SourceServiceInputError: 输入、subscription 或 binding 不可用。
            SourceServiceUnavailableError: Repository 或 persisted identity 失败。
            ScheduleVersionConflictError: 同 key immutable intent 漂移。
        """

        _validate_scope(scope)
        if type(request) is not SourcePollingScheduleRequest:
            _raise_invalid_input()
        normalized = _normalized_schedule_request(request)
        if normalized.schedule_key is None:
            _raise_persisted_invariant()
        try:
            validate_schedule_cron_expression(normalized.cron_expression)
            validate_timezone_name(normalized.timezone_name)
            if (
                normalized.job_deadline_seconds
                <= normalized.misfire_grace_seconds
            ):
                raise ScheduleInputError(
                    "job_deadline_seconds 必须大于 misfire_grace_seconds"
                )
            self._schedule_gateway.validate_cron_expression(
                normalized.cron_expression
            )
        except (
            ScheduleVersionConflictError,
            ScheduleInputError,
            ScheduleRepositoryError,
            ScheduleInvariantError,
            ScheduleExecutionUnavailableError,
        ) as error:
            _raise_downstream_error(error)
        caller_fingerprint = build_scheduled_source_request_fingerprint(
            normalized,
            normalized.schedule_key,
        )
        try:
            definition = self._schedule_gateway.get_by_key(
                scope,
                schedule_key=normalized.schedule_key,
            )
        except (
            ScheduleVersionConflictError,
            ScheduleInputError,
            ScheduleRepositoryError,
            ScheduleInvariantError,
            ScheduleExecutionUnavailableError,
        ) as error:
            _raise_downstream_error(error)
        if definition is not None:
            if not isinstance(definition, ScheduleDefinition):
                _raise_persisted_invariant()
            return _recover_schedule_definition(scope, normalized, definition)

        try:
            binding = self._source_repository.get_executable_binding(
                scope,
                normalized.subscription_id,
            )
        except (SourceSyncRequestRejected, SourceSyncRepositoryFailure) as error:
            _raise_source_repository_error(error)
        if not isinstance(binding, SourceExecutionBinding):
            _raise_persisted_invariant()
        if (
            binding.tenant_id != scope.tenant_id
            or binding.subscription_id != normalized.subscription_id
        ):
            _raise_persisted_invariant()
        if binding.subscription_version != normalized.expected_subscription_version:
            raise SourceServiceInputError(
                SourceSyncRequestRejectionCode.SUBSCRIPTION_VERSION_CONFLICT
            )

        scheduled_payload = ScheduledSourceSyncPayload(
            subscription_id=normalized.subscription_id,
            source_definition_id=binding.source_definition_id,
            expected_subscription_version=normalized.expected_subscription_version,
            schedule_key=normalized.schedule_key,
            source_request_fingerprint=caller_fingerprint,
        )
        try:
            registration = ScheduleRegistrationRequest(
                schedule_key=normalized.schedule_key,
                descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
                payload=build_scheduled_source_sync_payload_document(
                    scheduled_payload
                ),
                cron_expression=normalized.cron_expression,
                timezone_name=normalized.timezone_name,
                misfire_policy=normalized.misfire_policy,
                misfire_grace_seconds=normalized.misfire_grace_seconds,
                job_deadline_seconds=normalized.job_deadline_seconds,
            )
            return self._schedule_gateway.ensure_registered(scope, registration)
        except (
            ScheduleVersionConflictError,
            ScheduleInputError,
            ScheduleRepositoryError,
            ScheduleInvariantError,
            ScheduleExecutionUnavailableError,
        ) as error:
            _raise_downstream_error(error)

    def get_source_receipt(
        self,
        scope: TenantScope,
        source_sync_run_id: UUID,
    ) -> SourceSyncAttemptReceipt | None:
        """读取 tenant-scoped Source receipt。

        Args:
            scope: 可信租户范围。
            source_sync_run_id: Source run UUID。

        Returns:
            Strict receipt，或 missing/legacy 时 ``None``。

        Raises:
            SourceServiceInputError: 输入非法或 repository request 拒绝。
            SourceServiceUnavailableError: Repository failure。
        """

        _validate_scope(scope)
        if type(source_sync_run_id) is not UUID or source_sync_run_id.int == 0:
            _raise_invalid_input()
        try:
            return self._source_repository.get_source_receipt(
                scope,
                source_sync_run_id,
            )
        except (SourceSyncRequestRejected, SourceSyncRepositoryFailure) as error:
            _raise_source_repository_error(error)

    def get_source_health(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
    ) -> SourceHealthProjection:
        """读取 tenant-scoped Source health head。

        Args:
            scope: 可信租户范围。
            subscription_id: Source subscription identity。

        Returns:
            Persisted 或 virtual health projection。

        Raises:
            SourceServiceInputError: 输入非法或 repository request 拒绝。
            SourceServiceUnavailableError: Repository failure。
        """

        _validate_scope(scope)
        if type(subscription_id) is not SourceSubscriptionId:
            _raise_invalid_input()
        try:
            return self._source_repository.get_health(scope, subscription_id)
        except (SourceSyncRequestRejected, SourceSyncRepositoryFailure) as error:
            _raise_source_repository_error(error)

    def list_source_health_snapshots(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
        cursor: SourceHealthSnapshotCursor | None,
        *,
        limit: int,
    ) -> SourceHealthSnapshotPage:
        """按 descending keyset 分页读取 Source health snapshots。

        Args:
            scope: 可信租户范围。
            subscription_id: Source subscription identity。
            cursor: 可空 keyset cursor。
            limit: Exact 1..200 页大小。

        Returns:
            Strict snapshot page。

        Raises:
            SourceServiceInputError: 输入非法或 repository request 拒绝。
            SourceServiceUnavailableError: Repository failure。
        """

        _validate_scope(scope)
        if (
            type(subscription_id) is not SourceSubscriptionId
            or (cursor is not None and type(cursor) is not SourceHealthSnapshotCursor)
            or type(limit) is not int
            or not 1 <= limit <= _MAX_HEALTH_PAGE_SIZE
        ):
            _raise_invalid_input()
        try:
            return self._source_repository.list_health_snapshots(
                scope,
                subscription_id,
                cursor,
                limit=limit,
            )
        except (SourceSyncRequestRejected, SourceSyncRepositoryFailure) as error:
            _raise_source_repository_error(error)

    def reenable_source_health(
        self,
        scope: TenantScope,
        request: SourceHealthReenableRequest,
    ) -> SourceHealthProjection:
        """以 exact disabled health version CAS 恢复 healthy。

        Args:
            scope: 可信租户范围。
            request: Operator re-enable request。

        Returns:
            Version 前进后的 healthy projection。

        Raises:
            SourceServiceInputError: 输入、subscription、状态或版本冲突。
            SourceServiceUnavailableError: Repository failure。
        """

        _validate_scope(scope)
        if type(request) is not SourceHealthReenableRequest:
            _raise_invalid_input()
        try:
            return self._source_repository.reenable_health(scope, request)
        except (SourceSyncRequestRejected, SourceSyncRepositoryFailure) as error:
            _raise_source_repository_error(error)


__all__ = ["InvestmentSourcesService"]
