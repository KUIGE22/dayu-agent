"""投资平台 repository 协议与稳定错误。

本模块是 Slice 1.2 的 repository 契约真源（S12-CTRL-01/05），定义：

- 五类稳定错误层级：``RepositoryError`` 及其
  ``RepositoryInputError`` / ``RepositoryNotFoundError`` /
  ``RepositoryConflictError`` / ``RepositoryOptimisticConflictError``；
- ``IdentityRepositoryProtocol``：公司+证券原子注册、按 id 读取与
  ``(exchange_mic, ticker)`` 查找；
- ``SourceRepositoryProtocol``：数据源定义注册/读取/查找与订阅
  创建/读取/CAS 更新；
- ``WorkspaceImportRepositoryProtocol``（S15-CTRL-09）：workspace
  import 唯一单事务发布（advisory xact lock + marker + public
  reconcile + locator + completed marker）。

设计约束：

- 本模块位于 ``storage``（SQL implementation 层），只依赖 pure domain
  与标准库；每个公开方法首参显式为 ``TenantScope``；
- 稳定错误消息是固定 safe code，不含 DSN/SQL/候选值；
- 协议不暴露 ORM row、SQLAlchemy 类型或 ``Any``/``object``。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

from dayu.investment.domain.identifiers import CompanyId, SecurityId, TenantScope
from dayu.investment.domain.jobs import (
    AgentRunCorrelation,
    AgentRunCorrelationObservation,
    AgentRunStartAuthorizationDecision,
    AgentRunTerminalReconciliationDecision,
    JobAttemptReceipt,
    JobCancellationRequest,
    JobClaim,
    JobCompletion,
    JobEnqueueReceipt,
    JobEnqueueRequest,
    JobFailure,
    JobLeaseHandle,
    JobRecoveryResult,
)
from dayu.investment.domain.source import (
    CompanyProjection,
    CompanySecurityRegistration,
    RegisteredCompanySecurity,
    SecurityProjection,
    SourceDefinitionCreateRequest,
    SourceDefinitionId,
    SourceDefinitionProjection,
    SourceSubscriptionCreateRequest,
    SourceSubscriptionId,
    SourceSubscriptionProjection,
    SourceSubscriptionUpdateRequest,
)
from dayu.investment.domain.workspace_import import (
    WorkspaceImportReceipt,
    WorkspaceImportRequest,
)

if TYPE_CHECKING:
    from dayu.investment.domain.jobs import (
        AgentRunGovernanceCursor,
        AgentRunGovernanceProjectionPage,
        JobHeartbeatResult,
    )
    from dayu.investment.domain.schedules import (
        ScheduleActivationRequest,
        ScheduleDefinition,
        ScheduleDueCursor,
        ScheduleDuePage,
        ScheduleMarkEnqueuedResult,
        ScheduleMaterializationAdmission,
        ScheduleMaterializationDecision,
        ScheduleObservation,
        ScheduleOccurrence,
        ScheduleRegistrationRequest,
        ScheduleReplayCursor,
        ScheduleReplayPage,
        ScheduleReservationBatch,
        ScheduleReservationResult,
        ScheduleStateTransitionResult,
    )


class RepositoryError(RuntimeError):
    """repository 操作失败的稳定基类。

    消息只含固定 safe code，绝不包含 DSN、SQL、候选值或 credential。
    """


class RepositoryInputError(RepositoryError):
    """repository 输入非法时抛出的错误。

    在创建/checkout Session 前由 DTO/repository boundary 校验触发；
    不得执行 SQL，也不得传播 psycopg/SQLAlchemy 的类型转换错误。
    """


class RepositoryNotFoundError(RepositoryError):
    """目标租户内 row 不存在时抛出的错误。

    跨租户访问同样表现为 not-found，不泄漏目标存在性。
    """


class RepositoryConflictError(RepositoryError):
    """唯一键或业务键冲突时抛出的错误。"""


class RepositoryOptimisticConflictError(RepositoryConflictError):
    """CAS 更新时 ``expected_version`` 与当前版本不一致抛出的错误。"""


@runtime_checkable
class IdentityRepositoryProtocol(Protocol):
    """identity（公司/证券）repository 契约。"""

    def register_company_security(
        self,
        scope: TenantScope,
        request: CompanySecurityRegistration,
    ) -> RegisteredCompanySecurity:
        """原子注册公司+证券。

        Args:
            scope: 租户范围。
            request: 公司+证券注册请求。

        Returns:
            注册结果投影。

        Raises:
            RepositoryInputError: 输入非法时抛出。
            RepositoryConflictError: 唯一键冲突时抛出。
        """
        ...

    def get_company(
        self,
        scope: TenantScope,
        company_id: CompanyId,
    ) -> CompanyProjection | None:
        """按 id 读取公司。

        Args:
            scope: 租户范围。
            company_id: 公司标识。

        Returns:
            公司投影或 ``None``。
        """
        ...

    def get_security(
        self,
        scope: TenantScope,
        security_id: SecurityId,
    ) -> SecurityProjection | None:
        """按 id 读取证券。

        Args:
            scope: 租户范围。
            security_id: 证券标识。

        Returns:
            证券投影或 ``None``。
        """
        ...

    def find_security(
        self,
        scope: TenantScope,
        exchange_mic: str,
        ticker: str,
    ) -> SecurityProjection | None:
        """按交易所 MIC 与证券代码查找证券。

        Args:
            scope: 租户范围。
            exchange_mic: 4 位大写交易所 MIC。
            ticker: 证券代码。

        Returns:
            证券投影或 ``None``。
        """
        ...


@runtime_checkable
class SourceRepositoryProtocol(Protocol):
    """source（数据源定义/订阅）repository 契约。"""

    def register_source_definition(
        self,
        scope: TenantScope,
        request: SourceDefinitionCreateRequest,
    ) -> SourceDefinitionProjection:
        """注册数据源定义。

        Args:
            scope: 租户范围。
            request: 数据源定义创建请求。

        Returns:
            数据源定义投影。

        Raises:
            RepositoryInputError: 输入非法时抛出。
            RepositoryConflictError: ``source_key`` 冲突时抛出。
        """
        ...

    def get_source_definition(
        self,
        scope: TenantScope,
        source_definition_id: SourceDefinitionId,
    ) -> SourceDefinitionProjection | None:
        """按 id 读取数据源定义。

        Args:
            scope: 租户范围。
            source_definition_id: 数据源定义标识。

        Returns:
            数据源定义投影或 ``None``。
        """
        ...

    def find_source_definition(
        self,
        scope: TenantScope,
        source_key: str,
    ) -> SourceDefinitionProjection | None:
        """按 ``source_key`` 查找数据源定义。

        Args:
            scope: 租户范围。
            source_key: 数据源唯一键。

        Returns:
            数据源定义投影或 ``None``。
        """
        ...

    def create_source_subscription(
        self,
        scope: TenantScope,
        request: SourceSubscriptionCreateRequest,
    ) -> SourceSubscriptionProjection:
        """创建数据源订阅。

        Args:
            scope: 租户范围。
            request: 订阅创建请求。

        Returns:
            订阅投影。

        Raises:
            RepositoryInputError: 输入非法时抛出。
            RepositoryConflictError: 订阅目标冲突时抛出。
        """
        ...

    def get_source_subscription(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
    ) -> SourceSubscriptionProjection | None:
        """按 id 读取订阅。

        Args:
            scope: 租户范围。
            subscription_id: 订阅标识。

        Returns:
            订阅投影或 ``None``。
        """
        ...

    def update_source_subscription(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
        expected_version: int,
        request: SourceSubscriptionUpdateRequest,
    ) -> SourceSubscriptionProjection:
        """CAS 更新订阅（``tenant_id + id + version``）。

        Args:
            scope: 租户范围。
            subscription_id: 订阅标识。
            expected_version: 期望版本（正整数）。
            request: 订阅更新请求。

        Returns:
            更新后的订阅投影。

        Raises:
            RepositoryInputError: 输入非法时抛出。
            RepositoryNotFoundError: row 不存在（含跨租户）时抛出。
            RepositoryOptimisticConflictError: 版本不一致时抛出。
        """
        ...


@runtime_checkable
class JobStoreProtocol(Protocol):
    """durable job/attempt/lease/receipt/event/correlation 仓储契约。

    每个方法拥有自己的 tenant-scoped 单事务（``SET LOCAL app.tenant_id``
    后取 PG 时钟）；本协议是 ``PostgresJobStore`` 的唯一合法接口，不接收
    或读取 descriptor registry。存储层永不 import ``dayu.host`` /
    ``dayu.contracts``，也绝不接收 ``RunRecord`` 或 Host reader。
    """

    def enqueue(
        self,
        scope: TenantScope,
        request: JobEnqueueRequest,
    ) -> JobEnqueueReceipt:
        """入队一个已通过 Service registry gate 的 job。

        Args:
            scope: 租户范围。
            request: 已验证的入队请求。

        Returns:
            入队收据（同 fingerprint 重放返回 ``idempotency_reused=True``）。

        Raises:
            JobIdempotencyConflictError: 同 key 不同 fingerprint 时抛出。
            JobStateConflictError: definition 为 disabled 时抛出。
        """
        ...

    def claim(
        self,
        scope: TenantScope,
        worker_id: str,
    ) -> JobClaim | None:
        """以 SKIP LOCKED 领取一个 ready job。

        Args:
            scope: 租户范围。
            worker_id: worker 标识。

        Returns:
            ``JobClaim``；无可用 job 时返回 ``None``。
        """
        ...

    def heartbeat(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
    ) -> JobHeartbeatResult:
        """续约有效 lease 并返回闭合 heartbeat 结果。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。

        Returns:
            续约后的 ``JobHeartbeatResult``（action + claim）；generic
            job 返回 ``renewed``，未终结 correlation 的 job 按
            cancel/deadline 是否已到返回 ``renewed``/``governance_required``。

        Raises:
            JobLeaseLostError: lease 失效或 fence/token 不匹配时抛出。
            JobStateConflictError: generic job 已有 cancel intent 时抛出。
            JobDeadlineExceededError: generic job 已到 deadline 且已
                收敛 failed 时抛出。
        """
        ...

    def complete(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        completion: JobCompletion,
    ) -> JobAttemptReceipt:
        """以有效 lease 正常完成 job。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。
            completion: 完成结果。

        Returns:
            immutable attempt receipt。

        Raises:
            JobLeaseLostError: lease 失效时抛出。
            JobDeadlineExceededError: 无 cancel intent 但已到 deadline 时抛出。
            JobGovernanceRequiredError: 存在未终结 correlation 时零
                mutation 抛出（Worker 转 governance）。
        """
        ...

    def fail(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        failure: JobFailure,
    ) -> JobRecoveryResult:
        """以有效 lease 声明安全失败。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。
            failure: 安全失败声明。

        Returns:
            收敛后的 recovery 结果。

        Raises:
            JobLeaseLostError: lease 失效时抛出。
            JobGovernanceRequiredError: 存在未终结 correlation 时零
                mutation 抛出（Worker 转 governance）。
        """
        ...

    def cancel(
        self,
        scope: TenantScope,
        request: JobCancellationRequest,
    ) -> JobRecoveryResult:
        """请求取消一个 job。

        Args:
            scope: 租户范围。
            request: 取消请求。

        Returns:
            收敛后的 recovery 结果。
        """
        ...

    def recover(
        self,
        scope: TenantScope,
    ) -> tuple[JobRecoveryResult, ...]:
        """收敛所有从未提交 correlation 的过期 leased/cancel_requested attempt。

        Args:
            scope: 租户范围。

        Returns:
            按 ``(job_id ASC, attempt_id ASC)`` 排序的 recovery 结果 tuple。
        """
        ...

    def recover_agent_run_after_no_host(
        self,
        scope: TenantScope,
        correlation_id: UUID,
        observation_sha256: str,
    ) -> JobRecoveryResult | None:
        """对刚得到 ``NO_HOST_RUN`` 的该一条 correlation 执行 targeted 恢复。

        Args:
            scope: 租户范围。
            correlation_id: 目标 correlation UUID。
            observation_sha256: 该 decision observation 的 sha256。

        Returns:
            ``JobRecoveryResult``；任一前提变化时返回 ``None``（零
            mutation）。

        Raises:
            无。
        """
        ...

    def list_governable_agent_runs(
        self,
        scope: TenantScope,
        cursor: AgentRunGovernanceCursor | None,
        *,
        limit: int,
    ) -> AgentRunGovernanceProjectionPage:
        """列出全部未终结 correlation 的 governance join projection。

        覆盖 lease 有效/过期的全部未终结 correlation，以 PG clock/
        tenant join 收窄；固定 ``ORDER BY deadline_at ASC,
        correlation_id ASC`` 与同 tuple keyset。deadline/cancel truth
        只来自 PG 持久化列与同一事务 PG clock。

        Args:
            scope: 租户范围。
            cursor: 上一页 keyset cursor；从头开始时为 ``None``。
            limit: 本页行数上限（keyword-only，精确来自 settings
                governance page size）。

        Returns:
            本页 projection 与下一页 cursor（已到尾部时为 ``None``）。

        Raises:
            JobInputError: cursor 或 limit 不满足闭合输入契约时抛出。
        """
        ...

    def reserve_agent_run_correlation(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
    ) -> AgentRunCorrelation:
        """在独立 PG 事务中保留一个 agent run correlation（Transaction 2）。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。

        Returns:
            已持久化的 ``AgentRunCorrelation``。

        Raises:
            JobLeaseLostError: lease/attempt/job 状态不匹配时抛出。
            JobDeadlineExceededError: 已到 deadline 时抛出。
            JobCorrelationInvariantError: 已存在 correlation 身份不一致时抛出。
        """
        ...

    def get_agent_run_correlation(
        self,
        scope: TenantScope,
        correlation_id: UUID,
    ) -> AgentRunCorrelation:
        """按 ``(tenant_id, id)`` 精确读取 correlation。

        Args:
            scope: 租户范围。
            correlation_id: correlation UUID。

        Returns:
            完整 immutable identity/state/version 投影。

        Raises:
            JobNotFoundError: 本租户不存在或跨租户时抛出。
            JobCorrelationInvariantError: 读到的 row 违反不变量时抛出。
        """
        ...

    def list_expired_agent_run_correlations(
        self,
        scope: TenantScope,
    ) -> tuple[AgentRunCorrelation, ...]:
        """列出已提交 correlation 且绑定 attempt lease 已过期的 correlation。

        Args:
            scope: 租户范围。

        Returns:
            按 ``(created_at ASC, id ASC)`` 排序的 correlation tuple。
        """
        ...

    def authorize_agent_run_start(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        correlation_id: UUID,
    ) -> AgentRunStartAuthorizationDecision:
        """在单个 PG 事务内产生 live start authorization 决策。

        对任何无效 lease（缺失/过期/wrong tenant/job/attempt/fence/
        token、非 current attempt、cancel intent、deadline 或 correlation
        已 terminal）返回闭合 decision（``LEASE_LOST``/``CANCEL``/
        ``DEADLINE_EXCEEDED``/``INVARIANT_FAILURE``），零业务状态变更；
        绝不抛 ``JobLeaseLostError``。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。
            correlation_id: 目标 correlation UUID。

        Returns:
            闭合决策（含 correlation 快照）。

        Raises:
            无。
        """
        ...

    def reconcile_agent_run_terminal(
        self,
        scope: TenantScope,
        correlation_id: UUID,
        observation: AgentRunCorrelationObservation,
    ) -> AgentRunTerminalReconciliationDecision:
        """在单个 PG 事务内以 observation 收敛 correlation/attempt/job。

        Args:
            scope: 租户范围。
            correlation_id: 目标 correlation UUID。
            observation: Service strict mapping 出的 observation。

        Returns:
            闭合决策（含 immutable receipt 复用）。

        Raises:
            JobNotFoundError: correlation 不存在时抛出。
        """
        ...


@runtime_checkable
class ScheduleStoreProtocol(Protocol):
    """durable schedule/occurrence 仓储契约（Slice 2.2）。

    每个方法拥有自己的 tenant-scoped 单事务（``SET LOCAL app.tenant_id``
    后取 PG 时钟）。``job_schedules`` 是 immutable schedule
    definition/current cursor 真源；``job_schedule_occurrences`` 是
    cursor 与 job enqueue 之间的 durable outbox。``reserve_occurrences``
    与 ``begin_materialization`` / ``set_state`` 之间的竞态由
    schedule 行锁线性化：disable 先赢则 PENDING->SKIPPED 且零 job，
    begin 先赢则 MATERIALIZING 成为不可撤销的入队承诺。本协议不 import
    Host/Service/Redis/croniter。
    """

    def register(
        self,
        scope: TenantScope,
        request: ScheduleRegistrationRequest,
    ) -> ScheduleDefinition:
        """注册一个新的 disabled draft schedule definition。

        Args:
            scope: 租户范围。
            request: 注册请求（descriptor/payload/cron/timezone 内容
                注册后不可原地修改）。

        Returns:
            已持久化的 ``ScheduleDefinition``（state=disabled）。

        Raises:
            ScheduleInputError: 输入非法时抛出。
            ScheduleVersionConflictError: schedule_key 已存在时抛出。
        """
        ...

    def get(
        self,
        scope: TenantScope,
        schedule_id: UUID,
    ) -> ScheduleObservation | None:
        """按 ``(tenant_id, id)`` 读取 schedule 与同事务 PG 时钟。

        Args:
            scope: 租户范围。
            schedule_id: schedule UUID。

        Returns:
            ``ScheduleObservation``；本租户不存在或跨租户时返回
            ``None``。

        Raises:
            ScheduleInputError: schedule UUID 非法时抛出。
            ScheduleRepositoryError: PostgreSQL 操作或持久数据非法时抛出。
        """
        ...

    def get_occurrence(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
    ) -> ScheduleOccurrence | None:
        """按租户读取一条冻结 occurrence。

        Args:
            scope: 租户范围。
            occurrence_id: occurrence UUID。

        Returns:
            本租户的完整 occurrence；不存在或跨租户时返回 ``None``。

        Raises:
            无。
        """
        ...

    def set_state(
        self,
        scope: TenantScope,
        request: ScheduleActivationRequest,
        *,
        activation_next_fire_at: datetime | None,
    ) -> ScheduleStateTransitionResult:
        """CAS 切换 schedule state 并收敛 occurrence。

        ``disabled`` 同锁顺序把 schedule 置 disabled 并仅将仍为
        PENDING 的 occurrence 改为 SKIPPED(schedule_disabled)；
        MATERIALIZING/ENQUEUED/SKIPPED 不变。与 ``begin_materialization``
        的先后由同一 schedule 行锁线性化。

        Args:
            scope: 租户范围。
            request: 激活请求（含 expected_version CAS）。
            activation_next_fire_at: ACTIVE 尝试使用的 PG-clock candidate；
                DISABLED/unchanged 请求必须为 ``None``。

        Returns:
            携带 before/after/PG clock/candidate 的闭合 transition result。

        Raises:
            ScheduleVersionConflictError: 本租户不存在/跨租户或
                version/state/cursor 已变化时抛出（零 mutation）。
        """
        ...

    def list_due(
        self,
        scope: TenantScope,
        cursor: ScheduleDueCursor | None,
        *,
        limit: int,
    ) -> ScheduleDuePage:
        """按 process-local keyset 列出 bounded active due page。

        Args:
            scope: 租户范围。
            cursor: 上一次扫描的 due cursor；``None`` 从队头读取。
            limit: keyword-only 行数上限。

        Returns:
            无重复 wrap 的 ``ScheduleDuePage``；所有 observation 共享
            本次调用唯一 PG clock。

        Raises:
            ScheduleInputError: cursor 或 limit 非法时抛出。
            ScheduleRepositoryError: PostgreSQL 操作或持久数据非法时抛出。
        """
        ...

    def reserve_occurrences(
        self,
        scope: TenantScope,
        batch: ScheduleReservationBatch,
    ) -> ScheduleReservationResult:
        """按 schedule->occurrence 固定锁序插入 batch 并 CAS 推进 cursor。

        验证 active/version/current cursor；state/version/cursor 已变化
        时返回 ``ScheduleReservationResult(lost_race, ())`` 且零
        mutation，绝不抛裸 ``IntegrityError``。每个新 occurrence 的
        ``schedule_version=expected_version``，成功后 schedule version
        变为 ``expected_version+1``。

        Args:
            scope: 租户范围。
            batch: 由 Service 计算出的 reservation batch。

        Returns:
            闭合 reservation 结果。

        Raises:
            ScheduleInputError: batch 类型非法时抛出。
            ScheduleRepositoryError: PostgreSQL 操作或持久数据非法时抛出。
        """
        ...

    def list_replayable(
        self,
        scope: TenantScope,
        cursor: ScheduleReplayCursor | None,
        *,
        limit: int,
    ) -> ScheduleReplayPage:
        """列出 MATERIALIZING-first、PENDING-keyset 的 bounded page。

        Args:
            scope: 租户范围。
            cursor: PENDING process-local keyset cursor；``None`` 从队头。
            limit: keyword-only 行数上限。

        Returns:
            无重复 wrap 的 replay page；MATERIALIZING 严格先于 PENDING。

        Raises:
            ScheduleInputError: cursor 或 limit 非法时抛出。
            ScheduleRepositoryError: PostgreSQL 操作或持久数据非法时抛出。
        """
        ...

    def begin_materialization(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
        *,
        admission: ScheduleMaterializationAdmission,
    ) -> ScheduleMaterializationDecision:
        """原子执行 PENDING->MATERIALIZING（或重放/终态 no-work）。

        PENDING+available 在 schedule 行锁内原子转 MATERIALIZING；
        PENDING+unavailable 保持原行并返回 ``unavailable``；PENDING
        不接受 committed replay。MATERIALIZING 对任一 stale admission
        均返回 ``enqueue``；ENQUEUED/SKIPPED 返回 closed no-work。

        Args:
            scope: 租户范围。
            occurrence_id: 目标 occurrence UUID。
            admission: PENDING availability 或 durable replay 的闭合准入。

        Returns:
            闭合 materialization decision。

        Raises:
            ScheduleInputError: occurrence UUID 或 admission 非法时抛出。
            ScheduleInvariantError: 状态或 parent/occurrence identity
                不满足持久化不变量时抛出。
            ScheduleRepositoryError: PostgreSQL 操作或持久数据非法时抛出。
        """
        ...

    def mark_enqueued(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
        expected_snapshot_fingerprint: str,
        job_id: UUID,
    ) -> ScheduleMarkEnqueuedResult:
        """只接受 MATERIALIZING->ENQUEUED 的首次 job 绑定。

        即使 parent schedule 已在 begin 之后 disabled 也必须完成；
        ENQUEUED+同 job 为 idempotent replay，不同 job 抛 invariant；
        SKIPPED 返回 ``skipped_conflict``（调用方必须以 runtime
        invariant 停止）；PENDING 直接 invariant。

        Args:
            scope: 租户范围。
            occurrence_id: 目标 occurrence UUID。
            expected_snapshot_fingerprint: begin 时冻结的 snapshot
                fingerprint（逐字段重验）。
            job_id: 已入队 job UUID。

        Returns:
            闭合 mark 结果。

        Raises:
            ScheduleInvariantError: 状态/snapshot/job 不变量破坏时抛出。
        """
        ...


@runtime_checkable
class WorkspaceImportRepositoryProtocol(Protocol):
    """旧 workspace 显式导入 repository 契约（S15-CTRL-09）。

    ``publish_import`` 是唯一 DB transaction owner：每次调用只建一个
    session，``SET LOCAL app.tenant_id`` 后在同一 transaction 内完成
    advisory xact lock、marker read、public reference reconcile、
    source definition reconcile、locator inserts 与 completed marker。
    已有 marker 且全部 intended rows exact 时返回 ``no_op``；任何字段
    或 row drift 抛稳定 drift 错误。
    """

    def publish_import(
        self,
        scope: TenantScope,
        request: WorkspaceImportRequest,
    ) -> WorkspaceImportReceipt:
        """以单事务发布一次 workspace import。

        Args:
            scope: 租户范围。
            request: 已 fingerprint 的纯 import 请求。

        Returns:
            纯结果收据（``committed`` 或 ``no_op``）。

        Raises:
            WorkspaceImportSchemaUnavailableError: 0002 schema 不可用时
                抛出。
            WorkspaceImportDriftError: marker/row 与 intended projection
                不一致时抛出。
            WorkspaceImportRepositoryFailureError: 数据库失败时抛出。
        """
        ...


__all__ = [
    "IdentityRepositoryProtocol",
    "JobStoreProtocol",
    "RepositoryConflictError",
    "RepositoryError",
    "RepositoryInputError",
    "RepositoryNotFoundError",
    "RepositoryOptimisticConflictError",
    "ScheduleStoreProtocol",
    "SourceRepositoryProtocol",
    "WorkspaceImportRepositoryProtocol",
]
