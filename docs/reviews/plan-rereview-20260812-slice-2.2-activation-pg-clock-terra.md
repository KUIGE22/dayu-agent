# Slice 2.2 activation / availability 计划勘误独立对抗复审（Terra）

- **复审时间**：2026-08-12 04:34:49 CST
- **结论**：`FAIL`
- **Open H/M/L**：`0 / 1 / 1`
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **目标计划 SHA-256（已核验）**：`0706e9b3fed8dd1f55eafe2fae8d8556f129c25470b4e0d07a0c1fedb918dfe5`
- **计划勘误**：`docs/reviews/plan-fix-20260812-slice-2.2-activation-pg-clock-codex.md`
- **计划勘误 SHA-256（本次读取时）**：`82564ef192ff3b903d79a9e5db029896e22cd08e4fda9f0e098e64c602e8e580`
- **accepted baseline**：`2dcba107b20730a6ab40483f9b8a04c9320f7602`
- **复审边界**：已完整读取根 `AGENTS.md`、`planreview` 技能、目标计划和计划勘误；只读核对冻结 WIP 的 `domain/schedules.py`、`storage/protocols.py`、`postgres_schedules.py`、`0004` migration 与相关 domain tests。未运行实现、测试、live/network/provider/broker 或交易操作；未修改目标计划、勘误、生产代码、测试、依赖或 README。

## 1. 结论摘要

`S22-CTRL-008` 已把此前不可实施的 activation API、PENDING availability point-read/admission 边与 disabled audit cursor 语义补成可表达的闭合契约；冻结 WIP 的未完成实现不计为本次 finding。不过，计划仍没有把“candidate 在 fresh PG clock 后仍 future”的判断与最终 ACTIVE 写入绑定到同一个数据库线性化点。分钟边界可在 Python/两条 SQL statement 之间穿越，写入已过期的 active cursor，直接违反勘误要求的“首个严格 future cursor”。因此尚不可解除 implementation pause。

## 2. 已复证的闭合项

| 审核面 | 结论 | 直接证据 |
| --- | --- | --- |
| 两阶段 observation → Service cron candidate → Store CAS 的分层 | 除本报告 M finding 外闭合 | `S22-CTRL-008` 第 1–2 点（target:115–116）让 Store 返回同 tenant transaction 的 `ScheduleObservation`，只由 ScheduleService 调用唯一 cron helper；Store 接收 candidate，禁止 callback、跨层事务和 Storage croniter（target:283–325）。 |
| closed DTO 与零 mutation | 闭合 | `ScheduleStateTransitionAction` 精确封闭为 `applied/unchanged/clock_stale/unavailable_disabled`，`ScheduleStateTransitionResult` 为 action + observation；`clock_stale` 和 `unchanged` 均要求零 mutation（target:233–245、255）。 |
| PENDING availability、MATERIALIZING replay、disable/begin race | 闭合 | `get_occurrence` 是 availability 前唯一 point-read，closed admission 精确区分 `pending_available/pending_unavailable/committed_replay`（target:283–320）；Store 实际持久 state 优先、固定 schedule → occurrence 锁序，MATERIALIZING 不可被 stale unavailable 撤销（target:328–333、446–448、509–520）。相应命名测试已列出（target:665–668）。 |
| disabled draft NULL / retained audit cursor / active non-NULL | 闭合 | DTO 明定 disabled draft 可为 `None`、曾 active 后 disabled 保留 cursor（target:242）；DDL 合同要求 active non-NULL、disabled 可以保留（target:276–281），`list_due` 只处理 active（target:324），并有 PG16 与 audit-cursor 命名测试（target:660–661）。 |
| Service / JobService / Store owner 与 DAG | 闭合 | Store surface 不泄漏 session/callback，ScheduleService 才拥有 availability orchestration；registries append-only，availability 不落 PG/Redis/cache（target:283–325、404–448）。`STOP` 同时禁止 Storage croniter、callback/session 泄漏、第二 registry truth 与 begin-before-availability（target:767–768）。 |
| 冻结 WIP 的定位 | 不构成 finding | 勘误已把现有 ACTIVE invariant、disabled 清 cursor 与旧 DDL/测试明确标为冻结中间态（target:121；plan-fix §5）。本复审只将其当作计划必须修正的事实基线，而不是把未恢复实施本身误报为计划缺陷。 |

## 3. Findings

### TERRA-S22-APC-001-未修复-[中]-ACTIVE cursor 的 fresh-clock 判断未与最终写入原子线性化

- **位置**：`S22-CTRL-008` 第 2 点（target:115–116）；`ScheduleStoreProtocol.set_state` 的 ACTIVE 规则（target:283–325）；分钟边界复审门槛（plan-fix:51–55）。
- **问题类型**：并发恢复风险 / 契约缺失 / 测试缺口。
- **当前写法**：计划要求 Store 取得 fresh PG clock，若 candidate 不再 future 则 `clock_stale` 零 mutation；仍 future 时一次 `UPDATE` 写 active、cursor、version。
- **反例/失败场景**：Store 可以按当前文字合法实现成：在行锁内执行 `SELECT clock_timestamp()`，由 Python 比较 `candidate > database_now`，随后另发一条无时间谓词的 `UPDATE`。例如 candidate 为 `12:01:00Z`，前一 statement 在 `12:00:59.9999Z` 判为 future，而 `UPDATE` 在 `12:01:00Z` 后执行；row 仍会变为 ACTIVE 并持久化已过期 cursor。版本和 state CAS 都正确，因而现有并发赢家测试不会发现此时间竞态。
- **为什么有问题**：目标合同承诺“首个严格 future cursor”，计划勘误更要求分钟边界不得写入已过期 cursor。独立 precheck 无法证明写入线性化点仍满足该不变量；实现 Agent 会被迫自行选择 SQL 原子性，计划不是 code-generation-ready。
- **直接证据**：目标计划仅写“读取 fresh PG clock”后“candidate 仍 future 时一次 UPDATE”（target:116、324），没有要求该 `UPDATE` 自身含 PG-time predicate。冻结 WIP 的 `_clock` 同时暴露 `transaction_timestamp()` 与 `clock_timestamp()`，且旧 `set_state` 曾在取得 row lock 前取时钟（`dayu/investment/storage/postgres_schedules.py:214–228, 851–855`）；这是被勘误替换的中间态，不是本 finding 的对象，但直接证明两种 PG clock 与错误 sequencing 均是现实实现路径。
- **影响**：可持久化 active + past cursor，继而使 scheduler 把本不应激活的 fire 作为 misfire/occurrence 处理；违反 activation、re-enable 与审计的共同 cursor 真源，并使“严格 future”测试无法可靠验收。
- **建议改法和验证点**：在 target §S22-CTRL-008 第 2 点、Store ACTIVE 规则与 STOP 同步写死：在已持有 schedule row lock、已验证 tenant/id/version/source state 后，成功 ACTIVE 的线性化点必须是同一条条件 `UPDATE`；其 `WHERE` 同时包含 tenant/id/expected version/source state 与 `:activation_next_fire_at > clock_timestamp()`。必须明确使用 `clock_timestamp()`，不得以 `transaction_timestamp()` 或 precheck 的 Python 时间代替。若该 conditional update 因时间谓词不成立而零行，在仍持有 row lock 的事务内重读 row 与 fresh `clock_timestamp()`，返回 `clock_stale + ScheduleObservation`、零 mutation；version/state 不符仍走既有 closed conflict。future 的定义应明确为该 conditional update 的线性化点，不承诺任意进程暂停后直到 client commit 仍 future。新增命名测试 `test_activate_conditional_pg_clock_guard_rejects_candidate_expiring_at_update_boundary`，同时断言：时间 guard 与 CAS 在同一写 statement、零 version/cursor mutation、返回 fresh observation；保留既有 activate/disable winner test。
- **修复风险（低/中/高）**：低；是对既有两阶段方案的精确 SQL 原子性补足，不改变 Service cron owner、DTO、锁序或文件边界。
- **严重程度（低/中/高/严重）**：中。

### TERRA-S22-APC-002-未修复-[低]-clock-stale 的总 CAS 尝试次数在计划内不一致

- **位置**：`S22-CTRL-008` 第 2 点（target:116）、Store ACTIVE 规则（target:325）、勘误最小合同（plan-fix:29）及命名测试 `test_activate_clock_stale_retries_three_times_without_mutation_or_version_rebase`（target:659）。
- **问题类型**：契约缺失 / 测试缺口。
- **当前写法**：target:116 的“最多重试 3 次”可自然理解为首次 CAS 外再重试三次；target:325 则规定“单次 public 调用最多三次；第三次仍 stale 返回”，而 plan-fix 又写“最多三次重算”。
- **反例/失败场景**：两个符合局部文字的实现分别执行四次或三次 `set_state` CAS；在持续跨分钟的压力下，它们有不同的读写负荷、记录次数和可观察行为，现有测试名也无法裁决哪一个才是合同。
- **为什么有问题**：这是一个有界但真实的 public retry contract 冲突；无法用命名测试稳定验证“最多”语义。
- **直接证据**：上述三处文字使用“重试”“调用”“重算”但未统一计数单位，也没有精确调用次数断言。
- **影响**：不会破坏 tenant/state safety，但会让实现和复审对 retry budget 得出不同结论。
- **建议改法和验证点**：统一为“每次 public activate/re-enable 总计最多三次 `set_state` CAS 尝试，包含首次”；把命名测试改为或补为精确断言三次调用、三次均 `clock_stale`、原 expected version 不变、每次零 mutation。若设计选择首次加三次重试，也必须在三处同步写为四次总尝试。
- **修复风险（低/中/高）**：低；只收敛已存在的有界计数语义与测试断言。
- **严重程度（低/中/高/严重）**：低。

## 4. Open questions

无。两项 finding 都有直接计划文字和可复现的数据库 statement 边界反例，不依赖未完成 WIP、外部服务或推测。

## 5. 残余风险与跟踪

- 本 artifact 是计划复审，不是代码验收；冻结 WIP 尚未按勘误恢复，不能据此推断实现已具备计划语义。
- `TERRA-S22-APC-001` 修正后，真实 PG16 lane 仍必须证明条件写入的时钟/版本/state 线性化与零 mutation；不应以本机 clock、sleep 或 mock 成功替代。
- 两项修正均应回写 target 与 plan-fix 后进行新的独立复审；在 `open H/M/L = 0/0/0` 前，维持计划自身规定的 implementation pause。

## 6. 最终计划复审结论

`FAIL`。当前冻结 target SHA 已核验为 `0706e9b3fed8dd1f55eafe2fae8d8556f129c25470b4e0d07a0c1fedb918dfe5`，但 open H/M/L 为 `0 / 1 / 1`，不能授权恢复 implementation。
