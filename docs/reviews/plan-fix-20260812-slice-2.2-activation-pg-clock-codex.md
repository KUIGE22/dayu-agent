# Slice 2.2 activation / availability 实现期计划勘误

- **状态**：`CLOSED / DEEPSEEK + MIMO FINAL PLAN RE-REVIEW PASS`
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **此前 accepted plan baseline**：`2dcba107b20730a6ab40483f9b8a04c9320f7602`
- **实施状态**：`RESUME AUTHORIZED AFTER ACCEPTED PLAN ERRATUM COMMIT`；production/tests/dependency WIP 在该提交前继续冻结。
- **授权边界**：本记录闭合计划修正并授权 accepted plan erratum 本地提交后由Codex内部模型恢复实施；DeepSeek Flash不再写入，只保留DeepSeek独立审核。不授权 live provider/model/broker、交易、push 或 PR。

## 1. 触发原因

实现 `ScheduleStoreProtocol` 与 `PostgresScheduleStore` 时触发 accepted plan 的 STOP 条件。原合同无法同时满足“PostgreSQL clock 是唯一时钟真源”“croniter 只在 ScheduleService”“激活时原子写 active + 首个 future cursor”：

1. `ScheduleActivationRequest` 只有 `schedule_id`、`expected_version`、`target_state`；原 Store API 既不返回 disabled draft 的 PG clock observation，也不接收 Service 计算的 `next_fire_at`。
2. `reserve_occurrences` 只接受 active/current-cursor 且 batch 必须有 1 至 3 条 occurrence，不能被滥用为空 batch activation。
3. PENDING materialization 只有 occurrence ID；原 Store 没有 tenant-scoped point read，而 `begin_materialization` 一调用就提交状态，因此 Service 无法在 PENDING -> MATERIALIZING 前证明 frozen descriptor 的 execution availability。
4. accepted misfire scan-limit 语义要求 disable 后保留 cursor 供审计，但 WIP DTO/DDL/Store 中间态强制 disabled cursor 为 NULL。

因此裁决：

- `H-PLAN-001`：activation/re-enable API 不可实施，`ACCEPTED / FIXED IN PLAN`。
- `H-PLAN-002`：PENDING availability 缺 point-read/admission 边，`ACCEPTED / FIXED IN PLAN`。
- `M-PLAN-003`：disabled cursor 语义冲突，`ACCEPTED / FIXED IN PLAN`。

## 2. 最小合同修正

计划新增 `S22-CTRL-008`，锁定以下唯一方案：

1. `ScheduleObservation(definition, database_now)` 是 `get` 与 `list_due` 的唯一观察 DTO；definition 与 aware UTC PG clock 必须在同一 tenant-scoped 事务取得。
2. `set_state(..., activation_next_fire_at=...)` 在行锁后用一条 conditional DML 与同一 `clock_timestamp()` 值原子完成时间 guard、tenant/id/version/state CAS 和 observation 返回。ACTIVE candidate 已不再严格 future 时返回 `clock_stale` 且零 mutation；每次 public activation 总计最多三次 CAS（包含首次），保持原 expected version且不自动 rebase。
3. 新增 tenant-scoped `get_occurrence`。PENDING 先按 frozen descriptor 查询 JobService availability，再把 closed `ScheduleMaterializationAdmission` 交给 Store；MATERIALIZING 使用 `committed_replay`，不得再次运行 availability gate。
4. PENDING + unavailable 返回 typed no-work 并保持 schedule/occurrence 原字节；本地 negative availability 不能成为跨进程 global disable/skip 真源。并发赢家已提交 MATERIALIZING 时，stale unavailable 不得撤销 durable commitment。
5. descriptor/execution registries 只允许 append、exact-idempotent registration 与 conflict rejection；无 remove/replace。availability 不持久化、不缓存、不进入 Redis。
6. active 必须有 cursor；从未激活的 disabled draft 可为 NULL；manual 或 scan-limit disable 保留已有 cursor，re-enable 忽略旧值并按 fresh PG clock 覆盖。显式 disable 只 skip PENDING。

精确 Store surface 现为九项：`register`、`get`、`get_occurrence`、`set_state`、`list_due`、`reserve_occurrences`、`list_replayable`、`begin_materialization`、`mark_enqueued`。未引入 callback、跨层 session/UoW、Storage croniter、local clock、空 reservation batch、handler availability PG truth 或第二 registry。

## 3. 被拒绝的替代方案

- Store 导入 croniter 或用 `datetime.now()`：破坏 Service owner 与 PG-clock truth。
- 先把 schedule 设为 active、随后补 cursor：产生 active + NULL 的可见非法状态。
- 用空 `reserve_occurrences` batch 激活：违反 batch 与 occurrence 审计合同。
- callback、跨层持 SQL 事务或把 SQLAlchemy session 交给 Service：破坏 DAG 与可测试边界。
- 先 `begin_materialization` 再查 availability：缺 handler 时会留下不可撤销且无法入队的 MATERIALIZING。
- 把 availability 写入 PG/Redis、使用 process cache 或允许 registry remove/replace：制造第二真源与竞态漂移。
- disable 清空 cursor、re-enable 复用旧 cursor：分别破坏审计和 fresh PG-clock 语义。

## 4. 新增硬门禁

计划已增加 activation conditional PG guard、三次总 CAS、transition before/after action matrix、显式 scan-limit resulting state/cursor、并发 activate/disable、re-enable fresh cursor、active/NULL PG16 CHECK、disabled audit cursor、PENDING unavailable 零 mutation、MATERIALIZING-first replay page、PENDING replay与active due两条独立keyset轮转、mixed-capability scheduler、stale admission、MATERIALIZING committed enqueue trap、tenant-scoped point read 与 registry no-remove/replace 命名测试，并同步 STOP conditions。

复审必须特别证明：

- 两阶段 observation/CAS 在分钟边界不会写入已过期 cursor；
- version/state race 只有一个线性化赢家，失败方零 mutation 且不自动 rebase；
- negative availability 只能延后当前进程，不能 global disable/skip 或撤销已提交 MATERIALIZING；
- disabled + retained cursor 不会被 `list_due` 当作可调度；
- Store/Service/JobService DAG 无 callback、session、concrete repository 或 registry 泄漏。

## 5. WIP 冻结证据

本计划勘误开始时，除目标 plan 外共有 13 条 implementation WIP 路径；均保持未暂存、未提交。关键冻结 SHA-256：

- `dayu/investment/domain/schedules.py`：`0d566833aeabcb8e44e46d8219a7ffdb5a2d7b768458fc7336ef803cab9c8d1c`
- `dayu/investment/storage/postgres_schedules.py`：`796b405b53e785e20f98c22bebc8d31c7d08e750e6454c77c7036e4b559989a9`
- `dayu/investment/storage/migrations/versions/0004_durable_schedules.py`：`a544a0a545d9d16aa13fd86fb6d4a6b53b85b8d14044b5349214d7432f9c4867`
- `tests/investment/test_schedule_domain.py`：`3e4127846a42074ecee3eab500c8b999da40d19ce2a09df1960f494fb1a20ecd`

计划勘误期间Flash保持idle；在最终双审与Controller接受前禁止恢复写入。最终接受后实施owner已由用户改为Codex内部模型，冻结的Flash窗口不得继续写入。

## 6. 首轮复审 finding 与 corrective closure

首轮 Terra artifact `plan-rereview-20260812-slice-2.2-activation-pg-clock-terra.md` 结论为 `FAIL / open H/M/L=0/1/1`。Controller 同时接受两路只读增量审计的直接证据；合并裁决与修正如下：

| Finding | 裁决 | Corrective fix |
| --- | --- | --- |
| `TERRA-S22-APC-001` | `ACCEPTED / FIXED` | ACTIVE 成功改为 row lock 后单条 conditional DML；one-row materialized CTE 的同一 `clock_timestamp()` 同时用于 future predicate 与 returned observation，CAS 同 statement；零行返回 clock_stale/零 mutation。 |
| `TERRA-S22-APC-002` | `ACCEPTED / FIXED` | 统一为每次 public activate/re-enable 总计三次 CAS，包含首次；命名测试精确计数。 |
| `CTRL-S22-APC-003` | `ACCEPTED / FIXED` | `ScheduleReservationBatch` 新增 expected/resulting cursor 与 explicit resulting state；scan-limit 原子 disable 不再靠 skip reason 推断。 |
| `CTRL-S22-APC-004` | `ACCEPTED / FIXED` | `ScheduleStateTransitionResult` 增加 request、previous definition、observation 与 candidate，锁定 applied/unchanged/clock_stale action matrix；unavailable 改为 Service closed error。 |
| `CTRL-S22-APC-005` | `ACCEPTED / FIXED` | owner 表、pipeline 与 DAG 全部改为 `enqueue_committed_schedule_occurrence`；MATERIALIZING 禁止走普通 enqueue/availability。 |
| `CTRL-S22-APC-006` | `ACCEPTED / FIXED` | 跨进程 negative availability 不再 global disable/skip；activation 保持 disabled 并报 closed error，PENDING 返回 unavailable/零 mutation，capable process 可继续收敛。 |
| `CTRL-S22-APC-007` | `ACCEPTED / FIXED` | replay 改为 bounded page：MATERIALIZING 固定优先，PENDING 由 process-local keyset cursor 跨 tick 轮转；unavailable 继续页内下一项，且每 tick 仍有一次 bounded due reservation，避免 tenant 级 head-of-line blocking。 |
| `CTRL-S22-APC-008` | `ACCEPTED / FIXED` | due scan 同样增加独立 `ScheduleDueCursor/Page/ScanResult`；Store 无重复 wrap，Service 逐entry跳过本地 unavailable，Host跨tick立即消费cursor，页外available schedule不会被整页unavailable永久饿死。 |
| `CTRL-S22-APC-009` | `ACCEPTED / FIXED` | 消除cursor消费时序歧义：每个gateway返回后先赋typed cursor，再做首个gate/materialize/result处理await；命名测试逐调用顺序锁定。 |

Corrective target SHA-256 将由最终复审各自读取并记录；首轮 Terra 的 `0706e9b3...` 只保留为历史输入身份，不再代表当前正文。全部 nine findings 必须经 final dual plan re-review open0 后才算 CLOSED。

## 7. Final dual plan re-review closure

- DeepSeek：`docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-final-deepseek.md`，`PASS / open H/M/L=0/0/0`。
- MiMo：`docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-final-mimo.md`，`PASS / open H/M/L=0/0/0`。
- Terra补充架构复审：`docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-final-terra.md`，`PASS / open H/M/L=0/0/0`。
- 三路共同核验的 corrective 语义快照 SHA-256：`cf952ce6a76384c0dc62c642403804a9328d0b80e58897b9003ed1f473a29a62`。
- `TERRA-S22-APC-001`、`TERRA-S22-APC-002` 与 `CTRL-S22-APC-003` 至 `CTRL-S22-APC-009` 全部 `CLOSED`；当前 open H/M/L=`0/0/0`。

Controller接受该勘误。只允许先把目标plan与本次review/fix/acceptance artifacts形成独立本地accepted plan erratum commit；该提交不得夹带冻结的production/tests/dependency WIP。提交完成后由Codex内部模型恢复实施，DeepSeek Flash不再写入；后续代码最终门禁固定为DeepSeek + MiMo双路独立code review及corrective re-review open0。live provider/model/broker、交易、push与PR仍未授权。
