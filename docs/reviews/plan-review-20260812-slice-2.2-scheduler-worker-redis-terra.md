# Slice 2.2 Scheduler / Worker / Redis：Terra 独立计划复审

- **Gate**：Gateflow-governed dual plan review（仅计划审查，未启动 Gateflow）。
- **角色与边界**：独立架构/状态机审查；仅检查 target、master、handoff 与 `38ddad4` 基线事实。本 artifact 是唯一新增文件；未修改 production、tests、README、dependency、CI、target 或 master。
- **系统时钟时间**：2026-08-12 01:38:36 +0800。
- **基线**：`38ddad489f4f9cfa1ae2a4373d69a628e49578bf`。
- **完整读取**：根 `AGENTS.md`、target `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`、master `docs/plans/2026-08-10-investment-platform-restoration.md`、handoff `docs/reviews/plan-handoff-20260812-slice-2.2-scheduler-worker-redis-codex.md`，以及下列直接相关基线代码、迁移、测试、CI 与已接受的 PG16 lane 勘误。
- **结论**：**FAIL**。
- **Open H/M/L**：**5 / 4 / 0**。

## 动机判断与审查结论

动机成立：把 scheduler cursor、occurrence、job、lease 与 receipt 保持为 PostgreSQL
真源、把 Redis 限为 hint，是正确的架构方向；`fold=0` 与 nonexistent-local-time
skip 也避免了双跑 DST fire。问题不是需要另起队列或把 Redis 升格为真源，而是 target
尚未给 occurrence materialization、deadline cancel、async drain 和真实 lane 足够的
线性化/资源所有权/可执行验证合同。因此当前不能称为 code-generation-ready plan，也不能
解除 implementation freeze。

以下 finding 均来自基线的直接代码或 target 的缺失语义，不以未运行的测试结果代替根因。

## Findings

### TERRA-S22-001 — occurrence outbox 未关闭第二崩溃窗口及并发线性化（高）

- **位置**：target §2 `S22-CTRL-001`（30–42）、§5.1–§5.3（175–208）、§7.4（280–282）、§10（355–363）。
- **直接证据**：计划把 `JobService.enqueue()` 的 PG commit 与 `mark_enqueued()` 分为两个事务；occurrence 仅保存 schedule/version/fire/idempotency/job_id 等字段，`job_id` 只在 mark 后绑定。与此同时 disable 会把尚未 enqueued 的 pending occurrence 标成 `skipped`，且两个 scheduler 可以同时读取 pending。

  基线 `JobEnqueueRequest` 还包含 descriptor、canonical payload、`available_at`、`deadline_at`（`dayu/investment/domain/jobs.py:1020-1054`）；其 idempotency fingerprint 覆盖 descriptor 七字段、payload schema/version/hash 与两个时间（`dayu/investment/storage/postgres_jobs.py:2635-2673`）。target 的 occurrence schema 没有冻结这些输入，也没有定义 schedule update contract，却要求 `test_schedule_update_and_activation_require_exact_version`。

  更关键的是，基线 `PostgresJobStore.enqueue` 对 job run 先 `SELECT`（850–862）再普通 `INSERT`（876–906），冲突时 rollback 后原样抛出（927–929），不是原子地返回同一 receipt。因此两个 replay worker 同时读到 pending 时，败方可能得到 unique violation，而不是 target 所声称的同一 job/replay 收据。
- **反例**：

  1. scheduler A 已提交 job，尚未 mark occurrence 就崩溃；operator disable schedule 后把 pending occurrence 标为 skipped。恢复方既无持久 job 绑定，也没有按不可变 enqueue identity 查询/reconcile 的协议，结果是 `skipped` occurrence 旁遗留可 claim 的 ready job。
  2. scheduler A 读到 pending 后，scheduler B 先 disable/skip；A 随后仍提交 enqueue，mark 才发现状态冲突。计划未定义 disable 与 in-flight materialization 谁线性化获胜。
  3. crash/replay 前后 schedule payload/descriptor/deadline 或由时钟派生的 enqueue 字段不同，同一个 key 无法保证 fingerprint 相同；重放会 conflict，或在不同 definition 下生成第二 job。
- **精确计划修复**：在 target 中把 occurrence 变为完整的 durable materialization protocol，而不是只补测试：

  1. 在 `reserve_occurrence` 同事务冻结可重建的完整 `JobEnqueueRequest`（或逐字段 canonical snapshot + digest），包括 descriptor、canonical payload、`available_at`、`deadline_at` 与确定性 idempotency identity；明确 schedule update 是禁止变更 enqueue 输入，还是新 revision，且已 pending occurrence 永远只重放旧 snapshot。
  2. 增加持久 `materializing` 状态、materialization owner/fence 与可回收 lease；明确 pending -> materializing 与 disable 的行锁/CAS 是唯一线性化点。disable 只能 skip 尚未取得 materialization ownership 的 occurrence；已取得 ownership 的 occurrence 必须按同一 snapshot 收敛成 `enqueued` 或由 lease-recovery 重放，不能标作 skipped 后留下 job。
  3. 明确 `PostgresJobStore.enqueue` 的 job-run idempotency 为原子 conflict-re-read/fingerprint 校验：相同请求并发必须都返回同一 `JobEnqueueReceipt`，不同 fingerprint 才返回 closed conflict；`mark_enqueued` 只接受同一 fence/job 的幂等完成。
  4. 同步扩写 DTO、`ScheduleStoreProtocol`、0004 state/CHECK 与 recovery/disable state table；不得用 Service 内存锁、删除 occurrence 或“遇错重试”替代。
- **必要验证**：保留既有两个 crash test，并新增至少：

  - `test_crash_after_enqueue_before_mark_replays_frozen_request_and_reuses_one_job`；
  - `test_disable_after_enqueue_commit_before_mark_reconciles_without_orphan_job`；
  - `test_disable_racing_pending_materialization_has_one_linearized_outcome`；
  - `test_concurrent_pending_replay_reuses_one_job_and_marks_one_occurrence`（真实 PG16 双 engine/barrier；基线 `tests/integration/investment/test_postgres_jobs.py:667-703` 已有可复用模式）。

### TERRA-S22-002 — misfire 的主要中间区间没有状态转移（高）

- **位置**：target §5.1（183–185）、§5.2（191–197）、§4.1（131–143）。
- **直接证据**：target 只定义了 `database_now - next_fire_at <= misfire_grace_seconds` 时 materialize，以及 cursor 早于 max-lookback 时写 `lookback_exceeded` skipped occurrence。对 `misfire_grace_seconds < age <= schedule_max_lookback_seconds` 没有 state、skip reason、cursor 推进、`scheduled_for` 或 `coalesced_count` 规则；“总候选数有固定上限”也没有配置字段或固定值。
- **反例**：cron 每十分钟、grace 为 60 秒、进程停五分钟、lookback 为七天。当前 fire 不可 materialize，也不属于 lookback 分支；实现者只能擅自选择重复空转、无审计推进 cursor，或虚构 skip record。这三种行为对重启和审计都不同。
- **精确计划修复**：新增 closed `misfire_expired` skip reason；规定它与 `lookback_exceeded` 的优先级、边界包含关系、聚合 skipped occurrence 的确定性 `scheduled_for`/`coalesced_count`、同一事务的 cursor 变化和 UTC 严格单调性。把候选扫描上限设为有名字的 exact positive config/constant，并定义命中上限后的固定 outcome；同时定义 activate/re-enable 的首个 `next_fire_at` 计算。DST round-trip 后所有这些规则必须仍以 PG `database_now` 为唯一时间真源。
- **必要验证**：

  - `test_scheduler_skips_misfire_past_grace_before_lookback_and_advances_cursor`；
  - `test_scheduler_misfire_boundary_is_inclusive_and_dst_cursor_is_monotonic`；
  - 扩展 `test_scheduler_coalesces_misfire_with_bounded_lookback`，覆盖每分钟 cron、扫描上限、spring gap、fall fold 与重启后的同一 audit record。

### TERRA-S22-003 — correlated Host deadline 会被 Slice 2.1 heartbeat 提前终态化（高）

- **位置**：target `S22-CTRL-004`（56–60）、§6.2（241–245）、§7.3（269–278）。
- **直接证据**：target 承诺 PG cancel/deadline 时调用 `Host.cancel_run()`，但 worker 只在每个 poll 的 claim 前 govern；handler active 时 heartbeat conflict/deadline 只设置业务 cancellation signal。

  基线 heartbeat 在 `clock_now >= deadline` 时直接写 PG failed terminal，再抛 `JobDeadlineExceededError`（`dayu/investment/storage/postgres_jobs.py:1214-1242`）。现有唯一 correlation 枚举只选择已过 lease 的记录（2045–2079），而正在 heartbeat 的 attempt 不会过 lease。基线 recovery 也只从该 expired list 开始（`dayu/services/job_service.py:430-465`）。因此 deadline 先于 lease expiry 到达时，active Host run 不会收到 cancel；之后 PG 已 terminal，target 的 planned governance 亦无定义能补发 cancel。

  `Host.cancel_run()` 本身只写协作式 `cancel_requested_at`、不推进 terminal（`dayu/host/host.py:839-861`），所以“只设本地 cancellation signal”不能替代 Host cancel。基线 reconciliation 测试还明确现有顺序为 cancel -> deadline -> Host outcome（`tests/integration/investment/test_postgres_jobs.py:1858-1871`），target 没有说明 correlated active run 如何改变该既有优先级。
- **精确计划修复**：定义独立、tenant-scoped 的 `list_governable_agent_runs` / `govern_claim` PG predicate，覆盖**仍持有效 lease**的 correlated active run；它必须把 PG cancel intent 与 PG deadline 纳入同一 projection。对该分支规定：先取得 durable governance decision，再以 `Host.get_run` strict observe；active 且需 cancel 时调用 `cancel_run`，返回 terminal/KeyError/竞争状态均立即 re-observe 并走 correlation reconcile；发送失败不改 PG、不建新 attempt，按固定 interval 重试。

  同时明确修改 heartbeat/reconcile 的 correlated deadline precedence：不能让 generic heartbeat 在 Host cancel dispatch 前把 correlated job 直接 terminalize。须在计划中写出 fence/重读顺序和 `job_cancel_requested_at` 与 `host_cancel_requested_at` 的不同字段含义，而非实施者自行分支。
- **必要验证**：

  - `test_governance_deadline_before_lease_expiry_requests_host_cancel_once`；
  - `test_correlated_deadline_does_not_follow_generic_heartbeat_terminalization`；
  - `test_host_terminal_between_observe_and_cancel_reconciles_without_new_attempt`；
  - 将既有 terminal-priority 测试拆为 generic 与 correlated 两条合同。

### TERRA-S22-004 — `to_thread` / handler / heartbeat / drain 没有真实 inner-work 所有权（高）

- **位置**：target `S22-CTRL-006`（68–72）、§7.2–§7.5（255–286）、§12（425–428）。
- **直接证据**：target 要求全部同步 PG/Redis 调用经 `asyncio.to_thread`，却在 grace 到期时取消 handler task、停止 heartbeat、关闭 Redis 和 prepared runtime 并退出。它只给 connect/socket timeout，没有规定 `PubSub.get_message` 单次等待上界、in-flight thread future 的 owner/reap 规则、late completion 行为或 close-before-thread 的禁止顺序。

  基线已经对同类问题作过明确处理：CN download 的 docstring 直接说明 outer cancellation 不会中断已启动的 `to_thread` worker，并以 inner owner/done callback 管理 late work（`dayu/fins/pipelines/cn_download_filing_workflow.py:132-147,952-969`）；Host 资源释放也用 shield/while-not-done 收口线程工作（`dayu/host/executor.py:1682-1698`）。target 没有等价合同。非协作 handler 捕获 `CancelledError` 时同样可以在 grace 后继续访问共享 runtime。
- **反例**：SIGTERM 到达时 `to_thread(PubSub.get_message)` 或同步 heartbeat 已进入阻塞调用；外层 task 取消并不停止线程，随后计划关闭其 Redis/PG/runtime。结果可能是 late store access、close race、假定已退出的进程仍被默认 executor 阻塞，或 handler 迟到 finalize。
- **精确计划修复**：在 worker/scheduler 状态机中为每一个 handler、heartbeat、PG call 与 PubSub `to_thread` future 定义唯一 owner、至多一个 in-flight 同步调用、停止接受新 work、await/reap 与 resource close 的顺序。PubSub 必须使用有界 `get_message(timeout=...)`，并把该上界与 `shutdown_grace_seconds` 的关系写死。

  对非协作 handler 必须二选一并改变完成定义：要么 close 前等待其真实结束（grace 只是停止 intake 的软界限，不承诺 bounded exit），要么使用明确的可强制终止子进程边界；不能同时宣称固定 grace 后安全退出和零 late shared-resource side effect。不得把 `Task.cancel()` 当作线程取消。
- **必要验证**：

  - `test_worker_sigterm_while_pubsub_get_message_blocks_has_bounded_drain`；
  - `test_worker_grace_expiry_with_blocked_heartbeat_has_no_late_store_or_close_race`；
  - `test_worker_grace_expiry_with_noncooperative_handler_leaves_no_false_terminal`；
  - 扩展真实 subprocess SIGTERM test，覆盖 Redis disconnect/in-flight PubSub，而不只覆盖空闲路径。

### TERRA-S22-005 — 真实 PG16/Redis gate 会重现已接受的 session-cluster role 污染（高）

- **位置**：target §3（101–104）、§10（397）、§11（405–407）。
- **直接证据**：target 要求 five-file PG/Redis integration 与 “per-file isolated PG16 process/container”，但 gate 只写“三个独立 process lane”，没有文件到命令的映射。当前两个 workflow 都是单一 `pytest -m "integration and not e2e"`（`.github/workflows/ci-pr-extended.yml:29-35`、`.github/workflows/ci-mainline.yml:107-113`）；PG fixture 是 session-scoped cluster（`tests/integration/investment/conftest.py:590-612`），并且镜像缺失时 hard fail、不自动 pull（196–213、310–315）。

  这不是推测：已接受的 Slice 2.1 勘误记录了同一模式已产生 `63 passed / 35 failed`，根因是 cluster-global `dayu_platform_app` role 跨文件残留；其唯一接受修复是三条独立 pytest process（`docs/reviews/plan-fix-20260811-slice-2.1-pg16-lane-isolation-codex.md:11-32`）。
- **精确计划修复**：target §10/§11 和两份 CI workflow 必须给出可复制的 exact command contract：migration、identity、jobs、schedules、Redis wakeup 五个文件均各自在新的 pytest process/PG16 container 中运行；聚合 integration 命令必须排除这五个文件，防止它们随后再次共享 session cluster。CI 在这些命令之前显式 pull 现有 PG16 digest 和 target 规定的 Redis digest。将所有必需命名的 migration/RLS/race/Redis tests 映射到这五条命令；“三个 lane”不得保留。

  同时，target 声称 migration static DDL gate，却没有允许既有 owner `tests/investment/test_platform_migrations.py`（它当前承载 0003 静态 DDL contract，734–869）。把该文件加入 exact allowlist，并在其中放 0004 静态 DDL contract；不要把纯静态 DDL 检查伪装成 real integration。
- **必要验证**：CI 只以每条独立 process 的真实 exit code 判定；不能依靠 test order、`-k`、skip、共享 cluster cleanup 或 masked aggregate exit code。

### TERRA-S22-006 — occurrence DDL 没有写出 tenant-closed referential/state contract（中）

- **位置**：target §5.3（201–208）、§10（363–365）。
- **直接证据**：计划只写 occurrence 的两个 unique 和“FK organizations”，没有规定 `(tenant_id, schedule_id)` -> `job_schedules(tenant_id, id)`、`(tenant_id, job_run_id)` -> `job_runs(tenant_id, id)` 的 composite FK，也没有列出 `pending/enqueued/skipped` 与 nullable `job_run_id`/`skip_reason` 的互斥 CHECK。它却要求 real PG16 验证 tenant-scoped FK。

  基线 durable job DDL 对 tenant-contained relationship 已使用 `UNIQUE(tenant_id,id)` 与 composite FK（`0003_durable_jobs.py:200-210,281-284`）；因此这不是抽象偏好，而是本 slice 需要延续的 RLS/tenant invariant。
- **精确计划修复**：在 §5.3 列出 schedule/job 的 composite FK、`ON DELETE RESTRICT`、父表 `(tenant_id,id)` unique、各 state 对 `job_run_id`/`skip_reason`/materialization 字段的 exact CHECK，及不可变列 guard。真实 PG16 test 必须直接插入 cross-tenant FK 和非法 nullable/state 组合并确认拒绝。

### TERRA-S22-007 — Redis-first 成功路径缺少唯一 typed preparation/lifecycle contract（中）

- **位置**：target `S22-CTRL-007`（74–78）、§3（98）、§8（299–307）。
- **直接证据**：target 规定 Redis admission 必须早于 DSN、engine、S3、Host、workspace，并要求 prepared runtime 直接保留 typed `JobService` / `ScheduleService`，不能从 mapping cast 取回；但没有给出哪个 preparation API、return type、publisher 注入点与 reverse-close owner 实现它。

  基线 `PreparedHostRuntimeDependencies` 只持有 generic platform composition，没有 Job/Schedule/Redis typed refs（`dayu/services/startup_preparation.py:170-212`）；当前 call graph 先作 S3 admission/head，再建 PG provider，随后才构造 Host 和 provider mapping（776–922），且 `_build_production_services_provider` 目前只产生 identity/jobs（381–416）。production profile 又要求四个 infra env（`dayu/investment/config.py:86-127`），而 target 的 real PG+Redis tests 未说明是完整 production startup（含 S3 lifecycle）还是仅 queue wire test。现有失败路径测试不能证明成功路径的顺序。
- **精确计划修复**：在 `startup_preparation.py` 指定一个且仅一个 queue-preparation contract（扩展现有 prepared result，或同模块新增 typed `PreparedPlatformQueueRuntime`）：Redis admission 成功后才进入既有 runtime preparation；该 contract 以窄 publisher 注入 JobService，直接保存 typed job/schedule/Redis refs，并拥有失败和正常退出的逆序 close。`startup/platform.py` 只能调用该 contract，不能建立第二 composition root。

  计划还须二选一写明 real-test topology：完整 production profile 则列出受控 S3 service/double 的 owner/lifecycle；若 PG+Redis lane 只验证 queue wire，则不得把它表述为完整 production startup，另以 production-profile call-order test 覆盖 Redis -> S3 -> PG -> Host/workspace 的成功路径。
- **必要验证**：

  - `test_queue_preparation_admits_redis_before_existing_runtime_preparation`；
  - `test_queue_preparation_exposes_typed_job_and_schedule_services_without_mapping_cast`；
  - `test_queue_preparation_failure_closes_resources_in_reverse_dependency_order`；
  - `test_production_queue_real_redis_admission_precedes_postgres_s3_host_and_workspace_initialization`。

### TERRA-S22-008 — 依赖真源与 `uv.lock` allowlist 直接冲突（中）

- **位置**：target §3（100）、§4.2（156–161）；master `S11-CTRL-01`（1368–1380）。
- **直接证据**：target 把 `uv.lock` 列为 redis/croniter 的“唯一” resolver pin owner；但仓库 `.gitignore:26` 忽略 `uv.lock`，当前也不受 Git 跟踪。master 明确规定安装真值是 pip constraints，禁止把被忽略的 `uv.lock` 或新 lock tool 作为真源；现有 CI action 也是 `pip install ... -c <constraints>`（`.github/actions/install-locked-env/action.yml:5-16`）。
- **影响**：实施者即使修改本地 `uv.lock`，CI/commit 不会获得该变更；计划的 min/current/offline/four-platform 可复现性无法由该文件验证。
- **精确计划修复**：从 allowlist、resolver 流程和验证文字删除 `uv.lock`；明确 `pyproject.toml` 加窗口，`constraints/min-py311.txt` 与 `constraints/lock-common-py311.txt` 加 direct exact pins，四个平台 lock 仅在 resolver 证明必要时改变。CI/offline bundle 只消费这些 tracked constraints，不引入第二 lock truth。

### TERRA-S22-009 — “显式 scope”不是本 slice 的 tenant authority（中）

- **位置**：handoff §3（39–45）；target `S22-CTRL-002`（44–48）；master（1063–1068）；`dayu/investment/domain/identifiers.py:205-259`。
- **直接证据**：handoff 把 `tenant authority 缺失` 标成已由 `S22-CTRL-002` 修复；target 实际只是接收任意 CLI UUID、构造固定 `Principal`，并把 roster/service-account authentication 明确延期。基线 `Principal` 是公开构造器，文档明说不是认证 capability；`TenantScope` 也只是 API misuse guard。RLS 会隔离已写入 `app.tenant_id` 的 scope，但不会证明启动该 process 的人获授权操作该 UUID。
- **判断**：这不强迫 Slice 2.2 偷渡 RBAC。若唯一 threat model 是外部已授权的 process manager，则 one-process/one-explicit-tenant 是合理收缩；但当前不能把它称为“tenant authority 已修复”，且不能把 selector 单测当认证证明。
- **精确计划修复**：将 handoff/target completion wording 改为：本 slice 只固定显式 canonical tenant selector 与无 global claim；**外部 operator/process-manager 对 tenant 的授权是前置条件，未由本 slice 实现或验证**。把该前置条件、credential owner、无此部署保证时的 STOP/不启动规则写入 CLI operator contract。若 Controller 不接受外部 trust boundary，则应 defer daemon CLI 到 Slice 7.1/8.2，而不是让实现者发明伪 service principal。保留 CLI test 证明不从 payload/channel/workspace 推断 tenant，但不新增“授权已验证”的伪测试。

## 已核对但未形成 finding 的点

1. PostgreSQL 为 queue truth、Redis 为 post-commit tenant-scoped hint 的方向正确；target 对重复/乱序/丢失 hint 不改变 claim/fence 的约束足够明确。问题只在 runtime shutdown/成功 startup contract，见 TERRA-S22-004/007。
2. DST nonexistent skip 与 ambiguous `fold=0` 的局部选择明确；阻塞点是它们在 misfire/cursor/audit 边界的持久化闭合，见 TERRA-S22-002。
3. descriptor-only registry 与 production handler 空集合保持了 Slice 2.1 的 Service/Host 边界；本审查未发现应把业务 handler 或 Redis import 下沉到 storage 的理由。

## 建议的 Controller 收口顺序

1. 先裁决 TERRA-S22-001 至 005；它们是 implementation-blocking high findings。
2. 只修改 target、master 必要状态/指针与 Controller plan-fix artifact，补齐 TERRA-S22-006 至 009；不得让 implementation worker 在冻结期自行扩 allowlist 或发明 authority/second composition root。
3. 修正后重新运行独立 Terra 与另一独立 reviewer 的 plan re-review，只有 open H/M/L=0/0/0 才解除 target 的 implementation freeze。

## 验证记录

- 只读静态审计：target/master/handoff、`38ddad4` 基线的 JobStore/JobService/Host/startup/config/domain、0003 migration、PG16 integration fixture/tests、CI workflow、constraints/ignore 规则和 Slice 2.1 已接受 PG16 process-isolation artifact。
- 未运行 pytest、pyright、Ruff、Docker、Redis、PostgreSQL、模型、broker 或任何 live/provider action。
- 未 commit、push、创建 PR 或启动 Gateflow review。

## 最终结论

**FAIL，open H/M/L = 5/4/0。** 当前 target 的基本分层和 Redis-as-hint 方向可保留，但 outbox 需要真实的持久线性化与 immutable request replay；misfire、deadline governance、thread drain 和 real integration lane 也必须先被写成精确、可验证的计划合同。在这些 finding 关闭并经双路 re-review 前，Slice 2.2 implementation 必须继续冻结。
