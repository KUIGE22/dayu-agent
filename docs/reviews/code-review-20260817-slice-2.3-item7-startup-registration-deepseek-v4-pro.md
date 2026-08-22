# Slice 2.3 Item 7 startup registration independent code review

- **Gate / work unit**: Gateflow independent code review / Slice 2.3 Item 7 startup registration exact-seven
- **Reviewer role**: DeepSeek V4 Pro code reviewer；不是 Controller、不是 implementation/fix writer；不启动或重排 Gateflow；未修改任何实现/测试/README/plan/旧 artifact；未 stage/commit/push/PR
- **Scope**: strict deepreview current-changes。完整审查 exact-seven candidate 相对 accepted base 的真实入口，覆盖全部七个当前文件全文、完整 candidate diff、accepted master 全部 Item 7 contracts、acceptance/implementation artifact 与关键未改调用链/Protocols/registries/repository 事实；不以 plan review PASS 代替 code evidence
- **Base**: branch ``codex/investment-platform``、HEAD ``ee75d17955a4a8f30a56a02cae56fac34df79be5``、index empty
- **Actual model / route**: ``deepseek-v4-pro[1m]`` / local Claude Code CLI user-dispatch
- **Date / timezone**: 2026-08-22 / Asia/Shanghai
- **Status / verdict**: ``FAIL / open H/M/L = 0/0/1``（唯一 Low 见 F-01；无 H/M；本结论不是 qualified pass）
- **Independence**: 未读取任何 MiMo code-review artifact 或 MiMo 输出；未运行 tests/pyright/PG/Docker/network/provider/model/Broker；只使用只读 git diff/status/show、rg/grep/sed/shasum/wc；未生成 cache；本 artifact 是唯一写入

## 0. START identity drift gate（全部只读核验，逐项命中后才继续）

| 核验项 | 预期 | 实测 |
|---|---|---|
| branch / HEAD | ``codex/investment-platform`` / ``ee75d17955a4a8f30a56a02cae56fac34df79be5`` | 命中 |
| index | empty | ``git diff --cached --name-only`` 为空，命中 |
| worktree | 恰好 7 个 modified + 唯一 untracked implementation artifact | 命中（exact-seven 7 个 M + ``docs/reviews/implementation-20260817-slice-2.3-item7-startup-registration-codex.md``） |
| canonical candidate diff SHA-256（§6 命令逐字一致，含 ``--binary --no-ext-diff --full-index``） | ``2487df43700abb2334a1e2183dd88358c269ffef82cc39a069941491672510c9`` | 命中 |
| accepted master | ``13dee18b9fcd0ea470b3cf4333904aceb0f82db87098472d1b5b43ce14c03194`` / 3917 / 314076（``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md``） | 命中 |
| acceptance | ``67805449627264ea5b526624e6b43039373d0f2553f39ee315acb43ebb1fa2b9`` / 136 / 9986 | 命中 |
| implementation artifact | ``4ed3982630df251464170ec309d8f93925ef5632930a51fa51485f90a97e8a2f`` / 219 / 14375 | 命中 |
| exact-seven 七文件 SHA-256 / lines / bytes | 见 implementation artifact §3 after 列 | 全部命中 |
| code-review path | 必须不存在 | 命中（ABSENT） |

## 1. 结论（findings-first）

唯一 verdict：``FAIL / open H/M/L = 0/0/1``。

| Finding | 严重度 | 摘要 |
|---|---|---|
| F-01 | Low | PG black-box 模块 docstring 仍宣称“三个真实 Service”，与同文件已 rename 为 exact-four 的测试真值直接矛盾（stale truth）。 |
| OQ-01（不计 H/M/L） | — | preserved WIP 携带的纯格式收拢字节与 §10.1 non-goal“清理历史格式”的关系，需 Controller 裁决（详见 §4）。 |
| OQ-02（不计 H/M/L） | — | 十九阶段失败矩阵未注入 5 个既有 phase-2 seam，覆盖面为 Item 7 增量面（详见 §4）。 |

除 F-01 外，沿真实执行链的核验结论（§3）未发现 correctness、资源释放、幂等/恢复、分支顺序、参数有效性、类型安全、架构/过度耦合、缺失 adverse tests 或 validation 证据层面的 finding。

## 2. Findings

### F-01 [Low] PG black-box 模块 docstring 仍描述 exact-three，与同文件 exact-four 测试矛盾

- **入口**: ``tests/integration/investment/test_identity_repositories_postgres.py`` 模块 docstring。
- **行号**: 行 12–15（当前文件）。
- **输入**: 无（文档真值漂移，不涉及运行时输入）。
- **实际**: 行 12–15 仍写“production startup 组合精确承载三个真实 Service：``investment_identity``（``InvestmentIdentityService``）与 ``durable_jobs``（``JobService``，``platform_service_name == "durable_jobs"``）、``durable_schedules``（``ScheduleService``）”，未含 ``investment_sources``。
- **预期**: 同一文件行 1625 起已把唯一黑盒测试 rename 为 ``test_production_provider_wires_exact_four_service_mapping``，并在行 1685–1711 断言 mapping 精确为 ``investment_identity`` / ``investment_sources`` / ``durable_jobs`` / ``durable_schedules`` 四项；模块 docstring 应同步为四个真实 Service 并包含 ``investment_sources``。
- **直接证据**: 该文件当前字节中行 12–15 的 docstring 文本与行 1685–1690 的 ``assert set(services) == {...}`` 逐项矛盾；候选 diff 只改动了测试函数名/断言（``@@ -1622,19 +1622,21 @@`` 起的 rename hunk），docstring 未随 rename 同步。该文件属 exact-seven，writer 有编辑权但留下 stale truth。
- **影响**: 该文件是后续维护者首先阅读的 owner 文档；其宣称的生产 mapping 真值过时（少一项），与代码断言冲突，可能误导维护与后续 Item 8 lane 改造。无运行时行为影响。
- **最小 fix + 验证**: 把行 12–15 改为“四个真实 Service”，补齐 ``investment_sources``（``InvestmentSourcesService`` / ``PlatformSourceSyncServiceProtocol``）并保留“导入图不含 evidence/portfolio future module”等其它既有表述；验证：UTF-8 重读该段、重跑该 PG lane（plain Gate 2，postgres_identity 本 Item unchanged）、重冻结 exact-seven 该文件身份与统一 candidate diff SHA。
- **风险**: 修复仅改文档字节，无行为风险；但任何字节变化都要求 Controller 按 gate 流程重冻结 identity 并重启双路 review。
- **严重度**: Low。

## 3. 沿真实执行链的核验结论（无 finding 项）

以下每项均以当前文件字节与只读调用链证据逐点核验，不与 implementation artifact 的自我宣称互为证据。

### 3.1 UI/Service/Host/Agent 分层与 production auto vs explicit provider

- ``dayu/services/startup_preparation.py`` 是 Service 层 composition root；新增 import 方向为 services→investment infra/domain/connectors，与既有 services→investment 依赖方向一致，无反向依赖（生产链路行 83–96、100–122）。
- auto-provider 路径：``_default_provider_or_fail``（行 777–821）在 ``explicit_provider is None`` 且 production/integration 时才构造阶段 1 ``_PlatformPreparation``；显式 provider 在行 809–810 立即原样返回 ``(explicit_provider, None, None)``，**任何 Source-specific 构造/注册/封存/发布代码均只存在于 ``_build_production_services_provider``（行 623–715）**，而该函数只在 ``platform_preparation is not None``（auto 路径）时被调用（行 1524–1536）。显式 provider 零 Source 副作用在结构上成立，并有 application 测试 11 个 trap 零调用 + 双 registry 存储 identity/count/sealed 逐项不变的独立证明（测试行 2224–2325）。
- ``build_platform_composition`` 对显式 provider 在行 1457 调用（早于 Host 副作用），对 auto provider 在行 1539 调用且**恰一次**；``recover_host_startup_state`` 在行 1543，即 publish 之后——满足“publish 先于 startup recovery”且 single publish。
- Host/Agent 层零改动；``host: Host`` 与 ``fins_runtime: DefaultFinsRuntime`` 的 concrete 参数形态是 §10.1.1 明令的（“接收同一个 ``Host`` 与已构造的同一个 ``DefaultFinsRuntime``”），不是越界耦合。

### 3.2 shared session factory 与装配顺序

- 唯一 ``preparation.session_factory`` 同时传入 ``PostgresJobStore(session_factory=...)``（行 658）、``PostgresScheduleStore(...)``（行 659，位置参数即 ``session_factory: sessionmaker[Session]``，签名已核）、``PostgresSourceSyncRepository(preparation.session_factory)``（行 680，签名已核）。无第二 engine/session/runtime。
- 装配顺序（行 658–715）与 §10.1.2 及 application 顺序测试的 ``_EXPECTED_PRODUCTION_ASSEMBLY_ORDER``（15 个 seam）逐项一致；``register_descriptor`` → ``register_handler`` → descriptor ``seal`` → execution ``seal`` 各 exact-once，随后 6 臂断言（双 sealed、count==len(batch)==1、descriptor lookup equal、handler identity ``is not``）全部通过后才构造 ``_ProductionServicesProvider``；``provide_services`` 返回精确四项（行 769–774）。``JobExecutionRegistry.get_handler(descriptor)`` 语义已核（返回 handler|None，跨 registry 一致性校验），``register_handler`` 要求 descriptor 已注册且 handler ``job_type`` 与 descriptor 一致——生产注册顺序满足其前置条件。
- ``EXPECTED_PRODUCTION_HANDLER_BATCH`` 是 composition 函数内 immutable 单元素 batch，count 断言取 ``len(batch)``，满足 §3.1“batch/count 唯一真源、精确只含 source descriptor+handler pair”。

### 3.3 19 阶段失败、逆序 close、partial mapping 与 double dispose

- 生产 except 收口顺序（行 1569–1579）为 lifecycle（engine，经 ``owned_lifecycle``=``preparation.identity_service``）→ writer lease → S3 store → queue admission，与既有逆序契约一致；失败矩阵测试以共享 ``close_order`` 断言 ``["pg","lease","s3","redis"]`` 且每项 count==1，并断言 ``recovery_calls == []``、``successful_returns == []``、每个 probe ``failure_hits == 1``（测试行 3308–3392）。engine 只 dispose 一次：阶段 1 失败时阶段 1 自行 dispose 且 ``owned_lifecycle`` 保持 None；阶段 2 失败时只有 ``owned_lifecycle.close()`` 一条路径（行 1569–1579），double-dispose 由 19 参数化用例 + ``test_prepared_runtime_close_retry_disposes_shared_engine_exactly_once`` + PG ``test_production_provider_close_disposes_engine_once`` 共同证明。
- 失败矩阵的 19 个 stage 覆盖 Item 7 增量面的全部风险 seam：7 个新增 constructor、2 个 register、2 个 seal、6 臂断言、provider ``__init__``、``provide_services``（publish 内失败，``attempts==1``、``successful_returns==[]``）；断言为真实命中计数与 exact 顺序，非削弱断言凑 coverage。
- 发布前的 partial mapping 不可能外泄：composition 对象只在 ``build_platform_composition`` 成功返回后才被赋给 ``prepared.platform_composition``；任一前序失败都直接进入 except 收口。

### 3.4 public facade 与 private execution 的 Protocol 边界

- ``InvestmentSourcesService.__init__`` 只收 ``SourceManualJobGatewayProtocol`` / ``SourceScheduleGatewayProtocol`` / ``SourceSyncRepositoryProtocol`` 三个窄协议（签名已核），``platform_service_name == "investment_sources"``；``SourceSyncExecutionService.__init__`` 只收 ``SourceSyncRepositoryProtocol`` + ``SourceConnectorRegistry``（签名已核）；``SourceSyncExecutionHandler.__init__(*, execution_service: SourceSyncExecutionServiceProtocol)`` 只持 protocol、``job_type`` 来自 descriptor 且 ``execute`` 单次委托（已核）。生产构造把 concrete 传入 protocol 位置，属结构类型正常装配；concrete narrowing（``isinstance`` + 私有属性断言）只出现在两个 test owner 中，未掩盖协议问题（测试同时断言 protocol 满足与真实共享 factory）。
- ``SOURCE_SYNC_JOB_DESCRIPTOR``：``job_type="investment.source-sync.v1"``、``payload_schema_name="investment.source-sync"``、``version=1``、max_attempts=3、retry 30/300、lease 900，与 §3.4 逐字段一致（已核 ``source_sync.py:29–56``）。
- ``dayu/services/__init__.py`` 只导出 ``InvestmentSourcesService``，无 private execution 类型 re-export（已核）。

### 3.5 application tests 的真实证明力

- exact-four/exact-one 测试断言：四项 mapping 集合、``InvestmentSourcesService`` 实例与稳定名、双 registry sealed+count==1、descriptor lookup 相等、handler 为 ``SourceSyncExecutionHandler`` 且其 ``_execution_service._repository is source_repository``、connector registry 单 connector、``FinsService.host is bare_host``、``fins_runtime is prepared.fins_runtime``、三个 store ``_session_factory is session_factory``——均为 identity/类型级真实断言。
- explicit-provider 测试用**真实** ``DefaultFinsRuntime.create``（记录工厂）跑完整 prepare，断言 eager ``_source_sync_runtime`` component、11 个 trap 零命中、caller 双 registry 存储 identity/count/sealed 状态在 run 前与 ``prepared.close()`` 后逐项不变——不是 mock 自证。
- closed-shape 测试逐分支以 ``pytest.raises(..., match=...)`` 断言 6 类非法 admission shape 的精确错误文案，且对应生产 ``__post_init__`` 的分支矩阵（``kind 非法`` 分支因需要非枚举值、受本文件 AST 逃逸 guard 约束而未覆盖，属可接受缺口）。
- 文件自守 AST guard（``test_startup_preparation_test_avoids_escape_patterns``）保持，新增代码未引入 Any/object/cast/ignore。

### 3.6 PG black-box exact-three→exact-four rename

- 唯一 rename：``test_production_provider_wires_exact_three_service_mapping`` → ``test_production_provider_wires_exact_four_service_mapping``（行 1625）；旧名全仓零残留、新名恰好一次（已用只读 grep 全量核验五个 startup names 各 exactly once、四个历史名各 0 次）。
- 新增断言：第四项满足 ``PlatformSourceSyncServiceProtocol`` 且是 ``InvestmentSourcesService``（行 1693–1696）；其 ``_source_repository`` 是 ``PostgresSourceSyncRepository`` 且 ``_session_factory`` 与 ``PostgresJobStore``/``PostgresScheduleStore`` 的 ``_session_factory`` **同一实例**（``is``，行 1703–1711）；identity 的 company/security 注册断言（行 1712–1716）与重复 ``prepared.close()``（行 1717–1718）原样保留；另有既有的 engine dispose 恰一次黑盒测试未被触碰。
- state leak：该 lane 沿用既有 owner-label fixture teardown 与 ``_cleanup_production_startup_resources`` 全链清理；本 item 未改变 fixture 语义，未引入新外部资源。

### 3.7 四份 README 只描述已物化真值

- 根 ``README.md``：唯一 hunk（``@@ -382,9 +382,10 @@``）替换原 :385–387 段为 4 行，含“exact-one production Source Sync handler”“production execution registry 仍无 research/Agent/Broker handler”“启动期会构造并发布 platform production composition”“本仓库当前不提供 production Compose”“production Compose 仅指部署编排文件，platform production composition 仅指平台装配”，大小写敏感术语与 §11/§14.0.8 一致；``README.md:134`` 的既有部署真值行不在任何 hunk 内（byte zero diff）；无其它改动。
- ``tests/README.md:53``：exact-four 四项名 + exact-one Source Sync handler + 共享 PostgreSQL session factory，与黑盒测试真值一致。
- ``dayu/README.md:155–157``：不再声称 production execution registry 为空；写明原子发布前注册并封存 exact-one Source Sync handler、四项 Service、无 research/Agent/Broker handler，不泄漏具体实现类名。
- ``dayu/investment/README.md:268–269``：exact-one Source Sync handler、无 research/Agent/Broker handler，未注册 handler 稳定失败收敛表述保留。
- 四份 README 均无“registry 为空”残留、无 Item 8 final-nine-lane 完成声明（已 grep 核验；唯一命中为 20-F 章节边界的无关“Item 8/9/10”文本）。

### 3.8 其它维度的核验结论

- **correctness**: 未见逻辑错误；注册/封存/断言/发布顺序与 registry 实现的前置条件互相满足。
- **exception / resource release**: 阶段 1 与阶段 2 的失败收口路径闭合，engine 单次 dispose、Redis/S3/lease 逆序幂等关闭均有真实测试证明。
- **idempotency / recovery**: 重复 ``close()``、atexit 协调、publish 恰一次、startup recovery 位于 publish 之后，均已被现有测试锁定。
- **branch ordering**: explicit 早退 > 阶段 1 admission > S3/lease > Host > 阶段 2 > publish > recovery 的顺序未被打乱。
- **parameter effectiveness**: ``queue_settings``（ScheduleService 参数）、``wakeup_publisher``（JobServiceRuntimeAdapters）、``host``（reader/canceller + FinsService）、``fins_runtime``（FinsService）全部实际生效，无死参数。
- **type safety**: 新代码全强类型（batch 局部注解、protocol 注入），writer 报告的 Pyright 0/0/0 与既有 owner guard 一致；本次审查未运行 Pyright（约束禁止），此为证据采信边界（见 §5）。
- **architecture / overcoupling / overengineering**: 未引入新 lifecycle owner、未发明新状态；``SourceSyncExecutionService`` 未进入 platform mapping（仅 public facade 进入），符合 §3.3 拆分契约。
- **missing adverse tests**: 除 OQ-02 所述 5 个既有 seam 未逐点注入外，未发现其它必需而未覆盖的 adverse 场景。
- **validation evidence 是否足以 ship**: writer 的 §14.0 八步证据（64 focused、171 architecture、AST 5/4、Pyright/Ruff、fresh branch 80.48%、PG16 17 passed + 零残留、8863 non-integration、README/机械边界）记录完整、口径与 plan 一致；本次审查受 handoff 约束不能重跑，只能以字节级证据与证据账本一致性支撑结论（见 §5 Residual）。

## 4. Open Questions

- **OQ-01（不计 H/M/L）**: candidate 的 ``dayu/services/startup_preparation.py`` 相对 HEAD 含约 8 处纯格式收拢 hunk（如行 503–507、614、821、1286–1290、1348、1517、1669–1670 的括号合并/行合并，无任何语义变化）。这些字节属于 Controller 在 plan-fix §1 冻结、acceptance §1 明令 preserve-and-adopt 的 preserved WIP（implementation artifact §3 证明该文件 before/after identity 相同，Item 7 writer 零改动），但 accepted master §10.1 non-goal 又明确“不借 startup 交付……清理历史格式”。两者对同一批字节给出了相反的处置信号。需 Controller 裁决：①承认这些 WIP 字节为已接受输入、豁免 non-goal；或②要求 revert 格式 hunk 并重冻结 candidate SHA。本 review 不自行关闭该问题，也不因其单独判 FAIL。
- **OQ-02（不计 H/M/L）**: 十九阶段失败矩阵覆盖了 Item 7 增量面的全部 seam，但未对 5 个既有 phase-2 seam（``PostgresJobStore``/``PostgresScheduleStore``/``JobHandlerRegistry``/``JobExecutionRegistry``/``JobService``/``ScheduleService`` 构造）单独注入失败；这些构造器均为纯赋值、可失败面极小，且其失败会进入同一 except 收口路径（已被 19 个 stage 的 exact close-order 断言间接证明）。是否需要补第 20–24 阶段，由 Controller 判断；本 review 认为不构成 material finding。
- **OQ-03（不计 H/M/L）**: ``tests/application/test_service_startup_preparation.py`` 模块 docstring（行 1–14）仍以“Slice 0.2 的平台设置 / 组合注入点行为”为引言，而文件现承载 64 项测试（含 Item 7 装配矩阵）。这是过时而非虚假表述（不同于 F-01 的直接矛盾），且属 preserved WIP 字节，仅作观察记录。

## 5. Residual Risk

1. 本 review 未运行 tests/pyright/PG/Docker/network/provider/model/Broker（handoff 硬约束）。§3.8 的 validation 结论基于字节级证据与实现证据账本的一致性采信，不是独立重跑。
2. ``dayu/services/startup_preparation.py`` 的 fresh branch coverage 原始值为 80.48%，紧贴 ≥80.0 门槛；后续任何改动都可能跌回门禁以下，需在每次修改时重跑 fresh singleton lane。
3. OQ-01 若按 revert 处置，source 文件身份与 canonical candidate SHA 将变化，全部已记录 identity 需重冻结。
4. F-01 修复属 exact-seven 内字节变化，同样触发 candidate SHA 重冻结与双路 review 重跑。
5. 本候选仍含 preserved WIP 的历史格式噪声，增大了后续 diff 审查面（与 OQ-01 同源）。

## 6. END identities 与边界证明

本 artifact 自身最终 SHA-256 / 行数 / 字节数**不嵌入自身 preimage**（避免自包含 SHA 循环，与 acceptance artifact 约定一致），由 reviewer final report 只读重算并报告。

exact-seven 七文件 END 身份复核（与 §0 START 完全相同，逐项命中）：

| path | SHA-256 / lines / bytes |
|---|---|
| ``dayu/services/startup_preparation.py`` | ``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` / 1689 / 63289 |
| ``tests/application/test_service_startup_preparation.py`` | ``2707df2a5e81357b590c78e474f74f60778e945d5d853d983a3877e778fca545`` / 4123 / 130135 |
| ``tests/integration/investment/test_identity_repositories_postgres.py`` | ``b0049d210864fd3246562c50e926b90793169b6fc694a60401b88d4478004d53`` / 2123 / 73549 |
| ``README.md`` | ``d3760a46b7c0ce8cc0da0c26d1d4789d7c444560e9d1c7c5d677398dbffb4a94`` / 2407 / 153621 |
| ``tests/README.md`` | ``1db72b00c63c0afcc8ebd81d8220383cec3efb501928c00466b78c7f897c992f`` / 612 / 132898 |
| ``dayu/README.md`` | ``8fbf8605b9ec7bac1a84f3cf78d17bedc2e99f83bfea285e53307924838ccfe5`` / 1297 / 65205 |
| ``dayu/investment/README.md`` | ``1e39d2746962144d0f4a4ff1ca7f77063796fbddb35a1f4e70e0fbe708244331`` / 333 / 22921 |

三个 lineage artifact 复核（与 §0 完全相同）：

- accepted master ``13dee18b9fcd0ea470b3cf4333904aceb0f82db87098472d1b5b43ce14c03194`` / 3917 / 314076；
- acceptance ``67805449627264ea5b526624e6b43039373d0f2553f39ee315acb43ebb1fa2b9`` / 136 / 9986；
- implementation artifact ``4ed3982630df251464170ec309d8f93925ef5632930a51fa51485f90a97e8a2f`` / 219 / 14375。

边界证明（END 时点只读核验）：

- branch 仍为 ``codex/investment-platform``；HEAD 仍为 ``ee75d17955a4a8f30a56a02cae56fac34df79be5``；index 仍为空（``git diff --cached`` 无输出）。
- worktree modified 仍精确为 exact-seven 7 个 path，无第八个 modified。
- untracked 为三个：本 code-review artifact、implementation artifact，以及本 session 期间由平行 MiMo reviewer 写入的 ``docs/reviews/code-review-20260817-slice-2.3-item7-startup-registration-mimo.md``。START 时该 MiMo path 不存在（§0 已记录 ABSENT）；本 reviewer 未读取其内容，独立性不受影响，此仅为 END 边界如实记账。
- 未创建任何 cache、``.coverage``、pyc 或其它临时产物；除本 artifact 外零写入。
