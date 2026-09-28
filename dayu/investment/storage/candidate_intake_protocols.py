"""candidate+immutable receipt 单事务的窄存储协议，不暴露 SQL/Fins owner。"""

from typing import Protocol, runtime_checkable
from uuid import UUID

from dayu.investment.domain.candidate_intake import CandidateIntakeReceipt, CandidateIntakeRecordRequest
from dayu.investment.domain.identifiers import TenantScope


@runtime_checkable
class CandidateIntakeRepositoryProtocol(Protocol):
    """首提交拥有结果、tenant operation 幂等的持久化边界。"""

    def find_intake_receipt(
        self, scope: TenantScope, operation_id: UUID, request_fingerprint: str,
    ) -> CandidateIntakeReceipt | None:
        """读取历史结果；异请求为 conflict，损坏历史为 storage failure。

        Args:
            scope: 可信租户。
            operation_id: 本次 operation，不按 candidate ID 跨请求复用。
            request_fingerprint: 完整请求指纹。
        Returns:
            原不可变 receipt 或无记录。
        Raises:
            EvidenceInputError: 输入非法。
            EvidenceConflictError: operation 绑定异请求。
            EvidenceRepositoryError: SQL 或历史闭合失败。
        """
        ...

    def record_intake(
        self, scope: TenantScope, request: CandidateIntakeRecordRequest,
    ) -> CandidateIntakeReceipt:
        """原子写一次 candidate 与 receipt，并耐久恢复首结果。

        Args:
            scope: 可信租户。
            request: 严格成功或拒绝请求。
        Returns:
            版本1第一次提交结果。
        Raises:
            EvidenceInputError: 输入非法。
            EvidenceConflictError: 业务身份或请求冲突。
            EvidenceRepositoryError: 事务或历史闭合失败。
        """
        ...
