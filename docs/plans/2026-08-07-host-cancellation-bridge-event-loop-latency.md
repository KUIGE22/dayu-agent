# Host CancellationBridge 事件循环延迟修复计划（修订版 v5）

> Gate: plan | accepted-after-pass-with-risks | 不实施、不修改生产代码
> 评审链: `plan-review-20260807-113050` → `plan-review-20260807-114623` → `plan-review-20260807-120511` → `plan-review-20260807-121716`


## 修订摘要（v4 → v5）

| 变更 | 触发 |
|---|---|
| 生产 Slice 明确 `import asyncio`（`executor.py` 当前无此导入）| NN-7 |
| 测试 `_patched_start_run` 不调用 `original_start_run`；改为最小无副作用实现，含完整类型注解和 `cast` | NN-2a |
| observer 记录 `callback_seen_before_release` 再 finally release；主测试断言该布尔值 | NN-3 强化 |
| `_BlockingBridge.stop` 改用无 timeout `wait()`，由 observer finally 保证释放 | 防假通过 |
| repeat-cancel 测试先用 `to_thread` 等 `stop_started` 再连续 cancel | 确保取消发生在阻塞期间 |
| `pending` 类型定为 `asyncio.CancelledError \| None`；说明 worker 异常从 `exception()` 自然传播 | NN-8 |
| 新增 `_RunResources` docstring 同步 slice | NN-9 |
| 新增 `dayu/host/README.md` 抽象契约 slice | 显式化 |
| `_empty_stream` 完整类型注解 + 中文 docstring，所有新增函数含 docstring | NN-10 |
| Gate 状态写为 `accepted-after-pass-with-risks` | 评审结论 |


## 0. 裁决证据汇总

| Finding | 裁决 | v5 处置 |
|---|---|---|
| NN-1 | CLOSED | while-not-done 循环 |
| NN-2 | CLOSED | `_patched_start_run` 不调用 `original_start_run`（NN-2a）|
| NN-2a | **接受** | 最小无副作用实现，完整类型注解 |
| NN-3 | CLOSED | `callback_seen_before_release` + observer_error |
| NN-4 | CLOSED | `--isolated --python 3.11` |
| NN-5 | CLOSED | docstring Returns |
| NN-6 | CLOSED (defer) | §16 residual |
| NN-7 | **接受** | `import asyncio` 在生产 slice 显式列出 |
| NN-8 | **接受** | `pending_cancelled: asyncio.CancelledError \| None`；修正注释 |
| NN-9 | **接受** | `_RunResources` docstring slice |
| NN-10 | **接受** | 完整类型注解 + 中文 docstring |

```
实测证据:
  async-generator-finally-await=ok
  thread-join-instance-patch=ok [1.0]
  call-soon-threadsafe-event-ordering=ok
  loop-shield-repeat-cancel=ok
```


## 1. 目标

消除 4 个 async finally 块中同步 `_finish_run` → `bridge.stop()` → `thread.join()` 对 asyncio 事件循环的阻塞，同时不修改 `CancellationBridge`、不修改同步释放路径、不复制释放逻辑、不猜事件循环上下文。


## 2. 动机证据

### 2.1 阻塞路径

4 个 async finally 块同步调用 `self._finish_run(...)`，`_finish_run` → `_release_resources` → `bridge.stop()` → `thread.join(timeout=poll_interval * 2)`（默认 1.0s）。

### 2.2 真实阻塞风险

`_poll_loop` 中 `_stop_event.set()` 后：
- 线程在 `wait()` 中 → **立即唤醒** → 退出（~μs）
- 线程在 `get_run()` 中 → 等 SQLite 查询返回 → 退出（~查询耗时）
- 最坏：`get_run()` I/O 卡住 → `join` 阻塞至 timeout（默认 1.0s）

`join(timeout=poll_interval * 2)` 是上界保护。正常路径几乎立即返回；风险在 I/O 抖动时。


## 3. 非目标

不修改 `CancellationBridge`、`_release_resources`、`_finish_run` 同步方法、`DeadlineWatcher`、`ConcurrencyGovernor`、`_RunResources`、atomic-pop 设计。不修改 async daemon 信号处理路径（NN-6 defer，见 §16）。不扩展 `_release_resources` 异常隔离。不引入新依赖。


## 4. 完整调用链

### 异步路径

```
async finally
  → await _finish_run_async(bridge, deadline_watcher, permits, run_id)
    → release_task = create_task(to_thread(_finish_run, ...))
    → while not done: try shield; except CancelledError: record first; continue
    → worker_exc 优先传播；其次 pending_cancelled
    线程池 worker 内：
      _finish_run → pop(run_id) → _release_resources → bridge.stop()
```

### 同步路径（完全不变）

`run_operation_sync:516-517`、`host.py:862-863`。


## 5. 架构边界与不变量

1. atomic-pop 三者共用：`_finish_run`、`_finish_run_async`（worker 内调 `_finish_run`）、`release_resources_for_run`
2. 资源幂等
3. pop 在 worker 内：提交后 worker 开始前，资源留 registry
4. 有限次取消不穿透：while + shield 循环


## 6. 唯一设计决策（v5 最终版）

```
_finish_run_async(bridge, deadline_watcher, permits, run_id):
    release_task = create_task(to_thread(_finish_run, bridge, ...))
    pending_cancelled: asyncio.CancelledError | None = None
    while not release_task.done():
        try:
            await shield(release_task)
        except asyncio.CancelledError as exc:
            if pending_cancelled is None:
                pending_cancelled = exc
            continue
    worker_exc = release_task.exception()
    # 对 cancelled task, exception() 直接抛 CancelledError（shield 下不可达）
    if worker_exc is not None:
        raise worker_exc          ← 优先 worker 异常（finally 语义）
    if pending_cancelled is not None:
        raise pending_cancelled   ← worker 成功后抛第一份外层取消
```

| 场景 | 行为 |
|---|---|
| 零次取消 | while → break → 正常返回 |
| 单次/重复取消 | 记录第一份 → continue → worker 完成 → raise |
| worker 非取消异常 | 优先 raise |
| to_thread 提交失败 | `exception()` 返回异常 → raise |


## 7. Implementation Slices

### Slice 1：添加 `import asyncio`（1 行）

**文件**：`dayu/host/executor.py`
**证明**：`grep -n "import asyncio" dayu/host/executor.py` 当前无命中。`_finish_run_async` 需要 `asyncio.create_task`、`asyncio.to_thread`、`asyncio.shield`、`asyncio.CancelledError`。

**位置**：在 `import threading`（行 14）之后添加：

```python
import asyncio
```

---

### Slice 2：`_finish_run_async` 新方法（~25 行）

**文件**：`dayu/host/executor.py`
**位置**：`_finish_run` 方法之后（约行 1585）

代码与 v4 一致，docstring 已含完整 `Args:`/`Returns:`/`Raises:` 段。

---

### Slice 3：4 个 async finally 调用点迁移（4 行）

**文件**：`dayu/host/executor.py`

| # | 方法 | 行号 | 改为 `await self._finish_run_async(bridge=..., deadline_watcher=..., permits=..., run_id=...)` |
|---|---|---|---|
| 1 | `run_operation_stream` | 472-473 | × |
| 2 | `_run_agent_stream_internal` | 689-690 | × |
| 3 | `run_prepared_turn_stream` | 804-805 | × |
| 4 | `replay_agent_and_wait` | 1150-1151 | × |

**不变**：`run_operation_sync:516-517`、`host.py:862-863`。

---

### Slice 4：`_RunResources` docstring 同步（~5 行）

**文件**：`dayu/host/executor.py`
**位置**：`_RunResources` dataclass docstring（行 393-401）

旧：
```
由 ``_finish_run``（异步路径终态）或 ``release_resources_for_run``
（SIGINT/SIGTERM 同步路径）通过 atomic-pop 二选一释放。
```

改为：
```
由 ``_finish_run``、``_finish_run_async``（在线程池 worker 内调用
``_finish_run``）或 ``release_resources_for_run``（SIGINT/SIGTERM
同步路径）通过 atomic-pop 保证至多一次真实释放。
```

---

### Slice 5：`dayu/host/README.md` 抽象契约同步（~3 行）

**文件**：`dayu/host/README.md`
**位置**：§12 资源释放契约段（行 623）

旧：
> `_finish_run`（异步终态）与 `release_resources_for_run`（SIGINT 同步路径）通过 atomic-pop 二选一释放

改为：
> 异步终态与 SIGINT 同步路径通过 atomic-pop 二选一释放；异步路径将阻塞资源释放操作卸载到线程池，避免阻塞 asyncio 事件循环

---

### Slice 6：Public integration test（~90 行）

**文件**：`tests/application/test_host_executor_resource_registry.py`
**新增类**：`TestRunOperationStreamEventLoopSafety`
**测试数**：1 个

```python
import asyncio
import threading
from typing import AsyncIterator, cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.events import AppEvent
from dayu.contracts.execution_metadata import empty_execution_delivery_context
from dayu.host.cancellation_bridge import CancellationBridge
from dayu.host.executor import DefaultHostExecutor, RunDeadlineWatcher, _RunResources
from dayu.host.host_execution import HostedRunContext, HostedRunSpec


_DEADLOCK_TIMEOUT = 5.0  # 宽松 deadlock guard，不参与行为断言


class _BlockingBridge:
    """受控阻塞 bridge fake。"""

    def __init__(self) -> None:
        """初始化阻塞控制 event。"""
        self.stop_started = threading.Event()
        self.release_stop = threading.Event()

    def stop(self) -> None:
        """阻塞直到外部 release_stop.set()。由 observer finally 保证释放。"""
        self.stop_started.set()
        self.release_stop.wait()


class _NoopWatcher:
    """无副作用 watcher fake。"""

    def stop(self) -> None:
        """无操作。"""
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
    from tests.application.conftest import StubRunRegistry

    loop = asyncio.get_running_loop()
    bridge = _BlockingBridge()
    noop_watcher = _NoopWatcher()
    callback_executed = threading.Event()

    executor = DefaultHostExecutor(
        run_registry=StubRunRegistry(),  # type: ignore[arg-type]
    )

    # ----- _patched_start_run: 最小无副作用实现 -----
    def _patched_start_run(
        *,
        spec: HostedRunSpec,
        run_id: str,
        include_agent_lane: bool,
    ) -> tuple[HostedRunContext, CancellationBridge, RunDeadlineWatcher, list]:
        """最小无副作用 start_run：不创建真实 bridge/watcher。

        Args:
            spec: 宿主 run 规格。
            run_id: 当前 run ID。
            include_agent_lane: 是否叠加 llm_api lane。

        Returns:
            (HostedRunContext, fake bridge, fake watcher, 空 permits)。
        """
        _ = include_agent_lane
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
            [],
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
        """
        if False:
            yield  # type: ignore[misc]  # 空 async generator 语法

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
```

---

### Slice 7：Repeat-cancel 测试（~40 行）

```python
@pytest.mark.asyncio
async def test_finish_run_async_survives_repeat_cancel() -> None:
    """_finish_run_async 在重复取消下仍等待 worker 完成。

    先用 asyncio.to_thread 等 bridge.stop_started 确保 worker 已进入阻塞，
    再连续 cancel 外层 task。取消结束后释放 bridge.stop()，验证 task
    最终以 CancelledError 完成且资源已释放。

    Returns:
        无。

    Raises:
        AssertionError: bridge.stop() 未调用或资源未释放。
    """
    from tests.application.conftest import StubRunRegistry

    bridge = _BlockingBridge()
    executor = DefaultHostExecutor(
        run_registry=StubRunRegistry(),  # type: ignore[arg-type]
    )
    executor._run_resources["r1"] = _RunResources(
        bridge=cast(CancellationBridge, bridge),
        deadline_watcher=cast(RunDeadlineWatcher, _NoopWatcher()),
        permits=[],
    )

    async def _release() -> None:
        """调用 _finish_run_async 释放资源。"""
        await executor._finish_run_async(
            bridge=cast(CancellationBridge, bridge),
            deadline_watcher=cast(RunDeadlineWatcher, _NoopWatcher()),
            permits=[],
            run_id="r1",
        )

    task = asyncio.create_task(_release())

    # 等 worker 进入 bridge.stop() 阻塞
    await asyncio.wait_for(
        asyncio.to_thread(bridge.stop_started.wait),
        timeout=_DEADLOCK_TIMEOUT,
    )

    # worker 阻塞期间连续取消
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()

    # 释放 worker
    bridge.release_stop.set()

    try:
        await asyncio.wait_for(task, timeout=_DEADLOCK_TIMEOUT)
    except asyncio.CancelledError:
        pass  # 预期：worker 完成后抛出

    assert bridge.stop_started.is_set(), "bridge.stop() 必须被调用"
    assert "r1" not in executor._run_resources, "资源必须从 registry 中 pop"
```

---

### Slice 8：Call-site diff review（非代码）

三个未独立测试的调用点（`_run_agent_stream_internal:689-690`、`run_prepared_turn_stream:804-805`、`replay_agent_and_wait:1150-1151`）通过 diff review 验证 finally 块参数一致性，加上现有测试回归。


## 8. 逐片验证命令

所有命令使用 Python 3.11。当前 `.venv`（3.13）仅作第二回归参考。

```bash
# 确认 Python 版本
uv run --isolated --python 3.11 --extra dev --extra test python --version

# Slice 1-4 实现后
uv run --isolated --python 3.11 --extra dev --extra test pyright dayu/host/executor.py

# Slice 6 集成测试（通过 public run_operation_stream）
uv run --isolated --python 3.11 --extra dev --extra test \
  python -m pytest tests/application/test_host_executor_resource_registry.py \
  -k "run_operation_stream_finally" -v

# Slice 7 重复取消测试
uv run --isolated --python 3.11 --extra dev --extra test \
  python -m pytest tests/application/test_host_executor_resource_registry.py \
  -k "repeat_cancel" -v

# 全部已有测试回归
uv run --isolated --python 3.11 --extra dev --extra test \
  python -m pytest \
  tests/application/test_host_executor_resource_registry.py \
  tests/application/test_host_executor.py \
  tests/application/test_host_executor_lane_stacking.py \
  tests/application/test_host_executor_replay.py -v

# 全量 pyright
uv run --isolated --python 3.11 --extra dev --extra test pyright dayu/host/

# Diff review
git diff dayu/host/executor.py | grep -nE "^\+\s+await self\._finish_run_async|^-\s+self\._finish_run\("
```

第二环境（当前 3.13 `.venv`，仅回归参考）：
```bash
source .venv/bin/activate
python -m pytest tests/application/test_host_executor_resource_registry.py -v
pyright dayu/host/
```


## 9. 完成条件

- [ ] `import asyncio` 已添加到 `executor.py`
- [ ] `_finish_run_async` 已实现（~25 行，完整 docstring）
- [ ] `_RunResources` docstring 已更新
- [ ] 4 个 async finally 调用点已迁移
- [ ] Slice 6 public integration test PASS（Python 3.11）
- [ ] Slice 7 repeat-cancel test PASS（Python 3.11）
- [ ] 所有已有 `test_host_executor*` 测试继续通过
- [ ] `pyright dayu/host/executor.py` 零新增诊断
- [ ] `dayu/host/README.md` §12 已更新
- [ ] `git diff --check` 无空白问题
- [ ] diff review 通过


## 10. 停止条件

| 条件 | 处置 |
|---|---|
| while + shield 循环在 3.11 上与 3.13 行为不同 | 暂停，3.11 单独验证 |
| Slice 6 在慢 CI 上 observer hang | 调大 `_DEADLOCK_TIMEOUT` 或检查 monkeypatch |
| `cast` 导入冲突 | 确认 `from typing import cast` 在测试文件顶部 |


## 11. 回滚点

| 回滚点 | 操作 |
|---|---|
| Slice 1-4 完成 | `_finish_run_async` 无调用方，可安全保留 |
| Slice 3 任一调用点 | 逐点回退 finally 块 |
| 全量回归失败 | 保留 `_finish_run_async`，回退所有 finally 调用点 |


## 12. Residual Risks

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| async daemon 信号路径在事件循环上同步调用 bridge.stop()（NN-6 defer）| 确定 | 低——仅进程退出信号路径 | 非目标 §3，未来工作单元可评估 |
| 线程创建失败导致 worker 未启动 | 极低 | 低——资源留 registry，sync signal path 可接管 | §5 不变量 3 |
| `deadline_watcher.stop()` 未知异常阻断 bridge.stop() | 理论上不可达 | 低——`timer.cancel()` 无异常路径 | 文档诚实说明 |
| Slice 6 在慢 CI 上 observer 线程 hang | 低 | 低——`_DEADLOCK_TIMEOUT=5.0` 远大于正常执行时间 | 常量集中，可调大 |


## 13. 最终 Gate 状态

**accepted-after-pass-with-risks**（评审链 `plan-review-20260807-121716` 判定）。

实施条件：
1. 修正 `import asyncio`（NN-7）
2. `_patched_start_run` 不调用 original（NN-2a）
3. observer `callback_seen_before_release` 防假通过
4. `_BlockingBridge.stop` 无 timeout wait
5. repeat-cancel 先等 stop_started 再 cancel

唯一保留 risk：NN-6 defer（async daemon 信号路径），写入非目标和 residual risks。

---

*Plan artifact v5: code-generation-ready, handoff to implementer.*
*生成: 2026-08-07 | 评审链: 113050 → 114623 → 120511 → 121716*
*目标分支: codex/dual-model-research-mvp*
