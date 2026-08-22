# Slice 2.3 Item 7 startup registration same-reviewer code rereview

- **Gate / work unit**: Gateflow same-reviewer code re-review / Slice 2.3 Item 7 startup registration post-fix candidate
- **Reviewer role**: DeepSeek V4 Pro code reviewer；不是 Controller、不是 implementation/fix writer；不启动或重排 Gateflow；未修改任何实现/测试/README/plan/旧 artifact；未 stage/commit/push/PR
- **Scope**: 对同一 reviewer/model route 的 post-fix candidate 独立 re-review。从 byte0 重读 accepted master/plan-fix/plan-acceptance、implementation artifact、本人首审、fix artifact、post-fix exact-seven 全文与完整 candidate diff，并沿未改真实调用链核验关键构造签名与 registry 语义；不继承首审 verdict，重新应用 correctness / resource / idempotency+ordering / parameters+types / architecture+best-practice+overengineering+overcoupling+adverse-tests 五视角
- **Base**: branch ``codex/investment-platform``、HEAD ``ee75d17955a4a8f30a56a02cae56fac34df79be5``、index empty
- **Actual model / route**: ``deepseek-v4-pro[1m]`` / local Claude Code CLI user-dispatch
- **Date / timezone**: 2026-08-22 / Asia/Shanghai（本机系统时钟 2026-08-22 08:40 CST）
- **Status / verdict**: ``PASS / open H/M/L = 0/0/0``
- **Independence**: 未读取任何 MiMo code-review/code-rereview artifact 或 MiMo 输出；未运行 tests/pyright/PG/Docker/network/provider/model/Broker；未执行 Git 写、stage/commit/push/PR、cache 或实现修改；只使用只读 git status/diff/show、rg/grep/sed/shasum/wc/date；本 artifact 是唯一写入

## 0. START identity drift gate（全部只读核验，逐项命中后才继续）

| 核验项 | 预期 | 实测 |
|---|---|---|
| branch / HEAD | ``codex/investment-platform`` / ``ee75d17955a4a8f30a56a02cae56fac34df79be5`` | 命中 |
| index | empty | ``git diff --cached`` 为空，命中 |
| worktree | 恰好 7 个 modified path（exact-seven） | 命中（``git status --short`` 7 个 `` M``，与 handoff exact-seven 逐路径相等） |
| canonical post-fix candidate diff SHA-256（与 implementation/fix artifact §6 冻结命令逐字一致，含 ``--binary --no-ext-diff --full-index``） | ``cedfd01080e85ee93a2591b783c3e6bb202150fe389a392a5a1f4c246df541d9`` | 命中 |
| accepted master | ``13dee18b9fcd0ea470b3cf4333904aceb0f82db87098472d1b5b43ce14c03194`` / 3917 / 314076（``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md``） | 命中 |
| plan-fix | ``a57ec452e71f7f8136b96f7da855546a3ff29cbd0f43d3101f83f62658e5640d`` / 236 / 19145 | 命中 |
| plan-acceptance | ``67805449627264ea5b526624e6b43039373d0f2553f39ee315acb43ebb1fa2b9`` / 136 / 9986 | 命中 |
| implementation artifact | ``4ed3982630df251464170ec309d8f93925ef5632930a51fa51485f90a97e8a2f`` / 219 / 14375 | 命中 |
| 本人首审 artifact | ``0abf4379e6d1a53c8c8dfb50ceacf256ea503046ff96d28c8f5cf1fe503e8c94`` / 156 / 22450 | 命中 |
| fix artifact | ``8b3599bb3c5e5f865132ad6a64f82d0f065d956b2a4a74c0c58736780677be15`` / 162 / 8827 | 命中 |
| exact-seven 七文件 SHA-256 / lines / bytes | 见 fix artifact §5 | 全部命中（见 §7 END 表） |
| code-rereview path | 必须不存在 | 命中（ABSENT） |
| actual model | ``deepseek-v4-pro[1m]`` | 命中（session 环境确认） |

## 1. 结论（findings-first）

唯一 verdict：``PASS / open H/M/L = 0/0/0``。

- **F-01 closure**: ``CLOSED``。post-fix PG black-box 模块 docstring 已与同文件 exact-four 测试真值闭合，stale exact-three 文本在 exact-seven 内精确零残留，fix 为最小 docstring-only 字节变化，无行为回归（§2）。
- **Fresh findings**: 五视角独立复审（不继承首审 verdict）未发现新的 H/M/L finding（§3）。
- **Controller OQ 裁决核验**: OQ-01/OQ-02/OQ-03 三条裁决均未导致 material defect（§4）。
- 本结论只覆盖本 post-fix candidate（``cedfd010...``）相对 accepted base 的 exact-seven 增量面；PASS 仅当 open 0/0/0，此处满足。

## 2. F-01 closure 直接证据（首审 Low 的 same-reviewer 复核）

- **首审 F-01**: PG 模块 docstring 仍写 exact-three，与同文件 rename 后的 exact-four 黑盒测试矛盾。
- **post-fix 状态**: ``tests/integration/investment/test_identity_repositories_postgres.py`` 行 12–17 现为“production startup 组合精确承载四个真实 Service：``investment_identity``（``InvestmentIdentityService``）、``investment_sources``（``InvestmentSourcesService``）、``durable_jobs``（``JobService``，``platform_service_name == "durable_jobs"``）、``durable_schedules``（``ScheduleService``），且 导入图不含 evidence/portfolio future module；”。与同文件行 1686–1691 的 ``assert set(services) == {investment_identity, investment_sources, durable_jobs, durable_schedules}`` 及行 1694–1703 的四项类型/稳定名断言逐项一致；行 1711–1712 的共享 session factory 断言与 docstring“组合”表述一致；行 16–17 保留的“导入图不含 evidence/portfolio future module”表述与模块实际 import 面一致（全文件无 evidence/portfolio import）。
- **stale 残留**: 对 exact-seven 七文件 grep ``exact_three / exact-three / 三个真实`` 精确零命中；四个历史旧名（``test_production_provider_wires_exact_three_service_mapping``、``test_production_explicit_provider_keeps_custom_composition_after_redis_admission``、``test_production_provider_exposes_exact_slice22_service_mapping_with_empty_execution_registry``、``test_source_handler_registration_remains_absent_until_slice_2_3``）在源文件中零命中（唯一命中为 ``__pycache__`` 内过期 .pyc 二进制，属缓存残余，Python import 以 source mtime 重新编译，运行时零影响；AST named-test 审计只读源文件）。
- **fix 最小性**: 相对 pre-fix，仅该文件 identity 从 ``b0049d210864fd3246562c50e926b90793169b6fc694a60401b88d4478004d53 / 2123 / 73549`` 变为 ``1cefaee33dd0a2e93b236e36171efc2aced09dba4863872982eabe54b64c492e / 2124 / 73611``（+1 行 / +62 字节），与 docstring 仅增一行并补齐 ``investment_sources`` 的最小修改形状一致；其余六个 exact-seven identity 不变。diff 显示该文件相对 HEAD 的 hunk 只有模块 docstring 与既有 rename/断言 hunk，无任何生产语句变化。
- **回归**: 该文件 production 语句/分支零变化；production startup 代码路径（``dayu/services/startup_preparation.py``）identity 与 pre-fix 完全相同（``73309aba...`` 不变）。F-01 真实关闭且无回归。

## 3. 五视角独立复审（不继承首审 verdict；每项均以当前文件字节与只读调用链证据独立核验）

### 3.1 correctness

- ``_build_production_services_provider``（startup_preparation.py:623–715）装配顺序与 master §10.1.2–§10.1.4 逐项一致：JobStore/ScheduleStore/registries → JobService → ScheduleService → FinsService → FinsSourceConnector → PostgresSourceSyncRepository → SourceConnectorRegistry → InvestmentSourcesService → SourceSyncExecutionService → SourceSyncExecutionHandler → ``register_descriptor`` → ``register_handler`` → descriptor ``seal`` → execution ``seal`` → 六臂断言 → ``_ProductionServicesProvider``。注册前置条件真实满足：``JobHandlerRegistry.register_descriptor``（job_service.py:336–352）要求未封存且同 job_type 逐字段幂等；``JobExecutionRegistry.register_handler``（job_service.py:449–495）要求 descriptor 已注册且逐字段相等、handler 满足 ``JobExecutionHandlerProtocol``（runtime isinstance）、``handler.job_type == descriptor.job_type``、同 job_type 不得替换 identity。生产路径先注册 descriptor 再注册 handler，顺序满足其前置条件。
- 六臂断言（行 701–709）均驱动真实失败分支：``is_sealed`` 双检查、``descriptor_count/handler_count == len(batch) == 1``、``get_descriptor(...) != SOURCE_SYNC_JOB_DESCRIPTOR``（``JobHandlerDescriptor`` 为 frozen slots 七字段 dataclass，domain/jobs.py:979–999，``!=`` 为逐字段相等比较）、``get_handler(...) is not source_handler``（identity 比较；``get_handler`` job_service.py:499–530 在任一跨 registry 漂移时返回 ``None``，``None is not source_handler`` 恒真 → 抛出）。
- ``SOURCE_SYNC_JOB_DESCRIPTOR``（domain/source_sync.py:50–58）七字段与 master §3.4 逐值一致（job_type ``investment.source-sync.v1``、payload schema/version=1、max_attempts=3、retry 30/300、lease 900）；``SourceSyncExecutionHandler.job_type``（source_sync_execution.py:364）返回同一 fixed job type，``execute`` 单次原样委托（行 379–385），满足 registry 的 job_type 一致性检查。
- ``build_platform_composition``（startup/platform.py:39–73）在 auto 路径恰一次调用（startup_preparation.py:1539）且早于 ``recover_host_startup_state``（行 1543）；explicit 路径恰一次且在 Host 副作用前（行 1457）。``PlatformComposition`` 构造期校验键/名/值契约，四项 Service 均满足 ``PlatformServiceProtocol``（``platform_service_name`` 与键一致：identity 键为 ``_INVESTMENT_IDENTITY_SERVICE_NAME``，sources 键为 ``_INVESTMENT_SOURCES_SERVICE_NAME`` 行 136–137，job/schedule 键为既有常量）。
- 显式 provider 路径：``_default_provider_or_fail`` 行 809–810 原样早退 ``(explicit_provider, None, None)``，全部 Source-specific 构造/注册/封存代码只存在于 auto 路径的 ``_build_production_services_provider``，结构上不可达。
- 未发现 correctness finding。

### 3.2 resource（异常/释放/引擎 dispose）

- 阶段 1 失败：``_prepare_production_platform_dependencies``（行 574–620）自行 ``engine.dispose()`` 一次并向上抛；此时 composition root 的 ``owned_lifecycle`` 尚未赋值（保持 ``None``），except 不重复 close。
- 阶段 2（含 publish）失败：唯一收口为 composition root except（行 1569–1579），顺序为 lifecycle（``owned_lifecycle``=``preparation.identity_service``，engine 唯一 owner）→ lease → S3 → queue admission，恰为构造逆序（redis admission → s3 → lease → PG engine）；engine 恰 dispose 一次。19 阶段失败矩阵（application test 3308–3392）以共享 ``close_order`` 断言 ``["pg","lease","s3","redis"]`` 且四项各 count==1、``identity_service.close_calls == 1``、``writer_lease._released``、``s3_store.close_calls == 1``、``queue_adapter.close_calls == 1``，同时断言 ``recovery_calls == []``、``successful_returns == []``、每个 probe ``failure_hits == 1``（真实命中计数，非削弱断言）。
- 成功态：``PreparedHostRuntimeDependencies.close()`` 幂等（``test_prepared_runtime_close_retry_disposes_shared_engine_exactly_once`` + PG ``test_production_provider_close_disposes_engine_once`` 真实 Engine.dispose 计数 ==1）；atexit 协调器语义由既有 6 个单元测试锁定，本 Item 未改。
- 阶段 2 不新增 thread/timer/connection/atexit/second lifecycle owner；Source/execution/facade 均不持有 engine 或 close 权。
- 未发现 resource finding。

### 3.3 idempotency / recovery / ordering

- 发布恰一次：auto 路径 ``build_platform_composition`` 仅行 1539 一处调用；``_install_production_call_order_recorder`` + ``_EXPECTED_PRODUCTION_ASSEMBLY_ORDER``（application test 828–966 / 3701–3759）以 15 个 seam 的真实成功记录断言唯一装配顺序且 ``register_descriptor/register_handler/publish`` 各 count==1。
- publish 早于 startup recovery（行 1539 vs 1543）——满足 master §10.1.4。
- 任一 constructor/register/seal/assert/provider/publish 失败均无 partial mapping 外泄：composition 局部变量在成功前保持 ``_default_platform_composition()``，``prepared`` 对象只在全链成功后构造；19 阶段矩阵的 ``attempts`` 计数断言（仅 ``provide_services`` 阶段 attempts==1 且 successful_returns==[]）直接证明。
- 双 registry 封存后无 unseal 路径；registry 语义（append-only、seal 后拒绝、exact replay 幂等）由 job_service.py 实现与既有 ``test_job_service.py`` 守护（含 ``"remove"/"replace" not in dir(...)`` 断言 954–982）——被删除的旧 ``test_source_handler_registration_remains_absent_until_slice_2_3`` 中“无 remove/replace API”不变量仍在 test_job_service.py 覆盖，无回归。
- explicit-provider 分支顺序保持：composition 在 Host 副作用前构建，``_default_provider_or_fail`` 早退前不发生任何 Source 装配。
- 未发现 idempotency/ordering finding。

### 3.4 parameters / types

- 参数生效链逐一核验：``host`` 同时进入 JobService reader/canceller（行 665/668）与 ``FinsService(host=host, ...)``（行 678）；``fins_runtime`` 进入唯一 ``FinsService``（行 678）；``queue_settings`` 进入 ScheduleService 的 lookback/scan 上限（行 675–676）；``wakeup_publisher`` 进入 ``JobServiceRuntimeAdapters``（行 667–670）；``preparation.session_factory`` 进入三个 store（行 658/659/680）。无死参数、无默认化覆盖。
- 构造签名逐项与真实代码一致（未改调用链核验）：``PostgresJobStore(session_factory=...)``（postgres_jobs.py:612–619）、``PostgresScheduleStore(session_factory)``（postgres_schedules.py:1270–1277）、``PostgresSourceSyncRepository(session_factory)``（postgres_sources.py:1847–1854）、``FinsService`` 字段 host/fins_runtime（fins_service.py:34–39）、``FinsSourceConnector(fins_gateway=...)``（connectors/source.py:154–157）、``SourceConnectorRegistry(tuple)``（connectors/source.py:208–213）、``InvestmentSourcesService`` 三个窄 gateway（investment_sources.py:499–505）、``SourceSyncExecutionService(repository, connector_registry)``（source_sync_execution.py:180–190）、``SourceSyncExecutionHandler(execution_service=...)``（source_sync_execution.py:348）。
- 类型安全：新增生产代码全强类型；测试侧 ``Never/ParamSpec/Generic/Protocol`` 均非逃逸集合，文件自守 AST guard（application test 2612–2642）仍在且新增代码无 Any/object/cast/ignore/getattr/hasattr。writer/fix 报告的 Pyright 0/0/0 与 Ruff default/F/I 通过属证据账本采信（本 review 约束禁止重跑，见 §6）。
- 未发现 parameters/types finding。

### 3.5 architecture / best-practice / optimal / overengineering / overcoupling / adverse-tests

- 分层与依赖方向：services 层新增 import 为 services→investment infra/domain/connectors，与既有方向一致，无反向依赖；``dayu/services/__init__.py`` 只新增 ``InvestmentSourcesService`` 导出，private execution 类型无 re-export（已核）。
- concrete ``host: Host`` / ``fins_runtime: DefaultFinsRuntime`` 参数形态是 master §10.1.1 明令（“接收同一个 Host 与已构造的同一个 DefaultFinsRuntime”），且下游立即收窄为协议（JobService 的 reader/canceller 协议、FinsService 的 HostedExecutionGatewayProtocol/FinsRuntimeProtocol、facade 的三个窄 gateway）；非越界耦合。
- 无新增 lifecycle owner、无共享可变状态、无 God object；``EXPECTED_PRODUCTION_HANDLER_BATCH`` 为函数内 immutable 单元素 tuple，count 断言取 ``len(batch)``，满足 §3.1 batch/count 唯一真源。
- adverse-tests 证明力：19 阶段矩阵（7 constructor + 2 register + 2 seal + 6 assertion arm + provider init + provide_services）覆盖 Item 7 增量面全部风险 seam，且每个 probe 断言 exact 一次命中与真实 close 行为；explicit-provider 测试用**真实** ``DefaultFinsRuntime.create``（记录工厂）跑完整 prepare，11 个 trap 零命中 + caller 双 registry identity/count/sealed 逐项不变 + eager ``_source_sync_runtime`` 组件断言；PG black-box 用真实 PG16 证明四项 mapping、第四项同时满足 ``PlatformSourceSyncServiceProtocol`` 与 ``InvestmentSourcesService``、三 store 共享同一真实 session factory（``is`` 断言）、engine dispose 恰一次；closed-shape admission 测试逐分支断言 6 类非法 shape 的精确错误文案。断言为真实行为/identity 级断言，非削弱断言凑 coverage。
- 测试基建复杂度（typed probe、descriptor-safe 绑定、记录工厂）是为满足本仓 escape-guard 与 singleton coverage 门禁的必要表达，未掩盖协议问题（同一测试同时断言协议满足与真实共享 factory）；不构成 overengineering。
- 未发现 architecture/overcoupling/adverse-tests finding。

## 4. Controller OQ 裁决核验（仅在有证据表明导致 material defect 时才 finding）

- **OQ-01（preserved WIP 格式收拢字节，裁决 accepted input 不回退）**: 逐 hunk 复核（startup_preparation.py diff 中行 501–507、611–614、818–821、1285–1289、1345–1348、1514–1520、1666–1670 等）全部为括号合并/行合并，无任何分支、参数、返回值或异常语义变化；该文件 before/after identity 相同证明 Item 7 writer 零改动。accepted input 裁定不引入 material defect。
- **OQ-02（十九阶段不再新增 stage，裁决不加）**: 未被注入的既有 phase-2 seam（``PostgresJobStore``/``PostgresScheduleStore``/``JobHandlerRegistry``/``JobExecutionRegistry``/``JobService``/``ScheduleService`` 构造）均为纯赋值构造，且全部位于 composition root 同一 try 边界内——任一构造失败都会进入与 19 阶段完全相同的 except 收口，该收口的逆序 exact-once 行为已被 19 阶段矩阵及既有 ``test_queue_preparation_failure_closes_resources_in_reverse_dependency_order``（Host 构造失败，行 3782–3851）逐项锁定。不新增 stage 不会留下未被证明的生产行为面，裁定不导致 material defect。
- **OQ-03（application 模块 docstring 的 Slice 0.2 引言，裁决不改）**: 该引言描述“平台设置 / 组合注入点行为”并声明三条覆盖面，均为本文件当前仍在测试的真实行为（TestBuildPlatformComposition、TestPlatformAdmissionBeforeHostSideEffects 等 class 仍在文件中）；属非排他历史引言，非虚假表述（区别于 F-01 的直接矛盾）。裁定不导致 material defect。

## 5. Open Questions

- 无。

## 6. Residual Risk / boundary

1. 本 re-review 受 handoff 约束未重跑 tests/pyright/PG/Docker/network/provider/model/Broker；§3 的 validation 结论基于字节级证据、真实调用链签名核验与 implementation/fix 证据账本的一致性采信，不是独立重跑。fix writer 报告的 64 focused / 17 PG / Pyright 0/0/0 / Ruff / AST 5/4 门禁与“唯一字节变化是 PG 模块 docstring”的账本在字节层面自洽。
2. ``dayu/services/startup_preparation.py`` 的 fresh branch coverage 原始值 80.48% 紧贴 ≥80.0 门禁；该文件任何后续改动都必须重跑 fresh singleton lane。
3. **boundary 观察（不计 H/M/L，不属 candidate 缺陷）**: ``dayu/README.md:464`` 仍写“models_identity.py / models_auth.py / models_workspace_import.py（15 张表 ORM）”，而 ``tests/investment/test_platform_migrations.py:820`` 的既有 owner gate 锁定 metadata 精确 18 张（models_identity 11 + models_auth 5 + models_workspace_import 2，已核）。该行不在本 candidate 的 diff hunk 内（dayu/README 唯一 hunk 为行 152–157 的 registry 表述），也超出 master §10.1 对 dayu/README 的 Item 7 同步授权面（仅 empty registry/Service 装配表述）；属既有文档漂移，建议 Controller 另开独立 docs-only 工作单处理，不作为本 Item 的 H/M/L finding 或阻塞项。
4. 既有 ``git fsck`` repo-health residual（master §16 item 11）不属本 candidate；未被本 review 触碰或宣称修复。
5. 本 PASS 只证明 post-fix candidate ``cedfd010...`` 的 exact-seven 增量面；Controller 后续 acceptance/checkpoint 仍需按 plan-fix §5.4–5.5 的 stage 清单执行。

## 7. END identities 与边界证明

本 artifact 自身最终 SHA-256 / 行数 / 字节数不嵌入自身 preimage，由 reviewer final report 只读重算并报告。

exact-seven 七文件 END 身份复核（与 §0 START 完全相同，逐项命中）：

| path | SHA-256 / lines / bytes |
|---|---|
| ``dayu/services/startup_preparation.py`` | ``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` / 1689 / 63289 |
| ``tests/application/test_service_startup_preparation.py`` | ``2707df2a5e81357b590c78e474f74f60778e945d5d853d983a3877e778fca545`` / 4123 / 130135 |
| ``tests/integration/investment/test_identity_repositories_postgres.py`` | ``1cefaee33dd0a2e93b236e36171efc2aced09dba4863872982eabe54b64c492e`` / 2124 / 73611 |
| ``README.md`` | ``d3760a46b7c0ce8cc0da0c26d1d4789d7c444560e9d1c7c5d677398dbffb4a94`` / 2407 / 153621 |
| ``tests/README.md`` | ``1db72b00c63c0afcc8ebd81d8220383cec3efb501928c00466b78c7f897c992f`` / 612 / 132898 |
| ``dayu/README.md`` | ``8fbf8605b9ec7bac1a84f3cf78d17bedc2e99f83bfea285e53307924838ccfe5`` / 1297 / 65205 |
| ``dayu/investment/README.md`` | ``1e39d2746962144d0f4a4ff1ca7f77063796fbddb35a1f4e70e0fbe708244331`` / 333 / 22921 |

canonical post-fix candidate diff SHA-256 END 复核（冻结命令逐字）：``cedfd01080e85ee93a2591b783c3e6bb202150fe389a392a5a1f4c246df541d9``，与 START 一致。

lineage artifacts END 复核（与 §0 完全相同）：

- accepted master ``13dee18b9fcd0ea470b3cf4333904aceb0f82db87098472d1b5b43ce14c03194`` / 3917 / 314076；
- plan-fix ``a57ec452e71f7f8136b96f7da855546a3ff29cbd0f43d3101f83f62658e5640d`` / 236 / 19145；
- plan-acceptance ``67805449627264ea5b526624e6b43039373d0f2553f39ee315acb43ebb1fa2b9`` / 136 / 9986；
- implementation artifact ``4ed3982630df251464170ec309d8f93925ef5632930a51fa51485f90a97e8a2f`` / 219 / 14375；
- 本人首审 artifact ``0abf4379e6d1a53c8c8dfb50ceacf256ea503046ff96d28c8f5cf1fe503e8c94`` / 156 / 22450；
- fix artifact ``8b3599bb3c5e5f865132ad6a64f82d0f065d956b2a4a74c0c58736780677be15`` / 162 / 8827。

边界证明（END 时点只读核验）：

- branch 仍为 ``codex/investment-platform``；HEAD 仍为 ``ee75d17955a4a8f30a56a02cae56fac34df79be5``；index 仍为空（``git diff --cached --quiet`` exit 0）。
- worktree modified 仍精确为 exact-seven 7 个 path，无第八个 modified。
- 本 reviewer 未读取 ``docs/reviews/code-review-20260817-slice-2.3-item7-startup-registration-mimo.md`` 及其它任何 MiMo 输出；未创建 cache、``.coverage``、pyc 或其它临时产物；除本 artifact 外零写入。
