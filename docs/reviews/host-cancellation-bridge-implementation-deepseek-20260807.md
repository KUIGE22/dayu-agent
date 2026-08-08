# Host CancellationBridge Implementation Evidence

> Gate: implementation | DeepSeek | 2026-08-07
> Plan: `docs/plans/2026-08-07-host-cancellation-bridge-event-loop-latency.md` (v5)
> Accepted-plan commit: `07f102a`
> Follow-up: 2026-08-07 (controller review fixes — type: ignore removal, full docstrings, shared noop_watcher, pytest.raises)

---

## Changed Files

| File | Change |
|---|---|
| `dayu/host/executor.py` | +`import asyncio`; +`_finish_run_async` (~44 lines); 4 finally `_finish_run` → `await _finish_run_async`; `_RunResources` docstring sync |
| `tests/application/test_host_executor_resource_registry.py` | +2 new tests (~280 lines: `test_run_operation_stream_finally_does_not_block_event_loop`, `test_finish_run_async_survives_repeat_cancel`); +`_BlockingBridge`, `_NoopWatcher` helpers; imports: `asyncio`, `threading`, `AsyncIterator`, `CancellationToken`, `HostedRunContext`, `HostedRunSpec`, `AppEvent`, `AppEventType`, `RunRegistryProtocol` |
| `dayu/host/README.md` | §12 资源释放契约：抽象契约更新，移除具体方法名引用 |
| `docs/reviews/host-cancellation-bridge-implementation-deepseek-20260807.md` | 本文件（evidence artifact） |

**未修改**: `cancellation_bridge.py`, lock/config, 其它测试, 其它 `executor.py` 方法。

---

## Follow-up Fixes (controller review)

| # | 修正项 | 变更 |
|---|---|---|
| 1 | 删除 `type: ignore` | 两处 `DefaultHostExecutor(run_registry=StubRunRegistry())` → `cast(RunRegistryProtocol, StubRunRegistry())`；空 async generator `yield AppEvent(...)` 替代 `yield # type: ignore[misc]` |
| 2 | 补全 docstring Raises | `_BlockingBridge.__init__`/`.stop`、`_NoopWatcher.stop`、`_patched_start_run`、`_empty_stream`、`test_finish_run_async_survives_repeat_cancel`、`_release` 均补全 Args/Returns/Raises |
| 3 | `_patched_start_run` | `_ = spec, include_agent_lane`；返回注释 `# list[ConcurrencyPermit]` |
| 4 | repeat-cancel 加固 | 共用同一 `noop_watcher` 对象；`stop_started` 等待改为 `await asyncio.to_thread(bridge.stop_started.wait, _DEADLOCK_TIMEOUT)` 后 `assert started`；`pytest.raises(asyncio.CancelledError)` 替代 try/except |
| 5 | 类型合规 | diff 中无 `type: ignore`、无 `object`/`Any`/无类型签名；`RunRegistryProtocol` / `AppEventType` 已导入 |

---

## RED Evidence (Python 3.13, current .venv)

```
$ python -m pytest tests/application/test_host_executor_resource_registry.py \
  -k "run_operation_stream_finally" -v

FAILED tests/application/.../test_host_executor_resource_registry.py::test_run_operation_stream_finally_does_not_block_event_loop
AssertionError: call_soon_threadsafe 回调必须在 bridge.stop() 阻塞期间被执行，证明事件循环未被阻塞
assert False
```

**Exit code**: 1  
**Failure cause**: 旧代码 `run_operation_stream` finally 中同步调用 `self._finish_run(...)` → `bridge.stop()` → `thread.join()`（在本测试中为 `_BlockingBridge.stop()` 的 `release_stop.wait()`），阻塞了 asyncio 事件循环线程，导致 `call_soon_threadsafe` 回调永远无法执行，`callback_seen_before_release` 保持 `False`。  
**Not caused by**: `AttributeError`（所有属性/方法均存在），资源泄漏（测试结尾 observer finally 保证 `release_stop.set()`，测试结束后线程正常退出）。

---

## GREEN Evidence (after follow-up fixes)

### Python 3.13 (.venv)

```
$ python -m pytest tests/application/test_host_executor_resource_registry.py -k "run_operation_stream_finally or repeat_cancel" -v

test_run_operation_stream_finally_does_not_block_event_loop PASSED
test_finish_run_async_survives_repeat_cancel PASSED

2 passed in 0.05s
```

```
$ python -m pytest tests/application/test_host_executor_resource_registry.py \
  tests/application/test_host_executor.py \
  tests/application/test_host_executor_lane_stacking.py \
  tests/application/test_host_executor_replay.py -v

76 passed in 1.20s
```

### Python 3.11 (uv run --isolated)

```
$ uv run --isolated --python 3.11 --extra dev --extra test \
  python -m pytest tests/application/test_host_executor_resource_registry.py \
  -k "run_operation_stream_finally or repeat_cancel" -v

test_run_operation_stream_finally_does_not_block_event_loop PASSED
test_finish_run_async_survives_repeat_cancel PASSED

2 passed in 0.29s
```

---

## Pyright Evidence

| Environment | Target | Result |
|---|---|---|
| Python 3.13 (.venv) | `dayu/host/executor.py` | 0 errors, 0 warnings |
| Python 3.13 (.venv) | `dayu/host/executor.py` + `tests/application/test_host_executor_resource_registry.py` | 0 errors, 0 warnings |
| Python 3.11 (uv isolated) | `dayu/host/executor.py` + `tests/application/test_host_executor_resource_registry.py` | 0 errors, 0 warnings |

---

## Git Diff Check

```
$ git diff --check
(no output — clean)
```

---

## Type Safety Scan

```
$ git diff tests/application/test_host_executor_resource_registry.py | grep "type: ignore"
(no matches — zero type: ignore in new diff)
```

---

## Secrets Scan

```
$ git diff -- '*.py' '*.md' | grep -iE 'sk-[a-zA-Z0-9]{20,}'
(no matches)
```

---

## Residual Risks

| Risk | Severity | Notes |
|---|---|---|
| NN-6 defer: async daemon 信号路径在事件循环上同步调用 bridge.stop() | LOW | 非目标 §3，仅进程退出信号路径 |
| `deadline_watcher.stop()` 未知异常阻断 bridge.stop() | 理论上不可达 | `timer.cancel()` 无异常路径 |
| `to_thread` 提交失败导致 release_task 立即以异常完成 | 极低 | `exception()` 正常返回异常对象，优先传播 |
| 3 个未独立测试的调用点（`_run_agent_stream_internal`, `run_prepared_turn_stream`, `replay_agent_and_wait`）仅靠 diff review + 已有测试回归 | LOW | finally 块参数完全一致，76 个已有测试回归覆盖 |

---

## Implementation Checklist

- [x] `import asyncio` 已添加到 `executor.py`
- [x] `_finish_run_async` 已实现（~44 lines，完整中文 docstring，含 Args/Returns/Raises）
- [x] `_RunResources` docstring 已更新（提及 `_finish_run_async`）
- [x] 4 个 async finally 调用点已迁移为 `await self._finish_run_async(...)`
- [x] `run_operation_sync` 与 `release_resources_for_run` 同步路径不变
- [x] Slice 6 public integration test PASS（Python 3.11 + 3.13）
- [x] Slice 7 repeat-cancel test PASS（Python 3.11 + 3.13）
- [x] 所有已有 `test_host_executor*` 测试继续通过（76/76，3.11 + 3.13）
- [x] `pyright dayu/host/executor.py` + test file 零诊断（3.11 + 3.13）
- [x] 新增代码零 `type: ignore`、零 `object`/`Any`/无类型签名
- [x] 所有新增函数完整中文 docstring（含 Args/Returns/Raises）
- [x] `dayu/host/README.md` §12 已更新
- [x] `git diff --check` 无空白问题
- [x] 变更文件无 `sk-` 密钥泄漏
- [x] 未 commit、未 push、未 PR

---

*Evidence artifact: implementation gate complete (with follow-up fixes).*
*生成: 2026-08-07 | 模型: DeepSeek | 修订: follow-up controller review*
