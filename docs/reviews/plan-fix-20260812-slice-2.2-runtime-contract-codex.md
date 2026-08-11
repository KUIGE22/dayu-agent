# Slice 2.2 runtime contract 实现期计划修复

- **状态**：`CLOSED / DEEPSEEK + MIMO FINAL2 PASS / IMPLEMENTATION MAY RESUME`
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **触发点**：ScheduleService/Worker/Redis code-generation audit 触发目标计划 §12 STOP。
- **范围**：仅修改目标计划并新增本 artifact；实现草稿保持冻结、未测试、未提交。

## 1. 结论

原 accepted plan 在四个可达边界上不能由既有 schema/allowlist 唯一实现：

1. relocation 取得 distinct candidate 前耗尽scan limit时，lookback与scan-limit audit拥有相同 occurrence natural key；原文却要求同batch写两行，真实0004唯一键必使整批回滚。
2. pinned croniter 6.2.4 对部分五字段表达式返回`is_valid=True`，但首次`get_next`抛`CroniterBadDateError`；原文没有registration/runtime的closed disposition。
3. `AgentRunGovernanceResult`没有correlation/job/attempt identity；tenant-wide page含多个correlation时，Worker无法判断哪条结果可改变current attempt heartbeat。
4. Worker需要Redis read/protocol types，但这些types若与concrete adapter同模块，Worker import会在settings/profile validation前加载redis-py，破坏missing-package fail-fast顺序。

另有两项直接实现缺陷一并转为明确门禁：redis-py URL query会覆盖显式RESP2/decode/timeout kwargs；孤立Unicode surrogate会在canonical re-encode时抛异常而不是成为invalid hint。

因此当前实现继续冻结是必要的；不得以synthetic timestamp、捕获unique error、库存page位置、提前import Redis或宽松JSON parser绕过。

## 2. finding 映射与裁决

| ID | 证据 | 裁决 | 计划修复 |
| --- | --- | --- | --- |
| S22-RUNTIME-001 | `lookback_exceeded`与`candidate_scan_limit_exceeded`在distinct relocation candidate出现前都以persisted cursor为`scheduled_for`；0004唯一键不含reason | ACCEPTED | local scan-origin两态；provisional lookback与scan-limit相撞时只提交优先级更高的scan-limit audit；batch构造期拒重复scheduled_for；禁止schema/timestamp绕过 |
| S22-RUNTIME-002 | croniter 6.2.4：`0 0 31 2 *`为valid但`get_next`抛`CroniterBadDateError` | ACCEPTED | registration固定seed probe并在Store前拒绝；persisted runtime exhaustion固定invariant/nonzero/零mutation |
| S22-RUNTIME-003 | governance result只有action/code，无法关联current claim | ACCEPTED | result新增correlation/job/attempt UUID；Service按projection复制，Worker只消费匹配current job/attempt的状态变化 |
| S22-RUNTIME-004 | concrete Redis module是唯一`import redis` owner；Worker若为protocol import它会提前加载可选包 | ACCEPTED | pure Redis DTO/protocol/runtime state归`worker.py`；adapter单向import pure types；Worker禁止import adapter |
| S22-IMPL-001 | `Redis.from_url` query优先于kwargs；surrogate re-encode抛`UnicodeEncodeError` | ACCEPTED IMPLEMENTATION HARDENING | 既有fixed-wire/invalid-message合同的明确测试：query/fragment在client构造前拒绝，仅构造期配置错误固定收窄；surrogate/re-encode失败归INVALID_MESSAGE |

### 2.1 首轮纠错复审裁决

首轮 source reviews 为：

- `docs/reviews/plan-review-20260812-slice-2.2-runtime-corrective-deepseek.md`：`PASS / open H/M/L=0/0/3`；
- `docs/reviews/plan-review-20260812-slice-2.2-runtime-corrective-mimo.md`：`FAIL / open H/M/L=3/3/0`。

Controller逐项裁决：

| 来源 | 裁决 | 处理 |
| --- | --- | --- |
| DeepSeek L-1：global invariant缺显式测试 | ACCEPTED | 增加非current identity仍全局exit-1测试与STOP。 |
| DeepSeek L-2：governance gateway异常处置未定义 | ACCEPTED | 只允许closed `JobRepositoryFailureError`安全重试；其它未分类异常保留现场并非零停机，增加两条测试与STOP。 |
| DeepSeek L-3：runtime exhaustion测试入口不清 | ACCEPTED | 固定用真实Store直接准备immutable invalid/legacy definition；禁止mock或放宽registration，并拆分activation/due/scheduler exit-1测试。 |
| Controller M-1：S22-CTRL-009与allowlist/DAG未同步 | ACCEPTED | 补齐domain/Service/Worker/startup/test owners、精确修改点，并把DAG改为concrete adapter单向依赖Worker pure types。 |
| Controller M-2：governance cardinality/identity/action矩阵测试不足 | ACCEPTED | 增加page mismatch/duplicate、完整action矩阵与global invariant测试，并同步STOP。 |
| Controller M-3：cron两条只读路径与exit未分证 | ACCEPTED | 拆为activation no-set-state、due no-reserve与scheduler exit-1三条测试，并同步STOP。 |
| Controller L-1：Redis fragment与运行期意外异常未分证 | ACCEPTED | 增加fragment pre-construction与runtime TypeError/ValueError不得降级测试，并同步STOP。 |
| Closure M-1：governance重试引用未定义interval且无耗尽边界 | ACCEPTED | 不新增interval；沿既有poll/heartbeat cadence，新增strict `governance_failure_threshold=3`与env/snapshot，成功page重置counter，达到阈值exit 1。 |
| MiMo H-01/H-02/H-03、M-01/M-02/M-03 | REJECT AS IMPLEMENTATION-COMPLETENESS FINDINGS / WORDING HARDENING ACCEPTED IN PART | 本 gate 是实现冻结后的plan review；DTO、cron、Redis迁移和新增测试尚未落盘正是计划要解决的工作，不能以“当前代码未实现”判plan FAIL。target在§2/§3/§5/§6/§10已给closed目标、owner、异常、测试和STOP。为消除可生成性疑义，仍补充精确`__post_init__` error code、现有helper/touchpoint、受影响测试与当前未实施现场说明。 |

## 3. 新的 closed contract

### 3.1 Schedule audit 与 cron

- lookback audit先保存在Service局部provisional state；scan origin固定从`persisted_cursor`开始，仅在取得distinct valid relocation candidate时进入`distinct_relocated_cursor`；scan结束后才构造最终`ScheduleReservationBatch`。
- 若scan-limit audit与provisional lookback audit自然键相同，batch只含一条`candidate_scan_limit_exceeded` row；否则两条都保留。该规则完全由pure input决定，重启得到相同bytes。
- `ScheduleReservationBatch`构造期拒绝任意重复`scheduled_for`，unique conflict不得下沉到PostgreSQL。
- register以固定naive seed `2000-01-01 00:00:00`做一次candidate probe；无candidate抛固定`ScheduleInputError("schedule_cron_has_no_candidate")`且Store调用数为0。
- immutable persisted expression运行时若exhaust，抛固定`ScheduleInvariantError("schedule_cron_iteration_exhausted")`；activation可先只读`get`但不调用`set_state`，due可先只读`list_due`但不调用`reserve_occurrences`；不disable、不写audit。

### 3.2 Governance identity

`AgentRunGovernanceResult`字段精确为：

```text
correlation_id: UUID
job_id: UUID
attempt_id: UUID
action: AgentRunGovernanceAction
safe_error_code: SafeJobErrorCode | None
```

JobService只通过一个集中pure helper逐projection构造同序结果；组page前验证result/projection cardinality、三个identity与顺序逐项相等，且同页correlation/attempt identity不得重复。Worker只有在result的`job_id`和`attempt_id`同时匹配current claim时，才允许停止/恢复该attempt heartbeat；匹配current的`SEND_RETRY`继续同一lease，无关correlation仍完成其自身Host/PG治理但不能改变current handler/finalize。任一`INVARIANT_FAILURE`都使tenant runtime非零停止，不受current identity过滤。

`JobRepositoryFailureError`只沿既有poll/heartbeat governance cadence重试，不新增interval；Worker以process-local consecutive counter消费strict `settings.governance_failure_threshold`（默认3），成功page清零，达到阈值保留现场并exit 1。其它未分类异常立即exit 1；两条路径都不写false terminal。

### 3.3 Redis import/wire

- `worker.py`拥有pure read DTO/protocol/runtime state且不import redis-py或concrete adapter。
- `redis_wakeup.py`是唯一`import redis` owner，结构化满足Worker pure protocols和JobService publisher protocol。
- startup只在settings/profile验证后local-import concrete adapter；disabled/development与missing-package路径可先安全import Worker/CLI。
- URL必须无query/fragment；adapter固定RESP2、bytes、bounded timeout。非法provider配置与wire错误不携带URL/原始正文。
- decoder对surrogate或re-encode failure返回INVALID_MESSAGE，Worker继续相同PG poll路径。

## 4. 必需新增回归

- `test_nondefault_governance_failure_threshold_is_strict_and_enters_safe_startup_snapshot`
- `test_scan_limit_before_distinct_relocation_candidate_coalesces_colliding_audits_to_one_scan_limit_row`
- `test_scan_limit_after_distinct_relocation_candidate_persists_two_distinct_audits`
- `test_schedule_reservation_batch_rejects_duplicate_scheduled_for_before_postgres`
- `test_croniter_valid_but_candidate_empty_is_rejected_before_store`
- `test_persisted_cron_iteration_exhaustion_stops_without_schedule_mutation`
- `test_activation_cron_iteration_exhaustion_reads_only_and_never_calls_set_state`
- `test_due_cron_iteration_exhaustion_reads_only_and_never_calls_reserve_occurrences`
- `test_scheduler_cron_iteration_exhaustion_returns_exit_one_without_mutation`
- `test_governance_result_identity_is_copied_from_each_projection_in_page_order`
- `test_worker_matches_governance_identity_before_changing_current_attempt_heartbeat`
- `test_governance_page_rejects_cardinality_identity_order_or_duplicate_mismatch`
- `test_governance_action_matrix_keeps_send_retry_stops_missing_or_terminal_and_ignores_unrelated_results`
- `test_governance_invariant_failure_stops_runtime_regardless_of_current_attempt_identity`
- `test_governance_repository_failure_retries_until_configured_threshold_then_stops_without_false_terminal`
- `test_governance_success_resets_consecutive_repository_failure_count`
- `test_unclassified_governance_exception_stops_runtime_without_false_terminal`
- `test_worker_pure_protocol_module_imports_without_redis_package`
- `test_redis_adapter_is_the_only_import_redis_owner`
- `test_invalid_platform_settings_never_import_concrete_redis_adapter`
- `test_redis_url_query_cannot_override_resp2_bytes_or_bounded_timeouts`
- `test_redis_url_fragment_is_rejected_before_client_construction`
- `test_runtime_redis_type_or_value_error_propagates_without_degraded_transition`
- `test_lone_unicode_surrogate_hint_is_invalid_and_worker_continues_pg_polling`

## 5. 实施恢复 gate

只有以下条件全部满足，Controller才可恢复当前冻结草稿：

1. DeepSeek corrective plan review PASS，open H/M/L=0/0/0；
2. MiMo corrective plan review PASS，open H/M/L=0/0/0；
3. Controller记录两路review identity与accepted plan semantic snapshot；
4. 仅把plan/fix/review/acceptance docs纳入新的本地accepted plan-fix commit，不混入任何实现WIP；
5. 随后先修改pure governance identity和Redis type owner，再恢复ScheduleService测试，最后才实现Worker/Scheduler/startup。

## 6. 当前现场

- ScheduleService两个文件是未验证草稿，未运行focused/static，不可视为实现完成。
- Worker、Scheduler与special platform startup/CLI尚未实现；pure Redis types迁移属于恢复后的第一批实现工作，不是本plan review的前置代码事实。
- JobService、ProcessIntake与Redis adapter已有局部门禁证据，但会受本勘误影响，必须在恢复后重新验证。
- 未运行live Redis/provider/model/broker/交易；未push、未创建PR。

## 7. 最终闭合

- 首轮 DeepSeek review 为`PASS / open H/M/L=0/0/3`，首轮 MiMo review 为`FAIL / open H/M/L=3/3/0`；全部观察已在§2.1逐项裁决，真实文档缺口均接受并修复，实现尚未落盘的项目不再误算为plan finding。
- 中间 MiMo closure review `plan-review-20260812-slice-2.2-runtime-corrective-final-mimo.md` 对target `ead24a7e...`与fix `61b41b4e...`给出`PASS / open0`；随后Controller因独立closure审计发现governance重试无阈值，继续修订而未接受该中间快照。
- 最终 DeepSeek `plan-review-20260812-slice-2.2-runtime-corrective-final2-deepseek.md` 与 MiMo `plan-review-20260812-072323-slice-2.2-runtime-corrective-final2-mimo.md` 均为`PASS / open H/M/L=0/0/0`。
- 最终双审锁定target语义 SHA-256 `6287a159552ca49edeb08b276e8480b01264367f32f34ac30c7108305de229a0` 与fix SHA-256 `21a3eb1e3260b66107e31b14e594f9be4bd54abc9e7849a62413dfeff3a9ef76`；本节及target header之后只增加closure metadata，不改变已审合同语义。
- Controller acceptance 记录在`docs/reviews/plan-acceptance-20260812-slice-2.2-runtime-contract-codex.md`。实现可按§5 gate和目标计划§9恢复，但仍不得live/push/PR或跳过最终code review。
