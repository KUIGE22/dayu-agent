"""严格证据仓储的纯领域协议和固定安全错误。

本模块只规定 Slice 3.1 的十三个同步入口。认证入口自行验证 bearer，
租户范围仅作定位提示；协议不传递数据库连接、持久化行或外部资料句柄。
"""

from __future__ import annotations

from enum import Enum
from typing import ClassVar, Protocol, runtime_checkable
from uuid import UUID

from dayu.investment.domain.evidence import (
    ClaimConflict,
    ClaimConflictOpenRequest,
    ClaimConflictResolveRequest,
    ClaimCreateRequest,
    ClaimLocalEligibility,
    ClaimReviewRequest,
    ClaimRevisionBeginRequest,
    ClaimSnapshot,
    ClaimVersionAppendRequest,
    Fact,
    FactCreateRequest,
    ResearchCandidate,
    ResearchCandidateCreateRequest,
)
from dayu.investment.domain.identifiers import TenantScope


class EvidenceErrorCode(str, Enum):
    """供调用方分支处理的闭合、脱敏错误码。"""

    STORAGE_FAILURE = "evidence_storage_failure"
    INVALID_INPUT = "evidence_invalid_input"
    NOT_FOUND = "evidence_not_found"
    CONFLICT = "evidence_conflict"
    OPTIMISTIC_CONFLICT = "evidence_optimistic_conflict"
    DUPLICATE_TARGET = "evidence_duplicate_target"
    DIGEST_COLLISION = "evidence_digest_collision"
    REVIEW_REQUIRED_MATERIALIZATION_NEEDED = "review_required_materialization_needed"
    UNAUTHORIZED = "evidence_unauthorized"


class EvidenceRepositoryError(RuntimeError):
    """持久化或不变量失败的固定安全错误基类。"""

    code: ClassVar[EvidenceErrorCode] = EvidenceErrorCode.STORAGE_FAILURE

    def __init__(self) -> None:
        """只使用类绑定的安全码初始化异常。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(self.code.value)


class EvidenceInputError(EvidenceRepositoryError):
    """请求结构、范围或状态入口非法。"""

    code = EvidenceErrorCode.INVALID_INPUT


class EvidenceNotFoundError(EvidenceRepositoryError):
    """租户内目标缺失；跨租户目标也按缺失处理。"""

    code = EvidenceErrorCode.NOT_FOUND


class EvidenceConflictError(EvidenceRepositoryError):
    """业务键、operation 指纹或状态产生稳定冲突。"""

    code = EvidenceErrorCode.CONFLICT


class EvidenceOptimisticConflictError(EvidenceConflictError):
    """调用者版本与持久化 head 的 CAS 版本不符。"""

    code = EvidenceErrorCode.OPTIMISTIC_CONFLICT


class EvidenceDuplicateTargetError(EvidenceConflictError):
    """同一版本内关系与完整证据目标重复。"""

    code = EvidenceErrorCode.DUPLICATE_TARGET


class EvidenceDigestCollisionError(EvidenceConflictError):
    """同证券 digest 冲突但完整 locator JSONB 不相等。"""

    code = EvidenceErrorCode.DIGEST_COLLISION


class EvidenceMaterializationNeededError(EvidenceConflictError):
    """过期 approved head 须先经受控读取物化 review_required。"""

    code = EvidenceErrorCode.REVIEW_REQUIRED_MATERIALIZATION_NEEDED


class EvidenceUnauthorizedError(EvidenceRepositoryError):
    """令牌、租户提示或动作授权失败的统一脱敏错误。"""

    code = EvidenceErrorCode.UNAUTHORIZED


@runtime_checkable
class EvidenceRepositoryProtocol(Protocol):
    """租户闭合的 Fact、Claim、Conflict 与 Candidate 仓储接口。"""

    def create_fact(self, scope: TenantScope, request: FactCreateRequest) -> Fact:
        """追加一个不可变 Fact revision。

        Args:
            scope: 可信进程内租户范围。
            request: 含明确证券与 locator 的事实修订请求。

        Returns:
            已持久化的事实投影。

        Raises:
            EvidenceInputError: 请求或 revision 链非法。
            EvidenceConflictError: operation 或 revision 唯一键冲突。
            EvidenceRepositoryError: 持久化不变量失败。
        """

        ...

    def get_fact(self, scope: TenantScope, fact_id: UUID) -> Fact | None:
        """按租户读取不可变 Fact。

        Args:
            scope: 可信进程内租户范围。
            fact_id: Fact UUID。

        Returns:
            事实投影；缺失或跨租户时为空。

        Raises:
            EvidenceInputError: 标识或范围非法。
            EvidenceRepositoryError: 持久化投影不闭合。
        """

        ...

    def list_fact_revisions(self, scope: TenantScope, company_id: UUID,
                            fact_series_id: UUID) -> tuple[Fact, ...]:
        """按版号升序列出同一事实系列的不可变修订。

        Args:
            scope: 可信进程内租户范围。
            company_id: Fact 所属公司 UUID。
            fact_series_id: Fact series UUID。

        Returns:
            同租户修订序列；不存在时为空 tuple。

        Raises:
            EvidenceInputError: 标识或范围非法。
            EvidenceRepositoryError: 修订链或持久化投影不闭合。
        """

        ...

    def create_claim(self, scope: TenantScope, request: ClaimCreateRequest) -> ClaimSnapshot:
        """在一个事务创建 Claim shell、V1 draft 和完整链接集合。

        Args:
            scope: 可信进程内租户范围。
            request: V1 draft 与 replace_all 证据请求。

        Returns:
            最新 Claim 快照。

        Raises:
            EvidenceInputError: 请求或链接目标非法。
            EvidenceConflictError: ID、operation 或证据目标冲突。
            EvidenceRepositoryError: 事务内持久化失败。
        """

        ...

    def get_claim(self, scope: TenantScope, claim_id: UUID) -> ClaimSnapshot | None:
        """受控读取 current Claim，必要时物化已过期的 approved head。

        Args:
            scope: 可信进程内租户范围。
            claim_id: Claim UUID。

        Returns:
            当前完整版本与链接快照；缺失或跨租户时为空。

        Raises:
            EvidenceInputError: 标识或范围非法。
            EvidenceRepositoryError: head、链接或物化不变量失败。
        """

        ...

    def append_claim_version(
        self, scope: TenantScope, request: ClaimVersionAppendRequest
    ) -> ClaimSnapshot:
        """按允许的普通内容或提交审核状态边追加完整版本。

        Args:
            scope: 可信进程内租户范围。
            request: expected_version、内容与全量证据选择。

        Returns:
            CAS 成功后的当前 Claim 快照。

        Raises:
            EvidenceInputError: 状态边、内容或证据非法。
            EvidenceOptimisticConflictError: expected_version 已过期。
            EvidenceConflictError: operation 或证据目标冲突。
            EvidenceRepositoryError: 持久化不变量失败。
        """

        ...

    def begin_claim_revision(
        self, scope_hint: TenantScope, raw_token: bytes, request: ClaimRevisionBeginRequest
    ) -> ClaimSnapshot:
        """由有效 bearer 主体在同一 lineage 重开 draft。

        Args:
            scope_hint: 不可信租户定位提示，不代表 actor。
            raw_token: canonical bearer bytes，仅供事务内认证。
            request: 不含自由 author 或 reviewer 身份的重开请求。

        Returns:
            含 token-derived author witness 的新 Claim 快照。

        Raises:
            EvidenceUnauthorizedError: 令牌、主体或租户提示无效。
            EvidenceMaterializationNeededError: approved 已过期且须先物化。
            EvidenceOptimisticConflictError: expected_version 已过期。
            EvidenceInputError: 重开状态边或请求非法。
            EvidenceRepositoryError: 持久化不变量失败。
        """

        ...

    def record_claim_review(
        self, scope_hint: TenantScope, raw_token: bytes, request: ClaimReviewRequest
    ) -> ClaimSnapshot:
        """由同事务认证的显式 grant 审查人追加审查版本。

        Args:
            scope_hint: 不可信租户定位提示，不代表 reviewer。
            raw_token: canonical bearer bytes，仅供事务内认证。
            request: 不含自由 reviewer 身份或权限见证的审查请求。

        Returns:
            含 token/grant-derived reviewer witness 的新 Claim 快照。

        Raises:
            EvidenceUnauthorizedError: 令牌、主体或审查 grant 无效。
            EvidenceOptimisticConflictError: expected_version 已过期。
            EvidenceInputError: 审查状态边或请求非法。
            EvidenceRepositoryError: 持久化不变量失败。
        """

        ...

    def open_conflict(self, scope: TenantScope, request: ClaimConflictOpenRequest) -> ClaimConflict:
        """建立同租户公司两个 immutable version 间的冲突。

        Args:
            scope: 可信进程内租户范围。
            request: 已规范化端点和 material 标记。

        Returns:
            新 open conflict 投影。

        Raises:
            EvidenceInputError: 端点或范围非法。
            EvidenceConflictError: 无向端点 pair 或 operation 冲突。
            EvidenceRepositoryError: 持久化不变量失败。
        """

        ...

    def resolve_conflict_with_review(
        self, scope_hint: TenantScope, raw_token: bytes, request: ClaimConflictResolveRequest
    ) -> ClaimConflict:
        """以显式 reviewer grant 新增 successor 并原子解决冲突。

        Args:
            scope_hint: 不可信租户定位提示，不代表 reviewer。
            raw_token: canonical bearer bytes，仅供事务内认证。
            request: 双 expected_version、全量链接和新目标请求。

        Returns:
            带新版本及审查见证的 resolved conflict 投影。

        Raises:
            EvidenceUnauthorizedError: 令牌、主体或审查 grant 无效。
            EvidenceOptimisticConflictError: Claim 或 conflict CAS 已过期。
            EvidenceInputError: 状态边、目标增量或请求非法。
            EvidenceRepositoryError: 持久化不变量失败。
        """

        ...

    def local_claim_eligibility(self, scope: TenantScope, claim_id: UUID) -> ClaimLocalEligibility:
        """按 PG 时钟、冲突和 supports 给出严格局部资格原因。

        Args:
            scope: 可信进程内租户范围。
            claim_id: Claim UUID。

        Returns:
            局部筛选原因；就绪仍须外部资料 owner 验证。

        Raises:
            EvidenceInputError: 标识或范围非法。
            EvidenceNotFoundError: Claim 缺失或跨租户。
            EvidenceRepositoryError: current 或资格计算不变量失败。
        """

        ...

    def create_proposed_candidate(
        self, scope: TenantScope, request: ResearchCandidateCreateRequest
    ) -> ResearchCandidate:
        """仅创建 proposed 状态的租户私有研究候选。

        Args:
            scope: 可信进程内租户范围。
            request: 有界 canonical payload 与 origin 请求。

        Returns:
            proposed 候选投影。

        Raises:
            EvidenceInputError: payload、范围或请求非法。
            EvidenceConflictError: ID 或 operation 指纹冲突。
            EvidenceRepositoryError: 持久化不变量失败。
        """

        ...

    def get_candidate(self, scope: TenantScope, candidate_id: UUID) -> ResearchCandidate | None:
        """按租户读取候选 staging 投影。

        Args:
            scope: 可信进程内租户范围。
            candidate_id: Candidate UUID。

        Returns:
            候选投影；缺失或跨租户时为空。

        Raises:
            EvidenceInputError: 标识或范围非法。
            EvidenceRepositoryError: 持久化投影不闭合。
        """

        ...


__all__ = [
    "EvidenceConflictError",
    "EvidenceDigestCollisionError",
    "EvidenceDuplicateTargetError",
    "EvidenceErrorCode",
    "EvidenceInputError",
    "EvidenceMaterializationNeededError",
    "EvidenceNotFoundError",
    "EvidenceOptimisticConflictError",
    "EvidenceRepositoryError",
    "EvidenceRepositoryProtocol",
    "EvidenceUnauthorizedError",
]
