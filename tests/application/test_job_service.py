"""durable job domain 与 JobService 单元/应用测试（Slice 2.1/2.2）。

覆盖：15 个公开 DTO 的精确字段/默认值/嵌套不变量、canonical document
敏感键拒绝、generic receipt golden bytes 与 strict parse、descriptor-only
registry、Service enqueue gate 早于 store、Host observation strict
mapping、correlation-safe recover 顺序与 stable 返回、terminal
reconciliation 四步（correlation -> Host reader -> mapping -> store）、
execution registry/gateway、committed schedule enqueue、post-commit wakeup
以及 Host cancel/reobserve/targeted-recover governance 竞态。
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import re
from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from dayu.contracts.run import RunRecord, RunState
from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope
from dayu.investment.domain.jobs import (
    GENERIC_ATTEMPT_RECEIPT_SCHEMA_NAME,
    GENERIC_ATTEMPT_RECEIPT_SCHEMA_VERSION,
    AgentRunCorrelation,
    AgentRunCorrelationObservation,
    AgentRunGovernanceAction,
    AgentRunGovernanceCursor,
    AgentRunGovernancePage,
    AgentRunGovernanceProjection,
    AgentRunGovernanceProjectionPage,
    AgentRunGovernanceResult,
    AgentRunStartAuthorizationDecision,
    AgentRunTerminalReconciliationAction,
    AgentRunTerminalReconciliationDecision,
    AttemptReceiptOutcome,
    AttemptState,
    CanonicalJobDocument,
    CorrelationState,
    GenericAttemptReceiptReason,
    HostRunObservationState,
    JobAttemptReceipt,
    JobCancellationRequest,
    JobCancellationSignalProtocol,
    JobClaim,
    JobCompletion,
    JobEnqueueReceipt,
    JobEnqueueRequest,
    JobExecutionRequest,
    JobFailure,
    JobHandlerDescriptor,
    JobHeartbeatAction,
    JobHeartbeatResult,
    JobInputError,
    JobLeaseHandle,
    JobRecoveryResult,
    JobRepositoryFailureError,
    JobState,
    SafeJobErrorCode,
    build_canonical_document,
    build_generic_attempt_receipt,
    job_enqueue_request_fingerprint,
    parse_canonical_document,
    parse_generic_attempt_receipt,
)
from dayu.investment.domain.schedules import (
    CanonicalScheduleEnqueueSnapshot,
    ScheduleMaterializationAction,
    ScheduleMaterializationDecision,
    ScheduleOccurrence,
    ScheduleOccurrenceState,
)
from dayu.services.job_service import (
    DURABLE_JOBS_SERVICE_NAME,
    HostRunCancellationProtocol,
    JobExecutionHandlerProtocol,
    JobExecutionRegistry,
    JobHandlerRegistry,
    JobService,
    JobServiceRuntimeAdapters,
    JobWakeupPublisherProtocol,
    _build_validated_governance_page,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _tenant_scope(seed: int = 1) -> TenantScope:
    """构造测试租户范围。

    Args:
        seed: 租户 UUID 填充种子。

    Returns:
        ``TenantScope``。
    """

    return Principal(tenant_id=TenantId(f"00000000-0000-0000-0000-{seed:012x}"), user_id="u-1").to_scope()


def _descriptor(*, job_type: str = "test.job") -> JobHandlerDescriptor:
    """构造测试 descriptor。

    Args:
        job_type: job 类型。

    Returns:
        ``JobHandlerDescriptor``。
    """

    return JobHandlerDescriptor(
        job_type=job_type,
        payload_schema_name="test.payload",
        payload_schema_version=1,
        max_attempts=3,
        retry_base_seconds=1,
        retry_max_seconds=10,
        lease_duration_seconds=60,
    )


def _payload(*, text: str = "{}") -> CanonicalJobDocument:
    """构造 canonical payload document。

    Args:
        text: canonical JSON 文本。

    Returns:
        ``CanonicalJobDocument``。
    """

    return parse_canonical_document(
        text, schema_name="test.payload", schema_version=1
    )


def _enqueue_request(*, descriptor: JobHandlerDescriptor | None = None) -> JobEnqueueRequest:
    """构造入队请求。

    Args:
        descriptor: 可空 descriptor。

    Returns:
        ``JobEnqueueRequest``。
    """

    return JobEnqueueRequest(
        descriptor=descriptor if descriptor is not None else _descriptor(),
        idempotency_key="key-1",
        payload=_payload(),
        available_at=NOW,
        deadline_at=NOW + timedelta(hours=1),
    )


def _lease(seed: int = 1) -> JobLeaseHandle:
    """构造测试 lease。

    Args:
        seed: 随机填充种子。

    Returns:
        ``JobLeaseHandle``。
    """

    return JobLeaseHandle(
        tenant_id=_tenant_scope().tenant_id,
        job_id=uuid4(),
        attempt_id=uuid4(),
        fence=1,
        raw_token=f"{seed:064x}",
        acquired_at=NOW,
        expires_at=NOW + timedelta(minutes=1),
    )


class TestAllFifteenPublicJobDtos:
    """15 个公开 DTO 的字段/默认值/嵌套不变量。"""

    @pytest.mark.unit
    def test_all_fifteen_public_job_dtos_have_exact_fields_defaults_and_nesting(self) -> None:
        """15 个 DTO 的字段名、声明顺序、无默认值与 frozen slots 精确匹配契约。"""

        from dataclasses import MISSING

        expected_fields: dict[type, tuple[str, ...]] = {
            JobHandlerDescriptor: (
                "job_type",
                "payload_schema_name",
                "payload_schema_version",
                "max_attempts",
                "retry_base_seconds",
                "retry_max_seconds",
                "lease_duration_seconds",
            ),
            CanonicalJobDocument: ("schema_name", "schema_version", "canonical_bytes", "sha256"),
            JobEnqueueRequest: ("descriptor", "idempotency_key", "payload", "available_at", "deadline_at"),
            JobEnqueueReceipt: ("tenant_id", "definition_id", "job_id", "state", "idempotency_reused"),
            JobLeaseHandle: ("tenant_id", "job_id", "attempt_id", "fence", "raw_token", "acquired_at", "expires_at"),
            JobClaim: (
                "tenant_id",
                "definition_id",
                "job_id",
                "attempt_id",
                "attempt_number",
                "worker_id",
                "descriptor",
                "payload",
                "lease",
                "deadline_at",
            ),
            JobCompletion: ("result",),
            JobFailure: ("safe_error_code", "retryable"),
            JobCancellationRequest: ("job_id", "reason"),
            JobAttemptReceipt: (
                "tenant_id",
                "job_id",
                "attempt_id",
                "outcome",
                "result",
                "receipt",
                "safe_error_code",
                "finalized_at",
            ),
            JobRecoveryResult: (
                "job_id",
                "attempt_id",
                "job_state",
                "attempt_state",
                "receipt",
                "next_available_at",
                "safe_error_code",
            ),
            AgentRunCorrelation: (
                "id",
                "tenant_id",
                "job_id",
                "attempt_id",
                "idempotency_key",
                "reserved_host_run_id",
                "state",
                "observed_at",
                "last_observation_sha256",
                "created_at",
                "updated_at",
                "version",
            ),
            AgentRunCorrelationObservation: (
                "correlation_id",
                "host_run_id",
                "host_state",
                "host_completed_at",
                "sha256",
            ),
            AgentRunStartAuthorizationDecision: (
                "correlation",
                "attempt_id",
                "fence",
                "action",
                "safe_error_code",
            ),
            AgentRunTerminalReconciliationDecision: (
                "correlation",
                "observation",
                "attempt_id",
                "fence",
                "action",
                "receipt",
                "safe_error_code",
            ),
        }
        assert len(expected_fields) == 15
        for dto_type, names in expected_fields.items():
            assert is_dataclass(dto_type)
            assert "__slots__" in vars(dto_type)
            actual = tuple(field.name for field in fields(dto_type))
            assert actual == names, f"{dto_type} 字段顺序不匹配"
            for field in fields(dto_type):
                assert field.default is MISSING and field.default_factory is MISSING

    @pytest.mark.unit
    def test_enqueue_request_invariants(self) -> None:
        """deadline 必须晚于 available_at。"""

        with pytest.raises(JobInputError):
            JobEnqueueRequest(
                descriptor=_descriptor(),
                idempotency_key="k",
                payload=_payload(),
                available_at=NOW,
                deadline_at=NOW,
            )

    @pytest.mark.unit
    def test_lease_handle_invariants(self) -> None:
        """lease expiry 必须晚于 acquired。"""

        with pytest.raises(JobInputError):
            JobLeaseHandle(
                tenant_id=_tenant_scope().tenant_id,
                job_id=uuid4(),
                attempt_id=uuid4(),
                fence=1,
                raw_token="a" * 64,
                acquired_at=NOW,
                expires_at=NOW,
            )

    @pytest.mark.unit
    def test_correlation_reserved_id_invariant(self) -> None:
        """correlation 的 reserved ID 必须精确为 run_{attempt_id.hex}。"""

        attempt_id = uuid4()
        with pytest.raises(JobInputError):
            AgentRunCorrelation(
                id=uuid4(),
                tenant_id=_tenant_scope().tenant_id,
                job_id=uuid4(),
                attempt_id=attempt_id,
                idempotency_key="ik",
                reserved_host_run_id="run_" + "f" * 32,
                state=CorrelationState.RESERVED,
                observed_at=None,
                last_observation_sha256=None,
                created_at=NOW,
                updated_at=NOW,
                version=1,
            )


class TestCanonicalDocument:
    """canonical document 解析/编码/敏感键。"""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "key",
        ["password", "secret", "token", "authorization", "cookie", "api_key"],
    )
    def test_canonical_document_rejects_each_known_sensitive_key(self, key: str) -> None:
        """每个已知敏感键（含嵌套）都被拒绝。"""

        with pytest.raises(JobInputError):
            parse_canonical_document(
                json.dumps({"nested": {key: "value"}}, separators=(",", ":")),
                schema_name="s",
                schema_version=1,
            )

    @pytest.mark.unit
    def test_canonical_document_rejects_float_nan_infinity_duplicate_keys(self) -> None:
        """float/NaN/Infinity/重复 key 一律拒绝。"""

        for text in (
            '{"a":1.5}',
            '{"a":NaN}',
            '{"a":Infinity}',
            '{"a":1,"a":2}',
        ):
            with pytest.raises(JobInputError):
                parse_canonical_document(text, schema_name="s", schema_version=1)

    @pytest.mark.unit
    def test_canonical_document_rejects_non_canonical_bytes(self) -> None:
        """输入 bytes 与重新编码 bytes 不同（空白/非紧凑）时拒绝。"""

        with pytest.raises(JobInputError):
            parse_canonical_document(
                '{"a": 1}',
                schema_name="s",
                schema_version=1,
            )

    @pytest.mark.unit
    def test_canonical_document_encodes_sorted_compact(self) -> None:
        """编码结果：key 字典序、紧凑分隔符、无 BOM。"""

        document = build_canonical_document(
            {"b": 1, "a": "x"},
            schema_name="s",
            schema_version=1,
        )
        assert document.canonical_bytes == b'{"a":"x","b":1}'
        assert document.sha256 == hashlib.sha256(document.canonical_bytes).hexdigest()


class TestGenericAttemptReceipt:
    """generic receipt golden bytes / strict parse。"""

    def _result(self) -> CanonicalJobDocument:
        return build_canonical_document({"ok": True}, schema_name="r", schema_version=1)

    @pytest.mark.unit
    def test_generic_attempt_receipt_golden_bytes_for_every_non_host_outcome(self) -> None:
        """非 Host 的每个 outcome 组合产生确定的 canonical bytes/hash。"""

        job_id = uuid4()
        attempt_id = uuid4()
        result = self._result()
        combos = (
            (
                AttemptReceiptOutcome.SUCCEEDED,
                GenericAttemptReceiptReason.COMPLETION,
                None,
                result,
            ),
            (
                AttemptReceiptOutcome.FAILED,
                GenericAttemptReceiptReason.FAILURE,
                SafeJobErrorCode.HANDLER_REJECTED,
                None,
            ),
            (
                AttemptReceiptOutcome.CANCELLED,
                GenericAttemptReceiptReason.CANCEL_INTENT,
                SafeJobErrorCode.CANCELLED,
                None,
            ),
            (
                AttemptReceiptOutcome.FAILED,
                GenericAttemptReceiptReason.DEADLINE,
                SafeJobErrorCode.DEADLINE_EXCEEDED,
                None,
            ),
            (
                AttemptReceiptOutcome.FAILED,
                GenericAttemptReceiptReason.LEASE_EXPIRED,
                SafeJobErrorCode.LEASE_EXPIRED,
                None,
            ),
        )
        for outcome, reason, code, result_ref in combos:
            receipt = build_generic_attempt_receipt(
                job_id=job_id,
                attempt_id=attempt_id,
                outcome=outcome,
                reason=reason,
                safe_error_code=code,
                result_ref=result_ref,
            )
            assert receipt.schema_name == GENERIC_ATTEMPT_RECEIPT_SCHEMA_NAME
            assert receipt.schema_version == GENERIC_ATTEMPT_RECEIPT_SCHEMA_VERSION
            parsed = json.loads(receipt.canonical_bytes.decode("utf-8"))
            assert set(parsed) == {
                "attempt_id",
                "job_id",
                "outcome",
                "reason",
                "result",
                "safe_error_code",
                "schema_name",
                "schema_version",
            }
            assert list(parsed) == sorted(parsed)
            assert receipt.sha256 == hashlib.sha256(receipt.canonical_bytes).hexdigest()
            # 同输入必然同 bytes/hash（golden determinism）。
            again = build_generic_attempt_receipt(
                job_id=job_id,
                attempt_id=attempt_id,
                outcome=outcome,
                reason=reason,
                safe_error_code=code,
                result_ref=result_ref,
            )
            assert again.canonical_bytes == receipt.canonical_bytes
            assert again.sha256 == receipt.sha256

    @pytest.mark.unit
    def test_generic_attempt_receipt_strict_parse_rejects_wrong_key_set_or_combination(self) -> None:
        """strict parse 拒绝错误 key 集合与非法组合。"""

        job_id = uuid4()
        attempt_id = uuid4()
        result = self._result()
        valid = build_generic_attempt_receipt(
            job_id=job_id,
            attempt_id=attempt_id,
            outcome=AttemptReceiptOutcome.SUCCEEDED,
            reason=GenericAttemptReceiptReason.COMPLETION,
            safe_error_code=None,
            result_ref=result,
        )
        assert parse_generic_attempt_receipt(valid.canonical_bytes.decode("utf-8"))[
            "outcome"
        ] == "succeeded"
        # 错误 key 集合。
        tampered = json.loads(valid.canonical_bytes.decode("utf-8"))
        tampered["extra_key"] = 1
        with pytest.raises(JobInputError):
            parse_generic_attempt_receipt(
                json.dumps(tampered, sort_keys=True, separators=(",", ":"))
            )
        # 非法组合：completion 但 code 非空。
        invalid_combination = json.loads(valid.canonical_bytes.decode("utf-8"))
        invalid_combination["safe_error_code"] = "deadline_exceeded"
        with pytest.raises(JobInputError):
            parse_generic_attempt_receipt(
                json.dumps(invalid_combination, sort_keys=True, separators=(",", ":"))
            )
        # 非法组合：failure 无 code。
        failed_json = json.loads(valid.canonical_bytes.decode("utf-8"))
        failed_json["outcome"] = "failed"
        failed_json["reason"] = "failure"
        failed_json["result"] = None
        failed_json["safe_error_code"] = None
        with pytest.raises(JobInputError):
            parse_generic_attempt_receipt(
                json.dumps(failed_json, sort_keys=True, separators=(",", ":"))
            )

    @pytest.mark.unit
    def test_generic_attempt_receipt_schema_version_true_rejected_under_optimized_interpreter(
        self,
    ) -> None:
        """优化模式（``python -O``）下 receipt 顶层 ``schema_version`` 为 JSON ``true`` 仍必须拒绝。

        回归 F-001：旧实现以 ``assert type(schema_version) is int`` 做类型守卫，
        ``python -O`` 移除 assert 后 ``True == 1`` 使非法 schema version 被接受；
        修复后以显式 ``type(x) is int`` 校验，非法值统一 ``JobInputError``。
        候选文本保持 canonical 编码（字典序、紧凑分隔符）。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: 主进程或 ``-O`` 子进程未按契约拒绝时抛出。
        """

        import subprocess
        import sys
        from pathlib import Path

        job_id = uuid4()
        attempt_id = uuid4()
        valid = build_generic_attempt_receipt(
            job_id=job_id,
            attempt_id=attempt_id,
            outcome=AttemptReceiptOutcome.SUCCEEDED,
            reason=GenericAttemptReceiptReason.COMPLETION,
            safe_error_code=None,
            result_ref=self._result(),
        )
        tampered = json.loads(valid.canonical_bytes.decode("utf-8"))
        tampered["schema_version"] = True
        tampered_text = json.dumps(
            tampered, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        # 主进程直接拒绝（普通解释器）。
        with pytest.raises(JobInputError):
            parse_generic_attempt_receipt(tampered_text)
        # 优化模式子进程：只有 JobInputError 才 exit 0；被接受 exit 1；其它异常 exit 2。
        repo_root = str(Path(__file__).resolve().parents[2])
        script = (
            "import sys\n"
            "sys.path.insert(0, " + repr(repo_root) + ")\n"
            "from dayu.investment.domain.jobs import (\n"
            "    JobInputError,\n"
            "    parse_generic_attempt_receipt,\n"
            ")\n"
            "try:\n"
            "    parse_generic_attempt_receipt(" + repr(tampered_text) + ")\n"
            "except JobInputError:\n"
            "    sys.exit(0)\n"
            "except Exception:\n"
            "    sys.exit(2)\n"
            "sys.exit(1)\n"
        )
        completed = subprocess.run(
            [sys.executable, "-O", "-c", script],
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr


class TestJobHandlerRegistry:
    """descriptor-only registry 契约。"""

    @pytest.mark.unit
    def test_job_handler_registry_is_concrete_service_owner_and_empty_by_default(self) -> None:
        """唯一 concrete registry 默认空、无 invoke API、dict 不对外暴露。"""

        registry = JobHandlerRegistry()
        assert registry.get_descriptor("any") is None
        assert "invoke" not in dir(registry)
        assert "handle" not in dir(registry)
        assert "_descriptors" in registry.__dict__
        assert isinstance(registry._descriptors, dict)

    @pytest.mark.unit
    def test_register_descriptor_idempotent_and_conflicting_rejected(self) -> None:
        """同 job_type 完全一致幂等；任一字段不同抛 JobInputError。"""

        registry = JobHandlerRegistry()
        descriptor = _descriptor()
        registry.register_descriptor(descriptor)
        registry.register_descriptor(descriptor)
        assert registry.get_descriptor("test.job") == descriptor
        with pytest.raises(JobInputError):
            registry.register_descriptor(
                JobHandlerDescriptor(
                    job_type="test.job",
                    payload_schema_name="test.payload",
                    payload_schema_version=2,
                    max_attempts=3,
                    retry_base_seconds=1,
                    retry_max_seconds=10,
                    lease_duration_seconds=60,
                )
            )

    @pytest.mark.unit
    def test_schedule_registries_have_no_remove_or_replace_path(self) -> None:
        """两个 schedule execution registry 均为 append-only 且无替换入口。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        descriptors = JobHandlerRegistry()
        descriptor = _descriptor()
        descriptors.register_descriptor(descriptor)
        registry = JobExecutionRegistry(descriptors)
        handler = _CapturingExecutionHandler()
        registry.register_handler(descriptor, handler)
        registry.register_handler(descriptor, handler)
        assert registry.get_handler(descriptor) is handler
        assert "remove" not in dir(descriptors)
        assert "replace" not in dir(descriptors)
        assert "remove" not in dir(registry)
        assert "replace" not in dir(registry)
        with pytest.raises(JobInputError):
            registry.register_handler(descriptor, _CapturingExecutionHandler())
        with pytest.raises(JobInputError):
            registry.register_handler(
                _descriptor(job_type="other.job"),
                _CapturingExecutionHandler(job_type="other.job"),
            )
        with pytest.raises(JobInputError):
            registry.register_handler(
                descriptor,
                _CapturingExecutionHandler(job_type="wrong.job"),
            )


class _FakeJobStore:
    """可配置 database clock 的 fake JobStore（仅 Service 层测试）。"""

    def __init__(self) -> None:
        self.enqueue_calls: list[JobEnqueueRequest] = []
        self.correlations: dict[UUID, AgentRunCorrelation] = {}
        self.correlations_order: list[UUID] = []
        self.reconcile_decisions: dict[UUID, AgentRunTerminalReconciliationDecision] = {}
        self.targeted_results: dict[UUID, JobRecoveryResult | None] = {}
        self.targeted_calls: list[tuple[UUID, str]] = []
        self.generic_calls = 0
        self.generic_result: tuple[JobRecoveryResult, ...] = ()
        self.enqueue_result: JobEnqueueReceipt | None = None

    def enqueue(self, scope: TenantScope, request: JobEnqueueRequest) -> JobEnqueueReceipt:
        del scope
        self.enqueue_calls.append(request)
        if self.enqueue_result is not None:
            return self.enqueue_result
        return JobEnqueueReceipt(
            tenant_id=_tenant_scope().tenant_id,
            definition_id=uuid4(),
            job_id=uuid4(),
            state=JobState.READY,
            idempotency_reused=False,
        )

    def claim(self, scope: TenantScope, worker_id: str) -> JobClaim | None:
        del scope, worker_id
        raise AssertionError("该测试不应调用 claim")

    def heartbeat(self, scope: TenantScope, lease: JobLeaseHandle) -> JobHeartbeatResult:
        """拒绝未预期的 heartbeat 调用。

        Args:
            scope: 租户范围。
            lease: lease handle。

        Returns:
            本 fake 不返回。

        Raises:
            AssertionError: 测试意外调用 heartbeat 时抛出。
        """

        del scope, lease
        raise AssertionError("该测试不应调用 heartbeat")

    def list_governable_agent_runs(
        self,
        scope: TenantScope,
        cursor: AgentRunGovernanceCursor | None,
        *,
        limit: int,
    ) -> AgentRunGovernanceProjectionPage:
        """拒绝未预期的 governance page 查询。

        Args:
            scope: 租户范围。
            cursor: 可空 keyset cursor。
            limit: keyword-only page limit。

        Returns:
            本 fake 不返回。

        Raises:
            AssertionError: 测试意外查询 governance page 时抛出。
        """

        del scope, cursor, limit
        raise AssertionError("该测试不应调用 list_governable_agent_runs")

    def complete(self, scope: TenantScope, lease: JobLeaseHandle, completion: JobCompletion) -> JobAttemptReceipt:
        del scope, lease, completion
        raise AssertionError("该测试不应调用 complete")

    def fail(self, scope: TenantScope, lease: JobLeaseHandle, failure: JobFailure) -> JobRecoveryResult:
        del scope, lease, failure
        raise AssertionError("该测试不应调用 fail")

    def cancel(self, scope: TenantScope, request: JobCancellationRequest) -> JobRecoveryResult:
        del scope, request
        raise AssertionError("该测试不应调用 cancel")

    def recover(self, scope: TenantScope) -> tuple[JobRecoveryResult, ...]:
        del scope
        self.generic_calls += 1
        return self.generic_result

    def recover_agent_run_after_no_host(
        self,
        scope: TenantScope,
        correlation_id: UUID,
        observation_sha256: str,
    ) -> JobRecoveryResult | None:
        del scope
        self.targeted_calls.append((correlation_id, observation_sha256))
        return self.targeted_results.get(correlation_id)

    def reserve_agent_run_correlation(self, scope: TenantScope, lease: JobLeaseHandle) -> AgentRunCorrelation:
        del scope, lease
        raise AssertionError("该测试不应调用 reserve")

    def get_agent_run_correlation(self, scope: TenantScope, correlation_id: UUID) -> AgentRunCorrelation:
        del scope
        correlation = self.correlations.get(correlation_id)
        if correlation is None:
            raise KeyError("missing correlation")
        return correlation

    def list_expired_agent_run_correlations(self, scope: TenantScope) -> tuple[AgentRunCorrelation, ...]:
        del scope
        return tuple(self.correlations[correlation_id] for correlation_id in self.correlations_order)

    def authorize_agent_run_start(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        correlation_id: UUID,
    ) -> AgentRunStartAuthorizationDecision:
        del scope, lease, correlation_id
        raise AssertionError("该测试不应调用 authorize")

    def reconcile_agent_run_terminal(
        self,
        scope: TenantScope,
        correlation_id: UUID,
        observation: AgentRunCorrelationObservation,
    ) -> AgentRunTerminalReconciliationDecision:
        del scope
        base = self.reconcile_decisions[correlation_id]
        if base is None:
            raise KeyError("missing decision")
        # 以 Service mapping 出的 observation 重建决策（保持 action 与
        # observation 一致，sha256 由 Service 计算）。
        return AgentRunTerminalReconciliationDecision(
            correlation=base.correlation,
            observation=observation,
            attempt_id=base.attempt_id,
            fence=base.fence,
            action=base.action,
            receipt=base.receipt,
            safe_error_code=base.safe_error_code,
        )


class _CapturingObservationStore(_FakeJobStore):
    """记录 reconcile 收到的 observation 的 fake store（模块级）。"""

    def __init__(self) -> None:
        super().__init__()
        self.captured_observations: list[AgentRunCorrelationObservation] = []

    def reconcile_agent_run_terminal(
        self,
        scope: TenantScope,
        correlation_id: UUID,
        observation: AgentRunCorrelationObservation,
    ) -> AgentRunTerminalReconciliationDecision:
        del scope
        self.captured_observations.append(observation)
        return _no_host_decision(self.correlations[correlation_id])


class _CapturingCancelStore(_FakeJobStore):
    """记录 cancel 调用的窄 fake（不削弱 ``_FakeJobStore.cancel`` 的 trap）。"""

    def __init__(self) -> None:
        super().__init__()
        self.cancel_calls: list[tuple[TenantScope, JobCancellationRequest]] = []
        self.cancel_result: JobRecoveryResult | None = None

    def cancel(
        self,
        scope: TenantScope,
        request: JobCancellationRequest,
    ) -> JobRecoveryResult:
        self.cancel_calls.append((scope, request))
        if self.cancel_result is not None:
            return self.cancel_result
        raise AssertionError("该 fake 需要显式配置 cancel_result")


class _FakeHostReader:
    """fake Host run reader（可编程返回 RunRecord / None）。"""

    def __init__(self) -> None:
        self.records: dict[str, RunRecord] = {}
        self.read_calls: list[str] = []

    def get_run(self, run_id: str) -> RunRecord | None:
        self.read_calls.append(run_id)
        return self.records.get(run_id)


class _CancellationSignal:
    """测试用 pure cancellation signal。"""

    def __init__(self, *, requested: bool = False) -> None:
        """初始化取消标记。

        Args:
            requested: 初始取消标记。

        Returns:
            无。

        Raises:
            无。
        """

        self.requested = requested

    def is_cancel_requested(self) -> bool:
        """返回当前取消标记。

        Args:
            无。

        Returns:
            当前取消标记。

        Raises:
            无。
        """

        return self.requested

    async def wait_cancel_requested(self) -> None:
        """测试中立即返回。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        return None


class _CapturingExecutionHandler:
    """记录 execution request/cancellation 的 async handler。"""

    def __init__(
        self,
        *,
        job_type: str = "test.job",
        result: JobCompletion | JobFailure | None = None,
        raises: bool = False,
        cancelled: bool = False,
    ) -> None:
        """初始化可编程 handler。

        Args:
            job_type: handler job type。
            result: 可空闭合返回值。
            raises: 是否抛普通异常。
            cancelled: 是否抛 ``CancelledError``。

        Returns:
            无。

        Raises:
            无。
        """

        self._job_type = job_type
        self.result = result if result is not None else JobCompletion(result=_payload())
        self.raises = raises
        self.cancelled = cancelled
        self.calls: list[
            tuple[JobExecutionRequest, JobCancellationSignalProtocol]
        ] = []

    @property
    def job_type(self) -> str:
        """返回 handler job type。

        Args:
            无。

        Returns:
            配置的 job type。

        Raises:
            无。
        """

        return self._job_type

    async def execute(
        self,
        request: JobExecutionRequest,
        cancellation: JobCancellationSignalProtocol,
    ) -> JobCompletion | JobFailure:
        """记录调用并返回配置结果。

        Args:
            request: 收窄 execution request。
            cancellation: pure cancellation signal。

        Returns:
            配置的闭合结果。

        Raises:
            asyncio.CancelledError: ``cancelled=True`` 时抛出。
            RuntimeError: ``raises=True`` 时抛出。
        """

        self.calls.append((request, cancellation))
        if self.cancelled:
            raise asyncio.CancelledError
        if self.raises:
            raise RuntimeError("raw-handler-error")
        return self.result


class _MutableJobTypeExecutionHandler(_CapturingExecutionHandler):
    """可在注册后让 ``job_type`` property 失败的 handler。"""

    def __init__(self, *, raise_on_job_type: bool = False) -> None:
        """初始化动态 ``job_type`` 行为。

        Args:
            raise_on_job_type: 读取 property 时是否抛普通异常。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__()
        self.raise_on_job_type = raise_on_job_type

    @property
    def job_type(self) -> str:
        """返回稳定 job type 或模拟运行期 property failure。

        Args:
            无。

        Returns:
            ``test.job``。

        Raises:
            RuntimeError: ``raise_on_job_type`` 为 ``True`` 时抛出。
        """

        if self.raise_on_job_type:
            raise RuntimeError("raw-job-type-property-error")
        return "test.job"


class _FakeWakeupPublisher:
    """可配置成功/失败的 wakeup publisher。"""

    def __init__(
        self,
        *,
        error: Exception | None = None,
        result: bool = True,
    ) -> None:
        """初始化 publisher 行为。

        Args:
            error: 可空程序错误。
            result: 非异常时返回值。

        Returns:
            无。

        Raises:
            无。
        """

        self.error = error
        self.result = result
        self.calls: list[tuple[TenantScope, UUID]] = []

    def publish_hint(self, scope: TenantScope, job_id: UUID) -> bool:
        """记录 publish 调用。

        Args:
            scope: 租户范围。
            job_id: 已提交 job UUID。

        Returns:
            配置的布尔结果。

        Raises:
            Exception: 注入的程序错误原样抛出。
        """

        self.calls.append((scope, job_id))
        if self.error is not None:
            raise self.error
        return self.result


def _publish_non_bool(scope: TenantScope, job_id: UUID) -> int:
    """模拟第三方 publisher 违反窄协议返回整数。

    Args:
        scope: 租户范围。
        job_id: 已提交 job UUID。

    Returns:
        非 ``bool`` 的整数，用于验证 runtime contract gate。

    Raises:
        无。
    """

    del scope, job_id
    return 1


class _GovernanceJobStore(_FakeJobStore):
    """可编程 governance page/reconcile/recover 的 fake store。"""

    def __init__(self) -> None:
        """初始化空 governance page 与调用记录。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__()
        self.page = AgentRunGovernanceProjectionPage(
            projections=(),
            next_cursor=None,
        )
        self.list_calls: list[
            tuple[TenantScope, AgentRunGovernanceCursor | None, int]
        ] = []
        self.reconcile_calls: list[
            tuple[UUID, AgentRunCorrelationObservation]
        ] = []

    def list_governable_agent_runs(
        self,
        scope: TenantScope,
        cursor: AgentRunGovernanceCursor | None,
        *,
        limit: int,
    ) -> AgentRunGovernanceProjectionPage:
        """返回配置 page 并记录 keyword-only limit。

        Args:
            scope: 租户范围。
            cursor: 输入 cursor。
            limit: page limit。

        Returns:
            配置的 projection page。

        Raises:
            无。
        """

        self.list_calls.append((scope, cursor, limit))
        return self.page

    def reconcile_agent_run_terminal(
        self,
        scope: TenantScope,
        correlation_id: UUID,
        observation: AgentRunCorrelationObservation,
    ) -> AgentRunTerminalReconciliationDecision:
        """按 observation 重建配置 decision。

        Args:
            scope: 租户范围。
            correlation_id: correlation UUID。
            observation: Service observation。

        Returns:
            与当前 observation 闭合的配置 decision。

        Raises:
            KeyError: fake 未配置 decision 时抛出。
        """

        del scope
        self.reconcile_calls.append((correlation_id, observation))
        base = self.reconcile_decisions[correlation_id]
        return AgentRunTerminalReconciliationDecision(
            correlation=base.correlation,
            observation=observation,
            attempt_id=base.attempt_id,
            fence=base.fence,
            action=base.action,
            receipt=base.receipt,
            safe_error_code=base.safe_error_code,
        )


class _RepositoryFailureGovernanceStore(_GovernanceJobStore):
    """在 reconciliation 边界抛 closed repository failure 的 fake。"""

    def reconcile_agent_run_terminal(
        self,
        scope: TenantScope,
        correlation_id: UUID,
        observation: AgentRunCorrelationObservation,
    ) -> AgentRunTerminalReconciliationDecision:
        """模拟治理 reconciliation 的仓储基础设施失败。

        Args:
            scope: 租户范围。
            correlation_id: correlation UUID。
            observation: Service strict observation。

        Returns:
            永不返回。

        Raises:
            JobRepositoryFailureError: 每次固定抛出闭合仓储失败。
        """

        del scope, correlation_id, observation
        raise JobRepositoryFailureError()


class _ObserveThenTerminalStore(_GovernanceJobStore):
    """active 首次 reconcile、terminal 二次 reconcile 的竞态 fake。"""

    def __init__(self, receipt: JobAttemptReceipt) -> None:
        """初始化竞态 fake。

        Args:
            receipt: 二次 terminal reconciliation 返回的 receipt。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__()
        self.receipt = receipt

    def reconcile_agent_run_terminal(
        self,
        scope: TenantScope,
        correlation_id: UUID,
        observation: AgentRunCorrelationObservation,
    ) -> AgentRunTerminalReconciliationDecision:
        """按 observation active/terminal 返回对应 decision。

        Args:
            scope: 租户范围。
            correlation_id: correlation UUID。
            observation: Service strict observation。

        Returns:
            active wait 或 terminalized cancel decision。

        Raises:
            KeyError: fake 未配置 correlation 时抛出。
        """

        del scope
        self.reconcile_calls.append((correlation_id, observation))
        correlation = self.correlations[correlation_id]
        terminal = observation.host_state in (
            HostRunObservationState.SUCCEEDED,
            HostRunObservationState.FAILED,
            HostRunObservationState.CANCELLED,
            HostRunObservationState.UNSETTLED,
        )
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=correlation.attempt_id,
            fence=1,
            action=(
                AgentRunTerminalReconciliationAction.TERMINALIZED_CANCEL
                if terminal
                else AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT
            ),
            receipt=self.receipt if terminal else None,
            safe_error_code=None,
        )


class _CancelRaceGovernanceStore(_GovernanceJobStore):
    """按 reobserve 状态闭合 cancel ``KeyError`` 竞态的 fake store。"""

    def __init__(self, terminal_receipt: JobAttemptReceipt) -> None:
        """初始化竞态 store。

        Args:
            terminal_receipt: terminal reobserve 使用的 Host cancel receipt。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__()
        self._terminal_receipt = terminal_receipt

    def reconcile_agent_run_terminal(
        self,
        scope: TenantScope,
        correlation_id: UUID,
        observation: AgentRunCorrelationObservation,
    ) -> AgentRunTerminalReconciliationDecision:
        """按 active/terminal/missing observation 返回真实竞态决策。

        Args:
            scope: 租户范围。
            correlation_id: correlation UUID。
            observation: Service reobserve 结果。

        Returns:
            active wait、terminal cancel 或 invariant decision。

        Raises:
            KeyError: fake 未配置 correlation 时抛出。
        """

        del scope
        self.reconcile_calls.append((correlation_id, observation))
        correlation = self.correlations[correlation_id]
        if observation.host_state in (
            HostRunObservationState.SUCCEEDED,
            HostRunObservationState.FAILED,
            HostRunObservationState.CANCELLED,
            HostRunObservationState.UNSETTLED,
        ):
            action = AgentRunTerminalReconciliationAction.TERMINALIZED_CANCEL
            receipt = self._terminal_receipt
            safe_error_code = None
        elif observation.host_state is HostRunObservationState.MISSING:
            action = AgentRunTerminalReconciliationAction.INVARIANT_FAILURE
            receipt = None
            safe_error_code = SafeJobErrorCode.CORRELATION_INVARIANT
        else:
            action = AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT
            receipt = None
            safe_error_code = None
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=correlation.attempt_id,
            fence=1,
            action=action,
            receipt=receipt,
            safe_error_code=safe_error_code,
        )


class _TargetedRaceGovernanceStore(_GovernanceJobStore):
    """按 targeted-recover 失败后的 reobserve 状态返回决策。"""

    def reconcile_agent_run_terminal(
        self,
        scope: TenantScope,
        correlation_id: UUID,
        observation: AgentRunCorrelationObservation,
    ) -> AgentRunTerminalReconciliationDecision:
        """把 missing/active reobserve 映射为 NO_HOST/ACTIVE_WAIT。

        Args:
            scope: 租户范围。
            correlation_id: correlation UUID。
            observation: Service observation。

        Returns:
            与 observation 严格对应的 reconciliation decision。

        Raises:
            KeyError: fake 未配置 correlation 时抛出。
        """

        del scope
        self.reconcile_calls.append((correlation_id, observation))
        correlation = self.correlations[correlation_id]
        if observation.host_state is HostRunObservationState.MISSING:
            action = AgentRunTerminalReconciliationAction.NO_HOST_RUN
            safe_error_code = None
        elif observation.host_state in (
            HostRunObservationState.CREATED,
            HostRunObservationState.QUEUED,
            HostRunObservationState.RUNNING,
        ):
            action = AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT
            safe_error_code = None
        else:
            action = AgentRunTerminalReconciliationAction.INVARIANT_FAILURE
            safe_error_code = SafeJobErrorCode.CORRELATION_INVARIANT
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=correlation.attempt_id,
            fence=1,
            action=action,
            receipt=None,
            safe_error_code=safe_error_code,
        )


class _SequencedHost:
    """按序返回 Host records 并可配置 cancel 结果的 reader/canceller。"""

    def __init__(
        self,
        records: list[RunRecord | None],
        *,
        cancel_error: Exception | None = None,
    ) -> None:
        """初始化 Host observation 序列。

        Args:
            records: 至少一项的 observation 序列。
            cancel_error: 可空 cancel 异常。

        Returns:
            无。

        Raises:
            无。
        """

        self.records = list(records)
        self.cancel_error = cancel_error
        self.read_calls: list[str] = []
        self.cancel_calls: list[str] = []

    def get_run(self, run_id: str) -> RunRecord | None:
        """按序读取一个 Host record。

        Args:
            run_id: Host run ID。

        Returns:
            下一个配置 record；耗尽后重复最后一个。

        Raises:
            IndexError: records 为空时抛出。
        """

        self.read_calls.append(run_id)
        if len(self.records) > 1:
            return self.records.pop(0)
        return self.records[0]

    def cancel_run(self, run_id: str) -> RunRecord:
        """记录一次 Host cancel intent。

        Args:
            run_id: Host run ID。

        Returns:
            当前非空 record。

        Raises:
            Exception: 配置的 cancel 异常。
            KeyError: 当前 record 为空时抛出。
        """

        self.cancel_calls.append(run_id)
        if self.cancel_error is not None:
            raise self.cancel_error
        for record in self.records:
            if record is not None:
                return record
        raise KeyError(run_id)


def _make_service(
    *,
    store: _FakeJobStore | None = None,
    reader: _FakeHostReader | None = None,
    registry: JobHandlerRegistry | None = None,
    execution_registry: JobExecutionRegistry | None = None,
    canceller: HostRunCancellationProtocol | None = None,
    publisher: JobWakeupPublisherProtocol | None = None,
) -> tuple[JobService, _FakeJobStore, _FakeHostReader]:
    """构造 JobService 测试三元组。

    Args:
        store: 可空 fake store。
        reader: 可空 fake reader。
        registry: 可空 registry。
        execution_registry: 可空 execution registry。
        canceller: 可空 Host canceller。
        publisher: 可空 wakeup publisher。

    Returns:
        ``(service, store, reader)``。

    Raises:
        无。
    """

    fake_store = store if store is not None else _FakeJobStore()
    fake_reader = reader if reader is not None else _FakeHostReader()
    service = JobService(
        job_store=fake_store,
        descriptor_registry=registry if registry is not None else JobHandlerRegistry(),
        host_run_reader=fake_reader,
        execution_registry=execution_registry,
        runtime_adapters=JobServiceRuntimeAdapters(
            host_run_canceller=canceller,
            wakeup_publisher=publisher,
        ),
    )
    return service, fake_store, fake_reader


def _correlation(
    *,
    attempt_id: UUID | None = None,
    state: CorrelationState = CorrelationState.RESERVED,
) -> AgentRunCorrelation:
    """构造测试 correlation。

    Args:
        attempt_id: 可空 attempt UUID。
        state: correlation 状态。

    Returns:
        ``AgentRunCorrelation``。
    """

    attempt = attempt_id if attempt_id is not None else uuid4()
    return AgentRunCorrelation(
        id=uuid4(),
        tenant_id=_tenant_scope().tenant_id,
        job_id=uuid4(),
        attempt_id=attempt,
        idempotency_key="ik",
        reserved_host_run_id=f"run_{attempt.hex}",
        state=state,
        observed_at=None,
        last_observation_sha256=None,
        created_at=NOW,
        updated_at=NOW,
        version=1,
    )


def _no_host_decision(correlation: AgentRunCorrelation) -> AgentRunTerminalReconciliationDecision:
    """构造 NO_HOST_RUN 决策（observation sha256 为合成值）。

    Args:
        correlation: 目标 correlation。

    Returns:
        ``AgentRunTerminalReconciliationDecision``。
    """

    observation = AgentRunCorrelationObservation(
        correlation_id=correlation.id,
        host_run_id=correlation.reserved_host_run_id,
        host_state=HostRunObservationState.MISSING,
        host_completed_at=None,
        sha256="f" * 64,
    )
    return AgentRunTerminalReconciliationDecision(
        correlation=correlation,
        observation=observation,
        attempt_id=correlation.attempt_id,
        fence=1,
        action=AgentRunTerminalReconciliationAction.NO_HOST_RUN,
        receipt=None,
        safe_error_code=None,
    )


def _execution_claim() -> JobClaim:
    """构造 execution gateway 使用的闭合 claim。

    Args:
        无。

    Returns:
        合法 ``JobClaim``。

    Raises:
        无。
    """

    lease = _lease()
    return JobClaim(
        tenant_id=lease.tenant_id,
        definition_id=uuid4(),
        job_id=lease.job_id,
        attempt_id=lease.attempt_id,
        attempt_number=1,
        worker_id="worker-private",
        descriptor=_descriptor(),
        payload=_payload(),
        lease=lease,
        deadline_at=NOW + timedelta(hours=1),
    )


def _host_record(
    correlation: AgentRunCorrelation,
    *,
    state: RunState = RunState.RUNNING,
    cancel_requested: bool = False,
) -> RunRecord:
    """构造与 correlation reserved ID 闭合的 Host record。

    Args:
        correlation: 目标 correlation。
        state: Host run state。
        cancel_requested: 是否已有 Host cancel intent。

    Returns:
        合法 ``RunRecord``。

    Raises:
        无。
    """

    terminal = state in (
        RunState.SUCCEEDED,
        RunState.FAILED,
        RunState.CANCELLED,
        RunState.UNSETTLED,
    )
    return RunRecord(
        run_id=correlation.reserved_host_run_id,
        session_id=None,
        service_type="durable_job",
        scene_name=None,
        state=state,
        created_at=NOW,
        completed_at=NOW if terminal else None,
        cancel_requested_at=NOW if cancel_requested else None,
    )


def _governance_projection(
    correlation: AgentRunCorrelation,
    *,
    needs_cancel: bool = False,
    expired: bool = False,
    deadline: datetime | None = None,
) -> AgentRunGovernanceProjection:
    """构造 governance projection。

    Args:
        correlation: 目标 correlation。
        needs_cancel: 是否投射 PG cancel intent。
        expired: lease 是否已过期。
        deadline: 可空显式 deadline。

    Returns:
        合法 projection。

    Raises:
        无。
    """

    deadline_at = deadline if deadline is not None else NOW + timedelta(hours=1)
    return AgentRunGovernanceProjection(
        correlation=correlation,
        job_state=JobState.CANCEL_REQUESTED if needs_cancel else JobState.LEASED,
        attempt_state=AttemptState.LEASED,
        deadline_at=deadline_at,
        job_cancel_requested_at=NOW if needs_cancel else None,
        deadline_reached=NOW >= deadline_at,
        lease_expires_at=NOW if expired else NOW + timedelta(minutes=1),
        database_now=NOW,
    )


def _governance_result(
    correlation: AgentRunCorrelation,
    action: AgentRunGovernanceAction,
    safe_error_code: SafeJobErrorCode | None,
) -> AgentRunGovernanceResult:
    """按 correlation identity 构造测试 governance result。

    Args:
        correlation: identity 的来源 correlation。
        action: 闭合治理 action。
        safe_error_code: 与 action 匹配的安全错误码。

    Returns:
        携带 correlation/job/attempt UUID 的 governance result。

    Raises:
        JobInputError: identity 或 action/code 组合非法时抛出。
    """

    return AgentRunGovernanceResult(
        correlation_id=correlation.id,
        job_id=correlation.job_id,
        attempt_id=correlation.attempt_id,
        action=action,
        safe_error_code=safe_error_code,
    )


def _governance_decision(
    correlation: AgentRunCorrelation,
    action: AgentRunTerminalReconciliationAction,
    *,
    receipt: JobAttemptReceipt | None = None,
) -> AgentRunTerminalReconciliationDecision:
    """构造会由 fake store 替换 observation 的 governance decision。

    Args:
        correlation: 目标 correlation。
        action: store reconciliation action。
        receipt: 可空 terminal receipt。

    Returns:
        合法 decision 模板。

    Raises:
        无。
    """

    return AgentRunTerminalReconciliationDecision(
        correlation=correlation,
        observation=AgentRunCorrelationObservation(
            correlation_id=correlation.id,
            host_run_id=correlation.reserved_host_run_id,
            host_state=HostRunObservationState.MISSING,
            host_completed_at=None,
            sha256="a" * 64,
        ),
        attempt_id=correlation.attempt_id,
        fence=1,
        action=action,
        receipt=receipt,
        safe_error_code=None,
    )


def _materializing_decision() -> ScheduleMaterializationDecision:
    """构造 committed MATERIALIZING enqueue decision。

    Args:
        无。

    Returns:
        合法 schedule materialization decision。

    Raises:
        无。
    """

    request = _enqueue_request()
    snapshot = CanonicalScheduleEnqueueSnapshot(
        descriptor=request.descriptor,
        payload=request.payload,
        idempotency_key=request.idempotency_key,
        available_at=request.available_at,
        deadline_at=request.deadline_at,
        request_fingerprint=job_enqueue_request_fingerprint(request),
    )
    occurrence = ScheduleOccurrence(
        id=uuid4(),
        tenant_id=_tenant_scope().tenant_id,
        schedule_id=uuid4(),
        schedule_version=1,
        scheduled_for=NOW,
        state=ScheduleOccurrenceState.MATERIALIZING,
        snapshot=snapshot,
        job_id=None,
        coalesced_count=0,
        skip_reason=None,
        created_at=NOW,
        updated_at=NOW,
    )
    return ScheduleMaterializationDecision(
        action=ScheduleMaterializationAction.ENQUEUE,
        occurrence=occurrence,
    )


class TestSlice22ExecutionAndEnqueue:
    """Slice 2.2 execution gateway 与 enqueue side effects。"""

    @pytest.mark.unit
    def test_execution_availability_closes_mismatched_registry_injection(
        self,
    ) -> None:
        """Service 与 execution registry owner 不一致时不得正向证明。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        descriptor = _descriptor()
        execution_descriptors = JobHandlerRegistry()
        execution_descriptors.register_descriptor(descriptor)
        executions = JobExecutionRegistry(execution_descriptors)
        handler = _CapturingExecutionHandler()
        executions.register_handler(descriptor, handler)
        service_descriptors = JobHandlerRegistry()
        service, _, _ = _make_service(
            registry=service_descriptors,
            execution_registry=executions,
        )

        assert service.is_execution_available(descriptor) is False
        assert asyncio.run(
            service.execute_claim(
                _tenant_scope(),
                _execution_claim(),
                _CancellationSignal(),
            )
        ) == JobFailure(
            safe_error_code=SafeJobErrorCode.HANDLER_REJECTED,
            retryable=False,
        )
        assert handler.calls == []

    @pytest.mark.unit
    def test_execution_registry_closes_job_type_property_failure(
        self,
    ) -> None:
        """property 普通异常在注册/查询/执行边界分别安全收窄。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        descriptors = JobHandlerRegistry()
        descriptor = _descriptor()
        descriptors.register_descriptor(descriptor)
        registry = JobExecutionRegistry(descriptors)
        with pytest.raises(JobInputError):
            registry.register_handler(
                descriptor,
                _MutableJobTypeExecutionHandler(raise_on_job_type=True),
            )

        handler = _MutableJobTypeExecutionHandler()
        registry.register_handler(descriptor, handler)
        handler.raise_on_job_type = True
        service, _, _ = _make_service(
            registry=descriptors,
            execution_registry=registry,
        )

        assert registry.get_handler(descriptor) is None
        assert service.is_execution_available(descriptor) is False
        assert asyncio.run(
            service.execute_claim(
                _tenant_scope(),
                _execution_claim(),
                _CancellationSignal(),
            )
        ) == JobFailure(
            safe_error_code=SafeJobErrorCode.HANDLER_REJECTED,
            retryable=False,
        )
        assert handler.calls == []

    @pytest.mark.unit
    def test_worker_invokes_handler_only_through_job_service_execution_gateway(self) -> None:
        """gateway 解析双 registry 后恰一次调用 async handler。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        descriptors = JobHandlerRegistry()
        descriptor = _descriptor()
        descriptors.register_descriptor(descriptor)
        executions = JobExecutionRegistry(descriptors)
        completion = JobCompletion(result=_payload())
        handler = _CapturingExecutionHandler(result=completion)
        executions.register_handler(descriptor, handler)
        service, _, _ = _make_service(
            registry=descriptors,
            execution_registry=executions,
        )
        signal = _CancellationSignal()
        result = asyncio.run(
            service.execute_claim(_tenant_scope(), _execution_claim(), signal)
        )
        assert result is completion
        assert len(handler.calls) == 1
        assert service.is_execution_available(descriptor) is True
        assert isinstance(handler, JobExecutionHandlerProtocol)

    @pytest.mark.unit
    def test_execution_handler_never_receives_lease_fence_raw_token_or_worker_id(self) -> None:
        """handler request 精确八字段且不含 lease/fence/token/worker identity。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        descriptors = JobHandlerRegistry()
        descriptor = _descriptor()
        descriptors.register_descriptor(descriptor)
        executions = JobExecutionRegistry(descriptors)
        handler = _CapturingExecutionHandler()
        executions.register_handler(descriptor, handler)
        service, _, _ = _make_service(
            registry=descriptors,
            execution_registry=executions,
        )
        claim = _execution_claim()
        signal = _CancellationSignal()
        asyncio.run(service.execute_claim(_tenant_scope(), claim, signal))
        request, captured_signal = handler.calls[0]
        assert tuple(field.name for field in fields(request)) == (
            "tenant_id",
            "definition_id",
            "job_id",
            "attempt_id",
            "attempt_number",
            "descriptor",
            "payload",
            "deadline_at",
        )
        assert request.job_id == claim.job_id
        assert captured_signal is signal
        assert "lease" not in request.__slots__
        assert "fence" not in request.__slots__
        assert "raw_token" not in request.__slots__
        assert "worker_id" not in request.__slots__

    @pytest.mark.unit
    def test_unknown_handler_fails_once_without_host_model_or_business_side_effect(
        self,
    ) -> None:
        """unknown/异常/非法返回/取消后伪成功统一为 nonretryable rejection。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        descriptors = JobHandlerRegistry()
        descriptor = _descriptor()
        descriptors.register_descriptor(descriptor)
        empty_service, _, _ = _make_service(registry=descriptors)
        unknown = asyncio.run(
            empty_service.execute_claim(
                _tenant_scope(), _execution_claim(), _CancellationSignal()
            )
        )
        rejected = JobFailure(
            safe_error_code=SafeJobErrorCode.HANDLER_REJECTED,
            retryable=False,
        )
        assert unknown == rejected
        for handler, signal in (
            (_CapturingExecutionHandler(raises=True), _CancellationSignal()),
            (_CapturingExecutionHandler(), _CancellationSignal(requested=True)),
        ):
            executions = JobExecutionRegistry(descriptors)
            executions.register_handler(descriptor, handler)
            service, _, _ = _make_service(
                registry=descriptors,
                execution_registry=executions,
            )
            assert asyncio.run(
                service.execute_claim(_tenant_scope(), _execution_claim(), signal)
            ) == rejected
        invalid_handler = _CapturingExecutionHandler()
        setattr(invalid_handler, "result", "invalid-result")
        invalid_registry = JobExecutionRegistry(descriptors)
        invalid_registry.register_handler(descriptor, invalid_handler)
        invalid_service, _, _ = _make_service(
            registry=descriptors,
            execution_registry=invalid_registry,
        )
        assert asyncio.run(
            invalid_service.execute_claim(
                _tenant_scope(), _execution_claim(), _CancellationSignal()
            )
        ) == rejected

    @pytest.mark.unit
    def test_execute_claim_never_swallows_cancelled_error(self) -> None:
        """Worker drain 的 CancelledError 原样传播。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        descriptors = JobHandlerRegistry()
        descriptor = _descriptor()
        descriptors.register_descriptor(descriptor)
        executions = JobExecutionRegistry(descriptors)
        handler = _CapturingExecutionHandler(cancelled=True)
        executions.register_handler(descriptor, handler)
        service, _, _ = _make_service(
            registry=descriptors,
            execution_registry=executions,
        )
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(
                service.execute_claim(
                    _tenant_scope(), _execution_claim(), _CancellationSignal()
                )
            )

    @pytest.mark.unit
    def test_enqueue_commits_before_best_effort_publish_and_keeps_same_receipt(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """publisher 已收窄的 False 不得遮蔽已提交 receipt。

        Args:
            caplog: pytest 日志捕获器。

        Returns:
            无。

        Raises:
            无。
        """

        descriptors = JobHandlerRegistry()
        descriptors.register_descriptor(_descriptor())
        store = _FakeJobStore()
        receipt = JobEnqueueReceipt(
            tenant_id=_tenant_scope().tenant_id,
            definition_id=uuid4(),
            job_id=uuid4(),
            state=JobState.READY,
            idempotency_reused=False,
        )
        store.enqueue_result = receipt
        publisher = _FakeWakeupPublisher(result=False)
        service, _, _ = _make_service(
            store=store,
            registry=descriptors,
            publisher=publisher,
        )
        request = _enqueue_request()
        assert service.enqueue(_tenant_scope(), request) is receipt
        assert store.enqueue_calls == [request]
        assert publisher.calls == [(_tenant_scope(), receipt.job_id)]
        assert [
            record.getMessage()
            for record in caplog.records
            if record.name == "dayu.services.job_service"
        ] == ["platform_job_wakeup_publish_degraded"]

    @pytest.mark.unit
    @pytest.mark.parametrize("publisher_enabled", (False, True))
    def test_wakeup_safe_event_is_absent_for_true_publisher_or_no_publisher(
        self,
        caplog: pytest.LogCaptureFixture,
        publisher_enabled: bool,
    ) -> None:
        """publish True 与未注入 publisher 都不记降级事件。

        Args:
            caplog: pytest 日志捕获器。
            publisher_enabled: 是否注入返回 True 的 publisher。

        Returns:
            无。

        Raises:
            无。
        """

        descriptors = JobHandlerRegistry()
        descriptors.register_descriptor(_descriptor())
        store = _FakeJobStore()
        receipt = JobEnqueueReceipt(
            tenant_id=_tenant_scope().tenant_id,
            definition_id=uuid4(),
            job_id=uuid4(),
            state=JobState.READY,
            idempotency_reused=False,
        )
        store.enqueue_result = receipt
        publisher = _FakeWakeupPublisher() if publisher_enabled else None
        service, _, _ = _make_service(
            store=store,
            registry=descriptors,
            publisher=publisher,
        )

        assert service.enqueue(_tenant_scope(), _enqueue_request()) is receipt
        assert not any(
            record.getMessage() == "platform_job_wakeup_publish_degraded"
            for record in caplog.records
        )

    @pytest.mark.unit
    def test_materializing_replay_ignores_later_registry_drift_and_converges_to_one_job(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """committed replay 重建 snapshot，不调用 ordinary availability gate。

        Args:
            caplog: pytest 日志捕获器。

        Returns:
            无。

        Raises:
            无。
        """

        store = _FakeJobStore()
        receipt = JobEnqueueReceipt(
            tenant_id=_tenant_scope().tenant_id,
            definition_id=uuid4(),
            job_id=uuid4(),
            state=JobState.READY,
            idempotency_reused=True,
        )
        store.enqueue_result = receipt
        publisher = _FakeWakeupPublisher(result=False)
        service, _, _ = _make_service(store=store, publisher=publisher)
        decision = _materializing_decision()
        assert service.enqueue_committed_schedule_occurrence(
            _tenant_scope(), decision
        ) is receipt
        snapshot = decision.occurrence.snapshot
        assert snapshot is not None
        assert store.enqueue_calls == [
            JobEnqueueRequest(
                descriptor=snapshot.descriptor,
                idempotency_key=snapshot.idempotency_key,
                payload=snapshot.payload,
                available_at=snapshot.available_at,
                deadline_at=snapshot.deadline_at,
            )
        ]
        assert publisher.calls == [(_tenant_scope(), receipt.job_id)]
        assert [
            record.getMessage()
            for record in caplog.records
            if record.name == "dayu.services.job_service"
        ] == ["platform_job_wakeup_publish_degraded"]

    @pytest.mark.unit
    def test_post_commit_publish_failure_returns_same_enqueue_receipt(self) -> None:
        """adapter 收窄的 publish failure 不改变 PG receipt。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        descriptors = JobHandlerRegistry()
        descriptors.register_descriptor(_descriptor())
        store = _FakeJobStore()
        receipt = JobEnqueueReceipt(
            tenant_id=_tenant_scope().tenant_id,
            definition_id=uuid4(),
            job_id=uuid4(),
            state=JobState.READY,
            idempotency_reused=False,
        )
        store.enqueue_result = receipt
        service, _, _ = _make_service(
            store=store,
            registry=descriptors,
            publisher=_FakeWakeupPublisher(result=False),
        )
        assert service.enqueue(_tenant_scope(), _enqueue_request()) is receipt

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "program_error",
        (
            TypeError("publisher-type-error"),
            ValueError("publisher-value-error"),
            RuntimeError("publisher-runtime-error"),
        ),
    )
    def test_post_commit_publish_program_error_propagates_after_store_commit(
        self,
        program_error: Exception,
    ) -> None:
        """publisher 程序错误在 PG commit 后原样传播。

        Args:
            program_error: publisher 抛出的程序错误。

        Returns:
            无。

        Raises:
            无。
        """

        descriptors = JobHandlerRegistry()
        descriptors.register_descriptor(_descriptor())
        store = _FakeJobStore()
        receipt = JobEnqueueReceipt(
            tenant_id=_tenant_scope().tenant_id,
            definition_id=uuid4(),
            job_id=uuid4(),
            state=JobState.READY,
            idempotency_reused=False,
        )
        store.enqueue_result = receipt
        publisher = _FakeWakeupPublisher(error=program_error)
        service, _, _ = _make_service(
            store=store,
            registry=descriptors,
            publisher=publisher,
        )
        with pytest.raises(type(program_error), match=str(program_error)):
            service.enqueue(_tenant_scope(), _enqueue_request())

        assert len(store.enqueue_calls) == 1
        assert publisher.calls == [(_tenant_scope(), receipt.job_id)]

    @pytest.mark.unit
    def test_post_commit_publish_non_bool_return_is_contract_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """publisher 非 bool 返回在 PG commit 后按协议错误拒绝。

        Args:
            monkeypatch: 用于模拟第三方运行期违约的 pytest fixture。

        Returns:
            无。

        Raises:
            无。
        """

        descriptors = JobHandlerRegistry()
        descriptors.register_descriptor(_descriptor())
        store = _FakeJobStore()
        receipt = JobEnqueueReceipt(
            tenant_id=_tenant_scope().tenant_id,
            definition_id=uuid4(),
            job_id=uuid4(),
            state=JobState.READY,
            idempotency_reused=False,
        )
        store.enqueue_result = receipt
        publisher = _FakeWakeupPublisher()
        service, _, _ = _make_service(
            store=store,
            registry=descriptors,
            publisher=publisher,
        )
        monkeypatch.setattr(publisher, "publish_hint", _publish_non_bool)

        with pytest.raises(TypeError, match="publish_hint 必须返回 bool"):
            service.enqueue(_tenant_scope(), _enqueue_request())

        assert len(store.enqueue_calls) == 1

    @pytest.mark.unit
    def test_job_service_structurally_satisfies_worker_gateway_without_importing_host(
        self,
    ) -> None:
        """JobService 暴露精确 gateway 方法且 Service 不 import Host protocol。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        import dayu.services.job_service as service_module

        imports = TestContractOwnership._imported_module_names(
            open(service_module.__file__, encoding="utf-8").read()
        )
        assert not any(
            name == "dayu.host" or name.startswith("dayu.host.")
            for name in imports
        )
        assert asyncio.iscoroutinefunction(JobService.execute_claim)
        for method_name in (
            "recover",
            "claim",
            "execute_claim",
            "heartbeat",
            "complete",
            "fail",
            "govern_agent_runs",
        ):
            assert method_name in JobService.__dict__


class TestSlice22Governance:
    """Slice 2.2 Service governance closed state machine。"""

    @pytest.mark.unit
    def test_governance_result_identity_is_copied_from_each_projection_in_page_order(
        self,
    ) -> None:
        """每个 result 必须逐字段复制同位置 projection identity。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        first_correlation = _correlation()
        second_correlation = _correlation()
        first_projection = _governance_projection(
            first_correlation,
            deadline=NOW + timedelta(hours=1),
        )
        second_projection = _governance_projection(
            second_correlation,
            deadline=NOW + timedelta(hours=2),
        )
        store = _GovernanceJobStore()
        store.page = AgentRunGovernanceProjectionPage(
            projections=(first_projection, second_projection),
            next_cursor=None,
        )
        for correlation in (first_correlation, second_correlation):
            store.reconcile_decisions[correlation.id] = _governance_decision(
                correlation,
                AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT,
            )
        host = _SequencedHost(
            [_host_record(first_correlation), _host_record(second_correlation)]
        )
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )

        page = service.govern_agent_runs(_tenant_scope(), None, limit=2)

        assert tuple(
            (result.correlation_id, result.job_id, result.attempt_id)
            for result in page.results
        ) == tuple(
            (
                projection.correlation.id,
                projection.correlation.job_id,
                projection.correlation.attempt_id,
            )
            for projection in store.page.projections
        )
        assert tuple(result.action for result in page.results) == (
            AgentRunGovernanceAction.ACTIVE_WAIT,
            AgentRunGovernanceAction.ACTIVE_WAIT,
        )

    @pytest.mark.unit
    def test_governance_page_rejects_cardinality_identity_order_or_duplicate_mismatch(
        self,
    ) -> None:
        """Service page assembly 对数量、顺序、identity 与重复值 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        first_projection = _governance_projection(
            _correlation(),
            deadline=NOW + timedelta(hours=1),
        )
        second_projection = _governance_projection(
            _correlation(),
            deadline=NOW + timedelta(hours=2),
        )
        projections = (first_projection, second_projection)
        results = tuple(
            _governance_result(
                projection.correlation,
                AgentRunGovernanceAction.ACTIVE_WAIT,
                None,
            )
            for projection in projections
        )
        valid = _build_validated_governance_page(
            projections=projections,
            results=results,
            next_cursor=None,
        )
        assert valid.results == results
        with pytest.raises(JobInputError):
            _build_validated_governance_page(
                projections=projections,
                results=results[:1],
                next_cursor=None,
            )
        with pytest.raises(JobInputError):
            _build_validated_governance_page(
                projections=projections,
                results=(results[1], results[0]),
                next_cursor=None,
            )
        with pytest.raises(JobInputError):
            _build_validated_governance_page(
                projections=projections,
                results=(replace(results[0], job_id=uuid4()), results[1]),
                next_cursor=None,
            )
        duplicate_attempt_projection = _governance_projection(
            _correlation(attempt_id=first_projection.correlation.attempt_id),
            deadline=NOW + timedelta(hours=2),
        )
        duplicate_projections = (first_projection, duplicate_attempt_projection)
        duplicate_results = tuple(
            _governance_result(
                projection.correlation,
                AgentRunGovernanceAction.ACTIVE_WAIT,
                None,
            )
            for projection in duplicate_projections
        )
        with pytest.raises(JobInputError):
            _build_validated_governance_page(
                projections=duplicate_projections,
                results=duplicate_results,
                next_cursor=None,
            )
        store = _GovernanceJobStore()
        store.page = AgentRunGovernanceProjectionPage(
            projections=duplicate_projections,
            next_cursor=None,
        )
        host = _SequencedHost(
            [
                _host_record(first_projection.correlation),
                _host_record(duplicate_attempt_projection.correlation),
            ]
        )
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )
        with pytest.raises(JobInputError):
            service.govern_agent_runs(_tenant_scope(), None, limit=2)
        assert host.read_calls == []
        assert store.reconcile_calls == []

    @pytest.mark.unit
    def test_governance_repository_failure_propagates_without_false_result(self) -> None:
        """closed repository failure 必须交给 Worker 计数而非伪造 result。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        projection = _governance_projection(correlation)
        store = _RepositoryFailureGovernanceStore()
        store.page = AgentRunGovernanceProjectionPage(
            projections=(projection,),
            next_cursor=None,
        )
        host = _SequencedHost([_host_record(correlation)])
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )

        with pytest.raises(JobRepositoryFailureError):
            service.govern_agent_runs(_tenant_scope(), None, limit=1)

    @pytest.mark.unit
    def test_active_host_without_pg_trigger_waits_and_rotates_exact_cursor(self) -> None:
        """active projection 一一返回 ACTIVE_WAIT，并透传 cursor/limit。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        projection = _governance_projection(correlation)
        cursor = AgentRunGovernanceCursor(
            deadline_at=projection.deadline_at,
            correlation_id=correlation.id,
        )
        store = _GovernanceJobStore()
        store.page = AgentRunGovernanceProjectionPage(
            projections=(projection,), next_cursor=cursor
        )
        store.reconcile_decisions[correlation.id] = _governance_decision(
            correlation,
            AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT,
        )
        host = _SequencedHost([_host_record(correlation)])
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )
        page = service.govern_agent_runs(_tenant_scope(), None, limit=7)
        assert page.results == (
            _governance_result(
                correlation,
                AgentRunGovernanceAction.ACTIVE_WAIT,
                None,
            ),
        )
        assert page.next_cursor == cursor
        assert store.list_calls == [(_tenant_scope(), None, 7)]
        assert host.cancel_calls == []

    @pytest.mark.unit
    @pytest.mark.parametrize("expired", [False, True])
    def test_valid_lease_missing_host_stops_renewal_then_expiry_allows_targeted_recovery(
        self,
        expired: bool,
    ) -> None:
        """missing Host 在有效 lease 等待，expired 才 targeted recover。

        Args:
            expired: projection lease 是否已过期。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        projection = _governance_projection(correlation, expired=expired)
        store = _GovernanceJobStore()
        store.page = AgentRunGovernanceProjectionPage(
            projections=(projection,), next_cursor=None
        )
        store.reconcile_decisions[correlation.id] = _no_host_decision(correlation)
        store.targeted_results[correlation.id] = JobRecoveryResult(
            job_id=correlation.job_id,
            attempt_id=correlation.attempt_id,
            job_state=JobState.READY,
            attempt_state=AttemptState.ABANDONED,
            receipt=None,
            next_available_at=NOW + timedelta(minutes=1),
            safe_error_code=SafeJobErrorCode.LEASE_EXPIRED,
        )
        host = _SequencedHost([None])
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )
        result = service.govern_agent_runs(_tenant_scope(), None, limit=1).results[0]
        assert result.action is (
            AgentRunGovernanceAction.NO_HOST_RECOVERED
            if expired
            else AgentRunGovernanceAction.MISSING_HOST_WAIT
        )
        assert len(store.targeted_calls) == (1 if expired else 0)

    @pytest.mark.unit
    def test_valid_lease_missing_host_waits_without_targeted_or_generic_recovery(
        self,
    ) -> None:
        """有效 lease 的 missing Host 只等待，绝不进入任一 recovery。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        store = _GovernanceJobStore()
        store.page = AgentRunGovernanceProjectionPage(
            projections=(_governance_projection(correlation),),
            next_cursor=None,
        )
        store.reconcile_decisions[correlation.id] = _no_host_decision(correlation)
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=_SequencedHost([None]),
        )

        result = service.govern_agent_runs(_tenant_scope(), None, limit=1).results[0]
        assert result.action is AgentRunGovernanceAction.MISSING_HOST_WAIT
        assert store.targeted_calls == []
        assert store.generic_calls == 0

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("host_reappears", "expected_action"),
        [
            (True, AgentRunGovernanceAction.ACTIVE_WAIT),
            (False, AgentRunGovernanceAction.MISSING_HOST_WAIT),
        ],
    )
    def test_targeted_recovery_lost_race_reobserves_without_second_recovery(
        self,
        host_reappears: bool,
        expected_action: AgentRunGovernanceAction,
    ) -> None:
        """targeted 返回 None 后 reobserve active/missing 且不重复 recover。

        Args:
            host_reappears: 第二次 Host observation 是否恢复 active。
            expected_action: reobserve 后期望的 closed action。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        store = _TargetedRaceGovernanceStore()
        store.correlations[correlation.id] = correlation
        store.page = AgentRunGovernanceProjectionPage(
            projections=(_governance_projection(correlation, expired=True),),
            next_cursor=None,
        )
        store.targeted_results[correlation.id] = None
        reobserved_record = (
            _host_record(correlation) if host_reappears else None
        )
        host = _SequencedHost([None, reobserved_record])
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
        )

        result = service.govern_agent_runs(_tenant_scope(), None, limit=1).results[0]
        assert result.action is expected_action
        assert len(store.targeted_calls) == 1
        assert len(store.reconcile_calls) == 2
        assert store.generic_calls == 0

    @pytest.mark.unit
    @pytest.mark.parametrize("already_requested", [False, True])
    def test_governance_deadline_before_lease_expiry_requests_host_cancel_once(
        self,
        already_requested: bool,
    ) -> None:
        """PG trigger 下新 cancel 恰一次，既有 Host intent 只 reobserve。

        Args:
            already_requested: 初次 Host observation 是否已有 cancel intent。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        projection = _governance_projection(correlation, needs_cancel=True)
        store = _GovernanceJobStore()
        store.page = AgentRunGovernanceProjectionPage(
            projections=(projection,), next_cursor=None
        )
        store.reconcile_decisions[correlation.id] = _governance_decision(
            correlation,
            AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT,
        )
        host = _SequencedHost(
            [
                _host_record(correlation, cancel_requested=already_requested),
                _host_record(correlation, cancel_requested=True),
            ]
        )
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )
        result = service.govern_agent_runs(_tenant_scope(), None, limit=1).results[0]
        assert result.action is (
            AgentRunGovernanceAction.CANCEL_ALREADY_REQUESTED
            if already_requested
            else AgentRunGovernanceAction.CANCEL_REQUESTED
        )
        assert len(host.cancel_calls) == (0 if already_requested else 1)
        assert len(host.read_calls) == 2

    @pytest.mark.unit
    def test_deadline_sends_idempotent_host_cancel_and_never_claims_new_attempt(
        self,
    ) -> None:
        """重复治理同一 deadline 只写一次 Host intent 且零 recovery/claim。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        store = _GovernanceJobStore()
        store.page = AgentRunGovernanceProjectionPage(
            projections=(
                _governance_projection(correlation, deadline=NOW),
            ),
            next_cursor=None,
        )
        store.reconcile_decisions[correlation.id] = _governance_decision(
            correlation,
            AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT,
        )
        host = _SequencedHost(
            [
                _host_record(correlation),
                _host_record(correlation, cancel_requested=True),
            ]
        )
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )

        first = service.govern_agent_runs(_tenant_scope(), None, limit=1)
        second = service.govern_agent_runs(_tenant_scope(), None, limit=1)
        assert first.results[0].action is AgentRunGovernanceAction.CANCEL_REQUESTED
        assert second.results[0].action is (
            AgentRunGovernanceAction.CANCEL_ALREADY_REQUESTED
        )
        assert host.cancel_calls == [correlation.reserved_host_run_id]
        assert store.targeted_calls == []
        assert store.generic_calls == 0

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("second_state", "expected_action", "expected_code"),
        [
            (
                RunState.CANCELLED,
                AgentRunGovernanceAction.TERMINAL_RECONCILED,
                SafeJobErrorCode.HOST_RUN_CANCELLED,
            ),
            (
                RunState.RUNNING,
                AgentRunGovernanceAction.SEND_RETRY,
                None,
            ),
            (
                None,
                AgentRunGovernanceAction.INVARIANT_FAILURE,
                SafeJobErrorCode.CORRELATION_INVARIANT,
            ),
        ],
    )
    def test_cancel_key_error_reobserves_terminal_active_or_missing(
        self,
        second_state: RunState | None,
        expected_action: AgentRunGovernanceAction,
        expected_code: SafeJobErrorCode | None,
    ) -> None:
        """cancel ``KeyError`` 必须按 reobserve 真相闭合且零 recovery。

        Args:
            second_state: reobserve 的 Host 状态；``None`` 表示 missing。
            expected_action: 期望 governance action。
            expected_code: 期望 safe code。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        receipt = JobAttemptReceipt(
            tenant_id=correlation.tenant_id,
            job_id=correlation.job_id,
            attempt_id=correlation.attempt_id,
            outcome=AttemptReceiptOutcome.CANCELLED,
            result=None,
            receipt=_payload(),
            safe_error_code=SafeJobErrorCode.HOST_RUN_CANCELLED,
            finalized_at=NOW,
        )
        store = _CancelRaceGovernanceStore(receipt)
        store.correlations[correlation.id] = correlation
        store.page = AgentRunGovernanceProjectionPage(
            projections=(_governance_projection(correlation, needs_cancel=True),),
            next_cursor=None,
        )
        second_record = (
            _host_record(correlation, state=second_state)
            if second_state is not None
            else None
        )
        host = _SequencedHost(
            [_host_record(correlation), second_record],
            cancel_error=KeyError("cancel-race"),
        )
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )

        result = service.govern_agent_runs(_tenant_scope(), None, limit=1).results[0]
        assert result == _governance_result(
            correlation,
            expected_action,
            expected_code,
        )
        assert host.cancel_calls == [correlation.reserved_host_run_id]
        assert len(store.reconcile_calls) == 2
        assert store.targeted_calls == []
        assert store.generic_calls == 0

    @pytest.mark.unit
    @pytest.mark.parametrize("needs_cancel", [False, True])
    def test_active_or_cancel_pending_correlation_never_enters_generic_recovery(
        self,
        needs_cancel: bool,
    ) -> None:
        """active/cancel-pending correlation 只等待或投射 Host cancel。

        Args:
            needs_cancel: projection 是否携带 PG cancel intent。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        store = _GovernanceJobStore()
        store.page = AgentRunGovernanceProjectionPage(
            projections=(
                _governance_projection(correlation, needs_cancel=needs_cancel),
            ),
            next_cursor=None,
        )
        store.reconcile_decisions[correlation.id] = _governance_decision(
            correlation,
            AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT,
        )
        records: list[RunRecord | None] = [_host_record(correlation)]
        if needs_cancel:
            records.append(_host_record(correlation, cancel_requested=True))
        host = _SequencedHost(records)
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )

        result = service.govern_agent_runs(_tenant_scope(), None, limit=1).results[0]
        assert result.action is (
            AgentRunGovernanceAction.CANCEL_REQUESTED
            if needs_cancel
            else AgentRunGovernanceAction.ACTIVE_WAIT
        )
        assert store.targeted_calls == []
        assert store.generic_calls == 0

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("host_state", "decision_action", "expected_action", "expected_code"),
        [
            (
                RunState.FAILED,
                AgentRunTerminalReconciliationAction.TERMINALIZED_FAILURE,
                AgentRunGovernanceAction.TERMINAL_RECONCILED,
                SafeJobErrorCode.HOST_RUN_FAILED,
            ),
            (
                RunState.RUNNING,
                AgentRunTerminalReconciliationAction.STALE_ATTEMPT,
                AgentRunGovernanceAction.STALE,
                SafeJobErrorCode.CORRELATION_STALE_ATTEMPT,
            ),
        ],
    )
    def test_terminal_and_stale_decisions_map_to_closed_governance_results(
        self,
        host_state: RunState,
        decision_action: AgentRunTerminalReconciliationAction,
        expected_action: AgentRunGovernanceAction,
        expected_code: SafeJobErrorCode,
    ) -> None:
        """terminal/stale Store decisions 映射为精确 closed result。

        Args:
            host_state: Host observation 状态。
            decision_action: Store reconciliation action。
            expected_action: 期望 Service governance action。
            expected_code: 期望安全错误码。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        projection = _governance_projection(correlation)
        store = _GovernanceJobStore()
        store.page = AgentRunGovernanceProjectionPage(
            projections=(projection,), next_cursor=None
        )
        receipt = JobAttemptReceipt(
            tenant_id=correlation.tenant_id,
            job_id=correlation.job_id,
            attempt_id=correlation.attempt_id,
            outcome=AttemptReceiptOutcome.FAILED,
            result=None,
            receipt=_payload(),
            safe_error_code=SafeJobErrorCode.HOST_RUN_FAILED,
            finalized_at=NOW,
        ) if host_state is RunState.FAILED else None
        store.reconcile_decisions[correlation.id] = _governance_decision(
            correlation,
            decision_action,
            receipt=receipt,
        )
        host = _SequencedHost([_host_record(correlation, state=host_state)])
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )
        assert service.govern_agent_runs(
            _tenant_scope(), None, limit=1
        ).results[0] == _governance_result(
            correlation,
            expected_action,
            expected_code,
        )

    @pytest.mark.unit
    def test_active_host_deadline_comes_from_postgres_projection(self) -> None:
        """PG ``deadline_reached`` 是 active Host cancel 的唯一 deadline truth。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        projection = _governance_projection(correlation, deadline=NOW)
        store = _GovernanceJobStore()
        store.page = AgentRunGovernanceProjectionPage(
            projections=(projection,), next_cursor=None
        )
        store.reconcile_decisions[correlation.id] = _governance_decision(
            correlation,
            AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT,
        )
        host = _SequencedHost(
            [_host_record(correlation), _host_record(correlation, cancel_requested=True)]
        )
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )
        result = service.govern_agent_runs(_tenant_scope(), None, limit=1).results[0]
        assert result.action is AgentRunGovernanceAction.CANCEL_REQUESTED
        assert host.cancel_calls == [correlation.reserved_host_run_id]

    @pytest.mark.unit
    def test_cancel_send_failure_retries_without_mutating_pg_job(self) -> None:
        """Host cancel 异常返回 SEND_RETRY 且不 recover/创建新 attempt。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        projection = _governance_projection(correlation, needs_cancel=True)
        store = _GovernanceJobStore()
        store.page = AgentRunGovernanceProjectionPage(
            projections=(projection,), next_cursor=None
        )
        store.reconcile_decisions[correlation.id] = _governance_decision(
            correlation,
            AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT,
        )
        host = _SequencedHost(
            [_host_record(correlation)],
            cancel_error=RuntimeError("raw-host-error"),
        )
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )
        result = service.govern_agent_runs(_tenant_scope(), None, limit=1).results[0]
        assert result.action is AgentRunGovernanceAction.SEND_RETRY
        assert len(store.reconcile_calls) == 1
        assert store.targeted_calls == []
        assert store.generic_calls == 0

    @pytest.mark.unit
    def test_expired_lease_missing_host_alone_allows_targeted_recovery(self) -> None:
        """只有 expired+missing 才执行一次 targeted recovery。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        projection = _governance_projection(correlation, expired=True)
        store = _GovernanceJobStore()
        store.page = AgentRunGovernanceProjectionPage(
            projections=(projection,), next_cursor=None
        )
        store.reconcile_decisions[correlation.id] = _no_host_decision(correlation)
        store.targeted_results[correlation.id] = JobRecoveryResult(
            job_id=correlation.job_id,
            attempt_id=correlation.attempt_id,
            job_state=JobState.READY,
            attempt_state=AttemptState.ABANDONED,
            receipt=None,
            next_available_at=NOW + timedelta(minutes=1),
            safe_error_code=SafeJobErrorCode.LEASE_EXPIRED,
        )
        host = _SequencedHost([None])
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )
        result = service.govern_agent_runs(_tenant_scope(), None, limit=1).results[0]
        assert result.action is AgentRunGovernanceAction.NO_HOST_RECOVERED
        assert len(store.targeted_calls) == 1

    @pytest.mark.unit
    def test_host_terminal_between_observe_and_cancel_reconciles_without_new_attempt(
        self,
    ) -> None:
        """active 后 terminal 的 cancel race 只 reconcile，不 recover。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = _correlation()
        receipt = JobAttemptReceipt(
            tenant_id=correlation.tenant_id,
            job_id=correlation.job_id,
            attempt_id=correlation.attempt_id,
            outcome=AttemptReceiptOutcome.CANCELLED,
            result=None,
            receipt=_payload(),
            safe_error_code=SafeJobErrorCode.HOST_RUN_CANCELLED,
            finalized_at=NOW,
        )
        store = _ObserveThenTerminalStore(receipt)
        store.correlations[correlation.id] = correlation
        store.page = AgentRunGovernanceProjectionPage(
            projections=(_governance_projection(correlation, needs_cancel=True),),
            next_cursor=None,
        )
        host = _SequencedHost(
            [_host_record(correlation), _host_record(correlation, state=RunState.CANCELLED)]
        )
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=host,
            runtime_adapters=JobServiceRuntimeAdapters(host_run_canceller=host),
        )
        result = service.govern_agent_runs(_tenant_scope(), None, limit=1).results[0]
        assert result == _governance_result(
            correlation,
            AgentRunGovernanceAction.TERMINAL_RECONCILED,
            SafeJobErrorCode.HOST_RUN_CANCELLED,
        )
        assert store.targeted_calls == []
        assert store.generic_calls == 0


class TestJobService:
    """JobService 编排契约。"""

    @pytest.mark.unit
    def test_production_job_service_uses_empty_registry_and_rejects_business_enqueue(self) -> None:
        """生产装配的空 registry 拒绝任何业务 enqueue，且不调用 store。"""

        service, store, _ = _make_service()
        assert service.platform_service_name == DURABLE_JOBS_SERVICE_NAME
        with pytest.raises(JobInputError):
            service.enqueue(_tenant_scope(), _enqueue_request())
        assert store.enqueue_calls == []

    @pytest.mark.unit
    def test_job_service_enqueue_rejects_missing_or_mismatched_descriptor_before_store(self) -> None:
        """descriptor 缺失或任一字段不匹配在 store 之前抛错。"""

        registry = JobHandlerRegistry()
        registry.register_descriptor(_descriptor())
        service, store, _ = _make_service(registry=registry)
        service.enqueue(_tenant_scope(), _enqueue_request())
        assert len(store.enqueue_calls) == 1
        mismatched = JobEnqueueRequest(
            descriptor=JobHandlerDescriptor(
                job_type="test.job",
                payload_schema_name="test.payload",
                payload_schema_version=9,
                max_attempts=3,
                retry_base_seconds=1,
                retry_max_seconds=10,
                lease_duration_seconds=60,
            ),
            idempotency_key="key-2",
            payload=_payload(),
            available_at=NOW,
            deadline_at=NOW + timedelta(hours=1),
        )
        with pytest.raises(JobInputError):
            service.enqueue(_tenant_scope(), mismatched)
        assert len(store.enqueue_calls) == 1

    @pytest.mark.unit
    def test_job_service_cancel_delegates_scope_and_request_to_store(self) -> None:
        """``JobService.cancel`` 逐字委托 scope/request 给 store，且不触碰 Host reader。"""

        store = _CapturingCancelStore()
        reader = _FakeHostReader()
        scope = _tenant_scope(seed=7)
        request = JobCancellationRequest(job_id=uuid4(), reason="operator")
        store.cancel_result = JobRecoveryResult(
            job_id=request.job_id,
            attempt_id=None,
            job_state=JobState.CANCELLED,
            attempt_state=None,
            receipt=None,
            next_available_at=None,
            safe_error_code=SafeJobErrorCode.CANCELLED,
        )
        service, _, _ = _make_service(store=store, reader=reader)
        result = service.cancel(scope, request)
        assert result is store.cancel_result
        assert len(store.cancel_calls) == 1
        captured_scope, captured_request = store.cancel_calls[0]
        assert captured_scope is scope
        assert captured_request is request
        assert reader.read_calls == []

    @pytest.mark.unit
    def test_job_service_maps_host_run_or_missing_to_exact_observation(self) -> None:
        """JobService 单独把 missing/全部 Host RunState 映射为精确 observation。"""

        store = _FakeJobStore()
        correlation = _correlation()
        store.correlations[correlation.id] = correlation
        reader = _FakeHostReader()
        service, _, _ = _make_service(store=store, reader=reader)
        # missing
        capturing = _CapturingObservationStore()
        capturing.correlations[correlation.id] = correlation
        capturing.reconcile_decisions[correlation.id] = _no_host_decision(correlation)
        service2, _, _ = _make_service(store=capturing, reader=reader)
        service2.reconcile_agent_run_terminal(_tenant_scope(), correlation.id)
        assert capturing.captured_observations[0].host_state is HostRunObservationState.MISSING
        assert capturing.captured_observations[0].host_run_id == correlation.reserved_host_run_id
        assert capturing.captured_observations[0].host_completed_at is None

        # 全部 Host RunState 一一映射。
        state_map = {
            RunState.CREATED: HostRunObservationState.CREATED,
            RunState.QUEUED: HostRunObservationState.QUEUED,
            RunState.RUNNING: HostRunObservationState.RUNNING,
            RunState.SUCCEEDED: HostRunObservationState.SUCCEEDED,
            RunState.FAILED: HostRunObservationState.FAILED,
            RunState.CANCELLED: HostRunObservationState.CANCELLED,
            RunState.UNSETTLED: HostRunObservationState.UNSETTLED,
        }
        for run_state, expected in state_map.items():
            correlation2 = _correlation()
            capturing.correlations[correlation2.id] = correlation2
            reader.records[correlation2.reserved_host_run_id] = RunRecord(
                run_id=correlation2.reserved_host_run_id,
                session_id=None,
                service_type="durable_job",
                scene_name=None,
                state=run_state,
                created_at=NOW,
                completed_at=NOW if run_state in (
                    RunState.SUCCEEDED,
                    RunState.FAILED,
                    RunState.CANCELLED,
                    RunState.UNSETTLED,
                ) else None,
            )
            del capturing.captured_observations[:]
            capturing.reconcile_decisions[correlation2.id] = _no_host_decision(correlation2)
            service2.reconcile_agent_run_terminal(_tenant_scope(), correlation2.id)
            assert capturing.captured_observations[0].host_state is expected

    @pytest.mark.unit
    def test_direct_live_restart_reconciliation_always_reads_correlation_then_host_then_store(self) -> None:
        """每次 reconciliation 固定四步：correlation lookup -> Host reader -> store。"""

        store = _FakeJobStore()
        correlation = _correlation()
        store.correlations[correlation.id] = correlation
        decision = _no_host_decision(correlation)
        store.reconcile_decisions[correlation.id] = decision
        reader = _FakeHostReader()
        service, _, _ = _make_service(store=store, reader=reader)
        for _ in range(3):
            result = service.reconcile_agent_run_terminal(_tenant_scope(), correlation.id)
            assert result.action is AgentRunTerminalReconciliationAction.NO_HOST_RUN
        assert reader.read_calls == [correlation.reserved_host_run_id] * 3

    @pytest.mark.unit
    def test_terminal_reconciliation_never_calls_async_agent_entry(self) -> None:
        """reconcile 只调用 reader+store；JobService 不承载 async Agent entry。"""

        store = _FakeJobStore()
        reader = _FakeHostReader()
        correlation = _correlation()
        store.correlations[correlation.id] = correlation
        store.reconcile_decisions[correlation.id] = _no_host_decision(correlation)
        service, _, _ = _make_service(store=store, reader=reader)
        decision = service.reconcile_agent_run_terminal(
            _tenant_scope(), correlation.id
        )
        assert decision.action is AgentRunTerminalReconciliationAction.NO_HOST_RUN
        # 唯一被触碰的外沿是 reader.get_run 与 store.reconcile_agent_run_terminal；
        # 其余 store 方法均为 AssertionError trap，reconcile 路径不得进入。
        assert reader.read_calls == [correlation.reserved_host_run_id]
        # JobService 类命名空间不定义任何 async Agent entry 方法。
        assert "run_agent_stream" not in JobService.__dict__
        assert "run_agent_and_wait" not in JobService.__dict__

    @pytest.mark.unit
    def test_job_service_recover_returns_targeted_then_generic_results_in_stable_order(self) -> None:
        """recover 先按已排序 correlation 出 targeted 结果，最后恰一次 generic。"""

        store = _FakeJobStore()
        correlation_a = _correlation()
        correlation_b = _correlation()
        store.correlations[correlation_a.id] = correlation_a
        store.correlations[correlation_b.id] = correlation_b
        store.correlations_order = [correlation_a.id, correlation_b.id]
        decision_a = _no_host_decision(correlation_a)
        store.reconcile_decisions[correlation_a.id] = decision_a
        # correlation_b 是 HOST_ACTIVE_WAIT：不得进入 targeted。
        active_observation_b = AgentRunCorrelationObservation(
            correlation_id=correlation_b.id,
            host_run_id=correlation_b.reserved_host_run_id,
            host_state=HostRunObservationState.RUNNING,
            host_completed_at=None,
            sha256="c" * 64,
        )
        store.reconcile_decisions[correlation_b.id] = AgentRunTerminalReconciliationDecision(
            correlation=correlation_b,
            observation=active_observation_b,
            attempt_id=correlation_b.attempt_id,
            fence=1,
            action=AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT,
            receipt=None,
            safe_error_code=None,
        )
        targeted_result = JobRecoveryResult(
            job_id=correlation_a.job_id,
            attempt_id=correlation_a.attempt_id,
            job_state=JobState.READY,
            attempt_state=AttemptState.ABANDONED,
            receipt=None,
            next_available_at=None,
            safe_error_code=SafeJobErrorCode.LEASE_EXPIRED,
        )
        store.targeted_results[correlation_a.id] = targeted_result
        generic_result = JobRecoveryResult(
            job_id=uuid4(),
            attempt_id=uuid4(),
            job_state=JobState.FAILED,
            attempt_state=AttemptState.ABANDONED,
            receipt=None,
            next_available_at=None,
            safe_error_code=SafeJobErrorCode.RETRY_EXHAUSTED,
        )
        store.generic_result = (generic_result,)
        reader = _FakeHostReader()
        service, _, _ = _make_service(store=store, reader=reader)
        results = service.recover(_tenant_scope())
        assert results == (targeted_result, generic_result)
        assert store.generic_calls == 1
        expected_sha = _observation_from_record(
            correlation_a.id, correlation_a.reserved_host_run_id, None
        ).sha256
        assert store.targeted_calls == [(correlation_a.id, expected_sha)]

    @pytest.mark.unit
    def test_future_recovery_reconciles_existing_correlation_before_generic_recover(self) -> None:
        """expired correlation 先 reconciliation（含 active/no-host），generic 最后。"""

        store = _FakeJobStore()
        correlation = _correlation()
        store.correlations[correlation.id] = correlation
        store.correlations_order = [correlation.id]
        # HOST_ACTIVE_WAIT decision 不得进入 targeted/generic。
        active_observation = AgentRunCorrelationObservation(
            correlation_id=correlation.id,
            host_run_id=correlation.reserved_host_run_id,
            host_state=HostRunObservationState.RUNNING,
            host_completed_at=None,
            sha256="e" * 64,
        )
        store.reconcile_decisions[correlation.id] = AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=active_observation,
            attempt_id=correlation.attempt_id,
            fence=1,
            action=AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT,
            receipt=None,
            safe_error_code=None,
        )
        reader = _FakeHostReader()
        service, _, _ = _make_service(store=store, reader=reader)
        results = service.recover(_tenant_scope())
        assert results == ()
        assert store.targeted_calls == []
        assert store.generic_calls == 1

    @pytest.mark.unit
    def test_targeted_no_host_recovery_isolated_from_active_and_no_correlation_attempts(self) -> None:
        """仅 NO_HOST_RUN 进入 targeted；active/no-correlation 不进入任一 primitive。"""

        store = _FakeJobStore()
        no_host_corr = _correlation()
        active_corr = _correlation()
        store.correlations[no_host_corr.id] = no_host_corr
        store.correlations[active_corr.id] = active_corr
        store.correlations_order = [active_corr.id, no_host_corr.id]
        active_observation = AgentRunCorrelationObservation(
            correlation_id=active_corr.id,
            host_run_id=active_corr.reserved_host_run_id,
            host_state=HostRunObservationState.CREATED,
            host_completed_at=None,
            sha256="d" * 64,
        )
        store.reconcile_decisions[active_corr.id] = AgentRunTerminalReconciliationDecision(
            correlation=active_corr,
            observation=active_observation,
            attempt_id=active_corr.attempt_id,
            fence=1,
            action=AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT,
            receipt=None,
            safe_error_code=None,
        )
        no_host_decision = _no_host_decision(no_host_corr)
        store.reconcile_decisions[no_host_corr.id] = no_host_decision
        result = JobRecoveryResult(
            job_id=no_host_corr.job_id,
            attempt_id=no_host_corr.attempt_id,
            job_state=JobState.READY,
            attempt_state=AttemptState.ABANDONED,
            receipt=None,
            next_available_at=None,
            safe_error_code=SafeJobErrorCode.LEASE_EXPIRED,
        )
        store.targeted_results[no_host_corr.id] = result
        reader = _FakeHostReader()
        service, _, _ = _make_service(store=store, reader=reader)
        results = service.recover(_tenant_scope())
        assert results == (result,)
        expected_sha = _observation_from_record(
            no_host_corr.id, no_host_corr.reserved_host_run_id, None
        ).sha256
        assert store.targeted_calls == [(no_host_corr.id, expected_sha)]
        assert store.generic_calls == 1

    @pytest.mark.unit
    def test_missing_host_record_maps_to_missing_observation_with_correct_sha256(self) -> None:
        """Host record 不存在时 mapping 出 missing observation 且 fingerprint 稳定。"""

        correlation = _correlation()
        observation = _observation_from_record(correlation.id, correlation.reserved_host_run_id, None)
        assert observation.host_state is HostRunObservationState.MISSING
        assert observation.host_run_id == correlation.reserved_host_run_id
        assert observation.host_completed_at is None
        assert re.fullmatch(r"[0-9a-f]{64}", observation.sha256)
        again = _observation_from_record(correlation.id, correlation.reserved_host_run_id, None)
        assert again.sha256 == observation.sha256


def _observation_from_record(
    correlation_id: UUID,
    reserved_host_run_id: str,
    record: RunRecord | None,
) -> AgentRunCorrelationObservation:
    """复用 Service 私有 mapping 的只读便捷入口（测试专用）。

    Args:
        correlation_id: correlation UUID。
        reserved_host_run_id: reserved Host run ID。
        record: Host run 记录或 ``None``。

    Returns:
        ``AgentRunCorrelationObservation``。
    """

    from dayu.services.job_service import _map_run_record_to_observation

    return _map_run_record_to_observation(
        correlation_id=correlation_id,
        reserved_host_run_id=reserved_host_run_id,
        record=record,
    )


class TestContractOwnership:
    """唯一 owner / storage import guard。"""

    @staticmethod
    def _imported_module_names(source: str) -> set[str]:
        """提取源码中的顶层 import 模块名。

        Args:
            source: Python 源码文本。

        Returns:
            顶层 import/from 语句引用的模块名集合。
        """

        tree = ast.parse(source)
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                names.add(node.module)
        return names

    @pytest.mark.unit
    def test_job_domain_storage_protocol_and_service_registry_are_the_only_contract_owners(self) -> None:
        """domain/storage protocol/service registry 各自唯一 owner，无兼容 re-export。"""

        import dayu.investment.domain.jobs as jobs_module
        import dayu.investment.storage.protocols as storage_protocols_module
        import dayu.services.job_service as service_module

        jobs_imports = self._imported_module_names(
            open(jobs_module.__file__, encoding="utf-8").read()
        )
        assert not any(
            name == "dayu.host" or name.startswith("dayu.host.")
            or name == "dayu.contracts" or name.startswith("dayu.contracts.")
            for name in jobs_imports
        )
        storage_imports = self._imported_module_names(
            open(storage_protocols_module.__file__, encoding="utf-8").read()
        )
        assert not any(
            name == "dayu.host" or name.startswith("dayu.host.")
            or name == "dayu.contracts" or name.startswith("dayu.contracts.")
            for name in storage_imports
        )
        service_source = open(service_module.__file__, encoding="utf-8").read()
        assert "from dayu.investment.domain.jobs import" in service_source
        assert "from dayu.investment.storage.protocols import" in service_source
        # Host protocols 不承载 PG job DTO。
        host_protocols_source = open(
            "dayu/host/protocols.py", encoding="utf-8"
        ).read()
        assert "JobStoreProtocol" not in host_protocols_source
        assert "JobService" not in host_protocols_source

    @pytest.mark.unit
    def test_investment_storage_import_guard_still_rejects_host_and_contracts(self) -> None:
        """storage 实现源码不得 import dayu.host / dayu.contracts。"""

        import dayu.investment.storage.postgres_jobs as postgres_jobs_module

        imports = self._imported_module_names(
            open(postgres_jobs_module.__file__, encoding="utf-8").read()
        )
        assert not any(
            name == "dayu.host" or name.startswith("dayu.host.")
            or name == "dayu.contracts" or name.startswith("dayu.contracts.")
            for name in imports
        )


class TestJobGovernanceDtos:
    """Slice 2.2 heartbeat/governance 纯 DTO 的构造不变量测试。"""

    def _claim(self) -> JobClaim:
        """构造一个合法 ``JobClaim``。

        Args:
            无。

        Returns:
            合法的 ``JobClaim``。

        Raises:
            无。
        """

        lease = _lease()
        return JobClaim(
            tenant_id=lease.tenant_id,
            definition_id=uuid4(),
            job_id=lease.job_id,
            attempt_id=lease.attempt_id,
            attempt_number=1,
            worker_id="worker-a",
            descriptor=_descriptor(),
            payload=_payload(),
            lease=lease,
            deadline_at=NOW + timedelta(minutes=5),
        )

    def _projection(self) -> AgentRunGovernanceProjection:
        """构造一个合法 governance projection。

        Args:
            无。

        Returns:
            合法的 ``AgentRunGovernanceProjection``。

        Raises:
            无。
        """

        correlation = _correlation()
        return AgentRunGovernanceProjection(
            correlation=correlation,
            job_state=JobState.LEASED,
            attempt_state=AttemptState.LEASED,
            deadline_at=NOW + timedelta(hours=1),
            job_cancel_requested_at=None,
            deadline_reached=False,
            lease_expires_at=NOW + timedelta(minutes=1),
            database_now=NOW,
        )

    @pytest.mark.unit
    def test_job_heartbeat_result_rejects_string_action_and_non_claim(self) -> None:
        """action 必须是枚举、claim 必须是 ``JobClaim``。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        claim = self._claim()
        result = JobHeartbeatResult(action=JobHeartbeatAction.RENEWED, claim=claim)
        assert result.action is JobHeartbeatAction.RENEWED
        with pytest.raises(JobInputError):
            replace(result, action="renewed")
        with pytest.raises(JobInputError):
            replace(result, claim="claim")

    @pytest.mark.unit
    def test_governance_projection_rejects_wrong_types_and_derived_deadline_truth(self) -> None:
        """correlation 必须嵌套、deadline_reached 必须等于 PG 推导值。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        valid = self._projection()
        assert valid.deadline_reached is False
        with pytest.raises(JobInputError):
            replace(valid, deadline_reached=True)
        with pytest.raises(JobInputError):
            replace(valid, correlation="correlation")
        with pytest.raises(JobInputError):
            replace(
                valid,
                correlation=_correlation(state=CorrelationState.HOST_SUCCEEDED),
            )
        with pytest.raises(JobInputError):
            replace(valid, job_state="leased")
        with pytest.raises(JobInputError):
            replace(valid, deadline_at=datetime(2026, 1, 1))

    @pytest.mark.unit
    def test_governance_cursor_rejects_naive_time_and_non_uuid(self) -> None:
        """cursor 的 deadline 必须 aware UTC、correlation_id 必须 UUID。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        cursor = AgentRunGovernanceCursor(deadline_at=NOW, correlation_id=uuid4())
        assert cursor.correlation_id is not None
        with pytest.raises(JobInputError):
            replace(cursor, deadline_at=datetime(2026, 1, 1))
        with pytest.raises(JobInputError):
            replace(cursor, correlation_id="not-uuid")

    @pytest.mark.unit
    def test_governance_pages_reject_mutable_lists_and_wrong_cursor(self) -> None:
        """pages 必须 tuple（拒 list）且 cursor 必须合法或 None。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        projection = self._projection()
        valid_page = AgentRunGovernanceProjectionPage(
            projections=(projection,), next_cursor=None
        )
        assert valid_page.next_cursor is None
        with pytest.raises(JobInputError):
            replace(valid_page, projections=[projection])
        with pytest.raises(JobInputError):
            replace(valid_page, next_cursor="cursor")
        expected_cursor = AgentRunGovernanceCursor(
            deadline_at=projection.deadline_at,
            correlation_id=projection.correlation.id,
        )
        paged = AgentRunGovernanceProjectionPage(
            projections=(projection,),
            next_cursor=expected_cursor,
        )
        assert paged.next_cursor == expected_cursor
        with pytest.raises(JobInputError):
            replace(
                paged,
                next_cursor=AgentRunGovernanceCursor(
                    deadline_at=projection.deadline_at,
                    correlation_id=uuid4(),
                ),
            )
        with pytest.raises(JobInputError):
            AgentRunGovernanceProjectionPage(
                projections=(),
                next_cursor=expected_cursor,
            )
        earlier = replace(
            projection,
            correlation=_correlation(),
            deadline_at=projection.deadline_at - timedelta(minutes=1),
        )
        with pytest.raises(JobInputError):
            AgentRunGovernanceProjectionPage(
                projections=(projection, earlier),
                next_cursor=None,
            )
        with pytest.raises(JobInputError):
            AgentRunGovernanceProjectionPage(
                projections=(projection, projection),
                next_cursor=None,
            )
        result = _governance_result(
            projection.correlation,
            AgentRunGovernanceAction.ACTIVE_WAIT,
            None,
        )
        valid_result_page = AgentRunGovernancePage(
            results=(result,), next_cursor=None
        )
        assert valid_result_page.results == (result,)
        with pytest.raises(JobInputError):
            replace(valid_result_page, results=[result])
        with pytest.raises(JobInputError):
            AgentRunGovernancePage(results=(result, result), next_cursor=None)
        duplicate_attempt = _governance_result(
            _correlation(attempt_id=result.attempt_id),
            AgentRunGovernanceAction.ACTIVE_WAIT,
            None,
        )
        with pytest.raises(JobInputError):
            AgentRunGovernancePage(
                results=(result, duplicate_attempt),
                next_cursor=None,
            )

    @pytest.mark.unit
    def test_governance_result_rejects_string_action_and_wrong_code(self) -> None:
        """action 必须是枚举、safe_error_code 必须匹配 action。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        result = _governance_result(
            self._projection().correlation,
            AgentRunGovernanceAction.ACTIVE_WAIT,
            None,
        )
        assert tuple(field.name for field in fields(AgentRunGovernanceResult)) == (
            "correlation_id",
            "job_id",
            "attempt_id",
            "action",
            "safe_error_code",
        )
        with pytest.raises(JobInputError):
            replace(result, correlation_id="correlation")
        with pytest.raises(JobInputError):
            replace(result, job_id="job")
        with pytest.raises(JobInputError):
            replace(result, attempt_id="attempt")
        with pytest.raises(JobInputError):
            replace(result, action="ACTIVE_WAIT")
        with pytest.raises(JobInputError):
            replace(result, safe_error_code="code")
        with pytest.raises(JobInputError):
            replace(result, safe_error_code=SafeJobErrorCode.CANCELLED)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("action", "safe_error_code"),
        [
            (AgentRunGovernanceAction.ACTIVE_WAIT, None),
            (AgentRunGovernanceAction.MISSING_HOST_WAIT, None),
            (AgentRunGovernanceAction.CANCEL_REQUESTED, None),
            (AgentRunGovernanceAction.CANCEL_ALREADY_REQUESTED, None),
            (AgentRunGovernanceAction.SEND_RETRY, None),
            (
                AgentRunGovernanceAction.STALE,
                SafeJobErrorCode.CORRELATION_STALE_ATTEMPT,
            ),
            (
                AgentRunGovernanceAction.INVARIANT_FAILURE,
                SafeJobErrorCode.CORRELATION_INVARIANT,
            ),
            (AgentRunGovernanceAction.TERMINAL_RECONCILED, None),
            (
                AgentRunGovernanceAction.TERMINAL_RECONCILED,
                SafeJobErrorCode.HOST_RUN_FAILED,
            ),
            (
                AgentRunGovernanceAction.NO_HOST_RECOVERED,
                SafeJobErrorCode.CANCELLED,
            ),
            (
                AgentRunGovernanceAction.NO_HOST_RECOVERED,
                SafeJobErrorCode.DEADLINE_EXCEEDED,
            ),
            (
                AgentRunGovernanceAction.NO_HOST_RECOVERED,
                SafeJobErrorCode.LEASE_EXPIRED,
            ),
            (
                AgentRunGovernanceAction.NO_HOST_RECOVERED,
                SafeJobErrorCode.RETRY_EXHAUSTED,
            ),
        ],
    )
    def test_governance_result_accepts_exact_action_code_matrix(
        self,
        action: AgentRunGovernanceAction,
        safe_error_code: SafeJobErrorCode | None,
    ) -> None:
        """每个治理 action 只接受闭合矩阵允许的 safe code。

        Args:
            action: 待验证治理 action。
            safe_error_code: 待验证安全错误码。

        Returns:
            无。

        Raises:
            无。
        """

        correlation = self._projection().correlation
        result = _governance_result(
            correlation,
            action,
            safe_error_code,
        )

        assert result.action is action
        assert result.safe_error_code is safe_error_code

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("action", "safe_error_code"),
        [
            (AgentRunGovernanceAction.STALE, None),
            (AgentRunGovernanceAction.STALE, SafeJobErrorCode.CANCELLED),
            (AgentRunGovernanceAction.INVARIANT_FAILURE, None),
            (
                AgentRunGovernanceAction.INVARIANT_FAILURE,
                SafeJobErrorCode.REPOSITORY_FAILURE,
            ),
        ],
    )
    def test_governance_result_rejects_action_code_matrix_drift(
        self,
        action: AgentRunGovernanceAction,
        safe_error_code: SafeJobErrorCode | None,
    ) -> None:
        """固定 stale/invariant action 的唯一安全错误码。

        Args:
            action: 待验证治理 action。
            safe_error_code: 不匹配的安全错误码。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(JobInputError):
            AgentRunGovernanceResult(
                correlation_id=uuid4(),
                job_id=uuid4(),
                attempt_id=uuid4(),
                action=action,
                safe_error_code=safe_error_code,
            )

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "safe_error_code",
        tuple(
            code
            for code in SafeJobErrorCode
            if code
            not in (
                SafeJobErrorCode.HOST_RUN_FAILED,
                SafeJobErrorCode.HOST_RUN_CANCELLED,
                SafeJobErrorCode.HOST_RUN_UNSETTLED,
            )
        ),
    )
    def test_terminal_reconciled_rejects_every_forbidden_safe_code(
        self,
        safe_error_code: SafeJobErrorCode,
    ) -> None:
        """terminal reconciliation 只接受 Host terminal 的安全错误码。

        Args:
            safe_error_code: 不允许的安全错误码。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(JobInputError):
            AgentRunGovernanceResult(
                correlation_id=uuid4(),
                job_id=uuid4(),
                attempt_id=uuid4(),
                action=AgentRunGovernanceAction.TERMINAL_RECONCILED,
                safe_error_code=safe_error_code,
            )

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "safe_error_code",
        (None,)
        + tuple(
            code
            for code in SafeJobErrorCode
            if code
            not in (
                SafeJobErrorCode.CANCELLED,
                SafeJobErrorCode.DEADLINE_EXCEEDED,
                SafeJobErrorCode.LEASE_EXPIRED,
                SafeJobErrorCode.RETRY_EXHAUSTED,
            )
        ),
    )
    def test_no_host_recovered_rejects_every_forbidden_safe_code(
        self,
        safe_error_code: SafeJobErrorCode | None,
    ) -> None:
        """no-host recovery 必须携带 recover 状态机产生的安全错误码。

        Args:
            safe_error_code: 不允许的安全错误码或空值。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(JobInputError):
            AgentRunGovernanceResult(
                correlation_id=uuid4(),
                job_id=uuid4(),
                attempt_id=uuid4(),
                action=AgentRunGovernanceAction.NO_HOST_RECOVERED,
                safe_error_code=safe_error_code,
            )

    @pytest.mark.unit
    def test_job_execution_request_never_carries_lease_fence_token_or_worker_id(self) -> None:
        """execution request 只含收窄字段，不含 lease/fence/token/worker_id。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        from dataclasses import fields

        field_names = tuple(field.name for field in fields(JobExecutionRequest))
        assert field_names == (
            "tenant_id",
            "definition_id",
            "job_id",
            "attempt_id",
            "attempt_number",
            "descriptor",
            "payload",
            "deadline_at",
        )
        request = JobExecutionRequest(
            tenant_id=_tenant_scope().tenant_id,
            definition_id=uuid4(),
            job_id=uuid4(),
            attempt_id=uuid4(),
            attempt_number=1,
            descriptor=_descriptor(),
            payload=_payload(),
            deadline_at=NOW + timedelta(minutes=5),
        )
        assert request.attempt_number == 1
        for field_name in ("definition_id", "job_id", "attempt_id"):
            with pytest.raises(JobInputError):
                replace(request, **{field_name: "not-uuid"})
        with pytest.raises(JobInputError):
            replace(request, descriptor="descriptor")
        with pytest.raises(JobInputError):
            replace(request, payload="payload")
        with pytest.raises(JobInputError):
            JobExecutionRequest(
                tenant_id=_tenant_scope().tenant_id,
                definition_id=uuid4(),
                job_id=uuid4(),
                attempt_id=uuid4(),
                attempt_number=0,
                descriptor=_descriptor(),
                payload=_payload(),
                deadline_at=NOW + timedelta(minutes=5),
            )

    @pytest.mark.unit
    def test_job_enqueue_request_fingerprint_is_deterministic_and_covers_all_fields(self) -> None:
        """fingerprint 唯一真源：确定性且覆盖 descriptor/payload/时间全部字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        request = _enqueue_request()
        first = job_enqueue_request_fingerprint(request)
        second = job_enqueue_request_fingerprint(request)
        assert first == second
        assert len(first) == 64
        changed_deadline = JobEnqueueRequest(
            descriptor=request.descriptor,
            idempotency_key=request.idempotency_key,
            payload=request.payload,
            available_at=request.available_at,
            deadline_at=request.deadline_at + timedelta(minutes=1),
        )
        assert job_enqueue_request_fingerprint(changed_deadline) != first
        changed_payload = _enqueue_request()
        assert job_enqueue_request_fingerprint(changed_payload) == first
