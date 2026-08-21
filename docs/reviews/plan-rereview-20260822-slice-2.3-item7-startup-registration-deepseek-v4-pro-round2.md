# Slice 2.3 Item 7 startup registration corrective plan re-review round 2（DeepSeek V4 Pro）

- 日期：2026-08-22
- 角色：独立 plan reviewer（DeepSeek V4 Pro round-2 rereview，与 20260817 首审、20260822 首次复审同一 reviewer/model
  route）；非 Controller、非 Codex plan-fix writer、非 implementation writer
- actual model：``deepseek-v4-pro[1m]``；cwd ``/Users/wsk/workspace/dayu-agent``。二者与 dispatch 要求一致，未触发
  model/cwd STOP；本轮无 HTTP 402/配额失败。
- 结论：``FAIL / open H/M/L=0/1/2``
- 复审方式：五视角（architecture boundary / best practice / optimal solution / overengineering / overcoupling +
  failure-recovery + open questions + manifest-count-command 可执行性）自 byte0 fresh 重做；既复核本 route 上一轮
  ``S23-I7-DSV4P-RR-01``/``RR-02`` 的 corrective closure，也对整个 Item 7 plan 重做 adversarial
  code-generation-readiness review。不继承上一轮任何结论作为证据。
- 复审对象（post-writeback 冻结语义集合，本 artifact 只证明以下字节）：
  - target/master：``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md``，SHA-256
    ``8564c49f2657af61fe08d56480fac1e4f327be29d353efb33c58691f06162584``，3883 行 / 310791 字节；
  - fix：``docs/reviews/plan-fix-20260817-slice-2.3-item7-startup-registration-codex.md``，SHA-256
    ``8f3eb2008663ef4ed5deb9c9a97c48a89330ff74c612ee3dc56c240fb2dd9cf5``，165 行 / 12822 字节；
  - preserved WIP（未改写、未运行，只读复核）：``dayu/services/startup_preparation.py`` SHA-256
    ``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` / 1689 行 / 63289 字节；
    ``tests/application/test_service_startup_preparation.py`` SHA-256
    ``a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2`` / 4044 行 / 127443 字节；
  - 本 route 上一轮 corrective review（只读引用其 finding 编号与口径，证据全部本轮重取）：
    ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-deepseek-v4-pro.md``，SHA-256
    ``07b918fe6ce8b48c2d3bd67f702589018c9a77cf8ca13611cf6f8481197fea0f`` / 203 行 / 17178 字节。
- 漂移门：branch ``codex/investment-platform``；HEAD ``d604d8df7613db0103076b3a727156fd74dd9e1b``；
  ``git diff --cached --quiet`` 通过（index 空）；``git diff --check`` clean；tracked 修改仅
  master plan 与两份 preserved WIP。上述五份冻结身份逐项与 dispatch 冻结值 **零漂移**（见 §6）。
- 本 review 只读：零 plan/code/test/review 字节修改（除本 artifact 外）、零测试运行、零 PG/Docker/network/provider/model
  执行、零 stage/commit/push/PR、零 Git mutation。
- 独立性：本 artifact 不引用、不评价另一 review route 的任何输入或输出。master ``§17.2``、fix ``§9`` 中为账本而出现的
  该 route identity 只作为 plan 输入被检查其"账本位是否存在"，对应文件未被打开。披露：本轮有一次仓库级 ``grep`` 的
  候选路径集合可能包含该 route 的 artifact 路径，已在同一命令内以路径过滤排除，其字节未进入本 review 上下文。

## 1. 上一轮 accepted corrective 的 closure 复核

### 1.1 ``S23-I7-DSV4P-RR-01``（Medium，root README 三向互斥）：**部分闭合 / 见 RR2-01、RR2-03**

只读复核 writeback 实际落点：

- ``§11:2729`` 已从 exact-six 收口为「**七个且仅七个**path」，``:2737-2739`` 新增 ``README.md`` 并把可改面严格限定为
  当前 ``:385-387`` 一个段落、"该段以外root README字节zero diff"；``:2745-2747`` 的入选理由与 zero-diff 集合同步；
- 全文 **零 ``exact-six`` 残留**（机械 grep：``exact-six``/``exact-6``/``六个且仅六个``/``六个path`` 命中 0；唯一
  ``第六个path``:2848 属 Item 5 历史 exact-five 语境，与 Item 7 无关）；``exact-seven`` 覆盖 ``:2729``、``:2747``、
  ``:2866``、``:2897``、``:3308``、``:3351``、``:3401``、``:3414``、``:3423``、``:3630``、``:3662``、``:3875``，
  即 allowlist / 切片 / validation manifest / STOP / artifact-staging / residual / bookkeeping 七个面一致；
- ``§14.0.8:3394-3395`` 的机械 README 审计读入集合已扩为四份，root README 断言绑定到原 ``:385-387``；
- ``§15:3630`` 已改为「exact-seven 之外出现实现/README diff」；``§15:3620`` 的 root README zero-diff STOP 仍**正确地**
  只写给 prerequisite / Item 6 main；``§14:3565`` 的 Item 8 zero-diff 集合正确排除 ``tests/README.md``；
- 反向证据（本轮新取）：``dayu/fins/README.md`` 全文零 "production execution registry 为空" 类文本，因此
  ``§15:3633-3634`` 那条未限定文件集的「README 仍声明 production registry 为空」STOP，其可命中面恰好等于
  exact-seven 内的四份 README。原 RR-01 的「两条 STOP 必然触发其一」死锁**已消除**。

真值目标本轮逐条重证仍存在：root ``README.md:385-387``（三行一段，逐字与 ``§11:2737`` 引用一致）、
``tests/README.md`` 的 black-box "精确为 investment_identity / durable_jobs / durable_schedules 三个 Service"、
``dayu/README.md:156``、``dayu/investment/README.md:268-269``。四者确为 Item 7 落地即失真的旧真值，
``§14.0.8`` 对四份文件可判定。

**但闭合不完整**：``§10.1`` 这一 plan-fix 明文指定的 normative delta 段落仍写「三者」README（RR2-01，Medium），
且 root README 的 ``production Compose`` 语义未被区分（RR2-03，Low）。故 RR-01 判为 partial closure。

### 1.2 ``S23-I7-DSV4P-RR-02``（Low，轮次账本与 checkpoint stage 集合）：**CLOSED**

- 文件头 ``:4`` 已从「PLAN-FIX CANDIDATE / NOT REVIEWED」改为
  ``ITEM 7 … POST-REVIEW CORRECTIVE WRITEBACK CANDIDATE / … / DEEPSEEK V4 PRO REREVIEW FAIL 0/1/1 + MIMO REVIEW PASS
  0/0/0 RECORDED / IMPLEMENTATION AND TEST EXECUTION NOT AUTHORIZED / FRESH SAME-SHA DUAL PLAN REREVIEW REQUIRED``，
  与 normative 面已承载首审结论的事实一致；
- ``§17.2:3859-3862`` 冻结 historical initial DeepSeek 轮次：artifact 路径、SHA-256
  ``714dfa4f…`` / 115 行 / 9071 字节、``FAIL / open H/M/L=0/0/1``、accepted ``S23-I7-DSV4P-01`` 及其
  ``§13.1``/``§14.0.3`` writeback 落点。本轮以只读 ``shasum``/``wc`` 独立复算该 artifact identity，
  **三值逐项相符**，账本非杜撰；
- ``§17.2:3863-3868`` 冻结 current DeepSeek rereview 的 ``07b918fe…`` / 203 行 / 17178 字节 /
  ``FAIL 0/1/1``，与本轮冻结值逐字节一致，并逐条记录 RR-01/RR-02 的 accepted 状态与写回面；
- ``§17.2:3869-3873`` 为另一 review route 建立了轮次账本位并记录 Controller 的 ``rejected-with-reason`` 裁决
  （本 reviewer 只验证"账本位存在且结构与 ``§17.1`` 先例同构"，不打开、不引用、不评价该 route 的 artifact 或结论）；
- ``§17.2:3878-3881`` 明确当前状态为 ``POST-REVIEW FIX WRITTEN / AWAITING FRESH SAME-SHA DUAL PLAN REREVIEW``，
  不是 PASS、不授权 implementation/test/PG；
- ``§17.2:3882-3883`` 的 checkpoint stage 集合已按建议**逐 family 枚举**为：本 master + Item 7 ``plan-fix`` +
  ``plan-review-*`` + ``plan-rereview-*`` + ``plan-acceptance-*``，并显式排除两个 preserved WIP。
  可执行性复证：当前 untracked docs artifact 全部落入上述 family（本轮 ``git status --porcelain`` 只读观察，
  未逐一打开），故 checkpoint 之后 ``§14.0.1:3304`` 的 ``git ls-files --others --exclude-standard`` 可为空，
  dispatch preflight 不会因漏 stage 当场 STOP；两个 WIP 仍以 modified-tracked 形态保留，与文件头 Gate 的
  「working tree 仅有两项 preserved WIP，index/untracked empty」自洽。

**该 Low 不再 open。**

## 2. Fresh adversarial ledger（本轮独立重做，证据不复用任何历史轮次）

- **176 catalog 绝对算术**：以正则机械解析 ``§13`` 四小节 bullet named tests 得 13.1=54、13.2=42、13.3=53、13.4=27，
  合计 **176、零重复**，与 ``§13:2954``「当前总数精确为176，所有名字唯一」及 ``§14`` Gate 7:3543 的 aggregate 口径
  逐值相符。Item 7 五个 startup names 在 catalog 中各出现 **exactly once**；
- **旧 test-name negative AST regression set 可实施**：``§14.0.3:3323-3331`` 要求以 ``ast.parse`` 递归收集两个 test
  owner 的 ``FunctionDef/AsyncFunctionDef.name``。本轮以同一方法实测：四个旧名在当前 WIP 中各 **0 次**（原位改名已
  完成），其中三个在 ``HEAD:tests/application/test_service_startup_preparation.py`` 的 ``:1352``、``:2233``、``:2679``
  真实存在，第四个 ``test_production_provider_wires_exact_three_service_mapping`` 现存于
  ``tests/integration/investment/test_identity_repositories_postgres.py:1625``（class scope，缩进 ``def``，递归收集
  可覆盖）。即 negative set 是**针对真实回流风险的有意 regression guard**，且两份 owner 文件恰好覆盖全部四个旧名；
- **五个 new names 归属可判定**：前四项在 WIP application owner 各定义一次（``:2085``、``:3101``、``:3231``、
  ``:3623``；其中 ``:2085`` 位于 class 内，进一步证明"递归收集"是必需而非冗余），第五项由 PG black-box rename 产生、
  当前尚不存在，与 ``§13.1:3014-3016`` 的 owner 归属一致；
- **唯一 Low 的真实性与唯一性**：AST 复核五名 docstring —— 只有 ``:3101`` 的
  ``test_auto_production_registry_counts_are_exactly_one_and_service_mapping_is_exactly_four`` 为单行 docstring、
  无 ``Args/Returns/Raises``；其余三个 application names 三段齐备。其签名参数恰为 ``(monkeypatch, tmp_path)``，
  与 ``§14.0.3:3330`` 要求断言 ``Args`` 逐名含 ``monkeypatch:``/``tmp_path:`` **精确匹配**；参数化的
  ``:3231`` 多一个 ``failure_stage`` 但不在该断言集合内，无误伤；
- **§10.1 六步对 preserved WIP 逐项可满足**：``_build_production_services_provider``（:623）以同一
  ``preparation.session_factory``（:680）、同一 ``Host``/同一 ``DefaultFinsRuntime`` 只构造一个 ``FinsService``
  （:678）；构造序列 :678-691 与 §10.1 第 2 步同序且 public facade（``InvestmentSourcesService``:682）与 private
  execution owner（``SourceSyncExecutionService``:687 / ``SourceSyncExecutionHandler``:691）分离；
  register_descriptor→register_handler→descriptor seal→execution seal（:697-700）后**单处**断言双 sealed、
  两个 count == len(batch)、descriptor lookup ``!=`` 相等性与 handler ``is`` identity（:701-709），失败抛
  ``PlatformCompositionError``；provider 仅在断言后构造（:710），``provide_services``（:756-774）暴露精确四项
  ``investment_identity``/``investment_sources``/``durable_jobs``/``durable_schedules``，与 ``§10:2571``、
  ``§10.1:2598`` 逐 key 相符；auto 分支只调用一次 ``build_platform_composition``（:1539）且早于
  ``recover_host_startup_state``（:1543）；explicit 分支（:1455-1460）零 Source-specific 装配；失败路径
  （:1548-1573）沿 lifecycle/lease/s3/admission 既有逆序收口，engine 由 ``owned_lifecycle`` 唯一 dispose；
- **十九阶段 failure matrix 真实存在且可判定**：WIP tests 的 ``_ITEM7_FAILURE_STAGES`` 恰为 19 项，覆盖
  7 个 constructor + 2 个 register + 2 个 seal + 6 个 assert + ``provider_init`` + ``provide_services``，
  与 ``§10.1:2609``「十九阶段失败与逆序close」逐项相符，不是凑数表述；
- **§11.1 manifest 机械自洽**：``§11`` production allowlist 的 ``.py`` bullet 恰 44 个，``§11.1`` 表格 key 恰 44 个、
  唯一，二者 **set 完全相等**（差集双向为空），全部 tuple 非空且成员无重复；``dayu/services/startup_preparation.py``
  的 owner tuple 为 singleton ``(tests/application/test_service_startup_preparation.py,)``，与 ``§14.0.5:3353-3372``
  的 fresh exact-singleton branch coverage lane（``--include`` 单文件 + ``files`` exact singleton + raw combined
  ``>=80.0`` + 四个 exit）一致。README/workflow 非 Python，不进入 44 key，故 exact-seven 扩容不扰动该 matrix；
- **PG lane 定性正确**：``postgres_identity.py`` 不在 Item 7 exact-seven 内（changed set 只含
  ``startup_preparation.py`` 一个 production Python），故 ``§14.0.6:3384`` 定为 plain Gate 2、明令"不得生成或冒充其
  Gate 1 coverage"，与 ``§14`` Gate 2:3519-3522 的 unchanged-owner 规则一致；pinned digest 只读 ``docker image
  inspect``、禁止 pull/tag/skip/waive、要求单独 process 恰好一次且 fixture 零残留，均为可执行断言；
- **Item 7/Item 8 边界一致**：``§12:2870-2874`` 与 ``§14:3563-3565`` 一致地把 Item 8 限制为两份 workflow 的
  final 九 command/九 ignore + static audit + ``tests/README.md`` final-nine-lane 运行方法段，并明令 Item 7 已闭合的
  exact-four startup/black-box 文字与三份非 tests README zero diff；``§15:3634`` 反向 STOP「Item 8 再次改写已
  accepted startup 真值」。``tests/README.md`` 在两个 Item 中的可改段落互不重叠，无双写冲突；
- **artifact / reviewer / staging 面**：``§14.0`` 尾段（:3404-3425）冻结 implementation artifact 路径、
  ``candidate_diff_sha256`` 定义（baseline→candidate 的 exact-seven binary diff）、双路首审 artifact 路径与
  "首审 prompt 与上下文不得包含另一 reviewer 输出"、同 reviewer/model route 复审、"model/cwd/SHA 无法确认、
  HTTP 402、artifact 缺失、open 非 0/0/0 均不是 PASS"、以及 accepted checkpoint 只 stage exact-seven +
  本 Item artifact。链路完整、可执行、与 ``§17.2`` 的 plan-gate staging 规则不冲突；
- **architecture boundary / overengineering / overcoupling**：Item 7 只在 composition root
  （``dayu/services/startup_preparation.py``）装配，不反向依赖，public Source facade 与 private execution owner 分离，
  ``§11:2650`` 继续禁止 ``dayu/services/__init__.py`` re-export execution 类型；``§10.1:2617-2619`` non-goals 明确不
  新增第二 handler、不重构 composition、不新造 Source-specific lifecycle owner。exact-seven 不是过度扩张：四份
  README 各自携带一条被 Item 7 直接证伪的真值（本轮逐文件复证），PG black-box 是唯一 rename。未见 God object /
  多 owner 交叉写 / 隐性耦合；
- **failure & recovery**：``§10.1:2601-2603`` + 19 阶段矩阵 + ``§15:3631-3632`` 共同封住 partial mapping、
  重复 dispose、seal 后注册、explicit provider 被触碰四类失效；
- **open questions**：``§17.2:3874`` 与 fix ``§7`` 均声明零 Blocking Question，本轮未发现被隐藏的未决决定。

以上均只读成立。除下述三项 finding 外无其它异议。

## 3. Findings

### S23-I7-DSV4P-RR2-01（Medium）：``§10.1`` 这一 normative delta 段落仍把 Item 7 的 README 同步集写成「三者」，与已 accepted 的 exact-seven 真值直接冲突

精确位置：master ``:2612-2615``

> ……README只同步已物化真值：``tests/README.md``写black-box exact-four职责，``dayu/README.md``写高层
> composition/one handler边界，``dayu/investment/README.md``删除"production registry为空"的旧语句并写exact-one
> Source handler；**三者**都不得写Item 8尚未物化的final CI结果。

这是 ``§10.1 Item 7 corrective implementation handoff`` 内**唯一**逐文件列出 README 同步职责的句子，且是一个
闭合枚举（"三者"）。它与下列三处 active 真值互斥：

1. ``§11:2729`` + ``:2737-2739``：Item 7 writable allowlist 为 exact-seven，其中第四项就是 ``README.md``，
   并给出该文件的精确替换文本；``:2745-2747`` 明列四个新增候选 + ``dayu/investment/README.md``；
2. ``§12:2866-2868``：Item 7 顺序为「先修 application → 再 rename PG black-box → **最后按职责同步四份README**」；
3. ``§14.0.8:3394-3395``：机械审计"以UTF-8精确读取 ``README.md``、``tests/README.md``、``dayu/README.md`` 与
   ``dayu/investment/README.md`` **四份README**"，并断言 root README 的 ``:385-387`` 已被修改。

严重性来自 ``§10.1`` 的地位而非措辞：``docs/reviews/plan-fix-20260817-…-codex.md`` ``§3:57`` 逐字规定
「**Master §10.1是normative delta**。Writer不得发明新state，按以下顺序adopt现有实现」。即 dispatch 时 writer 被
明确指向 ``§10.1`` 作为落地契约。

hostile counterexample（两条路径都失败）：

- **路径 A（writer 信任 §10.1）**：按"三者"同步 README → 收尾时 ``§14.0.1:3307-3309`` 的
  「以NUL-safe tracked+untracked manifest证明changed implementation set **exact-equal** §11 Item 7 exact-seven」
  得到 6 个 path ≠ 7，fail closed；``§14.0.8:3395`` 的 root README 断言同时失败；``§15:3633-3634``
  「README仍声明production registry为空」STOP 触发。一次完整 Item 7 实施 + 全套 gate 之后才 STOP 回 Controller，
  且 STOP 时 working tree 已带 6 path 修改，与「preserve-and-adopt / 冻结身份」的回滚要求纠缠；
- **路径 B（谨慎 writer）**：``§12:2876-2877`` 规定「发现 plan contract无法构造或真实代码与计划矛盾时停止」。
  writer 在 dispatch 当场就会因 §10.1 与 §11/§12/§14.0.8 计数矛盾而 STOP，Item 7 **无法开始**。

这不是可容忍的冗余描述：``§17.2:3867`` 自述 RR-01 的写回面为「``§11`` exact-seven/root README单段边界、``§12``
Item 7/8切片、``§14.0`` 的allowlist/README/artifact/review/stage与``§15`` STOP」——``§10.1`` 不在其中，
证明这是**遗漏而非有意保留历史措辞**（对比 ``§13.3:3192``、``§11.1:2837`` 这类真正的历史陈述，都带
"historical"/"当时"/"本次"时间限定；``:2614`` 没有）。本条与 RR-01 同族：exact-seven 未穿透全部 active 面。

最小 docs-only fix（不改 normative implementation contract、allowlist、command、lane、Item 8 边界）：
把 ``:2612-2615`` 的 README 子句由三者扩为四者，插入 root ``README.md``（只改当前 ``:385-387`` 一段、其余字节
zero diff，内容以 ``§11:2737-2739`` 为准），并把"三者"改为"四者"。

severity：**Medium**。

### S23-I7-DSV4P-RR2-02（Low）：三处 ``174`` catalog 计数未随 ``176`` 写回，其中一处是 imperative 的 collector 规格

精确位置与原文：

- ``:2304``：「……下述12项named tests、44 mapping keys、**174 final catalog**、六个migration/PG owner、Item 6 main
  exact20/51与Item 8 workflow/docs defer全部保持不变。」
- ``:3255``：「……不得为这些cases动态生成、alias或增加catalog test名，prerequisite仍是12项、**overall仍174项**。」
- ``:3270``：「**机械collector必须证明**新增15项、两个rename、**总数174**及Item 6 main51/prerequisite12的file
  ownership，禁止一个test跨文件重复。」

对照当前真值：``§13:2951-2955``「……故当前总数精确为**176**，所有名字唯一」；``§14`` Gate 7:3543「只有Item 8更新
final workflows后，Slice aggregate gate才要求``§13``全部**176**项exact names各一次」。本轮已机械复算
54+42+53+27=176、零重复，**176 才是真值**。

同一轮 writeback 在**兄弟位置**已经做对：``§13.3:3192`` 写成「Item 6完成时的 **historical** aggregate named catalog
为174；Item 7加入``§13.1``两个startup delta后，final aggregate要求``§13``全部**176**个exact names各出现一次」。
即正确句式已存在，只是没有施加到上述三处。

hostile counterexample：``:3270`` 是命令式规格（"机械collector必须证明……总数174"），并非历史叙述，也无任何时间限定。
Item 8 / Slice aggregate writer 若以 ``§13.4`` 作为 collector 规格（它正是 ``§13.4`` 内唯一一处逐项列出 collector
必须证明什么的句子），会以 174 为期望值执行 named-test audit：实测 176 → 要么 STOP，要么反向"修正" ``§13`` 删掉
Item 7 的两个 startup delta 名 —— 后者恰是 ``§15:3634``「Item 8再次改写已accepted startup真值」明令禁止的动作，
而 collector 规格本身正在诱导它。``:2304`` 的"**final** catalog"措辞加重该风险：它把一个已被 supersede 的数字标为
"final"。

不阻断 Item 7 本身：``§14.0`` 只做 ``§14.0.3`` 的五名 incremental AST 审计，不跑 aggregate catalog；故降级为 Low。

最小 docs-only fix：按 ``§13.3:3192`` 既有句式给三处加时间限定，例如 ``:3270`` 改为「机械collector必须证明新增15项、
两个rename、Item 6 完成时的 historical 总数174（Item 7 后 final aggregate 为176）及……」；``:2304`` 的
"174 final catalog" 改为 "当时的174项catalog"；``:3255`` 的 "overall仍174项" 改为 "当时overall仍174项"。
不改 ``§13`` 名单、``§14`` Gate 7、任何 count 真值或 file ownership。

severity：**Low**。

### S23-I7-DSV4P-RR2-03（Low）：root README 的 ``production Compose``（部署编排文件）被与 ``production composition``（平台装配）混同，使 ``§14.0.8`` 断言面与 zero-diff 冻结面相撞

精确位置：``§11:2737-2739``（规定的替换文本）与 ``§14.0.8:3395-3398``（机械断言）。

只读事实（本轮独立取证）：

- root ``README.md:386`` 的 "不包含 production Compose" 与 ``README.md:134`` 的
  「与 Redis 服务，本仓库当前不提供 **production Compose**」是**同一条部署编排文件声明**，不是平台 composition；
- 仓库确无任何 compose 资产（``git ls-files`` 中无 ``docker-compose*.yml``/``compose*.yml``），Item 7 的 allowlist
  与 non-goals 也不新增，故该声明 Item 7 前后**都为真**，未被证伪；
- ``§14.0.8:3396`` 的断言主语是文件级的 "root``README.md``"，谓语含「不再声称 production execution registry为空/
  无Source handler/**无production composition**」；同段结尾又要求「其余root README字节zero diff」。

hostile counterexample A（gate 不可满足）：``§14.0.8`` 对 ``dayu/README.md``/``dayu/investment/README.md`` 的同族断言
写法是"文件不再含旧真值"（``:3399-3400``），机械实现自然也按文件级施加到 root README。此时 ``README.md:134`` 的
"不提供 production Compose" 命中 "无production composition" 这一 negation family → 断言失败；唯一出路是修改 ``:134``
→ 撞 ``§11:2739``「该段以外root README字节zero diff」与 ``§14.0.8`` 同句的 zero-diff 要求 → STOP。这与 RR-01 已
关闭的死锁同型，只是量级更小。

hostile counterexample B（真值删除）：``§11:2737-2739`` 规定的替换文本删掉了 ``:386`` 的 "不包含 production Compose"
而未说明理由。``AGENTS.md``「文档与 README 同步」硬约束是"只更新 README 中与当前代码不一致的部分"；删除一条仍然
成立、且面向用户的交付边界声明超出"最小真值修正"。（缓解事实：同一声明在 ``:134`` 保留，故不产生假陈述——
这也是本条只判 Low 的原因。）

最小 docs-only fix（二选一或同做）：

- ``§14.0.8:3395-3397`` 把断言收窄为段落级并显式豁免部署声明，例如「原``:385-387``段落不再声称 production execution
  registry 为空、不含 Source handler、不构造/发布 production composition；root README 其余段落（含 ``:134`` 的
  production Compose **部署**声明）不进入该断言集合且保持 zero diff」；
- ``§11:2737-2739`` 明确该 clause 的处置：或在替换文本中保留 "不包含 production Compose"，或写明"因与 ``:134``
  重复而有意省略"。

severity：**Low**。

## 4. 信息性说明（不计 finding）

1. WIP ``:692`` 的 ``EXPECTED_PRODUCTION_HANDLER_BATCH`` 是函数局部大写常量，注解为 variadic
   ``tuple[tuple[...], ...]``；``:704-705`` 断言 ``count == len(BATCH)`` 而非 ``§10:2566`` 字面的 "==1"。
   plan 层表述（``§10:2566``、``§10.1:2595``「count均为1」）本身正确，且 ``§13.1:2966`` 的 exactly-one 具名测试
   覆盖该语义；常量作用域与断言形态属 implementation code review 范畴，不是 plan finding。
2. ``§14.0.1:3300-3304`` 的 ``shasum``/``wc -l``/``git ls-files --others`` 三条命令只打印值、恒 exit 0，
   "任一非零立即STOP" 无法机械捕获 untracked 非空。散文层已给出期望值，且实施后 manifest（``:3307-3309``）与
   ``§15:3630`` 对 implementation path 污染 fail closed，残余风险仅限 docs 类 untracked（``:3308`` 本就"另列"）。
   不计 finding。
3. ``§13.1:3014``「上述五个startup names」未加显式标号，而相邻的 ``:2964-2965`` 两个 register/seal 名语义相近。
   本轮复证二者定义在 ``tests/application/test_job_service.py``（非 Item 7 owner file），配合 ``:3015-3016`` 的
   owner 归属与 PG black-box 唯一名可唯一识别；误识别亦 fail closed。不计 finding。
4. plan-fix ``§§1-8`` 仍含 "exact-six / 六个path"（``§2.2``）与 "root README……zero diff"（``§2.3``）等旧措辞，
   但 ``§9:161-163`` 以**逐项 enumerated supersede**（明列 exact-six、root README zero-diff、旧 review 状态三项）
   声明其为历史 wording 且"不得再作为active dispatch输入"，并把真源指回 master ``§11``/``§14.0``/``§17.2``。
   符合本 plan family 的 preserve-history 约定，不计 finding。
5. ``§14`` Gate 1:3431 的 ``accepted_base=f0414fac…`` 是 Slice aggregate 口径；Item 7 只走 ``§14.0``，二者不冲突，
   且非本轮 writeback 引入。
6. ``§8.6:2312``「根``README.md``保持zero diff」经上下文复核确属 0006 prerequisite 作用域（``:2310-2318``），
   不是 Item 7 约束，与 exact-seven 无冲突——特此记录，避免被误读为第四处 exact-seven 漂移。

## 5. Verdict

``FAIL / open H/M/L=0/1/2``（fresh open：High 0、Medium 1、Low 2）。

- ``S23-I7-DSV4P-01``（首审 Low）：仍 **CLOSED**（``§13.1:3017-3021``/``§14.0.3:3323-3331`` 的 fail-closed 旧名集
  本轮独立复证有效且必要）；
- ``S23-I7-DSV4P-RR-01``（Medium）：**部分闭合**——三向互斥与检测盲区已消除，但 exact-seven 未穿透 ``§10.1``
  且 ``production Compose`` 语义未区分，其残余部分转为下列两条新 finding，不再以 RR-01 编号 open；
- ``S23-I7-DSV4P-RR-02``（Low）：**CLOSED**；
- 新增 open：``S23-I7-DSV4P-RR2-01``（Medium）、``S23-I7-DSV4P-RR2-02``（Low）、``S23-I7-DSV4P-RR2-03``（Low）。

三条均为 docs-only、位置精确、修复不触碰 normative implementation contract、exact-seven allowlist、44-key matrix、
validation command、lane、count 真值或 Item 8 边界。无 ``Blocking Questions For Controller``。

除上述三项外，post-writeback 冻结集合、``§10``/``§10.1`` 六步对 preserved WIP 的逐行可满足性、exact-seven 在
allowlist/validation/artifact/review/staging/STOP/Item 8 七个面的一致性、176 项 catalog 绝对算术、五个 delta names
与四个旧名的 AST 可判定性、19 阶段 failure matrix、``§11.1`` 44-key/singleton coverage owner、``§14.0`` 八步
validation contract、PG plain-Gate-2 定性、Item 7/Item 8 边界与 ``§17.2`` 轮次账本/checkpoint family，均只读核验一致。

## 6. START = END 边界证明

本 review 期间唯一写入为本 artifact；五份冻结文件在 review 起止两次独立 ``shasum -a 256`` + ``wc -l`` + ``wc -c``
逐项相等，零漂移：

| 冻结对象 | START = END SHA-256 | 行 | 字节 |
|---|---|---|---|
| ``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`` | ``8564c49f2657af61fe08d56480fac1e4f327be29d353efb33c58691f06162584`` | 3883 | 310791 |
| ``docs/reviews/plan-fix-20260817-slice-2.3-item7-startup-registration-codex.md`` | ``8f3eb2008663ef4ed5deb9c9a97c48a89330ff74c612ee3dc56c240fb2dd9cf5`` | 165 | 12822 |
| ``dayu/services/startup_preparation.py``（preserved WIP） | ``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` | 1689 | 63289 |
| ``tests/application/test_service_startup_preparation.py``（preserved WIP） | ``a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2`` | 4044 | 127443 |
| ``docs/reviews/plan-rereview-20260822-…-deepseek-v4-pro.md``（本 route 上一轮） | ``07b918fe6ce8b48c2d3bd67f702589018c9a77cf8ca13611cf6f8481197fea0f`` | 203 | 17178 |

- branch START = END = ``codex/investment-platform``；HEAD START = END =
  ``d604d8df7613db0103076b3a727156fd74dd9e1b``；
- ``git diff --cached --quiet`` 通过（index 空）、``git diff --check`` clean，START/END 两次观察一致；
- 本 review 未 stage/commit/push/开 PR，未执行任何 Git mutation，未运行 tests/PG/Docker/network/provider/model；
- 未修改任何 plan/code/test/其它 review artifact；唯一新增文件为本 artifact
  ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-deepseek-v4-pro-round2.md``。
