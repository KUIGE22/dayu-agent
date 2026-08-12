# Slice 2.2 Redis 外部门禁修复记录

- 日期：2026-08-12
- Gate：implementation external validation fix
- Baseline：`37cac2f`
- Accepted plan：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- Controller 裁决：`docs/reviews/slice-2.2-scheduler-worker-redis-external-gate-adjudication-20260812-codex.md`
- 状态：**RDX-001 CLOSED / RDX-002 CLOSED / REDIS EXTERNAL LANE PASS**

## 修改范围

本次只修改获准的 Redis concrete adapter、对应 unit/integration tests，并新增本记录：

- `dayu/host/redis_wakeup.py`
- `tests/application/test_redis_wakeup.py`
- `tests/integration/investment/test_redis_queue_wakeup.py`
- `docs/reviews/slice-2.2-scheduler-worker-redis-external-gate-fix-20260812-codex.md`

未修改 accepted plan、总 implementation artifact、README、CI、依赖、Worker public protocol 或 production tenant bootstrap；未 commit、push 或创建 PR。

## Finding closure

### RDX-001 — CLOSED — resubscribe 线性化到 exact server ACK

`RedisWakeupSubscriber.resubscribe()` 现在完成以下单次有界协议：

1. 向唯一 canonical tenant channel 发送 `SUBSCRIBE`。
2. 在构造 Redis client 时已验证并用于 socket 的同一 timeout 上界内，以 `ignore_subscribe_messages=False` 读取 ACK。
3. 只有 frame key 集合精确为 `type/pattern/channel/data`、`type="subscribe"`、`pattern=None`、channel 为本 subscriber exact ASCII bytes、subscription count 为 exact `int(1)` 时返回 `True`。
4. ACK 缺失、畸形、跨 channel 或 redis-py `RedisError` 均返回 `False`；运行期 `TypeError` / `ValueError` 继续传播。
5. 正常消息读取仍显式使用 `ignore_subscribe_messages=True`，wire 仍为 RESP2 bytes；unit test 证明 ACK 被消费后下一次 read 直接返回真实 `WAKEUP`，没有 sleep/retry 掩盖。

`RedisWakeupAdapter.from_url()` 不改变 public signature；只把已验证 timeout 保存为 private concrete state，并通过 private subscriber factory 传递。直接注入 client 的测试构造路径使用既有 1 秒固定上界。

### RDX-002 — CLOSED — integration tenant 使用迁移 seed 真源

真实 integration scope 现在从 `dayu.investment.storage.db.DEFAULT_ORGANIZATION_ID` 构造 UUID，直接复用 migration 已 seed 的 default organization。测试不再复制 `...0022` UUID，也没有向 JobService、Store、migration 或任何 production 路径增加隐式 organization bootstrap。

## Validation evidence

| 门禁 | 命令摘要 | Exit / 结果 |
| --- | --- | --- |
| Focused unit | `uv run pytest tests/application/test_redis_wakeup.py -q --timeout=60` | `0`；`32 passed in 2.04s` |
| Integration collect | `uv run pytest tests/integration/investment/test_redis_queue_wakeup.py --collect-only -q` | `0`；文件完整收集 `3` nodes |
| Fixed image identity | `docker image inspect redis:8.4.0-bookworm@sha256:c22af04bb576503bf16b3e34a1fd2fd82de0f765afd866d2e380145e0af30d78 --format '{{json .RepoDigests}}'` | `0`；RepoDigest exact `redis@sha256:c22af04bb576503bf16b3e34a1fd2fd82de0f765afd866d2e380145e0af30d78` |
| Real Redis + PostgreSQL full file | `uv run pytest tests/integration/investment/test_redis_queue_wakeup.py -q -m integration --timeout=120` | `0`；`3 passed in 12.10s` |
| Exact Pyright | `uv run pyright dayu/host/redis_wakeup.py tests/application/test_redis_wakeup.py tests/integration/investment/test_redis_queue_wakeup.py` | `0`；`0 errors, 0 warnings, 0 informations` |
| Ruff default | `uv run ruff check <three Python files>` | `0`；all checks passed |
| Ruff F/I | `uv run ruff check --select F,I <three Python files>` | `0`；all checks passed |
| Ruff format | `uv run ruff format --check <three Python files>` | `0`；3 files already formatted |
| Redis adapter coverage | 预载 NumPy/Pandas 后由 Coverage API 运行同一 32-node unit file，随后 `coverage report -m --fail-under=80 dayu/host/redis_wakeup.py` | `0`；`220` statements、`20` miss、`91%` |
| Diff whitespace | `git diff --check` | `0` |
| Owned Docker cleanup | 按 `dayu-slice22.redis-owner` label 查询 container/network | `0` residual container；`0` residual network |

第一次直接 pytest-cov coverage 命令 exit `4`，原因是本机已知 coverage 注入顺序导致 Pandas 导入阶段无法加载已安装 NumPy；普通 unit、真实 integration 与 static 均不受影响。按项目既有验证方法在 coverage 启动前预载 NumPy/Pandas 后，同一 unit file `32 passed in 5.74s`，adapter coverage 为 `91%`。未修改 production 绕过此本机 instrumentation 问题。

真实第一节点保持严格顺序：`resubscribe() is True` 后只 publish 一次，随后只调用一次 `get_message()` 即得到 `RedisWakeupReadAction.WAKEUP`；另两节点通过真实 PostgreSQL organization 外键、enqueue/claim/attempt 约束。测试运行前后本 Slice owned Redis 资源均为零残留。

## Residual status

- RDX-001、RDX-002 无 open residual。
- Redis 仍按 accepted plan 仅提供可丢失 hint，PostgreSQL 仍是 job、lease、attempt 与幂等真源。
- 完整离线 resolver / wheelhouse gate 与最终 DeepSeek + MiMo code review 不属于本 fix handoff，由 Controller 在后续 gate 统一推进。
- 未执行 live market、模型、provider、Broker 或交易动作。
