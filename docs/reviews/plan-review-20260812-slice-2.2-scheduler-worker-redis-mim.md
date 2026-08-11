# Plan Review — Slice 2.2 Scheduler / Worker / Redis

## Scope

- **Mode**: adversarial plan review
- **Target**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **Baseline**: `38ddad4`（Slice 2.1 accepted commit）
- **Output file**: `docs/reviews/plan-review-20260812-slice-2.2-scheduler-worker-redis-mim.md`
- **Related docs**: master plan `docs/plans/2026-08-10-investment-platform-restoration.md`、Controller handoff `docs/reviews/plan-handoff-20260812-slice-2.2-scheduler-worker-redis-codex.md`
- **Code baseline verified**: `38ddad4` = HEAD，`git log` 确认；无后续 commit
- **Excluded**: 不修改 production/tests/README/dependency/CI/plan/artifacts；不运行 live/model/broker

## Conclusion

**PASS-WITH-RISKS / open H/M/L = 0/3/2**

Plan 整体结构清晰，七个 Controller blocking contract 全部有精确 plan section 对应，owner DAG、exact allowlist、schedule outbox 原子性、execution request token 隔离、Redis 安全消息、startup ordering 和 STOP conditions 设计扎实。以下 5 项 finding 中 3 项 Medium 不阻塞 plan acceptance，但应由 Controller 裁决是否在 plan 中补充精确规格。

---

## Assumptions Tested

1. **Occurrence outbox 原子性**: plan §5.3/§2 S22-CTRL-001 声称 cursor 推进和 pending occurrence 在同一事务。验证：plan 文本明确 "transaction: INSERT pending occurrence + CAS 推进 schedule cursor -> commit"，正确。
2. **Production baseline 两项 mapping**: plan §8 声称 Slice 2.1 accepted baseline 精确为 `investment_identity + durable_jobs`。验证：`startup_preparation.py:393,456` 确认当前 provider mapping 为 `{"investment_identity": ..., "durable_jobs": ...}`。正确。
3. **Host.cancel_run 协作语义**: plan §6.2 声称 `cancel_run` 只写 `cancel_requested_at`。验证：`host.py:839-862` 确认 `cancel_run` 调用 `request_cancel` 只写 `cancel_requested_at`，不推进状态。正确。
4. **cancel_run_and_settle 禁止正常 worker 使用**: plan §6.2/§12 STOP 声称正常 worker 不得调用 `cancel_run_and_settle`。验证：`host.py:863` 确认该方法是 CLI/process sync 路径，docstring 明确 "sync CLI 在 SIGINT/SIGTERM/atexit 路径上调用"。正确。
5. **新文件均不存在**: plan §3 allowlist 中的 `scheduler.py`、`worker.py`、`platform.py`、`schedules.py`、`redis_wakeup.py`、`schedule_service.py`、`0004_durable_schedules.py` 均不存在。需全新创建。正确。
6. **Queue config 不存在**: plan §4 的 `PlatformQueueSettings`、`PlatformQueueMode` 在 `config.py` 中不存在。当前 `PlatformDeploymentProfile` 只有 `DEVELOPMENT`/`PRODUCTION`，无 `INTEGRATION`。需新增。正确。
7. **Execution registry 不存在**: plan §6.1 的 `JobExecutionRegistry`、`JobExecutionHandlerProtocol`、`JobExecutionRequest` 在 `job_service.py` 中不存在。需新增。正确。
8. **Architecture constraints**: plan §3 DAG 与 AGENTS.md 分层约束一致。Storage 不 import Host/Service/Redis；Host 不 import concrete PG store。正确。

---

## Findings

### M-001-未修复-中-DST/misfire 算法对 croniter 行为的假设需要 empirical 验证

- **位置**: plan §5.2 "DST/misfire算法"
- **问题类型**: 假设未验证 / 切片过粗
- **当前写法**: plan 声称 "croniter只生成 naive local wall candidates; 每个candidate通过ZoneInfo UTC round-trip分类"、"nonexistent local time跳过且继续找下一candidate"、"ambiguous local time固定选择 fold=0"
- **反例/失败场景**: croniter 的 DST 行为取决于其内部实现。如果 croniter 在 DST transition 时生成的 naive local time 不符合 plan 的 "nonexistent 跳过" 期望（例如 croniter 可能直接跳过不存在的时间或返回相邻有效时间），ScheduleService 的 DST 分类逻辑会产生与 plan 不同的行为。plan 的 `test_scheduler_dst_nonexistent_time_policy_is_exact` 和 `test_scheduler_dst_ambiguous_fold_enqueues_exactly_once` 命名测试会证明实现是否正确，但 plan §5.2 的算法描述本身可能与 croniter 实际行为不匹配。
- **为什么有问题**: plan 的 §5.2 算法假设 croniter 行为是 "生成 naive local wall candidates"，但 croniter 的实际 API 是 `croniter.get_next(datetime)` 返回 naive datetime。DST transition 时的行为（nonexistent time 返回什么、ambiguous time 返回哪个 fold）取决于 croniter 内部逻辑，plan 没有说明如何验证或收窄这个假设。
- **直接证据**: plan §5.2 "croniter只生成 naive local wall candidates"；§10 命名测试 `test_scheduler_dst_nonexistent_time_policy_is_exact`
- **影响**: 实施 Agent 可能实现与 croniter 实际行为不一致的 DST 分类逻辑；或发现 croniter 行为与 plan 假设冲突后需要重新设计 §5.2 算法
- **建议改法和验证点**: 在 §5.2 明确：(1) croniter naive datetime 的 DST 行为需在 Slice A/B 的 pure domain tests 中先 empirical 验证并记录实际行为；(2) 若 croniter 行为与 plan 假设不一致，ScheduleService 必须以 croniter 实际输出为输入、ZoneInfo round-trip 为分类逻辑，不假设 croniter 内部 DST 语义。
- **修复风险（低）**: 只是 plan 措辞澄清，不改架构
- **严重程度（中）**:

### M-002-未修复-中-Scheduler occurrence 并发写入的 CAS 精确语义未指定

- **位置**: plan §5.3 `ScheduleStoreProtocol.reserve_occurrence`、§7.4
- **问题类型**: 契约缺失 / 并发恢复风险
- **当前写法**: plan §5.3 声称 `reserve_occurrence` "单事务 FOR UPDATE schedule、验证active/version/current next_fire、插入occurrence并推进cursor；CAS失败返回closed conflict而非抛裸IntegrityError"；§7.4 声称 "两个scheduler可同时读due/pending，但unique+CAS+job idempotency只能产生同一job"
- **反例/失败场景**: plan 没有指定 `reserve_occurrence` 的 CAS conflict 返回的具体 closed type。§5.1 的 DTO 列表中有 `ScheduleOccurrenceReservation` 但没有对应的 conflict error type。§5.1 只定义了 `ScheduleVersionConflictError`，但这是 version CAS 的错误，不是 occurrence reservation 的 conflict。两个 scheduler 同时 reserve 同一 due schedule 时，CAS conflict 的返回值是 `ScheduleVersionConflictError` 还是新的 closed 类型？这会影响 ScheduleService 的重试逻辑。
- **为什么有问题**: 实施 Agent 需要明确知道 CAS conflict 返回什么类型才能写正确的重试/跳过逻辑。如果返回类型不明确，Agent 可能猜测或创建 ad-hoc 错误处理。
- **直接证据**: plan §5.3 "CAS失败返回closed conflict而非抛裸IntegrityError"；§5.1 DTO 列表无 occurrence-specific conflict type
- **影响**: 实施 Agent 可能创建额外的 error type 或错误处理路径，偏离 plan 的 closed type 设计
- **建议改法和验证点**: 在 §5.1 明确 `reserve_occurrence` CAS conflict 的返回类型——是复用 `ScheduleVersionConflictError`（返回 expected_version vs actual）还是新增 `ScheduleOccurrenceConflictError`。若复用前者，明确说明。
- **修复风险（低）**: 只是 plan 措辞澄清
- **严重程度（中）**:

### M-003-未修复-中-Execution request 的 worker_id 排除缺少明确安全理由

- **位置**: plan §6.1
- **问题类型**: 契约缺失
- **当前写法**: plan §6.1 声称 `JobExecutionRequest` "字段精确为 tenant_id, definition_id, job_id, attempt_id, attempt_number, descriptor, payload, deadline_at；它不含 JobLeaseHandle、fence、raw token或worker id"
- **反例/失败场景**: plan 没有解释为什么 `worker_id` 不在 execution request 中。worker_id 被写入 `job_attempts.worker_id`（Slice 2.1 DDL），handler 可能需要知道哪个 worker 在执行自己（例如日志、metrics、或 worker-specific 行为）。排除 worker_id 的安全理由是什么？如果只是 "handler 不需要"，这属于过度限制；如果是 "防止 handler 做 worker-specific side effect"，plan 应明确说明。
- **为什么有问题**: 实施 Agent 需要知道排除 worker_id 的设计意图，才能在 handler protocol 设计和测试断言中正确体现这个约束。
- **直接证据**: plan §6.1 "它不含 JobLeaseHandle、fence、raw token或worker id"
- **影响**: 实施 Agent 可能遗漏 worker_id 排除的测试断言（§10 `test_execution_handler_never_receives_lease_fence_raw_token_or_worker_id` 包含 worker_id），或在 handler protocol 中错误地添加 worker_id
- **建议改法和验证点**: 在 §6.1 补充一句安全理由："worker_id 排除是防止 handler 做 worker-specific side effect 或按 worker 身份做业务判断；worker 身份只用于 PG attempt 审计和 metrics，不进入业务逻辑。"
- **修复风险（低）**: 只是 plan 措辞补充
- **严重程度（中）**:

### L-001-未修复-低-INTEGRATION profile 的 ordinary startup 拒绝机制未指定精确实现路径

- **位置**: plan §4.1、§8
- **问题类型**: 契约缺失
- **当前写法**: plan §4.1 声称 "现有DEVELOPMENT的'显式in-memory且禁止production infra'契约不放宽"；§8 声称 "ordinary application startup拒绝该profile，只有platform worker|scheduler专用preparation可接收"
- **反例/失败场景**: 当前 `load_platform_settings` 在 `config.py:288` 默认构造 `PlatformDeploymentProfile.DEVELOPMENT`。如果用户设置 `DAYU_PLATFORM_DEPLOYMENT_PROFILE=integration`，`load_platform_settings` 会接受它。plan 没有指定 ordinary startup（`prepare_host_runtime_dependencies`）如何拒绝 INTEGRATION profile。是在 `load_platform_settings` 层拒绝？还是在 `prepare_host_runtime_dependencies` 层拒绝？还是两者都需要？
- **为什么有问题**: 实施 Agent 需要知道拒绝发生的确切位置，才能正确实现 fail-closed 行为。
- **直接证据**: plan §4.1 "ordinary application startup拒绝该profile"；`config.py:288` 默认 DEVELOPMENT
- **影响**: 实施 Agent 可能在错误的层实现拒绝，或遗漏拒绝路径
- **建议改法和验证点**: 在 §4.1 或 §8 明确：INTEGRATION profile 在 `load_platform_settings` 层接受（因为 CLI 需要），但在 `prepare_host_runtime_dependencies`（ordinary startup）层拒绝并抛 `PlatformSettingsError`；只有 `dayu-cli platform worker/scheduler` 的专用 preparation 函数才跳过该拒绝。
- **修复风险（低）**: 只是 plan 措辞澄清
- **严重程度（低）**:

### L-002-未修复-低-Plan §3 allowlist 中 `dayu/cli/arg_parsing.py` 和 `dayu/cli/main.py` 的修改范围未指定

- **位置**: plan §3 CLI owner
- **问题类型**: 范围漂移风险
- **当前写法**: plan §3 把 `dayu/cli/arg_parsing.py`、`dayu/cli/arguments.py`、`dayu/cli/command_names.py`、`dayu/cli/main.py` 列为 "唯一 platform {worker|scheduler} parser/lazy dispatch、typed fields、signal/exit/cleanup"
- **反例/失败场景**: 这些文件是共享 CLI 入口。`arg_parsing.py` 已有 1600+ 行。如果实施 Agent 在这些共享文件中添加大量 scheduler/worker 逻辑（而非在 `commands/platform.py` 中），可能导致 shared CLI 文件膨胀和回归风险。
- **为什么有问题**: plan 没有明确 `arg_parsing.py`/`main.py` 的修改范围——是只添加一行 import + subparser 注册？还是添加完整的 parsing logic？
- **直接证据**: plan §3 "唯一platform {worker|scheduler} parser/lazy dispatch"
- **影响**: 实施 Agent 可能在共享 CLI 文件中添加过多逻辑，增加回归风险
- **建议改法和验证点**: 在 §3 明确：`arg_parsing.py` 只添加 subparser 注册（一行 import + 一行 `register` 调用）；`main.py` 只添加 dispatch 路由；所有 parsing logic、signal handling、cleanup 都在 `commands/platform.py` 中。
- **修复风险（低）**: 只是 plan 措辞澄清
- **严重程度（低）**:

## Open Questions

- Plan §5.2 的 croniter DST 行为假设需要 empirical 验证（与 M-001 关联）。建议在 Slice A 的 pure domain tests 中先验证 croniter 实际行为，再确认 §5.2 算法是否需要调整。
- Plan §6.2 的 `HostRunCancellationProtocol` 是新增 Protocol 还是直接注入 `Host` 实例？plan 说 "注入窄 HostRunCancellationProtocol.cancel_run(run_id) -> RunRecord"，但 `Host.cancel_run` 已存在且签名匹配。是否需要新建 Protocol 还是直接用 `Host` 的结构类型满足？

## Residual Risk

- **croniter 行为不确定性**: DST/misfire 算法的正确性依赖 croniter 的实际 naive datetime 生成行为，这在 plan review 阶段无法静态验证。风险由 §10 命名测试承担——`test_scheduler_dst_nonexistent_time_policy_is_exact` 和 `test_scheduler_dst_ambiguous_fold_enqueues_exactly_once` 会在实施阶段证明或反驳 plan 假设。
- **Redis Docker fixture 复杂度**: plan §10 要求真实 Redis Docker fixture 使用 "随机owned container name、owner label、127.0.0.1随机host port"，这与 Phase 1 的 PG16 fixture 模式一致，但 Redis container 的 readiness 检查和 cleanup 比 PG 更复杂（需要 PubSub subscribe 验证）。风险由 §11 门禁 6/7 承担。
- **五 slice 实施复杂度**: plan §9 的 A-E 五个 slice 涉及纯契约、PG migration、Service orchestration、Redis async loop 和 CLI/startup，每个 slice 都有独立的 gate。实施 Agent 需要严格按 slice 顺序执行，不能跳过 gate。风险由 §9 的 "任何slice未通过自己的测试/static/coverage，不进入下一slice" 承担。
