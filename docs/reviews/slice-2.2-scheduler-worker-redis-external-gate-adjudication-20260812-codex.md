# Slice 2.2 Redis 外部门禁失败 — Controller 裁决

- 日期：2026-08-12
- Gate：implementation external validation / fix
- Target plan：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- Implementation baseline：`37cac2f`
- 状态：**TWO FINDINGS ACCEPTED / FIX IN PROGRESS**

## Evidence

固定 Redis 8.4 digest 拉取与 identity 核验成功，但真实 integration lane 为 `3 failed`：

1. publish 后第一次 subscriber read 返回 `NO_MESSAGE`。
2. 另两项在 `JobService.enqueue` 写 `job_definitions` 时由 tenant organization 外键拒绝。

测试完成后本次 owner container/network 残留均为 0；未发生行情、模型、provider、Broker 或交易调用。

## Adjudication

### RDX-001 — accepted — resubscribe 未线性化到 server ACK

- `RedisWakeupSubscriber.resubscribe()` 当前只调用 redis-py `subscribe()`；该调用发送命令并更新 client local state，但不证明 Redis server 已处理 exact channel 的 subscribe ACK。
- 另一连接可在 ACK 前 publish，hint 合法丢失；即使 server 已订阅，首次 `get_message(ignore_subscribe_messages=True)` 也可能只消费 ACK并返回空，真实消息留在后续 frame。
- 这违反 accepted plan 对真实 RESP2 publish/subscribe interoperability、health recovery 后 resubscribe 成功和首条 hint 的验收要求。
- 裁决：在 concrete adapter 内有界读取并严格确认 exact tenant/channel 的 subscribe ACK；无 ACK、错误 channel、畸形 frame 或 RedisError均 safe false，程序 TypeError/ValueError不得吞成连接降级。无需 plan fix，既有 production/test allowlist 足够。

### RDX-002 — accepted — integration fixture 使用未注册 tenant

- migration 只 seed default organization；Redis integration file 使用另一个固定 tenant，却未显式注册 organization。
- PostgreSQL 外键拒绝是正确生产行为；本 Slice 明确禁止 worker/JobService 隐式创建或猜 tenant。
- 裁决：integration test 使用 authoritative default organization constant；不得修改 production tenant bootstrap。无需 plan fix，既有 integration-test allowlist 足够。

## Fix gate

允许修改：

- `dayu/host/redis_wakeup.py`
- `tests/application/test_redis_wakeup.py`
- `tests/integration/investment/test_redis_queue_wakeup.py`
- 对应 fix artifact

修复必须通过 focused unit、真实 Redis full lane、Pyright、Ruff、adapter coverage `>=80%`、diff-check 与 owned Docker cleanup；在此之前不得启动 DeepSeek + MiMo final code review、accepted implementation commit、push 或 PR。
