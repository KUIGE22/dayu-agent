# Slice 2.3 Item 7 startup registration corrective plan review（DeepSeek V4 Pro）

- 日期：2026-08-17
- 角色：独立 plan reviewer（DeepSeek V4 Pro 首审）；非 Controller、非 Codex plan-fix writer、非 implementation writer
- 结论：``FAIL / open H/M/L=0/0/1``
- 冻结语义三元组（本 review 只证明以下字节）：
  - target（master plan，working tree 修改态）：
    ``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md``，SHA-256
    ``e75e77e3382bccfa7f2ecd891381761176e9ea163f38b8c60f22391b716c517e``，3852 行；
  - fix（Codex plan-fix artifact）：
    ``docs/reviews/plan-fix-20260817-slice-2.3-item7-startup-registration-codex.md``，SHA-256
    ``582e21966240154913e1e475999b8b8608634b89a6bde1393eb9275fe75a93c0``，118 行；
  - preserved WIP（未改写、未运行，只读复核）：
    ``dayu/services/startup_preparation.py`` SHA-256
    ``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` / 1689 行；
    ``tests/application/test_service_startup_preparation.py`` SHA-256
    ``a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2`` / 4044 行。
- 冻结环境：branch ``codex/investment-platform``，HEAD ``d604d8df7613db0103076b3a727156fd74dd9e1b``；
  index 为空，untracked 仅 fix artifact 自身，``git diff --check`` clean。以上与 fix §1/§5 及 master 文件头
  Gate 逐项一致，无漂移。
- 本 review 只读：零代码/测试修改、零测试运行、零 stage/commit/push/PR；不运行 provider/model/network/PG。

## 1. 证据核验 ledger

只读核验 fix 全部直接证据引用，全部成立：

- Item 6 accepted artifact ``docs/reviews/code-review-20260814-182909.md:61-64`` 明确
  ``item7_started=false``、``item8_started=false``（L12 plain lane 记录），不能用 Item 6 证据冒充 Item 7；
- ``tests/integration/investment/test_identity_repositories_postgres.py:1625`` 现为
  ``test_production_provider_wires_exact_three_service_mapping``，1625-1682 断言 exact-three key set
  ``{investment_identity, durable_jobs, durable_schedules}``，与 fix 引用一致；
- ``tests/README.md:53`` 仍写 production provider mapping 精确为三个 Service；
  ``dayu/README.md:155-156`` 仍写“production execution registry 为空，这条基础设施链不包含
  source/research/Agent/Broker handler”；``dayu/investment/README.md:268`` 仍写“production
  descriptor/execution registry 当前为空”。三者确为 Item 7 落地后立即失真的旧真值；
- master §10（2535-2575，本次 zero diff）已要求 auto-provider exact-four mapping、唯一 handler batch、
  seal 后断言与逆序 close；exact-three 的“漂移”源不在 §10 而在旧 per-slice 测试/README 真值，动机成立；
- preserved application WIP 中五个 Item 7 startup names 中的前四个各定义 exactly once：
  ``test_explicit_production_provider_...``（2085）、``test_auto_production_registry_counts_...``（3101）、
  ``test_production_provider_failure_disposes_one_engine_once``（3231，经
  ``@pytest.mark.parametrize("failure_stage", _ITEM7_FAILURE_STAGES)``）、
  ``test_production_composition_constructs_...``（3623）；
  ``_ITEM7_FAILURE_STAGES``（641-661）恰为十九阶段 constructor/register/seal/assert/provider/publish matrix；
- ``test_auto_production_registry_counts_...`` 仅有单行 docstring（3105），确为 Item 7 delta 内唯一缺
  ``Args/Returns/Raises`` 的名字；读 AST 复核：五个 delta names 中只有它不完整；
- AGENTS.md 引用行准确：35（docstring 参数/返回值/异常）、61-65（测试与验证）、68-92（README 同步）；
- WIP rename 证据（``git diff`` 只读）：旧名 ``test_production_explicit_provider_keeps_custom_composition_after_redis_admission``、
  ``test_production_provider_exposes_exact_slice22_service_mapping_with_empty_execution_registry``、
  ``test_source_handler_registration_remains_absent_until_slice_2_3`` 已由 WIP 原位改名，不在工作树任何
  production/test 字节中；committed catalog 当时已含三个新名，drift 确为 catalog↔file 双向往返。

## 2. 生产代码与 §10.1 handoff 逐条对照

``dayu/services/startup_preparation.py``（只读走查）与 master §10.1 六步逐条一致：

1. ``_build_production_services_provider``（623）接收同一 ``Host``、同一 ``DefaultFinsRuntime``，以同一
   ``preparation.session_factory`` 构造 Job/Schedule/Source stores，无第二 engine/session/runtime；
2. 构造顺序精确为 JobService → ScheduleService → FinsService → FinsSourceConnector →
   PostgresSourceSyncRepository → SourceConnectorRegistry → InvestmentSourcesService →
   SourceSyncExecutionService → SourceSyncExecutionHandler；public facade 与 private execution owner 分离；
3. register_descriptor → register_handler → descriptor seal → execution seal 后，单处断言双 sealed、
   count==1、lookup equal、handler identity；无并发注册语义；
4. provider 仅在断言后构造，``provide_services``（756）暴露精确四项；
   ``_prepare_host_runtime_after_queue_admission``（1389）对 auto 分支只调用一次
   ``build_platform_composition``（1539），早于 ``recover_host_startup_state``（1543）；
5. failure 路径逆序收口 lease/S3/lifecycle/admission，engine 由 ``owned_lifecycle``（identity_service）
   唯一 close，19 阶段失败不产生 partial mapping、不重复 dispose；
6. explicit-provider 分支（1455-1462）不触达任何 Source-specific constructor/register/seal，只保留
   baseline eager ``DefaultFinsRuntime.create``（1498）。

PG black-box 扩展可构造：``InvestmentSourcesService(PlatformSourceSyncServiceProtocol)``
（``dayu/services/investment_sources.py:490``），第四项协议断言、真实
``PostgresSourceSyncRepository`` 共享 production session factory 断言均可达。

## 3. 闭环决定与 validation contract 对照

- 174→176 catalog 算术成立：committed catalog 缺 failure-matrix 名与 PG exact-four 名，+2 精确；五个
  startup names 的 owner 归属（前四 application、唯一 PG）与 master §13.1 一致；
- fix §4 八项 validation 与 master §14.0 八步逐项镜像；PG 为 unchanged
  ``postgres_identity.py`` 的 plain Gate 2、不冒充 Gate 1 coverage；digest 与 §14 Gate 2 同一 pinned 值；
- exact-six allowlist、Item 8 收窄（两 workflow + ``tests/README.md`` final-nine-lane，两个 Dayu README
  zero diff）、docs-only plan checkpoint 只 stage 本轮 docs、WIP 不混入——master §11/§12/§14/§17.2 内自洽；
- 三份 README 职责归属符合 AGENTS.md 固定职责划分；§15 新增三项 STOP 与 §16 新增 residual 恰当；
- §17.1 标题“（current）”与 §17.2 首条的 historical 声明不冲突，§17.2 为当前真源。

## 4. Findings

### S23-I7-DSV4P-01（Low）：改名旧名残留未进 fail-closed 名单

master §13.1/§14.0.3 的 Item 7 mechanical audit 只把旧 ``test_production_provider_wires_exact_three_service_mapping``
列为残留/双名并存 fail closed；WIP 原位改名的三个旧名
``test_production_explicit_provider_keeps_custom_composition_after_redis_admission``、
``test_production_provider_exposes_exact_slice22_service_mapping_with_empty_execution_registry``、
``test_source_handler_registration_remains_absent_until_slice_2_3`` 不在零残留断言内。这三个旧名断言的是与
新名直接矛盾的旧行为（custom composition after redis admission / empty execution registry / source handler
absent until slice 2.3）；若 writer 在允许的最小增量修复中误留其一，五名各一次的 AST 断言与 176 aggregate
审计都不会失败，只能靠 focused lane 运行时撞红。本 corrective 的动机恰是机械闭合 catalog↔file 漂移，而
§14.0.3 自身标准“字符串 grep 或只看 pytest PASS 不能替代”要求 name-level 机械闭合。

建议：§13.1 审计段与 §14.0.3 的零残留断言把上述三个旧名与 exact-three 旧名并列纳入“残留或双名并存均
fail closed”。

### 信息性说明（不计 finding）

1. fix §1“当前唯一 Low documentation gap”严格按 Item 7 five-name delta 口径成立；preserved application WIP
   中另有若干 Item 6 已接受内容/局部 fake 的历史简版 docstring，不在任何扫描 tests/application 的 gate 内，
   §10.1 non-goals 已明确排除历史格式清理，不属 Item 7 修复义务。
2. “上述五个startup names”指当前 master §13.1 2963-2967 行五个 Item 7 delta names；2961-2962 两个
   register/seal names 属 Item 6，不在 Item 7 incremental audit 内，与 174→176 算术一致。

## 5. Verdict

``FAIL / open H/M/L=0/0/1``。除 S23-I7-DSV4P-01 外，冻结证据、§10.1 六步、exact-six、catalog 算术、
validation contract、artifact/staging 规则均只读核验一致，无 Blocking Question 留给 Controller。
本 review 不引用、不共享任何 MiMo 首审内容；只证明 §0 冻结三元组。
