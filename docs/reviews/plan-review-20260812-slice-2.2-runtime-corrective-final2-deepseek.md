# Slice 2.2 Runtime Contract Final2 Closure-Only Corrective Plan Re-review（DeepSeek）

- **状态**：`REVIEW COMPLETE / FINAL2 CLOSURE-ONLY CORRECTIVE RE-REVIEW`
- **审查时间**：20260812-072327
- **target**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
  - **SHA-256**：`6287a159552ca49edeb08b276e8480b01264367f32f34ac30c7108305de229a0`
- **fix**：`docs/reviews/plan-fix-20260812-slice-2.2-runtime-contract-codex.md`
  - **SHA-256**：`21a3eb1e3260b66107e31b14e594f9be4bd54abc9e7849a62413dfeff3a9ef76`
- **审查类型**：实现冻结前的 plan review（closure-only corrective re-review）。当前代码/命名测试尚未实现是预期交付工作，不以"代码不存在/测试未落盘"报 finding；只报告计划本身矛盾、欠定义或不可生成。
- **方法**：只读文档 + 本地 pure 库实测（croniter 6.2.4 无网验证）+ adversarial 推演。未修改 target/fix/任何 production/tests/deps/README；未运行 live/network/provider/broker/交易；未 push/PR。
- **唯一新增文件**：本 artifact。

## 1. 输入完整性与版本校验

| 项 | 实测 SHA-256 | 与给定值 |
| --- | --- | --- |
| target | `6287a159552ca49edeb08b276e8480b01264367f32f34ac30c7108305de229a0` | 一致 |
| fix | `21a3eb1e3260b66107e31b14e594f9be4bd54abc9e7849a62413dfeff3a9ef76` | 一致 |

## 2. 复核范围（closure 观察点逐项闭合验证）

### 2.1 allowlist / DAG / exact touchpoints

- target §3 精确允许文件表 10 个关键 owner（`domain/schedules.py`、`schedule_service.py`、`domain/jobs.py`、`job_service.py`、`host/worker.py`、`host/redis_wakeup.py`、`startup_preparation.py`、`postgres_schedules.py`、`storage/protocols.py`、`host/process_intake.py`）全部在表中且责任描述一致（脚本逐文件命中）。
- S22-CTRL-009 末段精确修改点清单（`ScheduleReservationBatch.__post_init__`、ScheduleService 注册/activation/due cron helper、`AgentRunGovernanceResult.__post_init__`、JobService `_govern_projection` 及 result helper/page assembly、Worker governance action 消费、Redis adapter import/URL/codec 边界、startup admission）与 §3 owner 表逐项对应，未指向 allowlist 外文件。
- DAG：`concrete redis_wakeup adapter（唯一 import redis）------> Worker-owned pure Redis types` 单向依赖；Host worker/scheduler 不 import `dayu.services`/concrete adapter；Storage 不 import Host/Service/Redis —— 与 S22-CTRL-009.4、fix §3.3 一致，无反向依赖。
- fix §2.1 Controller M-1 "补齐 domain/Service/Worker/startup/test owners、精确修改点，并把 DAG 改为 concrete adapter 单向依赖 Worker pure types" 已落实。
- **闭合**。

### 2.2 ScheduleReservationBatch exact duplicate error

- target S22-CTRL-009.1 与 §5.1 均固定：`__post_init__` 构造期拒绝任意重复 `reservation.scheduled_for`，抛 `ScheduleInvariantError("schedule_batch_duplicate_scheduled_for")`，错误在 pure boundary closed，不泄漏数据库 unique error。
- fix §3.1 "ScheduleReservationBatch 构造期拒绝任意重复 scheduled_for，unique conflict 不得下沉到 PostgreSQL" 与 target 一致。
- §12 STOP（line 856）覆盖 "lookback/scan-limit 同 identity 时同时 INSERT 并依赖 unique error 回滚、伪造 timestamp/修改 schema 绕过"。
- §10 命名测试 `test_schedule_reservation_batch_rejects_duplicate_scheduled_for_before_postgres` 逐字存在。
- **闭合**。

### 2.3 cron registration + activation no-set-state + due no-reserve + scheduler exit1 + real Store prep

- registration：固定 naive seed `2000-01-01 00:00:00` probe，`CroniterBadDateError` 或零 candidate 抛 `ScheduleInputError("schedule_cron_has_no_candidate")`，发生在 Store 调用前（S22-CTRL-009.2、§5.1、§5.2 第 3 步一致）。本地实测：`0 0 31 2 *` is_valid=True 但 probe 抛 `CroniterBadDateError` —— 动机成立。
- runtime exhaustion：抛 `ScheduleInvariantError("schedule_cron_iteration_exhausted")`；activation 异常前可只读 `get` 不得调 `set_state`，due 可只读 `list_due` 不得调 `reserve_occurrences`，scheduler 非零停止，零 mutation；不落盘异常正文/cron/本机 clock，不伪装 scan-limit audit。
- real Store prep：§5.2 第 3 步末尾固定 "runtime exhaustion 回归必须通过真实 Store 测试准备直接持久化 immutable legacy/invalid schedule definition 再调用 Service 路径，不得 mock croniter、放宽 registration gate 或绕过真实 Store read"。
- §10 四个命名测试（`test_croniter_valid_but_candidate_empty_is_rejected_before_store`、`test_persisted_cron_iteration_exhaustion_stops_without_schedule_mutation`、`test_activation_cron_iteration_exhaustion_reads_only_and_never_calls_set_state`、`test_due_cron_iteration_exhaustion_reads_only_and_never_calls_reserve_occurrences`、`test_scheduler_cron_iteration_exhaustion_returns_exit_one_without_mutation`）全部逐字存在；§12 STOP（line 877）覆盖所有禁止项。
- **闭合**。

### 2.4 governance identity 集中构造 / cardinality / order / duplicates / action matrix / global invariant

- S22-CTRL-009.3 与 §6.2 一致：`AgentRunGovernanceResult(correlation_id, job_id, attempt_id, action, safe_error_code)`，三 UUID 由同一 input projection 逐字段复制；JobService 只经一个集中 pure helper 构造；组 page 前逐项验证 result/projection cardinality、identity、顺序完全相等；同页 correlation/attempt identity 不得重复。
- Worker 消费：仅 `job_id+attempt_id` 同时匹配 current claim 的 result 改变当前 heartbeat/finalize；匹配 `SEND_RETRY` 继续同一 lease、matching missing/terminal 停止、无关 correlation 只完成自身治理。
- `INVARIANT_FAILURE` 全局非零停机，不受 current identity 过滤（S22-CTRL-009.3、§6.2、fix §3.2、§12 STOP line 865 一致）。
- §10 七个 governance 命名测试（identity 复制/匹配/页面校验/action matrix/global invariant）逐字存在。
- **闭合**。

### 2.5 JobRepositoryFailureError 只沿既有 cadence、strict governance_failure_threshold、env/snapshot、counter reset、threshold exit1、其它异常立即 exit1

- §6.2 与 fix §3.2 一致：`JobRepositoryFailureError` 是唯一可重试基础设施失败，只沿既有 poll/heartbeat governance cadence 重试，不新增 interval；Worker process-local consecutive counter 计数，成功取得并验证的 page 立即清零；达到 `settings.governance_failure_threshold`（默认 3）保留现场、停止新 claim/handler、runtime 返回 1，不再重试；重启后 counter 从 0 开始。
- §4.1：`governance_failure_threshold: int = 3` + env `DAYU_PLATFORM_QUEUE_GOVERNANCE_FAILURE_THRESHOLD` + startup snapshot 记录；`test_nondefault_governance_failure_threshold_is_strict_and_enters_safe_startup_snapshot` 逐字存在。
- 其它未分类异常：立即保留现场并让 runtime 非零退出，绝不被宽捕获成 `SEND_RETRY`/连接降级/业务 failure（§6.2、fix §3.2、§12 STOP line 878）。
- §10 三个命名测试（repository failure threshold / success reset / unclassified exception）逐字存在。
- **闭合**。

### 2.6 Redis Worker-owned pure types / settings-before-import / query / fragment / surrogate / runtime TypeError/ValueError

- S22-CTRL-009.4 与 fix §3.3 一致：`dayu.host.worker` 拥有不 import redis-py 的 pure types；`dayu.host.redis_wakeup` 是唯一 `import redis` owner，单向 import pure types；Worker 不 import adapter；startup 顶层可 import Worker pure protocols，concrete adapter 只在 `_prepare_queue_admission` 在 settings/profile 验证后 local-import。
- URL：无 query、无 fragment；任一 query（protocol/decode_responses/socket timeout/未知键）在 `Redis.from_url` 前以固定 safe admission error 拒绝（S22-CTRL-009、§4.2、§12 STOP line 869 一致）。
- 异常收窄边界：仅 client 构造/URL 配置期收窄 `RedisError/TypeError/ValueError`；已构造 client/PubSub 运行期只收窄 `RedisError`，意外 `TypeError/ValueError` 不得伪装成连接降级。
- surrogate：合法 UTF-8 JSON 解码后含孤立 surrogate 或 canonical re-encode 失败一律 `INVALID_MESSAGE`，Worker 继续 PG poll（§7.1 一致）。
- §10 七个 Redis 命名测试（pure protocol import / only import owner / settings 不导入 adapter / query / fragment / runtime TypeError/ValueError / surrogate）全部逐字存在。
- **闭合**。

## 3. fix §4 测试名与 target §10 逐字一致性

脚本核验：fix §4 提取出 **24** 项测试名，target §10 缺失数 **0**。无重复列表冲突、无名称漂移；两处引用同一批测试。首轮 MiMo M-03（fix 与 plan 测试列表重复不一致）已不再成立。

## 4. Whole-plan blocking regression scan

adversarial 推演（只读，无网）：

1. **scan-limit 与 lookback 自然键闭环**：lookback 触发条件 `next_fire_at < L` 保证 relocation 得到的首个有效 `candidate_utc >= L` 的 C 必不等于 persisted cursor P（P < L ≤ C），因此 C == P 分支只发生在 lookback 未触发时（此时无 lookback audit，无冲突）；origin 仍为 persisted_cursor 时两 audit 同键只保留 scan-limit row，distinct_relocated_cursor 时两条 pairwise distinct —— 与 S22-CTRL-009.1、§5.2 第 2/3 步、fix §3.1 逐字闭环。
2. **scan-limit batch 字段一致性**：§5.1 "resulting cursor 等于 expected persisted cursor" 与 §5.2 第 6 步 "resulting_next_fire_at=expected_next_fire_at" 为同一字段语义；"禁止从 skip_reason 猜 target state" 两处一致。
3. **reservations 项数**：normal batch 最多 3 项（lookback+expired+eligible），scan-limit batch 1–2 条 audit，均满足 §5.1 "1 至 3 项"。
4. **governance threshold 与 redis threshold 分离**：`DAYU_PLATFORM_QUEUE_REDIS_FAILURE_THRESHOLD` 与 `DAYU_PLATFORM_QUEUE_GOVERNANCE_FAILURE_THRESHOLD` 为两个不同 env、两个独立 counter（§7.2 no-message 重置与 §6.2 成功 page 清零），无混用。
5. **INVARIANT_FAILURE 与 gateway 抛异常是两条路径**（§6.2 明示），与 fix §3.2 一致，无宽捕获口。
6. **三次 CAS 预算**：§5.3/S22-CTRL-008.2 "总计最多三次 set_state CAS 尝试，包含首次，三次均 stale 返回第三次 closed result，不自动 rebase" 与 §12 STOP "总 CAS 超过三次" 一致；cron exhaustion 在异常前零 CAS 调用，不与 CAS 预算冲突。
7. **STOP 覆盖**：fix §1 列举的四项修正 + 两项 hardening 全部映射到 §12 STOP 既有条目（line 856/857/858/865/869/877/878），无未覆盖的勘误约束。
8. **fix 与 target 文字一致性**：error code 字符串（`schedule_batch_duplicate_scheduled_for`、`schedule_cron_has_no_candidate`、`schedule_cron_iteration_exhausted`、`candidate_scan_limit_exceeded`、`lookback_exceeded`、`schedule_disabled`）在两份文档中逐字命中；governance 字段顺序 `correlation_id/job_id/attempt_id` 两处一致。

未发现计划自身矛盾、欠定义或不可生成描述。

## 5. Open Questions

无。

## 6. Residual Risks（target §13 既有，不阻塞 PASS）

- Redis hint 可丢/重复/乱序，PG poll 上界吸收延迟；Redis 永不成为 durable truth。
- Host/provider 取消与非协作 handler 受 cooperative/OS hard-stop 边界约束；lease recovery 不能消除任意外部非幂等副作用。
- runtime cron exhaustion 分支 production 近乎不可达（本地实测 probe 通过者产生无限序列），fail-closed 防御路径经真实 Store 直接持久化 legacy/invalid definition 触达，属于预期测试设计而非缺口。
- 一进程一 tenant 是 selector 安全收缩，不是认证；roster/auth 归 Slice 7.1/8.2。
- 本复审未运行真实 PG/Redis/SIGTERM lane（任务约束）；§11 门禁 5/6/7 真实证据仍需实施后 code review 复核。

## 7. 结论

**PASS / open H/M/L = 0/0/0**

target 与 fix 已充分整合首轮 DeepSeek L1/L2/L3、Controller M1/M2/M3/L1、Closure M-1 及 MiMo 首轮全部质疑点；S22-CTRL-009 四项勘误 + 两项 hardening 的全部 closure 观察点在 target/fix 中逐字闭环，allowlist/DAG/touchpoints/命名测试/STOP 无冲突；全计划 blocking regression scan 未发现 blocker。当前代码与命名测试未实现属于实现冻结预期交付，不构成 finding。Controller 可按 fix §5 gate 恢复实施。

**Reviewed target SHA-256**：`6287a159552ca49edeb08b276e8480b01264367f32f34ac30c7108305de229a0`
**Fix document SHA-256**：`21a3eb1e3260b66107e31b14e594f9be4bd54abc9e7849a62413dfeff3a9ef76`
