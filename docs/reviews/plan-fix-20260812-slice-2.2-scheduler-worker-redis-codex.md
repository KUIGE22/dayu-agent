# Slice 2.2 Scheduler / Worker / Redis — Controller Plan Fix

- **状态**：`ACCEPTED / TERRA + DUAL FINAL4 PLAN RE-REVIEW PASS / CLOSED`
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **master**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **handoff**：`docs/reviews/plan-handoff-20260812-slice-2.2-scheduler-worker-redis-codex.md`
- **代码基线**：`38ddad489f4f9cfa1ae2a4373d69a628e49578bf`
- **边界**：本次只修计划/Controller artifacts；production、tests、README、dependency、CI继续冻结。未运行Redis/PostgreSQL容器、模型、provider、broker或live action。

## 1. 结论先行

三路初审及后续closure复审的实质缺口均已在target plan中形成可编码合同；Terra、MiM、MiMo final4均PASS/open0，本Controller fix现已关闭。

本次最重要的架构修订：

1. occurrence从`pending`直接外部enqueue改为`pending -> materializing -> enqueued`。`materializing`是持久的不可撤销入队承诺；disable只能skip仍为pending的行。
2. reserve事务冻结完整`JobEnqueueRequest` identity；replay的`available_at/deadline_at`只由persisted scheduled time派生，禁止读取当前时钟。
3. `PostgresJobStore.enqueue`必须把同fingerprint并发冲突原子收敛为同一job/receipt；不能泄漏unique violation。
4. misfire的grace与lookback中间区间、candidate scan上限、DST边界和activate/re-enable cursor均有明确持久状态。
5. correlated active Host run在lease仍有效时也进入PG治理；heartbeat不能在Host cancel/reconcile前抢先写generic deadline terminal。
6. 首信号grace改为cooperative soft boundary；所有`to_thread`/handler inner work先真实reap再close，第二信号才是无假terminal的process hard stop。
7. startup用两个public wrapper共享一个typed private composition root，Redis admission真实早于path/S3/PG/Host/workspace。
8. 五个PG/Redis integration文件逐个独立pytest process；`uv.lock`从交付真源删除。

## 2. Terra findings 裁决

### TERRA-S22-001 — ACCEPTED / FIXED IN PLAN

finding成立：旧pending outbox不能闭合disable/enqueue/mark竞态，snapshot与并发job enqueue也未冻结。

修订：

- 新增`MATERIALIZING`、完整snapshot、state/CHECK/composite FK与列级UPDATE权限。
- disable与begin按schedule->occurrence同一锁序线性化。
- 同key并发enqueue使用数据库conflict-do-nothing + fingerprint re-read。
- 新增crash、disable race、concurrent replay、byte-identical request与unique conflict命名测试。

Terra建议的materializer owner/fence/lease仅该具体手段为`REJECTED-WITH-REASON`：lease到期仍可能并发外部enqueue，并额外引入时钟/续租/orphan状态；immutable snapshot + atomic job idempotency已使任意并发replay安全收敛。target明确多个scheduler可重放同一materializing occurrence，并以同job mark幂等闭合，因而无需伪造单进程ownership。

### TERRA-S22-002 — ACCEPTED / FIXED IN PLAN

新增`misfire_expired`、`lookback_exceeded`、`candidate_scan_limit_exceeded` closed reasons；明确grace等号边界、lookback跳转audit、最多三项reservation batch、exact count/None语义、strict UTC cursor、candidate scan limit、activate/re-enable首个future fire及pinned croniter empirical pre-edit gate。

### TERRA-S22-003 — ACCEPTED / FIXED IN PLAN

新增覆盖有效lease的`list_governable_agent_runs`；projection拆分`job_cancel_requested_at`与Host cancel intent。correlated heartbeat在deadline/cancel时续lease并返回governance-required，不再走generic terminalization；Worker在heartbeat前后Host observe/cancel/reobserve/reconcile。generic无correlation deadline语义保持Slice2.1不变。

### TERRA-S22-004 — ACCEPTED / FIXED IN PLAN

新增每个handler/heartbeat/PG/Redis future唯一owner、同类至多一个in-flight、有界PubSub wait、outer cancel不代表inner cancel、close前真实reap。首信号grace只承诺cooperative drain；非协作inner work继续heartbeat/保留runtime，第二信号才由process boundary hard-stop且不写假terminal。拒绝同时承诺不可能兼得的首信号硬时限与零late side effect。

### TERRA-S22-005 — ACCEPTED / FIXED IN PLAN

新增`tests/investment/test_platform_migrations.py` allowlist。migration/identity/jobs/schedules/Redis五个integration文件逐个独立pytest process与独立session cluster/container；workflow aggregate命令必须逐一`--ignore`，不重复共享cluster。真实exit不得由`-k`、order、skip或masked shell status替代。

### TERRA-S22-006 — ACCEPTED / FIXED IN PLAN

0004现明确organizations FK、schedule/job composite tenant FK、`ON DELETE RESTRICT`、state/snapshot/job/skip exact CHECK、RLS、最小列级UPDATE、无DELETE及真实cross-tenant/invalid-state写入测试。

### TERRA-S22-007 — ACCEPTED / FIXED IN PLAN

startup固定`_PreparedQueueAdmission`、`PreparedPlatformQueueRuntime`、`_prepare_queue_admission`、`_prepare_host_runtime_after_queue_admission`及一个platform public wrapper。ordinary/platform wrapper共用同一private root；无callback/bool bypass、无special->ordinary二次调用。真实Redis+PG lane只称queue-wire test；另以production call-order integration覆盖Redis->S3->PG->Host/workspace。

### TERRA-S22-008 — ACCEPTED / FIXED IN PLAN

从allowlist/交付/验证删除ignored且untracked的`uv.lock`。唯一安装真源为`pyproject.toml`窗口和tracked pip constraints；min/common direct exact pins由resolver生成，四平台locks仅在证明有差异时改。

### TERRA-S22-009 — ACCEPTED IN PART / FIXED WORDING / DEFERRED AUTH OWNER

事实成立：canonical tenant selector不是认证。target/master/handoff不再声称authority已实现，改为外部已授权operator/process-manager与credential分发是启动前置条件；不能证明则STOP。无global claim/tenant inference仍是本slice硬边界。service account、tenant roster、RBAC与部署credential owner明确留Slice7.1/8.2，不发明伪Principal能力。

## 3. MiM findings 裁决

- **M-001 ACCEPTED / FIXED**：pinned croniter empirical pre-edit gate、New York/Shanghai exact samples与行为不闭合时STOP已加入；与Terra-S22-002同簇。
- **M-002 ACCEPTED / FIXED**：`ScheduleReserveAction={reserved,lost_race}`与`ScheduleReservationResult`精确返回；lost race零mutation，不泄漏IntegrityError；与Terra-S22-001同簇。
- **M-003 ACCEPTED / FIXED**：worker identity只用于PG attempt审计/metrics，禁止handler按临时worker身份分支业务side effect/idempotency，因此execution request排除worker_id。
- **L-001 ACCEPTED / FIXED**：settings loader接受并验证INTEGRATION；ordinary preparation在任何side effect前拒绝；仅platform preparation接收。与MiMo M-001/startup findings重叠。
- **L-002 ACCEPTED / FIXED**：四个共享CLI文件各自只允许mechanical parser/type/name/lazy-dispatch改动；所有runtime逻辑归`commands/platform.py`。
- **Open question CLOSED**：`HostRunCancellationProtocol`明确在`job_service.py`新增为runtime-checkable结构协议；同一Host实例满足reader+canceller。

## 4. MiMo findings 裁决

- **M-001 ACCEPTED / FIXED**：INTEGRATION只允许PG DSN，Redis/object/auth任一非空fail-fast，绝不ignored。
- **M-002 ACCEPTED / FIXED**：`ScheduleSkipReason`精确closed enum为`misfire_expired/lookback_exceeded/schedule_disabled/candidate_scan_limit_exceeded`；coalesced不是reason。
- **M-003 ACCEPTED / FIXED**：Redis-first具体调用图、typed admission/private root/close owner已固定；与Terra-S22-007同簇。
- **M-004 ACCEPTED / FIXED**：固定redis-py 8.1.x + Redis 8.4只走RESP2；真实wire lane不兼容立即plan-fix/re-review，禁止silent fallback或换digest。
- **L-001 ACCEPTED AS RESIDUAL / DOCUMENTED**：heartbeat无jitter保留lease safety上界；每worker一个attempt，部署错开启动，多进程PG峰值列residual。
- **L-002 ACCEPTED / FIXED**：disable race由durable materializing线性化闭合，不采用“enqueue后mark发现skipped再继续”的错误方案；与Terra-S22-001同簇。

## 5. Controller 额外收口

1. schedule registration内容注册后immutable；只允许activate/disable/cursor version变化。内容更新必须新schedule key，避免历史snapshot指向被覆盖定义。
2. replay exact timestamps固定为`available_at=scheduled_for`、`deadline_at=scheduled_for+job_deadline_seconds`；这是同key fingerprint稳定的必要条件。
3. `ScheduleMarkEnqueuedAction.skipped_conflict`不是正常竞态结果；出现即runtime invariant nonzero stop并保留现场。
4. local缺pinned Redis image不能把skip计作PASS；fixture不implicit pull，CI明确pull。
5. production source execution registry继续精确为空；本slice仅测试handler，Slice2.3才可注册首个业务handler。
6. `job_enqueue_request_fingerprint`移至pure jobs domain成为ScheduleService/PostgresJobStore唯一算法真源，禁止复制storage私有实现。
7. heartbeat public contract升级为closed renewed/governance-required result；correlated lease expiry不再cap到business deadline，complete/fail在未终结correlation时零mutation并进入持续heartbeat/reobserve状态。
8. governance query使用deadline/correlation keyset page并循环游标，避免长期active rows饿死后续终态/deadline。
9. grace-abandon先线性化再cancel handler；其后所有结果忽略。第二signal固定`os._exit(1)`，不把普通task cancellation误称thread termination。
10. typed admission增加NOT_REQUIRED/POSTGRES_ONLY/REDIS closed形状：NOT_REQUIRED只覆盖disabled/development ordinary路径；production显式provider仍必须先完成REDIS admission，只替换custom composition而不得绕过Redis，direct Job/Schedule refs可空且admission资源仍exact-once关闭；platform wrapper拒NOT_REQUIRED。
11. CI使用plain tracked-environment `pytest`，不是会依赖ignored lock的`uv run`；PG16与Redis两个digest都显式pull，workflow其它full lanes明确排除integration。
12. scan-limit达到时丢弃provisional groups，只写以pre-scan working cursor为identity的单一closed audit并disable；不入队partial eligible group。
13. Agent correlation所有写入口统一锁序为`job_runs -> job_attempts -> job_leases -> agent_run_correlations`；reconcile/recover只允许无锁locator后按顺序重锁并最终重读correlation，heartbeat/complete/fail在父行锁内late re-read，reserve在同一父锁内重验，闭合反向死锁与“锁前未发现correlation”竞态。Host missing只有lease已过期才可targeted recover；有效lease必须等待/reobserve。
14. availability gate只在线性化PENDING→MATERIALIZING前可否决；一旦MATERIALIZING，durable commitment经窄`enqueue_committed_schedule_occurrence`使用frozen snapshot/同一PG idempotency真源完成，registry后续漂移不能把occurrence永久卡住或伪造skip。
15. production显式provider保留custom composition兼容，但profile仍唯一决定REDIS admission；provider injection不能成为production queue admission的第三条绕过路径。
16. Terra corrective `TERRA-S22-RR-001`已接受：lookback重定位唯一语义为最早有效UTC candidate `C >= L`；以`L-1 minute`的naive local minute为seed并逐个DST分类，`C == L`必须进入grace分类，禁止严格`get_next(L)`造成无审计丢fire。
17. final consistency H1已接受：generic `recover(scope)`纳入同一job→attempt→lease→correlation锁序；候选SQL的`NOT EXISTS`不是授权真源，父行锁后必须late re-read correlation并在存在时零mutation，闭合reserve提交窗口竞态。
18. final consistency H2已接受：valid-lease missing Host进入`MISSING_HOST_WAIT`后停止该attempt续租，以persisted expiry为上界；Host出现才恢复heartbeat，expiry仍missing才targeted recover，消除当前owner永久续租。
19. final consistency M1已接受：scan limit只计DST分类前的raw naive-local croniter candidate；下限改为`ceil(lookback/60)+2882`并补跨spring-gap计数测试，闭合CPU guard单位与offset跨度。
20. architecture truth补强：`dayu/host/worker.py`与`scheduler.py`只声明Host-local structural gateway ports，禁止import`dayu.services`；startup从上层注入结构兼容的JobService/ScheduleService，保持`UI -> Service -> Host -> Agent`无反向依赖。
21. schema migration truth补强：允许`dayu/cli/workspace_migrations/platform_jobs.py`及对应test只同步0004/head说明，既有`upgrade head`行为不改且去docstringAST exact，避免新schema交付后init插件文档仍声称head仅含0003。
22. final consistency port finding已接受：Host-local `WorkerJobGatewayProtocol`与`SchedulerGatewayProtocol`现有逐方法closed signatures、sync/async边界与pure-domain返回类型；Scheduler只调用Service-owned replay/reserve/materialize高层入口，绝不拿Store facade。pyright structural assignment与分层import测试锁定JobService/ScheduleService无需import Host即可满足。
23. `TERRA-S22-FINAL-001`已接受：新增event-loop-owned `ProcessIntakeGate`/epoch作为首信号唯一线性化点。所有已派发、后返回的claim/list/reserve在启动下一项工作前重验epoch；gate后claim不启动handler/heartbeat，list/reserve不开始materialization，只有gate前已经派发的一个Service-owned materialization可以完整收口。
24. `TERRA-S22-FINAL-002`已接受：deployment `PlatformQueueMode`与Worker-owned `RedisRuntimeState`分离；仅REDIS admission构造event-assisted/degraded状态机且阈值/探活间隔逐字读取settings，3/30仅默认值。POSTGRES_ONLY state及全部Redis refs为None并以测试证明零construct/ping/subscribe/recovery。
25. final contract `M-NEW-001`已接受：`ScheduleMaterializationResult`新增closed result action；并发输家在begin时看到ENQUEUED只返回`already_enqueued + receipt=None`并验证persisted job id，零JobService/Redis/mark，不伪造缺失definition/idempotency字段的enqueue receipt，也不扩大read gateway。
26. `TERRA-S22-FINAL3-001`已接受：Worker所有poll/heartbeat治理调用精确经`asyncio.to_thread`传入keyword-only `limit=settings.governance_page_size`，并把返回`AgentRunGovernancePage.next_cursor`立即写回唯一process-local cursor；尾页None让下一次从头开始。新增非默认page-size/cursor轮转命名测试与STOP，禁止默认limit、双cursor或storage page泄漏。

## 6. Corrective re-review closure

1. Terra final4：`docs/reviews/plan-rereview-20260812-slice-2.2-scheduler-worker-redis-final4-terra.md`，PASS/open `0/0/0`。
2. MiM final4：`docs/reviews/plan-rereview-20260812-slice-2.2-scheduler-worker-redis-final4-mim.md`，PASS/open `0/0/0`。
3. MiMo final4：`docs/reviews/plan-rereview-20260812-slice-2.2-scheduler-worker-redis-final4-mimo.md`，PASS/open `0/0/0`。
4. 三路锁定target语义正文SHA-256=`65357054b7c70ce36d664ca30ec8f71e2f89dec23223a58b0802ea3457082079`，Controller逐项确认上述26项CLOSED。
5. target/master/handoff/fix状态已统一accepted；production/tests/README/dependency/CI在plan gate中相对`38ddad4`保持零diff。包含本闭环的本地plan baseline commit成功后可启动DeepSeek Flash implementation；仍不得push/开PR或运行provider/broker/live交易。
