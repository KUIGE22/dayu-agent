"""durable job domain 与 JobService 单元/应用测试（Slice 2.1 B/C/D）。

覆盖：15 个公开 DTO 的精确字段/默认值/嵌套不变量、canonical document
敏感键拒绝、generic receipt golden bytes 与 strict parse、descriptor-only
registry、Service enqueue gate 早于 store、Host observation strict
mapping、correlation-safe recover 顺序与 stable 返回、terminal
reconciliation 四步（correlation -> Host reader -> mapping -> store）与
绝不调用 async Agent entry。
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from dayu.contracts.run import RunRecord, RunState
from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope
from dayu.investment.domain.jobs import (
    AgentRunCorrelation,
    AgentRunCorrelationObservation,
    AgentRunStartAuthorizationDecision,
    AgentRunTerminalReconciliationAction,
    AgentRunTerminalReconciliationDecision,
    AttemptReceiptOutcome,
    AttemptState,
    CanonicalJobDocument,
    CorrelationState,
    GENERIC_ATTEMPT_RECEIPT_SCHEMA_NAME,
    GENERIC_ATTEMPT_RECEIPT_SCHEMA_VERSION,
    GenericAttemptReceiptReason,
    HostRunObservationState,
    JobAttemptReceipt,
    JobCancellationRequest,
    JobClaim,
    JobCompletion,
    JobEnqueueReceipt,
    JobEnqueueRequest,
    JobFailure,
    JobHandlerDescriptor,
    JobInputError,
    JobLeaseHandle,
    JobRecoveryResult,
    JobState,
    SafeJobErrorCode,
    build_canonical_document,
    build_generic_attempt_receipt,
    parse_canonical_document,
    parse_generic_attempt_receipt,
)
from dayu.services.job_service import (
    DURABLE_JOBS_SERVICE_NAME,
    JobHandlerRegistry,
    JobService,
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

    def heartbeat(self, scope: TenantScope, lease: JobLeaseHandle) -> JobClaim:
        del scope, lease
        raise AssertionError("该测试不应调用 heartbeat")

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


def _make_service(
    *,
    store: _FakeJobStore | None = None,
    reader: _FakeHostReader | None = None,
    registry: JobHandlerRegistry | None = None,
) -> tuple[JobService, _FakeJobStore, _FakeHostReader]:
    """构造 JobService 测试三元组。

    Args:
        store: 可空 fake store。
        reader: 可空 fake reader。
        registry: 可空 registry。

    Returns:
        ``(service, store, reader)``。
    """

    fake_store = store if store is not None else _FakeJobStore()
    fake_reader = reader if reader is not None else _FakeHostReader()
    service = JobService(
        job_store=fake_store,
        descriptor_registry=registry if registry is not None else JobHandlerRegistry(),
        host_run_reader=fake_reader,
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
