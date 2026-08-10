"""FinsService evidence locator 真实 delegate 测试。"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator, Callable, TypeVar

import pytest

from dayu.contracts.agent_execution import ExecutionContract, ReplayHandle
from dayu.contracts.events import AppEvent, AppResult
from dayu.contracts.execution_metadata import ExecutionDeliveryContext
from dayu.contracts.host_execution import HostedRunContext, HostedRunSpec
from dayu.contracts.session import SessionRecord, SessionSource, SessionState
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.evidence_locator import (
    ArtifactKind,
    CitationProjection,
    DocumentLocatorPayload,
    EvidenceLocatorError,
    EvidenceLocatorProjection,
    EvidenceLocatorRequest,
    LocatorKind,
    canonical_json_bytes,
    sha256_hex,
)
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.host.prepared_turn import PreparedAgentTurnSnapshot
from dayu.services.fins_service import FinsService
from dayu.services.protocols import FinsServiceProtocol
from tests.fins.evidence_locator_testkit import (
    EvidenceRuntimeContext,
    build_evidence_runtime_context,
)

_PRIMARY_BYTES = b"<service primary bytes>"

SyncResultT = TypeVar("SyncResultT")
StreamEventT = TypeVar("StreamEventT")


class _EvidenceStubHost:
    """满足 HostedExecutionGatewayProtocol 的测试桩。

    本测试只验证 evidence 方法的 delegate 行为，不调用 host 任何方法。
    """

    def create_session(
        self,
        source: SessionSource,
        *,
        session_id: str | None = None,
        scene_name: str | None = None,
        metadata: ExecutionDeliveryContext | None = None,
    ) -> SessionRecord:
        """测试桩不支持 session 创建。

        Args:
            source: session 来源。
            session_id: 可选 session ID。
            scene_name: 可选场景名。
            metadata: 可选元数据。

        Returns:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del source, session_id, scene_name, metadata
        raise AssertionError("evidence delegate 测试不应调用 host")

    def ensure_session(
        self,
        session_id: str,
        source: SessionSource,
        *,
        scene_name: str | None = None,
        metadata: ExecutionDeliveryContext | None = None,
    ) -> SessionRecord:
        """测试桩不支持 session 创建。

        Args:
            session_id: session ID。
            source: session 来源。
            scene_name: 可选场景名。
            metadata: 可选元数据。

        Returns:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del session_id, source, scene_name, metadata
        raise AssertionError("evidence delegate 测试不应调用 host")

    def get_session(self, session_id: str) -> SessionRecord | None:
        """测试桩不支持 session 读取。

        Args:
            session_id: session ID。

        Returns:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del session_id
        raise AssertionError("evidence delegate 测试不应调用 host")

    def list_sessions(
        self,
        *,
        state: SessionState | None = None,
        source: str | None = None,
        scene_name: str | None = None,
    ) -> list[SessionRecord]:
        """测试桩不支持 session 列表。

        Args:
            state: 可选状态过滤。
            source: 可选来源。
            scene_name: 可选场景名。

        Returns:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del state, source, scene_name
        raise AssertionError("evidence delegate 测试不应调用 host")

    def touch_session(self, session_id: str) -> None:
        """测试桩不支持 session 触碰。

        Args:
            session_id: session ID。

        Returns:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del session_id
        raise AssertionError("evidence delegate 测试不应调用 host")

    def run_operation_stream(
        self,
        *,
        spec: HostedRunSpec,
        event_stream_factory: Callable[[HostedRunContext], AsyncIterator[StreamEventT]],
    ) -> AsyncIterator[StreamEventT]:
        """测试桩不支持流式执行。

        Args:
            spec: 运行规格。
            event_stream_factory: 事件流工厂。

        Yields:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del spec, event_stream_factory
        raise AssertionError("evidence delegate 测试不应调用 host")

    def run_operation_sync(
        self,
        *,
        spec: HostedRunSpec,
        operation: Callable[[HostedRunContext], SyncResultT],
        on_cancel: Callable[[], SyncResultT] | None = None,
    ) -> SyncResultT:
        """测试桩不支持同步执行。

        Args:
            spec: 运行规格。
            operation: 同步操作。
            on_cancel: 取消回调。

        Returns:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del spec, operation, on_cancel
        raise AssertionError("evidence delegate 测试不应调用 host")

    def run_agent_stream(
        self,
        execution_contract: ExecutionContract,
        *,
        resumed_pending_turn_id: str | None = None,
        resumed_pending_turn_lease_id: str | None = None,
    ) -> AsyncIterator[AppEvent]:
        """测试桩不支持 Agent 执行。

        Args:
            execution_contract: 执行契约。
            resumed_pending_turn_id: 可选恢复 ID。
            resumed_pending_turn_lease_id: 可选恢复 lease ID。

        Yields:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del execution_contract, resumed_pending_turn_id, resumed_pending_turn_lease_id
        raise AssertionError("evidence delegate 测试不应调用 host")

    def run_prepared_turn_stream(
        self,
        prepared_turn: PreparedAgentTurnSnapshot,
        *,
        resumed_pending_turn_id: str | None = None,
        resumed_pending_turn_lease_id: str | None = None,
    ) -> AsyncIterator[AppEvent]:
        """测试桩不支持 prepared turn 执行。

        Args:
            prepared_turn: prepared turn 快照。
            resumed_pending_turn_id: 可选恢复 ID。
            resumed_pending_turn_lease_id: 可选恢复 lease ID。

        Yields:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del prepared_turn, resumed_pending_turn_id, resumed_pending_turn_lease_id
        raise AssertionError("evidence delegate 测试不应调用 host")

    async def run_agent_and_wait(self, execution_contract: ExecutionContract) -> AppResult:
        """测试桩不支持 Agent 执行。

        Args:
            execution_contract: 执行契约。

        Returns:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del execution_contract
        raise AssertionError("evidence delegate 测试不应调用 host")

    async def run_agent_and_wait_replayable(
        self,
        execution_contract: ExecutionContract,
    ) -> tuple[AppResult, ReplayHandle]:
        """测试桩不支持 Agent 执行。

        Args:
            execution_contract: 执行契约。

        Returns:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del execution_contract
        raise AssertionError("evidence delegate 测试不应调用 host")

    async def replay_agent_and_wait(
        self,
        handle: ReplayHandle,
        execution_contract: ExecutionContract,
    ) -> tuple[AppResult, ReplayHandle]:
        """测试桩不支持 Agent 回放。

        Args:
            handle: replay 句柄。
            execution_contract: 执行契约。

        Returns:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del handle, execution_contract
        raise AssertionError("evidence delegate 测试不应调用 host")

    def discard_replay_state_for_session(self, session_id: str) -> None:
        """测试桩不支持 replay 清理。

        Args:
            session_id: session ID。

        Returns:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del session_id
        raise AssertionError("evidence delegate 测试不应调用 host")

    def discard_replay_state(self, handle: ReplayHandle) -> None:
        """测试桩不支持 replay 清理。

        Args:
            handle: replay 句柄。

        Returns:
            无。

        Raises:
            AssertionError: 测试不应调用 host。
        """

        del handle
        raise AssertionError("evidence delegate 测试不应调用 host")


class _RecordingEvidenceRuntime(DefaultFinsRuntime):
    """记录 evidence 调用的 runtime 包装。"""

    def __init__(self, ctx: EvidenceRuntimeContext) -> None:
        """初始化 runtime 包装。

        Args:
            ctx: runtime 测试上下文。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(
            workspace_root=Path("/tmp/service-evidence-test"),
            company_repository=ctx.company_repository,
            source_repository=ctx.source_repository,
            processed_repository=ctx.processed_repository,
            blob_repository=ctx.blob_repository,
            filing_maintenance_repository=ctx.filing_maintenance_repository,
            processor_registry=ctx.processor_registry,
        )
        self.resolve_calls = 0
        self.validate_calls = 0
        self.read_calls = 0

    def resolve_evidence_locator(self, request: EvidenceLocatorRequest) -> EvidenceLocatorProjection:
        """记录并转发 resolve 调用。

        Args:
            request: 证据定位器请求。

        Returns:
            委托结果。

        Raises:
            无。
        """

        self.resolve_calls += 1
        return super().resolve_evidence_locator(request)

    def validate_evidence_locator(self, locator: EvidenceLocatorProjection) -> None:
        """记录并转发 validate 调用。

        Args:
            locator: 证据定位器投影。

        Returns:
            无。

        Raises:
            无。
        """

        self.validate_calls += 1
        super().validate_evidence_locator(locator)

    def read_citation_projection(self, locator: EvidenceLocatorProjection) -> CitationProjection:
        """记录并转发 read 调用。

        Args:
            locator: 证据定位器投影。

        Returns:
            委托结果。

        Raises:
            无。
        """

        self.read_calls += 1
        return super().read_citation_projection(locator)


@pytest.fixture()
def ctx() -> EvidenceRuntimeContext:
    """构建空 runtime 上下文。"""

    return build_evidence_runtime_context({})


def _seed_document_source(ctx: EvidenceRuntimeContext) -> None:
    """写入 document+source 场景数据。"""

    ctx.source_repository.seed(
        "AAPL",
        "fil_1",
        SourceKind.FILING,
        meta={
            "document_id": "fil_1",
            "form_type": None,
            "is_deleted": False,
            "ingest_complete": True,
            "document_version": "v1",
            "source_fingerprint": "f" * 64,
        },
        primary_bytes=_PRIMARY_BYTES,
        primary_sha=sha256_hex(_PRIMARY_BYTES),
    )


def _build_document_source_request() -> EvidenceLocatorRequest:
    """构造 document+source 请求。"""

    return EvidenceLocatorRequest(
        schema_version="fins-evidence-locator-v1",
        repository_id="dayu.fins.public.v1",
        ticker="AAPL",
        document_id="fil_1",
        source_kind=SourceKind.FILING,
        artifact_kind=ArtifactKind.SOURCE,
        document_version="v1",
        source_fingerprint="f" * 64,
        primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
        locator_kind=LocatorKind.DOCUMENT,
        locator_payload=DocumentLocatorPayload(),
        locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
    )


def _make_service(runtime: DefaultFinsRuntime) -> FinsService:
    """构建测试用 FinsService。"""

    return FinsService(
        host=_EvidenceStubHost(),
        fins_runtime=runtime,
    )


@pytest.mark.unit
def test_fins_service_satisfies_fins_service_protocol(ctx: EvidenceRuntimeContext) -> None:
    """验证 FinsService 满足 FinsServiceProtocol。"""

    service = _make_service(_RecordingEvidenceRuntime(ctx))
    assert isinstance(service, FinsServiceProtocol)


@pytest.mark.unit
def test_resolve_evidence_locator_delegates_to_runtime(ctx: EvidenceRuntimeContext) -> None:
    """验证 FinsService.resolve_evidence_locator 真实委托 runtime。"""

    _seed_document_source(ctx)
    runtime = _RecordingEvidenceRuntime(ctx)
    service = _make_service(runtime)
    request = _build_document_source_request()
    projection = service.resolve_evidence_locator(request)
    assert runtime.resolve_calls == 1
    assert projection.repository_id == "dayu.fins.public.v1"
    assert projection.ticker == "AAPL"
    assert projection.document_id == "fil_1"
    assert projection.primary_content_sha256 == sha256_hex(_PRIMARY_BYTES)


@pytest.mark.unit
def test_validate_evidence_locator_delegates_to_runtime(ctx: EvidenceRuntimeContext) -> None:
    """验证 FinsService.validate_evidence_locator 真实委托 runtime。"""

    _seed_document_source(ctx)
    runtime = _RecordingEvidenceRuntime(ctx)
    service = _make_service(runtime)
    projection = service.resolve_evidence_locator(_build_document_source_request())
    service.validate_evidence_locator(projection)
    assert runtime.validate_calls == 1


@pytest.mark.unit
def test_read_citation_projection_delegates_to_runtime(ctx: EvidenceRuntimeContext) -> None:
    """验证 FinsService.read_citation_projection 真实委托 runtime。"""

    _seed_document_source(ctx)
    runtime = _RecordingEvidenceRuntime(ctx)
    service = _make_service(runtime)
    projection = service.resolve_evidence_locator(_build_document_source_request())
    citation = service.read_citation_projection(projection)
    assert runtime.read_calls == 1
    assert citation.content_bytes == _PRIMARY_BYTES
    assert citation.content_type == "text/html"


@pytest.mark.unit
def test_service_propagates_runtime_error(ctx: EvidenceRuntimeContext) -> None:
    """验证 Service 透传 runtime 的 fail-closed 错误。"""

    _seed_document_source(ctx)
    runtime = _RecordingEvidenceRuntime(ctx)
    service = _make_service(runtime)
    request = _build_document_source_request()
    from dataclasses import replace

    drifted = replace(request, document_version="v2")
    with pytest.raises(EvidenceLocatorError):
        service.resolve_evidence_locator(drifted)


@pytest.mark.unit
def test_service_rejects_direct_dto_unknown_schema_and_repository(
    ctx: EvidenceRuntimeContext,
) -> None:
    """验证三个 delegate 路径对 direct-DTO 反例均抛 EvidenceLocatorError。"""

    _seed_document_source(ctx)
    runtime = _RecordingEvidenceRuntime(ctx)
    service = _make_service(runtime)
    from dataclasses import replace

    bad_schema = replace(_build_document_source_request(), schema_version="fins-evidence-locator-v2")
    with pytest.raises(EvidenceLocatorError):
        service.resolve_evidence_locator(bad_schema)

    bad_repo_request = replace(_build_document_source_request(), repository_id="untrusted.repo")
    with pytest.raises(EvidenceLocatorError):
        service.resolve_evidence_locator(bad_repo_request)

    projection = service.resolve_evidence_locator(_build_document_source_request())
    bad_repo_projection = replace(projection, repository_id="untrusted.repo")
    with pytest.raises(EvidenceLocatorError):
        service.validate_evidence_locator(bad_repo_projection)
    with pytest.raises(EvidenceLocatorError):
        service.read_citation_projection(bad_repo_projection)


@pytest.mark.unit
def test_service_does_not_touch_host(ctx: EvidenceRuntimeContext) -> None:
    """验证 evidence 方法不触碰 host。"""

    _seed_document_source(ctx)
    service = _make_service(_RecordingEvidenceRuntime(ctx))
    projection = service.resolve_evidence_locator(_build_document_source_request())
    service.validate_evidence_locator(projection)
    service.read_citation_projection(projection)


@pytest.mark.unit
def test_service_round_trip_fragment_sha(ctx: EvidenceRuntimeContext) -> None:
    """验证 Service 全链路 citation bytes 的 SHA 闭合。"""

    _seed_document_source(ctx)
    service = _make_service(_RecordingEvidenceRuntime(ctx))
    projection = service.resolve_evidence_locator(_build_document_source_request())
    citation = service.read_citation_projection(projection)
    assert sha256_hex(citation.content_bytes) == projection.locator_content_sha256
    assert canonical_json_bytes(projection.to_dict()) == projection.to_json()
