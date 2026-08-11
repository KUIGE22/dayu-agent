# Slice 2.2 Scheduler / Worker / Redis — Controller Plan Handoff

- **状态**：`ACCEPTED / TERRA + DUAL FINAL4 PLAN RE-REVIEW PASS / IMPLEMENTATION HANDOFF READY`
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **master**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **前序代码基线**：`38ddad489f4f9cfa1ae2a4373d69a628e49578bf`
- **审计方式**：Controller + 三路只读 inventory；未修改production/tests/README/dependency/CI，未启动Redis/PG容器，未运行模型/provider/live交易。

## 1. 结论先行

master 原 Slice 2.2 五行只能表达目标，不能直接生成代码。Controller 初版关闭七个 blocking contract后，Terra/MiM/MiMo 初审与后续复审又发现 occurrence materialization、misfire中间区间、correlated heartbeat deadline、inner-future drain、PG lane隔离、startup、Host ports、signal intake、Redis runtime、terminal-race result与governance pagination等实质缺口；target已按`plan-fix-20260812-slice-2.2-scheduler-worker-redis-codex.md`全部修订。最终三路final4均open0，implementation handoff已就绪。

最终选择：

1. PostgreSQL `job_schedules + job_schedule_occurrences` 是持久schedule/cursor/outbox真源；research-template disabled/unbound manifest保持预览资产。
2. queue daemon一次只服务CLI显式传入的一个tenant，不猜default、不全局claim、不用BYPASSRLS；外部operator/process-manager授权与credential分发是本slice未实现的启动前置，不把selector伪称认证。
3. Slice2.1 descriptor registry保持不变；Service新增独立async execution registry/gateway，handler只能收到不含lease/fence/token的request。
4. Redis只是post-commit tenant/job hint；Worker无论何种mode始终从PG claim。
5. Agent active governance使用PG join projection中的deadline/cancel truth，Host取消只走`cancel_run`。
6. production首次Redis admission失败即在PG/Host/workspace副作用前停止；显式integration profile可PG-only。
7. 真实PG16、固定digest Redis、真实subprocess SIGTERM是硬门禁，fake-only不算完成。

## 2. 直接仓库证据

- `dayu/host/scheduler.py`、`dayu/host/worker.py`、`dayu/cli/commands/platform.py` 当前均不存在。
- `dayu/services/job_service.py` 明确把 `JobHandlerRegistry` 定义为 descriptor-only；没有invoke/handler/payload API，production registry为空。
- `JobService`/`JobStoreProtocol` 每个方法都强制 `TenantScope`；`TenantScope`只能由`Principal.to_scope()`派生，仓库没有tenant roster/system-principal/global claim owner。
- migration `0003_durable_jobs`没有schedule/cron/timezone/cursor/misfire/occurrence表。
- `_research_template_monitoring.py` 强制scheduler manifest及每个job `enabled=false`、`binding_status=unbound`、automated execution false，action只是validate command。
- `PlatformSettings`只有Redis env name presence；不存在`PlatformQueueSettings`，pyproject/locks无redis/croniter。
- production provider baseline精确映射为`investment_identity + durable_jobs`，workspace import是独立one-shot preparation。
- `JobClaim`携带persisted deadline；expired correlation projection不携带deadline/cancel，故重启active wait必须新增PG join projection，不能用worker clock猜。
- `Host.cancel_run`只写协作式cancel intent；`cancel_run_and_settle`是CLI/process强收敛路径，正常worker不得调用。

## 3. Controller裁决映射

| ID | Finding | 裁决 | Target closure |
| --- | --- | --- | --- |
| S22-AUDIT-001 | schedule持久状态/owner/allowlist缺失 | ACCEPTED / FIXED IN PLAN | S22-CTRL-001、§3、§5 |
| S22-AUDIT-002 | handler invocation缺失 | ACCEPTED / FIXED IN PLAN | S22-CTRL-003、§6.1 |
| S22-AUDIT-003 | tenant selector/authority边界缺失 | ACCEPTED IN PART / SELECTOR FIXED / AUTH DEFERRED | S22-CTRL-002、Slice7.1/8.2 |
| S22-AUDIT-004 | active Host deadline/cancel不闭合 | ACCEPTED / FIXED IN PLAN | S22-CTRL-004、§6.2 |
| S22-AUDIT-005 | queue config/dependency/profile冲突 | ACCEPTED / FIXED IN PLAN | S22-CTRL-005、§4 |
| S22-AUDIT-006 | async handler与sync store/Redis边界未定义 | ACCEPTED / FIXED IN PLAN | S22-CTRL-006、§7 |
| S22-AUDIT-007 | startup/recovery/close顺序未定义 | ACCEPTED / FIXED IN PLAN | S22-CTRL-007、§8 |
| S22-AUDIT-008 | master Slice2.1状态陈旧 | ACCEPTED / FIXED IN MASTER | Slice2.1=`CODE ACCEPTED AT 38ddad4` |

## 4. 需要独立review重点攻击的假设

1. occurrence outbox是否真的关闭cursor commit→enqueue与enqueue→mark两个崩溃窗口，特别是Redis hint可能早于occurrence mark时。
2. croniter naive local candidate + ZoneInfo round-trip规则是否对nonexistent/ambiguous local time逐字确定；bounded lookback是否会无审计跳fire。
3. integration profile是否会被ordinary startup误接受，或让production绕过Redis admission。
4. async handler task、sync store/Redis `to_thread`、heartbeat与signal drain是否存在线程/资源泄漏、假terminal或lease停止过早。
5. execution request是否完全排除raw lease token/fence/worker id，handler是否仍能绕过Service finalize。
6. Agent governance projection是否由PG clock/tenant join闭合；Host cancel send failure、missing/active/terminal race是否会进入generic recovery或第二attempt。
7. Redis运行态是否只在REDIS admission构造，并严格消费settings阈值/健康间隔；POSTGRES_ONLY是否零Redis调用且保持同一PG claim/fencing。
8. Redis-first admission能否在existing startup call graph中真实早于PG/S3/Host/workspace副作用，而不是只在platform CLI表面早。
9. fixed dependency ranges与Redis 8.4 digest是否能在Python3.11 min/current/offline四平台locks解出。
10. target allowlist是否仍漏migration runner、package lock、CI或production mapping owner；若漏应在plan review修复，不能留给implementation自行扩。

## 5. Review要求

- Terra：做architecture/state-machine/adversarial challenge，输出独立plan review artifact。
- MiM与MiMo：各自独立核对exact owners、call graph、failure windows、tests/validation/stop；不得互相抄结论。
- 任一路发现H/M/L时，Controller逐项ACCEPT/REJECT/DUPLICATE/DEFER并只修改plan/artifact；fix后两路重新review至open0。
- plan accepted不代表代码已写；accepted plan baseline必须先形成local commit，之后才把exact target交给DeepSeek Flash实施。

## 6. 初审与Controller修订

- Terra：`docs/reviews/plan-review-20260812-slice-2.2-scheduler-worker-redis-terra.md`，FAIL/open 5/4/0。
- MiM：`docs/reviews/plan-review-20260812-slice-2.2-scheduler-worker-redis-mim.md`，PASS-WITH-RISKS/open 0/3/2。
- MiMo：`docs/reviews/plan-review-20260812-slice-2.2-scheduler-worker-redis-mimo.md`，FAIL/open 0/4/2。
- Controller：全部H/M及有实质边界的L已接受并修订；Terra提出的materializer lease/fence实现建议仅拒绝该手段，改以durable MATERIALIZING + immutable snapshot + atomic concurrent enqueue收敛达到同一安全目标。完整逐项裁决见`docs/reviews/plan-fix-20260812-slice-2.2-scheduler-worker-redis-codex.md`。
- 最终 closure：Terra `...-final4-terra.md`、MiM `...-final4-mim.md`、MiMo `...-final4-mimo.md`均PASS/open0；锁定语义正文SHA-256为`65357054b7c70ce36d664ca30ec8f71e2f89dec23223a58b0802ea3457082079`。

## 7. 当前开放状态

- Plan findings open H/M/L：`0/0/0`；全部历史finding与最终pagination finding均CLOSED。
- Code findings：N/A；production implementation尚未开始。
- Live/network/broker/model execution：未授权且未运行。
- Push/PR：未授权且未运行。
