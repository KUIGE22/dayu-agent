# Slice 2.2 Scheduler / Worker / Redis — Terra 最终 closure-only 独立复审

- **结论**：**FAIL**。
- **开放 finding**：`H/M/L = 0/2/0`。
- **代码基线**：`38ddad489f4f9cfa1ae2a4373d69a628e49578bf`。
- **锁定 target**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`，SHA-256 `461c9557e640174ae985e73d2bbfd200d5520374395e5b1647adeb6bb1b0df85`。
- **锁定 Controller fix**：`docs/reviews/plan-fix-20260812-slice-2.2-scheduler-worker-redis-codex.md`，SHA-256 `501fe00ff19f99a2952fbf228aeb40a346ce85d78a69c206acff940f8a9c1d5a`。
- **历史 Terra corrective review**：`docs/reviews/plan-rereview-20260812-slice-2.2-scheduler-worker-redis-terra.md`，SHA-256 `a37edf259b50fe8ac9a9bf960ebb8859c0791f8a9ea28641cb104953718ba7eb`；它锁定的是修订前版本，仅作历史证据，不覆盖本次结论。
- **完整读取**：根 `AGENTS.md`、上述最新 target / Controller fix / 历史 Terra corrective review，并交叉核对 master、当前 Host/Service 分层守卫、startup、JobService 与 workspace migration 基线。
- **执行边界**：只读复审；未修改 target、master、fix、source、tests、README、dependency 或 CI；未运行 pytest、pyright、Ruff、Docker、PostgreSQL、Redis、模型、broker 或任何 live action；未 commit、push 或启动 Gateflow。

## 1. 结论先行

此前要求复证的 durability、时间边界、启动 admission 与 correlation 合同在**计划层**均已闭合；特别是无 materializer lease 并非遗漏。当前仍有两个独立的中严重度实现阻断项：首信号与已发出同步调用返回之间没有 intake 线性化屏障；Redis 运行态既未与 integration PG-only 模式分型，也没有消费可配置的失败阈值/探活间隔。因此不得解除 `IMPLEMENTATION FROZEN`。

## 2. 指定 closure 逐项复证

| 复证项 | 结论 | 当前直接证据 |
| --- | --- | --- |
| `TERRA-S22-RR-001` 的 `C >= L` 等号边界 | **CLOSED** | target §5.2 第 2 步（`244`）明确从 `L - 1 minute` 的 naive-local seed 枚举，丢弃仅 `candidate_utc < L` 的候选，要求首个 `C >= L`；`C == L` 必须进入 grace 分类，禁止严格 `get_next(L)` 跳过。§10 的 `test_scheduler_lookback_relocation_includes_fire_exactly_equal_to_boundary` 锁住该结果。 |
| 无 materializer lease 的 occurrence durable materializing / immutable snapshot / concurrent enqueue | **CLOSED** | target `31–47`、`235`、`259–264` 固定 pending → materializing → enqueue → mark，immutable request/fingerprint、同 fingerprint 原子收敛和同 job 幂等 mark；`301–303` 使 registry 漂移不能撤销已 materializing 的承诺。crash、disable、并发 replay 与同/异 fingerprint 的命名测试在 `480–507`。 |
| production explicit-provider Redis admission | **CLOSED** | target `87–106` 要求 ordinary 与 platform wrapper 共用一次 private root，production 即使显式 provider 也必须先取得 REDIS admission；`413–417` 规定 custom provider 仅替换 composition，不能绕过 admission，且资源仍 exact-once close。`471–473` 有直接回归测试。 |
| Agent correlation 统一锁序与 late re-read | **CLOSED** | target `315–318` 覆盖 reserve、authorize、heartbeat、complete/fail、generic recover、targeted recover 和 reconcile，锁序固定为 job → attempt → lease → correlation；generic recover 还明确要求 READ COMMITTED 下父行锁后的第二 statement 刷新 snapshot 再 re-read。`528–530` 具 race/late-recheck 测试。 |
| valid-lease `NO_HOST` wait | **CLOSED** | target `313` 将有效 lease 的 missing Host 固定为 `MISSING_HOST_WAIT`：零 recover/新 attempt，停止续租，以已持久化 expiry 为上界；Host 在 expiry 前出现才恢复 heartbeat，expiry 后仍 missing 才重新读取并 targeted recover。`538–540` 覆盖 wait、停止续租和 expiry recovery。 |
| PENDING availability 与 MATERIALIZING committed replay typed decision | **CLOSED** | target `301` 将 descriptor/execution availability proof 与 PENDING→MATERIALIZING 按 schedule lock 线性化；`303` 要求 store 返回 typed persisted `ScheduleMaterializationDecision`，committed entry 只接受 materializing+完整 snapshot，重算 fingerprint 后走同一 PG idempotency 真源，mark 时再锁内重验。`506–507` 覆盖 PENDING 拒绝与 materializing 后 registry drift。 |
| Host/Service 分层、migration init 文案与 README allowlist | **CLOSED（计划级）** | target `124–158` 改为 Host-local structural gateway ports，Host 不 import `dayu.services`，由上层 composition 结构注入；这与现有架构守卫 `tests/architecture/test_dependency_boundaries.py:101–123` 一致。target `128`、`449`、`476` 只同步既有 `upgrade head` 的 0004 说明，避免误称 head 仅含 0003；`134` 已将 `dayu/README.md` 加入 allowlist，满足根 `AGENTS.md:92`。 |

## 3. 开放 finding

### TERRA-S22-FINAL-001 — 首信号后已发出调用返回，仍可能启动新工作（中）

**根因与直接证据**：target `357` 正确承认同步 PG/Redis inner future 不能靠 outer cancellation 终止；但 `376–378` 只规定首信号“停止新 claim/tick/subscribe”，没有规定已经在 `asyncio.to_thread` 中的 `claim`、`list_replayable`、`list_due` 或 reserve 返回后必须重新检查 DRAINING。target `344–352` 仍可把已返回的 claim 变成 handler + heartbeat，`361–372` 仍可把 signal 前取得的 list/reservation 继续变成新的 `begin_materialization`。基线 `JobService.claim` 只给出 claim，没有一个可安全 release/abandon 的补偿入口。

**可达反例**：worker 发出 claim → 首个 SIGTERM 线性化为 DRAINING → claim 在 thread 中成功返回 → loop 按正常分支启动 handler/heartbeat；或 scheduler 的 list 返回后才执行 begin/materialization。两者都违反“停止 intake”，后者还可能在计划声明只应收口当前 begin/enqueue/mark 时开始新的 durable commitment。

**最小计划修复**：

1. 在首信号定义唯一、原子、process-local intake epoch/gate；每个 await/to_thread 返回后且在启动 handler/heartbeat、下一项 begin 或新 materialization 之前重验同一 epoch。
2. gate 前发出但 gate 后才返回的 claim 不启动 handler、不续租、不写假 terminal，明确由既有 lease expiry/recovery 收敛；list/due/reserve 结果不开始新的 begin/materialization。已经在线性化为 MATERIALIZING 的当前 occurrence 仍按既有规则收口 enqueue/mark。
3. 在现有 worker/scheduler signal tests 之外增加 named barrier cases：claim-return-after-signal、list/reserve-return-after-signal，以及 begin 已线性化后仍允许仅收口该 occurrence；三个 case 均证明没有新的 handler、claim、tick 或 materialization 被启动。

### TERRA-S22-FINAL-002 — Redis runtime state 与可配置参数真源未闭合（中）

**根因与直接证据**：target `163–187` 将 `redis_failure_threshold` 与 `redis_health_interval_seconds` 作为严格可配并写入 startup snapshot 的 settings；但 §7.2（`331–339`）又无条件硬编码“连续 3 次”与“每 30 秒”。任意合法非默认值会只改变 snapshot、不改变运行行为。与此同时 deployment `PlatformQueueMode` 只有 `event_assisted` / `postgres_polling`（`174`），POSTGRES_ONLY admission 明确没有任何 Redis ref（`415`），而 §7.2 又出现没有闭合类型/初始映射的 `POLLING_DEGRADED`。计划没有定义 integration PG-only worker 如何保证永不构造、ping、subscribe 或恢复 Redis。

**影响**：实现者只能猜测是复用 profile mode、额外布尔还是隐式字符串；这既无法以严格类型守住 PG-only 边界，也无法同时满足 config 与状态机两个相互矛盾的真源。

**最小计划修复**：

1. 保留 profile-derived `PlatformQueueMode`，另声明 worker-owned closed Redis runtime state（至少 `event_assisted` / `polling_degraded`）；仅 REDIS admission 创建该状态机，POSTGRES_ONLY 永远只 PG poll 且没有 Redis transition。
2. 将进入降级条件改为 `consecutive_failures >= settings.redis_failure_threshold`，健康 probe 调度改为 `settings.redis_health_interval_seconds`；文本中的 3/30 仅作为默认值。同步 target 高层摘要与 master 中的“三失败”表述，使其不再声称硬编码行为。
3. 增加非默认 threshold/health interval 的参数化测试与 integration PG-only worker 的零 Redis construct/ping/subscribe test；保留默认 `3/30` regression case。

## 4. 未重开的事项与残余风险

- 既有 workspace migration plugin 已登记在 init runner 且执行 `upgrade head`，production 旧库会自动到 0004；本次只需同步其说明，故不把它重复报为 schema migration 缺口。若未来宣称 `INTEGRATION` profile 能通过 `dayu-cli init` 初始化旧库，须另明确该 admission/迁移语义并重新 review。
- Redis hint 仍可丢失、重复或乱序；计划正确把 PG claim/fence/receipt 留为真源，代价是 poll interval 延迟。
- Host cancellation 和非协作 handler 仍受 cooperative/provider 与 OS hard-stop 边界限制；这是 target `612–618` 已记录的残余风险，不是本次新增 finding。
- 本结论仅验证计划合同及当前基线代码证据，未替代后续实现、真实 PG16/Redis/SIGTERM lane、类型检查或 code review。

## 5. Gate 决定

在 `TERRA-S22-FINAL-001` 与 `TERRA-S22-FINAL-002` 获 Controller 接受并形成新的最小 plan fix，且新的独立 re-review `PASS / open H/M/L=0/0/0` 前：

- 保持 `IMPLEMENTATION FROZEN`；
- 不得修改 production、tests、README、dependency 或 CI；
- 不得把本 artifact 视为 implementation acceptance。
