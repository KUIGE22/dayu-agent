# Slice 2.2 Scheduler / Worker / Redis：Terra corrective architecture plan re-review

- **审查边界**：独立、只读的计划/架构复审；唯一新增本 artifact。未修改 target、master、Controller fix、任何既有 review、production、tests、README、dependency 或 CI。
- **审查时间**：2026-08-12 02:04:28 +0800。
- **代码基线**：`38ddad489f4f9cfa1ae2a4373d69a628e49578bf`。
- **锁定的 target 版本**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md` SHA-256 `429a2ecc5f0c40eff3886186444d44ad73aa86409f07152a850038bbc2516130`。
- **完整读取**：根 `AGENTS.md`、Slice 2.2 target、Investment Platform Restoration master、Controller plan-fix 与原 Terra review；并交叉读取直接相关的 Slice 2.1 基线 JobStore/domain、Host/startup、PG16 fixture、CI/constraints 与原始 review 所指的证据。
- **执行边界**：未运行 pytest、pyright、Ruff、Docker、PostgreSQL、Redis、模型、broker 或任何 live action；未 commit、push 或启动 Gateflow。
- **结论**：**FAIL**。
- **Open H/M/L**：**0 / 1 / 0**。

## 结论先行

原 `TERRA-S22-001..009` 中八项已在**计划合同层**真实闭合。尤其是：不设置
materializer lease 并不是遗漏；在 durable `materializing`、不可变请求快照、数据库原子
同 fingerprint 收敛和同 job 的幂等 mark 同时成立时，它比可过期 owner lease 更安全。

但 misfire 的 lookback 重定位仍遗漏一个精确边界：旧 cursor 早于 lookback 边界、而一条
cron fire 恰好等于该边界时，target 没有规定重定位枚举是否包含该 fire。此处允许实施者用
严格的 next-candidate 查询跳过它，与“不无审计跳 fire”矛盾。因此尚不能解除 implementation
freeze。

## 原 Terra finding 闭合核对

| 原 finding | 结论 | 当前直接证据 |
| --- | --- | --- |
| `TERRA-S22-001` occurrence outbox/crash/concurrency | **CLOSED（计划级）** | target `31–47` 固定 reserve → `materializing` → enqueue → mark 顺序，冻结快照且禁止 disable 回退；`220–231` 固定完整请求身份与唯一 fingerprint 真源；`259–264` 固定行锁、mark 规则和 `ON CONFLICT DO NOTHING` 后 fingerprint re-read；`350–361` 定义并发 scheduler 状态机；`464–477` 列出两个 crash window、disable race、双 scheduler、同/异 fingerprint 测试。 |
| `TERRA-S22-002` DST/misfire 中间状态 | **PARTIALLY CLOSED；见开放 M** | `239–244` 已闭合 activate、DST、grace、expired group、scan-limit audit、cursor 与 rollback；但第 2 步的 lookback 重定位没有规定边界包含性。 |
| `TERRA-S22-003` correlated deadline precedence | **CLOSED（计划级）** | `301–311` 将 heartbeat 改为 `governance_required`、未终结 correlation 的 complete/fail 零 mutation，并固定 PG projection → Host observe/cancel/reobserve → reconcile；`303–305` 还加入 keyset page/cursor 防饥饿；`502–512` 覆盖 lease-valid deadline、priority、handler return 与 keyset rotation。 |
| `TERRA-S22-004` async inner work/drain | **CLOSED（计划级）** | `79–83`、`346` 要求唯一 inner-future owner、有界 PubSub、reap-before-close；`365–367` 明确 first-signal soft grace、`drain_abandon_requested` 线性化、继续 heartbeat 与 second-signal `os._exit(1)`；对应 blocked PubSub/heartbeat、non-cooperative handler、second-signal tests 已在 `513–517`、`529–530`。 |
| `TERRA-S22-005` five independent real lanes | **CLOSED（计划级）** | `536–546` 给出五个独立的 plain-`pytest` process、两种 pinned image 的显式 pull、聚合五项 exact ignore，并禁止其他 full lane 再收集 integration；`554` 将其升为 gate。 |
| `TERRA-S22-006` tenant-closed schedule DDL | **CLOSED（计划级）** | `250–255` 明列 `(tenant_id, id)` unique、schedule/job composite FK、`ON DELETE RESTRICT`、RLS/grant、state/snapshot/job/skip exact CHECK 与 immutable-column prohibition；`489–491` 要求静态和真实 PG16 验证。 |
| `TERRA-S22-007` Redis-first unique startup root | **CLOSED（计划级）** | `87–106` 和 `390–408` 固定两个 public wrapper 共用一个 typed private root、NOT_REQUIRED/POSTGRES_ONLY/REDIS closed shape、Redis-first admission、typed direct refs、reverse close 与 queue-wire/production-call-order 的分离；`454–458` 指定验证。 |
| `TERRA-S22-008` dependency truth / `uv.lock` | **CLOSED（计划级）** | `128`、`191–194` 仅允许 tracked pip constraints；`539–546` 使用 plain `pytest` 且明确禁止 `uv run`；这与现有 pip-only install action 和 master `1372–1379` 一致。 |
| `TERRA-S22-009` tenant authority wording | **CLOSED（边界/措辞级）** | target `51–55`、`380` 明确这是 selector 而非 authentication，外部已授权 operator/process manager 是不可伪测的启动前置；master `3874–3877` 同步这一边界，未把 selector 伪称 authority。 |

### 对无 materializer lease 的专项判定

这个选择成立，不应把原 review 中的 lease 方案机械复活。`materializing` 是 durable
commitment 而不是“某个 process 正在拥有”的瞬时锁：

1. reserve 事务已把全部 `JobEnqueueRequest` identity 冻结；重放不能引入新时钟、定义或
   idempotency key（target `35–45`、`220–231`）。
2. `begin_materialization` 与 disable 采用同一锁序；先 begin 者使 occurrence 不可被
   skip，先 disable 者则没有 enqueue（`259–262`、`361`）。
3. 两个 scheduler 同时重放同一 `materializing` 行仍可安全调用 enqueue：计划要求数据库
   `ON CONFLICT DO NOTHING` + 同事务 fingerprint re-read，得到同一 receipt/job，而不是
   基线先 SELECT 再普通 INSERT 所会泄漏的 `IntegrityError`
   （target `47`、`264`；基线 `postgres_jobs.py:850–929`）。
4. mark 只接受相同 job 的幂等完成；不同 job 是 invariant stop，不被伪装成正常竞态
   （target `262`、`361`）。

因此 lease 到期后再并发 external enqueue 的额外时钟/fence 问题不会带来安全性收益；当前
immutable snapshot + atomic idempotency 的收敛点已足够关闭原来的两个 crash window。

## 开放 finding

### TERRA-S22-RR-001 — lookback 重定位没有闭合等号边界（中）

- **关联原 finding**：`TERRA-S22-002`。
- **直接证据**：target `240` 只在 `next_fire_at < database_now - schedule_max_lookback_seconds`
  时写 `lookback_exceeded`，所以恰等于边界的 fire 不属于该 skip 分支；紧接着仅说
  “working cursor 从 lookback 边界重新找首个有效 candidate”，没有规定是最早
  `>= boundary` 的 candidate。第 3 步只固定终止条件是“首个严格晚于
  `database_now`”（`241`），而第 6 步承诺“不无审计跳 fire”（`244`）。
- **反例**：令 `L = database_now - schedule_max_lookback_seconds`。persisted cursor 在
  `L` 之前，cron 正好在 `L` 有一个 valid UTC fire。实施者若以通常严格前进的
  next-candidate 调用从 `L` 起算，会选择 `> L` 的下一 fire。该 `L` fire 既不会归入
  `lookback_exceeded`，也不会进入 `misfire_expired` 或 eligible group，重启后同样没有
  occurrence/audit 可证明它被处理。
- **影响**：这是 durable schedule 的一次确定性丢 fire/丢审计边界，非仅测试命名问题；
  范围限于 equality corner，故为中风险而非高风险。它仍使 target 自身的 open-0 gate
  不成立。
- **最小精确修复**：在 §5.2 第 2 步定义 `L` 后明确：重定位必须枚举最早有效 UTC
  candidate `C`，满足 `C >= L`；`C == L` 必须进入第 4/5 步，按 grace 分类为
  `misfire_expired` 或 eligible/pending，不能被 lookback audit 吞掉或被严格 next 调用
  跳过。只允许 `C < L` 的 fire 被 lookback 压缩。保留现有 scan-limit 合同：它现在已
  精确规定 partial group 丢弃、audit identity、disabled cursor 和 re-enable（`241`），
  不需要重开该项。
- **必要验证**：扩展既有
  `test_scheduler_misfire_boundary_is_inclusive_and_dst_cursor_is_monotonic`（target `483`）
  至少覆盖“cursor `< L`、fire `== L`”的 case；断言该 fire 恰好得到一个
  expired/pending reservation（按参数化 grace），cursor 严格前进，retry/restart 不丢失也不
  重复。测试必须同时保留 `lookback_exceeded` 对旧 persisted cursor 的唯一 audit。

## 已核对的重点合同

- **Misfire batch**：除了上述等号漏洞，grace 包含等号、expired aggregation、最多三项
  batch、DST empirical gate、scan-limit provisional group discard 与 stable audit identity
  已有可执行计划文本（target `235–244`）。
- **Correlated heartbeat precedence**：generic deadline terminalization 已在存在未终结
  correlation 时被隔离；租约续期、Host cancel/reobserve 和 terminal reconciliation 的先后
  关系明确，且 keyset cursor 不会永远卡在前 N 条（`301–311`）。
- **Inner-future soft grace/second signal**：计划不再承诺不可实现的“非协作 handler 也
  固定时限安全退出”；first signal 保持资源/heartbeat，second signal 明确进程边界 hard
  stop（`346`、`365–367`）。
- **Unique startup root**：队列 admission 的类型形状和 owner 已固定，真实 PG+Redis
  lane 与 production call-order lane 没有混称（`390–408`）。
- **五条独立 PG/Redis process**：当前文本已撤掉 `uv run`，并补足 PG16 和 Redis 的
  pinned digest pull；这解决了原 session-scoped PG cluster 的 role-pollution 风险
  （`536–546`）。

## 残余风险与 gate 决议

本结论只说明计划是否足以指导实现，不声称当前基线已经拥有上述能力；例如基线
`PostgresJobStore.enqueue` 仍是非原子的 SELECT/INSERT 流程，正是 target 要在 implementation
中替换的对象。所有 production/tests/CI/dependency 仍应相对 `38ddad4` 保持冻结，直到本
finding 通过最小 plan fix 后重新完成独立 corrective re-review。

**最终：FAIL，open H/M/L = 0/1/0。**
