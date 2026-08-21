# Slice 2.3 Item 7 startup registration corrective plan re-review（DeepSeek V4 Pro）

- 日期：2026-08-22
- 角色：独立 plan reviewer（DeepSeek V4 Pro 复审，与 20260817 首审同一 reviewer/model route）；非 Controller、
  非 Codex plan-fix writer、非 implementation writer
- 结论：``FAIL / open H/M/L=0/1/1``
- 复审对象（post-fix 冻结语义三元组，本 artifact 只证明以下字节）：
  - target（master plan，working tree 修改态）：
    ``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md``，SHA-256
    ``65007079da72782d21ea35d4c2ebc502661665983229f6c651be8c80aef21403``，3859 行 / 308008 字节；
  - fix（Codex plan-fix artifact，含 §8 writeback）：
    ``docs/reviews/plan-fix-20260817-slice-2.3-item7-startup-registration-codex.md``，SHA-256
    ``363e8916ffcf245581bfa0747a5b0d7a82da0f6d08f065e37cf791641d388644``，132 行；
  - prior review（本 reviewer 首审，只读引用其结论口径，不复用其证据）：
    ``docs/reviews/plan-review-20260817-slice-2.3-item7-startup-registration-deepseek-v4-pro.md``，SHA-256
    ``714dfa4f51d5ec70a40574ff9cf6fa0d7547d69a082a6e5258ec567fe6d2d38d``，115 行，``FAIL / open H/M/L=0/0/1``；
  - preserved WIP（未改写、未运行，只读复核）：
    ``dayu/services/startup_preparation.py`` SHA-256
    ``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` / 1689 行；
    ``tests/application/test_service_startup_preparation.py`` SHA-256
    ``a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2`` / 4044 行。
- 漂移门：cwd ``/Users/wsk/workspace/dayu-agent``；branch ``codex/investment-platform``；HEAD
  ``d604d8df7613db0103076b3a727156fd74dd9e1b``；index 空；untracked 仅两份 Item 7 docs artifact；
  ``git diff --check`` clean。两个 preserved WIP 的 SHA/行数与文件头 Gate、fix §1 逐字节一致，**零漂移**。
  master 与 fix artifact 相对首审冻结值的变化即 fix §8 writeback 本身，属预期 post-fix 态（见 §1）。
  actual model ``deepseek-v4-pro[1m]``，本轮无 HTTP 402/配额失败。
- 本 review 只读：零代码/测试/plan 修改、零测试运行、零 stage/commit/push/PR；不运行 provider/model/network/PG/Docker。
- 独立性：本 artifact 不引用、不共享任何 MiMo 输入或输出。

## 1. Writeback 边界核验（master 相对首审冻结值）

首审冻结 master 为 ``e75e77e3…`` / 3852 行 / 307390 字节；当前为 ``65007079…`` / 3859 行 / 308008 字节，
Δ=+7 行 / +618 字节。fix §8 声称 writeback 精确为 ``:3011-3018`` 与 ``:3320-3328`` 两处。只读复核：

- **行号锚点不变**：首审引用的 ``§10`` 仍在 2535-2575、``§10.1`` 仍在 2577、``§13.1`` 五个 Item 7 delta names
  仍在 2963-2967。3011 之前所有 section 锚点行号逐项不变，证明 §13.1 之前**零净行变化**；
- **字节算术闭合**：三个新增旧名以 ``\`\`name\`\``` 形式各出现于两处，纯名字字节 (80+92+63+3×4)×2 = 494；
  余下 124 字节为两处连接词（``、``/``或``/``且下列四个旧名各零次：``等 CJK 多字节），与 +618 精确相符。
  该算术不给任何第三处实质性编辑留出空间；
- **normative 面未变**：``§10``/``§10.1`` 六步、``§11`` exact-six、``§11.1`` 44 keys、``§14.0`` 八步命令与
  digest、``§12`` Item 7/Item 8 边界、``§15``/``§16`` 既有条目，均与首审所证一致。

说明：首审冻结的 pre-fix master 本身是未提交的 working-tree 态，其字节不可从 Git 恢复，故本节以
**section 锚点行号不变性 + 字节算术 + 内容逐条比对**证明 writeback 有界，而非 byte-diff。这是本轮可得的最强证据。

## 2. S23-I7-DSV4P-01 复核结论：**CLOSED**

首审 Low 要求把 WIP 原位改名的三个旧名与 exact-three 旧名并列纳入 ``§13.1`` 审计段与 ``§14.0.3`` 零残留断言。
只读复核两处均已闭合：

- ``§13.1:3011-3018``：``alias、wrapper、dynamic generation、substring match``、旧
  ``test_production_provider_wires_exact_three_service_mapping``、
  ``test_production_explicit_provider_keeps_custom_composition_after_redis_admission``、
  ``test_production_provider_exposes_exact_slice22_service_mapping_with_empty_execution_registry``、
  ``test_source_handler_registration_remains_absent_until_slice_2_3``「任一残留或与 new names 双名并存均 fail closed」；
- ``§14.0.3:3320-3328``：以 ``ast.parse`` 递归收集两个 test owner 的 ``FunctionDef/AsyncFunctionDef.name``，
  断言五个新名各 exactly once **且上述四个旧名各零次**，并要求该 AST command exit 0、明确「字符串 grep 或只看
  pytest PASS 不能替代」。即 fail-closed 集合已由文档层进入可执行断言层。

动机与可行性只读复证（本轮独立取证，不复用首审证据）：

- 三个旧名在 HEAD 的 ``tests/application/test_service_startup_preparation.py``（:1352、:2233、:2679）确实存在，
  在当前工作树全仓已零命中——即 WIP 已完成原位改名，旧名回流是真实且不被其它 gate 捕获的风险；
- 五个新名中前四个在 ``tests/application/test_service_startup_preparation.py`` 各定义一次
  （:2085、:3101、:3231、:3623），第五个 ``test_production_provider_wires_exact_four_service_mapping``
  当前不存在（由 PG black-box rename 产生），与 ``§13.1:3011-3013`` 的 owner 归属一致；
- 旧 exact-three 仍在 ``tests/integration/investment/test_identity_repositories_postgres.py:1625``，为 rename 目标；
- writeback 只落在审计/断言段，未改 normative implementation contract、exact-six allowlist、validation command、
  path/lane 或 Item 8 边界（§1 已证）；未修改或执行任何 production/test 文件。

**该 Low 不再 open。**

## 3. Fresh adversarial 复核 ledger（本轮独立重做，不继承首审结论）

- **catalog 算术**：机械解析 ``§13`` 全部 bullet named tests（含 ``；`` 结尾形态）得 13.1=54、13.2=42、13.3=53、
  13.4=27，合计 **176，零重复**，与 ``§13:2951`` 的「当前总数精确为 176，所有名字唯一」及 ``§14.0.7:3536`` 的
  aggregate 口径逐值相符。首审只证 174→+2 的增量口径，本轮补证了绝对总数；
- **Item 7 delta 归属**：``§13.1:3011`` 的「只认上述五个 startup names」成立。2961-2962 两个 register/seal names
  实际定义在 ``tests/application/test_job_service.py:908/935``（已物化、非 Item 7 owner file），不属 Item 7 delta，
  不影响增量审计；
- **唯一 Low 的真实性与唯一性**：AST 复核五个 delta names 的 docstring——
  ``test_auto_production_registry_counts_…``（:3101）为单行 docstring，无 ``Args/Returns/Raises``；
  其余三个 application names 与 PG black-box name 均三段齐备。``§14.0.3`` 要求断言 ``Args`` 逐名含
  ``monkeypatch:``/``tmp_path:``，与该函数签名 ``(monkeypatch: pytest.MonkeyPatch, tmp_path: Path)`` 精确匹配；
- **§10.1 六步对生产 WIP 的可满足性**：``_build_production_services_provider``（:623）以同一
  ``preparation.session_factory`` 构造 Job/Schedule/Source stores、同一 ``Host``/同一 ``DefaultFinsRuntime``
  只构造一个 ``FinsService``（:678）；构造序列 :658-691 与 §10.1 第 2 步逐项同序；register→register→seal→seal
  后单处断言双 sealed/count/lookup/identity（:696-709）；provider 仅在断言后构造（:710），
  ``provide_services``（:756）暴露精确四项；auto 分支只调用一次 ``build_platform_composition``（:1539）且早于
  ``recover_host_startup_state``（:1543）；explicit 分支（:1455-1460）零 Source-specific 装配，只保留 baseline
  eager ``DefaultFinsRuntime.create``（:1498）；失败路径（:1569-1579）按 lifecycle→lease→s3→admission 逆序收口，
  engine 由 ``owned_lifecycle`` 唯一 dispose；
- **十九阶段 failure matrix**：``_ITEM7_FAILURE_STAGES``（tests :641-661）实为 19 项 constructor/register/seal/
  assert/provider/publish 全序，与 ``§10.1:2609`` 的「十九阶段失败」逐项相符；
- **README 目标真值实存**：``tests/README.md:53`` 仍为 exact-three；``dayu/README.md:156`` 与
  ``dayu/investment/README.md:268-269`` 仍称 production execution registry 为空。三者确为 Item 7 落地即失真的旧真值，
  ``§14.0.8`` 的机械断言对这三份文件可判定；
- **lane/coverage 自洽**：``§11.1`` 中 ``dayu/services/startup_preparation.py`` 的 owner tuple 为 singleton
  ``(tests/application/test_service_startup_preparation.py,)``，与 ``§14.0.5`` 的 fresh exact-singleton lane 一致；
  ``postgres_identity.py`` 本 Item unchanged，故 ``§14.0.6`` 定为 plain Gate 2、不冒充 Gate 1，正确；
- **Item 8 收窄**：``§12:2867-2871`` 与 ``§14:3556-3558`` 一致地把 Item 8 限制为两 workflow +
  ``tests/README.md`` final-nine-lane，且两份 Dayu README zero diff、不得重写 Item 7 已接受文本。

以上均只读成立，除下述两项 finding 外无其它异议。

## 4. Findings

### S23-I7-DSV4P-RR-01（Medium）：root ``README.md`` 携带同一条被 Item 7 证伪的真值，却被永久锁为 zero diff，且不在 README 审计集内

``README.md:385-387`` 逐字写着：

> 当前只交付 generic Scheduler/Worker 与 durable 队列基础设施：production execution registry
> 为空，不包含 source/research/Agent/Broker handler，不包含 production Compose，也不会自动调用
> provider、模型、Broker 或执行真实交易。

这与 ``dayu/README.md:156``、``dayu/investment/README.md:268-269`` 是**同一条 production execution registry
为空的旧真值**。Item 7 落地后 auto-provider 在 startup 注册并封存 exactly-one Source Sync handler
（``§10:2571-2575``、``§10.1:2594-2599``），该子句即刻变为字面假。问题在于计划对同一条真值给了三种互斥处理：

1. ``§11:2742-2743`` 把 ``dayu/investment/README.md`` 纳入 Item 7 的**唯一理由**正是「因其『production registry
   当前为空』会在 Item 7 落地后立即失真」；按该判据，root ``README.md`` 必须同样纳入；
2. ``§11:2744`` 却写「root``README.md``、``dayu/fins/README.md``、两份 workflow 及其它 production/test/docs
   一律 zero diff」，并要求任一 exact-six 之外的 README 改动立即 STOP（``§15:3623`` 同义）；
3. ``§15:3626-3627`` 又把「Item 7 …… **README 仍声明 production registry 为空**」列为 STOP condition，
   且该句**未限定文件集**。

于是 Item 7 收尾时两条 STOP 必然触发其一：改 root README → 撞 ``§15:3623``；不改 → 撞 ``§15:3626``。
计划在别处是会按 Item 限定该约束的（``§15:3613`` 的 root README zero-diff STOP 明确只写给「prerequisite 或
Item 6 main」），这里却没有，说明是遗漏而非有意留白。

更关键的是**检测面与修复窗口同时缺失**：

- ``§14.0.8:3391-3395`` 的机械 README 审计只「以 UTF-8 读取三份 README」，「不再含 production execution registry
  为空的旧真值」只断言 ``dayu/README.md`` 与 ``dayu/investment/README.md``。root README 不在读入集合，
  gate 会全绿通过，而仓库主用户手册留着一句假话；
- ``§12:2867-2871`` 把 Item 8 收窄为两份 workflow 与 ``tests/README.md`` 的 final-nine-lane 段，
  明确排除 root README；Item 8 之后只剩 Slice aggregate **gate**（非 writer slice）。因此该子句在本 Slice 内
  **没有任何被修正的机会**，将随 Slice 2.3 一并交付；
- root ``README.md`` 本就在 ``§11:2672`` 的 Slice 全局 allowlist 内，纳入 Item 7 不需要突破 Slice 边界；
- AGENTS.md「文档与 README 同步」是硬约束：「测试通过后，立即同步更新相关 README；以代码为准，不写未来设计」
  「只更新 README 中与当前代码不一致的部分」。落地一个证伪主用户手册的变更并同时禁止修正它，与该硬约束直接冲突。

本条与已关闭的 S23-I7-DSV4P-01 属同一族（fail-closed 集合少列成员），但严重度更高：那一条是**可能**发生的检测
盲区，本条是**必然**发生的文档失真，且计划明文关闭了修复路径。

建议（按可维护性优先，取其一并同步三处）：

- 首选：把 Item 7 writable set 由 exact-six 扩为 **exact-seven**，新增 ``README.md`` 且严格限定为
  ``:385-387`` 该一条子句的最小真值修正（其余 root README 内容 zero diff）；``§14.0.8`` 的读入集合与
  「不再含 registry 为空」断言同步扩为四份 README；``§15:3623`` 的「exact-six」表述随之更新；
- 次选（若 Controller 坚持 root README 冻结）：必须同时 (a) 把 ``§15:3626`` 显式收窄为三份 in-scope README，
  (b) 在 ``§16`` 新增一条具名 residual 记录该已知假值与其后继 owner work unit。但这与 AGENTS.md 文档同步硬约束
  相抵，不推荐。

### S23-I7-DSV4P-RR-02（Low）：master 未冻结 Item 7 plan-review 轮次账本，且 checkpoint stage 集合未涵盖 ``plan-rereview`` artifact

master 文件头 :4 仍为 ``… PLAN-FIX CANDIDATE / … / FRESH SAME-SHA DEEPSEEK V4 PRO + MIMO PLAN REVIEW NEXT``，
``§17.2:3855`` 仍称「本 candidate 仍是 ``PLAN-FIX WRITTEN / NOT REVIEWED``」。但事实上：

- 首审已发生并留有 artifact ``docs/reviews/plan-review-20260817-slice-2.3-item7-startup-registration-deepseek-v4-pro.md``
  （``714dfa4f…`` / 115 行，``FAIL / open H/M/L=0/0/1``）；
- 其唯一 Low 已被 Controller 接受并**写回 normative 段** ``§13.1``/``§14.0.3``（fix §8:120-132）。

即 master 的 normative 面已承载首审结论，其 bookkeeping 面却仍声明「未被 review」。``§17`` 恰是
「Corrective acceptance bookkeeping」，``§17.1:3840-3846`` 为 Item 6 建立的先例是逐轮冻结 reviewer artifact 的
SHA/行数/actual model/route/verdict 与 accepted-closed findings；``§17.2`` 对 Item 7 一条未记。只读 Controller 若只看
文件头与 ``§17.2``，会误以为 ``§13.1``/``§14.0.3`` 的四名 fail-closed 集合是原始设计，而非一轮 FAIL 的产物。
``§17.2`` 同样未为另一 review route 记录任何轮次状态；本 reviewer 按独立性规则不观察、不引用、不评价该路
artifact 是否存在或其内容，只指出 master 缺少该 route 的账本位。

这不只是记账问题，还有一个可执行后果：``§17.2:3858`` 的 checkpoint stage 规则写作「只 stage 本轮 plan/fix 及
随后产生的 plan-review/acceptance artifacts」，未含 ``plan-rereview-*`` 形态；而 ``§14.0.1:3301`` 的 Item 7 dispatch
preflight 要求 ``git ls-files --others --exclude-standard`` 为**空**。任何未被枚举因而漏 stage 的轮次 artifact
都会让该 preflight 在 dispatch 当场 STOP。

建议：``§17.2`` 增记 Item 7 plan-review 轮次账本（首审 artifact 路径/SHA/行数/verdict、accepted Low 编号与其
writeback 落点、MiMo 路当前状态），把文件头状态改为反映 post-writeback 复审轮，并把 checkpoint stage 集合明确
枚举为 ``plan-fix`` + ``plan-review-*`` + ``plan-rereview-*`` + ``plan-acceptance-*``。

## 5. 信息性说明（不计 finding）

1. ``_build_production_services_provider`` 内的 ``EXPECTED_PRODUCTION_HANDLER_BATCH``（:692）是函数局部的大写
   常量。``§10:2566`` 直接引用了该名字，故计划层自洽；其命名/作用域是否合适属 implementation code review 范畴，
   不是 plan finding。
2. ``§14.1:3424`` 的 Gate 1 ``accepted_base=f0414fac…`` 是 Slice aggregate 口径，非 Item 7 增量口径；Item 7 只走
   ``§14.0``，二者不冲突，且该文本非本轮 writeback 引入，不在 Item 7 复审范围内。
3. ``docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md:755-757`` 的 accepted catalog 仍列三个旧名。
   按项目「不重写历史 accepted commit」约定，该文档为不可变历史记录，当前 named-test 真源以本 master ``§13``
   的 176 项为准；本 reviewer 不据此提出 finding。
4. 首审的两条信息性说明（Item 6 历史简版 docstring 不属 Item 7 修复义务；2961-2962 属既有已物化 register/seal
   tests）本轮独立复证仍成立。

## 6. Verdict

``FAIL / open H/M/L=0/1/1``。

- ``S23-I7-DSV4P-01``：**CLOSED**（``§13.1``/``§14.0.3`` writeback 有界且已进入可执行 AST 断言层）；
- 新增 open：``S23-I7-DSV4P-RR-01``（Medium）、``S23-I7-DSV4P-RR-02``（Low）。

除上述两项外，post-fix 冻结三元组、``§10``/``§10.1`` 六步对 preserved WIP 的可满足性、exact-six allowlist、
176 项 catalog 绝对算术、``§11.1`` singleton coverage owner、``§14.0`` 八步 validation contract、PG plain-Gate-2
定性、Item 7/Item 8 边界与 artifact/staging 规则，均只读核验一致，无 Blocking Question 留给 Controller。
本 review 未运行任何测试/PG/网络，未修改 plan、production 或 test 字节，只写本 artifact。
