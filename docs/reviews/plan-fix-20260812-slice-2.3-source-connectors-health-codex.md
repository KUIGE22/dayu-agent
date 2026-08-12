# Slice 2.3 corrective plan adjudication（Codex Controller）

- 日期：2026-08-12
- 状态：ACCEPTED / DEEPSEEK + MIMO FINAL PLAN RE-REVIEW PASS / CLOSED
- 基线：0db6c7b63608a15cd157f842a5be772799fdacd9
- 设计真源：docs/plans/2026-08-10-investment-platform-restoration.md
- 目标计划：docs/plans/2026-08-12-slice-2.3-source-connectors-health.md
- 初稿 SHA-256：b1c852ade68646f58bf43ffcb70308b589229c760796b265074f24a8d11c67b8
- 第一轮 corrective candidate SHA-256：281f0a753423df5142d76a9cf2597b143e8c32bea5f8d4c70a3e2c691b7f8e23
- 第二轮前 frozen SHA-256：``6a49a33af3bb4b515dce07fac5b8781746fefd591d88be49cf922239ddc52ff9``
  （Codex internal audit失败，不能继续复用）
- Round 2 frozen SHA-256：``62a4e3096a7335ac9da7cc473028ec5e9bd549b48d3f3ce647223c3f8b9b0f63``
  （后续Codex audit失败，不能继续复用）
- 最终复审锁定语义 SHA-256：``96bceb321464223c9022af25905ca36c4bfe5cdca371111384567acb396ee4f0``
  （ROUND 3 FINAL FROZEN；不得以此前SHA复审）
- acceptance metadata 写回后的目标文件 SHA-256：``7550c9e888fda5af4771cc92a7b716fefbeb08cfdb498fb114c88cf09624ef83``
  （只修改status/gate/review metadata，不改变最终复审锁定的合同语义）
- 初审 DeepSeek：docs/reviews/plan-review-20260812-slice-2.3-source-connectors-health-deepseek.md
- 初审 MiMo：docs/reviews/plan-review-20260812-122255-slice-2.3-source-connectors-health-mimo.md
- 第一轮 corrective DeepSeek：docs/reviews/plan-review-20260812-slice-2.3-source-connectors-health-corrective-deepseek.md（FAIL 1H/2M/1L）
- 第一轮 corrective MiMo：docs/reviews/plan-review-20260812-slice-2.3-source-connectors-health-corrective-mimo.md（PASS-WITH-RISKS，但列出2H/4M/2L，未达到open0）
- 最终独立复审 DeepSeek：docs/reviews/plan-rereview-20260812-slice-2.3-source-connectors-health-final-deepseek.md，artifact SHA-256 ``4a484ae0c1f702a65a6941e61e0643d17f653183a46c84fa2b737bdb1a4cf36d``，PASS/open ``0/0/0``。
- 最终独立复审 MiMo：docs/reviews/plan-rereview-20260812-slice-2.3-source-connectors-health-final-mimo.md，artifact SHA-256 ``a725900220b6d2614378713d545e63a583706f1a9a941d99598ebf7139f8b5d0``，PASS/open ``0/0/0``。
- 性质：Controller adjudication 与 corrective handoff；不是 code acceptance。

## 1. Controller 结论

初稿不能进入实现。DeepSeek 的2H/2M/5L、MiMo 的1M/2L均成立；另外真实代码核对发现
trusted TenantScope、date-only source truth、DownloadEvent identification、schedule occurrence
幂等、composite FK 和 source/Job 跨事务 crash closure等计划缺口。

纠正方案不扩 Worker、不引入通用prepared Job decision。本 Slice接受一个诚实边界：

- source terminal与Job terminal不做跨事务强一致；
- provider/business outcome一旦作为source observation提交，就以JobCompletion返回；
- 只有source commit前、无observation的closed execution failure进入Job retry；
- 最后attempt crash可能留下source truth成功而Job envelope失败，作为命名residual与测试；
- 若未来要求强一致，另开通用Job设计，禁止JobStore读取source表。

## 2. 初审finding裁决

| Finding | 裁决 | Corrective closure |
|---|---|---|
| DS23-001 retryable terminal阻断Fins重试 | ACCEPT | 删除RETRY_WAIT/per-attempt provider outcome重试。provider/business结果均source-terminal + JobCompletion；commit前基础设施错误才JobFailure。 |
| DS23-002 attempt row与旧idempotency unique冲突 | ACCEPT | 每Job只写一条producer source run；key=source-sync-attempt:v1:job:producer-attempt；后续attempt只重放，不插第二行。 |
| DS23-003 operation静态lease与heartbeat冲突 | ACCEPT | operation不存authoritative expiry；acquire/commit均按job->attempt->lease->operation锁序验证实时lease。 |
| DS23-004 deferred connector执行矛盾 | ACCEPT | deferred key可CRUD但不进production connector registry，不可manual enqueue/schedule，不产Job/health。 |
| DS23-005 outbox冲突回滚事实 | ACCEPT | 精确ON CONFLICT(tenant_id,dedupe_key) DO NOTHING；绝不回滚run/snapshot。 |
| DS23-006 handler非法返回CANCELLED | ACCEPT | handler永不返回CANCELLED；domain cancel映射SOURCE_INTERRUPTED，PG cancel intent仍由JobStore收敛。 |
| DS23-007 coverage不完整 | ACCEPT | 每个changed production module逐模块coverage>=80，另有exact changed-file static/full gates。 |
| DS23-008 MinIO locator门禁不精确 | ACCEPT | 加现有真实MinIO测试文件，FS/S3同fixture、canonical bytes/hash相同、readback通过、无路径字段。 |
| DS23-009 seal阻碍future handler | ACCEPT | 所有handler作为startup batch一次注册再seal；future slice修改composition batch，禁止unseal/runtime register。 |
| MiMo-0001 Registry Protocol缺seal/count | ACCEPT | Protocol与concrete同时加入seal/is_sealed/count；startup只通过typed contract使用。 |
| MiMo-0002 crash cut seam含混 | ACCEPT | 固定test-owned PG commit barrier与test-owned post-handler gateway；不加production seam、不sleep。 |
| MiMo-0003 old row migration兼容 | ACCEPT | 新列nullable；all-null旧row保持0001语义；all-nonnull新row受conditional CHECK；真实旧rowupgrade测试。 |

## 3. Controller新增finding裁决

### 3.1 Trusted TenantScope

现有JobExecutionHandlerProtocol只传JobExecutionRequest和cancellation，但repository要求不可公开
构造的TenantScope。纠正为execute(scope, request, cancellation)；JobService验证tenant identity并
传入同一个scope对象。八字段request保持不变，严禁重建Principal/scope或泄漏lease/token/fence。

### 3.2 Schedule recurring truth

现有ScheduleService的occurrence key已经包含schedule_id、schedule_version、scheduled_for；初稿
“第二occurrence复用第一Job”不成立。纠正为：静态scheduled payload合法；新增exact-idempotent
ensure_registered恢复draft response丢失；draft显式set_state激活，不伪造register+activate原子。

### 3.3 Source operation与Job crash

operation只有ACTIVE/TERMINAL并表示provider replay truth，不镜像Job state。live Job lease是唯一
租约真源。source commit后Worker crash若有next attempt则byte-identical replay；若deadline/max
直接终结则保留source truth且Job envelope可不同。计划禁止夸大为强闭合。

### 3.4 Fins date/no-change/locator

Fins三市场只持久化filing_date/report_date，不能提供source UTC timestamp。纠正为date +
calendar-day freshness。complete且documents=()（total=0或全部terminal classified ignored）才是
no_change/healthy；raw skipped若verified meta转为reused document则是succeeded，不能一概no_change。

locator只由DefaultFinsRuntime消费本次DownloadEvent terminal集合后，读取exact meta/primary bytes、
调用existing resolve + validate形成。禁止whole-repository scan、list_filings猜测或investment构造hash。

### 3.5 Event/cancellation/stream owner

固定MIC、form、reused/ignored reason闭集；unknown terminal/reason fail closed。asyncio取消原样传播，
domain cancel typed返回。runtime、Sec/Cn wrapper、ingestion service、backend、market workflow、
per-filing stream逐层finally aclose exact once，不依赖外层generator或GC隐式关闭。

### 3.6 PostgreSQL identity closure

0005新增operation/health head/semantic alert三表；source runs/snapshots只扩nullable兼容列。所有private
关系使用tenant+job/attempt或tenant+subscription完整composite FK；修复snapshot到run的弱FK；
subscription unique加入source_definition_id。downgrade对新business data与恢复旧index冲突均拒绝。

### 3.7 Health与alert

health head是唯一mutable current truth，snapshot/outbox append-only且同source terminal transaction。
disabled sticky，晚到并发observation保留run但不恢复/更新health。semantic alert不是delivery outbox，
恢复不发alert，物理通知留Slice7.6。

### 3.8 Corrective schema red-team

内部codegen模拟另发现：operation terminal FK可跨job混入同subscription的source run；alert可把
run R1与snapshot R2拼接；三新表列/guard/grant不够精确；计划还引用了不存在的
job_runs.current_attempt_id。全部接受并修正：

- operation用tenant+subscription+job+source-run四列FK；alert用含run+health-version+snapshot
  的五列FK；FK parent使用无predicate UNIQUE；
- 三新表逐列冻结类型/nullability/PK/unique/index/RLS/grant与transition guard，ORM metadata
  精确15->18；
- current attempt通过job_runs.current_attempt_number join job_attempts.attempt_number，再验证
  request attempt id、fence、unreleased lease与同一个PG clock；
- source run的旧/new conditional group、四count求和、latest date与每outcome status/error/retry
  CHECK逐项固定；health predicate修正为health_state_version；
- 无source commit而Job终结时保留ACTIVE物理审计，不伪造terminal；因本Slice无operation query consumer，
  不再发明或持久化retry_pending/abandoned/invariant-failure public projection。

### 3.9 第一轮 corrective MiMo findings 裁决

MiMo artifact的总标签``PASS-WITH-RISKS``与其正文open 2H/4M/2L不一致；Controller按finding正文逐项
裁决，不能把该artifact当pass：

| Finding | 裁决 | 本轮closure |
|---|---|---|
| CORR-001 lock order未指定 | REJECT factual misread | 第一轮target已经写明acquire/terminal共同逐行锁序；不采纳reviewer建议的表级LOCK。最终序列为job->job definition->attempt->lease->operation->subscription->source definition->security->health，Round 3进一步把每步冻结为``SELECT ... FOR UPDATE NOWAIT``与typed 55P03 mapping。 |
| CORR-002 FK parent UNIQUE ordering | ACCEPT | 增加完整0005 upgrade/downgrade DAG；每个parent UNIQUE先于child FK，reverse downgrade先child后parent。 |
| CORR-003 ingestion aclose规格缺失 | REJECT factual misread，独立底层问题另行ACCEPT | 第一轮target已列ingestion/service并要求每层direct-inner finally aclose；但真实调用链另发现遗漏Sec/Cn wrapper、market/per-filing owner，按DeepSeek/internal finding扩allowlist和exact chain。 |
| CORR-004 CHECK实现路径 | PARTIAL ACCEPT | 不接受“application validation/deferred trigger可替代”的建议；所有row expression冻结为named PostgreSQL CHECK，并另设insert guards只阻止新legacy shape。 |
| CORR-005 ensure_registered cron语义 | REJECT factual misread | 第一轮target已规定复用既有cron semantic validation、首次disabled draft、exact immutable compare；本轮仅补精确Service signature/helper名。 |
| CORR-006 handler可返回CANCELLED | ACCEPT | JobService全局把handler-returned CANCELLED映射既有HANDLER_REJECTED；只有PostgresJobStore persisted cancel intent生成generic CANCELLED。 |
| CORR-007 pipeline_backends不在allowlist | REJECT factual misread | 第一轮target §11已列该文件；无需据此扩scope。 |
| CORR-008 focused coverage含混 | PARTIAL ACCEPT | 冻结changed-module枚举、单module ``--cov``/branch/fail-under命令与module->tests->command->branch%证据，禁止aggregate掩盖。 |

### 3.10 第一轮 corrective DeepSeek findings 裁决

DeepSeek 1H/2M/1L均为真实代码事实并全部接受：

- live truth只用``job_attempts.lease_expires_at``；``job_leases.expires_at``是claim-time audit且
  heartbeat不更新，source acquire/terminal不得比较它；
- aclose allowlist/owner链加入SecPipeline、CnPipeline及真实market/per-filing forwarding layers；
- 两个source run partial unique index冻结exact name与``IS NOT NULL``predicate；
- handler提交source terminal后Worker cancellation后置门可把Job envelope映射HANDLER_REJECTED，作为
  显式residual和命名测试，绝不回滚source truth。

### 3.11 第二轮 internal code-generation findings 裁决

后续internal DTO/schema/wire/architecture red-team又发现会阻断代码生成的缺口，全部接受并写入target：

- 冻结所有Source DTO精确字段/type/nullability/action presence；terminal request只能携带typed Fins或
  no-provider candidate，最终UUID/PG clock/outcome/health/receipt/result/hash由repository锁内唯一生成；
- manual enqueue snapshot与locked current binding的漂移成为typed no-provider stale terminal；scheduled
  在acquire锁内冻结current binding，disabled为typed no-provider；terminal再次revalidate；
- terminal replay返回persisted byte-identical result/receipt且没有persistent replay marker，重放事实
  只由acquire action表达；
- DownloadEvent以nested filing_result为真源、flat mirror必须一致；CN/HK candidate_not_found特殊形状、
  pipeline terminal last/clean exhaustion、cancel/invariant/exception/clean EOF优先级与无typed rate-limit
  signal全部冻结；status=failed兼容现有default-zero summary并丢弃buffer，status=ok才做exact summary；
- HEALTH_ERRORS闭集、safe-error显式``IS NOT NULL``、source run/snapshot/outbox named row CHECK、new-insert
  guards、outbox跨表status/error repository invariant和legacy health preflight全部冻结；
- investment pure/domain现有architecture guard禁止``dayu.fins``。因此Source evidence改为investment-owned
  strict CanonicalJobDocument wrapper；FinsSourceConnector是唯一projection转换adapter，architecture新增
  closed connectors owner集合，未知path继续fail closed；raw projection hash与wrapper hash分别核验；
- Job definition UUID与Investment SourceDefinitionId分属不同命名空间，分别对各自locked parent验证，
  不做跨命名空间相等比较；manual tenant/version/window/payload hash/lineage forged input零source row；
- Fins request/result精确snake_case字段与outcome shape；Fins safe_error_code删除，adapter唯一映射Source
  error；public Source connector使用typed cancellation，callback只留FinsService-to-runtime局部兼容缝。
- operation只保留ownership/fence与terminal run FK，不复制business result；immutable source run增加
  canonical result JSON/hash，acquire replay沿FK读取run内persisted receipt/result；record_terminal不提供
  第二条idempotent replay route；
- acquire/terminal统一NOWAIT锁job->job definition->attempt->lease->operation->subscription->source definition->security->health，
  全部锁成功后只读一次fresh PG clock；binding drift/expiry与typed lock conflict均具真实PG test。
- query/as-of window以persisted job available_at（manual request available_at / scheduled occurrence fire）
  为业务seed，deadline只作execution cutoff；跨UTC午夜deadline不得产生未来source date。
- sync/health/operation DTO从既有large``domain/source.py``拆入新pure
  ``domain/source_sync.py``、``source_health.py``、``source_operation.py``，按exact DAG单向import并加
  结构/AST/direct-owner tests，禁止package compat re-export；
- subscription missing/binding non-executable、tenant/job/payload/snapshot identity、live loss与repository infra分别有
  source_sync-owned closed error enum/class；execution service按class/code映射SOURCE_INVALID/
  SOURCE_INTERRUPTED/REPOSITORY_FAILURE，scheduled pre-read race在insert前零operation拒绝；
- acquire decision三个成功branch的action/effective_state/operation_id及optional字段presence精确冻结；
  zero-operation rejection走typed exception，不伪造缺字段decision；source runv1 core已从11更新为13，
  增result_json/result_sha256并同步CHECK/guard/downgrade。
- 新storage/source_sync_protocols.py独占七方法pure protocol，不向既有large protocols.py聚合/re-export；
  public list/reenable/not-found/version/state闭集和SourceServiceInput/Unavailable mapping逐方法冻结；
- 0005 exact identifiers加入UTF-8 bytes<=63 gate，并缩短snapshot五列parent UNIQUE名，禁止PG silent
  truncation破坏catalog exactness。
- Platform与repository两个Protocol均冻结完整同步``def``签名/annotation；subscription与health冲突码
  分离；下游Job/Schedule typed idempotency/version conflict原样传播而不做message mapping。
- DownloadEvent strict narrowing只覆盖FILING identity/terminal与PIPELINE result的owned JSON子树；SEC合法
  ``FileObjectMeta`` file payload被忽略且不做递归JSON校验，public result绝不泄漏raw event/mapping。
- freshness只用同一post-lock PG UTC date，边界等于max age仍接受、超一日才repository authoritative
  stale_data override；no-change豁免，verified document/count保留并推进health。
- alert dedupe使用固定八字段canonical transition，event_id由dedupe key确定性UUIDv5派生，再build exact
  body/hash；operation/health head另有named BEFORE INSERT guards，禁止direct terminal/arbitrary version绕过。
- ``SourceExecutionBinding.security_company_id``精确绑定locked security所属company；live lease逐值核验
  tenant/job/attempt/fence/token lineage，cross-job persisted拼接为persisted_invariant且零source DML。

### 3.12 最终机械/可维护性 red-team 裁决

本轮冻结前的内部DB、architecture、response-loss与composition审计finding全部接受并写入当前SHA：

- manual/schedule response-loss recovery改为owner-correct read facade：JobService/JobStore按exact descriptor+
  idempotency key返回immutable ``JobIdempotencyRecord``，ScheduleService/Store按tenant+key返回definition；
  recovery hit先于mutable source preflight，支持Job已LEASED/terminal、definition禁用和source/security/config
  漂移仍恢复原receipt/draft。caller intent drift走既有typed conflict，persisted tamper分别走
  JobRepositoryFailureError/ScheduleRepositoryError再精确映射persisted_invariant；Source repository不跨读
  Job/Schedule表。manual fingerprint仅覆盖caller intent，不把derived snapshot/config变成第二真源；
- 删除无真实pipeline consumer的Fins ``operation_key``；Source operation与Fins document identity分别承担
  replay/reuse，不扩整个download chain制造空语义；
- 避免三个新God owner：investment pure contracts拆为source_sync/source_health/source_operation；完整Fins
  event状态机拆入``DefaultFinsWorkerSourceSyncRuntime``并冻结narrow pipeline/repository/locator ports；public
  facade留``investment_sources.py``，execution protocol/service/handler独立在
  ``services/source_sync_execution.py``，handler只one-call delegate；
- acquire request加入origin、Job definition id与full descriptor；repository锁序加入job_definition，并以
  locked job available_at生成scheduled snapshot。operation每generation持久
  ``owner_binding_disposition``，因此disabled acquire后并发operator re-enable仍能证明no-provider candidate，
  同时terminal current binding drift继续authoritative stale override；
- Fins priority拆为asyncio、external/domain cancellation、proven invariant、stream exception、clean terminal；
  clean status=cancelled才typed cancel，failed pipeline丢弃buffer，status=ok mixed verified+failed精确partial；
  private ingress只narrow owned JSON subtrees，不递归验证合法SEC FileObjectMeta；
- alert dedupe用八字段transition、deterministic UUIDv5，event.created_at精确绑定health snapshot observed_at，
  避免随机UUID/外部clock让同dedupe产生不同bytes；
- 0005增加same-job/different-attempt source-run五列terminal FK、operation snapshot object CHECK、每代disposition
  CHECK/guard；明确0005新增existing run/snapshot/outbox immutable guards。single <=63-byte manifest列出全部
  PK/UNIQUE/index/FK/CHECK/function/trigger/policy/grant，upgrade/self-check/tests/downgrade复用；downgrade admission
  检查全部14个新增run列（含latest source date），每个对象exact-once逆序移除；
- exact allowlist扩到Job/Schedule lookup owners、三domain owners、独立Fins/execution owners和两CI workflows。
  两workflow显式pull现有pinned PG/Redis与fixture同源pinned MinIO；migration/identity/jobs/schedules/sources/
  source-job/MinIO/Redis八个integration lane各自独立pytest process，remaining aggregate逐个ignore；
- auto-provider production路径才内部构造四项mapping、exact one source handler并seal；accepted explicit-provider
  seam保持identity unchanged，零auto platform/source-specific装配，但既有Host DefaultFinsRuntime构造不受影响；
- source/service/repository error taxonomy、Platform/repository/private gateway signatures、SafeJobErrorCode exact
  member/value/retry matrix、handler二参到三参全量替换、module-by-module branch coverage与命名tests全部冻结。

### 3.13 Codex plan-fix round 2 裁决

``6a49...``在进入external review前的Codex internal audit发现5H/3M；全部为真实可构造性/迁移准确性
finding并接受，旧SHA作废：

| Finding | 裁决 | Round 2 closure |
|---|---|---|
| H1 migration preflight把同名replacement也要求absent | ACCEPT | single manifest拆为``NEW_0005_OBJECT_NAMES``（必须absent）与三个``REPLACED_BASELINE_INDEX_NAMES``（必须present且exact 0001 shape），再执行其它preflight。 |
| H2 既有表新增列缺PG type/null/default | ACCEPT | 逐列冻结14个source run列的UUID/TEXT/BOOLEAN/INTEGER/DATE/JSONB、全部nullable且无default；snapshot version精确``INTEGER NULL``无default。 |
| H3 downgrade遗漏version partial index依赖 | ACCEPT | strong FK后先按exact name drop partial UNIQUE index，再drop parent uniques/CHECK，最后drop column；明确禁止CASCADE。 |
| H4 async execution直接调用sync repository会阻塞event loop且取消后可能orphan/commit后误报cancel | ACCEPT，liveness测试由Round 3修正 | ``SourceSyncExecutionService``唯一拥有to_thread task+shield+repeated-cancel reap；acquire是pre-PONR cancel-after-reap，terminal在最后domain check后无await地schedule thread形成PONR，PONR后inner durable decision优先。Round 3删除“持Source job lock时heartbeat仍推进”的错误断言，改为NOWAIT typed rollback/release后heartbeat才推进。 |
| H5 explicit-provider trap会误禁baseline DefaultFinsRuntime | ACCEPT | explicit provider只跳过auto platform与source-specific cross-platform FinsService/connector/facade/execution/handler；baseline DefaultFinsRuntime及eager internal component仍构造且不注入external provider。 |
| M1 PG wall clock后跳可违反finished_at | ACCEPT，公式由Round 3补全 | Round 2先引入single raw/derived time；Round 3补齐takeover +1 microsecond、optional later health head与reenable strict-forward公式。 |
| M2 两处CHECK使用不存在的``version`` | ACCEPT | snapshot/outbox均精确改为``health_state_version>0``。 |
| M3 scheduled payload summary漏字段 | ACCEPT | §3.4精确列出subscription/source definition/expected subscription version/schedule key/source request fingerprint五个业务字段。 |

本轮未扩产品语义、未修改source/tests/其它docs；没有需要Controller新裁决的合同冲突。状态继续是
``CORRECTIVE CANDIDATE / AWAITING DEEPSEEK + MIMO``，不是plan pass。

### 3.14 Codex plan-fix round 3 裁决

Round 2 closure后Codex internal liveness/schema audit又发现2H/1M，全部接受；``62a4...``旧SHA作废：

| Finding | 裁决 | Round 3 closure |
|---|---|---|
| H1 Source unique lock sequence可在持有job_run时阻塞后续row，使generic heartbeat无法推进 | ACCEPT | acquire/terminal每一张可能阻塞row统一``SELECT ... FOR UPDATE NOWAIT``；只按SQLSTATE 55P03 / psycopg LockNotAvailable映射repository unavailable，禁止lock_timeout/message guessing，全部Source DML晚于全锁。acquire conflict零operation/Fins；terminal PONR conflict全rollback、operation ACTIVE、retryable REPOSITORY_FAILURE，下一live attempt takeover exact-once。to_thread/shield/reap保留为event-loop/thread ownership，不再声称barrier期间heartbeat能越过Source job lock。 |
| H2 live lease列名错误 | ACCEPT | locked lease精确验证真实0003列``lease.attempt_id=locked_attempt.id``，绝不引用不存在的alternate attempt FK column；cross-job/malformed lineage test同步。 |
| M1 clock rollback公式不足以满足strict transition/head monotonicity | ACCEPT | generation1 acquired_at=single raw clock；takeover acquired/updated使用``GREATEST(raw, old acquired + 1 microsecond)``；terminal time同时取raw、operation acquired、optional locked head observed最大值；reenable取raw与old head observed+1 microsecond。run/receipt/op/health/snapshot/outbox仍共享唯一derived time并新增rollback/head-later tests。 |

本轮不改变generic Job lock protocol、不新增product state，也未遇到需Controller新裁决的合同冲突。状态仍为
``CORRECTIVE CANDIDATE / AWAITING DEEPSEEK + MIMO``，不是plan pass。

## 4. Code-generation boundary

实施顺序必须是 pure DTO -> handler scope/registry -> Fins gateway -> 0005/schema -> PG repository ->
source Service/schedule draft -> startup -> docs/full review。任何一步需要Worker、0001..0004、live
provider、JobStore source-specific hook或allowlist外owner，都回Controller，不得边编码边设计。

本轮实现曾继续冻结，直到：

1. internal code-generation adversarial review无open H/M/L；
2. DeepSeek corrective review PASS/open0；
3. MiMo corrective review PASS/open0；
4. Controller写acceptance artifact并完成accepted plan commit。

前3项现已满足，Controller acceptance artifact已写入；第4项只剩Controller创建本地accepted plan
commit。该本地commit成功后，implementation gate按target exact allowlist开放。

## 5. 当前验证

- 目标计划保留initial与第一轮corrective review artifacts作为历史证据；第一轮reviews均未解除freeze；
- target以ROUND 3 FINAL FROZEN语义快照
  ``96bceb321464223c9022af25905ca36c4bfe5cdca371111384567acb396ee4f0``分别交给fresh DeepSeek与MiMo；
  两路均核验同一exact bytes并独立给出PASS/open ``0/0/0``；
- 第一轮``281f...``结论未被复用；最终结论只来自上述两份fresh artifact；
- scoped tracked``git diff --check`` exit 0；两个untracked target用``git diff --no-index --check``仅因
  内容相对``/dev/null``不同返回1且无whitespace diagnostic；CR=0、NUL=0、LF/final newline均通过；
- Round 2结构审计证明run新增列table精确14个unique names、全部nullable/no-default并覆盖预定PG types，
  snapshot version exact type/null/default与downgrade dependent-index-before-column均命中；manifest提取57个
  exact identifiers，最大57 UTF-8 bytes、无>63对象；
- Round 2 contradiction ``rg``与旧replay/lease/caller-result positive-shape ``rg``均exit 1（零命中）；
- Round 3 target scan证明没有不存在的lease alternate-attempt字段、旧heartbeat-during-contention test、旧
  acquired-only terminal formula或plain locking contract；所有semantic ``FOR UPDATE``出现均为NOWAIT（另有一条
  明确禁止plain form的negative rule）。target精确命中55P03/psycopg typed mapping、三组strict monotonic
  formula与replacement named tests；
- stale-term ``rg``只命中明确的历史/禁止性文本：不存在的``job_runs.current_attempt_id``纠正说明、
  ``operator-enabled``消歧、禁止``terminal_result_json/hash``和一个natural-language binding-missing测试名；
  没有``replayed=true``、``idempotent_replay``、live ``lease.expires_at>``或caller canonical result路径；
- 未改production/test，未运行provider/network/live，未stage/commit/push。

## 6. 本轮 remaining risks / final review focus

本轮没有已知需要新产品决策的open question；这不等于review pass。fresh reviewers必须重点反证：

1. status=ok/failed/cancelled的真实SEC/CN/HK wire分支是否仍有未声明shape；
2. 0005 parent-key/FK DAG、conditional CHECK与legacy admission是否能在真实PG16无歧义生成；
3. investment-owned locator wrapper是否完全守住现有pure architecture guard且不丢readback identity；
4. manual stale与malformed/forged payload的分界是否保证只有真实业务drift会写stale terminal；
5. 每个expanded async stream direct owner是否在allowlist与owner tests中一一对应。
6. response-loss owner lookups、single DB manifest、explicit-provider branch与CI eight-lane wiring是否仍有
   与baseline concrete signature/catalog/workflow不一致的机械缺口。
7. sync repository offload在真实Python cancellation semantics下是否确实reap每个thread、保持event loop
   responsive，NOWAIT conflict是否在bounded deadline内rollback/release后才允许heartbeat推进，且terminal
   PONR后任何单次/重复outer cancellation都不能覆盖durable decision。

上述是发送最终复审时的fail-closed条件；两份fresh review均未产生open H/M/L，因此没有触发再次修正。

## 7. Final closure

Controller逐项核验两份最终artifact均锁定语义SHA-256
``96bceb321464223c9022af25905ca36c4bfe5cdca371111384567acb396ee4f0``，结论均为
``PASS / open H/M/L=0/0/0``，且artifact自身SHA-256分别为
``4a484ae0c1f702a65a6941e61e0643d17f653183a46c84fa2b737bdb1a4cf36d``与
``a725900220b6d2614378713d545e63a583706f1a9a941d99598ebf7139f8b5d0``。全部历史finding与
Controller internal audit finding均已进入target并CLOSED；没有blocking open question。

本plan-fix闭合为``ACCEPTED / CLOSED``。生产与测试实现、实现期修复只允许Codex internal models；
DeepSeek与MiMo只承担相互独立的plan/code review，不参与实现。accepted plan本地commit成功后下一入口为
Slice 2.3 implementation；本closure未修改production/tests，未stage/commit/push/开PR，也未运行或授权
真实provider、网络、模型、Broker、交易或部署动作。
