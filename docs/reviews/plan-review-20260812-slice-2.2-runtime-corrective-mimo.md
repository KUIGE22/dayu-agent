# Slice 2.2 Runtime Contract Corrective Plan Review (Independent)

- **状态**: `REVIEW COMPLETE`
- **Review 类型**: 独立纠错复审（Independent Corrective Re-review）
- **target**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
  - **SHA-256**: `ec2c97321b8497bbb55505c1e8aeaa05e5f51e1420f45f501a6409aaf5a410da`
- **fix**: `docs/reviews/plan-fix-20260812-slice-2.2-runtime-contract-codex.md`
  - **SHA-256**: `16cb71646dda027b567a8b2579ce52d0ca8f75f9f7a99e7a6c39bf35fe6bb85e`
- **重点**: S22-CTRL-009 四项勘误及其对全计划的回归
- **Review scope**: plan 与 fix 文档的精确性、可生成性、测试覆盖、STOP 覆盖、DAG 完整性、反例验证

## 1. 审查方法

1. 验证 target 与 fix 的 SHA-256 签名匹配用户指定值。
2. 以 S22-CTRL-009 四项为审计锚点，逐项比对 plan/fix 文档与当前 code baseline 的实际状态。
3. 对每项做 adversarial counter-example：文档声称的约束是否在现有代码中已实现、是否可由 implementation agent 唯一生成。
4. 检查 regression：fix 对四项的修改是否破坏 plan 其他章节的不变量。
5. 检查 STOP conditions 是否覆盖 fix 新增的边界。
6. 检查 allowlist/DAG 是否与 fix 的修改一致。
7. 检查测试名称是否精确存在于 codebase。

## 2. Assumptions Tested

| # | Assumption | Verdict |
|---|---|---|
| A1 | fix 文档的 12 项回归测试名称精确存在于 codebase | **FALSE** — 全部 12 项不存在 |
| A2 | `AgentRunGovernanceResult` 已包含 `correlation_id/job_id/attempt_id` | **FALSE** — 只有 `action` + `safe_error_code` |
| A3 | `ScheduleReservationBatch.__post_init__` 已校验 pairwise distinct `scheduled_for` | **FALSE** — 无此校验 |
| A4 | `_validate_croniter_expression` 已含固定 seed `2000-01-01 00:00:00` 探测 | **FALSE** — 只调用 `croniter.is_valid()` |
| A5 | fix 文档的 SHA 签名与用户指定值匹配 | **TRUE** |
| A6 | plan DAG 中 `dayu/host/` 不导入 `dayu/services/` | **TRUE** |
| A7 | `set_state` 使用 MATERIALIZED CTE + `clock_timestamp()` | **TRUE** |
| A8 | `begin_materialization` PENDING+committed_replay 是 invariant | **TRUE** |
| A9 | 零 mutation on croniter failure 由控制流保证 | **TRUE** |
| A10 | `RedisWakeupAdapter.from_url` 拒绝 URL query/fragment | **FALSE** — 无此验证 |
| A11 | `worker.py`/`scheduler.py` 已存在 | **FALSE** — 不存在 |
| A12 | `_prepare_queue_admission` 已存在 | **FALSE** — 不存在 |

## 3. Findings

### 编号-未修复-高-S22-CTRL-009-01: AgentRunGovernanceResult 缺失三 identity 字段

- **位置**: `dayu/investment/domain/jobs.py:1878-1937`; fix §3.2
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: `AgentRunGovernanceResult` 精确字段为 `action: AgentRunGovernanceAction` 和 `safe_error_code: SafeJobErrorCode | None`。fix 要求新增 `correlation_id: UUID`, `job_id: UUID`, `attempt_id: UUID` 并由同一 projection 逐字段复制。
- **反例/失败场景**: 当前 Worker 无法将 governance result 关联到 current claim 的 `job_id/attempt_id`。多 correlation page 中，Worker 只能按位置猜 identity，任意 correlation 的 `SEND_RETRY` 都可能错误地继续无关 attempt 的 heartbeat。`INVARIANT_FAILURE` 也无法触发 tenant-wide 停机。
- **为什么有问题**: fix §3.2 精确指定了新字段和集中构造规则，但 code baseline 中该 class 仍是旧设计。implementation agent 需要：(1) 修改 `AgentRunGovernanceResult` 新增三个 UUID 字段，(2) 修改 `_govern_projection()` 和 `_reconcile_governance_observation()` 逐 projection 复制，(3) 添加 page cardinality/identity/order 验证，(4) 更新所有现有测试的构造调用。fix 文档描述了目标但未在 plan 中明确哪些现有代码点需要修改。
- **直接证据**: `dayu/investment/domain/jobs.py:1878-1937` — class 只有 `action`/`safe_error_code`；`dayu/services/job_service.py:788-914` — `_govern_projection()` 构造 `AgentRunGovernanceResult(action=..., safe_error_code=...)` 不含 identity。
- **影响**: 实施 Agent 无法生成正确代码 — domain DTO 缺字段导致所有下游构造/验证代码必须同步修改，但 fix 未列出具体修改点。
- **建议改法和验证点**:
  1. fix 应明确列出 `AgentRunGovernanceResult.__post_init__` 新增的 identity 校验规则。
  2. fix 应列出 `_govern_projection()` 和 `_reconcile_governance_observation()` 的精确修改点。
  3. fix 应列出 page 验证（cardinality/identity/order）的新增位置。
  4. fix 应列出所有需要更新 identity 的现有测试文件和行号。
- **修复风险（中）**: DTO 变更影响面广但方向明确。
- **严重程度（高）**: 阻断 Worker 正确消费 governance result。

---

### 编号-未修复-高-S22-CTRL-009-02: ScheduleReservationBatch 缺失 pairwise distinct scheduled_for 校验

- **位置**: `dayu/investment/domain/schedules.py:1012-1069`; fix §3.1
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: `__post_init__` 校验 batch size（1-3）、版本/cursor 非法、ACTIVE cursor 推进、scan-limit audit 唯一性，但**不校验 reservations 中 `scheduled_for` 的 pairwise distinctness**。fix 要求构造期拒绝重复。
- **反例/失败场景**: 当 lookback relocation 前耗尽 scan limit 时，lookback provisional audit 和 scan-limit audit 以相同 `scheduled_for`（persisted cursor）进入 batch。0004 唯一键 `(tenant_id, schedule_id, schedule_version, scheduled_for)` 使 INSERT 失败，但错误是裸 `IntegrityError` 被包裹为 `ScheduleRepositoryError("schedule_repository_reserve")`，不是 clean domain error。Service 层无法区分"重复scheduled_for"和"并发竞争"。
- **为什么有问题**: plan §5.1 明确要求 "所有reservation的`scheduled_for`必须pairwise distinct，重复值构造期抛`ScheduleInvariantError`"，但代码中无此校验。fix §3.1 描述了目标但未在 DTO 代码中实现。
- **直接证据**: `dayu/investment/domain/schedules.py:1036-1040` — `__post_init__` 遍历 reservations 但只检查类型，不检查 scheduled_for 重复；`dayu/investment/storage/migrations/versions/0004_durable_schedules.py:250-251` — PG UNIQUE 约束存在但错误处理是 generic `ScheduleRepositoryError`。
- **影响**: 实施 Agent 可能在不知情的情况下生成依赖 PG error 的代码，违反 plan 的 "禁止INSERT error决定业务语义" 约束。
- **建议改法和验证点**:
  1. fix 应明确指出在 `ScheduleReservationBatch.__post_init__` 新增 pairwise distinct check。
  2. fix 应指定校验时机（在所有 type/size/state 校验之后）和异常类型（`ScheduleInvariantError("batch_duplicate_scheduled_for")`）。
  3. fix 应列出对 `test_scan_limit_before_distinct_relocation_candidate_coalesces_colliding_audits_to_one_scan_limit_row` 的影响。
- **修复风险（低）**: 纯 additive 校验。
- **严重程度（高）**: 违反 plan §5.1 不变量。

---

### 编号-未修复-高-S22-CTRL-009-03: croniter 缺失固定 seed 探测和错误消息

- **位置**: `dayu/services/schedule_service.py:128-146`; fix §3.1
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: `_validate_croniter_expression` 只调用 `croniter.is_valid(expression)`。fix 要求以固定 naive seed `2000-01-01 00:00:00` 执行一次 `get_next(datetime)` probe，无 candidate 时抛 `ScheduleInputError("schedule_cron_has_no_candidate")`。runtime exhaustion 抛 `ScheduleInvariantError("schedule_cron_iteration_exhausted")`。
- **反例/失败场景**: croniter 6.2.4 对 `0 0 31 2 *` 返回 `is_valid=True`，但 `get_next` 抛 `CroniterBadDateError`。当前代码不会在 registration 时捕获此情况，导致无效 cron 表达式被持久化。运行时遇到时被映射为通用 `ScheduleInvariantError` 而非精确的 exhaustion 消息。
- **为什么有问题**: fix §3.1 精确指定了固定 seed probe 和两个 closed error code，但 code baseline 中两者均未实现。当前错误消息 `cron_expression_invalid`（line 146）与 fix 要求的 `schedule_cron_has_no_candidate` 不匹配。
- **直接证据**: `dayu/services/schedule_service.py:142-146` — `valid = croniter.is_valid(expression)` 后直接 `raise ScheduleInputError("cron_expression_invalid")`；无 `get_next` probe；`grep` 确认 `schedule_cron_has_no_candidate` 和 `schedule_cron_iteration_exhausted` 在全仓不存在。
- **影响**: 实施 Agent 无法生成正确代码 — 需要新增 probe 逻辑和两个新 error code，但 fix 未在 plan 中更新 §5.1 的 error 枚举列表。
- **建议改法和验证点**:
  1. fix 应在 §5.1 `ScheduleInputError` 消息列表中新增 `"schedule_cron_has_no_candidate"`。
  2. fix 应在 §5.1 `ScheduleInvariantError` 消息列表中新增 `"schedule_cron_iteration_exhausted"`。
  3. fix 应明确 `_validate_croniter_expression` 的新实现：`croniter(expression, datetime(2000,1,1)).get_next(datetime)` + `CroniterBadDateError` 捕获。
  4. fix 应列出 activation/due 路径中 `CroniterBadDateError` -> `ScheduleInvariantError` 的映射点。
- **修复风险（中）**: 需要修改 Service 层核心函数。
- **严重程度（高）**: 违反 plan §5.2 和 S22-CTRL-009 item 2。

---

### 编号-未修复-中-Redis URL query/fragment 未在 admission 前拒绝

- **位置**: `dayu/host/redis_wakeup.py:495-508`; fix §3.3; plan §4.2; S22-IMPL-001
- **问题类型**: 契约缺失 / 实施门禁未实现
- **当前写法**: `RedisWakeupAdapter.from_url` 只校验 URL 非空无空白。fix 要求 URL 必须无 query/fragment，任一 query 在 `Redis.from_url` 前拒绝。
- **反例/失败场景**: Redis URL `redis://host:6379?protocol=3&decode_responses=true` 会被 `Redis.from_url` 解析，query 参数覆盖显式 `protocol=2` 和 `decode_responses=False` kwargs，破坏 RESP2/bytes contract。这正是 fix §2 S22-IMPL-001 描述的场景。
- **为什么有问题**: fix 明确将此列为 "implementation hardening" 并在 §3.3 中描述了目标，但 code baseline 中 `from_url` 无 URL 结构验证。
- **直接证据**: `dayu/host/redis_wakeup.py:495-496` — 只有 `type(redis_url) is not str or not redis_url or redis_url != redis_url.strip()` 校验；无 `urlparse` 或 query/fragment 检查。
- **影响**: implementation agent 可能遗漏此门禁，导致真实 Redis wire 测试失败。
- **建议改法和验证点**:
  1. fix 应在 `from_url` 校验中新增 `urlparse(redis_url).query` 和 `.fragment` 的非空拒绝。
  2. fix 应指定异常类型和消息（`ValueError("redis_url must not contain query or fragment")`）。
  3. fix 应列出 `test_redis_url_query_cannot_override_resp2_bytes_or_bounded_timeouts` 的精确测试场景。
- **修复风险（低）**: 纯 additive 校验。
- **严重程度（中）**: plan §4.2 的 fixed-wire contract 要求此门禁。

---

### 编号-未修复-中-worker.py 中 pure Redis types 位置错误

- **位置**: fix §3.3; plan §3 allowlist; S22-CTRL-009 item 4
- **问题类型**: 架构边界 / 不可直接实施
- **当前写法**: `RedisWakeupReadAction`, `RedisWakeupHint`, `RedisWakeupRead`, `RedisWakeupSubscriberProtocol`, `RedisWakeupSubscriberFactoryProtocol`, `RedisWakeupClientProtocol` 全部在 `redis_wakeup.py`（line 36-210）。fix 要求这些 pure types 归 `worker.py` 所有，`redis_wakeup.py` 只单向 import。
- **反例/失败场景**: `worker.py` 尚不存在（line 不存在）。当前设计下，Worker 创建后如果 import `redis_wakeup` 来获取 pure types，会同时加载 `import redis`（line 18），破坏 missing-package fail-fast 顺序。
- **为什么有问题**: fix §3.3 精确描述了目标：`worker.py` 拥有 pure types，`redis_wakeup.py` 只 import pure types + `import redis`。但当前 code baseline 中 pure types 与 concrete adapter 同模块。plan §3 allowlist 正确标注了 `worker.py`（新）拥有 pure types。
- **直接证据**: `dayu/host/redis_wakeup.py:18` — `import redis`；`dayu/host/redis_wakeup.py:36-210` — pure DTO/protocol 与 `import redis` 同模块。`dayu/host/worker.py` 不存在。
- **影响**: implementation agent 必须：(1) 创建 `worker.py`，(2) 将 pure types 从 `redis_wakeup.py` 移至 `worker.py`，(3) 修改 `redis_wakeup.py` 为单向 import。fix 未列出此重构步骤。
- **建议改法和验证点**:
  1. fix 应明确列出 pure types 的迁移路径（从 `redis_wakeup.py` 到 `worker.py`）。
  2. fix 应列出 `redis_wakeup.py` 的 import 修改。
  3. fix 应列出 `test_worker_pure_protocol_module_imports_without_redis_package` 的精确验证方式。
- **修复风险（中）**: 跨模块重构，需更新所有引用点。
- **严重程度（中）**: plan §3 DAG 要求此分离。

---

### 编号-未修复-中-12 项回归测试全部不存在

- **位置**: fix §4; plan §10
- **问题类型**: 测试缺口
- **当前写法**: fix §4 列出 12 项 "必需新增回归" 测试名称。`grep` 确认**全部 12 项在 codebase 中不存在**。
- **反例/失败场景**: fix 文档声称这些测试是 "必需新增" 的回归，但作为 plan review artifact，它们应被视为 plan 的一部分。plan §10 已包含同名测试（line 705-707, 695-696, 761-762, 792-794, 791, 790），但 fix §4 的列表与 plan §10 的列表有重叠但不完全一致。implementation agent 需要同时参考两处。
- **为什么有问题**: fix 的 "必需新增回归" 与 plan §10 的 "必需命名测试" 是同一批测试的两个表述。fix 应明确引用 plan §10 而不是重复列出（可能导致不一致）。
- **直接证据**: fix §4 列出 12 项名称；plan §10 line 705-707, 695-696, 761-762, 790-794 包含同名测试。`grep` 确认 codebase 中无任何匹配。
- **影响**: implementation agent 可能只看 fix §4 而遗漏 plan §10 的完整测试列表。
- **建议改法和验证点**:
  1. fix §4 应改为引用 "plan §10 中与 S22-CTRL-009 相关的全部测试名称"，而不是重复列出。
  2. 或者 fix §4 的列表应与 plan §10 完全一致。
- **修复风险（低）**: 文档一致性。
- **严重程度（中）**: 可能导致 implementation agent 遗漏测试。

---

### 编号-未修复-中-worker.py/scheduler.py/_prepare_queue_admission 不存在

- **位置**: plan §3 allowlist; plan §7; plan §8
- **问题类型**: 范围确认
- **当前写法**: plan 标注 `worker.py`（新）、`scheduler.py`（新）、`_prepare_queue_admission`（新增函数）为 Slice 2.2 交付物。三者在当前 codebase 中均不存在。
- **反例/失败场景**: 这是预期状态 — plan 的 implementation slices 明确将 Worker/Scheduler/Startup 放在 Slice D/E。但 fix 文档的 "当前现场" (§6) 只提到 "ScheduleService两个文件是未验证草稿"，未提及 Worker/Scheduler/Startup 完全不存在。
- **为什么有问题**: fix §6 的 "当前现场" 描述不完整。读者可能误以为只有 ScheduleService 草稿需要验证，而不知道 Worker/Scheduler/Startup 完全未开始。
- **直接证据**: `ls dayu/host/worker.py` — 文件不存在；`ls dayu/host/scheduler.py` — 文件不存在；`grep _prepare_queue_admission dayu/services/startup_preparation.py` — 无匹配。
- **影响**: implementation agent 可能低估工作量。
- **建议改法和验证点**:
  1. fix §6 应补充：Worker/Scheduler/Startup preparation 尚未开始，属于 Slice D/E 范围。
- **修复风险（低）**: 文档完整性。
- **严重程度（中）**: 可能误导实施优先级。

---

## 4. Positive Verifications (验证通过)

以下项经代码事实验证，plan/fix 描述与 code baseline 一致：

| # | 验证项 | 证据 |
|---|---|---|
| P1 | `set_state` 使用 MATERIALIZED CTE + `clock_timestamp()` | `postgres_schedules.py:860-861` — `WITH observed AS MATERIALIZED (SELECT clock_timestamp() AS database_now)` |
| P2 | `get` 返回 `ScheduleObservation(definition, database_now)` from PG clock | `postgres_schedules.py:1166-1180` — 同一 SQL 获取 definition + clock |
| P3 | `begin_materialization` PENDING+committed_replay 是 invariant | `postgres_schedules.py:1739-1744` — 抛 `ScheduleInvariantError` |
| P4 | `_govern_projection` 是集中 pure helper | `job_service.py:788-914` — 所有 result 由该函数构造 |
| P5 | `AgentRunGovernanceAction` 有全部 9 个值 | `domain/jobs.py:1866-1874` — 9 个 enum 成员 |
| P6 | 零 mutation on croniter failure 由控制流保证 | `schedule_service.py:727-731` — probe 在 Store call 之前 |
| P7 | DAG 正确：`dayu/host/` 不导入 `dayu.services/` | grep 确认零匹配 |
| P8 | lone surrogate 通过 `UnicodeDecodeError` -> `INVALID_MESSAGE` 处理 | `redis_wakeup.py:655,661` — 捕获后返回 None -> `_invalid_read()` |
| P9 | `_encode_canonical` 的 `ValueError` 被外层 try/except 捕获 | `redis_wakeup.py:656-661` — try 包含 `json.dumps` 和 `_encode_canonical` 调用 |
| P10 | `ScheduleVersionConflictError` 在 version 不匹配时正确抛出 | `postgres_schedules.py:1277,1279,909,981` |

## 5. STOP Condition Coverage

对照 plan §12 STOP conditions 与 fix 新增约束：

| STOP 条目 | 覆盖 fix 项 | 状态 |
|---|---|---|
| "lookback/scan-limit同identity时同时INSERT并依赖unique error回滚" | S22-CTRL-009-01 | **覆盖** — plan line 837 |
| "governance result缺correlation/job/attempt identity" | S22-CTRL-009-03 | **覆盖** — plan line 846 |
| "Redis URL query/fragment可覆盖RESP2/bytes/timeout" | S22-IMPL-001 | **覆盖** — plan line 850 |
| "register接受croniter-valid但无candidate的表达式" | S22-CTRL-009-02 | **覆盖** — plan line 858 |
| "孤立surrogate穿透为异常" | S22-IMPL-001 | **覆盖** — plan line 850 |
| "Worker/CLI/startup在settings验证前import concrete redis_wakeup/redis-py" | S22-CTRL-009-04 | **覆盖** — plan line 850 |

**结论**: plan §12 STOP conditions 已充分覆盖 fix 的所有新增约束。

## 6. DAG / Allowlist Consistency

- plan §3 allowlist 精确标注 `worker.py`（新）拥有 pure Redis types，`redis_wakeup.py` 拥有 concrete adapter。
- plan §3 DAG 正确：`Host-local WorkerJobGatewayProtocol/SchedulerGatewayProtocol` + pure domain -> `RedisWakeupProtocol`；`startup` 注入 structurally compatible services。
- plan §3 禁止 re-export、compat wrapper、lazy type escape、`Any`、`object`、`cast`、`type: ignore`、`getattr`、`hasattr`。
- fix §3.3 的 Redis import 边界描述与 plan §3 DAG 一致。
- **无矛盾**。

## 7. 可生成性评估

**fix 文档对 implementation agent 的可生成性不足**：

1. **AgentRunGovernanceResult**: fix 描述了目标字段但未列出需要修改的**所有现有代码点**（`_govern_projection`, `_reconcile_governance_observation`, `__post_init__` 校验, 所有测试中的构造调用）。
2. **ScheduleReservationBatch**: fix 描述了目标但未在 plan 中更新 §5.1 的 DTO 规格（pairwise distinct check 的具体位置和异常类型）。
3. **croniter probe**: fix 描述了目标但未在 plan 中更新 §5.1 的 error 枚举列表（新增 `schedule_cron_has_no_candidate` 和 `schedule_cron_iteration_exhausted`）。
4. **Redis URL**: fix 描述了目标但未在 plan 中更新 §4.2 的 wire contract（新增 URL 结构验证要求）。
5. **Pure Redis types**: fix 描述了目标但未在 plan 中明确 pure types 的迁移步骤。

**fix 更像是审计发现的总结，而不是可以被 implementation agent 直接消费的 plan amendment**。它识别了 4+2 个 gap 并描述了目标状态，但未将这些目标状态翻译为 plan 的精确章节更新。

## 8. Open Questions

1. fix 的 "实施恢复 gate" (§5) 要求 DeepSeek + MiMo corrective plan review 均 PASS。本 review 为 MiMo 独立纠错复审，发现 fix 本身存在可生成性不足的问题。Controller 是否需要先要求 fix 作者补充 implementation-level 细节，再进入双路 code review？
2. fix §3.3 的 Redis import 边界要求 pure types 在 `worker.py`。但 `worker.py` 尚不存在且是 Slice D 的交付物。fix 是否应在 "实施恢复 gate" 中明确 Slice D 的 pure types 迁移是第一步？

## 9. Residual Risks

| Risk | 跟踪建议 |
|---|---|
| fix 可生成性不足，implementation agent 可能遗漏修改点 | Controller 在恢复实施前要求 fix 补充 code-level 修改清单 |
| 12 项回归测试与 plan §10 重复但不完全一致 | 实施时以 plan §10 为准，fix §4 作为补充 |
| pure Redis types 迁移涉及跨模块重构 | Slice D 第一步执行，以 `test_worker_pure_protocol_module_imports_without_redis_package` 验证 |
| `_encode_canonical` 的 ValueError 路径可能在 Python 3.12+ 行为变化 | 以 `test_lone_unicode_surrogate_hint_is_invalid_and_worker_continues_pg_polling` 覆盖 |

## 10. Final Conclusion

**FAIL**

open H=3 / M=3 / L=0

**High findings**:
- H-01: `AgentRunGovernanceResult` 缺失 `correlation_id/job_id/attempt_id` — 阻断 Worker 正确消费 governance result
- H-02: `ScheduleReservationBatch` 缺失 pairwise distinct `scheduled_for` — 违反 plan §5.1 不变量
- H-03: croniter 缺失固定 seed 探测和 closed error code — 违反 plan §5.2 和 S22-CTRL-009 item 2

**Medium findings**:
- M-01: Redis URL query/fragment 未在 admission 前拒绝 — plan §4.2 wire contract 未实现
- M-02: pure Redis types 位置错误 — plan §3 DAG 要求的分离未实现
- M-03: 12 项回归测试全部不存在 — plan §10 测试覆盖缺口

**根因**: fix 文档识别了正确的 gap 并描述了目标状态，但未将目标状态翻译为 plan 的精确章节更新（DTO 规格、error 枚举、wire contract、代码修改清单），导致可生成性不足。建议 Controller 在恢复实施前要求 fix 补充 implementation-level 细节。

**两份 SHA**:
- target: `ec2c97321b8497bbb55505c1e8aeaa05e5f51e1420f45f501a6409aaf5a410da`
- fix: `16cb71646dda027b567a8b2579ce52d0ca8f75f9f7a99e7a6c39bf35fe6bb85e`
