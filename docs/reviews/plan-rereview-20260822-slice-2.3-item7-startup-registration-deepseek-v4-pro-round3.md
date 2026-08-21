# Slice 2.3 Item 7 startup registration corrective plan re-review round 3（DeepSeek V4 Pro）

- 日期：2026-08-22
- 角色：独立 plan reviewer（DeepSeek V4 Pro round-3 rereview，与 20260817 首审、20260822 首复、20260822 round-2
  同一 reviewer/model route）；非 Controller、非 Codex plan-fix writer、非 implementation writer。
- actual model：``deepseek-v4-pro[1m]``；route：local Claude Code CLI user-dispatch；cwd
  ``/Users/wsk/workspace/dayu-agent``。三者与 dispatch 要求一致；本轮无 HTTP 402/配额失败。
- 结论：``PASS / open H/M/L=0/0/0``
- 复审方式：五视角（架构边界与最佳实践 / 状态-恢复-部分失败 / manifest-count-command 可构造性 / 规范一致性 /
  账本与过程纪律）自 byte0 fresh 重做。既复核 SA25（round-2）三项 accepted finding 的 corrective closure，也对整个
  Item 7 plan 重做 adversarial code-generation-readiness review；不继承任何历史轮次结论作为证据。
- 复审对象（冻结语义集合，本 artifact 只证明以下字节）：
  - master：``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md``，SHA-256
    ``6f809046d09a649ba306f55d0d6348e9d56eb99c8fad2c640716e912e5c5bf6f``，3903 行 / 312988 字节；
  - fix：``docs/reviews/plan-fix-20260817-slice-2.3-item7-startup-registration-codex.md``，SHA-256
    ``bd741b02eca4f493d183f72f99d7c9eda50861f383aaf0eab2e030ced8769d5b``，196 行 / 15624 字节；
  - preserved WIP（未改写、未运行，只读复核）：``dayu/services/startup_preparation.py`` SHA-256
    ``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` / 1689 行 / 63289 字节；
    ``tests/application/test_service_startup_preparation.py`` SHA-256
    ``a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2`` / 4044 行 / 127443 字节；
  - 本 route 历史 review（只读引用其 finding 编号与口径，证据全部本轮重取；独立复算其身份见 §5）：
    ``docs/reviews/plan-review-20260817-slice-2.3-item7-startup-registration-deepseek-v4-pro.md``（
    ``714dfa4f…`` / 115 行 / 9071 字节，``FAIL 0/0/1``）、
    ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-deepseek-v4-pro.md``（
    ``07b918fe…`` / 203 行 / 17178 字节，``FAIL 0/1/1``）、
    ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-deepseek-v4-pro-round2.md``（
    ``a6e70440…`` / 320 行 / 29220 字节，``FAIL 0/1/2``）。
- 漂移门：branch ``codex/investment-platform``（``.git/HEAD`` 与 refs 只读核验）；HEAD
  ``d604d8df7613db0103076b3a727156fd74dd9e1b``。本 review 全程不运行 Git 命令、不运行 tests/pyright/PG/Docker/
  network/provider/model，零 stage/commit/push/PR；只写本 artifact（见 §6 边界证明）。
- 独立性：本 artifact 不读取、不引用、不评价另一 review route（MiMo）的任何 artifact。未打开
  ``docs/reviews/plan-review-20260822-slice-2.3-item7-startup-registration-mimo.md``、
  ``docs/reviews/plan-rereview-20260822-slice-2.3-item7-startup-registration-mimo-round2.md`` 或任何其它 MiMo 文件；
  master/fix 中出现的 MiMo identity/verdict 只作为“账本位是否存在”的 plan 输入被检查，不作为审查证据。

## 1. SA25（round-2）三项 accepted finding 的 closure 复核

### 1.1 ``S23-I7-DSV4P-RR2-01``（Medium，§10.1 “三者”与 exact-seven 冲突）：**CLOSED**

只读复核 writeback 实际落点（fix §10 声称 ``§10.1:2609-2618``）：

- ``§10.1:2614-2618`` 现为逐文件职责枚举：root ``README.md``（只改 ``:385-387`` 失真段落、保留
  ``本仓库当前不提供 production Compose`` 部署真值、其余字节 zero diff）、``tests/README.md``（black-box
  exact-four/``investment_sources`` 职责）、``dayu/README.md``（高层 platform production composition /
  exact-one Source Sync handler 边界）、``dayu/investment/README.md``（删除“production registry为空”旧语句并写
  exact-one Source Sync handler、无 research/Agent/Broker handler）；``:2618`` 结尾为「**四者**都不得写 Item 8
  尚未物化的 final CI 结果」。机械 grep：全文不再存在指 README 集合的“三者”，``四者`` 唯一命中即 ``:2618``。
- 与其它 active 面逐项一致：``§11:2732``「七个且仅七个path」、``§12:2874``「最后按职责同步**四份README**」、
  ``§14.0.8:3400-3401`` 读入集合恰为这四份、``§15:3639``「exact-seven之外出现实现/README diff」、
  ``§17.2:3895-3896``「四份职责内README在Item 7同步」。原 RR2-01 的“writer 按 §10.1 行事必撞 exact-seven
  manifest / 谨慎 writer 无法开工”两条 counterexample 均已不可构造。

### 1.2 ``S23-I7-DSV4P-RR2-02``（Low，三处 174 未加阶段限定）：**CLOSED**

只读复核三处写回：

- ``§8.6:2304-2305``：「Item 6完成时的**historical** catalog=174（Item 7后**final** aggregate=176）」；
- ``§13.4:3260``：「prerequisite仍是12项、**Item 6 phase当时**overall仍174项；**Item 7完成后的final
  aggregate为176项**」；
- ``§13.4:3276``：「机械collector必须在**Item 6 phase**证明……**historical**总数174及……file ownership，并在
  **Item 7/aggregate phase**证明**final**总数176」。

全文 174/176 命中复核（机械 grep + 逐条目视）：除上述三处外，``:2958-2959`` 为 159→174→176 完整链、
``:3197`` 与 ``:3552`` 为 phase-qualified 真值；其余 174 命中全部位于 ``§17.1`` 与 ``§17.2`` 的历史/账本叙述
（Item 6 acceptance 事件记录与「174 exact names…保持不变」的历史结论），无一处是未加时间限定的 imperative
count 规格。``§14`` Gate 7:3552 的 aggregate 口径仍为 176。imperative collector 已无 174 期望值。

### 1.3 ``S23-I7-DSV4P-RR2-03``（Low，production Compose 与 production composition 混同）：**CLOSED**

只读复核两处写回：

- ``§11:2742-2744``：替换文本保留「本仓库当前不提供 production Compose」并追加
  「``production Compose``仅指部署编排文件，与platform ``production composition``严格区分；该段以外含
  ``README.md:134``现有production Compose部署声明均字节zero diff」；
- ``§14.0.8:3403-3407``：断言收窄为「仅对root``README.md``原``:385-387``的replacement paragraph按大小写与术语
  精确检查」；「``production Compose``仅指部署编排，platform ``production composition``仅指平台装配，两个
  case-sensitive term不得互为旧真值命中」；「``README.md:134``的现有production Compose部署声明不进入该段
  断言集且字节zero diff」。

本轮 fresh 独立取证（只读 sed）确认两个可机械实施前提仍成立：root ``README.md:134`` 逐字为
「与 Redis 服务，本仓库当前不提供 production Compose。」（部署编排声明，Item 7 前后均为真）；``README.md:385-387``
恰为三行失真段落（「production execution registry 为空，不包含 source/research/Agent/Broker handler…」）。原
RR2-03 的 counterexample A（:134 被文件级否定断言误命中）与 counterexample B（部署真值被无理由删除）均已不可构造。

## 2. Fresh adversarial ledger（本轮独立重做，证据不复用任何历史轮次）

### 2.1 架构边界与最佳实践（architecture boundary / best practice / optimal solution / overengineering / overcoupling）

- 本轮重新逐行走查 preserved ``dayu/services/startup_preparation.py``：``_build_production_services_provider``
  （:623）以同一 ``preparation.session_factory`` 构造 Job/Schedule/Source stores、同一 ``Host`` 与同一
  ``DefaultFinsRuntime`` 只构造一个 ``FinsService``（:678）；构造序列 :658-691 与 ``§10.1:2591-2594`` 第 2 步
  逐项同序；public facade（``InvestmentSourcesService``:682）与 private execution owner
  （``SourceSyncExecutionService``:687/``SourceSyncExecutionHandler``:691）分离；register→register→seal→seal
  （:697-700）后单处断言双 sealed/count/lookup/identity（:701-709），失败抛 ``PlatformCompositionError``；
  provider 仅在断言后构造（:710），``provide_services``（:756-774）暴露精确四项；auto 分支只调用一次
  ``build_platform_composition``（:1539）且早于 ``recover_host_startup_state``（:1543）；explicit 分支
  （:1455-1462）零 Source-specific 装配。
- Item 7 只修改 composition root 一处 production Python，不反向依赖、不新建 God object、不新增第二个 handler、
  不为 Source Service/handler/registry 另造 close/atexit/thread/timer owner（``§10.1:2601-2604``）。exact-seven
  不是过度扩张：四份 README 各自携带一条被 Item 7 直接证伪的真值（本轮逐文件 sed 复核：root
  ``README.md:385-387``、``tests/README.md:53`` exact-three、``dayu/README.md:155-156`` registry 为空、
  ``dayu/investment/README.md:268-269`` registry 为空），PG black-box 是唯一 rename；``dayu/fins/README.md``、
  两份 workflow 与其余 path zero diff（``§11:2752``）与 AGENTS.md 分层/文档职责约束一致。

### 2.2 状态、恢复与部分失败（state / recovery / partial failure）

- preserved WIP tests 的 ``_ITEM7_FAILURE_STAGES``（:641-661）恰为 19 项 constructor/register/seal/assert/
  provider/publish 全序，与 ``§10.1:2609``「十九阶段失败与逆序close」逐项相符；19 阶段任一失败断言
  ``close_order == ["pg", "lease", "s3", "redis"]`` 各 exactly once（:3302-3310），engine 由 identity_service
  唯一 dispose，composition attempts 除 ``provide_services`` 阶段外为零（:3296-3298）。
- explicit-provider test（:2085-2257）用 trap 断言 ``platform_preparation``/``source_assembly_root``/
  ``fins_service``/``source_connector``/``source_repository``/``connector_registry``/``source_service``/
  ``execution_service``/``source_handler``/``descriptor_register``/``handler_register`` 全部零命中，且 caller
  registry 的 storage identity/count/sealed 状态逐项不变——与 ``§10.1:2605-2607`` 第 6 步逐项对应。
- publish-before-recovery、single-publish、逆序收口由 ``§10.1:2600-2604`` + ``§15:3640-3641`` 共同封住 partial
  mapping / 重复 dispose / seal 后注册 / explicit provider 被触碰四类失效。

### 2.3 manifest / count / command 可构造性（code-generation-readiness）

- **exact-seven writer allowlist**：``§11:2732-2753`` 枚举七个 path 且逐 path 冻结可改面；``§14.0.1:3313-3315``
  以 NUL-safe manifest 证明 changed set exact-equal。可机械实施。
- **PG black-box exact-four**：本轮 sed 复核 ``tests/integration/investment/test_identity_repositories_postgres.py``
  ～:1625-1712：现为 class-scope ``TestProductionStartupBlackBox.test_production_provider_wires_exact_three_service_mapping``，
  exact-three key 断言 + 真实 ``register_company_security`` identity register + 两次 ``prepared.close()``
  double-close 均实存，与 ``§10.1:2610-2614`` 的 rename/保留断言合同一致；第四项协议断言
  （``PlatformSourceSyncServiceProtocol``/``InvestmentSourcesService``/共享 session factory）全部由已物化对象可达。
- **§14.0 八步 validation contract**：focused+architecture 双 process（:3317-3326）、AST 五名 exactly-once +
  四旧名零次 + docstring heading/``monkeypatch:``/``tmp_path:`` 断言（:3329-3337，与 :3101 测试真实签名精确匹配）、
  三 Python path Pyright 0/0/0 + Ruff F/I（:3341-3354）、fresh exact-singleton branch coverage ``>=80.0``
  （:3361-3377）、pinned PG16 digest 只读 inspect + 单独 process 恰好一次 + 零残留 + plain Gate 2（:3382-3390，
  digest 与 ``§14`` Gate 2:3502 同一 pinned 值）、全仓 non-integration 独立 process（:3392-3398）、四 README
  机械断言 + LF/final-newline/allowlist/index audit（:3400-3411）。命令逐条可执行，无 placeholder 残留。
- **process isolation**：focused 两个 pytest process、PG 单独 process、non-integration 单独 process、coverage
  fresh mktemp 目录（``test ! -e`` 前置断言），无组合有状态 owner。
- **artifact / staging / reviewer round bookkeeping**：``§14.0:3413-3434`` 冻结 implementation artifact 路径、
  ``candidate_diff_sha256`` 定义、双路首审 artifact 路径与内容隔离、同 reviewer/model route 复审、
  「402/model/cwd/SHA 不明或缺 artifact 均不是 PASS」、accepted checkpoint 只 stage exact-seven + 本 Item artifact；
  ``§17.2:3902-3903`` 冻结 plan checkpoint 的 ``plan-fix``/``plan-review-*``/``plan-rereview-*``/
  ``plan-acceptance-*`` family 并排除两个 preserved WIP。两套 staging 规则互不冲突，且覆盖本轮新增的
  ``plan-rereview-*-round3`` 形态。

### 2.4 规范一致性（exact-seven / 四 README / 174-176 / Compose 术语 / Item 8 defer）

- 机械 grep：全文零 ``exact-six``/``exact-6``/``六个且仅六个`` 残留；``exact-seven`` 命中 :2732/:2752/:2871/
  :2902/:3314/:3357/:3410/:3415/:3423/:3432/:3639/:3671/:3876/:3895，全部与 exact-seven 真值同向，无矛盾句。
- ``§12:2871-2879`` 与 ``§14:3557-3574`` 一致地把 Item 8 收窄为两份 workflow + ``tests/README.md``
  final-nine-lane 运行方法段，两份 Dayu README 与 root README 在 Item 8 zero diff；``§11:2745`` 把 tests/README
  的 final CI 命令 defer Item 8——两个 Item 在 tests/README 的可改段落互不重叠，无双写冲突。
- catalog 计数：本轮复核 174/176 全部命中均带阶段限定（见 §1.2）；176 算术链（158→159→174→176）与
  ``§13:2956-2960`` 叙述、``§14`` Gate 7 aggregate 口径一致。Item 7 五个 startup names 的 owner 归属
  （前四 application、唯一 PG）与 preserved WIP 现状一致：:2085（class scope）、:3101、:3231（parametrized）、
  :3623 各定义 once，PG 名当前不存在（rename 目标），与 ``§13.1:3019-3021`` 逐项相符。
- Compose/composition 术语：``§10.1:2615``、``§11:2742-2744``、``§14.0.8:3403-3406`` 三处均 case-sensitive
  区分部署 ``production Compose`` 与平台 ``production composition``，``README.md:134`` 排除一致。

### 2.5 账本与过程纪律

- ``§17.2:3868-3893`` 已冻结本 route 全部历史轮次与另一 route 的轮次账本位；本轮以只读 ``shasum``/``wc``
  独立复算三个 DeepSeek artifact：``714dfa4f…``/115/9071、``07b918fe…``/203/17178、``a6e70440…``/320/29220，
  与 master ``§17.2``、fix ``§9``/``§10`` 账本逐值相符，账本非杜撰。
- 文件头 :4 与 ``§17.2:3898-3903`` 均明确 ``POST-REVIEW FIX WRITTEN / AWAITING FRESH SAME-SHA DUAL PLAN
  REREVIEW``、不授权 implementation/test/PG；fix §10 声明的 master END
  ``6f809046…``/3903/312988 与本轮 START 实测逐值相符。
- fix §10 声称的 writeback 落点（``§10.1:2609-2618``、``§8.6:2304-2306``、``§13.4:3259-3260``/``:3275-3277``、
  ``§11:2740-2744``、``§14.0.8:3400-3407``）本轮逐锚点目视复核，全部实存且内容与声明一致。

## 3. Findings

**无 material finding。**

## 4. 信息性说明（不计 finding，不构成 open question）

1. ``§17.1`` 标题仍带「（current）」且其账本句为「Current normalized ledger：…exact named catalog为174」。
   该节内容为 Item 6 acceptance 的历史事件叙述，``§17.2:3866-3867`` 已显式声明「当前入口唯一以文件头Gate与
   本节为准」，且无任何 executable 规格引用 ``§17.1`` 的 174（imperative collector 均位于 ``§13.4``/``§14`` 且已
   phase-qualified）。与 plan family 的 preserve-history + supersede 约定一致。可选改进：把 ``§17.1`` 标题
   ``（current）`` 改为 ``（historical）``，非本轮必须。
2. ``§14.0.8`` 对 root README 的断言锚点「原``:385-387``」是 pre-edit 行号；替换后段落行号会平移。因 ``§11``
   已把替换文本逐字冻结，writer 可机械地以冻结文本（如「本仓库当前不提供 production Compose，也不会自动调用
   真实provider、模型、Broker」）唯一定位替换段，故不构成可构造性缺口。
3. ``§14.0.1`` 的 ``shasum``/``wc -l``/``git ls-files --others`` 三条命令只打印值、恒 exit 0，无法单凭命令
   exit 捕获漂移；散文层给出期望值，且实施后 manifest（:3313-3315）与 ``§15:3639`` 对 implementation path
   污染 fail closed。此点 round-2 信息性说明已记录，本轮复证未变化。
4. ``§14.0`` 尾段与 ``§17.2`` 冻结的 implementation/code-review artifact 文件名仍以 20260817 为日期段，是
   deterministic 命名的有意决定，利于账本冻结；不构成阻塞。
5. ``§14.0.8`` 对两份 Dayu README 的「只声明exact-one Source Sync handler、无research/Agent/Broker handler」
   为散文级表述，其可机械执行面由三条具体断言承担（不再含 registry 为空旧真值、exact-four/investment_sources、
   不含 Item 8 final-nine-lane 完成声明），可实施。

## 5. Open questions / residual risks

- open H/M/L = 0/0/0；无 ``Blocking Questions For Controller``。
- residual 仍以 master ``§16`` 既有清单为准（provider 非 exactly-once、source/Job 双事务窗口、Redis hint
  语义、health disabled 的 no-op Job、bounded pool/connect/statement timeout 留待 reliability gate、无 typed
  code 的 Job/Schedule repository failure 映射、0006 upgrade 保真优先 admission、``git fsck`` repo-health
  独立工作单）。本轮未发现新增 residual。

## 6. START = END 边界证明

- 本 review 期间唯一写入为本 artifact；五份 required 文件在 review 起止两次独立 ``shasum -a 256`` + ``wc -l`` +
  ``wc -c`` 逐项相等（END 实测见下），零漂移：

| 冻结对象 | END SHA-256 | 行 | 字节 |
|---|---|---|---|
| ``docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`` | ``6f809046d09a649ba306f55d0d6348e9d56eb99c8fad2c640716e912e5c5bf6f`` | 3903 | 312988 |
| ``docs/reviews/plan-fix-20260817-slice-2.3-item7-startup-registration-codex.md`` | ``bd741b02eca4f493d183f72f99d7c9eda50861f383aaf0eab2e030ced8769d5b`` | 196 | 15624 |
| ``dayu/services/startup_preparation.py``（preserved WIP） | ``73309aba4502a695c31ab6629b37b000ca1717fa4690f951c30a1fddda3db23e`` | 1689 | 63289 |
| ``tests/application/test_service_startup_preparation.py``（preserved WIP） | ``a0010b1e129744dbec36b9f76d91614cc642a9b53de2c5a591f16fdf12dcf1f2`` | 4044 | 127443 |
| ``AGENTS.md`` | ``a23286913c328e1041659a8bc58c49345a23cec89ab78127123228a532f9296e`` | 109 | 7200 |

- branch START = END = ``codex/investment-platform``；HEAD START = END =
  ``d604d8df7613db0103076b3a727156fd74dd9e1b``（``.git/HEAD``/refs 只读核验，未运行任何 Git 命令）。
- 独立性：未打开任何 MiMo artifact；master/fix 中 MiMo identity/verdict 仅作账本位存在性检查。
- 本 review 未运行 tests/pyright/PG/Docker/network/provider/model，未修改任何 plan/code/test/README/旧 review
  字节，未 stage/commit/push/PR；唯一新增文件为本 artifact。

## 7. Verdict

``PASS / open H/M/L=0/0/0``。

- ``S23-I7-DSV4P-01``（首审 Low）：仍 CLOSED；
- ``S23-I7-DSV4P-RR-01``（Medium）、``S23-I7-DSV4P-RR-02``（Low）：仍 CLOSED；
- ``S23-I7-DSV4P-RR2-01``（Medium）、``S23-I7-DSV4P-RR2-02``（Low）、``S23-I7-DSV4P-RR2-03``（Low）：
  本轮 fresh 复核全部 CLOSED（§1 逐项证据）；
- 本轮新增 material finding：0；open H/M/L=0/0/0；无 qualified pass。

本 PASS 只证明 §0 冻结语义集合与上述 closure，不授权 implementation/test/PG；下一入口是 Controller 按
``§17.2`` 对双路 same-SHA fresh rereview 的 acceptance 与 docs-only local accepted plan checkpoint。
