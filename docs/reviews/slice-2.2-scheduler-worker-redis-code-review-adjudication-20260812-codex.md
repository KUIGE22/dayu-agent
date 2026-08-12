# Slice 2.2 Scheduler / Worker / Redis — 最终代码审查裁决

- 日期：2026-08-12
- Implementation baseline：`37cac2f`
- Accepted plan HEAD：`82cc7d4c5c369f776e12a8dd5a44d6557445ee33`
- DeepSeek source review：`docs/reviews/code-review-20260812-110001-slice-2.2-scheduler-worker-redis-deepseek.md`
- MiMo source review：`docs/reviews/code-review-20260812-110001-slice-2.2-scheduler-worker-redis-mimo.md`
- 状态：**CLOSED / DUAL CORRECTIVE RE-REVIEW PASS**

## Review verdicts

- DeepSeek Flash：`FAIL / open H/M/L = 0/1/0`。
- MiMo v2.5 Pro：`PASS / open H/M/L = 0/0/0`。
- Controller supplemental concurrency review：确认一个与 DeepSeek handler-exception finding 同根、但可由真实外层取消直接触发的 Worker owner-lifecycle 缺陷。

## Accepted findings

### S22-CR-001 — Medium — 正常轮询重复订阅会吞合法 hint 并虚假累计 Redis failure

- DeepSeek finding 1 accepted。
- `PlatformWorker` 已在启动阶段建立 subscription，但 event-assisted 每轮 poll 又无条件调用 `resubscribe()`。
- redis-py 的 `SUBSCRIBE` 发送与 ACK 消费分离；若 socket 中已有更早的 message frame，重复订阅后的 ACK 检查会先取走该合法 message、把它误判为订阅失败并累计 failure。
- Controller 用固定 Redis 8.4 实例复现：初次订阅与 publish 均成功，随后重复 `resubscribe()` 返回 `False`，下一次 read 为 `NO_MESSAGE`，且 owned container/network 清理为 0。
- 修复边界：正常 poll 复用已建立 subscription；仅首次创建或明确 degraded health recovery 重订阅。read/subscribe 失败使本地 subscription 状态失效；PG claim 真源、阈值、探活间隔、公开协议均不得改变。

### S22-CR-002 — Medium — Worker owner 取消或未分类 handler 异常时未先回收其子任务

- DeepSeek finding 4 的 handler-exception 路径 accepted；Controller supplemental finding 把同根外层 cancellation 路径定为 Medium。
- `_run_attempt()` 创建 handler 与 heartbeat task 后没有 owner-level cleanup；外层 `worker.run()` 被取消时会先进入 `finally` 关闭 subscriber，而 handler、heartbeat 与 `Event.wait` 仍在运行。
- Controller 直接复现：owner 已取消且 subscriber 已关闭，同时仍有三个 live child task；另一次 handler `RuntimeError` 复现留下 heartbeat 与 wait task。
- Corrective 草稿的首次取消清理虽能等待，但红队进一步复现：清理期间第二次 `task.cancel()` 会再次打断单层 `shield`，使 `run.finally` 提前关闭 subscriber，handler、heartbeat 与 `to_thread` 仍存活。因此 owner cleanup 必须抗任意重复 task cancellation，而不是只处理第一次。
- complete/fail 进入 governance-required 后还会创建第二个局部 heartbeat；该 task 必须由 `_wait_for_correlation()` 自己在 cancellation/exception 路径回收。
- 修复边界：用独立 cleanup owner 先发协作取消，并在重复 owner cancellation 下仍完整 reap handler 与所有 heartbeat owned work，再传播 `CancelledError` 或程序异常；不得写假 `complete/fail`、不得把外层取消降格为正常 drain、不得提前关闭 subscriber。

## Rejected or deferred observations

### DeepSeek finding 2 — terminal correlation filter — rejected as a code change

- 当前所有 terminal correlation 写入与 attempt/job terminalization 位于同一 PostgreSQL 事务；`LEASED attempt + terminal correlation` 在生产写路径不可达。
- 即使数据库被外部破坏，保留 correlation ownership、拒绝 generic complete/fail 比回退写第二个 terminal 更 fail-closed。
- 不为人为构造的破坏态放宽生产终态边界；不计 open finding。

### DeepSeek finding 3 — Host reader/canceller broad exception — deferred contract clarification

- accepted plan 同时要求 cancel send failure 可重试，以及未分类程序错误必须 fail-fast；现有 public port 没有闭合的“可重试 Host 交互失败”异常类型。
- 本轮若把任意内建异常猜作 transport marker，或直接移除既有 send-retry 行为，都会重新设计公开契约。
- 当前真实 Host adapter 的正常失败面为 `KeyError` race；未发现本 Slice 可触发的未分类异常。记录为后续窄异常契约工作，不在本 corrective fix 扩面。

### DeepSeek finding 5 — 数值 lexical 形态 — rejected

- `float("0x1p3")` 在当前 Python 直接 `ValueError`，review 所列 hex-float 证据不成立。
- underscore 整数虽被 Python parser 接受，但 plan 约束的是有限正数与范围，不是额外的十进制正则语法；当前行为无正确性或安全影响。

### MiMo finding 1 — 非有限 token 诊断文本 — rejected

- `value[:0]` 刻意避免把不受信任 Redis payload token 写入错误边界；消息仍被严格拒绝。
- safe diagnostics 优先于回显攻击者控制内容，不修改。

### MiMo finding 2 — tenant mismatch guard — rejected

- codec 已做租户绑定，Worker 再检查属于 defense-in-depth；不是错误，也不影响行为。

## Corrective gate

只允许修改：

- `dayu/host/worker.py`
- `tests/application/test_platform_worker.py`
- 本裁决、corrective-fix 与既有 implementation artifacts

必须新增并通过：

1. active non-cooperative handler + blocked heartbeat 时取消 owner：资源不得提前关闭，所有 owned work 收口后才传播 `CancelledError`；无 `complete/fail`。
2. 同一清理窗口连续两次取消 owner，仍必须等待真实 handler、heartbeat 与 `to_thread` 收口后才关闭资源；最终保持 cancelled outcome。
3. governance correlation wait 的第二 heartbeat 在 owner 取消（含重复取消）时被完整回收。
4. handler 未分类异常先回收 heartbeat，再由 runtime 返回 nonzero。
5. 多轮正常 event-assisted poll 只订阅一次、不会吞 queued hint；degraded health recovery 仍执行重订阅。
6. Worker focused、模块 coverage `>=80%`、exact Pyright、Ruff default/F/I/full-rule ratchet 与 diff-check 全部通过。

修复后必须由 DeepSeek 与 MiMo 对同一冻结 bytes 做 corrective re-review，二者均 `PASS / open H/M/L = 0/0/0` 后才能进入 accepted implementation commit；不得 push、开 PR、联网调用行情/模型/provider/Broker 或执行交易。

## Closure

- Codex internal corrective fix冻结SHA：worker `a478ea195676ebd9746e1059bd64c5d02129d6cee78f990f6079598981633d9b`；owner test `9550543f213c383ea4ac73f805727c4cff593dac169db0b0ce6569359cda21cc`。
- DeepSeek corrective re-review：`docs/reviews/code-review-20260812-113500-slice-2.2-corrective-deepseek.md`，`PASS / open H/M/L = 0/0/0`。
- MiMo corrective re-review：`docs/reviews/code-review-20260812-113500-slice-2.2-corrective-mimo.md`，`PASS / open H/M/L = 0/0/0`。
- Corrective focused `45 passed`、Worker coverage `86%`、related `399 passed`、全仓clean non-integration `8493 passed, 5 skipped, 209 deselected`；Pyright `0/0/0`、Ruff default/F/I、full-rule positive delta `{}`、diff-check与allowlist outside `0`全部通过。
- S22-CR-001 / S22-CR-002均CLOSED；rejected/deferred observations不转化为本Slice open finding。
- 当前已满足本地accepted implementation commit gate；仍未授权push、PR、merge、部署或live交易动作。
