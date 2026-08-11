"""reserved Agent run entry 测试（Slice 2.1 A）。

使用真实 ``HostStore`` + ``SQLiteRunRegistry`` 与 stub scene preparation /
fake agent，证明 reserved run identity 的 Host 侧 at-most-once 栅栏：

- ``run_agent_stream`` / ``run_agent_and_wait`` 等 Agent entry 在
  ``reserved_run_id`` 非空时先 ``ensure_reserved_run``；
- 仅 ``created=True`` 才构造 Agent / 调用模型；
- ``created=False`` 立即抛 ``ReservedAgentRunExistsError`` 且携带既有
  record，绝不产生第二次 Agent construction / model entry。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dayu.contracts.agent_execution import (
    AcceptedExecutionSpec,
    AcceptedModelSpec,
    AgentCreateArgs,
    AgentInput,
    ExecutionContract,
    ExecutionHostPolicy,
    ExecutionMessageInputs,
    ScenePreparationSpec,
)
from dayu.contracts.agent_types import AgentTraceIdentity
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.events import AppEventType
from dayu.contracts.run import RunState
from dayu.engine.protocols import ToolExecutor
from dayu.engine.tool_trace import ToolTraceRecorderFactory
from dayu.engine.events import EventType, StreamEvent
from dayu.host.executor import DefaultHostExecutor
from dayu.host.host_execution import HostedRunContext
from dayu.host.host_store import HostStore
from dayu.host.protocols import (
    ReservedAgentRunExistsError,
    ReservedRunIdentityConflictError,
    RunRegistryProtocol,
)
from dayu.host.run_registry import SQLiteRunRegistry
from dayu.host.scene_preparer import PreparedAgentExecution
from dayu.host.prepared_turn import PreparedAgentTurnSnapshot


def _execution_contract(*, session_key: str) -> ExecutionContract:
    """构造测试执行契约（非 resumable，走最简 Agent 路径）。

    Args:
        session_key: Host session key。

    Returns:
        ``ExecutionContract`` 实例。
    """

    return ExecutionContract(
        service_name="durable_job_test",
        scene_name="durable_job_test",
        host_policy=ExecutionHostPolicy(session_key=session_key, resumable=False),
        preparation_spec=ScenePreparationSpec(),
        message_inputs=ExecutionMessageInputs(user_message="durable job fixture"),
        accepted_execution_spec=AcceptedExecutionSpec(
            model=AcceptedModelSpec(model_name="test-model")
        ),
    )


class _StubScenePreparation:
    """stub scene preparation：只返回静态 prepared execution。"""

    async def prepare(self, execution_contract: ExecutionContract, run_context: HostedRunContext) -> PreparedAgentExecution:
        del execution_contract, run_context
        return PreparedAgentExecution(
            agent_input=AgentInput(
                system_prompt="test",
                messages=[],
                agent_create_args=AgentCreateArgs(runner_type="", model_name=""),
            ),
            resume_snapshot=None,
        )

    async def restore_prepared_execution(
        self,
        prepared_turn: PreparedAgentTurnSnapshot,
        run_context: HostedRunContext,
    ) -> AgentInput:
        del prepared_turn, run_context
        raise AssertionError("该测试不应走恢复路径")


class _FakeAgent:
    """fake agent：计数构造与 model entry 次数。"""

    construction_count = 0
    entry_count = 0

    def __init__(
        self,
        *,
        agent_create_args: AgentCreateArgs,
        tool_executor: ToolExecutor | None = None,
        tool_trace_recorder_factory: ToolTraceRecorderFactory | None = None,
        trace_identity: AgentTraceIdentity | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        del (
            agent_create_args,
            tool_executor,
            tool_trace_recorder_factory,
            trace_identity,
            cancellation_token,
        )
        _FakeAgent.construction_count += 1

    async def run_messages(self, messages, *, session_id, run_id, stream):
        del messages, session_id, run_id
        _FakeAgent.entry_count += 1
        yield StreamEvent(EventType.FINAL_ANSWER, {"content": "done", "degraded": False}, {})


def _make_executor(tmp_path: Path) -> tuple[DefaultHostExecutor, SQLiteRunRegistry]:
    """构造真实 SQLite registry + stub agent 的 executor。

    Args:
        tmp_path: 临时目录。

    Returns:
        ``(executor, registry)`` 二元组。
    """

    _FakeAgent.construction_count = 0
    _FakeAgent.entry_count = 0
    store = HostStore(tmp_path / "reserved.db")
    store.initialize_schema()
    registry = SQLiteRunRegistry(store)
    executor = DefaultHostExecutor(
        run_registry=registry,
        scene_preparation=_StubScenePreparation(),
    )
    return executor, registry


@pytest.mark.unit
def test_run_registry_protocol_declares_reserved_ensure_contract() -> None:
    """``RunRegistryProtocol`` 声明 reserved ensure 契约且真实实现满足之。"""

    assert RunRegistryProtocol.ensure_reserved_run is not None
    store = HostStore(Path("/tmp/placeholder-reserved.db"))  # 不初始化 schema，仅类型/协议断言
    registry = SQLiteRunRegistry(store)
    assert isinstance(registry, RunRegistryProtocol)


@pytest.mark.unit
def test_reserved_identity_errors_carry_exact_record_and_safe_message(
    tmp_path: Path,
) -> None:
    """两个 reserved 稳定错误携带既存 record 且 args 只含固定 safe code。"""

    _, registry = _make_executor(tmp_path)
    reserved_run_id = "run_" + "d" * 32
    result = registry.ensure_reserved_run(
        reserved_run_id=reserved_run_id,
        session_id="reserved-s1",
        service_type="durable_job_test",
        scene_name="durable_job_test",
        metadata=None,
    )
    assert result.created is True
    with pytest.raises(ReservedRunIdentityConflictError) as excinfo:
        registry.ensure_reserved_run(
            reserved_run_id=reserved_run_id,
            session_id="reserved-s1",
            service_type="another_service",
            scene_name="durable_job_test",
            metadata=None,
        )
    assert excinfo.value.record.run_id == reserved_run_id
    assert excinfo.value.record.service_type == "durable_job_test"
    assert excinfo.value.args == ("reserved_run_identity_conflict",)
    # 第二个错误：reserved run 已存在、不得再次构造 Agent。
    exists_error = ReservedAgentRunExistsError(excinfo.value.record)
    assert exists_error.record.run_id == reserved_run_id
    assert exists_error.args == ("reserved_agent_run_exists",)


@pytest.mark.unit
def test_reserved_agent_run_existing_never_builds_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """reserved run 已存在时第二次 entry 抛错且绝不构造 Agent / 调用模型。"""

    from unittest.mock import Mock

    executor, registry = _make_executor(tmp_path)
    monkeypatch.setattr("dayu.host.executor.build_async_agent", Mock(side_effect=_FakeAgent))
    execution_contract = _execution_contract(session_key="reserved-s1")
    reserved_run_id = "run_" + "a" * 32

    async def _run_once() -> None:
        async for _event in executor.run_agent_stream(
            execution_contract, reserved_run_id=reserved_run_id
        ):
            pass

    asyncio.run(_run_once())
    run = registry.get_run(reserved_run_id)
    assert run is not None
    assert run.state == RunState.SUCCEEDED
    assert _FakeAgent.construction_count == 1
    assert _FakeAgent.entry_count == 1

    # 第二次 entry：created=False，绝不构造 Agent，抛 ReservedAgentRunExistsError。
    with pytest.raises(ReservedAgentRunExistsError):
        asyncio.run(_run_once())
    assert _FakeAgent.construction_count == 1
    assert _FakeAgent.entry_count == 1


@pytest.mark.unit
def test_reserved_agent_run_existing_outcome_carries_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """existing outcome 的异常携带既有 record 供调用方查询/恢复。"""

    from unittest.mock import Mock

    executor, registry = _make_executor(tmp_path)
    monkeypatch.setattr("dayu.host.executor.build_async_agent", Mock(side_effect=_FakeAgent))
    execution_contract = _execution_contract(session_key="reserved-s2")
    reserved_run_id = "run_" + "b" * 32

    async def _run_once() -> None:
        async for _event in executor.run_agent_stream(
            execution_contract, reserved_run_id=reserved_run_id
        ):
            pass

    asyncio.run(_run_once())
    with pytest.raises(ReservedAgentRunExistsError) as excinfo:
        asyncio.run(_run_once())
    assert excinfo.value.record.run_id == reserved_run_id
    assert excinfo.value.record.session_id == "reserved-s2"
    assert excinfo.value.record.service_type == "durable_job_test"
    assert excinfo.value.record.scene_name == "durable_job_test"
    assert excinfo.value.args == ("reserved_agent_run_exists",)


@pytest.mark.unit
def test_reserved_agent_run_and_wait_created_path_enters_model_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``run_agent_and_wait`` reserved 路径首次创建并恰好一次 model entry。"""

    from unittest.mock import Mock

    executor, registry = _make_executor(tmp_path)
    monkeypatch.setattr("dayu.host.executor.build_async_agent", Mock(side_effect=_FakeAgent))
    execution_contract = _execution_contract(session_key="reserved-s3")
    reserved_run_id = "run_" + "c" * 32

    result = asyncio.run(
        executor.run_agent_and_wait(
            execution_contract, reserved_run_id=reserved_run_id
        )
    )
    assert result.content == "done"
    run = registry.get_run(reserved_run_id)
    assert run is not None
    assert run.state == RunState.SUCCEEDED
    assert _FakeAgent.construction_count == 1
    assert _FakeAgent.entry_count == 1

    # 第二次 wait：existing 抛错，不进入模型。
    with pytest.raises(ReservedAgentRunExistsError):
        asyncio.run(
            executor.run_agent_and_wait(
                execution_contract, reserved_run_id=reserved_run_id
            )
        )
    assert _FakeAgent.construction_count == 1
    assert _FakeAgent.entry_count == 1


@pytest.mark.unit
def test_reserved_run_id_absent_keeps_random_path_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无 reserved_run_id 时保持既有随机 run 路径与行为不变。"""

    from unittest.mock import Mock

    executor, registry = _make_executor(tmp_path)
    monkeypatch.setattr("dayu.host.executor.build_async_agent", Mock(side_effect=_FakeAgent))
    execution_contract = _execution_contract(session_key="random-s1")

    async def _collect_events() -> list[str]:
        event_types: list[str] = []
        async for event in executor.run_agent_stream(execution_contract):
            event_types.append(event.type)
        return event_types

    event_types = asyncio.run(_collect_events())
    assert AppEventType.FINAL_ANSWER in event_types
    runs = registry.list_runs()
    assert len(runs) == 1
    assert runs[0].run_id.startswith("run_")
    assert len(runs[0].run_id) == len("run_") + 12
