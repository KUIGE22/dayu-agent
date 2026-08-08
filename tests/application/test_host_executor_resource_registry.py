"""``DefaultHostExecutor`` run 资源注册表语义单元测试（覆盖 #46）。

覆盖：
- ``release_resources_for_run`` 从注册表 atomic-pop 后调用 governor.release /
  watcher.stop / bridge.stop；
- 与 ``_finish_run`` 互相幂等：先后两路调用只会真正释放一次；
- 未注册 run_id 静默 no-op，不抛异常；
- ``run_operation_stream`` finally 块不阻塞事件循环（异步资源释放到线程池）；
- ``_finish_run_async`` 重复取消安全性。
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator, cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.events import AppEvent, AppEventType
from dayu.contracts.execution_metadata import empty_execution_delivery_context
from dayu.host.cancellation_bridge import CancellationBridge
from dayu.host.executor import DefaultHostExecutor, RunDeadlineWatcher, _RunResources
from dayu.host.host_execution import HostedRunContext, HostedRunSpec
from dayu.host.protocols import (
    ConcurrencyGovernorProtocol,
    ConcurrencyPermit,
    LaneStatus,
    RunRegistryProtocol,
)
from tests.application.conftest import StubRunRegistry


_DEADLOCK_TIMEOUT = 5.0  # 宽松 deadlock guard，不参与行为断言


class _BlockingBridge:
    """受控阻塞 bridge fake。

    在 ``stop()`` 中阻塞直到外部 ``release_stop.set()``，用于模拟
    ``CancellationBridge.stop()`` → ``thread.join()`` 阻塞事件循环的场景。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    def __init__(self) -> None:
        """初始化阻塞控制 event。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """
        self.stop_started = threading.Event()
        self.release_stop = threading.Event()

    def stop(self) -> None:
        """阻塞直到外部 release_stop.set()。由 observer finally 保证释放。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """
        self.stop_started.set()
        self.release_stop.wait()


class _NoopWatcher:
    """无副作用 watcher fake。

    对应 ``RunDeadlineWatcher.stop()`` 的幂等无操作实现。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    def stop(self) -> None:
        """无操作。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """
        pass


@pytest.mark.asyncio
async def test_run_operation_stream_finally_does_not_block_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """通过 public run_operation_stream 验证 finally 块不阻塞事件循环。

    确定性验证（timeout 仅防死锁，行为断言基于事件先后）：
    1. monkeypatch _start_run：最小无副作用实现，注入 blocking bridge
    2. 外部 observer 线程：等 bridge.stop() 被调用 →
       call_soon_threadsafe 调度回调 → 记录 callback_seen_before_release
       → finally release_stop.set()
    3. 完整消费 run_operation_stream（触发 finally）
    4. 断言 callback_seen_before_release 为真

    旧代码（finally 中同步 _finish_run）必然 FAIL：
    bridge.stop() 阻塞事件循环线程，observer 等不到 release，
    t.join 超时 → is_alive() 断言失败。

    新代码（finally 中 await _finish_run_async）必须 PASS：
    bridge.stop() 在线程池中阻塞，事件循环继续处理回调。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        RuntimeError: observer 线程异常或超时时抛出。
        AssertionError: call_soon_threadsafe 回调未在 bridge.stop() 阻塞期间执行。
    """
    loop = asyncio.get_running_loop()
    bridge = _BlockingBridge()
    noop_watcher = _NoopWatcher()
    callback_executed = threading.Event()

    executor = DefaultHostExecutor(
        run_registry=cast(RunRegistryProtocol, StubRunRegistry()),
    )

    # ----- _patched_start_run: 最小无副作用实现，绝不调用 original -----
    def _patched_start_run(
        *,
        spec: HostedRunSpec,
        run_id: str,
        include_agent_lane: bool,
    ) -> tuple[HostedRunContext, CancellationBridge, RunDeadlineWatcher, list[ConcurrencyPermit]]:
        """最小无副作用 start_run：不创建真实 bridge/watcher。

        不调用 original _start_run，直接注册 run 并注入 fake 资源，
        避免泄漏真实 CancellationBridge 的 polling thread 和 RunDeadlineWatcher 的 timer。

        Args:
            spec: 宿主 run 规格。
            run_id: 当前 run ID。
            include_agent_lane: 是否叠加 llm_api lane。

        Returns:
            (HostedRunContext, fake bridge, fake watcher, 空 permits)。

        Raises:
            无。
        """
        _ = spec, include_agent_lane
        executor.run_registry.start_run(run_id)
        token = CancellationToken()
        context = HostedRunContext(run_id=run_id, cancellation_token=token)
        with executor._run_resources_lock:
            executor._run_resources[run_id] = _RunResources(
                bridge=cast(CancellationBridge, bridge),
                deadline_watcher=cast(RunDeadlineWatcher, noop_watcher),
                permits=[],
            )
        return (
            context,
            cast(CancellationBridge, bridge),
            cast(RunDeadlineWatcher, noop_watcher),
            [],  # list[ConcurrencyPermit]
        )

    monkeypatch.setattr(executor, "_start_run", _patched_start_run)

    # ----- 外部 observer -----
    observer_error: BaseException | None = None
    callback_seen_before_release = False

    def external_observer() -> None:
        """等 bridge.stop() 被调用后通过 call_soon_threadsafe 探测事件循环。

        将 callback_executed.wait 的结果记录到 callback_seen_before_release，
        然后 finally 释放 bridge.stop()。主测试只断言 callback_seen_before_release，
        避免释放后 callback 执行造成假通过。

        Args:
            无。

        Returns:
            无。

        Raises:
            无（异常存入 observer_error）。
        """
        nonlocal observer_error, callback_seen_before_release
        try:
            if not bridge.stop_started.wait(timeout=_DEADLOCK_TIMEOUT):
                raise RuntimeError("bridge.stop() 未在超时内调用")
            loop.call_soon_threadsafe(callback_executed.set)
            callback_seen_before_release = callback_executed.wait(
                timeout=_DEADLOCK_TIMEOUT
            )
        except BaseException as exc:
            observer_error = exc
        finally:
            bridge.release_stop.set()

    t = threading.Thread(target=external_observer, daemon=True, name="observer")
    t.start()

    # ----- 通过 public run_operation_stream 触发 finally -----
    spec = HostedRunSpec(
        operation_name="test",
        session_id=None,
        scene_name=None,
        metadata=empty_execution_delivery_context(),
    )

    async def _empty_stream(_ctx: HostedRunContext) -> AsyncIterator[AppEvent]:
        """空事件流，仅用于触发 finally 释放路径。

        Args:
            _ctx: 宿主 run 上下文。

        Returns:
            不产生事件的异步迭代器。

        Raises:
            无。
        """
        if False:
            yield AppEvent(type=AppEventType.DONE, payload={}, meta={})

    stream = executor.run_operation_stream(
        spec=spec,
        event_stream_factory=_empty_stream,
    )
    async for _ in stream:
        pass

    # ----- 验证 -----
    t.join(timeout=_DEADLOCK_TIMEOUT)
    if t.is_alive():
        bridge.release_stop.set()
        raise RuntimeError("observer 线程未在超时内完成")

    if observer_error is not None:
        raise RuntimeError(
            f"observer 线程异常: {observer_error}"
        ) from observer_error

    assert callback_seen_before_release, (
        "call_soon_threadsafe 回调必须在 bridge.stop() 阻塞期间被执行，"
        "证明事件循环未被阻塞"
    )


@pytest.mark.asyncio
async def test_finish_run_async_survives_repeat_cancel() -> None:
    """_finish_run_async 在重复取消下仍等待 worker 完成。

    先用 asyncio.to_thread 等 bridge.stop_started 确保 worker 已进入阻塞，
    再连续 cancel 外层 task。取消结束后释放 bridge.stop()，验证 task
    最终以 CancelledError 完成且资源已释放。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: bridge.stop() 未调用、资源未释放、或 stop_started 超时。
        asyncio.CancelledError: task 在 pytest.raises 中确认抛出。
    """
    bridge = _BlockingBridge()
    noop_watcher = _NoopWatcher()
    executor = DefaultHostExecutor(
        run_registry=cast(RunRegistryProtocol, StubRunRegistry()),
    )
    executor._run_resources["r1"] = _RunResources(
        bridge=cast(CancellationBridge, bridge),
        deadline_watcher=cast(RunDeadlineWatcher, noop_watcher),
        permits=[],
    )

    async def _release() -> None:
        """调用 _finish_run_async 释放资源。

        Args:
            无。

        Returns:
            无。

        Raises:
            BaseException: worker 异常或外层取消均从 _finish_run_async 传播。
        """
        await executor._finish_run_async(
            bridge=cast(CancellationBridge, bridge),
            deadline_watcher=cast(RunDeadlineWatcher, noop_watcher),
            permits=[],
            run_id="r1",
        )

    task = asyncio.create_task(_release())

    # 等 worker 进入 bridge.stop() 阻塞，带超时断言
    started = await asyncio.to_thread(
        bridge.stop_started.wait, _DEADLOCK_TIMEOUT
    )
    assert started, "bridge.stop() 未在超时内被 worker 调用"

    # worker 阻塞期间连续取消
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()

    # 释放 worker
    bridge.release_stop.set()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=_DEADLOCK_TIMEOUT)

    assert bridge.stop_started.is_set(), "bridge.stop() 必须被调用"
    assert "r1" not in executor._run_resources, "资源必须从 registry 中 pop"


@dataclass
class _SpyBridge:
    """记录 ``stop`` 调用次数的伪 CancellationBridge。"""

    stop_calls: int = 0

    def stop(self) -> None:
        """仅计数，无副作用。"""

        self.stop_calls += 1

    def start(self) -> None:
        """测试不需要启动，留空。"""


@dataclass
class _SpyWatcher:
    """记录 ``stop`` 调用次数的伪 RunDeadlineWatcher。"""

    stop_calls: int = 0

    def stop(self) -> None:
        """仅计数，无副作用。"""

        self.stop_calls += 1

    def start(self) -> None:
        """测试不需要启动，留空。"""


@dataclass
class _SpyGovernor:
    """记录 ``release`` 调用次数的伪 ConcurrencyGovernor。"""

    released: list[ConcurrencyPermit] = field(default_factory=list)
    raise_on_release: bool = False

    def release(self, permit: ConcurrencyPermit) -> None:
        """记录被释放的 permit，按需抛异常以验证错误分支。"""

        if self.raise_on_release:
            raise RuntimeError("permit 释放故意失败")
        self.released.append(permit)

    def acquire(self, lane: str, *, timeout: float | None = None) -> ConcurrencyPermit:
        """测试不会触发，未实现。"""

        raise NotImplementedError

    def acquire_many(
        self,
        lanes: list[str],
        *,
        timeout: float | None = None,
        cancellation_token: object | None = None,
    ) -> list[ConcurrencyPermit]:
        """测试不会触发，未实现。"""

        raise NotImplementedError

    def try_acquire(self, lane: str) -> ConcurrencyPermit | None:
        """测试不会触发，未实现。"""

        raise NotImplementedError

    def get_lane_status(self, lane: str) -> LaneStatus:
        """测试不会触发，未实现。"""

        raise NotImplementedError

    def get_all_status(self) -> dict[str, LaneStatus]:
        """测试不会触发，未实现。"""

        raise NotImplementedError

    def cleanup_stale_permits(self) -> list[str]:
        """测试不会触发，未实现。"""

        raise NotImplementedError


def _build_executor(governor: _SpyGovernor | None = None) -> DefaultHostExecutor:
    """构造仅测试用的最小 ``DefaultHostExecutor`` 实例。"""

    return DefaultHostExecutor(
        run_registry=cast("object", StubRunRegistry()),  # type: ignore[arg-type]
        concurrency_governor=cast(ConcurrencyGovernorProtocol, governor) if governor is not None else None,
    )


def _build_permit(permit_id: str, lane: str) -> ConcurrencyPermit:
    """构造测试 permit。"""

    return ConcurrencyPermit(permit_id=permit_id, lane=lane, acquired_at=datetime.now(tz=timezone.utc))


def _inject_resources(
    *,
    executor: DefaultHostExecutor,
    run_id: str,
    bridge: _SpyBridge,
    watcher: _SpyWatcher,
    permits: list[ConcurrencyPermit],
) -> None:
    """直接把伪资源注入到 executor 注册表，绕过 ``_start_run``。"""

    executor._run_resources[run_id] = _RunResources(
        bridge=cast(CancellationBridge, bridge),
        deadline_watcher=cast(RunDeadlineWatcher, watcher),
        permits=list(permits),
    )


@pytest.mark.unit
def test_release_resources_for_run_drains_registry_and_stops_components() -> None:
    """同步释放路径：从注册表 pop 后释放 permit / 停 watcher / 停 bridge。"""

    governor = _SpyGovernor()
    executor = _build_executor(governor)
    bridge = _SpyBridge()
    watcher = _SpyWatcher()
    permits = [_build_permit("p1", "lane_a"), _build_permit("p2", "lane_b")]
    _inject_resources(executor=executor, run_id="r1", bridge=bridge, watcher=watcher, permits=permits)

    executor.release_resources_for_run("r1")

    assert "r1" not in executor._run_resources
    assert [p.permit_id for p in governor.released] == ["p2", "p1"]  # reversed
    assert watcher.stop_calls == 1
    assert bridge.stop_calls == 1


@pytest.mark.unit
def test_release_resources_for_run_unknown_run_is_noop() -> None:
    """未注册 run_id 静默退出。"""

    governor = _SpyGovernor()
    executor = _build_executor(governor)

    executor.release_resources_for_run("missing")

    assert governor.released == []
    assert executor._run_resources == {}


@pytest.mark.unit
def test_release_resources_for_run_then_finish_run_is_idempotent() -> None:
    """先同步释放后异步 ``_finish_run``：第二步必须 no-op。"""

    governor = _SpyGovernor()
    executor = _build_executor(governor)
    bridge = _SpyBridge()
    watcher = _SpyWatcher()
    permits = [_build_permit("p1", "lane_a")]
    _inject_resources(executor=executor, run_id="r1", bridge=bridge, watcher=watcher, permits=permits)

    executor.release_resources_for_run("r1")
    # 第二次（异步 finally 路径）要 no-op
    executor._finish_run(
        bridge=cast(CancellationBridge, bridge),
        deadline_watcher=cast(RunDeadlineWatcher, watcher),
        permits=permits,
        run_id="r1",
    )

    assert len(governor.released) == 1
    assert watcher.stop_calls == 1
    assert bridge.stop_calls == 1


@pytest.mark.unit
def test_finish_run_then_release_resources_for_run_is_idempotent() -> None:
    """先异步 ``_finish_run`` 后同步释放：第二步必须 no-op。"""

    governor = _SpyGovernor()
    executor = _build_executor(governor)
    bridge = _SpyBridge()
    watcher = _SpyWatcher()
    permits = [_build_permit("p1", "lane_a")]
    _inject_resources(executor=executor, run_id="r1", bridge=bridge, watcher=watcher, permits=permits)

    executor._finish_run(
        bridge=cast(CancellationBridge, bridge),
        deadline_watcher=cast(RunDeadlineWatcher, watcher),
        permits=permits,
        run_id="r1",
    )
    executor.release_resources_for_run("r1")

    assert len(governor.released) == 1
    assert watcher.stop_calls == 1
    assert bridge.stop_calls == 1


@pytest.mark.unit
def test_release_resources_for_run_logs_and_continues_on_permit_release_failure() -> None:
    """permit 释放抛异常仅记日志，不影响 watcher / bridge.stop。"""

    governor = _SpyGovernor(raise_on_release=True)
    executor = _build_executor(governor)
    bridge = _SpyBridge()
    watcher = _SpyWatcher()
    permits = [_build_permit("p1", "lane_a")]
    _inject_resources(executor=executor, run_id="r1", bridge=bridge, watcher=watcher, permits=permits)

    executor.release_resources_for_run("r1")

    assert watcher.stop_calls == 1
    assert bridge.stop_calls == 1
    assert "r1" not in executor._run_resources


@pytest.mark.unit
def test_host_cancel_run_and_settle_invokes_executor_release_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host.cancel_run_and_settle 必须把资源释放转发给 DefaultHostExecutor。"""

    from typing import cast as _cast

    from dayu.contracts.run import RunState
    from dayu.host.host import Host
    from dayu.host.host_execution import HostExecutorProtocol
    from dayu.host.protocols import RunRegistryProtocol, SessionRegistryProtocol
    from dayu.host.reply_outbox_store import InMemoryReplyOutboxStore
    from tests.application.conftest import StubSessionRegistry

    registry = StubRunRegistry()
    record = registry.register_run(service_type="chat", session_id="session-1")
    registry.start_run(record.run_id)

    executor = DefaultHostExecutor(run_registry=_cast(RunRegistryProtocol, registry))
    host = Host(
        executor=_cast(HostExecutorProtocol, executor),
        session_registry=_cast(SessionRegistryProtocol, StubSessionRegistry()),
        run_registry=_cast(RunRegistryProtocol, registry),
        reply_outbox_store=InMemoryReplyOutboxStore(),
    )

    release_calls: list[str] = []

    def _spy(run_id: str) -> None:
        release_calls.append(run_id)

    monkeypatch.setattr(executor, "release_resources_for_run", _spy)

    settled = host.cancel_run_and_settle(record.run_id)

    assert settled.state == RunState.CANCELLED
    assert release_calls == [record.run_id]
