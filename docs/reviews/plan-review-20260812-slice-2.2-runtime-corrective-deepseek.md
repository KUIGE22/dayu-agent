# Slice 2.2 runtime contract 计划修复独立纠错复审（DeepSeek corrective）

- **状态**：`PASS / open H/M/L = 0/0/3`
- **复审对象**
  - target：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
    - SHA-256：`ec2c97321b8497bbb55505c1e8aeaa05e5f51e1420f45f501a6409aaf5a410da`
  - fix：`docs/reviews/plan-fix-20260812-slice-2.2-runtime-contract-codex.md`
    - SHA-256：`16cb71646dda027b567a8b2579ce52d0ca8f75f9f7a99e7a6c39bf35fe6bb85e`
- **复审范围**：S22-CTRL-009 四项（lookback/scan-limit audit 自然键合并与 distinct 双 audit、ScheduleReservationBatch 重复 scheduled_for 拒绝；croniter-valid 但无 candidate 的 registration/runtime 零 mutation；AgentRunGovernanceResult 三 identity、集中构造、page cardinality/order/duplicate 与 Worker SEND_RETRY/MISSING/terminal/global invariant 矩阵；Worker-owned pure Redis ports、settings 失败不导入 adapter、URL query 与 lone surrogate 实施门禁）及其对全计划的回归（allowlist、命名测试、STOP、DAG、可生成性）。
- **方法**：只读代码事实核对 + 本地 pure 库实测（croniter 6.2.4、redis-py 8.1.0、json surrogate，均不触网/不连 broker）+ adversarial 推演。未运行 live/network/provider/broker/交易；未修改 target/fix/production/tests/deps/README。

## 1. 输入完整性与版本校验

两份文档 SHA-256 实测与任务给定值完全一致（见上）。target 已包含 S22-CTRL-009 全文（§2 第 124-134 行）并声明"覆盖所有冲突旧文字"；fix 是对该勘误的裁决记录、closed contract 摘要与恢复 gate。fix §2 五项裁决（S22-RUNTIME-001~004 + S22-IMPL-001）与 target §2 S22-CTRL-009 四项 + 既有 Redis 合同 hardening 一一对应，无第六项计划外缺口。

## 2. 四项修正的动机验证（代码事实 + 实测）

| 修正项 | 验证结论 | 证据 |
| --- | --- | --- |
| 1. lookback/scan-limit 自然键冲突 | 依据成立 | `0004_durable_schedules.py:251` 唯一键为 `UNIQUE (tenant_id, schedule_id, schedule_version, scheduled_for)`，不含 skip reason；未 relocation 前 lookback 与 scan-limit audit 的 `scheduled_for` 都以 persisted cursor 表示，同 batch 两行必冲突 |
| 2. croniter-valid 但无 candidate | 依据成立（实测） | croniter 6.2.4：`croniter.is_valid('0 0 31 2 *') == True`，但 `get_next` 抛 `CroniterBadDateError`；闰日表达式 `0 0 29 2 *` 无限序列（2096→2104 可返回），probe 通过者 runtime 近乎不可达 |
| 3. governance result 缺 identity | 依据成立 | `dayu/investment/domain/jobs.py:1878` 现有 `AgentRunGovernanceResult` 仅 `action` + `safe_error_code`；`AgentRunCorrelation`（jobs.py:1500）直接携带 `id`/`job_id`/`attempt_id` 三 UUID，identity 逐字段复制可生成 |
| 4. Redis pure types 与 concrete 同模块 | 依据成立 | 当前冻结 WIP 中 `RedisWakeupReadAction/Hint/Read/Subscriber*/Client*` 全部定义于 `dayu/host/redis_wakeup.py`，该文件顶层 `import redis`（第 18 行）——Worker 若为 pure types import 该模块必然在 settings 校验前加载 redis-py，破坏 missing-package fail-fast |
| 5. URL query 覆盖 kwargs（hardening） | 依据成立（实测） | `redis.Redis.from_url('redis://127.0.0.1:6379/0?protocol=3&decode_responses=true&socket_timeout=1')` 实测 connection_kwargs 中 protocol=3/decode_responses=true/socket_timeout=1.0，query 确实覆盖显式 kwargs |
| 6. 孤立 surrogate re-encode（hardening） | 依据成立（实测） | 含 `\ud800` escape 的 bytes 经 `json.loads` 成功产生孤立 surrogate，canonical `ensure_ascii=False` re-encode 抛 `UnicodeEncodeError`；必须收窄为 `INVALID_MESSAGE` |

## 3. S22-CTRL-009 四项逻辑闭环推演（adversarial 反例测试）

### 3.1 lookback/scan-limit 自然键合并

- **未 relocation 耗尽 limit**：working cursor 保持 persisted cursor P；lookback provisional（scheduled_for=P）与 scan-limit audit（scheduled_for=P）同键 → 只保留 scan-limit row。与 S22-CTRL-009.1、"scan origin 仍为 persisted_cursor 时只保留 scan-limit row"（target §5.2 第 3 步）一致。
- **relocation 阶段耗尽 limit**：§5.2 第 2 步"重定位候选同样计入 scan limit"覆盖；未取得 C 则 origin 保持 persisted_cursor → 同上单条 scan-limit row。
- **relocation 成功（C != P）**：lookback audit=scheduled_for(P) 与 scan-limit audit=scheduled_for(C) 必不同（lookback 触发要求 P < L ≤ C）。两条并存且 pairwise distinct，与"已为 distinct_relocated_cursor 时两条 audit 才同 batch 存在"一致。
- **C == P**：仅当 P ≥ L（lookback 不触发），无 lookback audit，单条 scan-limit row；S22-CTRL-009.1"与 persisted cursor 不同后才切"的相等分支自洽。
- **normal batch（lookback+expired/eligible）**：expired/eligible 组 candidate ≥ C ≥ L > P，与 lookback row（P）永不撞键；三项 pairwise distinct 满足 §5.1。
- **与既有 PENDING 撞键**：PENDING scheduled_for 均为已推进过的旧 cursor（< 当前 persisted cursor P），而 audit 键为 P 或 C（≥ P）；且 reserve 与 cursor 推进同事务，scan-limit batch 的 schedule_version=expected_version 与历史行 version 不同。**任何场景下 audit/occurrence 不与该 batch 之外的行撞 0004 唯一键**——"由 pure input 决定、重启相同 bytes"的确定性闭环。
- **并发**：两个 scheduler 同 cursor 构造同键 audit，唯一赢家 CAS version+1，输家 lost_race 零 mutation；不泄漏 unique error。

### 3.2 cron 注册/运行处分置

- register probe（seed `2000-01-01 00:00:00`）在任何 Store 调用前抛 `ScheduleInputError("schedule_cron_has_no_candidate")`；实测确认该 seed 能稳定触发 `CroniterBadDateError`。
- runtime `CroniterBadDateError` → `ScheduleInvariantError("schedule_cron_iteration_exhausted")` 非零停机、零 transition/reservation/audit mutation；activation 可只读 `get`、due 可只读 `list_due` 的文字在 target §2 与 §5.2 一致。不落盘异常正文/cron 字符串/本机 clock，不伪装 scan-limit audit——与 §12 STOP 第 858 行闭合。
- 观察（非缺陷）：实测对通过 probe 的静态 5 字段表达式 croniter 6.2.4 产生无限序列，runtime exhaustion 分支 production 近乎不可达；fail-closed 防御方向正确，无整改必要（见 Open L-3）。

### 3.3 governance identity

- 三 identity（correlation_id/job_id/attempt_id）全部可从同一 `AgentRunGovernanceProjection.correlation` 逐字段复制（代码事实确认 correlation 携带三 UUID）；集中 pure helper 构造 + 组 page 前 zip 验证 cardinality/identity/顺序、同页 correlation/attempt 不重复，可生成。
- Worker 消费：仅 `job_id+attempt_id` 同时匹配 current claim 的 result 改变当前 heartbeat/finalize；同页 attempt identity 唯一 ⟹ 至多一个匹配 result，无歧义。`MISSING_HOST_WAIT` 停止续租、`ACTIVE_WAIT/CANCEL_REQUESTED/CANCEL_ALREADY_REQUESTED/SEND_RETRY` 继续同一 lease、terminal/NO_HOST_RECOVERED/STALE 停止该 attempt 的矩阵与 §6.2 既有语义逐项一致（jobs.py `__post_init__` 已实现 safe-code 矩阵校验）。
- `INVARIANT_FAILURE` 全局非零停机不受 current identity 过滤——明确覆盖"同页其它 correlation 的 invariant 也停机"的 adversarial 场景，堵住"只对当前 attempt 停机"的漏洞。
- 无 claim 时空闲页所有 result 均不匹配，不改变任何状态；claim 已结束时匹配自然失效——安全。

### 3.4 Redis pure 导入边界

- `worker.py`（尚不存在，恢复 gate 最后实现）将拥有 pure read DTO/protocol/runtime state，不 import redis-py；`redis_wakeup.py` 单向 import pure types 并保留唯一 `import redis`。当前 WIP 反向状态（pure types 在 redis_wakeup.py）正是待修复现场，fix §5 gate 第 1 项"先修改 Redis type owner"顺序正确。
- publisher 协议 `JobWakeupPublisherProtocol` 定义于 `dayu/services/job_service.py:167`（Service 层）；adapter 结构化满足即可，无需 import job_service——无 Host→Service 反向依赖。
- startup 顶层 import Worker pure protocols 安全（worker.py 不加载 redis-py）；concrete adapter 仅 `_prepare_queue_admission` local-import，与 §3"仅两处 local import"一致，`test_invalid_platform_settings_never_import_concrete_redis_adapter` 可实现。
- URL query/fragment 门禁在 `Redis.from_url` 前拒绝（实测证明必要性）；仅构造期收窄 `RedisError/TypeError/ValueError`，运行期只收窄 `RedisError`，防止意外 `TypeError/ValueError` 伪装成连接降级——边界精确。

## 4. 全计划回归扫描

- **命名测试**：fix §4 全部 12 个测试名逐字存在于 target §10（逐一 grep 命中，含 `test_scan_limit_before_distinct_relocation_candidate_coalesces_colliding_audits_to_one_scan_limit_row`、`test_scan_limit_after_distinct_relocation_candidate_persists_two_distinct_audits`、`test_schedule_reservation_batch_rejects_duplicate_scheduled_for_before_postgres`、`test_worker_pure_protocol_module_imports_without_redis_package`、`test_lone_unicode_surrogate_hint_is_invalid_and_worker_continues_pg_polling` 等）。
- **allowlist**：fix 未新增任何 production 文件；worker.py/redis_wakeup.py/schedules.py/schedule_service.py/process_intake.py 均在 target §3 既有 allowlist（标注"新"）。当前工作树全部 WIP 文件（未跟踪）都在 allowlist 内，无漂移。
- **DAG**：Redis type owner 变更不改变 target §3 DAG（`Host Worker -> RedisWakeupProtocol`，adapter 单向依赖 pure types）；存储不 import Host/Service/Redis、Host 不 import `dayu.services` 的依赖方向约束未被破坏。
- **STOP 条件**：§12 已含"settings 验证前 import concrete redis_wakeup/redis-py"（850 行）、"register 接受 croniter-valid 无 candidate、runtime CroniterBadDateError 伪装 scan-limit/disable"（858 行）、"lookback/scan-limit 同 identity 时同时 INSERT 并依赖 unique error 回滚、伪造 timestamp/修改 schema 绕过"（837 行）——与 S22-CTRL-009 四项闭合。
- **可生成性**：config.py 的 `PlatformQueueSettings`（字段/默认值/scan-limit 下限公式）已按 §4.1 实现；job_service.py 已有集中 governance helper 雏形（`_governance_send_retry`/`_governance_invariant_failure`）；`AgentRunCorrelation` 三 UUID 使 identity 复制无需新增数据源；fix §5 恢复 gate 顺序（pure identity + Redis type owner → ScheduleService 测试 → Worker/Scheduler/startup）与 §9 slices 依赖方向一致。
- **fix 与 target 文字一致性**：fix §3.1/3.2/3.3 与 target S22-CTRL-009.1/.2/.3/.4 及 §5.2 第 3 步、§7.1、§4.2 逐项核对无冲突残留；§5.2 第 3 步已显式引用 S22-CTRL-009 合并规则，无旧文字并存。

## 5. Open questions

### OQ-1（低）- INVARIANT_FAILURE 全局停机缺显式命名测试
- **位置**：target §10 "Worker/execution/governance" 测试清单（741-780 行）；S22-CTRL-009.3 / §6.2。
- **问题类型**：测试缺口。
- **当前写法**：S22-CTRL-009.3 要求"任一 result 为 INVARIANT_FAILURE 都让整个 runtime 非零停机，不受 current-attempt identity 过滤"，但 §10 命名测试无覆盖（现有 `test_worker_matches_governance_identity_before_changing_current_attempt_heartbeat` 只覆盖匹配语义）。
- **为什么有问题**：该停机路径是本勘误新引入的全局契约，且"非当前 attempt 的 invariant 也停机"是最易被实现者做成"只处理当前 attempt"的隐蔽分支。
- **建议改法**：新增命名测试如 `test_governance_invariant_failure_stops_runtime_regardless_of_current_attempt_identity`（构造同页含非匹配 correlation 的 INVARIANT_FAILURE，断言 runtime 停机）。
- **修复风险**：低。
- **严重程度**：低。

### OQ-2（低）- governance gateway 调用异常的 Worker 处置未定义
- **位置**：target §6.2（498-506 行）、§7.3。
- **问题类型**：契约缺失。
- **当前写法**：§6.2 只规定 gateway 返回值必须是 pure closed types；`govern_agent_runs` 本身抛异常（如 PG 瞬时故障）时 Worker 行为未写明。
- **反例/失败场景**：governance 调用抛未分类异常，Worker 若按 handler error 语义 fail-closed 停机，会把一次瞬时 PG 抖动升级为整个 runtime 停机；若静默继续，可能遗漏 deadline/cancel 治理。
- **建议改法**：在 §6.2 补充一句：governance gateway 未分类异常记录 safe event 后按下一 governance interval 重试（与 cancel send failure 模式一致），仅 INVARIANT_FAILURE（closed result）停机；不得因此写 PG/终止 current attempt。
- **修复风险**：低。
- **严重程度**：低。

### OQ-3（低）- runtime cron exhaustion 分支的生产可达性依赖 croniter 行为
- **位置**：target §2 S22-CTRL-009.2、§5.2 第 3 步、§12 第 858 行。
- **问题类型**：open question 未收敛（防御性设计观察）。
- **当前写法**：register probe 保证表达式在 2000-01-01 后有候选；实测 croniter 6.2.4 对静态 5 字段表达式产生无限序列，runtime `CroniterBadDateError` production 近乎不可达；该分支为 fail-closed 防御。
- **为什么有问题**：`test_persisted_cron_iteration_exhaustion_stops_without_schedule_mutation` 无法经 Service register 构造（probe 拦截），实现需经 Store 层直接持久化 invalid 表达式才能触达 runtime 分支——测试路径应在计划中明示，避免实现者用 mock 或放宽 probe 绕过。
- **建议改法**：无需改语义；在实现说明或测试注释中明确该测试经 store 直接注册绕过 probe（不违反 avoid-mocks 规则）。
- **修复风险**：低。
- **严重程度**：低。

## 6. Residual risks

- 本复审未运行任何真实 PG/Redis/SIGTERM lane（任务约束）；§11 门禁 5/6/7 的真实 lane 证据仍需实施后独立 code review 复核。
- 当前工作树存在大量未跟踪 WIP（schedules.py/schedule_service.py/redis_wakeup.py/process_intake.py/0004 等），均属冻结现场；fix §5 gate 通过前不得视为实现完成，Controller 恢复 gate 必须先执行"pure identity + Redis type owner 先行"的顺序。
- governance identity 升级会触碰 job_service.py 既有 helper 与 AgentRunGovernancePage 构造路径，恢复实施后需重跑 affected tests（fix §6 已声明）。

## 7. 结论

**PASS（open H/M/L = 0/0/3）。**

- 两份 SHA 校验通过；
- S22-CTRL-009 四项修正动机全部由代码事实与本地实测证实，fix 与 target 文字无冲突残留；
- 全计划回归（命名测试逐字、allowlist、DAG、STOP、可生成性）通过；
- adversarial 反例测试未发现 blocker：自然键合并逻辑在所有相撞场景闭环，governance identity 矩阵自洽，Redis 导入边界无反向依赖；
- 3 个 open 均为低严重度建议项（INVARIANT_FAILURE 命名测试、governance 异常处置、runtime exhaustion 测试路径），不阻塞 Controller 按 fix §5 gate 恢复实施。
